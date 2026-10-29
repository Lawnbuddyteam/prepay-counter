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
REVENUE_GOAL = 80000.0
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

def fetch_prepays_data(client):
    try:
        sheet = client.open(SHEET_NAME).worksheet("2027")
        raw_data = sheet.get_all_values()
        if len(raw_data) < 3: 
            return [], 0.0

        now_est = datetime.now(ZoneInfo("America/New_York"))
        if now_est.hour < 5:
            report_date = (now_est - timedelta(days=1)).date()
        else:
            report_date = now_est.date()

        dates_row = raw_data[0]
        daily_records = []
        total_season_revenue = 0.0
        current_date_in_loop = None
        
        for col_idx in range(0, len(dates_row), 2):
            date_val = dates_row[col_idx].strip()
            
            if date_val:
                current_date_in_loop = date_val
                
            try:
                col_date = pd.to_datetime(current_date_in_loop).date()
            except:
                col_date = None
                
            # Scan through rows to collect both daily and seasonal totals
            for row_idx in range(2, len(raw_data)):
                row = raw_data[row_idx]
                
                name = row[col_idx].strip() if col_idx < len(row) else ""
                amount_str = row[col_idx+1].strip() if col_idx+1 < len(row) else ""
                
                if name:
                    clean_amount = amount_str.replace('$', '').replace(',', '').strip()
                    try:
                        amt_float = float(clean_amount)
                    except ValueError:
                        amt_float = 0.0
                        
                    # Add to seasonal total unconditionally
                    total_season_revenue += amt_float
                        
                    # Add to daily display only if it matches today's date
                    if col_date == report_date:
                        daily_records.append({
                            "Name": name, 
                            "Amount": amt_float, 
                            "AmountStr": amount_str
                        })
                        
        return daily_records, total_season_revenue
    except Exception as e:
        st.error(f"Data Fetch Error: {e}")
        return [], 0.0

# --- 4. LIVE DASHBOARD RENDERING ---
now_est = datetime.now(ZoneInfo("America/New_York"))
refresh_rate = 120 if 6 <= now_est.hour < 20 else 3600 

@st.fragment(run_every=refresh_rate)
def render_dashboard():
    client = get_gspread_client()
    if not client:
        st.warning("⚠️ Waiting for Google Sheets connection...")
        return

    records, total_season_revenue = fetch_prepays_data(client)
    
    total_count = len(records)
    total_daily_revenue = sum(r["Amount"] for r in records)
    
    # --- TOP ROW: DAILY METRICS ---
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<p style="font-size:3.5vw; text-align:center; color:#5D9CEC; font-weight:bold; margin-bottom: 0;">TOTAL DAILY COUNT</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="font-size:12vw; text-align:center; color:white; font-weight:900; line-height:1.0; margin: 0;">{total_count}</p>', unsafe_allow_html=True)
        
        progress_count = min(total_count / COUNT_GOAL, 1.0)
        st.progress(progress_count)
        st.markdown(f"<p style='text-align:center; color:#39FF14; font-size:2vw; font-weight:bold; margin-top: 1vw;'>Goal Progress: {total_count} / {COUNT_GOAL}</p>", unsafe_allow_html=True)
        
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
