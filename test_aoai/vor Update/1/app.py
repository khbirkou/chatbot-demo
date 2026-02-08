import os
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

load_dotenv("keyaoai.env")  # oder ".env", je nach deinem Dateinamen

client = OpenAI(
    base_url="https://ai-orderbooking-01.openai.azure.com/openai/v1/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)

DEPLOYMENT = "gpt-4.1-mini"

app = FastAPI()

# In-Memory Store: session_id -> list[dict]
SESSIONS: dict[str, list[dict]] = {}

class ChatRequest(BaseModel):
    session_id: str
    message: str

@app.post("/chat")
def chat(req: ChatRequest):
    history = SESSIONS.setdefault(req.session_id, [])

    # User Message anhängen
    history.append({"role": "user", "content": req.message})

    # Verlauf an das Modell senden
    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": "Du bist ein hilfreicher Assistent."},
            *history
        ],
    )

    reply = resp.choices[0].message.content
    history.append({"role": "assistant", "content": reply})

    return {"reply": reply}

@app.post("/reset")
def reset(req: dict):
    session_id = req.get("session_id")
    if session_id:
        SESSIONS.pop(session_id, None)
    return {"ok": True}
