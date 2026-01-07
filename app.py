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

    /* KPI Card Styling */
    div[data-testid="stMetric"] {
        background-color:#161B22;
        border: 1px solid #30363D;
        border-radius: 10px;
        padding: 15px;
    }
    
    /* Expander Styling */
    .streamlit-expanderHeader {
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
        border-radius: 5px;
    }

    /* Button Grid for Customers */
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
    st.caption("Pulse Monitoring v1.4")
    st.divider()
    
    customer_selection = st.selectbox(
        "Client Selector", 
        ["All Customers"] + list(CLIENTS.keys()),
        key="customer_filter"
    )
    status_choice = st.radio("Alert Status", ["All", "Active", "Closed"], horizontal=True)
    
    # Time Mapping for Comparison
    time_options = {
        "6 Hours": {"curr": "SINCE 6 hours ago", "prev": "SINCE 12 hours ago UNTIL 6 hours ago"},
        "24 Hours": {"curr": "SINCE 24 hours ago", "prev": "SINCE 48 hours ago UNTIL 24 hours ago"},
        "7 Days": {"curr": "SINCE 7 days ago", "prev": "SINCE 14 days ago UNTIL 7 days ago"}
    }
    time_label = st.selectbox("Time Window", list(time_options.keys()))
    clauses = time_options[time_label]

    if st.button("🔄 Force Refresh"):
        st.cache_data.clear()
        st.rerun()

# ---------------- DATA FETCHING & TREND ANALYSIS ----------------
curr_rows = []
prev_counts = 0
targets = CLIENTS.items() if customer_selection == "All Customers" else [(customer_selection, CLIENTS.get(customer_selection, {}))]

with st.spinner(f"Analyzing {time_label} trends..."):
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
            curr_rows.append(df_res)
            
        # 2. Fetch Previous Period Count for Delta
        prev_q = f"SELECT count(incidentId) FROM NrAiIncident WHERE event = 'open' {clauses['prev']}"
        p_res = fetch_nrql(cfg["api_key"], cfg["account_id"], prev_q)
        if p_res:
            prev_counts += p_res[0]['count']

# ---------------- PROCESS VIEW ----------------
if curr_rows:
    full_curr = pd.concat(curr_rows)
    # Group events into incidents
    grouped = full_curr.groupby(["incidentId", "Customer", "conditionName", "Entity"]).agg(
        start_time=("timestamp", "min"),
        end_time=("timestamp", "max"),
        events=("event", "nunique")
    ).reset_index()
    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
    
    # Filter by Status
    display_df = grouped if status_choice == "All" else grouped[grouped["Status"] == status_choice]
    
    # Calculate Percentage Delta
    curr_total = len(grouped["incidentId"].unique())
    if prev_counts > 0:
        pct_change = ((curr_total - prev_counts) / prev_counts) * 100
        delta_str = f"{pct_change:+.1f}%"
    else:
        delta_str = "New"
else:
    display_df = pd.DataFrame()
    curr_total = 0
    delta_str = "0%"

# ---------------- MAIN CONTENT ----------------
st.markdown(f"<h1 class='main-header'>🔥 Quickplay Pulse</h1>", unsafe_allow_html=True)
st.markdown(f"**Viewing:** `{customer_selection}` | **Range:** `{time_label}`")

# KPI ROW
c1, c2 = st.columns(2)

# Total Alerts with Red/Green Trend Indicator
c1.metric(
    label="Total Alerts", 
    value=curr_total, 
    delta=delta_str, 
    delta_color="inverse" # Red for increase, Green for decrease
)

# Avg Resolution/Duration
c2.metric(
    label="Avg. Resolution Time", 
    value=calculate_mttr(display_df)
)

st.divider()

if display_df.empty:
    st.info(f"No {status_choice.lower()} alerts found in this window. 🎉")
    st.stop()

# ---------------- CLIENT TILES (ALL VIEW ONLY) ----------------
if customer_selection == "All Customers":
    st.subheader("Client Health Overview")
    counts = display_df["Customer"].value_counts()
    cols = st.columns(4)
    for i, (cust, cnt) in enumerate(counts.items()):
        with cols[i % 4]:
            if st.button(f"{cust}\n\n{cnt} Alerts", key=f"btn_{cust}", use_container_width=True):
                st.session_state.customer_filter = cust
                st.rerun()
    st.divider()

# ---------------- HIERARCHICAL LOG ----------------
st.subheader(f"📋 {status_choice} Alerts by Condition")

conditions = display_df["conditionName"].value_counts().index
for condition in conditions:
    cond_df = display_df[display_df["conditionName"] == condition]
    
    with st.expander(f"**{condition}** — {len(cond_df)} Alerts"):
        # Entity Breakdown Table
        entity_sum = cond_df.groupby("Entity").size().reset_index(name="Alerts")
        st.dataframe(
            entity_sum.sort_values("Alerts", ascending=False), 
            hide_index=True, 
            use_container_width=True,
            column_config={
                "Alerts": st.column_config.NumberColumn(format="%d 🚨")
            }
        )

# ---------------- FOOTER ----------------
sync_time = datetime.datetime.now().strftime("%H:%M:%S")
st.caption(f"Last sync: {sync_time} | Comparing vs previous {time_label} period.")
