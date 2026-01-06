import streamlit as st
import requests
import pandas as pd
import datetime
import altair as alt
from PIL import Image

# --- PAGE SETUP ---
st.set_page_config(page_title="Quickplay Stability", layout="wide", page_icon="🔥")

# --- CUSTOM CSS (REMAINS THE SAME) ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    #MainMenu, header, footer { visibility: hidden !important; }
    section[data-testid="stSidebar"] { background-color: #161B22; border-right: 1px solid #30363D; }
    div[data-testid="stMetric"] { background-color: #161B22; border: 1px solid #30363D; padding: 20px; border-radius: 10px; }
    div[data-testid="stMetricLabel"] { color: #8B949E; font-size: 14px; }
    div[data-testid="stMetricValue"] { color: #FFFFFF; font-size: 28px; font-weight: 700; }
    .stProgress > div > div > div > div { background-image: linear-gradient(90deg, #FF9F1C, #FF6B6B); }
    div[data-testid="stDataFrame"] { border: 1px solid #30363D; border-radius: 8px; }
    h1, h2, h3 { color: #FAFAFA !important; font-family: 'Inter', sans-serif; }
</style>
""", unsafe_allow_html=True)

# --- 1. CLIENT CONFIGURATION ---
try:
    CLIENTS = st.secrets["clients"]
except Exception:
    st.error("Secrets not configured! Check your .streamlit/secrets.toml.")
    CLIENTS = {}

ENDPOINT = "https://api.newrelic.com/graphql"

# --- 2. SIDEBAR CONTROLS (AUTO-UPDATE MODE) ---
with st.sidebar:
    st.markdown("### Selection")
    customer_keys = list(CLIENTS.keys())
    customer_options = ["All Customers"] + customer_keys if customer_keys else ["No Clients Configured"]
    
    # 1. Default: "All Customers" (index 0)
    selected_view = st.selectbox("Select Customer", customer_options, index=0)

    st.write("") 

    st.markdown("### Status")
    # 2. Default: "All" (index 0)
    status_filter = st.radio("Status Filter", ["All", "Active", "Closed"], horizontal=True, label_visibility="collapsed", index=0)

    st.write("") 

    st.markdown("### Time Range")
    time_ranges = {
        "Last 60 Minutes": "SINCE 60 minutes ago",
        "Last 6 Hours": "SINCE 6 hours ago",
        "Last 24 Hours": "SINCE 24 hours ago",
        "Last 7 Days": "SINCE 7 days ago",
        "Last 30 Days": "SINCE 30 days ago"
    }
    time_options = list(time_ranges.keys()) + ["Custom Date Range"]
    
    # 3. Default: "Last 6 Hours" (index 1)
    selected_time_label = st.selectbox("Time Frame", time_options, label_visibility="collapsed", index=1)

    if selected_time_label == "Custom Date Range":
        col_d1, col_d2 = st.columns(2)
        start_date = col_d1.date_input("Start", datetime.date.today() - datetime.timedelta(days=1))
        end_date = col_d2.date_input("End", datetime.date.today())
        time_clause = f"SINCE '{start_date} 00:00:00' UNTIL '{end_date} 23:59:59'"
    else:
        time_clause = time_ranges[selected_time_label]

# --- 4. DATA FETCHING HELPERS ---
def categorize_alert(row):
    text = (str(row['policyName']) + " " + str(row['conditionName'])).lower()
    infra_keywords = ['cpu', 'memory', 'disk', 'storage', 'network', 'host', 'server', 'latency', 'k8s', 'db', 'gcp']
    return 'Infra' if any(k in text for k in infra_keywords) else 'SOC'

def format_duration(td):
    ts = int(td.total_seconds())
    if ts < 60: return f"{ts}s"
    m, s = divmod(ts, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h > 0 else f"{m}m {s}s"

def style_status_column(val):
    if val == 'Active': return 'color: #FF5252; font-weight: 800;'
    if val == 'Closed': return 'color: #69F0AE; font-weight: 700;'
    return ''

@st.cache_data(ttl=60, show_spinner=False) # Lowered TTL to 60s for "Real-time" feel
def fetch_data(client_name, api_key, account_id, time_filter):
    query = f"""
    {{ actor {{ account(id: {account_id}) {{ nrql(query: "SELECT timestamp, policyName, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open', 'close') {time_filter} LIMIT MAX") {{ results }} }} }} }}
    """
    headers = {"API-Key": api_key, "Content-Type": "application/json"}
    try:
        response = requests.post(ENDPOINT, json={"query": query}, headers=headers)
        if response.status_code == 200:
            data = response.json().get('data', {}).get('actor', {}).get('account', {}).get('nrql', {}).get('results', [])
            df = pd.DataFrame(data)
            if not df.empty:
                df['Customer'] = client_name
                df.rename(columns={'entity.name': 'Entity'}, inplace=True) if 'entity.name' in df.columns else None
                return df
    except: pass
    return pd.DataFrame()

# --- 5. AUTOMATIC EXECUTION (NO BUTTON NEEDED) ---
all_data = []
targets = CLIENTS.items() if selected_view == "All Customers" else [(selected_view, CLIENTS[selected_view])]

for name, creds in targets:
    df_client = fetch_data(name, creds['api_key'], creds['account_id'], time_clause)
    if not df_client.empty: all_data.append(df_client)

# Process Data
if all_data:
    raw_df = pd.concat(all_data, ignore_index=True)
    raw_df['timestamp'] = pd.to_datetime(raw_df['timestamp'], unit='ms')
    
    grouped = raw_df.groupby(['incidentId', 'Customer', 'policyName', 'conditionName', 'priority']).agg(
        start_time=('timestamp', 'min'), end_time=('timestamp', 'max'), event_count=('event', 'nunique'),
        Entity=('Entity', 'first') if 'Entity' in raw_df.columns else ('incidentId', 'first')
    ).reset_index()

    grouped['Status'] = grouped['event_count'].apply(lambda x: 'Active' if x == 1 else 'Closed')
    grouped['Duration'] = grouped.apply(lambda x: format_duration((datetime.datetime.now() - x['start_time']) if x['Status'] == 'Active' else (x['end_time'] - x['start_time'])), axis=1)
    grouped['Category'] = grouped.apply(categorize_alert, axis=1)
    
    if status_filter == "Active": df_main = grouped[grouped['Status'] == 'Active']
    elif status_filter == "Closed": df_main = grouped[grouped['Status'] == 'Closed']
    else: df_main = grouped
    
    df_main = df_main.sort_values(by='start_time', ascending=False)
else:
    df_main = pd.DataFrame()

# --- 6. DISPLAY RENDER (SAME AS BEFORE) ---
try:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2: st.image("logo.png", use_container_width=True)
except:
    st.markdown("<h1 style='text-align: center; color: #FF9F1C; font-size: 80px;'>🔥 Quickplay</h1>", unsafe_allow_html=True)

st.markdown("<h2 style='text-align: center; margin-top: -10px; opacity: 0.8;'>Alerts Overview</h2>", unsafe_allow_html=True)
st.divider()

if df_main.empty:
    st.success("No incidents found. Systems are stable! 🎉")
else:
    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Incidents", len(df_main))
    m2.metric("🔥 Active Now", len(df_main[df_main['Status'] == 'Active']))
    m3.metric("🏗️ Infra Alerts", len(df_main[df_main['Category'] == 'Infra']))
    m4.metric("🛡️ SOC Alerts", len(df_main[df_main['Category'] == 'SOC']))

    # Chart, Tables, and Tabs follow below... (Same as previous code)
    # [Insert your existing Chart and Log logic here using 'df_main']
