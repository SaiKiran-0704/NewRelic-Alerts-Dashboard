import streamlit as st
import requests
import pandas as pd
import datetime
import altair as alt

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Quickplay Alerts",
    layout="wide",
    page_icon="🔥"
)

# ---------------- CUSTOM STYLING ----------------
st.markdown("""
<style>
body {
    background-color: #FF8C00;
}

.stApp { 
    background-color: #FF8C00;
}

.main-container {
    max-width: 1200px;
    margin: 0 auto;
    background-color: #FFFFFF;
    border-radius: 12px;
    padding: 30px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
}

#MainMenu, footer, header { 
    visibility: hidden; 
}

section[data-testid="stSidebar"] {
    display: none;
}

div[data-testid="stMetric"] {
    background-color: #F8F9FA;
    border: 1px solid #E0E0E0;
    border-radius: 8px;
    padding: 16px;
}

.stDataFrame {
    border: 1px solid #E0E0E0;
    border-radius: 8px;
}

.header-section {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 30px;
    border-bottom: 2px solid #FF8C00;
    padding-bottom: 20px;
}

.title-section {
    flex: 1;
}

.filters-section {
    display: flex;
    gap: 20px;
    align-items: flex-end;
}
</style>
""", unsafe_allow_html=True)

# Wrap main content
st.markdown('<div class="main-container">', unsafe_allow_html=True)

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

# ---------------- HEADER WITH FILTERS ----------------
col_title, col_filters = st.columns([2, 1])

with col_title:
    st.markdown("# 🔥 Quickplay SOC Alerts Overview")
    st.caption("Real-time alert monitoring and analysis")

with col_filters:
    st.markdown("### Filters")
    customer = st.selectbox(
        "Select Customer",
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

st.divider()

if customer != "All Customers":
    st.session_state.clicked_customer = None

# ---------------- HELPERS ----------------
def format_duration(td):
    s = int(td.total_seconds())
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d {h}h"
    return f"{h}h {m}m" if h else f"{m}m {s}s"

def style_status(v):
    return "color:#FF5C5C;font-weight:600" if v == "Active" else "color:#22A854;font-weight:600"

def count_alerts_for_period(name, api_key, account_id, time_clause):
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

def generate_summary(df):
    if df.empty:
        return "No alerts in this period"
    
    total = len(df)
    active = len(df[df["Status"] == "Active"])
    closed = len(df[df["Status"] == "Closed"])
    critical = len(df[df["priority"] == "CRITICAL"])
    
    summary = f"""**Alert Summary:**
- Total Alerts: {total}
- Active Now: {active}
- Resolved: {closed}
- Critical: {critical}"""
    return summary

def generate_insights(df):
    if df.empty:
        return [], []
    
    insights = []
    recommendations = []
    
    total = len(df)
    active = len(df[df["Status"] == "Active"])
    critical = len(df[df["priority"] == "CRITICAL"])
    
    if active > 0:
        active_pct = (active / total) * 100
        insights.append(f"🔴 {active_pct:.0f}% of alerts are still active")
    
    if critical > 0:
        insights.append(f"⚠️ {critical} critical alerts detected")
    
    if "conditionName" in df.columns and not df["conditionName"].empty:
        top_cond = df["conditionName"].value_counts().iloc[0]
        top_cond_name = df["conditionName"].value_counts().index[0]
        insights.append(f"📊 Top condition: '{top_cond_name}' ({top_cond} occurrences)")
    
    if active / total > 0.5:
        recommendations.append("📌 High active rate - consider tuning alert thresholds to reduce false positives")
    
    if critical / total > 0.2:
        recommendations.append("📌 Many critical alerts - review severity settings to prioritize real issues")
    
    if total > 20:
        recommendations.append("📌 High alert volume - implement grouping/deduplication rules")
    
    if recommendations == []:
        recommendations.append("✅ Alert conditions look well-tuned")
    
    return insights, recommendations

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

with st.spinner("📊 Loading alerts…"):
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

df = st.session_state.alerts
if df.empty:
    st.success("✅ No alerts found")
    st.stop()

# Filter view
df_view = df
if st.session_state.clicked_customer:
    df_view = df[df["Customer"] == st.session_state.clicked_customer]

# ---------------- KPIs ----------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Alerts", len(df_view))
col2.metric("Active Now", len(df_view[df_view["Status"] == "Active"]))
col3.metric("Resolved", len(df_view[df_view["Status"] == "Closed"]))
col4.metric("Critical", len(df_view[df_view["priority"] == "CRITICAL"]))

st.divider()

# ---------------- SUMMARY & INSIGHTS ----------------
st.markdown("### 📋 Alert Summary & Analysis")

col1, col2 = st.columns([1, 1])

with col1:
    st.markdown(generate_summary(df_view))

with col2:
    insights, recommendations = generate_insights(df_view)
    st.markdown("**Key Insights:**")
    for insight in insights:
        st.markdown(f"• {insight}")

st.markdown("**Recommendations:**")
for rec in recommendations:
    st.markdown(f"• {rec}")

st.divider()

# ---------------- COMPARISON ----------------
if st.session_state.clicked_customer:
    st.markdown("### 📈 Comparison: Last Week vs Last Month")
    
    cust_name = st.session_state.clicked_customer
    cfg = CLIENTS[cust_name]
    
    week_count = count_alerts_for_period(cust_name, cfg["api_key"], cfg["account_id"], "SINCE 7 days ago")
    month_count = count_alerts_for_period(cust_name, cfg["api_key"], cfg["account_id"], "SINCE 30 days ago")
    
    col1, col2 = st.columns(2)
    col1.metric("Last 7 Days", week_count)
    col2.metric("Last 30 Days", month_count)

    st.divider()
elif customer != "All Customers":
    st.markdown("### 📈 Comparison: Last Week vs Last Month")
    
    cust_name = customer
    cfg = CLIENTS[customer]
    
    week_count = count_alerts_for_period(cust_name, cfg["api_key"], cfg["account_id"], "SINCE 7 days ago")
    month_count = count_alerts_for_period(cust_name, cfg["api_key"], cfg["account_id"], "SINCE 30 days ago")
    
    col1, col2 = st.columns(2)
    col1.metric("Last 7 Days", week_count)
    col2.metric("Last 30 Days", month_count)

    st.divider()

# ---------------- CUSTOMER CHART ----------------
if customer == "All Customers":
    st.markdown("### Alerts by Customer")

    selection = alt.selection_point(encodings=["y"], name="select_customer")

    cust_chart = (
        alt.Chart(df)
        .mark_barh()
        .encode(
            y=alt.Y("Customer", sort="-x"),
            x="count()",
            tooltip=["Customer", "count()"],
            color=alt.condition(selection, alt.value("#FF8C00"), alt.value("#CCCCCC"))
        )
        .add_params(selection)
        .properties(height=250)
    )

    event = st.altair_chart(cust_chart, use_container_width=True, on_select="rerun")

    if event.selection and "select_customer" in event.selection:
        sel = event.selection["select_customer"]
        if sel and "Customer" in sel[0]:
            st.session_state.clicked_customer = sel[0]["Customer"]
            st.rerun()

# ---------------- CONDITION CHART ----------------
st.markdown("### Alerts by Condition")

cond_chart = alt.Chart(df_view).mark_barh().encode(
    y=alt.Y("conditionName", sort="-x"),
    x="count()",
    tooltip=["conditionName", "count()"],
    color=alt.value("#FF8C00")
).properties(height=300)

st.altair_chart(cond_chart, use_container_width=True)

st.divider()

# ---------------- ENTITY BREAKDOWN ----------------
st.markdown("### Alert Breakdown by Entity")

top_conditions = df_view["conditionName"].value_counts().head(5)
for cond, cnt in top_conditions.items():
    with st.expander(f"{cond} ({cnt})"):
        subset = df_view[df_view["conditionName"] == cond]
        entity_df = subset["Entity"].value_counts().head(10).reset_index()
        entity_df.columns = ["Entity", "Count"]
        st.dataframe(entity_df, use_container_width=True, hide_index=True)

st.markdown('</div>', unsafe_allow_html=True)
