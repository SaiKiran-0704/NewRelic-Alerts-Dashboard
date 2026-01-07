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

# ---------------- CLEAN UI STYLING ----------------
st.markdown("""
<style>
    .stApp { background-color:#0F1115; color:#E6E6E6; }
    .main-header { color: #F37021; font-weight: 800; margin-bottom: 0px; }
    .block-container { padding-top: 2rem; }
    
    /* KPI Card Style */
    div[data-testid="stMetric"] {
        background-color:#161B22;
        border: 1px solid #30363D;
        border-radius: 10px;
        padding: 15px;
    }
    
    /* Sidebar Style */
    section[data-testid="stSidebar"] {
        background-color:#151821;
        border-right:1px solid #2A2F3A;
    }

    /* Condition Group Headers */
    .stExpander {
        border: 1px solid #30363D !important;
        background-color: #111418 !important;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------- CONFIG & DATA ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

if "alerts" not in st.session_state: st.session_state.alerts = None
if "updated" not in st.session_state: st.session_state.updated = None
if "customer_filter" not in st.session_state: st.session_state.customer_filter = "All Customers"

# ---------------- HELPERS ----------------
def format_duration(td):
    s = int(td.total_seconds())
    if s < 60: return f"{s}s"
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"

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
        r = requests.post(ENDPOINT, json={"query": query}, headers={"API-Key": api_key})
        data = r.json()["data"]["actor"]["account"]["nrql"]["results"]
        df = pd.DataFrame(data)
        if not df.empty:
            df["Customer"] = name
            df.rename(columns={"entity.name": "Entity"}, inplace=True)
        return df
    except:
        return pd.DataFrame()

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("<h1 style='color:#F37021; font-size: 28px;'>🔥 quickplay</h1>", unsafe_allow_html=True)
    customer = st.selectbox("Client Selector", ["All Customers"] + list(CLIENTS.keys()), key="customer_filter")
    time_map = {"6h": "SINCE 6h ago", "24h": "SINCE 24h ago", "7d": "SINCE 7d ago"}
    time_label = st.selectbox("Time Window", list(time_map.keys()))
    time_clause = time_map[time_label]

# ---------------- DATA FETCH & PROCESS ----------------
all_rows = []
targets = CLIENTS.items() if customer == "All Customers" else [(customer, CLIENTS[customer])]

for name, cfg in targets:
    df_res = fetch_account(name, cfg["api_key"], cfg["account_id"], time_clause)
    if not df_res.empty: all_rows.append(df_res)

if all_rows:
    raw = pd.concat(all_rows)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], unit="ms")
    grouped = raw.groupby(["incidentId", "Customer", "conditionName", "priority", "Entity"]).agg(
        start_time=("timestamp", "min"),
        end_time=("timestamp", "max"),
        events=("event", "nunique")
    ).reset_index()
    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
    now = datetime.datetime.utcnow()
    grouped["Duration"] = grouped.apply(lambda r: format_duration((now - r.start_time) if r.Status == "Active" else (r.end_time - r.start_time)), axis=1)
    st.session_state.alerts = grouped.sort_values("start_time", ascending=False)
    st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts = pd.DataFrame()

# ---------------- MAIN DASHBOARD ----------------
st.markdown("<h1 class='main-header'>🔥 Quickplay Pulse</h1>", unsafe_allow_html=True)
df = st.session_state.alerts

if df is not None and not df.empty:
    # KPI Row
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Volume", len(df))
    active_df = df[df.Status == "Active"]
    c2.metric("Active Now", len(active_df), delta=len(active_df), delta_color="inverse")
    c3.metric("Unique Conditions", df["conditionName"].nunique())

    st.divider()

    # ---------------- ENTITY CONDITION GROUPS ----------------
    st.subheader("📋 Alerts by Condition Group")
    
    # Sort conditions by number of alerts (noisiest first)
    condition_counts = df["conditionName"].value_counts()
    
    for condition, count in condition_counts.items():
        # Filter data for this specific condition
        condition_df = df[df["conditionName"] == condition]
        
        # Color coding for the header
        has_active = "Active" in condition_df["Status"].values
        header_label = f"🔴 {condition} ({count})" if has_active else f"🟢 {condition} ({count})"
        
        with st.expander(header_label):
            # Displaying the specific entities impacted by this condition
            display_df = condition_df[["Status", "Customer", "Entity", "Duration", "start_time"]]
            st.dataframe(
                display_df.sort_values("Status"), 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "start_time": st.column_config.DatetimeColumn("Detected At", format="D MMM, HH:mm"),
                }
            )
else:
    st.success("No alerts found in this time range.")
