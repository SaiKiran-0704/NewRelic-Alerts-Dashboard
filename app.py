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
</style>
""", unsafe_allow_html=True)

# ---------------- CONFIG & DATA LOGIC ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

if "customer_filter" not in st.session_state: st.session_state.customer_filter = "All Customers"

# ---------------- HELPERS ----------------
def calculate_mttr(df):
    if df.empty: return "N/A"
    durations = []
    now = datetime.datetime.utcnow()
    for _, row in df.iterrows():
        if row["Status"] == "Active":
            durations.append((now - row["start_time"]).total_seconds() / 60)
        else:
            durations.append((row["end_time"] - row["start_time"]).total_seconds() / 60)
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

def process_alerts(data, name):
    df = pd.DataFrame(data)
    if df.empty: return pd.DataFrame()
    df["Customer"] = name
    df.rename(columns={"entity.name": "Entity"}, inplace=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("<h1 style='color:#F37021; font-size: 28px;'>🔥 quickplay</h1>", unsafe_allow_html=True)
    customer_selection = st.selectbox("Client Selector", ["All Customers"] + list(CLIENTS.keys()), key="customer_filter")
    status_choice = st.radio("Alert Status", ["All", "Active", "Closed"], horizontal=True)
    
    time_options = {
        "6 Hours": {"current": "SINCE 6 hours ago", "previous": "SINCE 12 hours ago UNTIL 6 hours ago"},
        "24 Hours": {"current": "SINCE 24 hours ago", "previous": "SINCE 48 hours ago UNTIL 24 hours ago"},
        "7 Days": {"current": "SINCE 7 days ago", "previous": "SINCE 14 days ago UNTIL 7 days ago"}
    }
    time_label = st.selectbox("Time Window", list(time_options.keys()))
    clauses = time_options[time_label]

# ---------------- DATA FETCHING ----------------
current_rows = []
prev_rows = []
targets = CLIENTS.items() if customer_selection == "All Customers" else [(customer_selection, CLIENTS.get(customer_selection, {}))]

with st.spinner("Analyzing trends..."):
    for name, cfg in targets:
        if not cfg: continue
        # Fetch Current
        curr_q = f"SELECT timestamp, conditionName, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {clauses['current']} LIMIT MAX"
        current_rows.append(process_alerts(fetch_nrql(cfg["api_key"], cfg["account_id"], curr_q), name))
        # Fetch Previous for Delta
        prev_q = f"SELECT incidentId FROM NrAiIncident WHERE event = 'open' {clauses['previous']} LIMIT MAX"
        prev_rows.append(pd.DataFrame(fetch_nrql(cfg["api_key"], cfg["account_id"], prev_q)))

# ---------------- CALCULATE DELTA ----------------
curr_df = pd.concat(current_rows) if current_rows else pd.DataFrame()
prev_total = sum([len(d["incidentId"].unique()) if not d.empty else 0 for d in prev_rows])

if not curr_df.empty:
    # Grouping to incidents
    grouped = curr_df.groupby(["incidentId", "Customer", "conditionName", "Entity"]).agg(
        start_time=("timestamp", "min"), end_time=("timestamp", "max"), events=("event", "nunique")
    ).reset_index()
    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
    
    # Filter by Status
    display_df = grouped if status_choice == "All" else grouped[grouped["Status"] == status_choice]
    
    curr_total = len(grouped["incidentId"].unique())
    # Calculate percentage change
    if prev_total > 0:
        delta_val = f"{((curr_total - prev_total) / prev_total) * 100:.1f}%"
    else:
        delta_val = "New"
else:
    display_df = pd.DataFrame()
    curr_total = 0
    delta_val = "0%"

# ---------------- MAIN CONTENT ----------------
st.markdown(f"<h1 class='main-header'>🔥 Quickplay Pulse</h1>")

# KPI Row with Comparison Delta
# Delta color: inverse (Red is bad/up, Green is good/down)
c1, c2 = st.columns(2)
c1.metric(
    label="Total Alerts (Current Window)", 
    value=curr_total, 
    delta=delta_val, 
    delta_color="inverse"
)
c2.metric(
    label="Avg. Resolution Time", 
    value=calculate_mttr(display_df)
)

st.divider()

if display_df.empty:
    st.info("No alerts found in this window.")
    st.stop()

# ---------------- HIERARCHICAL LOG ----------------
st.subheader(f"📋 {status_choice} Alerts by Condition")
for condition in display_df["conditionName"].value_counts().index:
    cond_df = display_df[display_df["conditionName"] == condition]
    with st.expander(f"**{condition}** — {len(cond_df)} Alerts"):
        entity_sum = cond_df.groupby("Entity").size().reset_index(name="Alerts")
        st.dataframe(entity_sum.sort_values("Alerts", ascending=False), hide_index=True, use_container_width=True)
