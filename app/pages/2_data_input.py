import bootstrap

import numpy as np
import pandas as pd
import streamlit as st
from sqlalchemy import text

from core.ahp import compute_priority, matrix_from_upper, upper_size, SAATY_LABELS
from persistence.engine import get_engine
from persistence.repositories.alternative_repo import AlternativeRepo
from persistence.repositories.criterion_repo import CriterionRepo
from persistence.repositories.measurement_repo import MeasurementRepo
from persistence.repositories.preference_repo import PreferenceRepo
from persistence.repositories.ahp_repo import AHPRepo


st.title("Step 2: Data Input")

engine = get_engine()
alt_repo = AlternativeRepo(engine)
crit_repo = CriterionRepo(engine)
meas_repo = MeasurementRepo(engine)
ahp_repo = AHPRepo(engine)
pref_repo = PreferenceRepo(engine)

scenario_id = st.session_state.get("scenario_id")
user_name = st.session_state.get("user_name", "")

if not scenario_id:
    st.info("Go to Step 1 and create or select a Scenario first.")
    st.stop()

st.session_state.setdefault("preference_set_id", None)
st.session_state.setdefault("data_ready", False)

# ----------------------------
# Navigation
# ----------------------------
nav_left, nav_right = st.columns(2)

with nav_left:
    if st.button("Back: Step 1 (Decision and Scenario)"):
        st.switch_page("pages/1_decision_setup.py")

with nav_right:
    can_next = bool(st.session_state.get("data_ready"))
    if st.button("Next: Step 3 (Run Models)", type="primary", disabled=not can_next):
        st.switch_page("pages/3_run_models.py")

st.caption("Save Alternatives + Criteria, then save Matrix + Weights to enable Next.")
st.divider()

# ----------------------------
# Preference Set (select or create)
# ----------------------------
st.subheader("Preference Set")

with engine.begin() as conn:
    prefs = conn.execute(
        text(
            """
            SELECT preference_set_id::text AS preference_set_id, name, type, status, created_at
            FROM preference_sets
            WHERE scenario_id = :sid
            ORDER BY created_at DESC
            """
        ),
        {"sid": scenario_id},
    ).mappings().all()

prefs = [dict(p) for p in prefs]

pref_options = ["Create new…"] + [p["preference_set_id"] for p in prefs]
default_pref = st.session_state.get("preference_set_id")
if not default_pref:
    default_pref = "Create new…" if not prefs else prefs[0]["preference_set_id"]

selected_pref = st.selectbox(
    "Select preference set",
    options=pref_options,
    index=pref_options.index(default_pref) if default_pref in pref_options else 0,
    format_func=lambda x: "Create new…" if x == "Create new…" else next(
        pp["name"] for pp in prefs if pp["preference_set_id"] == x
    ),
)

if selected_pref == "Create new…":
    new_pref_name = st.text_input("New preference set name", value="Default Weights")
    new_pref_type = st.selectbox(
        "Type",
        options=["direct", "ahp"],
        format_func=lambda x: {
            "direct": "Direct — enter weights manually",
            "ahp":    "AHP — derive weights from pairwise comparisons (Saaty scale)",
        }.get(x, x),
        index=0,
    )

    if st.button("Create Preference Set", type="primary"):
        pref_id = pref_repo.get_or_create_preference_set(
            scenario_id=scenario_id,
            name=new_pref_name.strip() or "Default Weights",
            pref_type=new_pref_type,
            created_by=user_name,
        )
        st.session_state["preference_set_id"] = pref_id
        st.success(f"Preference set created: {pref_id}")
        st.rerun()
else:
    st.session_state["preference_set_id"] = selected_pref

pref_id = st.session_state.get("preference_set_id")
if not pref_id:
    st.info("Create or select a preference set to continue.")
    st.stop()

# Determine type of the selected preference set
with engine.begin() as conn:
    pref_meta = conn.execute(
        text("SELECT type FROM preference_sets WHERE preference_set_id = :pid"),
        {"pid": pref_id},
    ).mappings().first()
pref_type = pref_meta["type"] if pref_meta else "direct"

st.divider()

# ----------------------------
# Load existing state from DB
# ----------------------------
existing_alts = alt_repo.list_by_scenario(scenario_id)
existing_crit = crit_repo.list_by_scenario(scenario_id)

alt_names_existing = [a["name"] for a in existing_alts] if existing_alts else []
crit_rows_existing = existing_crit if existing_crit else []

# ----------------------------
# Alternatives
# ----------------------------
st.subheader("Alternatives")

default_alts = alt_names_existing or ["Alfred", "Beverly", "Calvin", "Diane", "Edward", "Fran"]
alts_df = pd.DataFrame({"Alternative Name": default_alts})

alts_df = st.data_editor(
    alts_df,
    num_rows="dynamic",
    use_container_width=True,
    key="alts_editor_step2",
)

alt_names = [str(x).strip() for x in alts_df["Alternative Name"].dropna().tolist() if str(x).strip()]
alt_names = list(dict.fromkeys(alt_names))

st.divider()

# ----------------------------
# Criteria (dropdown for Scale Type and Unit, single Description)
# ----------------------------
st.subheader("Criteria")

UNIT_OPTIONS = [
    "score", "points", "rank", "rating",
    "USD", "percent", "days", "hours", "minutes",
    "ms", "seconds", "kg", "g", "km", "m",
    "Yes/No", "count", "other",
]

SCALE_OPTIONS = ["ratio", "interval", "ordinal", "binary"]
DIRECTION_OPTIONS = ["benefit", "cost"]

if crit_rows_existing:
    crit_df = pd.DataFrame({
        "Criterion Name": [c["name"] for c in crit_rows_existing],
        "Direction": [c["direction"] for c in crit_rows_existing],
        "Scale Type": [c["scale_type"] for c in crit_rows_existing],
        "Unit": [c["unit"] if c["unit"] else "score" for c in crit_rows_existing],
        "Description": [c["description"] if c["description"] else "" for c in crit_rows_existing],
    })
else:
    crit_df = pd.DataFrame({
        "Criterion Name": ["GRE", "GPA", "College ranking", "Recommendation Rating", "Interview Rating"],
        "Direction": ["benefit"] * 5,
        "Scale Type": ["ratio", "ratio", "ordinal", "ordinal", "ordinal"],
        "Unit": ["score", "points", "rank", "rating", "rating"],
        "Description": ["", "", "", "", ""],
    })

crit_df = st.data_editor(
    crit_df,
    num_rows="dynamic",
    use_container_width=True,
    key="crit_editor_step2",
    column_config={
        "Direction": st.column_config.SelectboxColumn("Direction", options=DIRECTION_OPTIONS),
        "Scale Type": st.column_config.SelectboxColumn("Scale Type", options=SCALE_OPTIONS),
        "Unit": st.column_config.SelectboxColumn("Unit", options=UNIT_OPTIONS),
        "Description": st.column_config.TextColumn("Description"),
    },
)

crit_rows = []
for _, r in crit_df.iterrows():
    name = str(r.get("Criterion Name", "")).strip()
    if not name:
        continue

    unit_val = str(r.get("Unit", "")).strip()
    if unit_val == "other":
        unit_val = None

    crit_rows.append({
        "name": name,
        "direction": str(r.get("Direction", "benefit")).strip(),
        "scale_type": str(r.get("Scale Type", "ratio")).strip(),
        "unit": unit_val,
        "description": str(r.get("Description", "")).strip() or None,
    })

crit_names = [c["name"] for c in crit_rows]
crit_names = list(dict.fromkeys(crit_names))

st.divider()

# ----------------------------
# Save alternatives + criteria
# ----------------------------
save_left, save_right = st.columns([1, 2])

with save_left:
    if st.button("Save Alternatives + Criteria", type="primary"):
        if not alt_names:
            st.error("Please provide at least 1 alternative.")
            st.stop()
        if not crit_rows:
            st.error("Please provide at least 1 criterion.")
            st.stop()

        alt_repo.upsert_by_names(scenario_id, alt_names)
        crit_repo.upsert_rows(scenario_id, crit_rows)

        alt_repo.delete_missing(scenario_id, alt_names)
        crit_repo.delete_missing(scenario_id, crit_names)

        st.session_state["data_ready"] = False
        st.success("Saved. Now fill Matrix and Weights and save to enable Next.")
        st.rerun()

with save_right:
    st.caption("If you change alternatives or criteria later, save Matrix + Weights again before running models.")

# Reload after save
existing_alts = alt_repo.list_by_scenario(scenario_id)
existing_crit = crit_repo.list_by_scenario(scenario_id)
alt_names_db = [a["name"] for a in existing_alts]
crit_names_db = [c["name"] for c in existing_crit]

if not alt_names_db or not crit_names_db:
    st.info("Save alternatives and criteria first to unlock the matrix editor.")
    st.stop()

st.divider()

# ----------------------------
# Weights editor  (direct)  OR  AHP pairwise  (ahp)
# ----------------------------

if pref_type == "ahp":
    # ── AHP: criteria pairwise comparisons ────────────────────────────────────
    st.subheader("AHP: Criteria Pairwise Comparisons")
    st.caption(
        "Saaty scale: 1 = Equal, 3 = Moderate, 5 = Strong, 7 = Very Strong, 9 = Extreme. "
        "Values < 1 favour the column criterion."
    )

    nc = len(crit_names_db)
    n_upper = upper_size(nc)

    # Load existing judgments from DB
    existing_judgments = ahp_repo.load_criteria_judgments(pref_id)
    with engine.begin() as conn:
        crit_id_rows = conn.execute(
            text("SELECT criterion_id::text, name FROM criteria WHERE scenario_id = :sid ORDER BY name"),
            {"sid": scenario_id},
        ).mappings().all()
    crit_name_to_id = {r["name"]: r["criterion_id"] for r in crit_id_rows}
    crit_id_to_name = {v: k for k, v in crit_name_to_id.items()}

    # Build lookup: (i_id, j_id) → judgment
    existing_jmap = {
        (r["criterion_i_id"], r["criterion_j_id"]): float(r["judgment"])
        for r in existing_judgments
    }

    # Render pairwise inputs
    crit_ids_ordered = [crit_name_to_id[n] for n in crit_names_db if n in crit_name_to_id]
    ahp_inputs = {}    # (i, j) → widget value

    for i in range(nc):
        for j in range(i + 1, nc):
            ni, nj = crit_names_db[i], crit_names_db[j]
            ii, ij = crit_name_to_id.get(ni), crit_name_to_id.get(nj)
            default_val = existing_jmap.get((ii, ij), existing_jmap.get((ij, ii), 1.0))
            if (ij, ii) in existing_jmap and (ii, ij) not in existing_jmap:
                default_val = 1.0 / existing_jmap[(ij, ii)]

            col1, col2, col3, col4 = st.columns([2, 2, 1, 2])
            with col1:
                st.markdown(f"**{ni}**")
            with col2:
                st.markdown(f"vs  *{nj}*")
            with col3:
                v = st.number_input(
                    "",
                    min_value=round(1.0 / 9, 4),
                    max_value=9.0,
                    value=float(round(default_val, 4)),
                    step=0.5,
                    key=f"ahp_crit_{pref_id}_{i}_{j}",
                    label_visibility="collapsed",
                    help=f"How much more important is '{ni}' relative to '{nj}'?",
                )
            with col4:
                int_v = int(round(v)) if v >= 1 else int(round(1.0 / v))
                label = SAATY_LABELS.get(int_v, "intermediate")
                color = "#e53e3e" if v > 1 else ("#2563eb" if v < 1 else "#6b7280")
                favours = ni if v >= 1 else nj
                st.markdown(
                    f"<span style='color:{color};font-size:0.85rem'>{label} — favours {favours}</span>",
                    unsafe_allow_html=True,
                )
            ahp_inputs[(i, j)] = v

    # Live consistency preview
    if nc >= 2:
        upper_vals = [ahp_inputs[(i, j)] for i in range(nc) for j in range(i + 1, nc)]
        mat_preview = matrix_from_upper(upper_vals, nc)
        res_preview = compute_priority(mat_preview)
        cr_val = res_preview.cr
        cr_color = "green" if cr_val < 0.10 else "red"
        st.markdown(
            f"**Consistency Ratio (CR):** "
            f"<span style='color:{cr_color};font-weight:700'>{cr_val:.4f}</span> "
            f"{'✓ Consistent (CR < 0.10)' if cr_val < 0.10 else '✗ Inconsistent — please revise'}",
            unsafe_allow_html=True,
        )

        # Show derived weights preview
        st.markdown("**Derived Priority Weights (preview):**")
        pv = res_preview.priority_vector
        w_preview_df = pd.DataFrame({
            "Criterion": crit_names_db,
            "Priority Weight": [f"{w:.4f}" for w in pv],
            "Weight %": [f"{w * 100:.1f}%" for w in pv],
        })
        st.dataframe(w_preview_df, use_container_width=True, hide_index=True)

    # AHP mode also needs the matrix to run TOPSIS-like scoring
    st.subheader("Performance Matrix (numeric)")
    st.caption("Required for AHP Hybrid mode (criteria weights × normalised performance).")
    existing_matrix = meas_repo.load_matrix_ui(scenario_id)
    if existing_matrix.empty:
        matrix_ui = pd.DataFrame(index=alt_names_db, columns=crit_names_db, dtype=float)
    else:
        matrix_ui = existing_matrix.reindex(index=alt_names_db, columns=crit_names_db)
    matrix_ui = st.data_editor(matrix_ui, use_container_width=True, key="matrix_editor_ahp")

    st.divider()

    # Save AHP judgments + matrix
    if st.button("Save AHP Judgments + Matrix", type="primary"):
        if nc < 2:
            st.error("Need at least 2 criteria to build a pairwise matrix.")
            st.stop()
        if matrix_ui.isna().any().any():
            st.error("Matrix has missing cells. Fill all values before saving.")
            st.stop()

        # Build upper-triangle list and judgment rows
        jmt_rows = []
        upper_save = []
        for i in range(nc):
            for j in range(i + 1, nc):
                v = float(ahp_inputs[(i, j)])
                upper_save.append(v)
                ii = crit_name_to_id.get(crit_names_db[i])
                ij = crit_name_to_id.get(crit_names_db[j])
                if ii and ij:
                    jmt_rows.append({"criterion_i_id": ii, "criterion_j_id": ij, "judgment": v})
                    jmt_rows.append({"criterion_i_id": ij, "criterion_j_id": ii, "judgment": 1.0 / v})

        ahp_repo.save_criteria_judgments(pref_id, jmt_rows)

        # Compute & store derived weights
        mat_save = matrix_from_upper(upper_save, nc)
        res_save = compute_priority(mat_save)
        pv_save = res_save.priority_vector
        weights_final = {crit_names_db[k]: float(pv_save[k]) for k in range(nc)}

        alt_map = alt_repo.upsert_by_names(scenario_id, alt_names_db)
        crit_map = crit_repo.upsert_rows(
            scenario_id,
            [{"name": c["name"], "direction": c["direction"], "scale_type": c["scale_type"],
              "unit": c["unit"], "description": c["description"]} for c in existing_crit],
        )
        # Save matrix
        try:
            matrix_numeric = matrix_ui.astype(float)
        except Exception:
            st.error("Matrix must be numeric in every cell.")
            st.stop()
        meas_repo.replace_all_for_scenario(scenario_id, alt_map, crit_map, matrix_numeric)

        # Store AHP-derived weights into criterion_weights (derived_from='ahp')
        del_w = "DELETE FROM criterion_weights WHERE preference_set_id = :pid"
        ins_w = """
            INSERT INTO criterion_weights
                   (preference_set_id, criterion_id, weight, weight_type, derived_from)
            VALUES (:pid, :criterion_id, :weight, 'normalized', 'ahp')
        """
        w_payloads = [
            {"pid": pref_id, "criterion_id": crit_map[cn], "weight": float(weights_final[cn])}
            for cn in crit_names_db if cn in crit_map
        ]
        with engine.begin() as conn:
            conn.execute(text(del_w), {"pid": pref_id})
            if w_payloads:
                conn.execute(text(ins_w), w_payloads)

        st.session_state["data_ready"] = True
        cr_final = res_save.cr
        if cr_final >= 0.10:
            st.warning(
                f"Saved, but CR = {cr_final:.4f} ≥ 0.10. "
                "Consider revising pairwise judgments to improve consistency before running."
            )
        else:
            st.success(f"Saved AHP judgments (CR = {cr_final:.4f}). Proceed to Step 3.")

else:
    # ── Direct weights ─────────────────────────────────────────────────────────
    st.subheader("Weights")

    existing_weights = pref_repo.load_weights_by_criterion_name(pref_id)
    weights_by_name = {}

    wcols = st.columns(min(5, len(crit_names_db)))
    for i, cname in enumerate(crit_names_db):
        with wcols[i % len(wcols)]:
            weights_by_name[cname] = st.number_input(
                f"{cname}",
                min_value=0.0,
                value=float(existing_weights.get(cname, 1.0)),
                step=0.05,
                key=f"w_step2_{pref_id}_{cname}",
            )

    auto_normalize = st.checkbox("Auto-normalize weights to sum to 1", value=True)

    st.divider()

    # Matrix editor
    st.subheader("Performance Matrix (numeric)")
    existing_matrix = meas_repo.load_matrix_ui(scenario_id)
    if existing_matrix.empty:
        matrix_ui = pd.DataFrame(index=alt_names_db, columns=crit_names_db, dtype=float)
    else:
        matrix_ui = existing_matrix.reindex(index=alt_names_db, columns=crit_names_db)
    matrix_ui = st.data_editor(matrix_ui, use_container_width=True, key="matrix_editor_step2")

    st.divider()

    # Save matrix + weights
    if st.button("Save Matrix + Weights", type="primary"):
        if matrix_ui.isna().any().any():
            st.error("Matrix has missing cells. Fill all values before saving.")
            st.stop()

        try:
            matrix_numeric = matrix_ui.astype(float)
        except Exception:
            st.error("Matrix must be numeric in every cell.")
            st.stop()

        w_vals = np.array([float(weights_by_name[c]) for c in crit_names_db], dtype=float)
        if auto_normalize:
            s = float(w_vals.sum())
            if s <= 0:
                st.error("Weights must sum to a positive number.")
                st.stop()
            w_vals = w_vals / s

        weights_final = {crit_names_db[i]: float(w_vals[i]) for i in range(len(crit_names_db))}

        alt_map = alt_repo.upsert_by_names(scenario_id, alt_names_db)
        crit_map = crit_repo.upsert_rows(
            scenario_id,
            [
                {
                    "name": c["name"],
                    "direction": c["direction"],
                    "scale_type": c["scale_type"],
                    "unit": c["unit"],
                    "description": c["description"],
                }
                for c in existing_crit
            ],
        )

        meas_repo.replace_all_for_scenario(scenario_id, alt_map, crit_map, matrix_numeric)
        pref_repo.replace_weights(pref_id, crit_map, weights_final)

        st.session_state["data_ready"] = True
        st.success("Saved matrix and weights. You can now proceed to Step 3.")

