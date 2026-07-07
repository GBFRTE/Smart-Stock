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

# --- DATABASE ENGINE SETUP ---
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
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    return sqlite3.connect('inventory_v2.db')

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

# --- SIDEBAR: AT-A-GLANCE SUMMARY & ADAPTIVE COLOR INDICATOR ---
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*), SUM(current_stock), COUNT(CASE WHEN quantity_to_buy > 0 THEN 1 END) FROM inventory")
db_summary = cursor.fetchone()
conn.close()

sb_total_types = db_summary[0] if db_summary[0] else 0
sb_total_units = db_summary[1] if db_summary[1] else 0
sb_needs_purchase = db_summary[2] if db_summary[2] else 0
sb_healthy_parts = sb_total_types - sb_needs_purchase

st.sidebar.header("📈 Stock Status Glance")

# Dynamic HTML Indicator Box Setup
if sb_needs_purchase == 0:
    status_color = "#198754"  # Vibrant Green
    status_text = f"🟢 SYSTEM HEALTHY<br><span style='font-size:13px;'>All {sb_total_types} components are fully stocked.</span>"
elif sb_needs_purchase <= 3:
    status_color = "#ffc107"  # Warning Amber
    status_text = f"🟡 WARNING DELAYS<br><span style='font-size:13px;'>{sb_needs_purchase} items pending procurement buy lines.</span>"
else:
    status_color = "#dc3545"  # Critical Red
    status_text = f"🔴 CRITICAL BACKLOG<br><span style='font-size:13px;'>Lots of due orders! {sb_needs_purchase} items need immediate buying.</span>"

# Inject the styled visual tracking widget
st.sidebar.markdown(
    f"""
    <div style="background-color: {status_color}; padding: 14px; border-radius: 8px; color: {'#000000' if status_color=='#ffc107' else '#ffffff'}; font-weight: bold; margin-bottom: 15px; text-align: center; box-shadow: 1px 1px 5px rgba(0,0,0,0.15);">
        {status_text}
    </div>
    """, 
    unsafe_allow_html=True
)

# Render organized layout breakdowns
sb_col1, sb_col2 = st.sidebar.columns(2)
sb_col1.metric("Unique Parts", sb_total_types)
sb_col2.metric("Total On Hand", sb_total_units)

sb_col3, sb_col4 = st.sidebar.columns(2)
sb_col3.metric("Healthy Lines", sb_healthy_parts)
sb_col4.metric("Procurement Due", sb_needs_purchase, delta=f"+{sb_needs_purchase}" if sb_needs_purchase > 0 else None, delta_color="inverse")

st.sidebar.write("---")

st.sidebar.header("🇮🇩 Marketplace Settings")
selected_marketplace = st.sidebar.selectbox("Select Platform", ["Tokopedia", "Shopee", "Lazada"], index=0)
selected_filter = st.sidebar.selectbox("Apply Filter / Sorting", ["Default", "Cheapest", "Most Sold", "Trusted"], index=0)

# --- MAIN INTERFACE NAVIGATION ---
tab_view, tab_add, tab_modify, tab_basket, tab_gemini = st.tabs([
    "🔍 View Inventory", 
    "➕ Add Part", 
    "✏️ Modify Part", 
    "🛒 Shopping Basket",
    "🤖 Gemini AI Scanner"
])

# ==========================================
# TAB 1: VIEW INVENTORY
# ==========================================
with tab_view:
    st.subheader("Current Stock Status")
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT id, part_name AS [Part Name], part_number AS [Part Number], current_stock AS [Current Stock], quantity_to_buy AS [Quantity to Buy] FROM inventory", conn)
    conn.close()
    
    if df.empty:
        st.info("Inventory database is empty.")
    else:
        st.dataframe(df[["Part Name", "Part Number", "Current Stock", "Quantity to Buy"]], use_container_width=True)

# ==========================================
# TAB 2: ADD PART
# ==========================================
with tab_add:
    st.subheader("Register a New Part")
    with st.form("add_part_form", clear_on_submit=True):
        new_name = st.text_input("Part Name")
        new_number = st.text_input("Part Number (Optional)")
        new_stock = st.number_input("Current Stock", min_value=0, step=1)
        new_qty_buy = st.number_input("Quantity to Buy", min_value=0, step=1)
        if st.form_submit_button("Save Part"):
            if not new_name.strip(): st.error("Part Name is required.")
            else:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('INSERT INTO inventory (part_name, part_number, current_stock, quantity_to_buy, in_basket) VALUES (?, ?, ?, ?, ?)', 
                               (new_name.strip(), new_number.strip(), new_stock, new_qty_buy, 1 if new_qty_buy > 0 else 0))
                conn.commit(); conn.close()
                st.success(f"Added {new_name}")
                st.rerun()

# ==========================================
# TAB 3: MODIFY PART (BUG-FIXED)
# ==========================================
with tab_modify:
    st.subheader("Update Existing Part Details")
    conn = get_db_connection()
    parts_df = pd.read_sql_query("SELECT id, part_name, part_number FROM inventory", conn)
    conn.close()
    
    if parts_df.empty:
        st.info("No items found in your active inventory data to modify.")
    else:
        # BUG FIX: Formatted options with ID index trackers to avoid collisions on duplicate names
        part_options = {f"{row['part_name']} [{row['part_number'] or 'No Number'}] (ID: {row['id']})": row['id'] for _, row in parts_df.iterrows()}
        selected_label = st.selectbox("Select Part to Update", list(part_options.keys()))
        selected_id = part_options[selected_label]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT part_name, part_number, current_stock, quantity_to_buy FROM inventory WHERE id = ?", (selected_id,))
        current_details = cursor.fetchone()
        conn.close()
        
        if current_details:
            # BUG FIX: Key form uniquely to the specific component ID to prevent layout bleeding on select box changes
            with st.form(f"modify_part_form_{selected_id}"):
                mod_name = st.text_input("Part Name", value=str(current_details[0]))
                mod_number = st.text_input("Part Number", value=str(current_details[1] if current_details[1] else ""))
                mod_stock = st.number_input("Current Stock", min_value=0, value=int(current_details[2]))
                mod_qty_buy = st.number_input("Quantity to Buy", min_value=0, value=int(current_details[3]))
                
                if st.form_submit_button("Update Part Details"):
                    if not mod_name.strip():
                        st.error("Part Name cannot be completely empty.")
                    else:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute('UPDATE inventory SET part_name=?, part_number=?, current_stock=?, quantity_to_buy=?, in_basket=? WHERE id=?', 
                                       (mod_name.strip(), mod_number.strip(), mod_stock, mod_qty_buy, 1 if mod_qty_buy > 0 else 0, selected_id))
                        conn.commit(); conn.close()
                        st.success("Item layout updated successfully.")
                        st.rerun()

# ==========================================
# TAB 4: SHOPPING BASKET
# ==========================================
with tab_basket:
    st.subheader("Items to Procure")
    conn = get_db_connection()
    basket_df = pd.read_sql_query("SELECT id, part_name, part_number, current_stock, quantity_to_buy FROM inventory WHERE quantity_to_buy > 0", conn)
    conn.close()
    
    if basket_df.empty: st.info("Shopping basket is empty.")
    else:
        for _, row in basket_df.iterrows():
            url = generate_procurement_url(row['part_name'], row['part_number'], selected_marketplace, selected_filter)
            with st.container():
                st.markdown(f"### 📦 {row['part_name']}")
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
# TAB 5: 🤖 GEMINI INTELLIGENT AI SCANNER
# ==========================================
with tab_gemini:
    st.subheader("🤖 Gemini Intelligent Import Engine")
    st.markdown("Drop a **picture** or paste a **messy message** to auto-extract your items.")
    
    if not HAS_GEMINI:
        st.error("Missing required AI modules. Check your requirements.txt deployment file profile.")
        
    api_key = st.text_input("🔑 Enter Gemini API Key", type="password", help="Get a free key from Google AI Studio")
    st.write("---")
    
    input_type = st.radio("Choose Input Format:", ["📋 Paste Text/Chat Message", "📸 Upload/Snap a Picture"], horizontal=True)
    
    ai_prompt = """
    You are an expert industrial inventory assistant. Analyze the input data and extract all spare parts or machine components mentioned.
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

    if input_type == "📋 Paste Text/Chat Message":
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
        uploaded_pic = st.file_uploader("Upload inventory photo or document capture:", type=["jpg", "jpeg", "png"])
        if uploaded_pic:
            st.image(uploaded_pic, caption="Staged Visual Input Source", width=300)
            
            if st.button("✨ Scan Picture Pixels", use_container_width=True) and HAS_GEMINI:
                if not api_key.strip():
                    st.warning("Please type in your API Key first.")
                else:
                    with st.spinner("Gemini Vision processing image matrices..."):
                        try:
                            img = PIL.Image.open(uploaded_pic)
                            genai.configure(api_key=api_key.strip())
                            model = genai.GenerativeModel('gemini-2.5-flash')
                            response = model.generate_content([ai_prompt, img])
                            clean_json = response.text.replace("```json", "").replace("```", "").strip()
                            st.session_state.extracted_data = json.loads(clean_json)
                        except Exception as e:
                            st.error(f"Vision parsing execution aborted: {str(e)}")

    # --- STRUCTURAL CONFIRMATION PANEL ---
    if st.session_state.extracted_data:
        st.write("---")
        st.success("🎉 Gemini extracted matching items perfectly! Review the data layout before saving:")
        
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
                    cursor.execute('''
                        INSERT INTO inventory (part_name, part_number, current_stock, quantity_to_buy, in_basket)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (p_name, p_num, c_stock, q_buy, 1 if q_buy > 0 else 0))
                    saved_count += 1
                    
            conn.commit()
            conn.close()
            
            st.session_state.extracted_data = None
            st.success(f"Successfully integrated {saved_count} items directly into your active inventory records!")
            st.rerun()