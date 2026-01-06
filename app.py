import streamlit as st
import requests
import pandas as pd
import datetime
import altair as alt

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Quickplay Stability", 
    layout="wide", 
    page_icon="🔥",
    initial_sidebar_state="expanded" 
)

# --- CUSTOM CSS (Branding & Locked Sidebar) ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    
    /* HIDE SIDEBAR TOGGLE BUTTON (>>) */
    button[data-testid="sidebar-toggle"] { display: none !important; }
    
    /* HIDE STREAMLIT UI ELEMENTS */
    #MainMenu, header, footer { visibility: hidden !important; }
    
    /* SIDEBAR STYLING */
    section[data-testid="stSidebar"] {
        background-color: #161B22; 
        border-right: 1px solid #30363D;
        min-width: 320px !important;
    }

    /* METRIC CARDS */
    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        padding: 20px;
        border-radius: 10px;
    }
    
    h1, h2, h3 { color: #FAFAFA !important; font-family: 'Inter', sans-serif; }
</style>
""", unsafe_allow_html=True)

# --- 1. CONFIGURATION ---
try:
    CLIENTS = st.secrets["clients"]
except:
    st.error("Secrets not configured.")
    CLIENTS = {}

ENDPOINT = "https://api.newrelic.com/graphql"

# --- 2. SIDEBAR (DEFAULT VALUES SET HERE) ---
with st.sidebar:
    st.markdown("<h2 style='color: #FF9F1C;'>Quickplay Ops</h2>", unsafe_allow_html=True)
    st.divider()
    
    # DEFAULT: All Customers (index 0)
    customer_keys = list(CLIENTS.keys())
    customer_options = ["All Customers"] + customer_keys if customer_keys else ["No Clients"]
    selected_view = st.selectbox("Select Customer", customer_options, index=0)

    # DEFAULT: All Status (index 0)
    st.markdown("### Status")
    status_filter = st.radio("Status Filter", ["All", "Active", "Closed"], index=0, horizontal=True)

    # DEFAULT: Last 6 Hours (index 1)
    st.markdown("### Time Range")
    time_ranges = {
        "Last 60 Minutes": "SINCE 60 minutes ago",
        "Last 6 Hours": "SINCE 6 hours ago",
        "Last 24 Hours": "SINCE 24 hours ago",
        "Last 7 Days": "SINCE 7 days ago"
    }
    time_options = list(time_ranges.keys())
    selected_time_label = st.selectbox("Time Frame", time_options, index=1)
    time_clause = time_ranges[selected_time_label]

# --- 3. HELPER FUNCTIONS ---
def categorize_alert(row):
    text = (str(row['policyName']) + " " + str(row['conditionName'])).lower()
    infra_keywords = ['cpu', 'memory', 'disk', 'network', 'host', 'server', 'latency', 'k8s', 'db', 'gcp']
    return 'Infra' if any(k in text for k in infra_keywords) else 'SOC'

def format_duration(td):
    ts = int(td.total_seconds())
    if ts < 60: return f"{ts}s"
    m, s = divmod(ts, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h > 0 else f"{m}m {s}s"

@st.cache_data(ttl=60)
def fetch_data(name, api_key, account_id, time_filter):
    query = f"""
    {{ actor {{ account(id: {account_id}) {{ nrql(query: "SELECT timestamp, policyName, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open', 'close') {time_filter} LIMIT MAX") {{ results }} }} }} }}
    """
    headers = {"API-Key": api_key, "Content-Type": "application/json"}
    try:
        r = requests.post(ENDPOINT, json={"query": query}, headers=headers)
        if r.status_code == 200:
            df = pd.DataFrame(r.json()['data']['actor']['account']['nrql']['results'])
            if not df.empty:
                df['Customer'] = name
                return df
    except: pass
    return pd.DataFrame()

# --- 4. DATA PROCESSING (AUTO-RUNS) ---
all_df_list = []
targets = CLIENTS.items() if selected_view == "All Customers" else [(selected_view, CLIENTS[selected_view])]

for name, creds in targets:
    df_temp = fetch_data(name, creds['api_key'], creds['account_id'], time_clause)
    if not df_temp.empty: all_df_list.append(df_temp)

if all_df_list:
    df = pd.concat(all_df_list, ignore_index=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Logic to group Open/Close events into single rows
    df_main = df.groupby(['incidentId', 'Customer', 'policyName', 'conditionName', 'priority']).agg(
        start_time=('timestamp', 'min'),
        end_time=('timestamp', 'max'),
        event_count=('event', 'nunique'),
        Entity=('entity.name', 'first')
    ).reset_index()

    df_main['Status'] = df_main['event_count'].apply(lambda x: 'Active' if x == 1 else 'Closed')
    df_main['Category'] = df_main.apply(categorize_alert, axis=1)
    df_main['Duration'] = df_main.apply(lambda x: format_duration(datetime.datetime.now() - x['start_time']) if x['Status'] == 'Active' else format_duration(x['end_time'] - x['start_time']), axis=1)
    
    # Apply Status Filter
    if status_filter != "All":
        df_main = df_main[df_main['Status'] == status_filter]
    
    df_main = df_main.sort_values(by='start_time', ascending=False)
else:
    df_main = pd.DataFrame()

# --- 5. UI DISPLAY ---
st.markdown("<h1 style='text-align: center; color: #FF9F1C; font-size: 80px; margin-bottom: 0px;'>🔥 Quickplay</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center; margin-top: -10px; opacity: 0.8;'>New Relic Alerts Overview</h3>", unsafe_allow_html=True)
st.divider()

if df_main.empty:
    st.success("No incidents found matching current filters.")
else:
    # KPI Metrics
    cols = st.columns(4)
    cols[0].metric("Total Incidents", len(df_main))
    cols[1].metric("🔥 Active Now", len(df_main[df_main['Status'] == 'Active']))
    cols[2].metric("🏗️ Infra Alerts", len(df_main[df_main['Category'] == 'Infra']))
    cols[3].metric("🛡️ SOC Alerts", len(df_main[df_main['Category'] == 'SOC']))

    # Customer Chart
    if selected_view == "All Customers":
        st.subheader("📊 Incident Volume by Customer")
        chart = alt.Chart(df_main).mark_bar(color='#FF9F1C').encode(
            x=alt.X('Customer', sort='-y'),
            y='count()',
            tooltip=['Customer', 'count()']
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)

    # Tables
    t1, t2 = st.tabs(["🏗️ Infrastructure", "🛡️ SOC"])
    log_cols = ['start_time', 'Customer', 'Entity', 'conditionName', 'priority', 'Status', 'Duration']
    
    with t1:
        st.dataframe(df_main[df_main['Category'] == 'Infra'][log_cols], use_container_width=True, hide_index=True)
    with t2:
        st.dataframe(df_main[df_main['Category'] == 'SOC'][log_cols], use_container_width=True, hide_index=True)
