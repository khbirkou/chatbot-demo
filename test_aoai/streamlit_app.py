import uuid
import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"

#st.set_page_config(page_title="Order Booking Bot", layout="wide")
st.set_page_config(
    page_title="Chatbot",
    page_icon="🤖",
    layout="wide",
)

# Sticky session id for backend session (language, name-correction, etc.)
if "sid" not in st.session_state:
    st.session_state.sid = str(uuid.uuid4())

# Remember last detected language for UI labels (fallback)
if "ui_lang" not in st.session_state:
    st.session_state.ui_lang = "de"  # default


def t(de: str, en: str) -> str:
    """Tiny helper for bilingual UI text."""
    return en if st.session_state.ui_lang == "en" else de


with st.sidebar:
    st.header("RAG Configuration")
    use_rag = st.toggle("Use RAG Knowledge Base", value=True)
    top_k = st.slider("Top-K Quellen", 1, 8, 4, 1)

    st.divider()

    if st.button(t("Reload KB (neue Dateien)", "Reload KB (new files)")):
        r = requests.post(f"{API_URL}/reload_kb", timeout=30)
        r.raise_for_status()
        st.success(t(
            f"Neu indexiert: {r.json()['chunks']} Chunks",
            f"Re-indexed: {r.json()['chunks']} chunks"
        ))

    if st.button(t("Chat leeren", "Clear chat")):
        st.session_state.messages = []
        st.rerun()

st.title("Order Booking Chatbot")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Show chat history
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Dynamic placeholder based on last known language
user_text = st.chat_input(t("Schreib deine Frage…", "Type your question…"))

if user_text:
    # Add user message to UI immediately
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    # Call backend
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

    # Keep backend session id if it ever changes
    if data.get("session_id"):
        st.session_state.sid = data["session_id"]

    # Update UI language from backend (requires app.py to return "lang")
    if data.get("lang") in ("de", "en"):
        st.session_state.ui_lang = data["lang"]

    bot_reply = data.get("reply", "")
    sources = data.get("sources", [])

    # Add assistant message
    st.session_state.messages.append({"role": "assistant", "content": bot_reply})
    with st.chat_message("assistant"):
        st.markdown(bot_reply)
        if sources:
            with st.expander(t("Quellen", "Sources")):
                for s in sources:
                    st.write(s)

# Optional small footer info
st.caption(t("Sprache wird automatisch aus deiner Nachricht erkannt.", "Language is auto-detected from your message."))
