import bootstrap

import pandas as pd
import streamlit as st
from sqlalchemy import text

from persistence.engine import get_engine
from persistence.repositories.run_repo import RunRepo
from persistence.repositories.result_repo import ResultRepo

st.title("Step 5: History and Compare")

engine = get_engine()
run_repo = RunRepo(engine)
result_repo = ResultRepo(engine)

scenario_id = st.session_state.get("scenario_id")
if not scenario_id:
    st.info("Go to Step 1 and select a Scenario first.")
    st.stop()

# Navigation
nav_left, nav_right = st.columns(2)
with nav_left:
    if st.button("Back: Step 4 (Results)"):
        st.switch_page("pages/4_results.py")
with nav_right:
    st.button("Next", disabled=True)

st.divider()

# ----------------------------
# Load decision_id for current scenario (for scenario comparison)
# ----------------------------
with engine.begin() as conn:
    row = conn.execute(
        text(
            """
            SELECT decision_id::text AS decision_id
            FROM scenarios
            WHERE scenario_id = :sid
            """
        ),
        {"sid": scenario_id},
    ).mappings().first()

decision_id = row["decision_id"] if row else None
if not decision_id:
    st.error("Could not find decision for the selected scenario.")
    st.stop()

# ----------------------------
# Preference names lookup (for readable labels)
# ----------------------------
with engine.begin() as conn:
    pref_map_rows = conn.execute(
        text(
            """
            SELECT preference_set_id::text AS preference_set_id, name
            FROM preference_sets
            WHERE scenario_id = :sid
            """
        ),
        {"sid": scenario_id},
    ).mappings().all()

pref_id_to_name = {r["preference_set_id"]: r["name"] for r in pref_map_rows}

def run_label(r: dict, pref_map: dict) -> str:
    pref_name = pref_map.get(r["preference_set_id"], r["preference_set_id"][:8] + "…")
    by = (r.get("executed_by") or "").strip()
    by_part = f" by {by}" if by else ""
    return f"{r['executed_at']} | {r['method'].upper()} | {pref_name}{by_part}"

# ----------------------------
# Section 1: Run history for current scenario
# ----------------------------
st.subheader("Run History (Current Scenario)")

runs = run_repo.list_runs(scenario_id, limit=200)
if not runs:
    st.info("No runs yet. Go to Step 3 to run TOPSIS.")
else:
    runs_df = pd.DataFrame(runs)
    runs_df["preference_name"] = runs_df["preference_set_id"].map(lambda x: pref_id_to_name.get(x, x))
    st.dataframe(
        runs_df[["executed_at", "method", "preference_name", "executed_by", "run_id"]],
        use_container_width=True,
    )

    st.download_button(
        "Download Run History CSV",
        data=runs_df[["executed_at", "method", "preference_name", "executed_by", "run_id"]]
        .to_csv(index=False)
        .encode("utf-8"),
        file_name="run_history_current_scenario.csv",
        mime="text/csv",
    )

st.divider()

# ----------------------------
# Section 2: Compare two runs within current scenario
# ----------------------------
st.subheader("Compare Two Runs (Current Scenario)")

topsis_runs = [r for r in runs if r["method"] == "topsis"]
if len(topsis_runs) < 2:
    st.info("Need at least 2 TOPSIS runs in this scenario to compare. Create another run in Step 3.")
else:
    topsis_df = pd.DataFrame(topsis_runs)
    topsis_df["label"] = topsis_df.apply(lambda row: run_label(row.to_dict(), pref_id_to_name), axis=1)
    labels = topsis_df["label"].tolist()
    label_to_run_id = dict(zip(labels, topsis_df["run_id"].tolist()))

    col1, col2 = st.columns(2)
    with col1:
        run_a_label = st.selectbox("Run A", options=labels, index=0)
    with col2:
        run_b_label = st.selectbox("Run B", options=labels, index=1 if len(labels) > 1 else 0)

    run_a = label_to_run_id[run_a_label]
    run_b = label_to_run_id[run_b_label]

    a_scores = pd.DataFrame(result_repo.get_scores_with_names(run_a))
    b_scores = pd.DataFrame(result_repo.get_scores_with_names(run_b))

    if a_scores.empty or b_scores.empty:
        st.error("One of the selected runs has no results saved.")
    else:
        a_scores = a_scores.rename(columns={"score": "score_a", "rank": "rank_a"})
        b_scores = b_scores.rename(columns={"score": "score_b", "rank": "rank_b"})

        cmp_df = a_scores.merge(b_scores, on="alternative_name", how="outer")
        cmp_df["rank_delta"] = cmp_df["rank_b"] - cmp_df["rank_a"]
        cmp_df["score_delta"] = cmp_df["score_b"] - cmp_df["score_a"]

        cmp_df = cmp_df.sort_values(by="rank_delta", key=lambda s: s.abs(), ascending=False)

        st.dataframe(cmp_df, use_container_width=True)

        st.download_button(
            "Download Run Comparison CSV",
            data=cmp_df.to_csv(index=False).encode("utf-8"),
            file_name="run_comparison_current_scenario.csv",
            mime="text/csv",
        )

        st.caption("rank_delta > 0 means the alternative ranked worse in Run B. rank_delta < 0 means it improved in Run B.")

st.divider()

# ----------------------------
# Section 3: Compare two scenarios under the same decision
# ----------------------------
st.subheader("Compare Two Scenarios (Same Decision)")

with engine.begin() as conn:
    scen_rows = conn.execute(
        text(
            """
            SELECT scenario_id::text AS scenario_id, name, description, created_at, created_by
            FROM scenarios
            WHERE decision_id = :did
            ORDER BY created_at ASC
            """
        ),
        {"did": decision_id},
    ).mappings().all()

scenarios = [dict(r) for r in scen_rows]
if len(scenarios) < 2:
    st.info("You need at least 2 scenarios under this decision to compare.")
    st.stop()

scen_ids = [s["scenario_id"] for s in scenarios]

def scen_label(s: dict) -> str:
    return f"{s['name']} ({s['scenario_id'][:8]}…)"

default_a = scenario_id
default_b = next((sid for sid in scen_ids if sid != default_a), scen_ids[0])

colA, colB = st.columns(2)
with colA:
    scen_a_id = st.selectbox(
        "Scenario A",
        options=scen_ids,
        index=scen_ids.index(default_a) if default_a in scen_ids else 0,
        format_func=lambda x: scen_label(next(ss for ss in scenarios if ss["scenario_id"] == x)),
        key="scen_a_select",
    )

with colB:
    scen_b_id = st.selectbox(
        "Scenario B",
        options=scen_ids,
        index=scen_ids.index(default_b) if default_b in scen_ids else 1,
        format_func=lambda x: scen_label(next(ss for ss in scenarios if ss["scenario_id"] == x)),
        key="scen_b_select",
    )

if scen_a_id == scen_b_id:
    st.warning("Pick two different scenarios to compare.")
    st.stop()

use_latest = st.checkbox("Use latest TOPSIS run in each scenario", value=True)

def load_pref_map_for_scenario(sid: str) -> dict:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT preference_set_id::text AS preference_set_id, name
                FROM preference_sets
                WHERE scenario_id = :sid
                """
            ),
            {"sid": sid},
        ).mappings().all()
    return {r["preference_set_id"]: r["name"] for r in rows}

def list_topsis_runs_for_scenario(sid: str):
    rr = run_repo.list_runs(sid, limit=200)
    return [r for r in rr if r["method"] == "topsis"]

runs_a = list_topsis_runs_for_scenario(scen_a_id)
runs_b = list_topsis_runs_for_scenario(scen_b_id)

if not runs_a or not runs_b:
    st.warning("Both scenarios must have at least 1 TOPSIS run to compare.")
    st.stop()

pref_map_a = load_pref_map_for_scenario(scen_a_id)
pref_map_b = load_pref_map_for_scenario(scen_b_id)

def pick_run_ui(label: str, runs_list: list, pref_map: dict, key: str):
    df = pd.DataFrame(runs_list)
    df["label"] = df.apply(lambda row: run_label(row.to_dict(), pref_map), axis=1)
    labels = df["label"].tolist()
    label_to_id = dict(zip(labels, df["run_id"].tolist()))
    chosen_label = st.selectbox(label, options=labels, index=0, key=key)
    return label_to_id[chosen_label]

if use_latest:
    run_a_id = runs_a[0]["run_id"]
    run_b_id = runs_b[0]["run_id"]
    st.info(f"Scenario A run: {run_a_id} | Scenario B run: {run_b_id}")
else:
    col1, col2 = st.columns(2)
    with col1:
        run_a_id = pick_run_ui("Select TOPSIS run for Scenario A", runs_a, pref_map_a, key="run_a_pick")
    with col2:
        run_b_id = pick_run_ui("Select TOPSIS run for Scenario B", runs_b, pref_map_b, key="run_b_pick")

a_scores = pd.DataFrame(result_repo.get_scores_with_names(run_a_id))
b_scores = pd.DataFrame(result_repo.get_scores_with_names(run_b_id))

if a_scores.empty or b_scores.empty:
    st.error("Selected run(s) missing results. Re-run TOPSIS in Step 3.")
    st.stop()

a_scores = a_scores.rename(columns={"score": "score_a", "rank": "rank_a"})
b_scores = b_scores.rename(columns={"score": "score_b", "rank": "rank_b"})

cmp_scen_df = a_scores.merge(b_scores, on="alternative_name", how="outer")
cmp_scen_df["rank_delta"] = cmp_scen_df["rank_b"] - cmp_scen_df["rank_a"]
cmp_scen_df["score_delta"] = cmp_scen_df["score_b"] - cmp_scen_df["score_a"]
cmp_scen_df = cmp_scen_df.sort_values(by="rank_delta", key=lambda s: s.abs(), ascending=False)

st.subheader("Scenario Comparison Result")
st.dataframe(cmp_scen_df, use_container_width=True)

st.download_button(
    "Download Scenario Comparison CSV",
    data=cmp_scen_df.to_csv(index=False).encode("utf-8"),
    file_name="scenario_comparison.csv",
    mime="text/csv",
)

st.caption("This compares TOPSIS results across scenarios under the same decision, using one run per scenario.")
