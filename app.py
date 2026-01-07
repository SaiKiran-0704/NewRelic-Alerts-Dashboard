import streamlit as st
import requests
import pandas as pd
import datetime

# ---------------- 1. PAGE CONFIG ----------------
st.set_page_config(
    page_title="Quickplay Pulse",
    layout="wide",
    page_icon="🔥",
    initial_sidebar_state="expanded" 
)

# ---------------- 2. PREMIUM UI OVERHAUL (CSS) ----------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    /* Main Background with Deep Radial Gradient */
    .stApp { 
        background: radial-gradient(circle at 50% 0%, #1a1c23 0%, #0a0c10 100%);
        color: #e0e0e0; 
        font-family: 'Inter', sans-serif; 
    }

    /* Remove Sidebar Toggle */
    button[kind="headerNoPadding"] { display: none !important; }

    /* Permanent Glassmorphism Sidebar */
    section[data-testid="stSidebar"] {
        width: 400px !important;
        background: rgba(22, 27, 34, 0.98) !important;
        border-right: 1px solid rgba(243, 112, 33, 0.3);
        position: fixed;
        backdrop-filter: blur(20px);
    }

    .sidebar-logo-container {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 0;
        text-shadow: 0 0 15px rgba(243, 112, 33, 0.4);
    }
    .sidebar-logo-text { 
        color: #F37021; 
        font-weight: 800; 
        font-size: 2.4rem; 
        letter-spacing: -2px;
    }

    /* Glowing Orange Center Header */
    .center-header {
        text-align: center;
        color: #F37021; 
        font-weight: 800;
        font-size: 4.5rem;
        margin: 20px 0;
        text-shadow: 0 0 30px rgba(243, 112, 33, 0.6);
        letter-spacing: -2px;
    }

    /* KPI Glass Cards */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 24px !important;
        padding: 35px !important;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5) !important;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-10px) scale(1.02);
        border: 1px solid rgba(243, 112, 33, 0.6) !important;
        background: rgba(243, 112, 33, 0.03) !important;
    }

    div[data-testid="stMetricValue"] > div {
        font-size: 4rem !important;
        font-weight: 800 !important;
        color: #ffffff !important;
        text-shadow: 0 0 10px rgba(255,255,255,0.2);
    }

    /* Customer Tile "Magic" - Out of the box grid */
    .stButton>button {
        background: linear-gradient(135deg, #1e222d 0%, #0f1115 100%) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        color: #ffffff !important;
        border-radius: 16px !important;
        font-weight: 800 !important;
        height: 100px !important;
        font-size: 1.2rem !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.4) !important;
        transition: all 0.3s ease !important;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .stButton>button:hover {
        border-color: #F37021 !important;
        box-shadow: 0 0 25px rgba(243, 112, 33, 0.3) !important;
        transform: scale(1.05);
        color: #F37021 !important;
    }

    /* Custom Scrollbar for NOC feel */
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: #0a0c10; }
    ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #F37021; }
</style>
""", unsafe_allow_html=True)

# ---------------- 3. CONFIG & DATA LOGIC ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

if "alerts" not in st.session_state: st.session_state.alerts = pd.DataFrame()
if "updated" not in st.session_state: st.session_state.updated = "Never"
if "customer_filter" not in st.session_state: st.session_state.customer_filter = "All Customers"
if "navigate_to_customer" not in st.session_state: st.session_state.navigate_to_customer = None

if st.session_state.navigate_to_customer:
    st.session_state.customer_filter = st.session_state.navigate_to_customer
    st.session_state.navigate_to_customer = None

# ---------------- 4. HELPERS ----------------
def get_dynamic_avg_value(count, time_label):
    if count == 0: return 0.0
    units = 1
    if "Hours" in time_label: units = int(time_label.split()[0])
    elif "24 Hours" in time_label: units = 24
    elif "7 Days" in time_label: units = 7
    elif "30 Days" in time_label: units = 4
    elif "60 Days" in time_label: units = 8
    elif "90 Days" in time_label: units = 12
    return count / units

def calculate_percent_delta(current, previous):
    if previous == 0: return f"+100%" if current > 0 else "0%"
    diff = ((current - previous) / previous) * 100
    return f"{diff:+.1f}%"

@st.cache_data(ttl=300)
def fetch_account_with_history(name, api_key, account_id, time_label):
    time_map = {
        "6 Hours": ("SINCE 6 hours ago", "SINCE 12 hours ago UNTIL 6 hours ago"),
        "24 Hours": ("SINCE 24 hours ago", "SINCE 48 hours ago UNTIL 24 hours ago"),
        "7 Days": ("SINCE 7 days ago", "SINCE 14 days ago UNTIL 7 days ago"),
        "30 Days": ("SINCE 30 days ago", "SINCE 60 days ago UNTIL 30 days ago"),
        "60 Days": ("SINCE 60 days ago", "SINCE 120 days ago UNTIL 60 days ago"),
        "90 Days": ("SINCE 90 days ago", "SINCE 180 days ago UNTIL 90 days ago")
    }
    curr_c, prev_c = time_map[time_label]
    query = f"""
    {{ actor {{ account(id: {account_id}) {{
          current: nrql(query: "SELECT timestamp, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {curr_c} LIMIT MAX") {{ results }}
          previous: nrql(query: "SELECT count(*) FROM NrAiIncident WHERE event = 'open' {prev_c}") {{ results }}
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
    except: return pd.DataFrame(), 0

# ---------------- 5. SIDEBAR ----------------
with st.sidebar:
    st.markdown("""<div class="sidebar-logo-container"><span style="font-size: 2.5rem;">🔥</span><span class="sidebar-logo-text">quickplay</span></div>""", unsafe_allow_html=True)
    st.divider()
    customer_selection = st.selectbox("Customer", ["All Customers"] + list(CLIENTS.keys()), key="customer_filter")
    status_choice = st.radio("Alert Status", ["All", "Active", "Closed"], horizontal=True)
    time_label = st.selectbox("Time Window", ["6 Hours", "24 Hours", "7 Days", "30 Days", "60 Days", "90 Days"])
    if st.button("🔄 Force Refresh Pulse", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ---------------- 6. DATA LOADING & PROCESSING ----------------
all_rows = []
total_prev_count = 0
targets = CLIENTS.items() if customer_selection == "All Customers" else [(customer_selection, CLIENTS.get(customer_selection, {}))]

with st.spinner("Synchronizing NOC Feed..."):
    for name, cfg in targets:
        if cfg:
            df_res, p_count = fetch_account_with_history(name, cfg["api_key"], cfg["account_id"], time_label)
            if not df_res.empty: all_rows.append(df_res)
            total_prev_count += p_count

if all_rows:
    raw = pd.concat(all_rows)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], unit="ms")
    grouped = raw.groupby(["incidentId", "Customer", "conditionName", "priority", "Entity"]).agg(
        start_time=("timestamp", "min"), end_time=("timestamp", "max"), events=("event", "nunique")
    ).reset_index()
    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
    display_df = grouped if status_choice == "All" else grouped[grouped["Status"] == status_choice]
    st.session_state.alerts = display_df.sort_values("start_time", ascending=False)
    st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts = pd.DataFrame()

# ---------------- 7. MAIN CONTENT ----------------
st.markdown('<h1 class="center-header">Pulse Monitoring</h1>', unsafe_allow_html=True)

df = st.session_state.alerts

# KPI Row
card_titles = {"6 Hours": "Avg Alerts / Hour", "24 Hours": "Avg Alerts / Hour", "7 Days": "Avg Alerts / Day", "30 Days": "Avg Alerts / Week", "60 Days": "Avg Alerts / Week", "90 Days": "Avg Alerts / Week"}
card_title = card_titles.get(time_label, "Avg Alerts")

curr_total = len(df)
curr_avg = get_dynamic_avg_value(curr_total, time_label)
prev_avg = get_dynamic_avg_value(total_prev_count, time_label)
res_rate = (len(df[df.Status=='Closed'])/len(df))*100 if not df.empty else 0

c1, c2, c3 = st.columns(3)
with c1: st.metric("Total Alerts", curr_total, delta=calculate_percent_delta(curr_total, total_prev_count), delta_color="inverse")
with c2: st.metric(card_title, f"{curr_avg:.1f}", delta=calculate_percent_delta(curr_avg, prev_avg), delta_color="inverse")
with c3: st.metric("Resolution Rate", f"{res_rate:.0f}%")

st.divider()

if df.empty:
    st.info(f"No {status_choice.lower()} alerts found.")
    st.stop()

# --- THE UI MAGIC: CUSTOMER STATUS GRID ---
if customer_selection == "All Customers":
    st.markdown("<h3 style='letter-spacing:2px; color:#F37021; text-transform:uppercase;'>Alerts By Customer</h3>", unsafe_allow_html=True)
    counts = df["Customer"].value_counts()
    cols = st.columns(4)
    for i, (cust, cnt) in enumerate(counts.items()):
        with cols[i % 4]:
            # Each button is styled as a cyber-tile via CSS
            if st.button(f"🏢 {cust}\n\n{cnt} INCIDENTS", key=f"c_{cust}", use_container_width=True):
                st.session_state.navigate_to_customer = cust
                st.rerun()

st.divider()

# Log Analysis
st.subheader(f"Analysis: {status_choice} Conditions")
for condition in df["conditionName"].value_counts().index:
    cond_df = df[df["conditionName"] == condition]
    with st.expander(f"📌 {condition} ({len(cond_df)})"):
        st.dataframe(cond_df.groupby("Entity").size().reset_index(name="Alert Count").sort_values("Alert Count", ascending=False), hide_index=True, use_container_width=True)

st.caption(f"Network Status: ACTIVE | Last Sync: {st.session_state.updated}")
