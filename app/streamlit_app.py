
import bootstrap
import streamlit as st
from persistence.engine import ping_db

from persistence.engine import ping_db

st.set_page_config(page_title="MCDA MVP", layout="wide")

st.title("MCDA MVP (TOPSIS + VFT)")
st.caption("Wizard workflow: Decision → Scenario → Data → Run → Results")

st.session_state.setdefault("user_name", "atharva")
st.session_state.setdefault("decision_id", None)
st.session_state.setdefault("scenario_id", None)

with st.sidebar:
    st.header("Workflow")
    st.session_state["user_name"] = st.text_input("Your name", value=st.session_state["user_name"])

    st.divider()
    ok = ping_db()
    st.write("DB:", "✅" if ok else "❌")
    if not ok:
        st.warning("Database not reachable. Fix DATABASE_URL then refresh.")
        st.stop()

    decision_ok = bool(st.session_state.get("decision_id"))
    scenario_ok = bool(st.session_state.get("scenario_id"))

    st.write("Step 1: Decision", "✅" if decision_ok else "⬜")
    st.write("Step 2: Scenario", "✅" if scenario_ok else "⬜")
    st.write("Step 3: Data Input", "⬜")
    st.write("Step 4: Run", "⬜")
    st.write("Step 5: Results", "⬜")

    st.divider()
    st.subheader("Quick jump")
    if st.button("Go to Step 1"):
        st.switch_page("pages/1_decision_setup.py")

    if st.button("Go to Step 2"):
        st.switch_page("pages/2_data_input.py")

st.write("Use the sidebar steps. The pages will guide you with Next and Back buttons.")
