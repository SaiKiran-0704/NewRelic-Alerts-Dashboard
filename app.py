import streamlit as st
import requests
import pandas as pd
import datetime

# ... [PAGE CONFIG AND STYLING REMAIN THE SAME] ...

# Add this helper function for time calculations
def get_time_window_seconds(time_label):
    """Convert time label to seconds for calculating prior window"""
    windows = {
        "6 Hours": 6 * 3600,
        "24 Hours": 24 * 3600,
        "7 Days": 7 * 24 * 3600,
        "30 Days": 30 * 24 * 3600
    }
    return windows.get(time_label, 3600)

def calculate_percentage_change(current_count, prior_count):
    """Calculate percentage change between two periods"""
    if prior_count == 0:
        return None if current_count == 0 else 100.0
    return ((current_count - prior_count) / prior_count) * 100

# ... [EXISTING CONFIG AND HELPERS] ...

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

# ✨ NEW: Fetch prior period data for comparison
@st.cache_data(ttl=300)
def fetch_account_prior_period(name, api_key, account_id, time_label):
    """Fetch data from prior period for delta calculation"""
    window_seconds = get_time_window_seconds(time_label)
    # Prior period: same length, but shifted back
    prior_time_clause = f"SINCE {window_seconds * 2} seconds ago UNTIL {window_seconds} seconds ago"
    
    query = f"""
    {{ actor {{ account(id: {account_id}) {{
          nrql(query: "SELECT timestamp, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {prior_time_clause} LIMIT MAX") {{
            results
          }}
        }} }} }}
    """
    try:
        r = requests.post(ENDPOINT, json={"query": query}, headers={"API-Key": api_key}, timeout=15)
        data = r.json()["data"]["actor"]["account"]["nrql"]["results"]
        return pd.DataFrame(data) if data else pd.DataFrame()
    except:
        return pd.DataFrame()

# ... [SIDEBAR CODE REMAINS THE SAME] ...

# ✨ UPDATED: Load both current and prior period data
all_rows = []
all_rows_prior = []
targets = CLIENTS.items() if customer_selection == "All Customers" else [(customer_selection, CLIENTS.get(customer_selection, {}))]

with st.spinner("Syncing Pulse..."):
    for name, cfg in targets:
        if cfg:
            df_res = fetch_account(name, cfg["api_key"], cfg["account_id"], time_clause)
            if not df_res.empty: 
                all_rows.append(df_res)
            
            # ✨ NEW: Fetch prior period
            df_res_prior = fetch_account_prior_period(name, cfg["api_key"], cfg["account_id"], time_label)
            if not df_res_prior.empty:
                all_rows_prior.append(df_res_prior)

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
    
    # ✨ NEW: Process prior period for comparison
    if all_rows_prior:
        raw_prior = pd.concat(all_rows_prior)
        raw_prior["timestamp"] = pd.to_datetime(raw_prior["timestamp"], unit="ms")
        grouped_prior = raw_prior.groupby(["incidentId", "Customer", "conditionName", "priority", "Entity"]).agg(
            start_time=("timestamp", "min"),
            end_time=("timestamp", "max"),
            events=("event", "nunique")
        ).reset_index()
        grouped_prior["Status"] = grouped_prior["events"].apply(lambda x: "Active" if x == 1 else "Closed")
        
        if status_choice != "All":
            st.session_state.alerts_prior = grouped_prior[grouped_prior["Status"] == status_choice].copy()
        else:
            st.session_state.alerts_prior = grouped_prior.copy()
    else:
        st.session_state.alerts_prior = pd.DataFrame()
else:
    st.session_state.alerts = pd.DataFrame()
    st.session_state.alerts_prior = pd.DataFrame()

# ... [MAIN CONTENT HEADER] ...

st.markdown(f"<h1 class='main-header'>🔥 Quickplay Pulse</h1>", unsafe_allow_html=True)
st.markdown(f"**Viewing:** `{customer_selection}` | **Range:** `{time_label}`")

df = st.session_state.alerts
df_prior = st.session_state.alerts_prior if "alerts_prior" in st.session_state else pd.DataFrame()

# ✨ UPDATED: KPI ROW with delta indicators
if status_choice in ["Active", "Closed"]:
    c1, c2 = st.columns(2)
    
    # Calculate delta for current selection
    current_count = len(df)
    prior_count = len(df_prior) if not df_prior.empty else 0
    delta_pct = calculate_percentage_change(current_count, prior_count)
    
    c1.metric(
        f"{status_choice} Alerts",
        current_count,
        delta=f"{delta_pct:.1f}%" if delta_pct is not None else None,
        delta_color="inverse"  # inverse: green for decrease, red for increase
    )
    c2.metric("Avg. Duration" if status_choice == "Active" else "Avg. Resolution Time", calculate_mttr(df))
else:
    # Standard 3-column KPI for "All" view with deltas
    c1, c2, c3 = st.columns(3)
    
    # Calculate delta for Total Alerts
    current_count = len(df)
    prior_count = len(df_prior) if not df_prior.empty else 0
    delta_pct = calculate_percentage_change(current_count, prior_count)
    
    c1.metric(
        "Total Alerts",
        current_count,
        delta=f"{delta_pct:.1f}%" if delta_pct is not None else None,
        delta_color="inverse"  # inverse: green for decrease, red for increase
    )
    c2.metric("Avg. Resolution (MTTR)", calculate_mttr(df))
    c3.metric("Resolution Rate", get_resolution_rate(df))

st.divider()

if df.empty:
    st.info(f"No {status_choice.lower()} alerts found. 🎉")
    st.stop()

# ... [REST OF CODE REMAINS THE SAME] ...
