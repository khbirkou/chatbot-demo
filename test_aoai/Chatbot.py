import uuid
import requests
import streamlit as st
import os

API_URL = "http://127.0.0.1:8000"
#API_URL = "http://localhost:8000"

#API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

# Einmalig: Page Config nur im Router
st.set_page_config(page_title="OB Bot", page_icon="🤖", layout="wide")

# Sticky backend session id (global)
if "sid" not in st.session_state:
    st.session_state.sid = str(uuid.uuid4())

# Global defaults
st.session_state.setdefault("use_rag", True)
st.session_state.setdefault("top_k", 4)

# Global sidebar (für alle Pages)
with st.sidebar:
    st.markdown("### RAG Configuration")
    st.session_state.use_rag = st.toggle(
        "Use RAG Knowledge Base",
        value=st.session_state.use_rag
    )
    st.session_state.top_k = st.slider(
        "Top-K Quellen",
        1, 8,
        st.session_state.top_k,
        1
    )

    st.divider()

    if st.button("Reload KB (neue Dateien)"):
        r = requests.post(f"{API_URL}/reload_kb", timeout=30)
        r.raise_for_status()
        st.success(f"Neu indexiert: {r.json()['chunks']} Chunks")

    # Chat-Verlauf global löschen
    if st.button("Chat leeren"):
        st.session_state.messages = []
        st.rerun()

# Navigation: nur Seiten definieren

nav = st.navigation(
    [
        st.Page("pages/0_Home.py", title="Home", icon="🏠"),
        st.Page("pages/1_Requirement_Refinement.py", title="Requirement Refinement", icon="🛠️"),
        st.Page("pages/2_Requirements_to_Testcases.py", title="Requirements to Testcases", icon="🧪"),
        st.Page("pages/3_Database.py", title="Database", icon="🗄️"),
        st.Page("pages/4_Test_Data_Request.py", title="Test Data Request", icon="🧾"),
        st.Page("pages/5_Chat.py", title="Chatbot", icon="💬"),
    ]
)

nav.run()
