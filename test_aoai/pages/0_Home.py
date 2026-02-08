import sqlite3
import streamlit as st

st.set_page_config(page_title="Home", page_icon="🏠", layout="wide")

DB_PATH = "greenmow.db"

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_models():
    with db_connect() as conn:
        cur = conn.cursor()
        # distinct Modelle + Anzahl
        cur.execute("""
            SELECT model, COUNT(*) AS cnt
            FROM mowers
            GROUP BY model
            ORDER BY cnt DESC, model ASC
        """)
        return cur.fetchall()

st.title("AI Test Data Management Demo")
st.caption("Requirements → Testcases → Test Data + RAG + DB Tool Calling")

st.divider()

with st.container(border=True):
    st.subheader("About Evergreen Mowing / GreenMow")
    st.write(
        "Diese Anwendung zeigt, wie GenAI in den Testing-Lifecycle integriert werden kann "
        "(Requirements → Testcases → Test Data Requests) und wie RAG + DB Tool Calling genutzt werden."
    )

    st.markdown("**Our Products (from DB)**")

    try:
        rows = get_models()
        if not rows:
            st.info("Keine Mower-Daten gefunden. (Tabelle `mowers` ist leer?)")
        else:
            # schön als Bullet-List
            for r in rows:
                st.markdown(f"- **{r['model']}** — {r['cnt']} ")
    except Exception as e:
        st.warning(f"DB nicht lesbar: {e}")

st.divider()

with st.container(border=True):
    st.subheader("Demo Purpose")
    st.write(
        "Diese Demo zeigt, wie **Generative AI** in den **Requirements-to-Testing** Prozess eingebunden werden kann: "
        "von unstrukturierten Anforderungen über strukturierte Spezifikationen bis hin zu Testfällen und Testdaten."
    )

st.divider()

with st.container(border=True):
    st.subheader("GenAI Capabilities")
    st.markdown(
        """
✅ **Chatbot (RAG + DB Tool Calling)**  
- Fragen zu Dokumenten (RAG)  
- Datenbankabfragen / Statusänderungen via Tool-Calling  

✅ **Requirement Refinement** 
- Natural Language → strukturierte Requirements (Titel, User Story, AC, Edge Cases)
 
✅ **Requirements → Testcases** 
- Requirement-Text → Testfälle (positive/negative/edge) als JSON + Tabelle
 
✅ **Test Data Requests (work_orders)**  
- Work Orders/Test-Data-Requests erstellen, browsen und Status pflegen

✅ **Database View**
- Mower-Daten anzeigen/filtern und Status prüfen
        """.strip()
    )
