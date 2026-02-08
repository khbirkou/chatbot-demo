import json
import re
import uuid
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
    """Try to extract JSON even if model wraps it in fences or adds text."""
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

def ensure_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [str(x)]

def new_req_id() -> str:
    return f"REQ-{str(uuid.uuid4())[:8].upper()}"


# ----------------------------
# Session state for this page
# ----------------------------
if "rr_original" not in st.session_state:
    st.session_state.rr_original = ""

if "rr_spec" not in st.session_state:
    # structure we edit in UI
    st.session_state.rr_spec = {
        "requirement_id": new_req_id(),
        "type": "Functional",          # Functional / Non-Functional
        "category_code": "MAINT",
        "category_name": "Maintenance & Diagnostics",
        "applicable_models": [],       # optional list
        "title": "",
        "short_description": "",
        "user_story": "",
        "acceptance_criteria": [],     # list of {given, when, then}
        "business_rules": [],
        "edge_cases": [],
        "open_questions": [],
    }

if "rr_sources" not in st.session_state:
    st.session_state.rr_sources = []


# ----------------------------
# UI Layout (like screenshot)
# ----------------------------
st.title(t("Requirement Refinement", "Requirement Refinement"))
st.caption(t(
    "Transformiere natürliche Sprache in strukturierte, testbare Anforderungen (DE/EN).",
    "Transform natural language into structured, testable requirements (DE/EN)."
))

left, main = st.columns([0.28, 0.72], gap="large")

with left:
    st.markdown("### " + t("Optionen", "Options"))

    mode = st.radio(
        t("Select Option", "Select Option"),
        [
            t("Neues Requirement verfeinern", "Refine New Requirement"),
            t("Bestehende Requirements ansehen", "Browse Existing Requirements"),
            t("Bestehendes Requirement bearbeiten", "Edit Existing Requirement"),
        ],
        index=0,
        label_visibility="visible",
    )

    st.divider()

    # You can later replace with real DB list
    st.caption(t("Speicher (Session)", "Storage (Session)"))
    st.write(t(
        "Aktuell wird in `st.session_state` gespeichert. DB-Anbindung kann später folgen.",
        "Currently stored in `st.session_state`. DB integration can be added later."
    ))


with main:
    # ---- Mode A: Refine New Requirement ----
    if mode == t("Neues Requirement verfeinern", "Refine New Requirement"):
        st.subheader(t("Requirement eingeben", "Enter requirement"))

        default_text = t(
            "Ein Techniker möchte den Status eines Mähers ändern (AVAILABLE → IN_SERVICE).",
            "A technician wants to change a mower status (AVAILABLE → IN_SERVICE)."
        )

        req_text = st.text_area(
            t("Beschreibe dein Requirement", "Describe your requirement"),
            value=st.session_state.rr_original or default_text,
            height=150,
        )

        colA, colB = st.columns([1, 1])
        with colA:
            btn = st.button(t("Refine Requirement", "Refine Requirement"), type="primary")
        with colB:
            if st.button(t("Reset", "Reset")):
                st.session_state.rr_original = ""
                st.session_state.rr_sources = []
                st.session_state.rr_spec["requirement_id"] = new_req_id()
                st.session_state.rr_spec.update({
                    "title": "",
                    "short_description": "",
                    "user_story": "",
                    "acceptance_criteria": [],
                    "business_rules": [],
                    "edge_cases": [],
                    "open_questions": [],
                })
                st.rerun()

        if btn:
            if not req_text.strip():
                st.warning(t("Bitte zuerst ein Requirement eingeben.", "Please enter a requirement first."))
                st.stop()

            st.session_state.rr_original = req_text

            # RAG settings from global sidebar
            use_rag = st.session_state.get("use_rag", True)
            top_k = st.session_state.get("top_k", 4)
            sid = st.session_state.get("sid")  # set in main file

            # JSON schema prompt (DE/EN)
            if st.session_state.ui_lang == "en":
                system = """
You are OB Bot. Convert a requirement into a structured specification.
Return ONLY valid JSON (no markdown fences, no extra text).

Schema:
{
  "requirement_id": "REQ-....",
  "type": "Functional|Non-Functional",
  "category_code": "...",
  "category_name": "...",
  "applicable_models": ["..."],
  "title": "...",
  "short_description": "...",
  "user_story": "As a ... I want ... so that ...",
  "acceptance_criteria": [{"given":"...","when":"...","then":"..."}],
  "business_rules": ["..."],
  "edge_cases": ["..."],
  "open_questions": ["..."]
}

Rules:
- Output must be entirely in English.
- Keep acceptance criteria concise and testable.
""".strip()
            else:
                system = """
Du bist OB Bot. Wandle eine Anforderung in eine strukturierte Spezifikation um.
Gib NUR gültiges JSON zurück (keine Markdown-Fences, kein Zusatztext).

Schema:
{
  "requirement_id": "REQ-....",
  "type": "Functional|Non-Functional",
  "category_code": "...",
  "category_name": "...",
  "applicable_models": ["..."],
  "title": "...",
  "short_description": "...",
  "user_story": "Als ... möchte ich ... damit ...",
  "acceptance_criteria": [{"given":"...","when":"...","then":"..."}],
  "business_rules": ["..."],
  "edge_cases": ["..."],
  "open_questions": ["..."]
}

Regeln:
- Ausgabe vollständig auf Deutsch.
- Akzeptanzkriterien kurz, testbar, eindeutig.
""".strip()

            prompt = f"{system}\n\nRequirement:\n{req_text}"

            with st.spinner(t("Verfeinere Requirement...", "Refining requirement...")):
                r = requests.post(
                    f"{API_URL}/chat",
                    json={
                        "message": prompt,
                        "use_rag": use_rag,
                        "top_k": top_k,
                        "session_id": sid,
                    },
                    timeout=60,
                )
                r.raise_for_status()
                data = r.json()

            # update ui language from backend
            if data.get("lang") in ("de", "en"):
                st.session_state.ui_lang = data["lang"]

            st.session_state.rr_sources = data.get("sources", [])
            raw = data.get("reply", "") or ""
            json_text = extract_json(raw)

            try:
                spec = json.loads(json_text)

                # normalize fields & keep defaults if missing
                current = st.session_state.rr_spec
                current["requirement_id"] = spec.get("requirement_id") or current["requirement_id"]
                current["type"] = spec.get("type") or current["type"]
                current["category_code"] = spec.get("category_code") or current["category_code"]
                current["category_name"] = spec.get("category_name") or current["category_name"]
                current["applicable_models"] = ensure_list(spec.get("applicable_models"))

                current["title"] = spec.get("title", "")
                current["short_description"] = spec.get("short_description", "")
                current["user_story"] = spec.get("user_story", "")

                ac = spec.get("acceptance_criteria", [])
                if not isinstance(ac, list):
                    ac = []
                # keep only dicts with given/when/then
                cleaned_ac = []
                for item in ac:
                    if isinstance(item, dict):
                        cleaned_ac.append({
                            "given": str(item.get("given", "")).strip(),
                            "when": str(item.get("when", "")).strip(),
                            "then": str(item.get("then", "")).strip(),
                        })
                current["acceptance_criteria"] = cleaned_ac

                current["business_rules"] = ensure_list(spec.get("business_rules"))
                current["edge_cases"] = ensure_list(spec.get("edge_cases"))
                current["open_questions"] = ensure_list(spec.get("open_questions"))

                st.success(t("Requirement refined successfully!", "Requirement refined successfully!"))

            except Exception:
                st.error(t(
                    "Modell hat kein gültiges JSON geliefert. Roh-Ausgabe:",
                    "Model did not return valid JSON. Raw output:"
                ))
                st.code(raw)

        # ---- After refine: show editor (like screenshot) ----
        st.divider()
        st.subheader(t("Refined Requirement", "Refined Requirement"))

        with st.expander(t("Original Input anzeigen", "View Original Input"), expanded=False):
            st.write(st.session_state.rr_original or t("— (leer) —", "— (empty) —"))

        spec = st.session_state.rr_spec

        with st.container(border=True):
            st.markdown("#### " + t("Review & Edit Refined Requirement", "Review & Edit Refined Requirement"))

            c1, c2 = st.columns([1, 1], gap="large")

            with c1:
                spec["requirement_id"] = st.text_input(t("Requirement ID", "Requirement ID"), value=spec["requirement_id"])
                spec["category_code"] = st.text_input(t("Category Code", "Category Code"), value=spec["category_code"])
                spec["category_name"] = st.text_input(t("Category Name", "Category Name"), value=spec["category_name"])

            with c2:
                # checkbox style like screenshot
                type_is_func = st.checkbox(t("Functional Requirement", "Functional Requirement"), value=(spec["type"] == "Functional"))
                spec["type"] = "Functional" if type_is_func else "Non-Functional"

                models_csv = st.text_input(
                    t("Applicable Models (comma-separated)", "Applicable Models (comma-separated)"),
                    value=", ".join(spec.get("applicable_models", [])),
                    placeholder="e.g. GM-T3, GM-T5",
                )
                spec["applicable_models"] = [x.strip() for x in models_csv.split(",") if x.strip()]

            spec["title"] = st.text_input(t("Title", "Title"), value=spec["title"])
            spec["user_story"] = st.text_area(t("User Story", "User Story"), value=spec["user_story"], height=90)
            spec["short_description"] = st.text_area(t("Description", "Description"), value=spec["short_description"], height=110)

            st.markdown("##### " + t("Acceptance Criteria (Given/When/Then)", "Acceptance Criteria (Given/When/Then)"))

            # render acceptance criteria rows editable
            ac_list = spec.get("acceptance_criteria", [])
            if not ac_list:
                st.info(t("Noch keine Akzeptanzkriterien. Füge eins hinzu.", "No acceptance criteria yet. Add one."))

            for i, ac in enumerate(ac_list):
                with st.container(border=True):
                    st.markdown(f"**AC-{i+1:02d}**")
                    ac["given"] = st.text_input(t("Gegeben / Given", "Given"), value=ac.get("given", ""), key=f"ac_given_{i}")
                    ac["when"]  = st.text_input(t("Wenn / When", "When"), value=ac.get("when", ""), key=f"ac_when_{i}")
                    ac["then"]  = st.text_input(t("Dann / Then", "Then"), value=ac.get("then", ""), key=f"ac_then_{i}")

                    col_del, _ = st.columns([1, 5])
                    if col_del.button(t("Löschen", "Delete"), key=f"ac_del_{i}"):
                        spec["acceptance_criteria"].pop(i)
                        st.rerun()

            col_add, col_save = st.columns([1, 1])
            with col_add:
                if st.button(t("Akzeptanzkriterium hinzufügen", "Add Acceptance Criterion")):
                    spec["acceptance_criteria"].append({"given": "", "when": "", "then": ""})
                    st.rerun()

            with col_save:
                if st.button(t("Speichern (Session)", "Save (Session)"), type="primary"):
                    st.session_state.rr_spec = spec
                    st.success(t("Gespeichert.", "Saved."))

        # Show sources if RAG used
        if st.session_state.rr_sources:
            with st.expander(t("Quellen", "Sources")):
                for s in st.session_state.rr_sources:
                    st.write(s)


    # ---- Mode B/C placeholders (optional) ----
    else:
        st.info(t(
            "Dieses Feature ist noch ein Platzhalter. (Später: DB-Anbindung)",
            "This is a placeholder for now. (Later: DB integration)"
        ))
