import os
import glob
import uuid
import json
from dataclasses import dataclass
from typing import List, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from pypdf import PdfReader
from rank_bm25 import BM25Okapi

import sqlite3


# ----------------- Config -----------------

load_dotenv("keyaoai.env")  # oder ".env"

client = OpenAI(
    base_url="https://ai-orderbooking-01.openai.azure.com/openai/v1/",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)

DEPLOYMENT = "gpt-4.1-mini"
BOT_NAME = "OB Bot"

# SQLite DB
DB_PATH = "greenmow.db"
ALLOWED_MOWER_STATUSES = {"AVAILABLE", "IN_SERVICE", "MAINTENANCE", "OUT_OF_ORDER"}

# Work Orders (passt zu deinem PRAGMA table_info(work_orders))
ALLOWED_WO_PRIORITY = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
ALLOWED_WO_STATUS = {"OPEN", "IN_PROGRESS", "DONE", "CANCELLED"}

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


# ----------------- SQLite helpers -----------------

def db_connect():
    if not os.path.exists(DB_PATH):
        raise RuntimeError(f"DB file not found: {DB_PATH} (hast du db_init.py schon ausgeführt?)")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---- Mowers ----

def db_list_mowers(status: Optional[str] = None) -> List[dict]:
    if status and status not in ALLOWED_MOWER_STATUSES:
        raise ValueError(f"Invalid status. Allowed: {sorted(ALLOWED_MOWER_STATUSES)}")
    with db_connect() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT id, model, site, status, last_service_date FROM mowers WHERE status = ? ORDER BY id",
                (status,),
            )
        else:
            cur.execute("SELECT id, model, site, status, last_service_date FROM mowers ORDER BY id")
        return [dict(r) for r in cur.fetchall()]


def db_get_mower(mower_id: str) -> Optional[dict]:
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, model, site, status, last_service_date FROM mowers WHERE id = ?",
            (mower_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def db_update_mower_status(mower_id: str, new_status: str) -> dict:
    if new_status not in ALLOWED_MOWER_STATUSES:
        return {"ok": False, "error": f"Invalid status. Allowed: {sorted(ALLOWED_MOWER_STATUSES)}"}

    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE mowers SET status = ? WHERE id = ?", (new_status, mower_id))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "Mower not found"}
        return {"ok": True, "mower": db_get_mower(mower_id)}


# ---- Work Orders ----
# Schema (dein Screenshot):
# id INTEGER PK, mower_id TEXT NOT NULL, title TEXT NOT NULL, priority TEXT NOT NULL,
# status TEXT NOT NULL, owner TEXT NULL, created_at TEXT NOT NULL

def db_list_work_orders(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    mower_id: Optional[str] = None,
    limit: int = 50
) -> List[dict]:
    if status and status not in ALLOWED_WO_STATUS:
        raise ValueError(f"Invalid work order status. Allowed: {sorted(ALLOWED_WO_STATUS)}")
    if priority and priority not in ALLOWED_WO_PRIORITY:
        raise ValueError(f"Invalid work order priority. Allowed: {sorted(ALLOWED_WO_PRIORITY)}")

    limit = max(1, min(int(limit or 50), 200))

    q = """
        SELECT id, mower_id, title, priority, status, owner, created_at
        FROM work_orders
        WHERE
            (? IS NULL OR status = ?)
            AND (? IS NULL OR priority = ?)
            AND (? IS NULL OR mower_id = ?)
        ORDER BY id DESC
        LIMIT ?
    """
    params = (status, status, priority, priority, mower_id, mower_id, limit)

    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(q, params)
        return [dict(r) for r in cur.fetchall()]


def db_create_work_order(
    mower_id: str,
    title: str,
    priority: str = "MEDIUM",
    status: str = "OPEN",
    owner: Optional[str] = None
) -> dict:
    if not mower_id or not str(mower_id).strip():
        return {"ok": False, "error": "mower_id is required"}
    if not title or not str(title).strip():
        return {"ok": False, "error": "title is required"}
    if priority not in ALLOWED_WO_PRIORITY:
        return {"ok": False, "error": f"Invalid priority. Allowed: {sorted(ALLOWED_WO_PRIORITY)}"}
    if status not in ALLOWED_WO_STATUS:
        return {"ok": False, "error": f"Invalid status. Allowed: {sorted(ALLOWED_WO_STATUS)}"}

    # optional: mower existence check (kannst du rausnehmen, wenn du willst)
    if db_get_mower(mower_id) is None:
        return {"ok": False, "error": f"Mower not found: {mower_id}"}

    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO work_orders (mower_id, title, priority, status, owner, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (mower_id, title.strip(), priority, status, owner),
        )
        conn.commit()
        wo_id = cur.lastrowid

        cur.execute(
            "SELECT id, mower_id, title, priority, status, owner, created_at FROM work_orders WHERE id = ?",
            (wo_id,),
        )
        row = cur.fetchone()
        return {"ok": True, "work_order": dict(row) if row else {"id": wo_id}}


def db_update_work_order_status(work_order_id: int, status: str) -> dict:
    if status not in ALLOWED_WO_STATUS:
        return {"ok": False, "error": f"Invalid status. Allowed: {sorted(ALLOWED_WO_STATUS)}"}

    try:
        wo_id = int(work_order_id)
    except Exception:
        return {"ok": False, "error": "work_order_id must be an integer"}

    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE work_orders SET status = ? WHERE id = ?", (status, wo_id))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "Work order not found"}

        cur.execute(
            "SELECT id, mower_id, title, priority, status, owner, created_at FROM work_orders WHERE id = ?",
            (wo_id,),
        )
        row = cur.fetchone()
        return {"ok": True, "work_order": dict(row) if row else {"id": wo_id, "status": status}}


# ----------------- Startup -----------------

@app.on_event("startup")
def _startup():
    load_kb("kb")
    if not os.path.exists(DB_PATH):
        print(f"DB: {DB_PATH} nicht gefunden. Bitte db_init.py ausführen.")
    else:
        print(f"DB: {DB_PATH} gefunden.")


# ----------------- Session State (in-memory) -----------------

SESSION_LANG: Dict[str, str] = {}              # "de" / "en"
SESSION_LAST_REPLY: Dict[str, str] = {}        # last assistant reply text
SESSION_NAME_CORRECTED: Dict[str, bool] = {}   # name correction already done?


# ----------------- Language + Intent helpers -----------------

_GREETINGS = {
    "hi", "hii", "hello", "hey",
    "hallo", "guten tag", "guten morgen", "guten abend",
    "servus", "moin", "yo"
}

_OTHER_ASSISTANT_NAMES = {"chatgpt", "copilot", "gpt", "gpt-4", "gpt4", "gpt-4o", "openai"}


def normalize(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def is_greeting_only(text: str) -> bool:
    return normalize(text) in _GREETINGS


def is_language_only(text: str) -> bool:
    return normalize(text) in {"english", "englisch", "deutsch", "german", "de", "en"}


def explicit_lang_request(text: str) -> Optional[str]:
    t = normalize(text)
    en_triggers = [
        "english", "englisch", "in english", "speak english", "english please",
        "auf englisch", "in englisch", "können wir auf englisch", "kannst du auf englisch",
        "please answer in english", "answer in english",
    ]
    de_triggers = [
        "deutsch", "german", "in german", "speak german", "german please",
        "auf deutsch", "in deutsch", "können wir auf deutsch", "kannst du auf deutsch",
        "please answer in german", "answer in german",
    ]
    if any(x in t for x in en_triggers):
        return "en"
    if any(x in t for x in de_triggers):
        return "de"
    return None


def detect_lang(text: str) -> str:
    t = normalize(text)

    req = explicit_lang_request(t)
    if req:
        return req

    if t in {"english", "englisch", "en"}:
        return "en"
    if t in {"deutsch", "german", "de"}:
        return "de"

    if any(ch in t for ch in ["ä", "ö", "ü", "ß"]):
        return "de"

    tt = f" {t} "
    de_markers = [" wie ", " was ", " warum ", " bitte ", " kannst ", " können ", " ich ", " und ", " nicht ", " für "]
    en_markers = [" what ", " why ", " how ", " please ", " can ", " i ", " and ", " not ", " for ", " much ", " many "]

    score_de = sum(m in tt for m in de_markers)
    score_en = sum(m in tt for m in en_markers)

    if score_de == 0 and score_en == 0:
        return "en"
    return "en" if score_en > score_de else "de"


def wants_translation_to_en(text: str) -> bool:
    t = normalize(text)
    triggers = [
        "auf englisch zurück", "auf englisch bitte", "kannst du das auf englisch",
        "kannst du mir das auf englisch", "in english", "please answer in english",
        "translate to english", "return it in english",
    ]
    return any(x in t for x in triggers)


def wants_translation_to_de(text: str) -> bool:
    t = normalize(text)
    triggers = [
        "auf deutsch zurück", "auf deutsch bitte", "kannst du das auf deutsch",
        "kannst du mir das auf deutsch", "in german", "please answer in german",
        "translate to german", "return it in german",
    ]
    return any(x in t for x in triggers)


def mentions_other_bot_name(text: str) -> bool:
    t = normalize(text)
    return any(n in t for n in _OTHER_ASSISTANT_NAMES)


def translate_text(text: str, target_lang: str) -> str:
    target = "English" if target_lang == "en" else "German"
    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": f"Translate the text to {target}. Output only the translation."},
            {"role": "user", "content": text},
        ],
    )
    return resp.choices[0].message.content or ""


# ----------------- Tools (DB) for Tool-Calling -----------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_mowers",
            "description": "List mowers from the internal SQLite database. Optionally filter by status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Optional. One of: AVAILABLE, IN_SERVICE, MAINTENANCE, OUT_OF_ORDER"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_mower",
            "description": "Get details for a mower by id from the internal SQLite database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mower_id": {"type": "string", "description": "Mower id, e.g. GM-A-001"}
                },
                "required": ["mower_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_mower_status",
            "description": "Update a mower status in the internal SQLite database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mower_id": {"type": "string", "description": "Mower id, e.g. GM-A-001"},
                    "status": {"type": "string", "description": "New status: AVAILABLE, IN_SERVICE, MAINTENANCE, OUT_OF_ORDER"}
                },
                "required": ["mower_id", "status"]
            }
        }
    },

    # ---- Work Orders tools ----
    {
        "type": "function",
        "function": {
            "name": "list_work_orders",
            "description": "List work orders from the internal SQLite database. Optional filters: status, priority, mower_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Optional. One of: OPEN, IN_PROGRESS, DONE, CANCELLED"},
                    "priority": {"type": "string", "description": "Optional. One of: LOW, MEDIUM, HIGH, CRITICAL"},
                    "mower_id": {"type": "string", "description": "Optional. Mower id, e.g. GM-A-001"},
                    "limit": {"type": "integer", "description": "Optional. Max results (1..200). Default 50."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_work_order",
            "description": "Create a new work order for a mower.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mower_id": {"type": "string", "description": "Mower id, e.g. GM-A-001"},
                    "title": {"type": "string", "description": "Short title of the work order"},
                    "priority": {"type": "string", "description": "LOW, MEDIUM, HIGH, CRITICAL (default MEDIUM)"},
                    "status": {"type": "string", "description": "OPEN, IN_PROGRESS, DONE, CANCELLED (default OPEN)"},
                    "owner": {"type": "string", "description": "Optional owner / assignee"}
                },
                "required": ["mower_id", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_work_order_status",
            "description": "Update the status of an existing work order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "work_order_id": {"type": "integer", "description": "Work order id (integer)"},
                    "status": {"type": "string", "description": "OPEN, IN_PROGRESS, DONE, CANCELLED"}
                },
                "required": ["work_order_id", "status"]
            }
        }
    }
]


def run_tool(tool_name: str, args: dict) -> dict:
    try:
        # ---- Mowers ----
        if tool_name == "list_mowers":
            status = args.get("status")
            return {"mowers": db_list_mowers(status=status)}
        if tool_name == "get_mower":
            mower = db_get_mower(args["mower_id"])
            return {"mower": mower, "found": mower is not None}
        if tool_name == "update_mower_status":
            return db_update_mower_status(args["mower_id"], args["status"])

        # ---- Work Orders ----
        if tool_name == "list_work_orders":
            return {
                "work_orders": db_list_work_orders(
                    status=args.get("status"),
                    priority=args.get("priority"),
                    mower_id=args.get("mower_id"),
                    limit=args.get("limit", 50),
                )
            }
        if tool_name == "create_work_order":
            return db_create_work_order(
                mower_id=args.get("mower_id", ""),
                title=args.get("title", ""),
                priority=args.get("priority", "MEDIUM"),
                status=args.get("status", "OPEN"),
                owner=args.get("owner"),
            )
        if tool_name == "update_work_order_status":
            return db_update_work_order_status(args["work_order_id"], args["status"])

        return {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        return {"error": str(e)}


# ----------------- API -----------------

class ChatRequest(BaseModel):
    message: str
    use_rag: bool = False
    top_k: int = 4
    session_id: Optional[str] = None


@app.post("/chat")
def chat(req: ChatRequest):
    msg = req.message or ""
    sid = req.session_id or str(uuid.uuid4())

    # 0) Sprache: explizite Wünsche überschreiben Session; sonst Session behalten
    forced = explicit_lang_request(msg)
    if forced:
        lang = forced
        SESSION_LANG[sid] = forced
    elif sid in SESSION_LANG:
        lang = SESSION_LANG[sid]
    else:
        lang = detect_lang(msg)
        SESSION_LANG[sid] = lang

    # 1) User schreibt nur "english/deutsch" => Sprachumschaltung bestätigen
    if is_language_only(msg):
        SESSION_LANG[sid] = "en" if normalize(msg) in {"english", "englisch", "en"} else "de"
        lang = SESSION_LANG[sid]
        reply = (
            "Sure — I’ll reply in English from now on. How can I help?"
            if lang == "en"
            else "Klar — ich antworte ab jetzt auf Deutsch. Wie kann ich dir helfen?"
        )
        SESSION_LAST_REPLY[sid] = reply
        return {"reply": reply, "sources": [], "session_id": sid, "lang": lang}

    # 2) Übersetzung: letzte Bot-Antwort übersetzen (nur wenn wirklich „translate/auf … zurück“)
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
            return {"reply": reply, "sources": [], "session_id": sid, "lang": target_lang}

        translated = translate_text(last, target_lang)
        SESSION_LAST_REPLY[sid] = translated
        return {"reply": translated, "sources": [], "session_id": sid, "lang": target_lang}

    # 3) Reine Begrüßung => kurze Antwort in der aktuellen Session-Sprache
    if is_greeting_only(msg):
        reply = "Hello! How can I help you?" if lang == "en" else "Hallo! Wie kann ich dir helfen?"
        SESSION_LAST_REPLY[sid] = reply
        return {"reply": reply, "sources": [], "session_id": sid, "lang": lang}

    # -------- RAG Retrieval --------
    context_chunks = retrieve(msg, top_k=max(1, min(req.top_k, 8))) if req.use_rag else []
    context_text = ""
    sources = []
    if context_chunks:
        sources = [c.doc_id for c in context_chunks]
        context_text = "\n\n".join([f"[{i+1}] SOURCE: {c.doc_id}\n{c.text}" for i, c in enumerate(context_chunks)])

    # Name correction: nur 1x pro Session (wenn User GPT/ChatGPT/Copilot sagt)
    do_name_correction = False
    if mentions_other_bot_name(msg) and not SESSION_NAME_CORRECTED.get(sid, False):
        do_name_correction = True
        SESSION_NAME_CORRECTED[sid] = True

    # System prompt
    # Wichtig: Output IMMER nur in einer Sprache (keine Mischung).
    if lang == "en":
        system = (
            f"You are {BOT_NAME} (OrderBooking Bot). Reply in English ONLY.\n"
            "Never claim you are ChatGPT, GPT, Copilot, or any other assistant.\n"
            "Do NOT repeat your name in every reply.\n"
            "Use provided context as the primary source.\n"
            "If the answer is not in the context (and you cannot know), say you don't know.\n"
            "Do not invent facts. If details are not in the provided context or tool results, say you don’t have that information.\n"
            "Do not mix languages. If context is in another language, translate it internally but keep the answer in English.\n"
            "You may call tools to query/update the internal database if needed.\n"
            "When you use tool results, explain them clearly in English.\n"
        )
        if do_name_correction:
            system += "Start this reply with exactly: \"I’m OB Bot.\" Then continue normally. (Only this time.)\n"
    else:
        system = (
            f"Du bist {BOT_NAME} (OrderBooking Bot). Antworte NUR auf Deutsch.\n"
            "Behaupte niemals, dass du ChatGPT, GPT, Copilot oder ein anderer Assistent bist.\n"
            "Nenne deinen Namen nicht in jeder Antwort.\n"
            "Wenn Kontext bereitgestellt wird, nutze ihn als Hauptgrundlage.\n"
            "Wenn die Antwort nicht im Kontext steht (und du es nicht wissen kannst), sage ehrlich, dass du es nicht weißt.\n"
            "Erfinde keine Fakten. Wenn Details nicht im Kontext oder Tool-Ergebnis stehen, sage klar, dass du dazu keine Informationen hast.\n"
            "Mische keine Sprachen. Wenn Kontext auf Englisch ist, nutze ihn, aber antworte trotzdem komplett auf Deutsch.\n"
            "Du darfst Tools nutzen, um die interne Datenbank abzufragen/zu aktualisieren, wenn nötig.\n"
            "Wenn du Tool-Ergebnisse nutzt, erkläre sie verständlich auf Deutsch.\n"
        )
        if do_name_correction:
            system += "Beginne diese Antwort mit genau: \"Ich bin OB Bot.\" Dann normal weitermachen. (Nur dieses Mal.)\n"

    messages: List[dict] = [{"role": "system", "content": system}]
    if context_text:
        messages.append({"role": "system", "content": f"Kontext:\n{context_text}"})
    messages.append({"role": "user", "content": msg})

    # -------- Model call + Tool-calling loop --------
    resp = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )

    max_steps = 5
    steps = 0

    while steps < max_steps:
        steps += 1
        assistant_msg = resp.choices[0].message
        tool_calls = getattr(assistant_msg, "tool_calls", None)

        # No tools requested => final answer
        if not tool_calls:
            reply = assistant_msg.content or ""
            SESSION_LAST_REPLY[sid] = reply
            return {"reply": reply, "sources": sources, "session_id": sid, "lang": lang}

        # Append assistant tool-call message
        messages.append({
            "role": "assistant",
            "content": assistant_msg.content or "",
            "tool_calls": [tc.model_dump() for tc in tool_calls],
        })

        # Execute tools
        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except Exception:
                fn_args = {}

            result = run_tool(fn_name, fn_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

        # Ask model again with tool results
        resp = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

    # If tool loop doesn't converge
    reply = (
        "Tool-calling loop did not finish. Please try again with a simpler request."
        if lang == "en"
        else "Tool-Loop hat nicht abgeschlossen. Bitte stelle die Anfrage einfacher."
    )
    SESSION_LAST_REPLY[sid] = reply
    return {"reply": reply, "sources": sources, "session_id": sid, "lang": lang}


@app.post("/reload_kb")
def reload_kb():
    load_kb("kb")
    return {"ok": True, "chunks": len(CHUNKS)}


# ----------------- Optional: DB test endpoints (Swagger) -----------------

@app.get("/db/mowers")
def api_list_mowers(status: Optional[str] = None):
    try:
        return {"mowers": db_list_mowers(status=status)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/db/mowers/{mower_id}")
def api_get_mower(mower_id: str):
    mower = db_get_mower(mower_id)
    if not mower:
        raise HTTPException(status_code=404, detail="Mower not found")
    return mower


class UpdateStatusRequest(BaseModel):
    status: str


@app.post("/db/mowers/{mower_id}/status")
def api_update_status(mower_id: str, req: UpdateStatusRequest):
    result = db_update_mower_status(mower_id, req.status)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
    return result


# Optional work order endpoints (praktisch zum Testen in Swagger)
@app.get("/db/work_orders")
def api_list_work_orders(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    mower_id: Optional[str] = None,
    limit: int = 50,
):
    try:
        return {"work_orders": db_list_work_orders(status=status, priority=priority, mower_id=mower_id, limit=limit)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class CreateWorkOrderRequest(BaseModel):
    mower_id: str
    title: str
    priority: Optional[str] = "MEDIUM"
    status: Optional[str] = "OPEN"
    owner: Optional[str] = None


@app.post("/db/work_orders")
def api_create_work_order(req: CreateWorkOrderRequest):
    result = db_create_work_order(
        mower_id=req.mower_id,
        title=req.title,
        priority=req.priority or "MEDIUM",
        status=req.status or "OPEN",
        owner=req.owner,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
    return result


class UpdateWorkOrderStatusRequest(BaseModel):
    status: str


@app.post("/db/work_orders/{work_order_id}/status")
def api_update_work_order_status(work_order_id: int, req: UpdateWorkOrderStatusRequest):
    result = db_update_work_order_status(work_order_id, req.status)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
    return result
