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

# --- Premium UI Styling ---
st.set_page_config(page_title="Smart Stock Elite", layout="wide", page_icon="📈")

# Injecting clean custom CSS for an executive layout
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Inter', sans-serif;
        background-color: #FAFAFA;
    }
    
    .main-title { 
        font-size: 2.8rem; 
        font-weight: 800; 
        color: #312E81; /* Premium Deep Indigo */
        letter-spacing: -0.05em;
        margin-bottom: 0.1rem; 
    }
    
    .sub-title { 
        font-size: 1.1rem; 
        color: #475569; /* Polished Slate Gray */
        font-weight: 400;
        margin-bottom: 2.5rem; 
    }
    
    div[data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        color: #1E1B4B !important;
    }
    
    .status-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">Smart Stock Elite</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">High-Precision Machinery Components Procurement Dashboard</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["Dashboard Overview", "Tokopedia Procurement Basket", "Inventory Management"])


# ==============================================================================
# TAB 1: DASHBOARD OVERVIEW
# ==============================================================================
with tab1:
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM inventory", conn)
        
    if df.empty:
        st.info("The inventory tracking system is currently empty. Open the Inventory Management tab to initialize entries.")
    else:
        df['Status'] = df.apply(
            lambda r: "🔴 Out of Stock" if r['quantity'] == 0 
            else ("🟡 Procurement Pending" if r['quantity_to_purchase'] > 0 else "🟢 Fully Stocked"), 
            axis=1
        )
        
        # Key Metrics Grid
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Total Line Items", len(df))
        with m2:
            st.metric("Critical Depletions", len(df[df['quantity'] == 0]))
        with m3:
            st.metric("Active Purchase Orders", len(df[df['quantity_to_purchase'] > 0]))
            
        st.write("---")
        
        st.dataframe(
            df[['stock_code', 'name', 'quantity', 'quantity_to_purchase', 'Status']],
            column_config={
                "stock_code": st.column_config.TextColumn("Part Number"),
                "name": st.column_config.TextColumn("Component Identity"),
                "quantity": st.column_config.NumberColumn("Current On-Hand"),
                "quantity_to_purchase": st.column_config.NumberColumn("Allocated Order Size"),
                "Status": st.column_config.TextColumn("Operational Status")
            },
            hide_index=True,
            use_container_width=True
        )


# ==============================================================================
# TAB 2: TOKOPEDIA PROCUREMENT BASKET
# ==============================================================================
with tab2:
    st.subheader("Active Order Queue")
    
    with get_db_connection() as conn:
        items = conn.execute("SELECT * FROM inventory WHERE quantity_to_purchase > 0 OR manual_finding = 1").fetchall()
        
    if not items:
        st.success("All component pipelines are balanced. No active Tokopedia procurements required.")
    else:
        for item in items:
            qty_to_buy = max(1, item['quantity_to_purchase'])
            part_no = item['stock_code'].strip() if item['stock_code'] else ""
            part_name = item['name'].strip()
            
            # Precision Strict Matching Layout
            # Wraps the term in quotes to bypass lookalikes and locate the definitive merchant
            search_query = f'"{part_name} {part_no}"'.strip()
            encoded_query = urllib.parse.quote_plus(search_query)
            
            is_locked = bool(item['sourcing_url'] and item['sourcing_url'].strip().startswith("http"))
            
            with st.container(border=True):
                col_left, col_mid, col_right = st.columns([3, 2, 2])
                
                with col_left:
                    st.markdown(f"### {part_name}")
                    st.markdown(f"**Part Number Reference:** `{part_no if part_no else 'Unspecified'}`")
                    
                    if is_locked:
                        st.markdown("🔒 **Link Status:** Verified Direct Supplier Locked")
                        if st.button("Unlock Supply Chain Link", key=f"reset_{item['id']}"):
                            with get_db_connection() as conn:
                                conn.execute("UPDATE inventory SET sourcing_url = '' WHERE id = ?", (item['id'],))
                                conn.commit()
                            st.rerun()
                    else:
                        st.markdown("🔍 **Link Status:** Dynamic Strict Phrase Matching Active")
                        
                        # Clean popover module for setting permanent supply lines
                        with st.popover("Lock Direct Store URL", use_container_width=True):
                            pasted_url = st.text_input("Paste exact verified supplier link:", key=f"input_url_{item['id']}")
                            if st.button("Commit Link to Database", key=f"save_url_{item['id']}"):
                                if pasted_url.strip().startswith("http"):
                                    with get_db_connection() as conn:
                                        conn.execute("UPDATE inventory SET sourcing_url = ? WHERE id = ?", (pasted_url.strip(), item['id']))
                                        conn.commit()
                                    st.success("Supplier endpoint successfully assigned.")
                                    st.rerun()
                                else:
                                    st.error("Provide a fully qualified web address.")
                        
                with col_mid:
                    st.markdown(f"Current Stock: `{item['quantity']}`")
                    st.markdown(f"#### Targeted Procurement: **{qty_to_buy} Units**")
                    
                with col_right:
                    if is_locked:
                        # Fires directly to the dedicated supplier catalog item
                        st.link_button("🛍️ Open Direct Store Page", item['sourcing_url'].strip(), type="primary", use_container_width=True)
                    else:
                        # Searches Tokopedia using high-volume sorting filters to isolate the definitive store listing
                        final_url = f"https://www.tokopedia.com/search?st=product&q={encoded_query}&ob=5"
                        st.link_button("🚀 Find Direct Match", final_url, type="secondary", use_container_width=True)
                        
                    st.write("")
                    if st.button("Remove from Basket Queue", key=f"drop_{item['id']}", use_container_width=True):
                        with get_db_connection() as conn:
                            conn.execute("UPDATE inventory SET quantity_to_purchase = 0, manual_finding = 0 WHERE id = ?", (item['id'],))
                            conn.commit()
                        st.rerun()


# ==============================================================================
# TAB 3: INVENTORY MANAGEMENT
# ==============================================================================
with tab3:
    action = st.radio("System Action Protocol", ["Add Part Record", "Modify Existing Record", "Purge Record"], horizontal=True)
    st.write("---")
    
    if action == "Add Part Record":
        with st.form("add_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                input_name = st.text_input("Component Name Reference")
                input_code = st.text_input("Manufacturer Part Number")
            with col2:
                input_qty = st.number_input("On-Hand Inventory Units", min_value=0, value=0, step=1)
                input_purchase = st.number_input("Immediate Purchase Allocation Size", min_value=0, value=0, step=1)
                
            input_url = st.text_input("Direct Tokopedia Link Overwrite")
            input_force = st.checkbox("Force placement into the procurement queue")
            
            if st.form_submit_button("Initialize Component Entry"):
                if not input_name.strip() or not input_code.strip():
                    st.error("Both the Component Name and Part Number fields must be accurately designated.")
                else:
                    with get_db_connection() as conn:
                        conn.execute("""
                            INSERT INTO inventory (name, stock_code, quantity, quantity_to_purchase, sourcing_url, manual_finding)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (input_name.strip(), input_code.strip(), input_qty, input_purchase, input_url.strip(), 1 if input_force else 0))
                        conn.commit()
                    st.success(f"Successfully integrated record for: {input_name}")
                    st.rerun()

    elif action == "Modify Existing Record":
        with get_db_connection() as conn:
            records = conn.execute("SELECT id, name, stock_code FROM inventory").fetchall()
            
        if not records:
            st.warning("No tracking records exist to amend.")
        else:
            record_map = {f"{r['name']} [PN: {r['stock_code']}]": r['id'] for r in records}
            selected_item = st.selectbox("Select Target Registry to Modify", list(record_map.keys()))
            db_id = record_map[selected_item]
            
            with get_db_connection() as conn:
                current = conn.execute("SELECT * FROM inventory WHERE id = ?", (db_id,)).fetchone()
                
            with st.form("edit_form"):
                mod_name = st.text_input("Component Name Reference", value=current['name'])
                mod_code = st.text_input("Manufacturer Part Number", value=current['stock_code'])
                col1, col2 = st.columns(2)
                mod_qty = col1.number_input("On-Hand Inventory Units", min_value=0, value=current['quantity'], step=1)
                mod_purchase = col2.number_input("Immediate Purchase Allocation Size", min_value=0, value=current['quantity_to_purchase'], step=1)
                mod_url = st.text_input("Direct Tokopedia Link Overwrite", value=current['sourcing_url'] or "")
                mod_force = st.checkbox("Force placement into the procurement queue", value=bool(current['manual_finding']))
                
                if st.form_submit_button("Commit Database Adjustments"):
                    if not mod_name.strip() or not mod_code.strip():
                        st.error("Component Name and Part Number references cannot be left vacant.")
                    else:
                        with get_db_connection() as conn:
                            conn.execute("""
                                UPDATE inventory 
                                SET name = ?, stock_code = ?, quantity = ?, quantity_to_purchase = ?, sourcing_url = ?, manual_finding = ?
                                WHERE id = ?
                            """, (mod_name.strip(), mod_code.strip(), mod_qty, mod_purchase, mod_url.strip(), 1 if mod_force else 0, db_id))
                            conn.commit()
                        st.success("Database logs modified successfully.")
                        st.rerun()

    elif action == "Purge Record":
        with get_db_connection() as conn:
            records = conn.execute("SELECT id, name, stock_code FROM inventory").fetchall()
            
        if not records:
            st.warning("No tracking records exist to purge.")
        else:
            record_map = {f"{r['name']} [PN: {r['stock_code']}]": r['id'] for r in records}
            selected_purge = st.selectbox("Select Target Registry to Purge", list(record_map.keys()))
            db_id = record_map[selected_purge]
            
            confirm = st.checkbox("Authorize permanent deletion of this registry sequence")
            if st.button("Execute Record Purge", type="secondary") and confirm:
                with get_db_connection() as conn:
                    conn.execute("DELETE FROM inventory WHERE id = ?", (db_id,))
                    conn.commit()
                st.success("Component tracing record completely extracted from system memory.")
                st.rerun()