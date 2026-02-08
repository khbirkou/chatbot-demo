import os
import pandas as pd
import sqlite3
import streamlit as st

DB_PATH = "greenmow.db"

if not os.path.exists(DB_PATH):
    st.error(f"DB file not found: {DB_PATH}")
    st.stop()

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def read_df(query: str, params=()):
    with db_connect() as conn:
        return pd.read_sql_query(query, conn, params=params)

def exec_sql(query: str, params=()):
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.lastrowid

st.title("Test Data Request")
st.caption("Create and track test data requests (work orders).")

tab1, tab2 = st.tabs(["Create Request", "Browse Requests"])

# ---- TAB 1: Create ----
with tab1:
    st.subheader("Create a Work Order")

    mower_id = st.text_input("Mower ID", placeholder="e.g. GM-A-001")
    title = st.text_input("Title", placeholder="e.g. Replace blade / Schedule maintenance")
    col1, col2 = st.columns(2)
    with col1:
        priority = st.selectbox("Priority", ["LOW", "MEDIUM", "HIGH", "CRITICAL"], index=1)
    with col2:
        status = st.selectbox("Status", ["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"], index=0)

    owner = st.text_input("Owner (optional)", placeholder="e.g. Max / Team QA")

    if st.button("Create Work Order", type="primary"):
        if not mower_id.strip() or not title.strip():
            st.warning("Please fill Mower ID and Title.")
        else:
            new_id = exec_sql(
                """
                INSERT INTO work_orders (mower_id, title, priority, status, owner, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (mower_id.strip(), title.strip(), priority, status, owner.strip() or None),
            )
            st.success(f"Work order created (id={new_id}) ✅")

# ---- TAB 2: Browse ----
with tab2:
    st.subheader("Work Orders")

    c1, c2 = st.columns(2)
    with c1:
        f_status = st.selectbox("Filter Status", ["(all)", "OPEN", "IN_PROGRESS", "DONE", "CANCELLED"], index=0)
    with c2:
        f_mower = st.text_input("Filter Mower ID", value="", placeholder="e.g. GM-A-001")

    q = """
        SELECT id, mower_id, title, priority, status, owner, created_at
        FROM work_orders
        WHERE 1=1
    """
    params = []
    if f_status != "(all)":
        q += " AND status = ?"
        params.append(f_status)
    if f_mower.strip():
        q += " AND mower_id = ?"
        params.append(f_mower.strip())
    q += " ORDER BY id DESC"

    df = read_df(q, params)

    if df.empty:
        st.info("No work orders found.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("### Update Status")
        selected_id = st.selectbox("Select Work Order ID", df["id"].tolist(), index=0)
        new_status = st.selectbox("New Status", ["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"], index=1)

        if st.button("Update Status"):
            exec_sql("UPDATE work_orders SET status = ? WHERE id = ?", (new_status, int(selected_id)))
            st.success("Status updated ✅")
            st.rerun()
