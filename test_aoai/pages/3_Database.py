import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = "greenmow.db"


# ----------------------------
# DB helpers
# ----------------------------
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def read_df(query: str, params=()):
    with db_connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


# ----------------------------
# UI
# ----------------------------
st.title("🗄️ Database")
st.caption("Full view of the SQLite database tables: mowers + work_orders.")

# Quick stats (optional)
col1, col2 = st.columns(2)
with col1:
    try:
        cnt_mowers = read_df("SELECT COUNT(*) AS c FROM mowers")["c"].iloc[0]
        st.metric("Mowers", int(cnt_mowers))
    except Exception:
        st.metric("Mowers", "—")

with col2:
    try:
        cnt_wos = read_df("SELECT COUNT(*) AS c FROM work_orders")["c"].iloc[0]
        st.metric("Work Orders", int(cnt_wos))
    except Exception:
        st.metric("Work Orders", "—")

tab1, tab2 = st.tabs(["Mowers", "Work Orders"])


# ----------------------------
# TAB 1: MOWERS
# ----------------------------
with tab1:
    st.subheader("Mowers")

    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        f_status = st.selectbox(
            "Status",
            ["(all)", "AVAILABLE", "IN_SERVICE", "MAINTENANCE", "OUT_OF_ORDER"],
            index=0
        )
    with c2:
        f_site = st.text_input("Site contains", value="")
    with c3:
        f_model = st.text_input("Model contains", value="")

    q = """
        SELECT id, model, site, status, last_service_date
        FROM mowers
        WHERE 1=1
    """
    params = []
    if f_status != "(all)":
        q += " AND status = ?"
        params.append(f_status)
    if f_site.strip():
        q += " AND site LIKE '%' || ? || '%'"
        params.append(f_site.strip())
    if f_model.strip():
        q += " AND model LIKE '%' || ? || '%'"
        params.append(f_model.strip())
    q += " ORDER BY id"

    df = read_df(q, params)

    if df.empty:
        st.info("No mowers found (check filters).")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("### Mower details")
        selected_id = st.selectbox("Select mower", df["id"].tolist(), index=0)
        row = df[df["id"] == selected_id].iloc[0]

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("ID", row["id"])
        d2.metric("Model", row["model"])
        d3.metric("Status", row["status"])
        d4.metric("Site", row["site"])
        st.write(f"**Last service date:** {row['last_service_date']}")


# ----------------------------
# TAB 2: WORK ORDERS
# ----------------------------
with tab2:
    st.subheader("Work Orders")

    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        wo_status = st.selectbox(
            "Status",
            ["(all)", "OPEN", "IN_PROGRESS", "DONE", "CANCELLED"],
            index=0
        )
    with c2:
        wo_priority = st.selectbox(
            "Priority",
            ["(all)", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
            index=0
        )
    with c3:
        wo_mower = st.text_input("Mower ID equals (optional)", value="", placeholder="e.g. GM-A-001")

    q = """
        SELECT id, mower_id, title, priority, status, owner, created_at
        FROM work_orders
        WHERE 1=1
    """
    params = []
    if wo_status != "(all)":
        q += " AND status = ?"
        params.append(wo_status)
    if wo_priority != "(all)":
        q += " AND priority = ?"
        params.append(wo_priority)
    if wo_mower.strip():
        q += " AND mower_id = ?"
        params.append(wo_mower.strip())

    q += " ORDER BY id DESC"

    df = read_df(q, params)

    if df.empty:
        st.info("No work orders found (check filters).")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("### Work order details")
        selected_wo = st.selectbox("Select work order", df["id"].tolist(), index=0)
        row = df[df["id"] == selected_wo].iloc[0]

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("WO ID", row["id"])
        d2.metric("Mower ID", row["mower_id"])
        d3.metric("Status", row["status"])
        d4.metric("Priority", row["priority"])

        st.write(f"**Title:** {row['title']}")
        st.write(f"**Owner:** {row['owner'] if row['owner'] else '—'}")
        st.write(f"**Created at:** {row['created_at']}")
