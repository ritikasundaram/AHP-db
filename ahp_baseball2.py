"""
ahp_baseball.py  —  Standalone AHP Decision Tool (Baseball Player Evaluation)
Run: streamlit run ahp_baseball.py
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="AHP Baseball", layout="wide", page_icon="⚾")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.main .block-container { padding-top: 1.5rem; max-width: 1200px; }

.badge {
    display:inline-block; background:#fff3f3; color:#e53e3e;
    border:1px solid #fca5a5; border-radius:20px;
    padding:2px 12px; font-size:0.78rem; font-weight:600; margin-bottom:.4rem;
}
.section-title { font-size:1.35rem; font-weight:700; color:#111; margin-bottom:.1rem; }
.section-sub   { font-size:0.85rem; color:#888; margin-bottom:1rem; }
.card { background:white; border:1px solid #e8e8ec; border-radius:10px; padding:1.25rem 1.5rem; margin-bottom:1rem; }
.metric-box { background:white; border:1px solid #e8e8ec; border-radius:8px; padding:.9rem 1rem; text-align:center; }
.metric-val { font-size:1.8rem; font-weight:700; color:#111; line-height:1.1; }
.metric-lbl { font-size:0.75rem; color:#888; text-transform:uppercase; letter-spacing:.05em; margin-top:.2rem; }
.cr-ok  { background:#d1fae5; color:#065f46; padding:3px 12px; border-radius:20px; font-weight:600; font-size:.82rem; }
.cr-bad { background:#fee2e2; color:#991b1b; padding:3px 12px; border-radius:20px; font-weight:600; font-size:.82rem; }
.winner { background:#fef9c3; border:2px solid #f59e0b; border-radius:10px; padding:1rem 1.5rem; }
hr { border:none; border-top:1px solid #e8e8ec; margin:1.25rem 0; }
.stButton>button { border-radius:7px !important; font-weight:600 !important; }
.stButton>button[kind="primary"] { background:#e53e3e !important; color:white !important; border:none !important; }
.stTabs [data-baseweb="tab"] { font-weight:500; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# AHP MATH
# ─────────────────────────────────────────────────────────────────────────────
RI = {1:0.00, 2:0.00, 3:0.58, 4:0.90, 5:1.12, 6:1.24, 7:1.32, 8:1.41, 9:1.45, 10:1.49}

SAATY = {
    1:"Equal", 2:"Weak", 3:"Moderate", 4:"Moderate+",
    5:"Strong", 6:"Strong+", 7:"Very Strong", 8:"Very Strong+", 9:"Extreme",
}

def compute_ahp(matrix: np.ndarray):
    """Returns priority_vector, lambda_max, CI, CR, normalised_matrix."""
    n = matrix.shape[0]
    if n == 1:
        return np.array([1.0]), 1.0, 0.0, 0.0, matrix.copy()
    col_sums = matrix.sum(axis=0)
    col_sums = np.where(col_sums == 0, 1e-12, col_sums)
    norm = matrix / col_sums
    pv   = norm.mean(axis=1)
    lmax = float((matrix @ pv / np.where(pv==0,1e-12,pv)).mean())
    ci   = (lmax - n) / (n - 1)
    cr   = ci / RI.get(n, 1.49)
    return pv, lmax, ci, cr, norm

def build_matrix(upper_vals, n):
    m = np.ones((n, n))
    idx = 0
    for i in range(n):
        for j in range(i+1, n):
            v = upper_vals[idx]
            m[i,j] = v
            m[j,i] = 1.0/v
            idx += 1
    return m

def upper_n(n): return n*(n-1)//2

def cr_html(cr):
    if cr < 0.10:
        return f'<span class="cr-ok">✓ CR = {cr:.4f}  Consistent</span>'
    return f'<span class="cr-bad">✗ CR = {cr:.4f}  Inconsistent — revise</span>'

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
def _init():
    defaults = {
        # Alternatives
        "players": ["DJ Lemahieu", "Mike Trout", "Fernando Tatis Jr."],
        # Criteria
        "criteria": ["Hitting", "Fielding", "Running", "X Factor"],
        # Criteria pairwise upper-triangle (from Excel: H>F=2, H>R=5, H>X=4, F>R=2, F>X=1, R>X=1/2)
        "crit_upper": [2.0, 5.0, 4.0, 2.0, 1.0, 0.5],
        # Player raw scores per criterion  (rows=players, cols=criteria)
        "scores": np.array([
            [8.0, 10.0,  5.0, 10.0],   # DJ Lemahieu
            [10.0,  8.0,  8.0,  8.0],  # Mike Trout
            [8.0,  6.0, 10.0,  7.0],   # Fernando Tatis Jr.
        ], dtype=float),
        "result": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
_init()
S = st.session_state

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="badge">AHP • ANALYTIC HIERARCHY PROCESS</div>', unsafe_allow_html=True)
col_h1, col_h2 = st.columns([3,1])
with col_h1:
    st.markdown('<div class="section-title">⚾ Baseball Player Evaluation</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-sub">Saaty\'s pairwise comparison method — mirrors the Excel AHP-2 workbook approach</div>', unsafe_allow_html=True)
with col_h2:
    if st.button("▶  Run AHP", type="primary", use_container_width=True):
        # ── Compute ──────────────────────────────────────────────────────────
        nc = len(S["criteria"])
        na = len(S["players"])
        crit_mat = build_matrix(S["crit_upper"], nc)
        crit_pv, crit_lmax, crit_ci, crit_cr, crit_norm = compute_ahp(crit_mat)

        # Normalise raw scores per criterion (simple proportion like Excel)
        raw = S["scores"].astype(float)
        col_tots = raw.sum(axis=0)
        col_tots = np.where(col_tots==0, 1e-12, col_tots)
        norm_scores = raw / col_tots        # each column sums to 1
        weighted   = norm_scores * crit_pv  # multiply by criterion weight
        totals     = weighted.sum(axis=1)   # composite score per player

        S["result"] = {
            "crit_mat":   crit_mat,
            "crit_norm":  crit_norm,
            "crit_pv":    crit_pv,
            "crit_lmax":  crit_lmax,
            "crit_ci":    crit_ci,
            "crit_cr":    crit_cr,
            "raw":        raw,
            "col_tots":   col_tots,
            "norm_scores":norm_scores,
            "weighted":   weighted,
            "totals":     totals,
            "ranking":    np.argsort(-totals),
        }
        st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "⚙️  Setup",
    "📊  Criteria Pairwise",
    "🏟️  Player Scores",
    "🏆  Results",
])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — SETUP
# ═════════════════════════════════════════════════════════════════════════════
with tab1:
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### 👤 Players (Alternatives)")
        players_txt = st.text_area(
            "One per line", value="\n".join(S["players"]),
            height=140, key="players_input",
            help="Enter each player's name on a separate line."
        )
        new_players = [p.strip() for p in players_txt.strip().split("\n") if p.strip()]
        if new_players != S["players"]:
            S["players"] = new_players
            nc = len(S["criteria"])
            na = len(new_players)
            S["scores"] = np.ones((na, nc))
            S["result"] = None

    with col_b:
        st.markdown("#### 📋 Criteria")
        crit_txt = st.text_area(
            "One per line", value="\n".join(S["criteria"]),
            height=140, key="criteria_input",
            help="Enter each criterion on a separate line."
        )
        new_crit = [c.strip() for c in crit_txt.strip().split("\n") if c.strip()]
        if new_crit != S["criteria"]:
            S["criteria"] = new_crit
            nc = len(new_crit)
            S["crit_upper"] = [1.0] * upper_n(nc)
            na = len(S["players"])
            S["scores"] = np.ones((na, nc))
            S["result"] = None

    st.markdown("<br>", unsafe_allow_html=True)
    st.info(
        "**How it works (Excel approach):**  \n"
        "1. Fill in the criteria pairwise matrix (Saaty 1–9 scale) → derives criterion weights.  \n"
        "2. Fill in raw player scores per criterion (e.g. 1–10).  \n"
        "3. Click **Run AHP** → scores are normalised per column, multiplied by weights, and summed."
    )

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — CRITERIA PAIRWISE
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    nc   = len(S["criteria"])
    crits = S["criteria"]

    st.markdown("#### Criteria Pairwise Comparison Matrix")
    st.caption(
        "Enter how much more important row criterion is vs column criterion.  "
        "**Scale:** 1 = Equal · 3 = Moderate · 5 = Strong · 7 = Very Strong · 9 = Extreme.  "
        "Values < 1 mean the column criterion is more important."
    )

    # Show Saaty reference
    with st.expander("Saaty Scale Reference"):
        scale_df = pd.DataFrame({"Value": list(SAATY.keys()), "Meaning": list(SAATY.values())})
        st.dataframe(scale_df, use_container_width=False, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Upper-triangle inputs ─────────────────────────────────────────────────
    vals = list(S["crit_upper"])
    if len(vals) != upper_n(nc):
        vals = [1.0] * upper_n(nc)

    new_vals = list(vals)
    idx = 0

    header_cols = st.columns([2.5, 2.5, 1.2, 2.8])
    header_cols[0].markdown("**Criterion A**")
    header_cols[1].markdown("**Criterion B**")
    header_cols[2].markdown("**Value**")
    header_cols[3].markdown("**Interpretation**")
    st.markdown("<hr style='margin:4px 0 10px'>", unsafe_allow_html=True)

    for i in range(nc):
        for j in range(i+1, nc):
            c0, c1, c2, c3 = st.columns([2.5, 2.5, 1.2, 2.8])
            with c0: st.markdown(f"<div style='padding-top:6px;font-weight:500'>{crits[i]}</div>", unsafe_allow_html=True)
            with c1: st.markdown(f"<div style='padding-top:6px;color:#666'>vs  {crits[j]}</div>", unsafe_allow_html=True)
            with c2:
                v = st.number_input("", min_value=round(1/9,3), max_value=9.0,
                                    value=float(round(vals[idx],3)), step=0.5,
                                    key=f"cp_{i}_{j}", label_visibility="collapsed")
                new_vals[idx] = v
            with c3:
                if v >= 1:
                    lbl = SAATY.get(int(round(v)), "—")
                    st.markdown(f"<div style='padding-top:6px;font-size:.82rem;color:#e53e3e'>"
                                f"{lbl} — <b>{crits[i]}</b> favoured</div>", unsafe_allow_html=True)
                else:
                    inv = int(round(1/v))
                    lbl = SAATY.get(inv, "—")
                    st.markdown(f"<div style='padding-top:6px;font-size:.82rem;color:#2563eb'>"
                                f"{lbl} — <b>{crits[j]}</b> favoured</div>", unsafe_allow_html=True)
            idx += 1

    S["crit_upper"] = new_vals

    # ── Live matrix + CR preview ──────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    cmat = build_matrix(new_vals, nc)
    pv, lmax, ci, cr, cnorm = compute_ahp(cmat)

    col_cr, col_lm = st.columns([2,2])
    with col_cr:
        st.markdown(cr_html(cr), unsafe_allow_html=True)
    with col_lm:
        st.markdown(f"<span style='font-size:.82rem;color:#666'>λ_max = {lmax:.4f} &nbsp;·&nbsp; CI = {ci:.4f}</span>",
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Full matrix display
    st.markdown("**Full Pairwise Matrix**")
    mat_df = pd.DataFrame(cmat, index=crits, columns=crits)
    st.dataframe(mat_df.style.format("{:.4f}"), use_container_width=True)

    # Normalised matrix + weights
    col_norm, col_w = st.columns([3,2])
    with col_norm:
        st.markdown("**Normalised Matrix**")
        norm_df = pd.DataFrame(cnorm, index=crits, columns=crits)
        st.dataframe(norm_df.style.format("{:.4f}"), use_container_width=True)
    with col_w:
        st.markdown("**Derived Criterion Weights**")
        w_df = pd.DataFrame({
            "Criterion": crits,
            "Weight":    pv.round(4),
            "Weight %":  [f"{w*100:.1f}%" for w in pv],
        })
        st.dataframe(w_df, use_container_width=True, hide_index=True)

        # Bar chart for weights
        fig_w = px.bar(w_df, x="Criterion", y="Weight",
                       color="Weight", color_continuous_scale="Reds",
                       text="Weight %", title="Criterion Priority Weights")
        fig_w.update_layout(showlegend=False, coloraxis_showscale=False,
                            margin=dict(t=30,b=5), height=220,
                            plot_bgcolor="white", paper_bgcolor="white")
        fig_w.update_traces(textposition="outside")
        st.plotly_chart(fig_w, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — PLAYER SCORES
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("#### Player Raw Scores")
    st.caption(
        "Enter a numeric score for each player on each criterion (e.g. 1–10).  "
        "Higher = better. These are normalised **column-wise** (same as the Excel workbook)."
    )

    na   = len(S["players"])
    nc   = len(S["criteria"])
    raw  = S["scores"]
    if raw.shape != (na, nc):
        raw = np.ones((na, nc))
        S["scores"] = raw

    scores_df = pd.DataFrame(raw, index=S["players"], columns=S["criteria"])
    edited = st.data_editor(
        scores_df,
        use_container_width=True,
        key="score_editor",
        num_rows="fixed",
        column_config={c: st.column_config.NumberColumn(c, min_value=0.0, step=0.5) for c in S["criteria"]},
    )
    try:
        S["scores"] = edited.astype(float).values
    except Exception:
        st.warning("All values must be numeric.")

    # Show column sums (like Excel "Totals" row)
    col_sums = S["scores"].sum(axis=0)
    totals_row = pd.DataFrame([col_sums], index=["Column Total"], columns=S["criteria"])
    st.dataframe(totals_row.style.format("{:.2f}").set_properties(**{"font-weight":"bold"}),
                 use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Preview normalised scores
    with st.expander("Preview: Normalised Scores (column proportions)"):
        norm_s = S["scores"] / np.where(col_sums==0, 1e-12, col_sums)
        norm_s_df = pd.DataFrame(norm_s.round(4), index=S["players"], columns=S["criteria"])
        st.dataframe(norm_s_df.style.format("{:.4f}"), use_container_width=True)
        st.caption("Each column sums to 1.0. Multiplied by criterion weights → weighted scores.")

    # Radar for raw scores
    st.markdown("**Player Profile Radar**")
    fig_r = go.Figure()
    pal = ["#e53e3e","#2563eb","#059669","#d97706","#7c3aed"]
    for i, player in enumerate(S["players"]):
        vals_r = S["scores"][i].tolist()
        fig_r.add_trace(go.Scatterpolar(
            r=vals_r + [vals_r[0]],
            theta=S["criteria"] + [S["criteria"][0]],
            fill="toself", name=player,
            fillcolor=pal[i%len(pal)].replace("#","rgba(").replace(",",",,") if False else "rgba(0,0,0,0)",
            line=dict(color=pal[i%len(pal)], width=2),
            marker=dict(size=6),
        ))
    fig_r.update_layout(
        polar=dict(radialaxis=dict(visible=True)),
        paper_bgcolor="white", height=350,
        margin=dict(t=20,b=20),
        legend=dict(orientation="h", y=-0.1),
    )
    st.plotly_chart(fig_r, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — RESULTS
# ═════════════════════════════════════════════════════════════════════════════
with tab4:
    if S["result"] is None:
        st.info("Click **▶ Run AHP** (top-right) to compute results.")
        st.stop()

    R = S["result"]
    ranking   = R["ranking"]
    totals    = R["totals"]
    weighted  = R["weighted"]
    crits     = S["criteria"]
    players   = S["players"]

    # ── Winner banner ─────────────────────────────────────────────────────────
    winner = players[ranking[0]]
    st.markdown(f"""
    <div class="winner">
      <span style="font-size:2rem">🏆</span>
      <span style="font-size:1.4rem;font-weight:700;margin-left:.5rem">{winner}</span>
      <span style="font-size:1rem;color:#92400e;margin-left:.5rem">
        — Best Player  |  AHP Score: {totals[ranking[0]]:.4f}
      </span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Top 3 podium ──────────────────────────────────────────────────────────
    medals = ["🥇", "🥈", "🥉"]
    top3 = list(ranking[:3])
    rest = list(ranking[3:])

    # Render top 3 inside their own container so nothing else bleeds into this row
    with st.container():
        c1, c2, c3 = st.columns(3)
        podium_slots = [c1, c2, c3]
        for slot, rank_idx in zip(podium_slots, top3):
            p   = players[rank_idx]
            s   = totals[rank_idx]
            pos = list(ranking).index(rank_idx)
            medal  = medals[pos]
            border = "2px solid #f59e0b" if pos == 0 else "1px solid #e8e8ec"
            bg     = "#fffbeb"           if pos == 0 else "white"
            with slot:
                st.markdown(f"""
                <div class="metric-box" style="border:{border};background:{bg};">
                  <div style="font-size:1.8rem">{medal}</div>
                  <div class="metric-val" style="font-size:1.2rem">{p}</div>
                  <div style="font-size:1.15rem;color:#e53e3e;font-weight:700;margin:.2rem 0">{s:.4f}</div>
                  <div class="metric-lbl">Rank #{pos + 1}</div>
                </div>
                """, unsafe_allow_html=True)

    # ── Remaining players — strictly on a new row below ───────────────────────
    if rest:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            "<div style='font-size:.8rem;font-weight:600;color:#9ca3af;"
            "text-transform:uppercase;letter-spacing:.08em;margin-bottom:.5rem'>"
            "Other Contenders</div>",
            unsafe_allow_html=True,
        )
        with st.container():
            n_rest   = len(rest)
            # max 4 per row; pad remaining slots with empty so columns stay stable
            cols_per_row = min(n_rest, 4)
            rest_cols = st.columns(cols_per_row)
            for col, rank_idx in zip(rest_cols, rest):
                p   = players[rank_idx]
                s   = totals[rank_idx]
                pos = list(ranking).index(rank_idx)
                with col:
                    st.markdown(f"""
                    <div class="metric-box"
                         style="background:#f9fafb;border:1px solid #e8e8ec;padding:.8rem;">
                      <div style="font-size:.9rem;font-weight:700;color:#9ca3af">
                        # {pos + 1}
                      </div>
                      <div style="font-size:1rem;font-weight:600;color:#374151;margin:.25rem 0">
                        {p}
                      </div>
                      <div style="font-size:.95rem;color:#6b7280;font-weight:600">
                        {s:.4f}
                      </div>
                      <div class="metric-lbl">Score</div>
                    </div>
                    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(cr_html(R["crit_cr"]), unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Full AHP Table (mirrors the Excel layout) ─────────────────────────────
    st.markdown("#### AHP Score Table")

    rows = []
    for i, p in enumerate(players):
        row = {"Player": p}
        for j, c in enumerate(crits):
            row[c]                  = round(float(R["raw"][i,j]), 2)
            row[f"{c} Weight"]      = round(float(R["crit_pv"][j]), 2)
            row[f"{c} Score"]       = round(float(R["weighted"][i,j]), 4)
        row["Total"] = round(float(totals[i]), 4)
        rows.append(row)

    result_df = pd.DataFrame(rows)

    # Highlight the winner row
    def highlight_winner(row):
        best_score = result_df["Total"].max()
        color = "background-color:#fef9c3" if row["Total"] == best_score else ""
        return [color]*len(row)

    st.dataframe(
        result_df.style.apply(highlight_winner, axis=1).format(precision=4),
        use_container_width=True, hide_index=True,
    )

    # Ranking summary
    rank_df = pd.DataFrame([
        {"Rank": i+1, "Player": players[r], "AHP Total Score": round(float(totals[r]),4)}
        for i, r in enumerate(ranking)
    ])
    st.markdown("**Ranking Summary**")
    st.dataframe(rank_df, use_container_width=True, hide_index=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Charts ────────────────────────────────────────────────────────────────
    c_left, c_right = st.columns(2)

    with c_left:
        st.markdown("#### Composite AHP Scores")
        sorted_players = [players[r] for r in ranking]
        sorted_scores  = [totals[r] for r in ranking]
        bar_colors = ["#e53e3e" if i==0 else "#93c5fd" for i in range(len(players))]
        fig_bar = go.Figure(go.Bar(
            x=sorted_players, y=sorted_scores,
            marker_color=bar_colors,
            text=[f"{s:.4f}" for s in sorted_scores],
            textposition="outside",
        ))
        fig_bar.update_layout(
            margin=dict(t=10,b=10), height=320,
            plot_bgcolor="white", paper_bgcolor="white",
            yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
            font=dict(family="DM Sans"),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with c_right:
        st.markdown("#### Criterion Weights (Radar)")
        fig_rad = go.Figure(go.Scatterpolar(
            r=list(R["crit_pv"]) + [R["crit_pv"][0]],
            theta=crits + [crits[0]],
            fill="toself",
            fillcolor="rgba(229,62,62,0.12)",
            line=dict(color="#e53e3e", width=2),
            marker=dict(size=7),
        ))
        fig_rad.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, max(R["crit_pv"])*1.3])),
            paper_bgcolor="white", height=320,
            margin=dict(t=10,b=10),
        )
        st.plotly_chart(fig_rad, use_container_width=True)

    # Stacked weighted score contribution
    st.markdown("#### Score Composition — Criterion Contributions per Player")
    stack_data = []
    for j, c in enumerate(crits):
        for i, p in enumerate(players):
            stack_data.append({"Player": p, "Criterion": c, "Weighted Score": float(weighted[i,j])})
    stack_df = pd.DataFrame(stack_data)
    fig_stack = px.bar(stack_df, x="Player", y="Weighted Score", color="Criterion",
                       barmode="stack", title="",
                       color_discrete_sequence=px.colors.qualitative.Set2)
    fig_stack.update_layout(
        margin=dict(t=10,b=10), height=320,
        plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", y=-0.2),
        font=dict(family="DM Sans"),
    )
    st.plotly_chart(fig_stack, use_container_width=True)

    # ── Step-by-step workings (like Excel) ───────────────────────────────────
    with st.expander("📋  Step-by-step Workings (full detail)"):
        st.markdown("**Step 1: Criteria Pairwise Matrix**")
        mat_disp = pd.DataFrame(R["crit_mat"].round(4), index=crits, columns=crits)
        st.dataframe(mat_disp.style.format("{:.4f}"), use_container_width=True)

        col_tot = R["crit_mat"].sum(axis=0)
        st.markdown(f"**Column Totals:** {dict(zip(crits, col_tot.round(4)))}")

        st.markdown("**Step 2: Normalised Matrix (each column ÷ its total)**")
        norm_disp = pd.DataFrame(R["crit_norm"].round(4), index=crits, columns=crits)
        st.dataframe(norm_disp.style.format("{:.4f}"), use_container_width=True)

        w_disp = pd.DataFrame({
            "Criterion": crits,
            "Row Average (= Weight)": R["crit_pv"].round(4),
        })
        st.markdown("**Step 3: Row averages = Priority Weights**")
        st.dataframe(w_disp, use_container_width=True, hide_index=True)
        st.markdown(f"λ_max = `{R['crit_lmax']:.4f}` · CI = `{R['crit_ci']:.4f}` · CR = `{R['crit_cr']:.4f}`")

        st.markdown("**Step 4: Raw Player Scores**")
        raw_disp = pd.DataFrame(R["raw"], index=players, columns=crits)
        st.dataframe(raw_disp.style.format("{:.2f}"), use_container_width=True)

        st.markdown("**Step 5: Column-Normalised Scores (each column ÷ its total)**")
        ns_disp = pd.DataFrame(R["norm_scores"].round(4), index=players, columns=crits)
        st.dataframe(ns_disp.style.format("{:.4f}"), use_container_width=True)

        st.markdown("**Step 6: Weighted Scores (Normalised Score × Criterion Weight)**")
        ws_disp = pd.DataFrame(R["weighted"].round(4), index=players, columns=crits)
        ws_disp["TOTAL"] = R["totals"].round(4)
        st.dataframe(ws_disp.style.format("{:.4f}")
                     .highlight_max(subset=["TOTAL"], color="#fef9c3"),
                     use_container_width=True)

    # ── Download ──────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button(
        "⬇  Download Results CSV",
        data=result_df.to_csv(index=False).encode("utf-8"),
        file_name="ahp_baseball_results.csv",
        mime="text/csv",
    )
