import uuid
import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"

# KEIN st.set_page_config() hier (nur im Hauptfile chatbot.py)

# Safety: falls sid nicht im Hauptfile gesetzt wurde
if "sid" not in st.session_state:
    st.session_state.sid = str(uuid.uuid4())

# UI language state
if "ui_lang" not in st.session_state:
    st.session_state.ui_lang = "de"

def t(de: str, en: str) -> str:
    return en if st.session_state.ui_lang == "en" else de

# Chat state
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("🤖   OB-ChatBot")
st.caption(t(
    "Sprache wird automatisch aus deiner Nachricht erkannt (Deutsch/English).",
    "Language is auto-detected from your message (German/English)."
))

# Render history
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

user_text = st.chat_input(t("Schreib deine Frage…", "Type your question…"))

if user_text:
    # Show user message immediately
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    # Read global sidebar config (set in chatbot.py)
    use_rag = st.session_state.get("use_rag", True)
    top_k = st.session_state.get("top_k", 4)

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

    # keep backend session id
    if data.get("session_id"):
        st.session_state.sid = data["session_id"]

    # update UI language if backend returns lang
    if data.get("lang") in ("de", "en"):
        st.session_state.ui_lang = data["lang"]

    bot_reply = data.get("reply", "")
    sources = data.get("sources", [])

    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    with st.chat_message("assistant"):
        st.markdown(bot_reply)
        if sources:
            with st.expander(t("Quellen", "Sources")):
                for s in sources:
                    st.write(s)


