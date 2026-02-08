import os
import glob
import uuid
from dataclasses import dataclass
from typing import List, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

from pypdf import PdfReader
from rank_bm25 import BM25Okapi

# ----------------- Config -----------------

load_dotenv("keyaoai.env")  # oder ".env"

client = OpenAI(
    base_url="https://ai-orderbooking-01.openai.azure.com/openai/v1/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)

DEPLOYMENT = "gpt-4.1-mini"
BOT_NAME = "OB Bot"

app = FastAPI()

# ----------------- RAG: KB laden + Index bauen -----------------

@dataclass
class Chunk:
    doc_id: str
    text: str


CHUNKS: List[Chunk] = []
BM25 = None
TOKENIZED: List[List[str]] = []


def simple_tokenize(text: str) -> List[str]:
    return [t for t in "".join(ch if ch.isalnum() else " " for ch in (text or "").lower()).split() if t]


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    out = []
    i = 0
    while i < len(text):
        out.append(text[i:i + chunk_size])
        i += max(1, chunk_size - overlap)
    return out


def read_pdf(path: str) -> str:
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def load_kb(kb_dir: str = "kb") -> None:
    global CHUNKS, BM25, TOKENIZED
    CHUNKS = []
    TOKENIZED = []

    paths = []
    paths += glob.glob(os.path.join(kb_dir, "*.txt"))
    paths += glob.glob(os.path.join(kb_dir, "*.md"))
    paths += glob.glob(os.path.join(kb_dir, "*.pdf"))

    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        try:
            if ext in [".txt", ".md"]:
                with open(p, "r", encoding="utf-8") as f:
                    text = f.read()
            elif ext == ".pdf":
                text = read_pdf(p)
            else:
                continue
        except Exception as e:
            print(f"KB: konnte Datei nicht lesen {p}: {e}")
            continue

        for idx, ch in enumerate(chunk_text(text)):
            doc_id = f"{os.path.basename(p)}#chunk{idx}"
            CHUNKS.append(Chunk(doc_id=doc_id, text=ch))
            TOKENIZED.append(simple_tokenize(ch))

    if TOKENIZED:
        BM25 = BM25Okapi(TOKENIZED)
        print(f"KB: {len(paths)} Dateien, {len(CHUNKS)} Chunks indexiert")
    else:
        BM25 = None
        print("KB: keine Inhalte gefunden (Ordner kb leer?)")


def retrieve(query: str, top_k: int = 4) -> List[Chunk]:
    if BM25 is None or not CHUNKS:
        return []
    qtok = simple_tokenize(query)
    scores = BM25.get_scores(qtok)
    best = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [CHUNKS[i] for i in best if scores[i] > 0]


@app.on_event("startup")
def _startup():
    load_kb("kb")

# ----------------- Session State (in-memory) -----------------
# Hinweis: Bei mehreren Server-Instanzen/Restart geht das verloren -> dann in Redis/DB auslagern.

SESSION_LANG: Dict[str, str] = {}         # "de" / "en"
SESSION_LAST_REPLY: Dict[str, str] = {}   # last assistant reply text
SESSION_NAME_CORRECTED: Dict[str, bool] = {}  # name correction already done?

# ----------------- Language + Intent helpers -----------------

_GREETINGS = {
    "hi", "hii", "hello", "hey", "hallo", "guten tag", "guten morgen", "guten abend",
    "servus", "moin", "yo"
}

def normalize(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

def is_greeting_only(text: str) -> bool:
    t = normalize(text)
    return t in _GREETINGS

def is_language_only(text: str) -> bool:
    t = normalize(text)
    return t in {"english", "englisch", "deutsch", "german", "de", "en"}

def detect_lang(text: str) -> str:
    """
    Heuristik:
    - Wenn der User explizit "english/englisch" schreibt => en
    - Wenn er "deutsch/german" schreibt => de
    - Sonst: einfache Sprach-Indizien.
    """
    t = normalize(text)

    if t in {"english", "englisch", "en"}:
        return "en"
    if t in {"deutsch", "german", "de"}:
        return "de"

    # Sehr einfache Erkennung: typische deutsche Wörter/Zeichen
    german_signals = ["ß", "ä", "ö", "ü", " nicht ", " und ", " oder ", " bitte ", " kannst ", " können ", " ich "]
    tt = f" {t} "
    if any(sig in tt for sig in german_signals):
        return "de"

    # Default: English
    return "en"

def wants_translation_to_en(text: str) -> bool:
    t = normalize(text)
    triggers = [
        "auf englisch zurück", "auf englisch bitte", "auf englisch",
        "in englisch", "kannst du das auf englisch", "kannst du mir das auf englisch",
        "übersetz", "uebersetz", "translate", "in english", "english please",
        "can you give it in english", "can you return it in english",
        "please answer in english",
    ]
    return any(x in t for x in triggers)

def wants_translation_to_de(text: str) -> bool:
    t = normalize(text)
    triggers = [
        "auf deutsch zurück", "auf deutsch bitte", "auf deutsch",
        "in deutsch", "kannst du das auf deutsch", "kannst du mir das auf deutsch",
        "übersetz", "uebersetz", "translate", "in german", "german please",
        "please answer in german",
    ]
    # "übersetz/translate" ist mehrdeutig -> hier nur DE, wenn "deutsch/german" vorkommt
    if "übersetz" in t or "uebersetz" in t or "translate" in t:
        return ("deutsch" in t) or ("german" in t) or ("auf deutsch" in t) or ("in german" in t)
    return any(x in t for x in triggers)

def mentions_other_bot_name(text: str) -> bool:
    t = normalize(text)
    # falls User "chatgpt" oder "copilot" erwähnt
    return ("chatgpt" in t) or ("copilot" in t)

def translate_text(text: str, target_lang: str) -> str:
    target = "English" if target_lang == "en" else "German"
    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": f"Translate the text to {target}. Output only the translation, no extra text."},
            {"role": "user", "content": text},
        ],
    )
    return resp.choices[0].message.content

# ----------------- API -----------------

class ChatRequest(BaseModel):
    message: str
    use_rag: bool = False
    top_k: int = 4
    session_id: Optional[str] = None  # Streamlit sendet das mit


@app.post("/chat")
def chat(req: ChatRequest):
    msg = req.message or ""
    sid = req.session_id or str(uuid.uuid4())

    # Sprache: automatisch aus User-Text ableiten (oder die Session weiter nutzen)
    lang = detect_lang(msg)
    SESSION_LANG[sid] = lang

    # 1) User schreibt nur "english"/"deutsch" => bestätige nur die Sprachumschaltung
    if is_language_only(msg):
        if lang == "en":
            reply = "Sure — I’ll reply in English from now on. How can I help?"
        else:
            reply = "Klar — ich antworte ab jetzt auf Deutsch. Wie kann ich dir helfen?"
        SESSION_LAST_REPLY[sid] = reply
        return {"reply": reply, "sources": [], "session_id": sid}

    # 2) Übersetzungswunsch: Übersetze die letzte Bot-Antwort
    if wants_translation_to_en(msg) or wants_translation_to_de(msg):
        target_lang = "en" if wants_translation_to_en(msg) else "de"
        SESSION_LANG[sid] = target_lang

        last = (SESSION_LAST_REPLY.get(sid) or "").strip()
        if not last:
            reply = (
                "Sure — please paste the text you want me to translate to English."
                if target_lang == "en"
                else "Klar — bitte füge den Text ein, den ich ins Deutsche übersetzen soll."
            )
            SESSION_LAST_REPLY[sid] = reply
            return {"reply": reply, "sources": [], "session_id": sid}

        translated = translate_text(last, target_lang)
        SESSION_LAST_REPLY[sid] = translated
        return {"reply": translated, "sources": [], "session_id": sid}

    # 3) Reine Begrüßung => nur kurze Antwort, ohne RAG
    if is_greeting_only(msg):
        reply = "Hello! How can I help you?" if lang == "en" else "Hallo! Wie kann ich dir helfen?"
        SESSION_LAST_REPLY[sid] = reply
        return {"reply": reply, "sources": [], "session_id": sid}

    # -------- RAG Retrieval --------
    context_chunks = retrieve(msg, top_k=max(1, min(req.top_k, 8))) if req.use_rag else []
    context_text = ""
    sources = []
    if context_chunks:
        sources = [c.doc_id for c in context_chunks]
        context_text = "\n\n".join([f"[{i+1}] SOURCE: {c.doc_id}\n{c.text}" for i, c in enumerate(context_chunks)])

    target_label = "English" if lang == "en" else "Deutsch"

    # Name correction: nur 1x pro Session
    do_name_correction = False
    if mentions_other_bot_name(msg) and not SESSION_NAME_CORRECTED.get(sid, False):
        do_name_correction = True
        SESSION_NAME_CORRECTED[sid] = True

    # System prompt
    if lang == "en":
        system = (
            f"You are {BOT_NAME} (OrderBooking Bot). Reply in English.\n"
            "Use any provided context as the primary source.\n"
            "If the context is in another language, you may use it and translate relevant parts.\n"
            "If the answer is not in the context (and you cannot know), say that you don't know.\n"
            "Do NOT repeat your name in every message.\n"
        )
        if do_name_correction:
            system += "The user mentioned another assistant name; start your reply with: 'I’m OB Bot.' (only this time).\n"
    else:
        system = (
            f"Du bist {BOT_NAME} (OrderBooking Bot). Antworte auf Deutsch.\n"
            "Wenn Kontext bereitgestellt wird, nutze ihn als Hauptgrundlage.\n"
            "Wenn der Kontext in einer anderen Sprache ist, darfst du ihn nutzen und relevante Stellen übersetzen.\n"
            "Wenn die Antwort nicht im Kontext steht (und du es nicht wissen kannst), sage ehrlich, dass du es nicht weißt.\n"
            "Nenne deinen Namen nicht in jeder Antwort.\n"
        )
        if do_name_correction:
            system += "Der Nutzer hat dich mit einem anderen Namen angesprochen; beginne die Antwort mit: 'Ich bin OB Bot.' (nur dieses Mal).\n"

    messages = [{"role": "system", "content": system}]
    if context_text:
        messages.append({"role": "system", "content": f"Kontext:\n{context_text}"})
    messages.append({"role": "user", "content": msg})

    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=messages,
    )

    reply = resp.choices[0].message.content
    SESSION_LAST_REPLY[sid] = reply
    return {"reply": reply, "sources": sources, "session_id": sid}


@app.post("/reload_kb")
def reload_kb():
    load_kb("kb")
    return {"ok": True, "chunks": len(CHUNKS)}
