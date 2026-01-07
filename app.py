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
if "customer_filter" not in st.session_state: st.session_state.customer_filter = "All Customers"
if "navigate_to_customer" not in st.session_state: st.session_state.navigate_to_customer = None

if st.session_state.navigate_to_customer:
    st.session_state.customer_filter = st.session_state.navigate_to_customer
    st.session_state.navigate_to_customer = None

# ---------------- HELPERS ----------------
def format_duration(td):
    s = int(td.total_seconds())
    if s < 60: return f"{s}s"
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"

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

def get_resolution_rate(df):
    if df.empty: return "0%"
    return f"{(len(df[df.Status=='Closed'])/len(df))*100:.0f}%"

@st.cache_data(ttl=300)
def fetch_account(name, api_key, account_id, time_clause):
    query = f"""
    {{ actor {{ account(id: {account_id}) {{
          nrql(query: "SELECT timestamp, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {time_clause} LIMIT MAX") {{
            results
          }}
        }} }} }}
    """
    try:
        r = requests.post(ENDPOINT, json={"query": query}, headers={"API-Key": api_key}, timeout=15)
        data = r.json()["data"]["actor"]["account"]["nrql"]["results"]
        df = pd.DataFrame(data)
        if not df.empty:
            df["Customer"] = name
            df.rename(columns={"entity.name": "Entity"}, inplace=True)
        return df
    except:
        return pd.DataFrame()

# ---------------- DATA FETCHING ----------------
all_rows = []
time_map = {
    "6 Hours": "SINCE 6 hours ago",
    "24 Hours": "SINCE 24 hours ago",
    "7 Days": "SINCE 7 days ago",
    "30 Days": "SINCE 30 days ago"
}

# SIDEBAR (Top Part)
with st.sidebar:
    st.markdown("<h1 style='color:#F37021; font-size: 28px;'>🔥 quickplay</h1>", unsafe_allow_html=True)
    st.caption("Pulse Monitoring v1.5")
    st.divider()
    
    customer_selection = st.selectbox(
        "Client Selector",
        ["All Customers"] + list(CLIENTS.keys()),
        key="customer_filter_input"
    )
    
    time_label = st.selectbox("Time Window", list(time_map.keys()))
    time_clause = time_map[time_label]

# Run fetching
targets = CLIENTS.items() if customer_selection == "All Customers" else [(customer_selection, CLIENTS.get(customer_selection, {}))]
for name, cfg in targets:
    if cfg:
        df_res = fetch_account(name, cfg["api_key"], cfg["account_id"], time_clause)
        if not df_res.empty: all_rows.append(df_res)

# Process initial data to get condition names
if all_rows:
    raw = pd.concat(all_rows)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], unit="ms")
    
    grouped = raw.groupby(["incidentId", "Customer", "conditionName", "priority", "Entity"]).agg(
        start_time=("timestamp", "min"),
        end_time=("timestamp", "max"),
        events=("event", "nunique")
    ).reset_index()
    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
    
    # FETCH ALL UNIQUE CONDITIONS & ADD 'ALL' OPTION
    raw_conditions = sorted(grouped["conditionName"].unique().tolist())
    condition_options = ["All"] + raw_conditions
else:
    grouped = pd.DataFrame()
    condition_options = ["All"]

# ---------------- SIDEBAR FILTERS ----------------
with st.sidebar:
    status_choice = st.radio("Alert Status", ["All", "Active", "Closed"], horizontal=True)
    
    # CONDITION FILTER WITH 'ALL' AS DEFAULT
    selected_conditions = st.multiselect(
        "Condition Filter",
        options=condition_options,
        default=["All"],
        help="Select 'All' to see everything, or pick specific conditions."
    )

    if st.button("🔄 Force Refresh"):
        st.cache_data.clear()
        st.rerun()

# ---------------- FILTER LOGIC ----------------
if not grouped.empty:
    # If "All" is in selection OR selection is empty, show everything
    if "All" in selected_conditions or not selected_conditions:
        mask = pd.Series([True] * len(grouped))
    else:
        mask = grouped["conditionName"].isin(selected_conditions)
    
    if status_choice != "All":
        mask &= (grouped["Status"] == status_choice)
    
    display_df = grouped[mask].copy()
    st.session_state.alerts = display_df.sort_values("start_time", ascending=False)
    st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts = pd.DataFrame()

# ---------------- MAIN DASHBOARD UI ----------------
st.markdown(f"<h1 class='main-header'>🔥 Quickplay Pulse</h1>", unsafe_allow_html=True)
st.markdown(f"**Viewing:** `{customer_selection}` | **Range:** `{time_label}`")

df = st.session_state.alerts

# KPI ROW
if status_choice in ["Active", "Closed"]:
    c1, c2 = st.columns(2)
    c1.metric(f"{status_choice} Alerts", len(df))
    c2.metric("Avg. Duration" if status_choice == "Active" else "Avg. Resolution Time", calculate_mttr(df))
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Alerts", len(df))
    c2.metric("Avg. Resolution (MTTR)", calculate_mttr(df))
    c3.metric("Resolution Rate", get_resolution_rate(df))

st.divider()

if df.empty:
    st.info(f"No alerts found matching your criteria. 🎉")
    st.stop()

# CLIENT TILES (ALL VIEW ONLY)
if customer_selection == "All Customers":
    st.subheader("Client Health Overview")
    counts = df["Customer"].value_counts()
    cols = st.columns(4)
    for i, (cust, cnt) in enumerate(counts.items()):
        with cols[i % 4]:
            if st.button(f"{cust}\n\n{cnt} Alerts", key=f"c_{cust}", use_container_width=True):
                st.session_state.navigate_to_customer = cust
                st.rerun()
    st.divider()

# INCIDENT LOG
st.subheader(f"📋 {status_choice} Alerts by Condition")
conditions_to_show = df["conditionName"].value_counts().index
for condition in conditions_to_show:
    cond_df = df[df["conditionName"] == condition]
    with st.expander(f"**{condition}** — {len(cond_df)} Alerts"):
        entity_summary = cond_df.groupby("Entity").size().reset_index(name="Alert Count")
        entity_summary = entity_summary.sort_values("Alert Count", ascending=False)
        st.dataframe(
            entity_summary, 
            hide_index=True, 
            use_container_width=True,
            column_config={"Alert Count": st.column_config.NumberColumn("Alerts", format="%d 🚨")}
        )

st.caption(f"Last sync: {st.session_state.updated} | Quickplay Internal Pulse")
