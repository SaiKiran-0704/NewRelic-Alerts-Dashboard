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

    /* KPI Card Refinement */
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
    closed = df[df["Status"] == "Closed"]
    if closed.empty: return "N/A"
    
    # Accurate MTTR calculation using vectorized timestamps
    durations = (closed['end_time'] - closed['start_time']).dt.total_seconds() / 60
    avg = durations.mean()
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

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("<h1 style='color:#F37021; font-size: 28px;'>🔥 quickplay</h1>", unsafe_allow_html=True)
    st.caption("Pulse Monitoring v1.1")
    st.divider()
    
    customer = st.selectbox(
        "Client Selector",
        ["All Customers"] + list(CLIENTS.keys()),
        key="customer_filter"
    )

    time_map = {
        "6 Hours": "SINCE 6 hours ago",
        "24 Hours": "SINCE 24 hours ago",
        "7 Days": "SINCE 7 days ago",
        "30 Days": "SINCE 30 days ago"
    }
    time_label = st.selectbox("Time Window", list(time_map.keys()))
    time_clause = time_map[time_label]

    if st.button("🔄 Force Refresh"):
        st.cache_data.clear()
        st.rerun()

    if st.session_state.updated:
        st.markdown(f"**Last Sync:** `{st.session_state.updated}`")

# ---------------- LOAD & PROCESS DATA ----------------
all_rows = []
targets = CLIENTS.items() if customer == "All Customers" else [(customer, CLIENTS[customer])]

with st.spinner("Syncing with New Relic..."):
    for name, cfg in targets:
        df_res = fetch_account(name, cfg["api_key"], cfg["account_id"], time_clause)
        if not df_res.empty: all_rows.append(df_res)

if all_rows:
    raw = pd.concat(all_rows)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], unit="ms")
    
    # Logic to collapse Open/Close events into single Incidents
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

# ---------------- MAIN CONTENT ----------------
st.markdown(f"<h1 class='main-header'>🔥 Quickplay Pulse</h1>", unsafe_allow_html=True)
st.markdown(f"**Viewing:** `{customer}` | **Range:** `{time_label}`")

df = st.session_state.alerts
if df.empty:
    st.success("All systems operational. No alerts found. 🎉")
    st.stop()

# ---------------- KPI ROW ----------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Alerts", len(df))
c2.metric("Active Alerts", len(df[df.Status == "Active"]))
c3.metric("Avg. Resolution (MTTR)", calculate_mttr(df))
c4.metric("Resolution Rate", get_resolution_rate(df))

st.divider()

# ---------------- CLIENT TILES ----------------
if customer == "All Customers":
    st.subheader("Client Health Overview")
    counts = df["Customer"].value_counts()
    cols = st.columns(4)
    for i, (cust, cnt) in enumerate(counts.items()):
        with cols[i % 4]:
            if st.button(f"{cust}\n\n{cnt} Alerts", key=f"c_{cust}", use_container_width=True):
                st.session_state.navigate_to_customer = cust
                st.rerun()
    st.divider()

# ---------------- HIERARCHICAL INCIDENT LOG ----------------
st.subheader("📋 Alerts by Condition & Entity")

# Group alerts by Condition Name
conditions = df.sort_values("Status")["conditionName"].unique()

for condition in conditions:
    cond_df = df[df["conditionName"] == condition]
    active_in_cond = len(cond_df[cond_df.Status == "Active"])
    status_icon = "🔴" if active_in_cond > 0 else "🟢"
    
    # Header for the Condition
    with st.expander(f"{status_icon} **{condition}** — {len(cond_df)} Total Alerts ({active_in_cond} Active)"):
        
        # Nested Table: Entity Breakdown
        st.markdown("### Entity Summary")
        entity_summary = cond_df.groupby("Entity").size().reset_index(name="Alert Count")
        entity_summary = entity_summary.sort_values("Alert Count", ascending=False)
        
        st.dataframe(
            entity_summary, 
            hide_index=True, 
            use_container_width=True,
            column_config={"Alert Count": st.column_config.NumberColumn(format="%d 🚨")}
        )
        
        # Detailed Incident List for this Condition
        st.markdown("### Incident History")
        st.dataframe(
            cond_df[["Status", "Customer", "Entity", "Duration", "start_time"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "start_time": st.column_config.DatetimeColumn("Detected At", format="D MMM, HH:mm"),
                "Status": st.column_config.TextColumn("Status")
            }
        )

# ---------------- FOOTER ----------------
st.caption(f"Pulse internal tool. Data cached for 5 minutes. Last sync: {st.session_state.updated}")
