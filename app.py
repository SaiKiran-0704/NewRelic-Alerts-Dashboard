import streamlit as st
import requests
import pandas as pd
import datetime

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Quickplay Pulse",
    layout="wide",
    page_icon="🔥"
)

# ---------------- ADVANCED BRANDED UI (CSS) ----------------
st.markdown("""
<style>
    /* Main Background and Typography */
    .stApp { background-color: #0A0C10; color: #E6E6E6; font-family: 'Inter', sans-serif; }
    .main-header { 
        color: #F37021; 
        font-weight: 800; 
        font-size: 2.5rem; 
        margin-bottom: -10px;
        letter-spacing: -1px;
    }
    
    /* KPI Card Glassmorphism */
    div[data-testid="stMetric"] {
        background: rgba(22, 27, 34, 0.7);
        border: 1px solid rgba(243, 112, 33, 0.2);
        border-radius: 12px;
        padding: 20px !important;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        backdrop-filter: blur(10px);
    }
    
    /* Smaller Delta font */
    div[data-testid="stMetricDelta"] > div {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
    }
    
    /* Styled Expander Headers */
    .streamlit-expanderHeader {
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
        border-radius: 8px;
        color: #F37021 !important;
        font-weight: 600 !important;
    }

    /* Customer Buttons Styling */
    .stButton>button {
        background: #161B22;
        border: 1px solid #30363D;
        color: #E6E6E6;
        border-radius: 8px;
        padding: 10px;
        transition: all 0.3s ease;
        text-align: left;
    }
    .stButton>button:hover {
        border-color: #F37021;
        box-shadow: 0 0 10px rgba(243, 112, 33, 0.4);
        color: #F37021;
    }

    /* Custom Scrollbar */
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: #0A0C10; }
    ::-webkit-scrollbar-thumb { background: #30363D; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #F37021; }
</style>
""", unsafe_allow_html=True)

# ---------------- DATA LOGIC ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

def get_dynamic_avg_details(count, time_label):
    if "Hours" in time_label:
        units = int(time_label.split()[0]); return count / units, "Avg. Alerts / Hour"
    elif "24 Hours" in time_label: return count / 24, "Avg. Alerts / Hour"
    elif "7 Days" in time_label: return count / 7, "Avg. Alerts / Day"
    elif "30 Days" in time_label: return count / 4, "Avg. Alerts / Week"
    return count, "Avg. Alerts"

def calculate_delta(current, previous):
    if previous == 0: return f"+100%" if current > 0 else "0%"
    diff = ((current - previous) / previous) * 100
    return f"{diff:+.1f}%"

@st.cache_data(ttl=300)
def fetch_pulse_data(name, api_key, account_id, time_label):
    time_map = {
        "6 Hours": ("SINCE 6 hours ago", "UNTIL now", "SINCE 12 hours ago", "UNTIL 6 hours ago"),
        "24 Hours": ("SINCE 24 hours ago", "UNTIL now", "SINCE 48 hours ago", "UNTIL 24 hours ago"),
        "7 Days": ("SINCE 7 days ago", "UNTIL now", "SINCE 14 days ago", "UNTIL 7 days ago"),
        "30 Days": ("SINCE 30 days ago", "UNTIL now", "SINCE 60 days ago", "UNTIL 30 days ago")
    }
    curr_since, curr_until, prev_since, prev_until = time_map[time_label]
    query = f"""
    {{ actor {{ account(id: {account_id}) {{
          current: nrql(query: "SELECT timestamp, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {curr_since} {curr_until} LIMIT MAX") {{ results }}
          previous: nrql(query: "SELECT count(*) FROM NrAiIncident WHERE event = 'open' {prev_since} {prev_until}") {{ results }}
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

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("<h1 style='color:#F37021; font-size: 32px; font-weight: 800;'>QUICKPLAY</h1>", unsafe_allow_html=True)
    st.markdown("---")
    customer_selection = st.selectbox("🎯 Target Client", ["All Customers"] + list(CLIENTS.keys()))
    time_label = st.selectbox("⏱️ Time Window", ["6 Hours", "24 Hours", "7 Days", "30 Days"])
    status_choice = st.radio("🚦 Status Filter", ["All", "Active", "Closed"], horizontal=True)
    st.markdown("---")
    if st.button("🔄 Force Refresh Pulse", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ---------------- PROCESSING ----------------
all_curr = []; total_prev_count = 0
targets = CLIENTS.items() if customer_selection == "All Customers" else [(customer_selection, CLIENTS.get(customer_selection, {}))]

with st.spinner("Synchronizing pulse data..."):
    for name, cfg in targets:
        if cfg:
            df_c, p_count = fetch_pulse_data(name, cfg["api_key"], cfg["account_id"], time_label)
            if not df_c.empty: all_curr.append(df_c)
            total_prev_count += p_count

if all_curr:
    raw = pd.concat(all_curr)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], unit="ms")
    grouped = raw.groupby(["incidentId", "Customer", "conditionName", "priority", "Entity"]).agg(
        start_time=("timestamp", "min"), end_time=("timestamp", "max"), events=("event", "nunique")
    ).reset_index()
    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
    df = grouped if status_choice == "All" else grouped[grouped["Status"] == status_choice]
else:
    df = pd.DataFrame()

# ---------------- DASHBOARD UI ----------------
st.markdown("<p class='main-header'>🔥 Pulse Overview</p>", unsafe_allow_html=True)
st.markdown(f"**Target:** `{customer_selection}` | **Window:** `{time_label}`")
st.markdown("<br>", unsafe_allow_html=True)

# KPI Row with Comparison Deltas
curr_total = len(df)
total_delta = calculate_delta(curr_total, total_prev_count)
curr_avg, avg_label = get_dynamic_avg_details(curr_total, time_label)
prev_avg, _ = get_dynamic_avg_details(total_prev_count, time_label)
avg_delta = calculate_delta(curr_avg, prev_avg)

c1, c2, c3 = st.columns(3)
with c1: st.metric("TOTAL INCIDENTS", curr_total, delta=total_delta, delta_color="inverse")
with c2: st.metric(avg_label.upper(), f"{curr_avg:.1f}", delta=avg_delta, delta_color="inverse")
with c3: 
    res_rate = (len(df[df.Status=='Closed'])/len(df))*100 if not df.empty else 0
    st.metric("RESOLUTION RATE", f"{res_rate:.0f}%")

st.markdown("<br>", unsafe_allow_html=True)

# Client Grid (Only if "All" is selected)
if customer_selection == "All Customers" and not df.empty:
    st.subheader("📡 Regional Health Status")
    counts = df["Customer"].value_counts()
    cols = st.columns(4)
    for i, (cust, cnt) in enumerate(counts.items()):
        with cols[i % 4]:
            st.button(f"🏢 {cust}\n\n{cnt} Total Alerts", key=f"btn_{cust}", use_container_width=True)

# Incident Breakdown
st.markdown("---")
st.subheader("📋 Incident Analysis")
if not df.empty:
    for condition in df["conditionName"].value_counts().index:
        cond_df = df[df["conditionName"] == condition]
        with st.expander(f"📌 {condition} ({len(cond_df)})"):
            st.dataframe(
                cond_df.groupby("Entity").size().reset_index(name="Alert Count").sort_values("Alert Count", ascending=False),
                hide_index=True, use_container_width=True
            )
else:
    st.info("No monitoring events recorded for this period.")

st.markdown("<br><br>", unsafe_allow_html=True)
st.caption(f"System Sync: {datetime.datetime.now().strftime('%H:%M:%S')} UTC | Quickplay Monitoring Pulse")
