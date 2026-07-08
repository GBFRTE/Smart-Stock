import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
import json

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

# --- DATABASE ENGINE SETUP & MIGRATION ---
def init_db():
    conn = sqlite3.connect('inventory_v2.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_name TEXT NOT NULL,
            part_number TEXT,
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
        
    conn.commit()
    conn.close()

# Execute database structure check
init_db()

def get_db_connection():
    return sqlite3.connect('inventory_v2.db')

# --- DYNAMIC PART EMOTE CONTEXT MAPPER ---
def get_part_emoji(part_name):
    """Scans keywords in English/Indonesian to assign contextual emojis dynamically for the shopping basket."""
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

st.title("Smart Stock")
st.markdown("### *Inventory & Procurement Control*")
st.write("---")

# --- SIDEBAR: AT-A-GLANCE SUMMARY WITH OPERATIONAL ERROR DEFENSE ---
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
    # Safe fallback if database is momentarily locked or undergoing migration on cloud servers
    init_db()
    sb_total_types, sb_total_units, sb_needs_purchase = 0, 0, 0

sb_healthy_parts = sb_total_types - sb_needs_purchase

st.sidebar.header("📈 Stock Status Glance")

if sb_needs_purchase == 0:
    status_color = "#198754"  
    status_text = f"🟢 SYSTEM HEALTHY<br><span style='font-size:13px;'>All {sb_total_types} components are fully stocked.</span>"
elif sb_needs_purchase <= 3:
    status_color = "#ffc107"  
    status_text = f"🟡 WARNING DELAYS<br><span style='font-size:13px;'>{sb_needs_purchase} items pending procurement buy lines.</span>"
else:
    status_color = "#dc3545"  
    status_text = f"🔴 CRITICAL BACKLOG<br><span style='font-size:13px;'>Lots of due orders! {sb_needs_purchase} items need immediate buying.</span>"

st.sidebar.markdown(
    f"""
    <div style="background-color: {status_color}; padding: 14px; border-radius: 8px; color: {'#000000' if status_color=='#ffc107' else '#ffffff'}; font-weight: bold; margin-bottom: 15px; text-align: center; box-shadow: 1px 1px 5px rgba(0,0,0,0.15);">
        {status_text}
    </div>
    """, 
    unsafe_allow_html=True
)

sb_col1, sb_col2 = st.sidebar.columns(2)
sb_col1.metric("Unique Parts", sb_total_types)
sb_col2.metric("Total On Hand", sb_total_units)

sb_col3, sb_col4 = st.sidebar.columns(2)
sb_col3.metric("Healthy Lines", sb_healthy_parts)
sb_col4.metric("Procurement Due", sb_needs_purchase, delta=f"+{sb_needs_purchase}" if sb_needs_purchase > 0 else None, delta_color="inverse")

# --- SIDEBAR FEATURE: DYNAMIC INVENTORY FINDER (CLEAN TEXT) ---
st.sidebar.write("---")
st.sidebar.header("🔍 Find Inventory")
search_query = st.sidebar.text_input("Quick Search Name or Code", placeholder="e.g., Seal, LF3806", key="sidebar_search")

if search_query.strip():
    conn = get_db_connection()
    search_pattern = f"%{search_query.strip()}%"
    search_df = pd.read_sql_query('''
        SELECT part_name AS [Name], part_number AS [Code], current_stock AS [Stock], quantity_to_buy AS [To Buy] 
        FROM inventory 
        WHERE part_name LIKE ? OR part_number LIKE ?
    ''', conn, params=(search_pattern, search_pattern))
    conn.close()
    
    if not search_df.empty:
        st.sidebar.success(f"🎯 Matches Found ({len(search_df)}):")
        st.sidebar.dataframe(search_df, hide_index=True, use_container_width=True)
    else:
        st.sidebar.error("❌ No matching item found.")

st.sidebar.write("---")

st.sidebar.header("🇮🇩 Marketplace Settings")
selected_marketplace = st.sidebar.selectbox("Select Platform", ["Tokopedia", "Shopee", "Lazada"], index=0)
selected_filter = st.sidebar.selectbox("Apply Filter / Sorting", ["Default", "Cheapest", "Most Sold", "Trusted"], index=0)

# =========================================================================
# BULLETPROOF STATE NAVIGATION (Replaces st.tabs to fix content bleeding)
# =========================================================================
active_view = st.radio(
    "Workspace Navigation:",
    ["🔍 View Inventory", "🛠️ Manage Parts Workspace", "🛒 Shopping Basket", "🤖 Gemini AI Scanner"],
    horizontal=True,
    label_visibility="collapsed"
)
st.write("---")

# ==========================================
# VIEW INVENTORY WORKSPACE (CLEAN TEXT)
# ==========================================
if active_view == "🔍 View Inventory":
    st.subheader("Current Stock Status")
    st.caption("💡 Tip: Click directly on any row below to instantly select it for removal.")
    
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, part_name AS [Part Name], part_number AS [Part Number], current_stock AS [Current Stock], quantity_to_buy AS [Quantity to Buy] FROM inventory", conn)
    conn.close()
    
    if df.empty:
        st.info("Inventory database is empty.")
    else:
        table_selection = st.dataframe(
            df[["id", "Part Name", "Part Number", "Current Stock", "Quantity to Buy"]], 
            use_container_width=True,
            hide_index=True,
            column_config={"id": None}, 
            selection_mode="single-row",
            on_select="rerun"
        )
        
        if table_selection and table_selection.selection.rows:
            selected_row_idx = table_selection.selection.rows[0]
            target_id = int(df.iloc[selected_row_idx]["id"])
            target_name = str(df.iloc[selected_row_idx]["Part Name"])
            target_code = str(df.iloc[selected_row_idx]["Part Number"] or "N/A")
            
            st.write("---")
            st.markdown(f"### 🗑️ Direct Action: Delete **{target_name}** (`{target_code}`)?")
            
            if st.button(f"Confirm: Permanently Erase From System", type="primary", use_container_width=True):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM inventory WHERE id = ?", (target_id,))
                conn.commit()
                conn.close()
                st.toast(f"Successfully removed {target_name}!")
                st.rerun()

# ==========================================
# UNIFIED MANAGE PARTS WORKSPACE
# ==========================================
elif active_view == "🛠️ Manage Parts Workspace":
    st.subheader("Component Registry & Modification Panel")
    
    conn = get_db_connection()
    parts_df = pd.read_sql_query("SELECT id, part_name, part_number FROM inventory", conn)
    conn.close()
    
    workspace_options = ["➕ Register New Part (Fresh Entry)"]
    part_id_mapping = {}
    
    for _, row in parts_df.iterrows():
        display_label = f"Edit: {row['part_name']} [{row['part_number'] or 'No Number'}] (ID: {row['id']})"
        workspace_options.append(display_label)
        part_id_mapping[display_label] = row['id']
        
    selected_action = st.selectbox("Choose Operation Mode:", workspace_options, index=0)
    st.write("---")
    
    if selected_action == "➕ Register New Part (Fresh Entry)":
        st.markdown("### ✨ Register a New Part")
        with st.form("unified_add_form", clear_on_submit=True):
            new_name = st.text_input("Part Name", placeholder="e.g., Engine Oil Filter")
            new_number = st.text_input("Part Number / Model Serial (Optional)", placeholder="e.g., LF3806")
            new_stock = st.number_input("Current Stock On Hand", min_value=0, step=1, value=0)
            new_qty_buy = st.number_input("Initial Purchase Request Qty", min_value=0, step=1, value=0)
            
            if st.form_submit_button("💾 Save New Component Entry"):
                if not new_name.strip(): 
                    st.error("Part Name is a mandatory field.")
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('INSERT INTO inventory (part_name, part_number, current_stock, quantity_to_buy, in_basket) VALUES (?, ?, ?, ?, ?)', 
                                   (new_name.strip(), new_number.strip(), new_stock, new_qty_buy, 1 if new_qty_buy > 0 else 0))
                    conn.commit()
                    conn.close()
                    st.success(f"Successfully registered '{new_name.strip()}'.")
                    st.rerun()

    else:
        target_id = part_id_mapping[selected_action]
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT part_name, part_number, current_stock, quantity_to_buy FROM inventory WHERE id = ?", (target_id,))
        current_details = cursor.fetchone()
        conn.close()
        
        if current_details:
            st.markdown(f"### ✏️ Edit Component Configurations: *{current_details[0]}*")
            with st.form(f"unified_modify_form_{target_id}"):
                mod_name = st.text_input("Part Name", value=str(current_details[0]))
                mod_number = st.text_input("Part Number", value=str(current_details[1] if current_details[1] else ""))
                mod_stock = st.number_input("Current Stock", min_value=0, value=int(current_details[2]))
                mod_qty_buy = st.number_input("Quantity to Buy", min_value=0, value=int(current_details[3]))
                
                if st.form_submit_button("💾 Save Structural Variations"):
                    if not mod_name.strip():
                        st.error("Part Name cannot be completely empty.")
                    else:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute('UPDATE inventory SET part_name=?, part_number=?, current_stock=?, quantity_to_buy=?, in_basket=? WHERE id=?', 
                                       (mod_name.strip(), mod_number.strip(), mod_stock, mod_qty_buy, 1 if mod_qty_buy > 0 else 0, target_id))
                        conn.commit()
                        conn.close()
                        st.success("Item updated.")
                        st.rerun()

# ==========================================
# SHOPPING BASKET WORKSPACE (EMOJI LOCALISED)
# ==========================================
elif active_view == "🛒 Shopping Basket":
    st.subheader("Items to Procure")
    conn = get_db_connection()
    basket_df = pd.read_sql_query("SELECT id, part_name, part_number, current_stock, quantity_to_buy FROM inventory WHERE quantity_to_buy > 0", conn)
    conn.close()
    
    if basket_df.empty: 
        st.info("Shopping basket is empty.")
    else:
        for _, row in basket_df.iterrows():
            url = generate_procurement_url(row['part_name'], row['part_number'], selected_marketplace, selected_filter)
            basket_emoji = get_part_emoji(row['part_name'])
            with st.container():
                st.markdown(f"### {basket_emoji} {row['part_name']}")
                c_det, c_act = st.columns([3, 2])
                c_det.write(f"**Part Code:** `{row['part_number'] or 'N/A'}` | **Stock:** {row['current_stock']} | **Order Qty:** {row['quantity_to_buy']}")
                st.link_button(f"🛒 Search on {selected_marketplace}", url, use_container_width=True)
                if c_act.button(f"Mark Received", key=f"rec_{row['id']}", use_container_width=True):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('UPDATE inventory SET current_stock=?, quantity_to_buy=0 WHERE id=?', (row['current_stock'] + row['quantity_to_buy'], row['id']))
                    conn.commit(); conn.close()
                    st.rerun()

# ==========================================
# GEMINI AI SCANNER WORKSPACE
# ==========================================
elif active_view == "🤖 Gemini AI Scanner":
    st.subheader("Gemini Intelligent Import Engine")
    st.markdown("Drop a **picture, PDF file, text list,** or paste a **messy message** to auto-extract items.")
    
    if not HAS_GEMINI:
        st.error("Missing required AI modules. Check your requirements.txt deployment file profile.")
    
    key_col1, key_col2 = st.columns([3, 1])
    api_key = key_col1.text_input("🔑 Enter Gemini API Key", type="password", help="Input your authorization key from Google Studio")
    key_col2.markdown("<div style='padding-top:28px;'></div>", unsafe_allow_html=True)
    key_col2.link_button("🚀 Get Free Key", "https://aistudio.google.com/", use_container_width=True)
    
    st.write("---")
    
    input_type = st.radio("Choose Input Format:", ["📋 Paste Text / Chat Message", "📄 Upload File (Photo, PDF, or TXT)"], horizontal=True)
    
    ai_prompt = """
    You are an expert industrial inventory assistant. Analyze the input data and extract all physical spare parts or machine components mentioned.
    
    CRITICAL CONSTRAINT: Ignore any text that clearly belongs to the application user interface layout context itself. 
    Do NOT extract words like "Gemini AI Scanner", "Smart Stock", "View Inventory", "Shopping Basket", "Manage Parts Workspace", or button prompts.
    Only pull legitimate inventory parts listed inside invoices, lists, or log manifests.

    You MUST output a valid JSON array of objects and absolutely NOTHING else. Do not include markdown tags (no ```json).
    Each item object inside the array must exactly mirror this structure:
    [
      {
        "part_name": "Clean descriptive name in English (e.g., Hydraulic Seal Kit)",
        "part_number": "The specific alpha-numeric code/serial number if visible, otherwise pass empty string ''",
        "current_stock": integer (use the listed current/on-hand amount, or 0 if unmentioned),
        "quantity_to_buy": integer (use the listed order/purchase amount, or 0 if unmentioned)
      }
    ]
    """

    if input_type == "📋 Paste Text / Chat Message":
        user_text = st.text_area("Paste chaotic text or message columns below:", height=150)
        if st.button("✨ Scan Text Content", use_container_width=True) and HAS_GEMINI:
            if not api_key.strip():
                st.warning("Please type in your API Key first.")
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
        uploaded_file = st.file_uploader("Upload inventory photo, PDF invoice, or text manifest:", type=["jpg", "jpeg", "png", "pdf", "txt"])
        if uploaded_file:
            file_mime = uploaded_file.type
            
            if "image" in file_mime:
                st.image(uploaded_file, caption="Staged Visual Input Source", width=300)
            else:
                st.info(f"📄 Document Ready: `{uploaded_file.name}` ({file_mime})")
            
            if st.button("✨ Scan Document File Context", use_container_width=True) and HAS_GEMINI:
                if not api_key.strip():
                    st.warning("Please type in your API Key first.")
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
                                response = model.generate_content([
                                    ai_prompt,
                                    {"mime_type": "application/pdf", "data": pdf_bytes}
                                ])
                            else:
                                text_content = uploaded_file.read().decode("utf-8")
                                response = model.generate_content([ai_prompt, text_content])
                                
                            clean_json = response.text.replace("```json", "").replace("```", "").strip()
                            st.session_state.extracted_data = json.loads(clean_json)
                        except Exception as e:
                            st.error(f"Multi-modal scanning execution aborted: {str(e)}")

    # --- STRUCTURAL CONFIRMATION PANEL (Strictly routed within Gemini view block) ---
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
                        cursor.execute('''
                            UPDATE inventory 
                            SET quantity_to_buy = ?, in_basket = ? 
                            WHERE id = ?
                        ''', (new_total_buy, 1 if new_total_buy > 0 else 0, existing_part[0]))
                    else:
                        cursor.execute('''
                            INSERT INTO inventory (part_name, part_number, current_stock, quantity_to_buy, in_basket)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (p_name, p_num, c_stock, q_buy, 1 if q_buy > 0 else 0))
                    
                    saved_count += 1
                    
            conn.commit()
            conn.close()
            
            st.session_state.extracted_data = None
            st.success(f"Successfully processed {saved_count} items directly into active database storage!")
            st.rerun()