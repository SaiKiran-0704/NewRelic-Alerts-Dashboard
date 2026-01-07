import streamlit as st
import requests
import pandas as pd
import datetime

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Quickplay Pulse",
    layout="wide",
    page_icon="🔥",
    initial_sidebar_state="expanded" 
)

# ---------------- ADVANCED VISUAL BRANDING & PERMANENT SIDEBAR (CSS) ----------------
st.markdown("""
<style>
    /* Main App Background */
    .stApp { background-color:#0A0C10; color:#E6E6E6; }
    
    /* REMOVE COLLAPSE ACTION & MAKE SIDEBAR PERMANENT */
    button[kind="headerNoPadding"] {
        display: none !important;
    }
    
    /* Permanent Sidebar with Dark Theme */
    section[data-testid="stSidebar"] {
        width: 400px !important;
        background-color: #161B22 !important;
        border-right: 1px solid #30363D;
        position: fixed;
    }

    /* Sidebar Logo Styling */
    .sidebar-logo-container {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 20px;
    }
    .sidebar-logo-text { 
        color: #F37021; 
        font-weight: 800; 
        font-size: 2.2rem; 
        letter-spacing: -1.5px;
    }

    /* Center Header Styling - Pulse Monitoring now Orange */
    .center-header {
        text-align: center;
        color: #F37021; 
        font-weight: 800;
        font-size: 3.5rem;
        margin-top: 0px;
        margin-bottom: 10px;
    }
    
    .block-container { padding-top: 1rem; }

    /* Adjust Main Content */
    section.main {
        margin-left: 50px;
    }
    
    /* Sidebar Text & Label Enhancement */
    [data-testid="stSidebar"] .stText, 
    [data-testid="stSidebar"] label, 
    [data-testid="stSidebar"] p {
        color: #E6E6E6 !important;
        font-size: 1.2rem !important;
        font-weight: 700 !important;
        margin-bottom: 12px !important;
    }

    /* Glassmorphism for Sidebar Widgets */
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"],
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
        background-color: #0A0C10 !important;
        border-radius: 12px !important;
        border: 1px solid #30363D !important;
        padding: 8px;
    }

    /* Key Metric Card Styling */
    div[data-testid="stMetric"] {
        background-color:#161B22;
        border: 1px solid #30363D;
        border-radius: 15px;
        padding: 25px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }

    /* Prominent Metric Numbers */
    div[data-testid="stMetricValue"] > div {
        font-size: 3.2rem !important;
        font-weight: 800 !important;
        color: #FFFFFF !important;
    }

    /* Sidebar Action Button */
    [data-testid="stSidebar"] .stButton>button {
        background-color: #F37021 !important;
        border: none !important;
        color: white !important;
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        border-radius: 15px !important;
        padding: 15px 20px !important;
        margin-top: 30px !important;
        width: 100%;
        transition: 0.3s;
    }
</style>
""", unsafe_allow_html=True)

# ---------------- CONFIG & DATA LOGIC ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

if "alerts" not in st.session_state: st.session_state.alerts = None
if "updated" not in st.session_state: st.session_state.updated = None
if "customer_filter" not in st.session_state: st.session_state.customer_filter = "All Customers"
if "navigate_to_customer" not in st.session_state: st.session_state.navigate_to_customer = None

if st.session_state.navigate_to_customer:
    st.session_state.customer_filter = st.session_state.navigate_to_customer
    st.session_state.navigate_to_customer = None

# ---------------- HELPERS ----------------
def get_dynamic_avg_value(count, time_label):
    if count == 0: return 0.0
    if "Hours" in time_label:
        units = int(time_label.split()[0])
        return count / units
    elif "24 Hours" in time_label:
        return count / 24
    elif "7 Days" in time_label:
        return count / 7
    elif "30 Days" in time_label:
        return count / 4 
    return float(count)

def get_resolution_rate(df):
    if df.empty: return 0
    return (len(df[df.Status=='Closed'])/len(df))*100

def calculate_percent_delta(current, previous):
    if previous == 0:
        return f"+100%" if current > 0 else "0%"
    diff = ((current - previous) / previous) * 100
    return f"{diff:+.1f}%"

@st.cache_data(ttl=300)
def fetch_account_with_history(name, api_key, account_id, time_label):
    time_map_history = {
        "6 Hours": ("SINCE 6 hours ago", "SINCE 12 hours ago UNTIL 6 hours ago"),
        "24 Hours": ("SINCE 24 hours ago", "SINCE 48 hours ago UNTIL 24 hours ago"),
        "7 Days": ("SINCE 7 days ago", "SINCE 14 days ago UNTIL 7 days ago"),
        "30 Days": ("SINCE 30 days ago", "SINCE 60 days ago UNTIL 30 days ago")
    }
    curr_clause, prev_clause = time_map_history[time_label]
    
    query = f"""
    {{ actor {{ account(id: {account_id}) {{
          current: nrql(query: "SELECT timestamp, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {curr_clause} LIMIT MAX") {{
            results
          }}
          previous: nrql(query: "SELECT count(*) FROM NrAiIncident WHERE event = 'open' {prev_clause}") {{
            results
          }}
        }} }} }}
    """
    try:
        r = requests.post(ENDPOINT, json={"query": query}, headers={"API-Key": api_key}, timeout=15)
        res = r.json()["data"]["actor"]["account"]
        df_curr = pd.DataFrame(res["current"]["results"])
        prev_count = res["previous"]["results"][0]["count"]
        
        if not df_curr.empty:
            df_curr["Customer"] = name
            df_curr.rename(columns={"entity.name": "Entity"}, inplace=True)
        return df_curr, prev_count
    except:
        return pd.DataFrame(), 0

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("""
        <div class="sidebar-logo-container">
            <span style="font-size: 2.2rem;">🔥</span>
            <span class="sidebar-logo-text">quickplay</span>
        </div>
    """, unsafe_allow_html=True)
    st.divider()
    
    customer_selection = st.selectbox(
        "Client Selector",
        ["All Customers"] + list(CLIENTS.keys()),
        key="customer_filter"
    )

    status_choice = st.radio("Alert Status", ["All", "Active", "Closed"], horizontal=True)
    time_label = st.selectbox("Time Window", ["6 Hours", "24 Hours", "7 Days", "30 Days"])

    if st.button("🔄 Force Refresh Pulse"):
        st.cache_data.clear()
        st.rerun()

# ---------------- LOAD & PROCESS DATA ----------------
all_rows = []
total_prev_count = 0
targets = CLIENTS.items() if customer_selection == "All Customers" else [(customer_selection, CLIENTS.get(customer_selection, {}))]

with st.spinner("Syncing Pulse Trends..."):
    for name, cfg in targets:
        if cfg:
            df_res, p_count = fetch_account_with_history(name, cfg["api_key"], cfg["account_id"], time_label)
            if not df_res.empty: all_rows.append(df_res)
            total_prev_count += p_count

if all_rows:
    raw = pd.concat(all_rows)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], unit="ms")
    grouped = raw.groupby(["incidentId", "Customer", "conditionName", "priority", "Entity"]).agg(
        start_time=("timestamp", "min"),
        end_time=("timestamp", "max"),
        events=("event", "nunique")
    ).reset_index()
    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
    display_df = grouped if status_choice == "All" else grouped[grouped["Status"] == status_choice]
    st.session_state.alerts = display_df.sort_values("start_time", ascending=False)
    st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts = pd.DataFrame()

# ---------------- MAIN CONTENT ----------------
# Centered Title (Color set in CSS)
st.markdown('<h1 class="center-header">Pulse Monitoring</h1>', unsafe_allow_html=True)

# Viewing and Range display removed as requested

df = st.session_state.alerts

# ---------------- PROMINENT KPI ROW ----------------
card_titles = {"6 Hours": "Avg Alerts / Hour", "24 Hours": "Avg Alerts / Hour", "7 Days": "Avg Alerts / Day", "30 Days": "Avg Alerts / Week"}
card_title = card_titles.get(time_label, "Avg Alerts")

curr_total = len(df)
curr_avg = get_dynamic_avg_value(curr_total, time_label)
prev_avg = get_dynamic_avg_value(total_prev_count, time_label)
res_rate = get_resolution_rate(df)

total_delta_pct = calculate_percent_delta(curr_total, total_prev_count)
avg_delta_pct = calculate_percent_delta(curr_avg, prev_avg)

c1, c2, c3 = st.columns(3)
with c1: st.metric("Total Alerts", curr_total, delta=total_delta_pct, delta_color="inverse")
with c2: st.metric(card_title, f"{curr_avg:.1f}", delta=avg_delta_pct, delta_color="inverse")
with c3: st.metric("Resolution Rate", f"{res_rate:.0f}%")

st.divider()

if df.empty:
    st.info(f"No {status_choice.lower()} alerts found.")
    st.stop()

# ---------------- CLIENT TILES ----------------
if customer_selection == "All Customers":
    # Renamed from Regional Health Status to Alerts by customer
    st.subheader("Alerts by customer")
    counts = df["Customer"].value_counts()
    cols = st.columns(4)
    for i, (cust, cnt) in enumerate(counts.items()):
        with cols[i % 4]:
            if st.button(f"🏢 {cust}\n\n{cnt} Alerts", key=f"c_{cust}", use_container_width=True):
                st.session_state.navigate_to_customer = cust
                st.rerun()
    st.divider()

# ---------------- INCIDENT LOG ----------------
st.subheader(f"Log: {status_choice} Alerts by Condition")
for condition in df["conditionName"].value_counts().index:
    cond_df = df[df["conditionName"] == condition]
    with st.expander(f"📌 {condition} - {len(cond_df)} Alerts"):
        st.dataframe(cond_df.groupby("Entity").size().reset_index(name="Alert Count").sort_values("Alert Count", ascending=False), hide_index=True, use_container_width=True)

st.caption(f"Last sync: {st.session_state.updated} | Quickplay Internal Pulse")
