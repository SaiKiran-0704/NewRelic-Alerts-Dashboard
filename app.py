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
    }

    .stButton>button {
        background-color: #1C2128;
        border: 1px solid #30363D;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# ---------------- CONFIG ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

# ---------------- HELPERS ----------------
def calculate_mttr(df):
    if df.empty: return "N/A"
    durations = []
    now = datetime.datetime.utcnow()
    for _, row in df.iterrows():
        start = row["start_time"]
        end = row["end_time"] if row["Status"] == "Closed" else now
        durations.append((end - start).total_seconds() / 60)
    avg = sum(durations) / len(durations)
    return f"{int(avg//60)}h {int(avg%60)}m" if avg >= 60 else f"{int(avg)}m"

@st.cache_data(ttl=300)
def fetch_nrql(api_key, account_id, query):
    gql_query = f"{{ actor {{ account(id: {account_id}) {{ nrql(query: \"{query}\") {{ results }} }} }} }}"
    try:
        r = requests.post(ENDPOINT, json={"query": gql_query}, headers={"API-Key": api_key}, timeout=15)
        return r.json()["data"]["actor"]["account"]["nrql"]["results"]
    except:
        return []

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("<h1 style='color:#F37021; font-size: 28px;'>🔥 quickplay</h1>", unsafe_allow_html=True)
    customer_selection = st.selectbox("Client Selector", ["All Customers"] + list(CLIENTS.keys()))
    status_choice = st.radio("Alert Status", ["All", "Active", "Closed"], horizontal=True)
    
    # Dynamic Time Mapping
    time_options = {
        "6 Hours": {"curr": "SINCE 6 hours ago", "prev": "SINCE 12 hours ago UNTIL 6 hours ago"},
        "24 Hours": {"curr": "SINCE 24 hours ago", "prev": "SINCE 48 hours ago UNTIL 24 hours ago"},
        "7 Days": {"curr": "SINCE 7 days ago", "prev": "SINCE 14 days ago UNTIL 7 days ago"}
    }
    time_label = st.selectbox("Time Window", list(time_options.keys()))
    clauses = time_options[time_label]

# ---------------- DATA PROCESSING ----------------
curr_all = []
prev_counts = 0
targets = CLIENTS.items() if customer_selection == "All Customers" else [(customer_selection, CLIENTS.get(customer_selection, {}))]

with st.spinner(f"Comparing current {time_label} vs previous..."):
    for name, cfg in targets:
        if not cfg: continue
        
        # 1. Fetch Current Data
        curr_q = f"SELECT timestamp, conditionName, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {clauses['curr']} LIMIT MAX"
        res = fetch_nrql(cfg["api_key"], cfg["account_id"], curr_q)
        if res:
            df_res = pd.DataFrame(res)
            df_res["Customer"] = name
            df_res.rename(columns={"entity.name": "Entity"}, inplace=True)
            df_res["timestamp"] = pd.to_datetime(df_res["timestamp"], unit="ms")
            curr_all.append(df_res)
            
        # 2. Fetch Previous Count (Simple count for delta)
        prev_q = f"SELECT count(incidentId) FROM NrAiIncident WHERE event = 'open' {clauses['prev']}"
        p_res = fetch_nrql(cfg["api_key"], cfg["account_id"], prev_q)
        if p_res:
            prev_counts += p_res[0]['count']

# ---------------- PREPARE VIEW ----------------
if curr_all:
    full_curr = pd.concat(curr_all)
    grouped = full_curr.groupby(["incidentId", "Customer", "conditionName", "Entity"]).agg(
        start_time=("timestamp", "min"),
        end_time=("timestamp", "max"),
        events=("event", "nunique")
    ).reset_index()
    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
    
    # Filter for selected status
    display_df = grouped if status_choice == "All" else grouped[grouped["Status"] == status_choice]
    
    # Delta Logic
    curr_count = len(grouped["incidentId"].unique())
    if prev_counts > 0:
        percent_change = ((curr_count - prev_counts) / prev_counts) * 100
        delta_str = f"{percent_change:+.1f}%"
    else:
        delta_str = "New"
else:
    display_df = pd.DataFrame()
    curr_count = 0
    delta_str = "0%"

# ---------------- MAIN CONTENT ----------------
st.markdown(f"<h1 class='main-header'>🔥 Quickplay Pulse</h1>", unsafe_allow_html=True)
st.markdown(f"**Viewing:** `{customer_selection}` | **Range:** `{time_label}`")

# KPI ROW
c1, c2 = st.columns(2)
# Delta color "inverse": Increase is RED, Decrease is GREEN
c1.metric(
    label="Total Alerts", 
    value=curr_count, 
    delta=delta_str, 
    delta_color="inverse"
)
c2.metric(
    label="Avg. Duration/Resolution", 
    value=calculate_mttr(display_df)
)

st.divider()

if display_df.empty:
    st.info("No alerts found for this window.")
    st.stop()

# HIERARCHICAL LOG
st.subheader(f"📋 {status_choice} Alerts by Condition")
conditions = display_df["conditionName"].value_counts().index
for condition in conditions:
    cond_df = display_df[display_df["conditionName"] == condition]
    with st.expander(f"**{condition}** — {len(cond_df)} Alerts"):
        entity_sum = cond_df.groupby("Entity").size().reset_index(name="Alerts")
        st.dataframe(entity_sum.sort_values("Alerts", ascending=False), hide_index=True, use_container_width=True)
