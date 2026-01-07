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

# ---------------- ADVANCED VISUAL HIERARCHY (CSS) ----------------
st.markdown("""
<style>
    .stApp { background-color:#0F1115; color:#E6E6E6; }
    .main-header { color: #F37021; font-weight: 800; margin-bottom: 0px; }
    .block-container { padding-top: 2rem; }

    /* Key Metric Card Styling */
    div[data-testid="stMetric"] {
        background-color:#161B22;
        border: 1px solid #30363D;
        border-radius: 12px;
        padding: 20px !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }

    /* Make Primary Metric Number Prominent */
    div[data-testid="stMetricValue"] > div {
        font-size: 2.8rem !important;
        font-weight: 700 !important;
        color: #FFFFFF !important;
    }

    /* Reduce Secondary Label Size */
    div[data-testid="stMetricLabel"] > div > p {
        font-size: 0.9rem !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #8B949E !important;
    }

    /* Adjust Delta (Indicator) Size */
    div[data-testid="stMetricDelta"] > div {
        font-size: 0.9rem !important;
        font-weight: 500;
    }
    
    .streamlit-expanderHeader {
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
        border-radius: 5px;
        font-size: 1rem;
        font-weight: 500;
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
def get_dynamic_avg_value(count, time_label):
    if count == 0: return 0.0
    if "Hours" in time_label:
        units = int(time_label.split()[0])
        return count / units
    elif "24 Hours" in time_label:
        return count / 24
    elif "7 Days" in time_label:
        return count / 7
    elif "30 Days" in time_label:
        return count / 4 
    return float(count)

def get_resolution_rate(df):
    if df.empty: return 0
    return (len(df[df.Status=='Closed'])/len(df))*100

def calculate_percent_delta(current, previous):
    if previous == 0:
        return f"+100%" if current > 0 else "0%"
    diff = ((current - previous) / previous) * 100
    return f"{diff:+.1f}%"

@st.cache_data(ttl=300)
def fetch_account_with_history(name, api_key, account_id, time_label):
    time_map_history = {
        "6 Hours": ("SINCE 6 hours ago", "SINCE 12 hours ago UNTIL 6 hours ago"),
        "24 Hours": ("SINCE 24 hours ago", "SINCE 48 hours ago UNTIL 24 hours ago"),
        "7 Days": ("SINCE 7 days ago", "SINCE 14 days ago UNTIL 7 days ago"),
        "30 Days": ("SINCE 30 days ago", "SINCE 60 days ago UNTIL 30 days ago")
    }
    curr_clause, prev_clause = time_map_history[time_label]
    
    query = f"""
    {{ actor {{ account(id: {account_id}) {{
          current: nrql(query: "SELECT timestamp, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {curr_clause} LIMIT MAX") {{
            results
          }}
          previous: nrql(query: "SELECT count(*) FROM NrAiIncident WHERE event = 'open' {prev_clause}") {{
            results
          }}
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
    st.caption("Pulse Monitoring v2.1")
    st.divider()
    
    customer_selection = st.selectbox(
        "Client Selector",
        ["All Customers"] + list(CLIENTS.keys()),
        key="customer_filter"
    )

    status_choice = st.radio("Alert Status", ["All", "Active", "Closed"], horizontal=True)

    time_labels = ["6 Hours", "24 Hours", "7 Days", "30 Days"]
    time_label = st.selectbox("Time Window", time_labels)

    if st.button("🔄 Force Refresh"):
        st.cache_data.clear()
        st.rerun()

# ---------------- LOAD & PROCESS DATA ----------------
all_rows = []
total_prev_count = 0
targets = CLIENTS.items() if customer_selection == "All Customers" else [(customer_selection, CLIENTS.get(customer_selection, {}))]

with st.spinner("Syncing Pulse Trends..."):
    for name, cfg in targets:
        if cfg:
            df_res, p_count = fetch_account_with_history(name, cfg["api_key"], cfg["account_id"], time_label)
            if not df_res.empty: all_rows.append(df_res)
            total_prev_count += p_count

if all_rows:
    raw = pd.concat(all_rows)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], unit="ms")
    
    grouped = raw.groupby(["incidentId", "Customer", "conditionName", "priority", "Entity"]).agg(
        start_time=("timestamp", "min"),
        end_time=("timestamp", "max"),
        events=("event", "nunique")
    ).reset_index()
    
    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
    
    if status_choice != "All":
        display_df = grouped[grouped["Status"] == status_choice].copy()
    else:
        display_df = grouped.copy()

    st.session_state.alerts = display_df.sort_values("start_time", ascending=False)
    st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts = pd.DataFrame()

# ---------------- MAIN CONTENT ----------------
st.markdown(f"<h1 class='main-header'>🔥 Quickplay Pulse</h1>", unsafe_allow_html=True)
st.markdown(f"Viewing: {customer_selection} | Range: {time_label}")

df = st.session_state.alerts

# ---------------- PROMINENT KPI ROW ----------------
# UI Diagram showing Hierarchy: 
card_titles = {
    "6 Hours": "Avg Alerts per Hour",
    "24 Hours": "Avg Alerts per Hour",
    "7 Days": "Avg Alerts per Day",
    "30 Days": "Avg Alerts per Week"
}
card_title = card_titles.get(time_label, "Avg Alerts")

curr_total = len(df)
curr_avg = get_dynamic_avg_value(curr_total, time_label)
prev_avg = get_dynamic_avg_value(total_prev_count, time_label)
res_rate = get_resolution_rate(df)

total_delta_pct = calculate_percent_delta(curr_total, total_prev_count)
avg_delta_pct = calculate_percent_delta(curr_avg, prev_avg)

# Display Metrics
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Total Alerts", curr_total, delta=total_delta_pct, delta_color="inverse")
with c2:
    st.metric(card_title, f"{curr_avg:.1f}", delta=avg_delta_pct, delta_color="inverse")
with c3:
    st.metric("Resolution Rate", f"{res_rate:.0f}%")

st.divider()

if df.empty:
    st.info(f"No {status_choice.lower()} alerts found.")
    st.stop()

# ---------------- CLIENT TILES ----------------
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

# ---------------- INCIDENT LOG ----------------
st.subheader(f"Log: {status_choice} Alerts by Condition")

conditions = df["conditionName"].value_counts().index
for condition in conditions:
    cond_df = df[df["conditionName"] == condition]
    with st.expander(f"{condition} - {len(cond_df)} Alerts"):
        entity_summary = cond_df.groupby("Entity").size().reset_index(name="Alert Count")
        entity_summary = entity_summary.sort_values("Alert Count", ascending=False)
        st.dataframe(
            entity_summary, 
            hide_index=True, 
            use_container_width=True,
            column_config={
                "Alert Count": st.column_config.NumberColumn("Alerts", format="%d 🚨")
            }
        )

st.caption(f"Last sync: {st.session_state.updated} | Quickplay Internal Pulse")
