import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
import json
import time  # Handles pacing and user-friendly visual delays

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
            in_basket INTEGER DEFAULT 0
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
        
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    return sqlite3.connect('inventory_v2.db')

# --- DYNAMIC PART EMOTE CONTEXT MAPPER ---
def get_part_emoji(part_name):
    pn = part_name.lower()
    if any(w in pn for w in ["ban", "tire", "wheel", "roda", "velg"]):
        return "🛞"
    elif any(w in pn for w in ["oli", "oil", "lubricant", "pelumas"]):
        return "🛢️"
    elif any(w in pn for w in ["solar", "fuel", "bensin", "diesel", "bakar", "tangki"]):
        return "⛽"
    elif any(w in pn for w in ["aki", "battery", "baterai"]):
        return "🔋"
    elif any(w in pn for w in ["rem", "brake", "pad"]):
        return "🛑"
    elif any(w in pn for w in ["busi", "spark", "plug", "listrik", "cable"]):
        return "⚡"
    elif any(w in pn for w in ["air", "water", "coolant", "radiator", "cairan", "wiper"]):
        return "💧"
    elif any(w in pn for w in ["lampu", "lamp", "light", "bohlam"]):
        return "💡"
    elif any(w in pn for w in ["rantai", "chain", "belt", "tali", "v-belt"]):
        return "⛓️"
    elif any(w in pn for w in ["filter", "saringan", "separator"]):
        return "🌪️"
    elif any(w in pn for w in ["seal", "gasket", "karet", "baut", "nut", "screw", "bearing"]):
        return "🔩"
    elif any(w in pn for w in ["kaca", "glass", "spion", "mirror", "window"]):
        return "🪞"
    return "📦"

# --- DYNAMIC MARKETPLACE URL GENERATOR ---
def generate_procurement_url(part_name, part_number, marketplace, filter_type):
    if part_number and part_number.strip():
        search_term = f"{part_name.strip()} {part_number.strip()}"
    else:
        search_term = part_name.strip()
        
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
    elif marketplace == "Lazada":
        base_url = f"https://www.lazada.co.id/catalog/?q={encoded_query}"
        if filter_type == "Cheapest": base_url += "&sort=priceasc"  
        elif filter_type == "Most Sold": base_url += "&sort=popularity"  
        elif filter_type == "Trusted": base_url += "&rating=4"  
            
    return base_url

# --- MINIMALIST BRANDING ---
st.set_page_config(page_title="Smart Stock", page_icon="📦", layout="wide")

st.title("📊 Smart Stock")
st.markdown("### *Inventory & Procurement Control*")
st.write("---")

# --- SIDEBAR: GLOBAL SETUP & CLEAN LOGISTICS ---
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
    status_color = "#198754"  
    status_text = f"🟢 SYSTEM HEALTHY<br><span style='font-size:13px;'>All {sb_total_types} components are fully stocked.</span>"
elif sb_needs_purchase <= 3:
    status_color = "#ffc107"  
    status_text = f"🟡 WARNING DELAYS<br><span style='font-size:13px;'>{sb_needs_purchase} items pending procurement buy lines.</span>"
else:
    status_color = "#dc3545"  
    status_text = f"🔴 CRITICAL BACKLOG<br><span style='font-size:13px;'>{sb_needs_purchase} items need immediate buying.</span>"

st.sidebar.markdown(
    f"""
    <div style="background-color: {status_color}; padding: 14px; border-radius: 8px; color: {'#000000' if status_color=='#ffc107' else '#ffffff'}; font-weight: bold; margin-bottom: 15px; text-align: center;">
        {status_text}
    </div>
    """, 
    unsafe_allow_html=True
)

sb_col1, sb_col2 = st.sidebar.columns(2)
sb_col1.metric("Unique Parts", sb_total_types)
sb_col2.metric("Total On Hand", sb_total_units)

# --- SIDEBAR GLOBAL CREDENTIALS MANAGER ---
st.sidebar.write("---")
st.sidebar.header("🔑 AI Access Configurations")
api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Universal key utilized for scanning and generating reports.")

# --- SIDEBAR FEATURE: DYNAMIC INVENTORY FINDER ---
st.sidebar.write("---")
st.sidebar.header("🔍 Find Inventory")
search_query = st.sidebar.text_input("Quick Search Name or Code", placeholder="e.g., Seal, LF3806", key="sidebar_search")

if search_query.strip():
    conn = get_db_connection()
    search_pattern = f"%{search_query.strip()}%"
    search_df = pd.read_sql_query('''
        SELECT part_name AS [Name], part_number AS [Code], machinery_name AS [Machinery], current_stock AS [Stock] 
        FROM inventory 
        WHERE part_name LIKE ? OR part_number LIKE ? OR machinery_name LIKE ?
    ''', conn, params=(search_pattern, search_pattern, search_pattern))
    conn.close()
    
    if not search_df.empty:
        st.sidebar.success(f"🎯 Matches Found ({len(search_df)}):")
        st.sidebar.dataframe(search_df, hide_index=True, use_container_width=True)
    else:
        st.sidebar.error("❌ No matching item found.")
        
    if st.sidebar.button("❌ Clear Search Results", use_container_width=True, type="secondary"):
        st.session_state.sidebar_search = ""
        st.rerun()

st.sidebar.write("---")

# --- STATE NAVIGATION ROUTER ---
active_view = st.radio(
    "Workspace Navigation:",
    ["🔍 View Inventory", "🛠️ Manage Parts Workspace", "🛒 Shopping Basket", "🤖 Gemini AI Scanner"],
    horizontal=True,
    label_visibility="collapsed"
)
st.write("---")

# =========================================================================
# VIEW INVENTORY WORKSPACE (WITH INTEGRATED MARK-PURCHASED TICK ACTION)
# =========================================================================
if active_view == "🔍 View Inventory":
    st.subheader("Current Stock Status")
    
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT id, 
               part_name AS [Part Name], 
               part_number AS [Part Number], 
               machinery_name AS [Machinery], 
               current_stock AS [Current Stock], 
               quantity_to_buy AS [Quantity to Buy] 
        FROM inventory
    """, conn)
    conn.close()
    
    if df.empty:
        st.info("Inventory database is empty.")
    else:
        raw_machines = df["Machinery"].fillna("").unique()
        unique_machinery = ["All Machinery"] + sorted([m for m in raw_machines if m.strip() != ""])
        
        filter_col, sort_col, exp_btn_col = st.columns([1.5, 1.5, 1])
        selected_machinery = filter_col.selectbox("🏗️ Filter by Specific Machinery:", unique_machinery, index=0)
        selected_sorting = sort_col.selectbox("🔃 Sort Inventory Display:", ["Default Matrix", "Highest Stock On Hand", "Most Quantity to Buy"], index=0)
        
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
                st.error("Generative AI modules are missing from the configuration matrix.")
            else:
                with st.spinner("Gemini is auditing inventory metrics..."):
                    try:
                        raw_manifest = df[["Part Name", "Part Number", "Machinery", "Current Stock", "Quantity to Buy"]].to_json(orient="records")
                        report_prompt = f"Audit this industrial dataset and append 'Category', 'Stock Health', and 'Procurement Priority'. Output raw JSON array only: {raw_manifest}"
                        
                        genai.configure(api_key=api_key.strip())
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        response = model.generate_content(report_prompt)
                        
                        clean_json = response.text.replace("```json", "").replace("```", "").strip()
                        st.session_state.ai_export_df = pd.read_json(clean_json)
                        st.toast("AI Spreadsheet compiled successful!")
                    except Exception as e:
                        st.error(f"Spreadsheet compilation failed: {str(e)}")
                        
        if st.session_state.ai_export_df is not None:
            excel_ready_csv = st.session_state.ai_export_df.to_csv(index=False, sep=";").encode('utf-8-sig')
            st.download_button(label="📥 Click to Download Professional Spreadsheet (.csv)", data=excel_ready_csv, file_name="AI_Inventory_Report.csv", mime="text/csv", use_container_width=True)
                
        st.caption("💡 Tip: Click anywhere on any row below to unlock instant actions for that component.")
        
        table_selection = st.dataframe(
            df[["id", "Part Name", "Part Number", "Machinery", "Current Stock", "Quantity to Buy"]], 
            use_container_width=True,
            hide_index=True,
            column_config={"id": None}, 
            selection_mode="single-row",
            on_select="rerun"
        )
        
        # INTERACTIVE CONTROL PANEL (TICK AS PURCHASED & REMOVALS)
        if table_selection and table_selection.selection.rows:
            selected_row_idx = table_selection.selection.rows[0]
            target_id = int(df.iloc[selected_row_idx]["id"])
            target_name = str(df.iloc[selected_row_idx]["Part Name"])
            target_code = str(df.iloc[selected_row_idx]["Part Number"] or "N/A")
            qty_to_buy = int(df.iloc[selected_row_idx]["Quantity to Buy"])
            current_stock = int(df.iloc[selected_row_idx]["Current Stock"])
            
            st.write("---")
            st.markdown(f"🛠️ **Dynamic Dashboard Control for:** `{target_name}` (`{target_code}`)")
            
            act_col1, act_col2 = st.columns(2)
            
            # Contextual Procurement Button
            if qty_to_buy > 0:
                if act_col1.button(f"✅ Mark Item as Purchased (Add {qty_to_buy} to Stock)", type="primary", use_container_width=True):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('UPDATE inventory SET current_stock=?, quantity_to_buy=0, in_basket=0 WHERE id=?', (current_stock + qty_to_buy, target_id))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"📦 Order Complete! Transferred {qty_to_buy} units directly into Active Stock.")
                    time.sleep(1.5)  # Deliberate feedback delay
                    st.rerun()
            else:
                act_col1.info("ℹ️ No outstanding orders pending procurement for this item.")
                
            if act_col2.button(f"🗑️ Permanently Remove Item From Fleet Records", type="secondary", use_container_width=True):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM inventory WHERE id = ?", (target_id,))
                conn.commit()
                conn.close()
                
                st.success(f"🗑️ Successfully deleted '{target_name}' from inventory lines.")
                time.sleep(1.5)  # Deliberate feedback delay
                st.rerun()

# ==========================================
# UNIFIED MANAGE PARTS WORKSPACE
# ==========================================
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
        st.markdown("### ✨ Register a New Part")
        with st.form("unified_add_form", clear_on_submit=True):
            new_name = st.text_input("Part Name", placeholder="e.g., Hydraulic Cylinder Seal Kit")
            new_machinery = st.text_input("Assigned Machinery / Equipment Name", placeholder="e.g., Caterpillar 320D Excavator")
            new_number = st.text_input("Part Number / Model Serial (Optional)", placeholder="e.g., LF3806")
            new_stock = st.number_input("Current Stock On Hand", min_value=0, step=1, value=0)
            new_qty_buy = st.number_input("Initial Purchase Request Qty", min_value=0, step=1, value=0)
            
            if st.form_submit_button("💾 Save New Component Entry"):
                if not new_name.strip(): 
                    st.error("Part Name is a mandatory field.")
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO inventory (part_name, part_number, machinery_name, current_stock, quantity_to_buy, in_basket) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (new_name.strip(), new_number.strip(), new_machinery.strip(), new_stock, new_qty_buy, 1 if new_qty_buy > 0 else 0))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"✅ Successfully registered '{new_name.strip()}' into the fleet log matrix!")
                    time.sleep(1.5)
                    st.rerun()

    else:
        target_id = part_id_mapping[selected_action]
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT part_name, part_number, current_stock, quantity_to_buy, machinery_name FROM inventory WHERE id = ?", (target_id,))
        current_details = cursor.fetchone()
        conn.close()
        
        if current_details:
            st.markdown(f"### ✏️ Edit Component Configurations: *{current_details[0]}*")
            with st.form(f"unified_modify_form_{target_id}"):
                mod_name = st.text_input("Part Name", value=str(current_details[0]))
                mod_machinery = st.text_input("Assigned Machinery / Equipment Name", value=str(current_details[4] if current_details[4] else ""))
                mod_number = st.text_input("Part Number", value=str(current_details[1] if current_details[1] else ""))
                mod_stock = st.number_input("Current Stock", min_value=0, value=int(current_details[2]))
                mod_qty_buy = st.number_input("Quantity to Buy", min_value=0, value=int(current_details[3]))
                
                if st.form_submit_button("💾 Save Structural Variations"):
                    if not mod_name.strip():
                        st.error("Part Name cannot be completely empty.")
                    else:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute('''
                            UPDATE inventory 
                            SET part_name=?, part_number=?, machinery_name=?, current_stock=?, quantity_to_buy=?, in_basket=? 
                            WHERE id=?
                        ''', (mod_name.strip(), mod_number.strip(), mod_machinery.strip(), mod_stock, mod_qty_buy, 1 if mod_qty_buy > 0 else 0, target_id))
                        conn.commit()
                        conn.close()
                        
                        st.success("🔧 System entry modified and verified successfully.")
                        time.sleep(1.5)
                        st.rerun()

# ==========================================
# SHOPPING BASKET WORKSPACE
# ==========================================
elif active_view == "🛒 Shopping Basket":
    st.subheader("Items to Procure")
    
    with st.expander("⚙️ Target Marketplace Settings & Filters", expanded=False):
        col_m1, col_m2 = st.columns(2)
        selected_marketplace = col_m1.selectbox("Select E-Commerce Platform", ["Tokopedia", "Shopee", "Lazada"], index=0)
        selected_filter = col_m2.selectbox("Apply Search Sorting / Filter Matrix", ["Default", "Cheapest", "Most Sold", "Trusted"], index=0)
    
    st.write("---")
    
    conn = get_db_connection()
    basket_df = pd.read_sql_query("SELECT id, part_name, part_number, machinery_name, current_stock, quantity_to_buy FROM inventory WHERE quantity_to_buy > 0", conn)
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
                c_det.write(f"**Part Code:** `{row['part_number'] or 'N/A'}` | **Stock On Hand:** {row['current_stock']} | **Order Volume:** {row['quantity_to_buy']}")
                st.link_button(f"🛒 Search on {selected_marketplace}", url, use_container_width=True)
                if c_act.button(f"Mark Received", key=f"rec_{row['id']}", use_container_width=True):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('UPDATE inventory SET current_stock=?, quantity_to_buy=0 WHERE id=?', (row['current_stock'] + row['quantity_to_buy'], row['id']))
                    conn.commit(); conn.close()
                    
                    st.toast("📦 Stock replenishment logged successfully.")
                    time.sleep(1.5)
                    st.rerun()

# ==========================================
# GEMINI AI SCANNER WORKSPACE
# ==========================================
elif active_view == "🤖 Gemini AI Scanner":
    st.subheader("Gemini Intelligent Import Engine")
    st.markdown("Drop a **picture, PDF file, text list,** or paste a **messy message** to auto-extract items.")
    
    if not HAS_GEMINI:
        st.error("Missing required AI modules. Check your requirements.txt deployment file profile.")
    
    st.write("---")
    input_type = st.radio("Choose Input Format:", ["📋 Paste Text / Chat Message", "📄 Upload File (Photo, PDF, or TXT)"], horizontal=True)
    
    ai_prompt = """
    You are an expert industrial inventory assistant. Analyze the input data and extract all physical spare parts or machine components mentioned.
    Each item object inside the array must exactly mirror this structure:
    [
      {
        "part_name": "Clean descriptive name in English (e.g., Hydraulic Seal Kit)",
        "part_number": "The specific alpha-numeric code/serial number if visible, otherwise pass empty string ''",
        "machinery_name": "The name of the heavy machine or equipment it belongs to if visible, otherwise pass empty string ''",
        "current_stock": integer (use listed current amount, or 0 if unmentioned),
        "quantity_to_buy": integer (use listed order amount, or 0 if unmentioned)
      }
    ]
    """

    if input_type == "📋 Paste Text / Chat Message":
        user_text = st.text_area("Paste chaotic text or message columns below:", height=150, key=f"text_area_field_{st.session_state.text_scanner_session_id}")
        if st.button("✨ Scan Text Content", use_container_width=True) and HAS_GEMINI:
            if not api_key.strip():
                st.warning("Please type in your API Key in the sidebar first.")
            elif not user_text.strip():
                st.error("Please paste your text lines first.")
            else:
                with st.spinner("Gemini is parsing linguistic syntax layout..."):
                    try:
                        genai.configure(api_key=api_key.strip())
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        response = model.generate_content([ai_prompt, user_text])
                        clean_json = response.text.replace("```json", "").replace("```", "").strip()
                        st.session_state.extracted_data = json.loads(clean_json)
                    except Exception as e:
                        st.error(f"AI parsing execution aborted: {str(e)}")

    else:
        uploaded_file = st.file_uploader("Upload inventory photo, PDF invoice, or text manifest:", type=["jpg", "jpeg", "png", "pdf", "txt"], key=f"file_uploader_field_{st.session_state.uploader_session_id}")
        if uploaded_file:
            file_mime = uploaded_file.type
            if "image" in file_mime:
                st.image(uploaded_file, caption="Staged Visual Input Source", width=300)
            else:
                st.info(f"📄 Document Ready: `{uploaded_file.name}`")
            
            if st.button("✨ Scan Document File Context", use_container_width=True) and HAS_GEMINI:
                if not api_key.strip():
                    st.warning("Please type in your API Key in the sidebar first.")
                else:
                    with st.spinner("Gemini Multi-modal processing active file matrices..."):
                        try:
                            genai.configure(api_key=api_key.strip())
                            model = genai.GenerativeModel('gemini-2.5-flash')
                            if "image" in file_mime:
                                img = PIL.Image.open(uploaded_file)
                                response = model.generate_content([ai_prompt, img])
                            elif "pdf" in file_mime:
                                pdf_bytes = uploaded_file.read()
                                response = model.generate_content([ai_prompt, {"mime_type": "application/pdf", "data": pdf_bytes}])
                            else:
                                text_content = uploaded_file.read().decode("utf-8")
                                response = model.generate_content([ai_prompt, text_content])
                                
                            clean_json = response.text.replace("```json", "").replace("```", "").strip()
                            st.session_state.extracted_data = json.loads(clean_json)
                        except Exception as e:
                            st.error(f"Multi-modal scanning execution aborted: {str(e)}")

    if st.session_state.extracted_data and active_view == "🤖 Gemini AI Scanner":
        st.write("---")
        st.success("🎉 Gemini extracted matching items perfectly! Review data layout before saving:")
        preview_df = pd.DataFrame(st.session_state.extracted_data)
        st.dataframe(preview_df, use_container_width=True)
        
        if st.button("📥 Save All Extracted Items to SQLite Database", use_container_width=True, type="primary"):
            conn = get_db_connection()
            cursor = conn.cursor()
            
            saved_count = 0
            for item in st.session_state.extracted_data:
                p_name = item.get("part_name", "Unmapped Component").strip()
                p_num = item.get("part_number", "").strip()
                p_machinery = item.get("machinery_name", "").strip()
                c_stock = int(item.get("current_stock", 0))
                q_buy = int(item.get("quantity_to_buy", 0))
                
                if p_name:
                    if p_num:
                        cursor.execute("SELECT id, quantity_to_buy FROM inventory WHERE LOWER(part_number) = LOWER(?) LIMIT 1", (p_num,))
                        existing_part = cursor.fetchone()
                    else:
                        existing_part = None
                        
                    if existing_part:
                        new_total_buy = existing_part[1] + q_buy
                        cursor.execute('UPDATE inventory SET quantity_to_buy = ?, in_basket = ? WHERE id = ?', (new_total_buy, 1 if new_total_buy > 0 else 0, existing_part[0]))
                    else:
                        cursor.execute('INSERT INTO inventory (part_name, part_number, machinery_name, current_stock, quantity_to_buy, in_basket) VALUES (?, ?, ?, ?, ?, ?)', (p_name, p_num, p_machinery, c_stock, q_buy, 1 if q_buy > 0 else 0))
                    saved_count += 1
                    
            conn.commit()
            conn.close()
            
            st.session_state.extracted_data = None
            st.session_state.uploader_session_id += 1        
            st.session_state.text_scanner_session_id += 1    
            
            st.success(f"Successfully processed and cleared {saved_count} items into database storage!")
            time.sleep(1.5)
            st.rerun()