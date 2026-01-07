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

# ---------------- CLEAN & BRANDED UI ----------------
st.markdown("""
<style>
    .stApp { background-color:#0F1115; color:#E6E6E6; }
    .main-header { color: #F37021; font-weight: 800; margin-bottom: 0px; }
    .block-container { padding-top: 2rem; }

    div[data-testid="stMetric"] {
        background-color:#161B22;
        border: 1px solid #30363D;
        border-radius: 10px;
        padding: 15px;
    }
    
    .streamlit-expanderHeader {
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
        border-radius: 5px;
        font-size: 1.1rem;
    }

    .stButton>button {
        background-color: #1C2128;
        border: 1px solid #30363D;
        color: white;
        transition: 0.3s;
    }
    .stButton>button:hover {
        border-color: #F37021;
        color: #F37021;
    }
</style>
""", unsafe_allow_html=True)

# ---------------- CONFIG & DATA LOGIC ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

if "alerts" not in st.session_state: st.session_state.alerts = None
if "updated" not in st.session_state: st.session_state.updated = None

# ---------------- HELPERS ----------------
def get_dynamic_avg_details(count, time_label):
    if "Hours" in time_label:
        units = int(time_label.split()[0])
        return count / units, "Avg. Alerts / Hour"
    elif "24 Hours" in time_label:
        return count / 24, "Avg. Alerts / Hour"
    elif "7 Days" in time_label:
        return count / 7, "Avg. Alerts / Day"
    elif "30 Days" in time_label:
        return count / 4, "Avg. Alerts / Week"
    return count, "Avg. Alerts"

def calculate_delta(current, previous):
    if previous == 0:
        return f"+100%" if current > 0 else "0%"
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
    except:
        return pd.DataFrame(), 0

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("<h1 style='color:#F37021; font-size: 28px;'>🔥 quickplay</h1>", unsafe_allow_html=True)
    st.caption("Pulse Monitoring v1.9")
    st.divider()
    
    # Use session_state key to allow tile-clicks to update the dropdown
    customer_selection = st.selectbox(
        "Client Selector", 
        ["All Customers"] + list(CLIENTS.keys()), 
        key="customer_selection_key"
    )
    
    status_choice = st.radio("Alert Status", ["All", "Active", "Closed"], horizontal=True)
    time_label = st.selectbox("Time Window", ["6 Hours", "24 Hours", "7 Days", "30 Days"])

    if st.button("🔄 Force Refresh"):
        st.cache_data.clear()
        st.rerun()

# ---------------- LOAD & PROCESS ----------------
all_curr = []
total_prev_count = 0
targets = CLIENTS.items() if customer_selection == "All Customers" else [(customer_selection, CLIENTS.get(customer_selection, {}))]

with st.spinner("Syncing Pulse Trends..."):
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
    
    display_df = grouped if status_choice == "All" else grouped[grouped["Status"] == status_choice]
    st.session_state.alerts = display_df.sort_values("start_time", ascending=False)
    st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts = pd.DataFrame()

# ---------------- MAIN CONTENT ----------------
st.markdown(f"<h1 class='main-header'>🔥 Quickplay Pulse</h1>", unsafe_allow_html=True)
df = st.session_state.alerts

# KPI LOGIC
curr_total = len(df)
total_delta = calculate_delta(curr_total, total_prev_count)

curr_avg, avg_label = get_dynamic_avg_details(curr_total, time_label)
prev_avg, _ = get_dynamic_avg_details(total_prev_count, time_label)
avg_delta = calculate_delta(curr_avg, prev_avg)

# Invert delta colors: In alerts, increase is RED (bad), decrease is GREEN (good)
c1, c2, c3 = st.columns(3)
c1.metric("Total Alerts", curr_total, delta=total_delta, delta_color="inverse")
c2.metric(avg_label, f"{curr_avg:.1f}", delta=avg_delta, delta_color="inverse")
c3.metric("Resolution Rate", f"{(len(df[df.Status=='Closed'])/len(df))*100:.0f}%" if not df.empty else "0%")

st.divider()
if df.empty:
    st.info("No alerts found.")
    st.stop()

# CLIENT TILES & LOG
if customer_selection == "All Customers":
    counts = df["Customer"].value_counts()
    cols = st.columns(4)
    for i, (cust, cnt) in enumerate(counts.items()):
        with cols[i % 4]:
            if st.button(f"{cust}\n\n{cnt} Alerts", key=f"c_{cust}", use_container_width=True):
                # Update sidebar dropdown and rerun
                st.session_state.customer_selection_key = cust
                st.rerun()

st.subheader(f"📋 {status_choice} Alerts by Condition")
for condition in df["conditionName"].value_counts().index:
    cond_df = df[df["conditionName"] == condition]
    with st.expander(f"**{condition}** — {len(cond_df)} Alerts"):
        st.dataframe(cond_df.groupby("Entity").size().reset_index(name="Count").sort_values("Count", ascending=False), hide_index=True, use_container_width=True)
