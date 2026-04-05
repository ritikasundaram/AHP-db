import bootstrap

import pandas as pd
import numpy as np
import streamlit as st
from sqlalchemy import text
import plotly.express as px
import plotly.graph_objects as go

from persistence.engine import get_engine
from persistence.repositories.result_repo import ResultRepo
from persistence.repositories.run_repo import RunRepo
from persistence.repositories.topsis_read_repo import TopsisReadRepo
from persistence.repositories.ahp_repo import AHPRepo

st.title("Step 4: Results")

engine = get_engine()
scenario_id = st.session_state.get("scenario_id")
if not scenario_id:
    st.info("Go to Step 1 and select a Scenario first.")
    st.stop()

# Navigation
nav_left, nav_right = st.columns(2)
with nav_left:
    if st.button("Back: Step 3 (Run Models)"):
        st.switch_page("pages/3_run_models.py")
with nav_right:
    if st.button("Next: Step 5 (History)"):
        st.switch_page("pages/5_history.py")

st.divider()

run_repo = RunRepo(engine)
result_repo = ResultRepo(engine)
topsis_read = TopsisReadRepo(engine)
ahp_repo = AHPRepo(engine)

runs = run_repo.list_runs(scenario_id, limit=50)
eligible_runs = [r for r in runs if r["method"] in ("topsis", "ahp")]

if not eligible_runs:
    st.warning("No runs yet. Go to Step 3 and run a model first.")
    st.stop()

default_run = st.session_state.get("last_run_id")
if default_run not in [r["run_id"] for r in eligible_runs]:
    default_run = eligible_runs[0]["run_id"]

run_id = st.selectbox(
    "Select a run",
    options=[r["run_id"] for r in eligible_runs],
    index=[r["run_id"] for r in eligible_runs].index(default_run),
    format_func=lambda x: next(
        f"[{rr['method'].upper()}] {rr['executed_at']} | {rr.get('executed_by','')} | pref={rr['preference_set_id'][:8]}…"
        for rr in eligible_runs if rr["run_id"] == x
    ),
)

st.session_state["last_run_id"] = run_id

# Run metadata
with engine.begin() as conn:
    meta = conn.execute(
        text("""
            SELECT run_id::text AS run_id, method, engine_version, executed_at, executed_by,
                   preference_set_id::text AS preference_set_id
            FROM runs
            WHERE run_id = :rid
        """),
        {"rid": run_id},
    ).mappings().first()

st.subheader("Run Summary")
st.write(
    {
        "run_id": meta["run_id"],
        "method": meta["method"],
        "engine_version": meta["engine_version"],
        "executed_at": str(meta["executed_at"]),
        "executed_by": meta.get("executed_by"),
        "preference_set_id": meta["preference_set_id"],
    }
)

st.divider()

# Ranking table
st.subheader("Ranking")
scores = result_repo.get_scores_with_names(run_id)
scores_df = pd.DataFrame(scores)
st.dataframe(scores_df, use_container_width=True)

st.download_button(
    "Download Ranking CSV",
    data=scores_df.to_csv(index=False).encode("utf-8"),
    file_name=f"ranking_{run_id}.csv",
    mime="text/csv",
)

st.divider()

# ── Method-specific detail tabs ───────────────────────────────────────────────
run_method = meta["method"]

if run_method == "topsis":
    st.subheader("TOPSIS Details")

    dist_df = topsis_read.get_distances(run_id)
    ideals_df = topsis_read.get_ideals(run_id)
    norm_df = topsis_read.get_matrix(run_id, "normalized")
    w_df = topsis_read.get_matrix(run_id, "weighted")

    tab1, tab2, tab3, tab4 = st.tabs(["Distances", "Ideals (PIS/NIS)", "Normalized Matrix", "Weighted Matrix"])

    with tab1:
        st.dataframe(dist_df, use_container_width=True)
        st.download_button("Download Distances CSV", data=dist_df.to_csv(index=False).encode("utf-8"),
                           file_name=f"topsis_distances_{run_id}.csv", mime="text/csv")
    with tab2:
        st.dataframe(ideals_df, use_container_width=True)
        st.download_button("Download Ideals CSV", data=ideals_df.to_csv(index=False).encode("utf-8"),
                           file_name=f"topsis_ideals_{run_id}.csv", mime="text/csv")
    with tab3:
        if norm_df.empty:
            st.info("No normalized matrix found for this run.")
        else:
            st.dataframe(norm_df, use_container_width=True)
            st.download_button("Download Normalized Matrix CSV", data=norm_df.to_csv().encode("utf-8"),
                               file_name=f"topsis_normalized_matrix_{run_id}.csv", mime="text/csv")
    with tab4:
        if w_df.empty:
            st.info("No weighted matrix found for this run.")
        else:
            st.dataframe(w_df, use_container_width=True)
            st.download_button("Download Weighted Matrix CSV", data=w_df.to_csv().encode("utf-8"),
                               file_name=f"topsis_weighted_matrix_{run_id}.csv", mime="text/csv")

    st.subheader("Charts")
    if not scores_df.empty:
        fig_scores = px.bar(scores_df.sort_values("rank", ascending=True),
                            x="alternative_name", y="score", hover_data=["rank"],
                            title="TOPSIS Score (C*) by Alternative")
        st.plotly_chart(fig_scores, use_container_width=True)
    if not dist_df.empty:
        fig_scatter = px.scatter(dist_df, x="s_pos", y="s_neg", text="alternative",
                                 hover_data=["c_star"], title="Separation Measures: S+ vs S-")
        fig_scatter.update_traces(textposition="top center")
        st.plotly_chart(fig_scatter, use_container_width=True)
    if not w_df.empty:
        fig_heat = px.imshow(w_df.values, x=list(w_df.columns), y=list(w_df.index),
                             aspect="auto", title="Weighted Matrix Heatmap")
        st.plotly_chart(fig_heat, use_container_width=True)
    if not ideals_df.empty:
        ideals_long = ideals_df.melt(id_vars=["criterion"], value_vars=["pos_ideal", "neg_ideal"],
                                     var_name="ideal_type", value_name="value")
        fig_ideals = px.bar(ideals_long, x="criterion", y="value", color="ideal_type",
                            barmode="group", title="PIS vs NIS by Criterion")
        st.plotly_chart(fig_ideals, use_container_width=True)

elif run_method == "ahp":
    st.subheader("AHP Details")

    # Run artifacts
    ahp_artifacts = ahp_repo.get_run_artifacts(run_id)
    if ahp_artifacts:
        cr_val = float(ahp_artifacts["criteria_cr"])
        cr_color = "green" if cr_val < 0.10 else "red"
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Criteria CR", f"{cr_val:.4f}",
                      delta="Consistent ✓" if cr_val < 0.10 else "Inconsistent ✗",
                      delta_color="normal" if cr_val < 0.10 else "inverse")
        with col2:
            st.metric("λ_max", f"{float(ahp_artifacts['lambda_max']):.4f}")
        with col3:
            st.metric("Mode", ahp_artifacts["mode"].title())

    # Criterion priority weights
    crit_prio_df = ahp_repo.get_criterion_priorities(run_id)
    alt_prio_df  = ahp_repo.get_alternative_priorities(run_id)

    ahp_tab1, ahp_tab2, ahp_tab3, ahp_tab4 = st.tabs([
        "Criteria Weights", "Alternative Priorities", "Charts", "Score Composition"
    ])

    with ahp_tab1:
        if not crit_prio_df.empty:
            crit_prio_df["weight_%"] = (crit_prio_df["priority"] * 100).round(2).astype(str) + "%"
            st.dataframe(crit_prio_df, use_container_width=True, hide_index=True)
            st.download_button("Download Criteria Weights CSV",
                               data=crit_prio_df.to_csv(index=False).encode("utf-8"),
                               file_name=f"ahp_crit_weights_{run_id}.csv", mime="text/csv")
        else:
            st.info("No criterion priorities saved for this run.")

    with ahp_tab2:
        if not alt_prio_df.empty:
            st.dataframe(alt_prio_df, use_container_width=True, hide_index=True)
            st.download_button("Download Alternative Priorities CSV",
                               data=alt_prio_df.to_csv(index=False).encode("utf-8"),
                               file_name=f"ahp_alt_priorities_{run_id}.csv", mime="text/csv")
            # Show CR per criterion
            if "cr" in alt_prio_df.columns:
                cr_summary = (alt_prio_df.groupby("criterion")["cr"].first()
                              .reset_index().rename(columns={"cr": "Consistency Ratio"}))
                cr_summary["Status"] = cr_summary["Consistency Ratio"].apply(
                    lambda x: "✓ Consistent" if x < 0.10 else "✗ Inconsistent"
                )
                st.markdown("**Consistency per Criterion:**")
                st.dataframe(cr_summary, use_container_width=True, hide_index=True)
        else:
            st.info("No alternative priorities found for this run.")

    with ahp_tab3:
        # Composite score bar
        if not scores_df.empty:
            fig_bar = px.bar(
                scores_df.sort_values("rank"),
                x="alternative_name", y="score",
                title="AHP Composite Score by Alternative",
                color="score",
                color_continuous_scale="RdBu",
                text="score",
            )
            fig_bar.update_traces(texttemplate="%{text:.4f}", textposition="outside")
            fig_bar.update_layout(coloraxis_showscale=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        # Criteria weight radar
        if not crit_prio_df.empty:
            crits = crit_prio_df["criterion"].tolist()
            weights = crit_prio_df["priority"].tolist()
            fig_radar = go.Figure(go.Scatterpolar(
                r=weights + [weights[0]],
                theta=crits + [crits[0]],
                fill="toself",
                fillcolor="rgba(229,62,62,0.15)",
                line=dict(color="#e53e3e", width=2),
                marker=dict(size=7),
            ))
            fig_radar.update_layout(
                title="Criteria Priority Weights (Radar)",
                polar=dict(radialaxis=dict(visible=True, range=[0, max(weights) * 1.25])),
                paper_bgcolor="white",
            )
            st.plotly_chart(fig_radar, use_container_width=True)

    with ahp_tab4:
        # Stacked contribution chart: priority_per_criterion × criterion_weight
        if not alt_prio_df.empty and not crit_prio_df.empty:
            crit_w_map = dict(zip(crit_prio_df["criterion"], crit_prio_df["priority"]))
            alt_prio_df["contribution"] = alt_prio_df["priority"] * alt_prio_df["criterion"].map(crit_w_map)

            fig_stack = px.bar(
                alt_prio_df,
                x="alternative",
                y="contribution",
                color="criterion",
                barmode="stack",
                title="Score Composition: Criterion Contributions per Alternative",
            )
            st.plotly_chart(fig_stack, use_container_width=True)
            st.download_button("Download Composition CSV",
                               data=alt_prio_df.to_csv(index=False).encode("utf-8"),
                               file_name=f"ahp_composition_{run_id}.csv", mime="text/csv")
        else:
            st.info("Not enough data to render composition chart.")

