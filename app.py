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
            if cols and 'quantity_to_purchase' not in cols:
                conn.execute("DROP TABLE inventory")
        except Exception:
            pass
            
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                stock_code TEXT,
                quantity INTEGER DEFAULT 0,
                quantity_to_purchase INTEGER DEFAULT 0,
                sourcing_url TEXT,
                manual_finding INTEGER DEFAULT 0
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
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">Smart Stock</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Machinery Spare Parts Tracking Dashboard</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["Dashboard", "Shopping Basket (Tokopedia)", "Manage Parts"])


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
            else ("🟡 Procurement Pending" if r['quantity_to_purchase'] > 0 else "🟢 Stocked"), 
            axis=1
        )
        
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Total Items Tracked", len(df))
        with m2:
            st.metric("Out of Stock Alerts", len(df[df['quantity'] == 0]))
        with m3:
            st.metric("Items in Basket", len(df[df['quantity_to_purchase'] > 0]))
            
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
# TAB 2: SHOPPING BASKET (DIRECT TOKOPEDIA INTEGRATION)
# ==============================================================================
with tab2:
    st.subheader("Tokopedia Direct Match Basket")
    
    with get_db_connection() as conn:
        items = conn.execute("SELECT * FROM inventory WHERE quantity_to_purchase > 0 OR manual_finding = 1").fetchall()
        
    if not items:
        st.success("Your procurement basket is empty. Add a purchase quantity to parts under 'Manage Parts'.")
    else:
        for item in items:
            qty_to_buy = max(1, item['quantity_to_purchase'])
            part_no = item['stock_code'].strip() if item['stock_code'] else ""
            part_name = item['name'].strip()
            
            search_query = f"{part_name} {part_no}".strip()
            encoded_query = urllib.parse.quote_plus(search_query)
            
            # Check if we have a locked direct store link
            is_locked = bool(item['sourcing_url'] and item['sourcing_url'].strip().startswith("http"))
            
            with st.container(border=True):
                col_left, col_mid, col_right = st.columns([3, 2, 2])
                
                with col_left:
                    st.markdown(f"### {part_name}")
                    st.markdown(f"**Part Number:** `{part_no if part_no else 'N/A'}`")
                    
                    if is_locked:
                        st.markdown("🎯 **Status:** 🔒 **Locked to Specific Store**")
                        if st.button("Unlock / Reset Link", key=f"reset_{item['id']}"):
                            with get_db_connection() as conn:
                                conn.execute("UPDATE inventory SET sourcing_url = '' WHERE id = ?", (item['id'],))
                                conn.commit()
                            st.rerun()
                    else:
                        st.markdown("🎯 **Status:** 🔍 Using Targeted Search (Most Sold Filter)")
                        
                        # Inline fast-locking form right inside the basket row
                        with st.popover("🔗 Lock Direct Link", use_container_width=True):
                            pasted_url = st.text_input("Paste exact store item link here:", key=f"input_url_{item['id']}")
                            if st.button("Save & Lock Link", key=f"save_url_{item['id']}"):
                                if pasted_url.strip().startswith("http"):
                                    with get_db_connection() as conn:
                                        conn.execute("UPDATE inventory SET sourcing_url = ? WHERE id = ?", (pasted_url.strip(), item['id']))
                                        conn.commit()
                                    st.success("Store link locked successfully!")
                                    st.rerun()
                                else:
                                    st.error("Please enter a valid URL.")
                        
                with col_mid:
                    st.markdown(f"Current Stock Balance: `{item['quantity']}`")
                    st.markdown(f"#### Order Quantity: **{qty_to_buy} Units**")
                    
                with col_right:
                    if is_locked:
                        # Leads straight to your exact chosen vendor item page
                        st.link_button("🛍️ Open Direct Store Page", item['sourcing_url'].strip(), type="primary", use_container_width=True)
                    else:
                        # Fallback targeted search string pre-filtered for Best Selling/Most Reviews (ob=5)
                        final_url = f"https://www.tokopedia.com/search?st=product&q={encoded_query}&ob=5"
                        st.link_button("🚀 Find & Match on Tokopedia", final_url, type="secondary", use_container_width=True)
                        
                    st.write("")
                    if st.button("Clear from Basket", key=f"drop_{item['id']}", use_container_width=True):
                        with get_db_connection() as conn:
                            conn.execute("UPDATE inventory SET quantity_to_purchase = 0, manual_finding = 0 WHERE id = ?", (item['id'],))
                            conn.commit()
                        st.rerun()


# ==============================================================================
# TAB 3: MANAGE PARTS
# ==============================================================================
with tab3:
    action = st.radio("Choose Action", ["Add Part", "Edit Part", "Delete Part"], horizontal=True)
    st.write("---")
    
    if action == "Add Part":
        with st.form("add_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                input_name = st.text_input("Part Name")
                input_code = st.text_input("Part Number")
            with col2:
                input_qty = st.number_input("Current Stock Balance", min_value=0, value=0, step=1)
                input_purchase = st.number_input("Quantity to Purchase (Instantly Adds to Basket)", min_value=0, value=0, step=1)
                
            input_url = st.text_input("Direct Tokopedia Product Link (Optional Override)")
            input_force = st.checkbox("Force item into basket layout regardless of quantity")
            
            if st.form_submit_button("Save New Part"):
                if not input_name.strip() or not input_code.strip():
                    st.error("Please fill in both the Part Name and Part Number fields.")
                else:
                    with get_db_connection() as conn:
                        conn.execute("""
                            INSERT INTO inventory (name, stock_code, quantity, quantity_to_purchase, sourcing_url, manual_finding)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (input_name.strip(), input_code.strip(), input_qty, input_purchase, input_url.strip(), 1 if input_force else 0))
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
                mod_purchase = col2.number_input("Quantity to Purchase (Instantly Adds to Basket)", min_value=0, value=current['quantity_to_purchase'], step=1)
                mod_url = st.text_input("Direct Tokopedia Product Link", value=current['sourcing_url'] or "")
                mod_force = st.checkbox("Force item into basket layout regardless of quantity", value=bool(current['manual_finding']))
                
                if st.form_submit_button("Save Changes"):
                    if not mod_name.strip() or not mod_code.strip():
                        st.error("Part Name and Part Number fields cannot be left empty.")
                    else:
                        with get_db_connection() as conn:
                            conn.execute("""
                                UPDATE inventory 
                                SET name = ?, stock_code = ?, quantity = ?, quantity_to_purchase = ?, sourcing_url = ?, manual_finding = ?
                                WHERE id = ?
                            """, (mod_name.strip(), mod_code.strip(), mod_qty, mod_purchase, mod_url.strip(), 1 if mod_force else 0, db_id))
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