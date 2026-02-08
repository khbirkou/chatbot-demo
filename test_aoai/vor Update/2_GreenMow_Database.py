import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = "greenmow.db"

st.set_page_config(page_title="Database", layout="wide")


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def read_df(query: str, params=()):
    with db_connect() as conn:
        return pd.read_sql_query(query, conn, params=params)


def list_tables() -> set[str]:
    df = read_df("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    return set(df["name"].tolist()) if not df.empty else set()


TABLES = list_tables()


st.title("Comprehensive Database View")
st.caption("This page displays both the lawn mower model database and physical inventory with filtering capabilities.")

tab1, tab2 = st.tabs(["Available Models", "Physical Inventory"])

# ------------------ TAB 1: MODELS ------------------
with tab1:
    st.subheader("Lawn Mower Models")

    has_models = "mower_models" in TABLES
    has_specs = "model_specs" in TABLES

    # ---- Filters ----
    colA, colB, colC = st.columns([2, 2, 2])
    with colA:
        brand = st.text_input("Brand contains", value="")
    with colB:
        product_line = st.text_input("Product Line contains", value="")
    with colC:
        model_name = st.text_input("Model Name contains", value="")

    if has_models:
        # ✅ Use real model table
        models = read_df(
            """
            SELECT
                id,
                brand,
                product_line,
                model_name,
                tagline,
                description
            FROM mower_models
            WHERE
                (? = '' OR brand LIKE '%' || ? || '%')
                AND (? = '' OR product_line LIKE '%' || ? || '%')
                AND (? = '' OR model_name LIKE '%' || ? || '%')
            ORDER BY id
            """,
            (brand, brand, product_line, product_line, model_name, model_name),
        )

        if models.empty:
            st.info("No models found. Check your filters.")
        else:
            st.dataframe(
                models[["id", "brand", "product_line", "model_name", "tagline"]],
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("### Model Details")

            selected_id = st.selectbox(
                "Select a Model for Detailed Information",
                models["id"].tolist(),
                index=0
            )

            selected = models[models["id"] == selected_id].iloc[0]

            col1, col2 = st.columns([2, 3])
            with col1:
                st.markdown(f"#### {selected['brand']} {selected['model_name']}")
                if pd.notna(selected.get("tagline")) and str(selected.get("tagline")).strip():
                    st.caption(selected["tagline"])
                st.write(f"**Model ID:** {selected['id']}")
                st.write(f"**Product Line:** {selected['product_line']}")
            with col2:
                st.markdown("#### Description")
                st.write(selected.get("description") or "—")

            st.markdown("### Detailed Specifications")

            if has_specs:
                specs = read_df(
                    """
                    SELECT component, details, testing_focus
                    FROM model_specs
                    WHERE model_id = ?
                    ORDER BY component
                    """,
                    (selected_id,),
                )

                if specs.empty:
                    st.info("No specifications found for this model.")
                else:
                    st.dataframe(specs, use_container_width=True, hide_index=True)
            else:
                st.info("Table 'model_specs' not found in DB. Add it to show detailed specifications.")

    else:
        # ✅ Fallback: derive "models" from inventory table
        if "mowers" not in TABLES:
            st.error("No usable tables found. Missing 'mowers' and 'mower_models'.")
            st.write("Tables found:", sorted(TABLES))
        else:
            st.warning("Table 'mower_models' not found. Showing a derived model list from 'mowers' table.")

            derived_models = read_df(
                """
                SELECT
                    model AS model_name,
                    COUNT(*) AS units
                FROM mowers
                WHERE
                    (? = '' OR model LIKE '%' || ? || '%')
                GROUP BY model
                ORDER BY units DESC, model_name ASC
                """,
                (model_name, model_name),
            )

            if derived_models.empty:
                st.info("No models found in 'mowers'.")
            else:
                st.dataframe(derived_models, use_container_width=True, hide_index=True)

                st.markdown("### Model Details")
                selected_model = st.selectbox(
                    "Select a model",
                    derived_models["model_name"].tolist(),
                    index=0
                )

                # show units breakdown by status
                breakdown = read_df(
                    """
                    SELECT status, COUNT(*) AS units
                    FROM mowers
                    WHERE model = ?
                    GROUP BY status
                    ORDER BY units DESC
                    """,
                    (selected_model,),
                )
                st.write(f"**Selected model:** {selected_model}")
                st.dataframe(breakdown, use_container_width=True, hide_index=True)

# ------------------ TAB 2: PHYSICAL INVENTORY ------------------
with tab2:
    st.subheader("Physical Inventory")

    if "mowers" not in TABLES:
        st.error("Table 'mowers' not found in DB.")
        st.write("Tables found:", sorted(TABLES))
    else:
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            status = st.selectbox("Status", ["(all)", "AVAILABLE", "IN_SERVICE", "MAINTENANCE", "OUT_OF_ORDER"], index=0)
        with col2:
            site = st.text_input("Site contains", value="")
        with col3:
            model = st.text_input("Model contains", value="")

        inventory = read_df(
            """
            SELECT id, model, site, status, last_service_date
            FROM mowers
            WHERE
                (? = '(all)' OR status = ?)
                AND (? = '' OR site LIKE '%' || ? || '%')
                AND (? = '' OR model LIKE '%' || ? || '%')
            ORDER BY id
            """,
            (status, status, site, site, model, model),
        )

        if inventory.empty:
            st.info("No inventory items found.")
        else:
            st.dataframe(inventory, use_container_width=True, hide_index=True)

            st.markdown("### Unit Details")
            selected_mower_id = st.selectbox("Select mower", inventory["id"].tolist(), index=0)

            mower = inventory[inventory["id"] == selected_mower_id].iloc[0]
            c1, c2, c3 = st.columns(3)
            c1.metric("Mower ID", mower["id"])
            c2.metric("Model", mower["model"])
            c3.metric("Status", mower["status"])
            st.write(f"**Site:** {mower['site']}")
            st.write(f"**Last service date:** {mower['last_service_date']}")
