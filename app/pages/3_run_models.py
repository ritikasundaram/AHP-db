import bootstrap

import streamlit as st
from sqlalchemy import text

from persistence.engine import get_engine
from services.scenario_service import ScenarioService
from services.topsis_service import TopsisService
from services.ahp_service import AHPService
from persistence.repositories.result_repo import ResultRepo
from persistence.repositories.run_repo import RunRepo
from persistence.repositories.ahp_repo import AHPRepo
from core.ahp import upper_size, matrix_from_upper, compute_priority

st.title("Step 3: Run Models")

engine = get_engine()
scenario_id = st.session_state.get("scenario_id")
user_name = st.session_state.get("user_name", "")

if not scenario_id:
    st.info("Go to Step 1 and select a Scenario first.")
    st.stop()

nav_left, nav_right = st.columns(2)
with nav_left:
    if st.button("Back: Step 2 (Data Input)"):
        st.switch_page("pages/2_data_input.py")
with nav_right:
    if st.button("Next: Step 4 (Results)"):
        st.switch_page("pages/4_results.py")

st.divider()

with engine.begin() as conn:
    prefs = conn.execute(
        text("""
            SELECT preference_set_id::text AS preference_set_id, name, type, status, created_at
            FROM preference_sets WHERE scenario_id = :sid ORDER BY created_at DESC
        """),
        {"sid": scenario_id},
    ).mappings().all()
prefs = [dict(p) for p in prefs]

if not prefs:
    st.warning("No preference sets found. Go to Step 2 and create one, then save weights.")
    st.stop()

pref_id = st.selectbox(
    "Preference set",
    options=[p["preference_set_id"] for p in prefs],
    format_func=lambda x: next(
        f"{pp['name']}  [{pp['type']}]" for pp in prefs if pp["preference_set_id"] == x
    ),
)
pref_type = next((p["type"] for p in prefs if p["preference_set_id"] == pref_id), "direct")

if pref_type == "ahp":
    model_options = ["AHP", "TOPSIS"]
else:
    model_options = ["TOPSIS", "AHP"]

model = st.selectbox("Model to run", options=model_options, index=0)

ahp_mode = "hybrid"
if model == "AHP":
    ahp_mode = st.radio(
        "AHP mode",
        options=["hybrid", "full"],
        format_func=lambda x: {
            "hybrid": "Hybrid — AHP criteria weights × normalised performance matrix",
            "full":   "Full AHP — pairwise comparisons for alternatives too",
        }[x],
        horizontal=True,
    )

scenario_service = ScenarioService(engine)
result_repo = ResultRepo(engine)
run_repo = RunRepo(engine)
topsis_service = TopsisService(engine)
ahp_service = AHPService(engine)
ahp_repo = AHPRepo(engine)

try:
    data = scenario_service.load(scenario_id, pref_id)
    ok, issues = scenario_service.validate(data)
except Exception as e:
    st.error(str(e))
    st.stop()

st.subheader("Validation")
if ok:
    st.success("Scenario is runnable.")
else:
    for msg in issues:
        st.error(msg)
    st.stop()

st.divider()

# ── AHP Full mode: alternative pairwise ──────────────────────────────────────
alt_upper_by_crit: dict = {}

if model == "AHP" and ahp_mode == "full":
    st.subheader("AHP Full Mode: Alternative Pairwise Comparisons")
    st.caption("For each criterion, compare alternatives using Saaty's 1–9 scale.")

    with engine.begin() as conn:
        crit_rows_db = conn.execute(
            text("SELECT criterion_id::text, name FROM criteria WHERE scenario_id = :sid ORDER BY name"),
            {"sid": scenario_id},
        ).mappings().all()
        alt_rows_db = conn.execute(
            text("SELECT alternative_id::text, name FROM alternatives WHERE scenario_id = :sid ORDER BY name"),
            {"sid": scenario_id},
        ).mappings().all()
    crit_id_map = {r["name"]: r["criterion_id"] for r in crit_rows_db}
    alt_id_map  = {r["name"]: r["alternative_id"] for r in alt_rows_db}

    na = len(data.alternative_names)
    sel_crit = st.selectbox("Select criterion to compare", data.criterion_names)
    crit_id = crit_id_map.get(sel_crit, "")

    existing_alt_j = ahp_repo.load_alternative_judgments(pref_id, crit_id)
    alt_jmap = {(r["alternative_i_id"], r["alternative_j_id"]): float(r["judgment"]) for r in existing_alt_j}

    alt_inputs = {}
    for i in range(na):
        for j in range(i + 1, na):
            ni, nj = data.alternative_names[i], data.alternative_names[j]
            ai = alt_id_map.get(ni, "")
            aj = alt_id_map.get(nj, "")
            default_v = alt_jmap.get((ai, aj), 1.0)
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{ni}** vs *{nj}*")
            with col2:
                v = st.number_input("", min_value=round(1.0/9,4), max_value=9.0,
                                    value=float(round(default_v, 4)), step=0.5,
                                    key=f"alt_j_{sel_crit}_{i}_{j}", label_visibility="collapsed")
            alt_inputs[(i, j)] = v

    if st.button(f"Save '{sel_crit}' alternative judgments", type="secondary"):
        rows_to_save = []
        for i in range(na):
            for j in range(i + 1, na):
                v = float(alt_inputs.get((i, j), 1.0))
                ai = alt_id_map.get(data.alternative_names[i], "")
                aj = alt_id_map.get(data.alternative_names[j], "")
                if ai and aj:
                    rows_to_save.append({"criterion_id": crit_id, "alternative_i_id": ai, "alternative_j_id": aj, "judgment": v})
                    rows_to_save.append({"criterion_id": crit_id, "alternative_i_id": aj, "alternative_j_id": ai, "judgment": 1.0/v})
        ahp_repo.save_alternative_judgments(pref_id, rows_to_save)
        st.success(f"Saved judgments for '{sel_crit}'.")

    for cname in data.criterion_names:
        cid = crit_id_map.get(cname, "")
        rows_c = ahp_repo.load_alternative_judgments(pref_id, cid)
        jmap_c = {(r["alternative_i_id"], r["alternative_j_id"]): float(r["judgment"]) for r in rows_c}
        upper_c = [jmap_c.get((alt_id_map.get(data.alternative_names[i],""), alt_id_map.get(data.alternative_names[j],"")), 1.0)
                   for i in range(na) for j in range(i+1, na)]
        alt_upper_by_crit[cname] = upper_c

    st.divider()

# ── AHP criteria weights preview ──────────────────────────────────────────────
if model == "AHP":
    with engine.begin() as conn:
        crit_ids_ordered = conn.execute(
            text("SELECT criterion_id::text, name FROM criteria WHERE scenario_id = :sid ORDER BY name"),
            {"sid": scenario_id},
        ).mappings().all()
    crit_id_list = [r["criterion_id"] for r in crit_ids_ordered]
    crit_name_list = [r["name"] for r in crit_ids_ordered]
    nc = len(crit_id_list)

    judgments_db = ahp_repo.load_criteria_judgments(pref_id)
    jmap_crit = {(r["criterion_i_id"], r["criterion_j_id"]): float(r["judgment"]) for r in judgments_db}

    if nc >= 2 and judgments_db:
        upper_v = [jmap_crit.get((crit_id_list[i], crit_id_list[j]), 1.0)
                   for i in range(nc) for j in range(i+1, nc)]
        mat_p = matrix_from_upper(upper_v, nc)
        res_p = compute_priority(mat_p)
        cr_v = res_p.cr
        color = "green" if cr_v < 0.10 else "red"
        st.markdown(
            f"**AHP Criteria CR:** "
            f"<span style='color:{color};font-weight:700'>{cr_v:.4f}</span> "
            f"({'✓ Consistent' if cr_v < 0.10 else '✗ Inconsistent — revise in Step 2'})",
            unsafe_allow_html=True,
        )
    else:
        st.info("No AHP criteria judgments found. Go to Step 2 (AHP preference set) and save pairwise comparisons first.")

st.divider()

# ── Run ───────────────────────────────────────────────────────────────────────
st.subheader("Run")
if st.button("Run and Save", type="primary"):
    if model == "TOPSIS":
        run_id = topsis_service.run_and_persist(
            scenario_id=scenario_id,
            preference_set_id=pref_id,
            executed_by=user_name,
            data=data,
        )
    elif model == "AHP":
        with engine.begin() as conn:
            crit_ids_run = conn.execute(
                text("SELECT criterion_id::text, name FROM criteria WHERE scenario_id = :sid ORDER BY name"),
                {"sid": scenario_id},
            ).mappings().all()
        crit_id_list_run = [r["criterion_id"] for r in crit_ids_run]
        nc_run = len(crit_id_list_run)
        judgments_run = ahp_repo.load_criteria_judgments(pref_id)
        jmap_run = {(r["criterion_i_id"], r["criterion_j_id"]): float(r["judgment"]) for r in judgments_run}
        crit_upper_run = [jmap_run.get((crit_id_list_run[i], crit_id_list_run[j]), 1.0)
                          for i in range(nc_run) for j in range(i+1, nc_run)]

        run_id = ahp_service.run_and_persist(
            scenario_id=scenario_id,
            preference_set_id=pref_id,
            executed_by=user_name,
            data=data,
            crit_upper=crit_upper_run,
            alt_upper_by_crit=alt_upper_by_crit,
            mode=ahp_mode,
        )

    st.session_state["last_run_id"] = run_id
    st.success(f"Run created: `{run_id}`")

    scores = result_repo.get_scores_with_names(run_id)
    st.subheader("Ranking")
    st.dataframe(scores, use_container_width=True)

st.divider()
st.subheader("Run History")
runs = run_repo.list_runs(scenario_id, limit=20)
if runs:
    st.dataframe(runs, use_container_width=True)
else:
    st.info("No runs yet.")
