import bootstrap

import streamlit as st
from persistence.engine import get_engine
from persistence.repositories.decision_repo import DecisionRepo
from persistence.repositories.scenario_repo import ScenarioRepo

st.title("Step 1: Decision and Scenario Setup")

engine = get_engine()
decision_repo = DecisionRepo(engine)
scenario_repo = ScenarioRepo(engine)

st.session_state.setdefault("decision_id", None)
st.session_state.setdefault("scenario_id", None)

st.subheader("1A) Select or Create Decision")

decisions = decision_repo.list_decisions(limit=50)
decision_options = ["Create new…"] + [d["decision_id"] for d in decisions]

selected_decision = st.selectbox(
    "Decision",
    options=decision_options,
    format_func=lambda x: "Create new…" if x == "Create new…" else next(
        dd["title"] for dd in decisions if dd["decision_id"] == x
    ) if decisions else "Create new…",
)

if selected_decision == "Create new…":
    title = st.text_input("Decision title", value="Admissions Selection")
    purpose = st.text_area("Purpose / context", value="Select best candidate using MCDA.", height=90)
    owner_team = st.text_input("Owner team (optional)", value="")

    if st.button("Create Decision", type="primary"):
        did = decision_repo.create_decision(title.strip(), purpose.strip(), owner_team.strip())
        st.session_state["decision_id"] = did
        st.session_state["scenario_id"] = None
        st.success(f"Decision created: {did}")
else:
    st.session_state["decision_id"] = selected_decision
    st.info(f"Selected decision: {selected_decision}")

st.divider()
st.subheader("1B) Select or Create Scenario")

if not st.session_state.get("decision_id"):
    st.warning("Select or create a Decision first.")
    st.stop()

scenarios = scenario_repo.list_scenarios(st.session_state["decision_id"], limit=100)
scenario_options = ["Create new…"] + [s["scenario_id"] for s in scenarios]

selected_scenario = st.selectbox(
    "Scenario",
    options=scenario_options,
    format_func=lambda x: "Create new…" if x == "Create new…" else next(
        ss["name"] for ss in scenarios if ss["scenario_id"] == x
    ) if scenarios else "Create new…",
)

if selected_scenario == "Create new…":
    sname = st.text_input("Scenario name", value="Base Case")
    sdesc = st.text_area("Scenario description (optional)", value="", height=90)
    created_by = st.session_state.get("user_name", "")

    if st.button("Create Scenario"):
        sid = scenario_repo.create_scenario(
            decision_id=st.session_state["decision_id"],
            name=sname.strip(),
            description=sdesc.strip(),
            created_by=created_by,
        )
        st.session_state["scenario_id"] = sid
        st.success(f"Scenario created: {sid}")
else:
    st.session_state["scenario_id"] = selected_scenario
    st.info(f"Selected scenario: {selected_scenario}")

st.divider()

col1, col2 = st.columns(2)
with col1:
    st.button("Back", disabled=True)
with col2:
    can_next = bool(st.session_state.get("scenario_id"))
    if st.button("Next: Go to Data Input", type="primary", disabled=not can_next):
        st.switch_page("pages/2_data_input.py")

st.caption("Decision holds the business problem. Scenario holds a version of inputs under that decision.")
