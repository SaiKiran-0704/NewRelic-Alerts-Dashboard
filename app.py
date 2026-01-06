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

    status_filter = st.radio(
        "Status",
        ["All", "Active", "Closed"],
        horizontal=True
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

def generate_summary(df):
    """Generate alert summary"""
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
    """Generate insights and recommendations"""
    if df.empty:
        return [], []
    
    insights = []
    recommendations = []
    
    total = len(df)
    active = len(df[df["Status"] == "Active"])
    critical = len(df[df["priority"] == "CRITICAL"])
    
    # Insights
    if active > 0:
        active_pct = (active / total) * 100
        insights.append(f"🔴 {active_pct:.0f}% of alerts are still active")
    
    if critical > 0:
        insights.append(f"⚠️ {critical} critical alerts detected")
    
    # Top condition
    if "conditionName" in df.columns and not df["conditionName"].empty:
        top_cond = df["conditionName"].value_counts().iloc[0]
        top_cond_name = df["conditionName"].value_counts().index[0]
        insights.append(f"📊 Top condition: '{top_cond_name}' ({top_cond} occurrences)")
    
    # Recommendations
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

    if status_filter != "All":
        grouped = grouped[grouped["Status"] == status_filter]

    st.session_state.alerts = grouped.sort_values("start_time", ascending=False)
    st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts = pd.DataFrame()

# ---------------- HEADER ----------------
st.markdown("## 🔥 Quickplay Alerts")
st.caption("Click a customer to drill down")
st.divider()

df = st.session_state.alerts
if df.empty:
    st.success("No alerts found 🎉")
    st.stop()

# ---------------- CUSTOMER DRILLDOWN ----------------
df_view = df
if st.session_state.clicked_customer:
    df_view = df[df["Customer"] == st.session_state.clicked_customer]
    st.info(f"📍 Viewing alerts for **{st.session_state.clicked_customer}**")
    if st.button("🔄 Reset to All Customers"):
        st.session_state.clicked_customer = None
        st.rerun()

# ---------------- KPIs ----------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Alerts", len(df_view))
c2.metric("Active Alerts", len(df_view[df_view["Status"] == "Active"]))
c3.metric("Resolved", len(df_view[df_view["Status"] == "Closed"]))
c4.metric("Critical", len(df_view[df_view["priority"] == "CRITICAL"]))

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

# ---------------- CUSTOMER CHART (CLICKABLE) ----------------
if customer == "All Customers":
    st.markdown("### Alerts by Customer (click to filter)")

    selection = alt.selection_point(encodings=["x"], name="select_customer")

    cust_chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("Customer", sort="-y"),
            y="count()",
            tooltip=["Customer", "count()"],
            color=alt.condition(selection, alt.value("#FF9F1C"), alt.value("#444"))
        )
        .add_params(selection)
        .properties(height=260)
    )

    event = st.altair_chart(cust_chart, use_container_width=True, on_select="rerun")

    if event.selection and "select_customer" in event.selection:
        sel = event.selection["select_customer"]
        if sel and "Customer" in sel[0]:
            st.session_state.clicked_customer = sel[0]["Customer"]
            st.rerun()

# ---------------- CONDITION CHART ----------------
st.markdown("### Alerts by Condition")

cond_chart = alt.Chart(df_view).mark_bar().encode(
    x=alt.X("conditionName", sort="-y", axis=alt.Axis(labelAngle=-40)),
    y="count()",
    tooltip=["conditionName", "count()"],
    color=alt.value("#FF9F1C")
).properties(height=300)

st.altair_chart(cond_chart, use_container_width=True)

st.divider()

# ---------------- ENTITY BREAKDOWN ----------------
st.markdown("### 🔎 Alert Breakdown by Entity")

for cond, cnt in df_view["conditionName"].value_counts().items():
    with st.expander(f"⚠️ {cond} ({cnt})"):
        subset = df_view[df_view["conditionName"] == cond]
        entity_df = subset["Entity"].value_counts().reset_index()
        entity_df.columns = ["Entity", "Alerts"]
        st.dataframe(entity_df, use_container_width=True, hide_index=True)

st.divider()

# ---------------- LIVE LOGS ----------------
st.markdown("### 📝 Live Alert Logs")

cols = ["start_time", "Customer", "Entity", "conditionName", "priority", "Status", "Duration"]

st.dataframe(
    df_view[cols].style.map(style_status, subset=["Status"]),
    use_container_width=True,
    hide_index=True
)
