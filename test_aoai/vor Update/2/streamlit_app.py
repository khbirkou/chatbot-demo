import uuid
import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Order Booking Bot", layout="wide")

# Sticky session id for language preference on backend
if "sid" not in st.session_state:
    st.session_state.sid = str(uuid.uuid4())

with st.sidebar:
    st.header("RAG Configuration")
    use_rag = st.toggle("Use RAG Knowledge Base", value=True)
    top_k = st.slider("Top-K Quellen", 1, 8, 4, 1)

    st.divider()
    if st.button("Reload KB (neue Dateien)"):
        r = requests.post(f"{API_URL}/reload_kb", timeout=30)
        r.raise_for_status()
        st.success(f"Neu indexiert: {r.json()['chunks']} Chunks")

    if st.button("Clear chat"):
        st.session_state.messages = []
        st.rerun()

st.title("Order Booking Chatbot")

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

user_text = st.chat_input("Frag etwas aus deinen Dokumenten…")
if user_text:
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    r = requests.post(
        f"{API_URL}/chat",
        json={
            "message": user_text,
            "use_rag": use_rag,
            "top_k": top_k,
            "session_id": st.session_state.sid,
        },
        timeout=60,
    )

    r.raise_for_status()
    data = r.json()

    # keep backend session id if it ever changes
    if "session_id" in data and data["session_id"]:
        st.session_state.sid = data["session_id"]

    bot_reply = data["reply"]
    sources = data.get("sources", [])

    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    with st.chat_message("assistant"):
        st.markdown(bot_reply)
        if sources:
            with st.expander("Quellen"):
                for s in sources:
                    st.write(s)
