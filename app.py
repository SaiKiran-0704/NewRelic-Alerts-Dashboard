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
    section[data-testid="stSidebar"] { background-color:#151821; border-right:1px solid #2A2F3A; }
    .stExpander { border: 1px solid #30363D !important; background-color: #161B22 !important; }
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
    # Added entity.type to the SELECT statement
    query = f"""
    {{ actor {{ account(id: {account_id}) {{
          nrql(query: "SELECT timestamp, conditionName, priority, incidentId, event, entity.name, entity.type FROM NrAiIncident WHERE event IN ('open','close') {time_clause} LIMIT MAX") {{
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
            # Cleanup naming
            df.rename(columns={"entity.name": "Entity", "entity.type": "Type"}, inplace=True)
            # Handle missing types
            df["Type"] = df["Type"].fillna("Other")
        return df
    except Exception:
        return pd.DataFrame()

# ---------------- DATA PROCESSING ----------------
with st.sidebar:
    st.markdown("<h1 style='color:#F37021; font-size: 28px;'>🔥 quickplay</h1>", unsafe_allow_html=True)
    customer = st.selectbox("Client Selector", ["All Customers"] + list(CLIENTS.keys()), key="customer_filter")
    time_map = {"6h": "SINCE 6h ago", "24h": "SINCE 24h ago", "7d": "SINCE 7d ago"}
    time_label = st.selectbox("Time Window", list(time_map.keys()))
    time_clause = time_map[time_label]

all_rows = []
targets = CLIENTS.items() if customer == "All Customers" else [(customer, CLIENTS[customer])]

for name, cfg in targets:
    df_res = fetch_account(name, cfg["api_key"], cfg["account_id"], time_clause)
    if not df_res.empty: all_rows.append(df_res)

if all_rows:
    raw = pd.concat(all_rows)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], unit="ms")
    # Group including 'Type'
    grouped = raw.groupby(["incidentId", "Customer", "conditionName", "priority", "Entity", "Type"]).agg(
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

# ---------------- MAIN UI ----------------
st.markdown("<h1 class='main-header'>🔥 Quickplay Pulse</h1>", unsafe_allow_html=True)
df = st.session_state.alerts

if df is not None and not df.empty:
    # KPI Row
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Alerts", len(df))
    c2.metric("Active Now", len(df[df.Status == "Active"]))
    c3.metric("Entity Groups", df["Type"].nunique())

    st.divider()

    # ---------------- ENTITY GROUPING VIEW ----------------
    st.subheader("📁 Alerts by Entity Type")
    
    # Create an expander for each entity type (e.g., HOST, APPLICATION, SYNTHETIC)
    for ent_type, type_df in df.groupby("Type"):
        with st.expander(f"{ent_type} ({len(type_df)} Alerts)"):
            # Sub-table for this group
            display_cols = ["Status", "Customer", "Entity", "conditionName", "Duration"]
            st.dataframe(
                type_df[display_cols],
                use_container_width=True,
                hide_index=True
            )
else:
    st.success("No alerts found for this selection.")
