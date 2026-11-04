import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Prepay Dashboard", initial_sidebar_state="collapsed")

SHEET_NAME = "Prepay Customers" 
COUNT_GOAL = 93
REVENUE_GOAL = 91000.0
SEASON_GOAL = 2000000.0

GCP_CREDS = st.secrets.get("GCP_SERVICE_ACCOUNT")

# --- 2. IPAD-OPTIMIZED CSS ---
st.markdown("""
    <style>
        /* Force Black Background */
        .stApp {
            background-color: #000000;
        }
        
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 0rem !important;
            max-width: 98% !important;
        }
        header {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Progress Bar Neon Color */
        .stProgress > div > div > div > div {
            background-color: #39FF14;
            box-shadow: 0 0 15px #39FF14;
            height: 30px;
            border-radius: 10px;
        }
        
        /* Client List Styling */
        .client-card {
            background-color: rgba(255, 255, 255, 0.1);
            padding: 1vw;
            border-radius: 8px;
            margin-bottom: 1vw;
            border-left: 4px solid #39FF14;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. CORE FUNCTIONS ---
@st.cache_resource(ttl=1800)
def get_gspread_client():
    if not GCP_CREDS: return None
    try:
        if isinstance(GCP_CREDS, str):
            info = json.loads(GCP_CREDS)
        else:
            info = dict(GCP_CREDS)
            
        if 'private_key' in info:
            info['private_key'] = info['private_key'].replace('\\n', '\n')
            
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            info, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Auth Error: {e}")
        return None

# The underscore in _client tells Streamlit not to hash the gspread connection
@st.cache_data(ttl=120)
def fetch_prepays_data(_client):
    try:
        sheet = _client.open(SHEET_NAME).worksheet("2027")
        
        # Download rows 1 through 43
        raw_data = sheet.get("A1:ZZ43") 
        
        if len(raw_data) < 3: 
            return [], 0.0, 0

        # --- 5 AM EST RESET LOGIC ---
        now_est = datetime.now(ZoneInfo("America/New_York"))
        if now_est.hour < 5:
            report_date = (now_est - timedelta(days=1)).date()
        else:
            report_date = now_est.date()

        dates_row = raw_data[0]
        daily_records = []
        total_season_count = 0
        
        # --- 1. TOTAL SEASON REVENUE (Summing Row 43) ---
        total_season_revenue = 0.0
        if len(raw_data) >= 43:
            row_43 = raw_data[42]
            for cell in row_43:
                clean_cell = str(cell).replace('$', '').replace(',', '').strip()
                try:
                    val = float(clean_cell)
                    if val > 0:
                        total_season_revenue += val
                except ValueError:
                    pass
        
        # --- 2. DAILY METRICS & SEASON COUNT (Rows 3-42) ---
        max_cols = max(len(row) for row in raw_data)
        
        for col_idx in range(0, max_cols, 2):
            # Strictly use the explicit date written in this column's row 1
            date_str = dates_row[col_idx].strip() if col_idx < len(dates_row) else ""
            
            try:
                col_date = pd.to_datetime(date_str).date()
            except Exception:
                col_date = None
                
            max_row = min(42, len(raw_data))
            
            # Loop exactly Rows 3 through 42 (Indices 2 through 41)
            for row_idx in range(2, max_row):
                row = raw_data[row_idx]
                
                name = row[col_idx].strip() if col_idx < len(row) else ""
                amount_str = row[col_idx+1].strip() if col_idx+1 < len(row) else ""
                
                clean_amount = amount_str.replace('$', '').replace(',', '').strip()
                try:
                    amt_float = float(clean_amount)
                except ValueError:
                    amt_float = 0.0
                    
                # Increment total season count for valid client entries across ALL days
                if name and amt_float > 0:
                    total_season_count += 1
                    
                # Add to daily display ONLY if this specific column matches today's date
                if name and amt_float > 0 and col_date == report_date:
                    daily_records.append({
                        "Name": name, 
                        "Amount": amt_float, 
                        "AmountStr": amount_str
                    })
                        
        return daily_records, total_season_revenue, total_season_count
    except Exception as e:
        st.error(f"Data Fetch Error: {e}")
        return [], 0.0, 0

# --- 4. LIVE DASHBOARD RENDERING ---
now_est = datetime.now(ZoneInfo("America/New_York"))
# Set a consistent 120-second (2 minute) refresh rate so it catches the 5 AM rollover quickly
refresh_rate = 120 

@st.fragment(run_every=refresh_rate)
def render_dashboard():
    client = get_gspread_client()
    if not client:
        st.warning("⚠️ Waiting for Google Sheets connection...")
        return

    records, total_season_revenue, total_season_count = fetch_prepays_data(client)
    
    total_count = len(records)
    total_daily_revenue = sum(r["Amount"] for r in records)
    prepay_client_pct = round((total_season_count / 8450) * 100)
    
    # --- TOP ROW: DAILY METRICS ---
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<p style="font-size:3.5vw; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom: 0;">TOTAL DAILY COUNT</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="font-size:12vw; text-align:center; color:white; font-weight:900; line-height:1.0; margin: 0;">{total_count}</p>', unsafe_allow_html=True)
        
        progress_count = min(total_count / COUNT_GOAL, 1.0)
        st.progress(progress_count)
        st.markdown(f"<p style='text-align:center; color:#39FF14; font-size:2vw; font-weight:bold; margin-top: 1vw;'>Goal Progress: {total_count} / {COUNT_GOAL}</p>", unsafe_allow_html=True)
        # Added Season Count and Prepay Client %
        st.markdown(f"<p style='text-align:center; color:#888888; font-size:1.6vw; font-weight:bold; margin-top: 0.5vw;'>Season Count: {total_season_count} &nbsp;|&nbsp; Prepay Client % of Total Clients: {prepay_client_pct}%</p>", unsafe_allow_html=True)
        
    with col2:
        st.markdown('<p style="font-size:3.5vw; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom: 0;">TOTAL DAILY REVENUE</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="font-size:10vw; text-align:center; color:white; font-weight:900; line-height:1.2; margin: 0;">${total_daily_revenue:,.0f}</p>', unsafe_allow_html=True)
        
        progress_rev = min(total_daily_revenue / REVENUE_GOAL, 1.0)
        st.progress(progress_rev)
        st.markdown(f"<p style='text-align:center; color:#39FF14; font-size:2vw; font-weight:bold; margin-top: 1vw;'>Goal Progress: ${total_daily_revenue:,.0f} / ${REVENUE_GOAL:,.0f}</p>", unsafe_allow_html=True)
        
    sync_time = datetime.now(ZoneInfo("America/New_York")).strftime('%I:%M %p')
    st.markdown(f'<p style="text-align:center; color:#888888; font-size:1.5vw; margin-top: 2vw;">Last Update: {sync_time} EST</p>', unsafe_allow_html=True)

    # --- MIDDLE ROW: TOTAL SEASONAL REVENUE ---
    st.markdown('<p style="font-size:2.5vw; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom: 0; margin-top: 3vw;">TOTAL SEASON REVENUE</p>', unsafe_allow_html=True)
    st.markdown(f'<p style="font-size:6vw; text-align:center; color:white; font-weight:900; line-height:1.0; margin: 0;">${total_season_revenue:,.0f}</p>', unsafe_allow_html=True)
    
    progress_season = min(total_season_revenue / SEASON_GOAL, 1.0)
    st.progress(progress_season)
    st.markdown(f"<p style='text-align:center; color:#39FF14; font-size:1.5vw; font-weight:bold; margin-top: 1vw;'>Goal Progress: ${total_season_revenue:,.0f} / ${SEASON_GOAL:,.0f}</p>", unsafe_allow_html=True)

    st.divider()

    # --- BOTTOM ROW: CLIENT LIST (4 COLUMNS) ---
    if total_count > 0:
        cols = st.columns(4)
        for i, record in enumerate(records):
            target_col = cols[i % 4]
            display_amt = f"${record['Amount']:,.2f}" if record['Amount'] > 0 else record['AmountStr']
            
            with target_col:
                st.markdown(f"""
                    <div class="client-card">
                        <p style="font-size: 1.5vw; color: white; font-weight: bold; margin: 0;">{record['Name']}</p>
                        <p style="font-size: 1.5vw; color: #39FF14; margin: 0;">{display_amt}</p>
                    </div>
                """, unsafe_allow_html=True)
    else:
        st.markdown("<h3 style='text-align: center; color: #888; font-size: 2.5vw;'>No prepays logged for today yet.</h3>", unsafe_allow_html=True)

render_dashboard()
