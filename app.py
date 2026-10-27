import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import os

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Prepay Dashboard", initial_sidebar_state="collapsed")

SHEET_NAME = "Prepay Customers" # Update this to your actual spreadsheet name if different
GCP_CREDS = os.environ.get('gcp_service_account') or os.environ.get('GCP_SERVICE_ACCOUNT')

# --- 2. IPAD-OPTIMIZED CSS ---
st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 0rem !important;
            max-width: 98% !important;
        }
        header {visibility: hidden;}
        footer {visibility: hidden;}
        
        .metric-title { font-size: 3vw; text-align: center; color: #5D9CEC; font-weight: bold; margin-bottom: -1vw; }
        .metric-value { font-size: 15vw; text-align: center; color: white; font-weight: 900; line-height: 1; margin: 0; }
        .revenue-value { color: #39FF14; } /* Neon green for revenue */
        
        .client-card {
            background-color: rgba(255, 255, 255, 0.05);
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 10px;
            border-left: 4px solid #5D9CEC;
        }
        .client-name { font-size: 1.2vw; color: white; font-weight: bold; margin: 0;}
        .client-amount { font-size: 1.2vw; color: #39FF14; margin: 0;}
    </style>
""", unsafe_allow_html=True)

# --- 3. CORE FUNCTIONS ---
@st.cache_resource(ttl=1800)
def get_gspread_client():
    if not GCP_CREDS: return None
    try:
        info = json.loads(GCP_CREDS)
        if 'private_key' in info:
            info['private_key'] = info['private_key'].replace('\\n', '\n')
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            info, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Auth Error: {e}")
        return None

def fetch_daily_prepays(client):
    try:
        sheet = client.open(SHEET_NAME).sheet1
        raw_data = sheet.get_all_values()
        if len(raw_data) < 3: 
            return []

        # Determine "Business Date" (Switches over at 5 AM EST)
        now_est = datetime.now(ZoneInfo("America/New_York"))
        if now_est.hour < 5:
            report_date = (now_est - timedelta(days=1)).date()
        else:
            report_date = now_est.date()

        dates_row = raw_data[0]
        daily_records = []
        current_date_in_loop = None
        
        # Scan through columns (stepping by 2 for Name/Amount pairs)
        for col_idx in range(0, len(dates_row), 2):
            date_val = dates_row[col_idx].strip()
            
            # Carry over the date if the header is merged across multiple Name/Amount blocks
            if date_val:
                current_date_in_loop = date_val
                
            try:
                # Convert sheet date string to a comparable date object
                col_date = pd.to_datetime(current_date_in_loop).date()
            except:
                continue
                
            # If this column matches today's reporting date, parse rows 3 downwards (index 2+)
            if col_date == report_date:
                for row_idx in range(2, len(raw_data)):
                    row = raw_data[row_idx]
                    
                    name = row[col_idx].strip() if col_idx < len(row) else ""
                    amount_str = row[col_idx+1].strip() if col_idx+1 < len(row) else ""
                    
                    if name:
                        # Clean the dollar amount string to convert it to a float for math
                        clean_amount = amount_str.replace('$', '').replace(',', '').strip()
                        try:
                            amt_float = float(clean_amount)
                        except ValueError:
                            amt_float = 0.0
                            
                        daily_records.append({
                            "Name": name, 
                            "Amount": amt_float, 
                            "AmountStr": amount_str
                        })
                        
        return daily_records
    except Exception as e:
        st.error(f"Data Fetch Error: {e}")
        return []

# --- 4. LIVE DASHBOARD RENDERING ---
now_est = datetime.now(ZoneInfo("America/New_York"))
# Update every 2 mins (120s) between 6 AM and 8 PM, otherwise check once an hour (3600s)
refresh_rate = 120 if 6 <= now_est.hour < 20 else 3600 

@st.fragment(run_every=refresh_rate)
def render_dashboard():
    client = get_gspread_client()
    if not client:
        st.warning("⚠️ Waiting for Google Sheets connection...")
        return

    records = fetch_daily_prepays(client)
    
    total_count = len(records)
    total_revenue = sum(r["Amount"] for r in records)
    
    # --- BIG NUMBER METRICS ---
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<p class="metric-title">TOTAL DAILY COUNT</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="metric-value">{total_count}</p>', unsafe_allow_html=True)
    with col2:
        st.markdown('<p class="metric-title">TOTAL DAILY REVENUE</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="metric-value revenue-value">${total_revenue:,.2f}</p>', unsafe_allow_html=True)
        
    sync_time = datetime.now(ZoneInfo("America/New_York")).strftime('%I:%M %p')
    st.markdown(f'<p style="text-align:center; color:#666; font-size:1vw; margin-top: -2vw;">Last Update: {sync_time} EST</p>', unsafe_allow_html=True)

    st.divider()

    # --- CLIENT LIST (4 COLUMNS) ---
    # We display them in 4 columns so hundreds of names fit nicely on the screen
    if total_count > 0:
        cols = st.columns(4)
        for i, record in enumerate(records):
            # Calculate which column to place this record in (goes left to right, then down)
            target_col = cols[i % 4]
            
            # Fallback to the raw string if the float conversion failed (e.g., they typed "TBD")
            display_amt = f"${record['Amount']:,.2f}" if record['Amount'] > 0 else record['AmountStr']
            
            with target_col:
                st.markdown(f"""
                    <div class="client-card">
                        <p class="client-name">{record['Name']}</p>
                        <p class="client-amount">{display_amt}</p>
                    </div>
                """, unsafe_allow_html=True)
    else:
        st.markdown("<h3 style='text-align: center; color: #888;'>No prepays logged for today yet.</h3>", unsafe_allow_html=True)

# Start the app
render_dashboard()
