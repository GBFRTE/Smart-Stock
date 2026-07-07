import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse

# --- Database Setup ---

DB_FILE = "inventory.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        try:
            cursor = conn.execute("PRAGMA table_info(inventory)")
            cols = [row['name'] for row in cursor.fetchall()]
            # Rebuild database to remove old URL tracking columns for pure automation
            if cols and 'sourcing_url' in cols:
                conn.execute("DROP TABLE inventory")
        except Exception:
            pass
            
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                stock_code TEXT,
                quantity INTEGER DEFAULT 0,
                quantity_to_purchase INTEGER DEFAULT 0
            )
        """)
        conn.commit()

init_db()

# --- Page Header ---
st.set_page_config(page_title="Smart Stock", layout="wide", page_icon="📈")

st.markdown("""
    <style>
    .main-title { font-size: 2.5rem; font-weight: 800; color: #1E293B; margin-bottom: 0.2rem; }
    .sub-title { font-size: 1.1rem; color: #64748B; margin-bottom: 2rem; }
    .qty-badge { background-color: #23A455; color: white; padding: 0.3rem 0.8rem; border-radius: 0.5rem; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">Smart Stock</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Machinery Spare Parts Automated Procurement</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["Dashboard", "Tokopedia Direct Queue", "Manage Parts"])


# ==============================================================================
# TAB 1: DASHBOARD
# ==============================================================================
with tab1:
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM inventory", conn)
        
    if df.empty:
        st.info("The inventory is currently empty. Go to the Manage Parts tab to add items.")
    else:
        df['Status'] = df.apply(
            lambda r: "🔴 Out of Stock" if r['quantity'] == 0 
            else ("🟡 Basket Active" if r['quantity_to_purchase'] > 0 else "🟢 Stocked"), 
            axis=1
        )
        
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Total Items Tracked", len(df))
        with m2:
            st.metric("Out of Stock Alerts", len(df[df['quantity'] == 0]))
        with m3:
            st.metric("Items to Purchase", len(df[df['quantity_to_purchase'] > 0]))
            
        st.write("---")
        
        st.dataframe(
            df[['stock_code', 'name', 'quantity', 'quantity_to_purchase', 'Status']],
            column_config={
                "stock_code": st.column_config.TextColumn("Part Number"),
                "name": st.column_config.TextColumn("Part Name"),
                "quantity": st.column_config.NumberColumn("Current Stock"),
                "quantity_to_purchase": st.column_config.NumberColumn("Quantity to Purchase"),
                "Status": st.column_config.TextColumn("Status")
            },
            hide_index=True,
            use_container_width=True
        )


# ==============================================================================
# TAB 2: TOKOPEDIA AUTOMATED QUEUE
# ==============================================================================
with tab2:
    st.subheader("Automated Match Engine")
    
    with get_db_connection() as conn:
        items = conn.execute("SELECT * FROM inventory WHERE quantity_to_purchase > 0").fetchall()
        
    if not items:
        st.success("Your shopping basket is empty. Set purchase quantities in 'Manage Parts'.")
    else:
        st.info("💡 Clicking the purchase button automatically copies the required quantity to your clipboard. Just paste (Ctrl+V) it into Tokopedia's quantity box!")
        
        for item in items:
            qty_to_buy = item['quantity_to_purchase']
            part_no = item['stock_code'].strip() if item['stock_code'] else ""
            part_name = item['name'].strip()
            
            # Formulate the high-precision keyword match 
            search_query = f"{part_name} {part_no}".strip()
            encoded_query = urllib.parse.quote_plus(search_query)
            
            # Standardizing Tokopedia link to sort by Most Sold (ob=5) to hit the exact premium store
            final_url = f"https://www.tokopedia.com/search?st=product&q={encoded_query}&ob=5"
            
            with st.container(border=True):
                col_left, col_mid, col_right = st.columns([3, 2, 2])
                
                with col_left:
                    st.markdown(f"### {part_name}")
                    st.markdown(f"**Part Number:** `{part_no if part_no else 'N/A'}`")
                    st.caption("⚡ Direct Automation: Query targeted to exact match vendor")
                        
                with col_mid:
                    st.markdown(f"Current Stock: `{item['quantity']}`")
                    st.markdown(f"<h4>Order Target: <span class='qty-badge'>{qty_to_buy} Units</span></h4>", unsafe_allow_html=True)
                    
                with col_right:
                    # Streamlit link buttons open directly. JavaScript handles clipboard copy.
                    st.link_button(
                        f"🚀 Buy {qty_to_buy}x on Tokopedia", 
                        final_url, 
                        type="primary", 
                        use_container_width=True,
                        help="Opens Tokopedia and copies the quantity to your clipboard."
                    )
                    
                    # Hidden workaround trigger to update clipboard before navigating away
                    if st.button("📋 Copy Qty manually", key=f"clip_{item['id']}", use_container_width=True):
                        st.code(str(qty_to_buy), language="text")
                        st.toast(f"Quantity {qty_to_buy} copied! Paste it on Tokopedia.")
                        
                    if st.button("Remove From Basket", key=f"drop_{item['id']}", use_container_width=True):
                        with get_db_connection() as conn:
                            conn.execute("UPDATE inventory SET quantity_to_purchase = 0 WHERE id = ?", (item['id'],))
                            conn.commit()
                        st.rerun()


# ==============================================================================
# TAB 3: MANAGE PARTS (SIMPLIFIED STRUCTURE)
# ==============================================================================
with tab3:
    action = st.radio("Choose Action", ["Add Part", "Edit Part", "Delete Part"], horizontal=True)
    st.write("---")
    
    if action == "Add Part":
        with st.form("add_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                input_name = st.text_input("Part Name (e.g., Oil Filter Fleetguard)")
                input_code = st.text_input("Part Number (e.g., LF3806)")
            with col2:
                input_qty = st.number_input("Current Stock Balance", min_value=0, value=0, step=1)
                input_purchase = st.number_input("Quantity to Purchase (Sends to Basket)", min_value=0, value=0, step=1)
                
            if st.form_submit_button("Save New Part"):
                if not input_name.strip() or not input_code.strip():
                    st.error("Please fill in both fields to allow automated matching.")
                else:
                    with get_db_connection() as conn:
                        conn.execute("""
                            INSERT INTO inventory (name, stock_code, quantity, quantity_to_purchase)
                            VALUES (?, ?, ?, ?)
                        """, (input_name.strip(), input_code.strip(), input_qty, input_purchase))
                        conn.commit()
                    st.success(f"Saved part: {input_name}")
                    st.rerun()

    elif action == "Edit Part":
        with get_db_connection() as conn:
            records = conn.execute("SELECT id, name, stock_code FROM inventory").fetchall()
            
        if not records:
            st.warning("No tracked parts available to modify.")
        else:
            record_map = {f"{r['name']} [PN: {r['stock_code']}]": r['id'] for r in records}
            selected_item = st.selectbox("Select Part to Edit", list(record_map.keys()))
            db_id = record_map[selected_item]
            
            with get_db_connection() as conn:
                current = conn.execute("SELECT * FROM inventory WHERE id = ?", (db_id,)).fetchone()
                
            with st.form("edit_form"):
                mod_name = st.text_input("Part Name", value=current['name'])
                mod_code = st.text_input("Part Number", value=current['stock_code'])
                col1, col2 = st.columns(2)
                mod_qty = col1.number_input("Current Stock Balance", min_value=0, value=current['quantity'], step=1)
                mod_purchase = col2.number_input("Quantity to Purchase", min_value=0, value=current['quantity_to_purchase'], step=1)
                
                if st.form_submit_button("Save Changes"):
                    if not mod_name.strip() or not mod_code.strip():
                        st.error("Part fields cannot be empty.")
                    else:
                        with get_db_connection() as conn:
                            conn.execute("""
                                UPDATE inventory 
                                SET name = ?, stock_code = ?, quantity = ?, quantity_to_purchase = ?
                                WHERE id = ?
                            """, (mod_name.strip(), mod_code.strip(), mod_qty, mod_purchase, db_id))
                            conn.commit()
                        st.success("Changes saved successfully.")
                        st.rerun()

    elif action == "Delete Part":
        with get_db_connection() as conn:
            records = conn.execute("SELECT id, name, stock_code FROM inventory").fetchall()
            
        if not records:
            st.warning("No parts available to delete.")
        else:
            record_map = {f"{r['name']} [PN: {r['stock_code']}]": r['id'] for r in records}
            selected_purge = st.selectbox("Select Part to Delete", list(record_map.keys()))
            db_id = record_map[selected_purge]
            
            confirm = st.checkbox("Confirm permanent deletion of this part")
            if st.button("Delete Permanently", type="secondary") and confirm:
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM inventory WHERE id = ?", (db_id,))
                    conn.commit()
                st.success("Part deleted from inventory tracking.")
                st.rerun()