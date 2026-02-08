import json
import re
import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"


# ----------------------------
# Helpers
# ----------------------------
if "ui_lang" not in st.session_state:
    st.session_state.ui_lang = "de"

def t(de: str, en: str) -> str:
    return en if st.session_state.ui_lang == "en" else de

def extract_json(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1].strip()
    return text.strip()

def safe_json_loads(s: str):
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # remove trailing commas before } or ]
        s2 = re.sub(r",(\s*[}\]])", r"\1", s)
        return json.loads(s2)

def build_requirement_from_refined(spec: dict, lang: str) -> str:
    """
    Convert refined spec JSON into a compact text input for testcase generation.
    Keeps language consistent with lang.
    """
    if not spec:
        return ""

    title = spec.get("title", "").strip()
    desc = spec.get("short_description", "").strip()
    user_story = spec.get("user_story", "").strip()
    rules = spec.get("business_rules", []) or []
    edges = spec.get("edge_cases", []) or []
    ac = spec.get("acceptance_criteria", []) or []

    # Format AC
    ac_lines = []
    for i, item in enumerate(ac, start=1):
        if not isinstance(item, dict):
            continue
        g = (item.get("given") or "").strip()
        w = (item.get("when") or "").strip()
        th = (item.get("then") or "").strip()
        if not (g or w or th):
            continue
        if lang == "en":
            ac_lines.append(f"- Given {g}\n  When {w}\n  Then {th}")
        else:
            ac_lines.append(f"- Gegeben {g}\n  Wenn {w}\n  Dann {th}")

    if lang == "en":
        out = []
        if title: out.append(f"Title: {title}")
        if user_story: out.append(f"User Story: {user_story}")
        if desc: out.append(f"Description: {desc}")
        if ac_lines: out.append("Acceptance Criteria:\n" + "\n".join(ac_lines))
        if rules: out.append("Business Rules:\n- " + "\n- ".join(map(str, rules)))
        if edges: out.append("Edge Cases:\n- " + "\n- ".join(map(str, edges)))
        return "\n\n".join(out).strip()
    else:
        out = []
        if title: out.append(f"Titel: {title}")
        if user_story: out.append(f"User Story: {user_story}")
        if desc: out.append(f"Beschreibung: {desc}")
        if ac_lines: out.append("Akzeptanzkriterien:\n" + "\n".join(ac_lines))
        if rules: out.append("Business Rules:\n- " + "\n- ".join(map(str, rules)))
        if edges: out.append("Edge Cases:\n- " + "\n- ".join(map(str, edges)))
        return "\n\n".join(out).strip()


# ----------------------------
# UI
# ----------------------------
st.title(t("Requirements to Testcases", "Requirements to Testcases"))
st.caption(t(
    "Füge ein Requirement ein oder nutze das verfeinerte Requirement aus Requirement Refinement.",
    "Paste a requirement or use the refined requirement from Requirement Refinement."
))

# Quick connect button to refined requirement
col1, col2 = st.columns([1, 2], gap="small")

with col1:
    use_refined = st.button(t("Refined Requirement übernehmen", "Use refined requirement"))

with col2:
    st.info(t(
        "Tipp: Erst in 'Requirement Refinement' verfeinern, dann hier Testcases generieren.",
        "Tip: Refine in 'Requirement Refinement' first, then generate test cases here."
    ))

# Text area
if "tc_input" not in st.session_state:
    st.session_state.tc_input = ""

if use_refined:
    spec = st.session_state.get("rr_spec", {})
    # Use current UI language to keep consistent output
    lang = st.session_state.ui_lang
    merged = build_requirement_from_refined(spec, lang)
    if not merged.strip():
        st.warning(t(
            "Kein verfeinertes Requirement gefunden. Bitte zuerst Requirement Refinement ausführen.",
            "No refined requirement found. Please run Requirement Refinement first."
        ))
    else:
        st.session_state.tc_input = merged

req_text = st.text_area(
    t("Requirement", "Requirement"),
    height=220,
    value=st.session_state.tc_input,
    placeholder=t(
        "z.B. Ein Benutzer kann sich mit E-Mail + Passwort anmelden. Bei 5 Fehlversuchen wird der Account 15 Minuten gesperrt.",
        "e.g. A user can log in with email + password. After 5 failed attempts the account is locked for 15 minutes."
    )
)

# Optional knobs
cA, cB, cC = st.columns(3)
with cA:
    n_cases = st.slider(t("Anzahl Testcases", "Number of test cases"), 3, 12, 5, 1)
with cB:
    strict = st.checkbox(t("Strikt nur JSON", "Strict JSON only"), value=True)
with cC:
    temperature = st.slider("temperature", 0.0, 1.0, 0.2, 0.05)

# Generate
btn = st.button(t("Generate Test Cases", "Generate Test Cases"), type="primary", disabled=not req_text.strip())

if btn:
    use_rag = st.session_state.get("use_rag", True)
    top_k = st.session_state.get("top_k", 4)
    sid = st.session_state.get("sid")

    if not sid:
        st.error(t(
            "sid fehlt in st.session_state. Stelle sicher, dass du in deiner Hauptdatei (chatbot.py) die Session-ID setzt.",
            "sid missing in st.session_state. Make sure your main file sets the session id (chatbot.py)."
        ))
        st.stop()

    lang = st.session_state.ui_lang
    output_language = "English" if lang == "en" else "Deutsch"

    if lang == "en":
        system = f"""
You are a QA engineer. Convert the input into {n_cases} test cases.
Write all human-readable fields in English only. Do NOT mix languages.
Return ONLY valid JSON with this schema (single JSON object):
{{
  "test_cases": [
    {{
      "id": "TC-001",
      "title": "...",
      "preconditions": ["..."],
      "steps": ["..."],
      "expected_result": "...",
      "type": "positive|negative|edge",
      "priority": "high|medium|low"
    }}
  ]
}}
""".strip()
    else:
        system = f"""
Du bist QA Engineer. Erzeuge aus dem Input {n_cases} Testfälle.
Schreibe alle menschenlesbaren Felder NUR auf Deutsch. Keine Mischsprache.
Gib NUR gültiges JSON zurück (ein einziges JSON-Objekt) mit diesem Schema:
{{
  "test_cases": [
    {{
      "id": "TC-001",
      "title": "...",
      "preconditions": ["..."],
      "steps": ["..."],
      "expected_result": "...",
      "type": "positive|negative|edge",
      "priority": "high|medium|low"
    }}
  ]
}}
""".strip()

    # One prompt to backend (your /chat already handles system prompts)
    prompt = f"{system}\n\nINPUT:\n{req_text}"

    with st.spinner(t("Erzeuge Testcases...", "Generating test cases...")):
        r = requests.post(
            f"{API_URL}/chat",
            json={
                "message": prompt,
                "use_rag": use_rag,
                "top_k": top_k,
                "session_id": sid,
            },
            timeout=90,
        )
        r.raise_for_status()
        data = r.json()

    # update ui_lang if backend detected it
    if data.get("lang") in ("de", "en"):
        st.session_state.ui_lang = data["lang"]

    raw = data.get("reply", "") or ""
    json_text = extract_json(raw)

    try:
        parsed = safe_json_loads(json_text)
        tcs = parsed.get("test_cases", [])

        if not isinstance(tcs, list):
            raise ValueError('"test_cases" is not a list')

        st.session_state.last_testcases = parsed
        st.session_state.last_testcases_sources = data.get("sources", [])

        st.success(t(f"Erzeugt: {len(tcs)} Testcases", f"Generated: {len(tcs)} test cases"))
        st.json(parsed)

        st.markdown("### " + t("Tabellenansicht", "Table view"))
        st.dataframe(
            [
                {
                    "id": tc.get("id"),
                    "title": tc.get("title"),
                    "type": tc.get("type"),
                    "priority": tc.get("priority"),
                    "expected_result": tc.get("expected_result"),
                }
                for tc in tcs
            ],
            use_container_width=True,
            hide_index=True,
        )

        # show sources if any
        sources = st.session_state.get("last_testcases_sources", [])
        if sources:
            with st.expander(t("Quellen", "Sources")):
                for s in sources:
                    st.write(s)

    except Exception as e:
        st.error(t(
            "Konnte JSON nicht parsen. Debug:",
            "Could not parse JSON. Debug:"
        ))
        st.write("**Extracted JSON candidate:**")
        st.code(json_text)
        st.write("**Raw model output:**")
        st.code(raw)
        st.exception(e)
