import streamlit as st
import requests
import pandas as pd
import datetime
import altair as alt

# ---- MUST BE FIRST ----
st.set_page_config(
    page_title="Quickplay Alerts",
    layout="wide",
    page_icon="🔥"
)

# ---------------- CLEAN UI ----------------
st.markdown("""
<style>
.stApp { background-color:#0F1115; color:#E6E6E6; }
#MainMenu, footer, header { visibility:hidden; }

section[data-testid="stSidebar"] {
    background-color:#151821;
    border-right:1px solid #2A2F3A;
}

div[data-testid="stMetric"] {
    background-color:#151821;
    border:1px solid #2A2F3A;
    border-radius:10px;
    padding:16px;
}

.stDataFrame {
    border:1px solid #2A2F3A;
    border-radius:8px;
}
</style>
""", unsafe_allow_html=True)

# ---------------- CONFIG ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

# ---------------- SESSION STATE ----------------
if "alerts" not in st.session_state:
    st.session_state.alerts = None
if "updated" not in st.session_state:
    st.session_state.updated = None
if "clicked_customer" not in st.session_state:
    st.session_state.clicked_customer = None

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("### Filters")

    customer = st.selectbox(
        "Customer",
        ["All Customers"] + list(CLIENTS.keys()),
        key="customer_filter"
    )

    time_map = {
        "Last 6 Hours": "SINCE 6 hours ago",
        "Last 24 Hours": "SINCE 24 hours ago",
        "Last 7 Days": "SINCE 7 days ago",
        "Last 1 Month": "SINCE 30 days ago",
        "Last 3 Months": "SINCE 90 days ago"
    }
    time_label = st.selectbox("Time Range", list(time_map.keys()))
    time_clause = time_map[time_label]

    if st.session_state.updated:
        st.caption(f"Updated at {st.session_state.updated}")

# Reset click selection when dropdown changes
if customer != "All Customers":
    st.session_state.clicked_customer = None

# ---------------- HELPERS ----------------
def format_duration(td):
    s = int(td.total_seconds())
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"

def style_status(v):
    return "color:#FF5C5C;font-weight:600" if v == "Active" else "color:#6EE7B7;font-weight:600"

def count_alerts_for_period(name, api_key, account_id, time_clause):
    """Count total alerts for a given time period"""
    query = f"""
    {{
      actor {{
        account(id: {account_id}) {{
          nrql(query: "SELECT count(DISTINCT incidentId) FROM NrAiIncident WHERE event IN ('open','close') {time_clause}") {{
            results
          }}
        }}
      }}
    }}
    """
    try:
        r = requests.post(
            ENDPOINT,
            json={"query": query},
            headers={"API-Key": api_key}
        )
        result = r.json()
        if "data" in result and result["data"]["actor"]["account"]["nrql"]["results"]:
            return result["data"]["actor"]["account"]["nrql"]["results"][0].get("count", 0)
    except:
        pass
    return 0

def calculate_mttr(df):
    """Calculate Mean Time To Resolution"""
    if df.empty:
        return "N/A"
    
    closed_alerts = df[df["Status"] == "Closed"]
    if len(closed_alerts) == 0:
        return "No resolved alerts yet"
    
    durations = []
    for duration_str in closed_alerts["Duration"]:
        try:
            total_minutes = 0
            parts = duration_str.split()
            for i, part in enumerate(parts):
                if 'd' in part:
                    total_minutes += int(part.replace('d', '')) * 1440
                elif 'h' in part:
                    total_minutes += int(part.replace('h', '')) * 60
                elif 'm' in part:
                    total_minutes += int(part.replace('m', ''))
                elif 's' in part:
                    total_minutes += int(part.replace('s', '')) / 60
            durations.append(total_minutes)
        except:
            pass
    
    if durations:
        avg_minutes = sum(durations) / len(durations)
        hours = int(avg_minutes // 60)
        minutes = int(avg_minutes % 60)
        return f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
    return "N/A"

def get_alert_frequency(df, time_label):
    """Calculate alerts per hour/day based on time period"""
    if df.empty:
        return "N/A"
    
    total_alerts = len(df)
    
    if "6 Hours" in time_label:
        freq = total_alerts / 6
        return f"{freq:.1f} per hour"
    elif "24 Hours" in time_label:
        freq = total_alerts / 24
        return f"{freq:.1f} per hour"
    elif "7 Days" in time_label:
        freq = total_alerts / 7
        return f"{freq:.1f} per day"
    elif "1 Month" in time_label:
        freq = total_alerts / 30
        return f"{freq:.1f} per day"
    elif "3 Months" in time_label:
        freq = total_alerts / 90
        return f"{freq:.1f} per day"
    
    return f"{total_alerts} total"

def get_resolution_rate(df):
    """Calculate % of alerts that have been resolved"""
    if df.empty:
        return "0%"
    
    total = len(df)
    resolved = len(df[df["Status"] == "Closed"])
    rate = (resolved / total) * 100
    return f"{rate:.0f}%"

def get_top_3_entities(df):
    """Get top 3 most affected entities"""
    if df.empty or "Entity" not in df.columns:
        return []
    
    top_entities = df["Entity"].value_counts().head(3)
    result = []
    for entity, count in top_entities.items():
        result.append((entity, count))
    return result

def calculate_alert_trend(df_current, time_label):
    """Calculate trend compared to previous period"""
    if df_current.empty:
        return "N/A"
    
    current_count = len(df_current)
    
    if current_count > 100:
        return "High volume"
    elif current_count > 50:
        return "Moderate volume"
    else:
        return "Low volume"

def generate_better_insights(df, time_label):
    """Generate improved insights with better metrics"""
    if df.empty:
        return {
            "mttr": "N/A",
            "frequency": "N/A",
            "resolution_rate": "0%",
            "top_entities": [],
            "trend": "N/A",
            "recommendations": ["No alerts in this period"]
        }
    
    total = len(df)
    active = len(df[df["Status"] == "Active"])
    resolved = len(df[df["Status"] == "Closed"])
    
    top_condition = "N/A"
    if "conditionName" in df.columns and not df["conditionName"].empty:
        top_cond = df["conditionName"].value_counts().iloc[0]
        top_condition = df["conditionName"].value_counts().index[0]
    
    recommendations = []
    
    if active / total > 0.5:
        recommendations.append("🎯 High active rate (>50%) - Consider tuning alert thresholds")
    
    if top_condition != "N/A":
        top_count = df["conditionName"].value_counts().iloc[0]
        if top_count > total * 0.3:
            recommendations.append(f"🎯 '{top_condition}' causes {(top_count/total)*100:.0f}% of alerts - Needs investigation")
    
    if len(recommendations) == 0:
        recommendations.append("✅ Alert conditions look well-tuned")
    
    return {
        "mttr": calculate_mttr(df),
        "frequency": get_alert_frequency(df, time_label),
        "resolution_rate": get_resolution_rate(df),
        "top_entities": get_top_3_entities(df),
        "trend": calculate_alert_trend(df, time_label),
        "top_condition": top_condition,
        "recommendations": recommendations
    }

@st.cache_data(ttl=300)
def fetch_account(name, api_key, account_id, time_clause):
    query = f"""
    {{
      actor {{
        account(id: {account_id}) {{
          nrql(query: "SELECT timestamp, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {time_clause} LIMIT MAX") {{
            results
          }}
        }}
      }}
    }}
    """
    r = requests.post(
        ENDPOINT,
        json={"query": query},
        headers={"API-Key": api_key}
    )
    df = pd.DataFrame(r.json()["data"]["actor"]["account"]["nrql"]["results"])
    if not df.empty:
        df["Customer"] = name
        df.rename(columns={"entity.name": "Entity"}, inplace=True)
    return df

# ---------------- LOAD DATA ----------------
all_rows = []
targets = CLIENTS.items() if customer == "All Customers" else [(customer, CLIENTS[customer])]

with st.spinner("Loading alerts…"):
    for name, cfg in targets:
        df = fetch_account(name, cfg["api_key"], cfg["account_id"], time_clause)
        if not df.empty:
            all_rows.append(df)

if all_rows:
    raw = pd.concat(all_rows)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], unit="ms")

    grouped = raw.groupby(
        ["incidentId", "Customer", "conditionName", "priority", "Entity"]
    ).agg(
        start_time=("timestamp", "min"),
        end_time=("timestamp", "max"),
        events=("event", "nunique")
    ).reset_index()

    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")

    now = datetime.datetime.utcnow()
    grouped["Duration"] = grouped.apply(
        lambda r: format_duration(
            (now - r.start_time) if r.Status == "Active" else (r.end_time - r.start_time)
        ),
        axis=1
    )

    st.session_state.alerts = grouped.sort_values("start_time", ascending=False)
    st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts = pd.DataFrame()

# ---------------- HEADER ----------------
st.markdown("## 🔥 Quickplay Alerts")
st.divider()

# ---- FILTERS IN MAIN AREA ----
col1, col2 = st.columns(2)

with col1:
    customer = st.selectbox(
        "Select Customer",
        ["All Customers"] + list(CLIENTS.keys()),
        key="customer_filter_main"
    )

with col2:
    time_map = {
        "Last 6 Hours": "SINCE 6 hours ago",
        "Last 24 Hours": "SINCE 24 hours ago",
        "Last 7 Days": "SINCE 7 days ago",
        "Last 1 Month": "SINCE 30 days ago",
        "Last 3 Months": "SINCE 90 days ago"
    }
    time_label = st.selectbox("Select Time Range", list(time_map.keys()))
    time_clause = time_map[time_label]

st.divider()

df = st.session_state.alerts
if df.empty:
    st.success("No alerts found 🎉")
    st.stop()

# ---- CUSTOMER DRILLDOWN ----
df_view = df
if st.session_state.clicked_customer:
    df_view = df[df["Customer"] == st.session_state.clicked_customer]
    col1, col2 = st.columns([4, 1])
    with col1:
        st.info(f"📍 Viewing alerts for **{st.session_state.clicked_customer}**")
    with col2:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.clicked_customer = None
            st.rerun()

# ---------------- KPIs ----------------
c1, c2 = st.columns(2)
c1.metric("Total Alerts", len(df_view))
c2.metric("Active Alerts", len(df_view[df_view["Status"] == "Active"]))

st.divider()

# ---------------- SUMMARY & INSIGHTS ----------------
st.markdown("### 📊 Alert Metrics & Analysis")

metrics = generate_better_insights(df_view, time_label)

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Mean Time to Resolve", metrics["mttr"])
    st.metric("Alert Frequency", metrics["frequency"])

with col2:
    st.metric("Resolution Rate", metrics["resolution_rate"])
    st.metric("Volume Status", metrics["trend"])

with col3:
    st.markdown("**Top Affected Entities:**")
    if metrics["top_entities"]:
        for entity, count in metrics["top_entities"]:
            st.markdown(f"• {entity}: {count} alerts")
    else:
        st.markdown("• No entity data available")

st.divider()

st.markdown("**Top Alert Condition:**")
if metrics["top_condition"] != "N/A":
    st.markdown(f"🔔 **{metrics['top_condition']}**")
else:
    st.markdown("No conditions detected")

st.markdown("**Recommendations:**")
for rec in metrics["recommendations"]:
    st.markdown(f"• {rec}")

st.divider()

st.divider()

# ---- SHOW CARDS AND ANALYTICS WHEN "ALL CUSTOMERS" ----
if not st.session_state.clicked_customer and customer == "All Customers":
    
    # Alerts by Customer Cards
    st.markdown("### Alerts by Customer")
    
    customer_counts = df["Customer"].value_counts().sort_values(ascending=False)
    
    cols_per_row = 3
    
    for i in range(0, len(customer_counts), cols_per_row):
        cols = st.columns(cols_per_row)
        
        for j, (cust_name, count) in enumerate(list(customer_counts.items())[i:i+cols_per_row]):
            with cols[j]:
                if st.button(
                    f"",
                    key=f"card_{cust_name}",
                    use_container_width=True,
                    help=f"Click to view {cust_name} details"
                ):
                    st.session_state.clicked_customer = cust_name
                    st.rerun()
                
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #FF9F1C 0%, #FF8C00 100%);
                    border-radius: 12px;
                    padding: 20px;
                    text-align: center;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                    color: white;
                    min-height: 200px;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                ">
                    <div style="font-size: 32px; font-weight: bold; margin-bottom: 10px;">{count}</div>
                    <div style="font-size: 12px; opacity: 0.9;">Alerts</div>
                    <div style="font-size: 16px; font-weight: bold; margin-top: 20px;">{cust_name}</div>
                </div>
                """, unsafe_allow_html=True)
    
    st.divider()
    
    # Show overall analytics for all customers
    st.markdown("### 📊 Alert Metrics & Analysis (All Customers)")
    
    metrics = generate_better_insights(df_view, time_label)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Mean Time to Resolve", metrics["mttr"])
        st.metric("Alert Frequency", metrics["frequency"])
    
    with col2:
        st.metric("Resolution Rate", metrics["resolution_rate"])
        st.metric("Volume Status", metrics["trend"])
    
    with col3:
        st.markdown("**Top Affected Entities:**")
        if metrics["top_entities"]:
            for entity, count in metrics["top_entities"]:
                st.markdown(f"• {entity}: {count} alerts")
        else:
            st.markdown("• No entity data available")
    
    st.divider()
    
    st.markdown("**Top Alert Condition:**")
    if metrics["top_condition"] != "N/A":
        st.markdown(f"🔔 **{metrics['top_condition']}**")
    else:
        st.markdown("No conditions detected")
    
    st.markdown("**Recommendations:**")
    for rec in metrics["recommendations"]:
        st.markdown(f"• {rec}")
    
    st.divider()

# ---------------- ENTITY BREAKDOWN ----------------
st.markdown("### Alert Details by Condition")

top_conditions = df_view["conditionName"].value_counts()
for cond, cnt in top_conditions.items():
    with st.expander(f"{cond} ({cnt})"):
        subset = df_view[df_view["conditionName"] == cond]
        entity_summary = subset.groupby("Entity").size().reset_index(name="Count")
        entity_summary = entity_summary.sort_values("Count", ascending=False)
        st.dataframe(entity_summary, use_container_width=True, hide_index=True)
