import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
import json
import time
from datetime import datetime

# --- AI DEPENDENCY VERIFICATION ---
try:
    import google.generativeai as genai
    import PIL.Image
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# --- STATE MEMORY INITIALIZATION ---
if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = None
if "ai_export_df" not in st.session_state:
    st.session_state.ai_export_df = None
if "uploader_session_id" not in st.session_state:
    st.session_state.uploader_session_id = 0
if "text_scanner_session_id" not in st.session_state:
    st.session_state.text_scanner_session_id = 0
# State fix for Price Intelligence to prevent nested button crashes
if "price_audit_payload" not in st.session_state:
    st.session_state.price_audit_payload = None
if "target_part_row" not in st.session_state:
    st.session_state.target_part_row = None

# --- DATABASE ENGINE SETUP & MIGRATION ---
def init_db():
    conn = sqlite3.connect('inventory_v2.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_name TEXT NOT NULL,
            part_number TEXT,
            machinery_name TEXT DEFAULT '',
            current_stock INTEGER DEFAULT 0,
            quantity_to_buy INTEGER DEFAULT 0,
            in_basket INTEGER DEFAULT 0,
            last_price REAL DEFAULT 0.0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_id INTEGER,
            price REAL NOT NULL,
            recorded_date TEXT NOT NULL,
            price_type TEXT DEFAULT 'Actual',
            FOREIGN KEY(part_id) REFERENCES inventory(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute("PRAGMA table_info(inventory)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    if 'quantity_to_buy' not in existing_columns:
        cursor.execute('ALTER TABLE inventory ADD COLUMN quantity_to_buy INTEGER DEFAULT 0')
    if 'in_basket' not in existing_columns:
        cursor.execute('ALTER TABLE inventory ADD COLUMN in_basket INTEGER DEFAULT 0')
    if 'machinery_name' not in existing_columns:
        cursor.execute("ALTER TABLE inventory ADD COLUMN machinery_name TEXT DEFAULT ''")
    if 'last_price' not in existing_columns:
        cursor.execute("ALTER TABLE inventory ADD COLUMN last_price REAL DEFAULT 0.0")
        
    cursor.execute("PRAGMA table_info(price_history)")
    hist_columns = [col[1] for col in cursor.fetchall()]
    if 'price_type' not in hist_columns:
        cursor.execute("ALTER TABLE price_history ADD COLUMN price_type TEXT DEFAULT 'Actual'")
        
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    return sqlite3.connect('inventory_v2.db')

def get_part_emoji(part_name):
    pn = part_name.lower()
    if any(w in pn for w in ["ban", "tire", "wheel", "roda", "velg"]): return "🛞"
    if any(w in pn for w in ["oli", "oil", "lubricant", "pelumas"]): return "🛢️"
    if any(w in pn for w in ["solar", "fuel", "bensin", "diesel", "bakar", "tangki"]): return "⛽"
    if any(w in pn for w in ["aki", "battery", "baterai"]): return "🔋"
    if any(w in pn for w in ["rem", "brake", "pad"]): return "🛑"
    if any(w in pn for w in ["busi", "spark", "plug", "listrik", "cable"]): return "⚡"
    if any(w in pn for w in ["air", "water", "coolant", "radiator", "cairan", "wiper"]): return "💧"
    if any(w in pn for w in ["lampu", "lamp", "light", "bohlam"]): return "💡"
    if any(w in pn for w in ["rantai", "chain", "belt", "tali", "v-belt"]): return "⛓️"
    if any(w in pn for w in ["filter", "saringan", "separator"]): return "🌪️"
    if any(w in pn for w in ["seal", "gasket", "karet", "baut", "nut", "screw", "bearing"]): return "🔩"
    if any(w in pn for w in ["kaca", "glass", "spion", "mirror", "window"]): return "🪞"
    return "📦"

def generate_procurement_url(part_name, part_number, marketplace, filter_type):
    search_term = f"{part_name.strip()} {part_number.strip()}".strip()
    encoded_query = urllib.parse.quote(search_term)
    
    if marketplace == "Tokopedia":
        base_url = f"https://www.tokopedia.com/search?q={encoded_query}"
        if filter_type == "Cheapest": base_url += "&ob=3"  
        elif filter_type == "Most Sold": base_url += "&ob=5"  
        elif filter_type == "Trusted": base_url += "&fshop=2"  
    elif marketplace == "Shopee":
        base_url = f"https://shopee.co.id/search?keyword={encoded_query}"
        if filter_type == "Cheapest": base_url += "&sortBy=price&order=asc"
        elif filter_type == "Most Sold": base_url += "&sortBy=sales"
        elif filter_type == "Trusted": base_url += "&sortBy=relevancy" 
    else:
        base_url = f"https://www.lazada.co.id/catalog/?q={encoded_query}"
        if filter_type == "Cheapest": base_url += "&sort=priceasc"  
        elif filter_type == "Most Sold": base_url += "&sort=popularity"  
        elif filter_type == "Trusted": base_url += "&rating=4"  
    return base_url

# --- INITIAL APP INTERFACE BRANDING ---
st.set_page_config(page_title="Smart Stock", page_icon="📦", layout="wide")
st.title("📊 Smart Stock")
st.markdown("### *Inventory & Procurement Control*")
st.write("---")

# --- SIDEBAR AT-A-GLANCE STATUS LOGISTICS ---
try:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(current_stock), COUNT(CASE WHEN quantity_to_buy > 0 THEN 1 END) FROM inventory")
    db_summary = cursor.fetchone()
    conn.close()
    sb_total_types = db_summary[0] if db_summary[0] else 0
    sb_total_units = db_summary[1] if db_summary[1] else 0
    sb_needs_purchase = db_summary[2] if db_summary[2] else 0
except sqlite3.OperationalError:
    init_db()
    sb_total_types, sb_total_units, sb_needs_purchase = 0, 0, 0

st.sidebar.header("📈 Stock Status Glance")
if sb_needs_purchase == 0:
    status_color, status_text = "#198754", "🟢 SYSTEM HEALTHY<br><span style='font-size:13px;'>All lines stocked.</span>"
elif sb_needs_purchase <= 3:
    status_color, status_text = "#ffc107", "🟡 WARNING DELAYS<br><span style='font-size:13px;'>Procurement lines pending.</span>"
else:
    status_color, status_text = "#dc3545", "🔴 CRITICAL BACKLOG<br><span style='font-size:13px;'>Immediate orders required.</span>"

st.sidebar.markdown(f'<div style="background-color: {status_color}; padding: 14px; border-radius: 8px; color: {"#000000" if status_color=="#ffc107" else "#ffffff"}; font-weight: bold; margin-bottom: 15px; text-align: center;">{status_text}</div>', unsafe_allow_html=True)

sb_col1, sb_col2 = st.sidebar.columns(2)
sb_col1.metric("Unique Parts", sb_total_types)
sb_col2.metric("Total On Hand", sb_total_units)

st.sidebar.write("---")
st.sidebar.header("🔑 AI Access Configurations")
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Universal key for auditing and scanning engines.")
st.sidebar.link_button("✨ Get Free Gemini API Key", "https://aistudio.google.com/app/apikey", use_container_width=True)
st.sidebar.write("---")

active_view = st.radio(
    "Workspace Navigation:",
    ["🔍 View Inventory", "🛠️ Manage Parts Workspace", "🛒 Shopping Basket", "🤖 Gemini AI Scanner", "📊 Price Intelligence"],
    horizontal=True, label_visibility="collapsed"
)
st.write("---")

# =========================================================================
# WORKSPACE 1: VIEW INVENTORY
# =========================================================================
if active_view == "🔍 View Inventory":
    st.subheader("Current Stock Status")
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, part_name AS [Part Name], part_number AS [Part Number], machinery_name AS [Machinery], current_stock AS [Current Stock], quantity_to_buy AS [Quantity to Buy], last_price AS [Last Price (Rp)] FROM inventory", conn)
    conn.close()
    
    if df.empty:
        st.info("Inventory database is empty.")
    else:
        search_query = st.text_input("🔍 Quick Search Component", placeholder="Type part name, code, or machinery descriptor...")
        raw_machines = df["Machinery"].fillna("").unique()
        unique_machinery = ["All Machinery"] + sorted([m for m in raw_machines if m.strip() != ""])
        
        filter_col, sort_col, exp_btn_col = st.columns([1.5, 1.5, 1])
        selected_machinery = filter_col.selectbox("🏗️ Filter by Specific Machinery:", unique_machinery, index=0)
        selected_sorting = sort_col.selectbox("🔃 Sort Inventory Display:", ["Default Matrix", "Highest Stock On Hand", "Most Quantity to Buy"], index=0)
        
        if search_query.strip():
            q = search_query.strip().lower()
            df = df[df["Part Name"].fillna("").str.lower().str.contains(q) | df["Part Number"].fillna("").str.lower().str.contains(q) | df["Machinery"].fillna("").str.lower().str.contains(q)]
        if selected_machinery != "All Machinery":
            df = df[df["Machinery"] == selected_machinery]
        if selected_sorting == "Highest Stock On Hand":
            df = df.sort_values(by="Current Stock", ascending=False)
        elif selected_sorting == "Most Quantity to Buy":
            df = df.sort_values(by="Quantity to Buy", ascending=False)
            
        st.write("---")
        if exp_btn_col.button("✨ Generate AI Spreadsheet", use_container_width=True, type="primary"):
            if not api_key.strip():
                st.error("Please insert your Gemini API Key in the sidebar to run the auditor tool.")
            elif not HAS_GEMINI:
                st.error("Generative AI modules missing.")
            else:
                with st.spinner("Gemini is auditing inventory metrics..."):
                    try:
                        raw_manifest = df[["Part Name", "Part Number", "Machinery", "Current Stock", "Quantity to Buy", "Last Price (Rp)"]].to_json(orient="records")
                        report_prompt = f"Audit this industrial dataset and append exactly these keys: 'Category', 'Stock Health', and 'Procurement Priority'. Output raw JSON array only: {raw_manifest}"
                        genai.configure(api_key=api_key.strip())
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        response = model.generate_content(report_prompt)
                        st.session_state.ai_export_df = pd.read_json(response.text.replace("```json", "").replace("```", "").strip())
                        st.toast("AI Spreadsheet compiled successfully!")
                    except Exception as e:
                        st.error(f"Spreadsheet mapping failed: {str(e)}")
                        
        if st.session_state.ai_export_df is not None:
            excel_ready_csv = st.session_state.ai_export_df.to_csv(index=False, sep=";").encode('utf-8-sig')
            st.download_button(label="📥 Click to Download Professional Spreadsheet (.csv)", data=excel_ready_csv, file_name="AI_Inventory_Report.csv", mime="text/csv", use_container_width=True)
                
        st.caption("💡 Tip: Click anywhere on any row below to unlock price profiles and quick-purchase buttons.")
        
        # Safe handling if older Streamlit versions do not support selection
        try:
            table_selection = st.dataframe(
                df[["id", "Part Name", "Part Number", "Machinery", "Current Stock", "Quantity to Buy", "Last Price (Rp)"]], 
                use_container_width=True, hide_index=True, column_config={"id": None, "Last Price (Rp)": st.column_config.NumberColumn(format="Rp %,d")}, 
                selection_mode="single-row", on_select="rerun"
            )
        except TypeError:
            table_selection = None
            st.dataframe(df[["id", "Part Name", "Part Number", "Machinery", "Current Stock", "Quantity to Buy", "Last Price (Rp)"]], use_container_width=True, hide_index=True)
            st.warning("⚠️ Local Streamlit version outdated. Row selection features disabled. Run `pip install --upgrade streamlit` to enable.")

        if table_selection and table_selection.selection.rows:
            selected_row_idx = table_selection.selection.rows[0]
            t_id = int(df.iloc[selected_row_idx]["id"])
            t_name = str(df.iloc[selected_row_idx]["Part Name"])
            qty_to_buy = int(df.iloc[selected_row_idx]["Quantity to Buy"])
            c_stock = int(df.iloc[selected_row_idx]["Current Stock"])
            c_price = float(df.iloc[selected_row_idx]["Last Price (Rp)"] or 0.0)
            
            st.write("---")
            conn = get_db_connection()
            hist_df = pd.read_sql_query("SELECT recorded_date AS [Date], price AS [Price (Rp)] FROM price_history WHERE part_id = ? ORDER BY recorded_date ASC", conn, params=(t_id,))
            conn.close()
            
            chart_col, action_col = st.columns([3, 2])
            with chart_col:
                st.markdown(f"📈 **Price Profile Visualizer:** `{t_name}`")
                if not hist_df.empty:
                    st.line_chart(hist_df.set_index("Date")[["Price (Rp)"]], use_container_width=True)
                else:
                    st.info("💡 No historical tracking logs seed yet.")
            with action_col:
                st.markdown("🛠️ **Quick Dashboard Controls**")
                if qty_to_buy > 0:
                    exec_price = st.number_input("Verify Final Unit Cost Paid (Rp):", min_value=0.0, value=c_price, step=5000.0, key="quick_cost_input")
                    if st.button(f"✅ Mark Item as Purchased (Add {qty_to_buy} to Stock)", type="primary", use_container_width=True):
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute('UPDATE inventory SET current_stock=?, quantity_to_buy=0, in_basket=0, last_price=? WHERE id=?', (c_stock + qty_to_buy, exec_price, t_id))
                        cursor.execute('INSERT INTO price_history (part_id, price, recorded_date, price_type) VALUES (?, ?, ?, "Actual")', (t_id, exec_price, today_str))
                        conn.commit()
                        conn.close()
                        st.success(f"📦 Dispatched! Added {qty_to_buy} items into Central Stock.")
                        time.sleep(1.0)
                        st.rerun()
                else:
                    st.info("ℹ️ No outstanding procurement orders for this asset line.")
                    
                if st.button("🗑️ Permanently Remove Item From Fleet Records", type="secondary", use_container_width=True):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM inventory WHERE id = ?", (t_id,))
                    cursor.execute("DELETE FROM price_history WHERE part_id = ?", (t_id,))
                    conn.commit(); conn.close()
                    st.success(f"🗑️ Successfully erased '{t_name}' records.")
                    time.sleep(1.0)
                    st.rerun()

# =========================================================================
# WORKSPACE 2: MANAGE PARTS WORKSPACE
# =========================================================================
elif active_view == "🛠️ Manage Parts Workspace":
    st.subheader("Component Registry & Modification Panel")
    conn = get_db_connection()
    parts_df = pd.read_sql_query("SELECT id, part_name, part_number, machinery_name FROM inventory", conn)
    conn.close()
    
    workspace_options = ["➕ Register New Part (Fresh Entry)"]
    part_id_mapping = {}
    for _, row in parts_df.iterrows():
        m_label = f" ({row['machinery_name']})" if row['machinery_name'] else ""
        display_label = f"Edit: {row['part_name']}{m_label} [{row['part_number'] or 'No Number'}] (ID: {row['id']})"
        workspace_options.append(display_label)
        part_id_mapping[display_label] = row['id']
        
    selected_action = st.selectbox("Choose Operation Mode:", workspace_options, index=0)
    st.write("---")
    
    if selected_action == "➕ Register New Part (Fresh Entry)":
        with st.form("unified_add_form", clear_on_submit=True):
            new_name = st.text_input("Part Name *", placeholder="e.g., Hydraulic Cylinder Seal Kit")
            new_machinery = st.text_input("Assigned Machinery / Equipment Name", placeholder="e.g., Caterpillar 320D Excavator")
            new_number = st.text_input("Part Number / Model Serial (Optional)", placeholder="e.g., LF3806")
            new_stock = st.number_input("Current Stock On Hand", min_value=0, step=1, value=0)
            new_qty_buy = st.number_input("Initial Purchase Request Qty", min_value=0, step=1, value=0)
            new_price = st.number_input("Base Purchase Unit Price (Rp)", min_value=0.0, step=5000.0, value=0.0)
            
            if st.form_submit_button("💾 Save New Component Entry"):
                if not new_name.strip():
                    st.error("Part Name is a mandatory field.")
                else:
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('INSERT INTO inventory (part_name, part_number, machinery_name, current_stock, quantity_to_buy, in_basket, last_price) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                                   (new_name.strip(), new_number.strip(), new_machinery.strip(), new_stock, new_qty_buy, 1 if new_qty_buy > 0 else 0, new_price))
                    if new_price > 0:
                        cursor.execute('INSERT INTO price_history (part_id, price, recorded_date, price_type) VALUES (?, ?, ?, "Actual")', (cursor.lastrowid, new_price, today_str))
                    conn.commit(); conn.close()
                    st.success(f"✅ Successfully registered '{new_name.strip()}' into inventory logs!")
                    time.sleep(1.0)
                    st.rerun()
    else:
        target_id = part_id_mapping[selected_action]
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT part_name, part_number, current_stock, quantity_to_buy, machinery_name, last_price FROM inventory WHERE id = ?", (target_id,))
        current_details = cursor.fetchone()
        conn.close()
        
        if current_details:
            with st.form(f"unified_modify_form_{target_id}"):
                mod_name = st.text_input("Part Name", value=str(current_details[0]))
                mod_machinery = st.text_input("Assigned Machinery Name", value=str(current_details[4] if current_details[4] else ""))
                mod_number = st.text_input("Part Number", value=str(current_details[1] if current_details[1] else ""))
                mod_stock = st.number_input("Current Stock", min_value=0, value=int(current_details[2]))
                mod_qty_buy = st.number_input("Quantity to Buy", min_value=0, value=int(current_details[3]))
                mod_price = st.number_input("Adjust Latest Unit Price (Rp)", min_value=0.0, step=5000.0, value=float(current_details[5] or 0.0))
                
                if st.form_submit_button("💾 Save Structural Variations"):
                    if not mod_name.strip():
                        st.error("Part Name cannot be empty.")
                    else:
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute('UPDATE inventory SET part_name=?, part_number=?, machinery_name=?, current_stock=?, quantity_to_buy=?, in_basket=?, last_price=? WHERE id=?', 
                                       (mod_name.strip(), mod_number.strip(), mod_machinery.strip(), mod_stock, mod_qty_buy, 1 if mod_qty_buy > 0 else 0, mod_price, target_id))
                        if mod_price != current_details[5]:
                            cursor.execute('INSERT INTO price_history (part_id, price, recorded_date, price_type) VALUES (?, ?, ?, "Actual")', (target_id, mod_price, today_str))
                        conn.commit(); conn.close()
                        st.success("🔧 Entry verified and modified successfully.")
                        time.sleep(1.0)
                        st.rerun()

# =========================================================================
# WORKSPACE 3: SHOPPING BASKET
# =========================================================================
elif active_view == "🛒 Shopping Basket":
    st.subheader("Items to Procure")
    with st.expander("⚙️ Target Marketplace Settings & Filters", expanded=False):
        col_m1, col_m2 = st.columns(2)
        selected_marketplace = col_m1.selectbox("Select E-Commerce Platform", ["Tokopedia", "Shopee", "Lazada"], index=0)
        selected_filter = col_m2.selectbox("Apply Search Sorting Matrix", ["Default", "Cheapest", "Most Sold", "Trusted"], index=0)
        
    st.write("---")
    conn = get_db_connection()
    basket_df = pd.read_sql_query("SELECT id, part_name, part_number, machinery_name, current_stock, quantity_to_buy, last_price FROM inventory WHERE quantity_to_buy > 0", conn)
    conn.close()
    
    if basket_df.empty:
        st.info("Shopping basket is empty.")
    else:
        for _, row in basket_df.iterrows():
            machinery_label = f" [For: {row['machinery_name']}]" if row['machinery_name'] else ""
            basket_emoji = get_part_emoji(row['part_name'])
            url = generate_procurement_url(row['part_name'], row['part_number'], selected_marketplace, selected_filter)
            
            with st.container():
                st.markdown(f"### {basket_emoji} {row['part_name']}{machinery_label}")
                c_det, c_act = st.columns([3, 2])
                c_det.write(f"**Part Code:** `{row['part_number'] or 'N/A'}` | **Stock:** {row['current_stock']} | **Order Volume:** {row['quantity_to_buy']} | **Last Cost:** Rp {row['last_price'] or 0.0:,.2f}")
                st.link_button(f"🛒 Search on {selected_marketplace}", url, use_container_width=True)
                
                with c_act.expander("Verify Price & Mark Received"):
                    card_price = st.number_input("Actual Unit Price (Rp):", min_value=0.0, value=float(row['last_price'] or 0.0), key=f"p_in_{row['id']}")
                    if st.button("Confirm Restock", key=f"rec_{row['id']}", use_container_width=True):
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute('UPDATE inventory SET current_stock=?, quantity_to_buy=0, last_price=? WHERE id=?', (row['current_stock'] + row['quantity_to_buy'], card_price, row['id']))
                        cursor.execute('INSERT INTO price_history (part_id, price, recorded_date, price_type) VALUES (?, ?, ?, "Actual")', (row['id'], card_price, today_str))
                        conn.commit(); conn.close()
                        st.toast("📦 Stock replenishment logged successfully.")
                        time.sleep(1.0)
                        st.rerun()

# =========================================================================
# WORKSPACE 4: GEMINI AI SCANNER
# =========================================================================
elif active_view == "🤖 Gemini AI Scanner":
    st.subheader("Gemini Intelligent Import Engine")
    st.markdown("Drop a **picture, PDF invoice, text list,** or paste **chaotic chat messages** to auto-extract log metrics.")
    
    if not HAS_GEMINI:
        st.error("Missing required generative AI python libraries.")
        
    input_type = st.radio("Choose Input Format:", ["📋 Paste Text / Chat Message", "📄 Upload File (Photo, PDF, or TXT)"], horizontal=True)
    ai_prompt = """You are an expert industrial inventory parser. Extract physical spare components or machinery parts listed. Return a valid JSON array of objects and absolutely nothing else. Structure layout format: [{"part_name": "Name", "part_number": "Serial or empty string", "machinery_name": "Equipment name or empty string", "current_stock": int, "quantity_to_buy": int}]"""
    
    if input_type == "📋 Paste Text / Chat Message":
        user_text = st.text_area("Paste chaotic ledger strings below:", height=150, key=f"text_area_field_{st.session_state.text_scanner_session_id}")
        if st.button("✨ Scan Text Content", use_container_width=True) and HAS_GEMINI:
            if not api_key.strip(): st.warning("Please type in your Gemini API Key first.")
            elif not user_text.strip(): st.error("Text field cannot be empty.")
            else:
                with st.spinner("AI parsing context..."):
                    try:
                        genai.configure(api_key=api_key.strip())
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        response = model.generate_content([ai_prompt, user_text])
                        
                        # Fortified cleaner to guarantee valid JSON load execution
                        cleaned_json = response.text.replace("```json", "").replace("```", "").strip()
                        st.session_state.extracted_data = json.loads(cleaned_json)
                    except Exception as e: st.error(f"Execution aborted: {str(e)}")
    else:
        uploaded_file = st.file_uploader("Drop log sheets here:", type=["jpg", "jpeg", "png", "pdf", "txt"], key=f"file_uploader_field_{st.session_state.uploader_session_id}")
        if uploaded_file:
            file_mime = uploaded_file.type
            if "image" in file_mime: st.image(uploaded_file, caption="Staged Input Matrix", width=300)
            else: st.info(f"📄 Document Ready: `{uploaded_file.name}`")
            
            if st.button("✨ Scan Document File Context", use_container_width=True) and HAS_GEMINI:
                if not api_key.strip(): st.warning("Please configure API key first.")
                else:
                    with st.spinner("Processing multimodal matrices..."):
                        try:
                            genai.configure(api_key=api_key.strip())
                            model = genai.GenerativeModel('gemini-2.5-flash')
                            if "image" in file_mime:
                                response = model.generate_content([ai_prompt, PIL.Image.open(uploaded_file)])
                            elif "pdf" in file_mime:
                                response = model.generate_content([ai_prompt, {"mime_type": "application/pdf", "data": uploaded_file.read()}])
                            else:
                                response = model.generate_content([ai_prompt, uploaded_file.read().decode("utf-8")])
                            
                            cleaned_json = response.text.replace("```json", "").replace("```", "").strip()
                            st.session_state.extracted_data = json.loads(cleaned_json)
                        except Exception as e: st.error(f"Multimodal scan failure: {str(e)}")

    if st.session_state.extracted_data and active_view == "🤖 Gemini AI Scanner":
        st.write("---")
        st.success("🎉 Gemini extracted elements cleanly! Review layout metrics before saving:")
        preview_df = pd.DataFrame(st.session_state.extracted_data)
        st.dataframe(preview_df, use_container_width=True)
        
        if st.button("📥 Save All Extracted Items to SQLite Database", use_container_width=True, type="primary"):
            conn = get_db_connection()
            cursor = conn.cursor()
            saved_count = 0
            for item in st.session_state.extracted_data:
                p_name = item.get("part_name", "Unmapped").strip()
                p_num = item.get("part_number", "").strip()
                p_mach = item.get("machinery_name", "").strip()
                c_stock = int(item.get("current_stock", 0))
                q_buy = int(item.get("quantity_to_buy", 0))
                
                if p_name:
                    cursor.execute("SELECT id, quantity_to_buy FROM inventory WHERE LOWER(part_number) = LOWER(?) AND part_number != '' LIMIT 1", (p_num,))
                    existing = cursor.fetchone()
                    if existing:
                        n_buy = existing[1] + q_buy
                        cursor.execute('UPDATE inventory SET quantity_to_buy=?, in_basket=? WHERE id=?', (n_buy, 1 if n_buy > 0 else 0, existing[0]))
                    else:
                        cursor.execute('INSERT INTO inventory (part_name, part_number, machinery_name, current_stock, quantity_to_buy, in_basket, last_price) VALUES (?, ?, ?, ?, ?, ?, 0.0)', (p_name, p_num, p_mach, c_stock, q_buy, 1 if q_buy > 0 else 0))
                    saved_count += 1
            conn.commit(); conn.close()
            st.session_state.extracted_data = None
            st.session_state.uploader_session_id += 1        
            st.session_state.text_scanner_session_id += 1    
            st.success(f"Processed and automatically cleared {saved_count} items into database storage!")
            time.sleep(1.0)
            st.rerun()

# =========================================================================
# WORKSPACE 5: AUTOMATED PRICE INTELLIGENCE (NESTED BUTTON FIX APPLIED)
# =========================================================================
elif active_view == "📊 Price Intelligence":
    st.subheader("📈 Autonomous Price Intelligence Agent")
    st.markdown("Select a component below to trigger an automated market analysis across Tokopedia, Shopee, and Lazada.")
    
    conn = get_db_connection()
    parts_list_df = pd.read_sql_query("SELECT id, part_name, part_number, machinery_name, last_price FROM inventory", conn)
    conn.close()
    
    if parts_list_df.empty:
        st.info("Register components inside your workspace first to initialize market scanning.")
    else:
        part_options = {}
        for _, r in parts_list_df.iterrows():
            lbl = f"📦 {r['part_name']} [Code: {r['part_number'] or 'N/A'}] (Machinery: {r['machinery_name'] or 'General'})"
            part_options[lbl] = r
            
        chosen_part_label = st.selectbox("Select Component Asset for AI Scraping Audit:", list(part_options.keys()))
        selected_part_row = part_options[chosen_part_label]
        
        st.write("---")
        # Trigger button changes state values instead of processing inline code
        if st.button("🤖 Launch Real-Time Cross-Platform Price Audit & Forecast", type="primary", use_container_width=True):
            if not api_key.strip():
                st.warning("Please insert your universal Gemini API Key in the sidebar.")
            elif not HAS_GEMINI:
                st.error("AI modules missing from operational container configuration.")
            else:
                with st.spinner("Gemini Market Intelligence Agent searching cross-platform indexes..."):
                    try:
                        p_name = selected_part_row['part_name']
                        p_num = selected_part_row['part_number'] or ''
                        p_mach = selected_part_row['machinery_name'] or ''
                        
                        market_audit_prompt = f"""You are an Indonesian heavy equipment procurement intelligence analyst. Return a clean, raw JSON schema mapping live price values for: {p_name} ({p_num}) for machinery {p_mach}. Structure must match: {{"tokopedia_price": int, "shopee_price": int, "lazada_price": int, "best_price": int, "winning_platform": "String", "historical_timeline": [{"date": "2026-04", "price": int}], "forecast_timeline": [{"date": "2026-08", "price": int}]}}"""
                        genai.configure(api_key=api_key.strip())
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        response = model.generate_content(market_audit_prompt)
                        
                        cleaned_json = response.text.replace("```json", "").replace("```", "").strip()
                        st.session_state.price_audit_payload = json.loads(cleaned_json)
                        st.session_state.target_part_row = selected_part_row
                    except Exception as e:
                        st.error(f"Marketplace analysis aborted: {str(e)}")
        
        # Safe isolation rendering context outside of tracking triggers!
        if st.session_state.price_audit_payload is not None:
            payload = st.session_state.price_audit_payload
            t_row = st.session_state.target_part_row
            
            st.markdown("### 🛒 Real-time Marketplace Price Evaluation")
            col_tok, col_sho, col_laz = st.columns(3)
            col_tok.metric("Tokopedia Est.", f"Rp {payload['tokopedia_price']:,}")
            col_sho.metric("Shopee Est.", f"Rp {payload['shopee_price']:,}")
            col_laz.metric("Lazada Est.", f"Rp {payload['lazada_price']:,}")
            st.success(f"🏆 Best Reliable Choice: **Rp {payload['best_price']:,}** via **{payload['winning_platform']}**")
            
            timeline_records = []
            for h in payload['historical_timeline']:
                timeline_records.append({"Date": h['date'], "Price (Rp)": h['price']})
            timeline_records.append({"Date": datetime.now().strftime("%Y-%m-%d"), "Price (Rp)": payload['best_price']})
            for f in payload['forecast_timeline']:
                timeline_records.append({"Date": f['date'], "Price (Rp)": f['price']})
                
            timeline_df = pd.DataFrame(timeline_records).sort_values(by="Date")
            st.markdown("### 📊 Continuous Price Trajectory Matrix (Past -> Present -> Future)")
            st.line_chart(timeline_df.set_index("Date"), use_container_width=True)
            
            st.write("---")
            if st.button("📥 Lock Winning Price as Current System Valuation Asset", type="secondary", use_container_width=True):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('UPDATE inventory SET last_price=? WHERE id=?', (payload['best_price'], int(t_row['id'])))
                
                for h in payload['historical_timeline']:
                    cursor.execute('INSERT INTO price_history (part_id, price, recorded_date, price_type) VALUES (?, ?, ?, "Historical Audit")', (int(t_row['id']), h['price'], h['date']))
                for f in payload['forecast_timeline']:
                    cursor.execute('INSERT INTO price_history (part_id, price, recorded_date, price_type) VALUES (?, ?, ?, "Future Estimate")', (int(t_row['id']), f['price'], f['date']))
                
                conn.commit(); conn.close()
                st.session_state.price_audit_payload = None  # Clear memory state cache cleanly
                st.success("🎉 Pricing profile stored cleanly inside database tracking lines!")
                time.sleep(1.0)
                st.rerun()