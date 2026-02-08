import uuid
import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Guidance Chatbot", layout="wide")

# Session-ID pro Browser-Session
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

with st.sidebar:
    st.header("Conversation Management")
    if st.button("Clear Conversation"):
        requests.post(f"{API_URL}/reset", json={"session_id": st.session_state.session_id})
        st.session_state.messages = []

st.title("Guidance Chatbot")

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

user_text = st.chat_input("Ask me something…")
if user_text:
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    r = requests.post(
        f"{API_URL}/chat",
        json={"session_id": st.session_state.session_id, "message": user_text},
        timeout=60,
    )
    r.raise_for_status()
    bot_reply = r.json()["reply"]

    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    with st.chat_message("assistant"):
        st.markdown(bot_reply)
