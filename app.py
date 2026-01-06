import streamlit as st
import requests
import pandas as pd
import datetime
import altair as alt
import json

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Quickplay Alerts",
    layout="wide",
    page_icon="🔥"
)

# ---------------- CLEAN UI ----------------
st.markdown("""
<style>
.stApp { 
    background-color: #FFFFFF; 
    color: #1A1A1A; 
}
#MainMenu, footer, header { 
    visibility: hidden; 
}

section[data-testid="stSidebar"] {
    background-color: #F8F9FA;
    border-right: 1px solid #E0E0E0;
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

.insight-box {
    background-color: #E8F4F8;
    border-left: 4px solid #0088CC;
    padding: 12px;
    border-radius: 4px;
    margin: 8px 0;
}

.warning-box {
    background-color: #FFF4E6;
    border-left: 4px solid #FF9F1C;
    padding: 12px;
    border-radius: 4px;
    margin: 8px 0;
}

.success-box {
    background-color: #E6F7ED;
    border-left: 4px solid #6EE7B7;
    padding: 12px;
    border-radius: 4px;
    margin: 8px 0;
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
    st.markdown("### ⚙️ Filters")

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
        st.caption(f"🔄 Updated: {st.session_state.updated}")

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

@st.cache_data(ttl=300)
def fetch_comparison_data(name, api_key, account_id):
    """Fetch data for last week and last month"""
    periods = {
        "Last 7 Days": "SINCE 7 days ago",
        "Last 30 Days": "SINCE 30 days ago"
    }
    
    result = {}
    for period, clause in periods.items():
        query = f"""
        {{
          actor {{
            account(id: {account_id}) {{
              nrql(query: "SELECT timestamp, incidentId, event FROM NrAiIncident WHERE event IN ('open','close') {clause} LIMIT MAX") {{
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
            result[period] = len(df.groupby("incidentId").size())
        else:
            result[period] = 0
    return result

def generate_insights(df, customer_name):
    """Generate AI-like insights from alert data"""
    insights = []
    
    if df.empty:
        return ["No alerts in this period"]
    
    # Most problematic condition
    top_condition = df["conditionName"].value_counts().head(1)
    if len(top_condition) > 0:
        insights.append(f"🔴 **Top Issue:** '{top_condition.index[0]}' with {top_condition.values[0]} alerts")
    
    # Priority distribution
    high_priority = len(df[df["priority"] == "CRITICAL"])
    if high_priority > 0:
        insights.append(f"⚠️ **Critical Priority:** {high_priority} critical incidents detected")
    
    # Status distribution
    active_count = len(df[df["Status"] == "Active"])
    if active_count > 0:
        pct = (active_count / len(df)) * 100
        insights.append(f"🚨 **Currently Active:** {active_count} alerts ({pct:.0f}%)")
    else:
        insights.append(f"✅ **All Resolved:** All {len(df)} incidents have been closed")
    
    # Most affected entity
    if "Entity" in df.columns:
        top_entity = df["Entity"].value_counts().head(1)
        if len(top_entity) > 0:
            insights.append(f"📌 **Most Affected:** {top_entity.index[0]} ({top_entity.values[0]} alerts)")
    
    return insights

def generate_recommendations(df):
    """Generate improvement suggestions"""
    recommendations = []
    
    if df.empty:
        return recommendations
    
    active_count = len(df[df["Status"] == "Active"])
    total = len(df)
    
    if active_count / total > 0.5:
        recommendations.append("🎯 Consider tuning alert thresholds - high active alert rate suggests potential alert fatigue")
    
    high_priority = len(df[df["priority"] == "CRITICAL"])
    if high_priority > total * 0.3:
        recommendations.append("🎯 Review CRITICAL alert definitions - adjust severity levels to reduce noise")
    
    if "conditionName" in df.columns:
        condition_counts = df["conditionName"].value_counts()
        if len(condition_counts) > 0 and condition_counts.iloc[0] > total * 0.5:
            recommendations.append(f"🎯 Investigate '{condition_counts.index[0]}' - it's causing {condition_counts.iloc[0]} alerts. Consider adding auto-remediation")
    
    return recommendations

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

    if status_filter != "All":
        grouped = grouped[grouped["Status"] == status_filter]

    st.session_state.alerts = grouped.sort_values("start_time", ascending=False)
    st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts = pd.DataFrame()

# ---------------- HEADER ----------------
st.markdown("# 🔥 Quickplay Alerts")
st.markdown(f"**Time Period:** {time_label}")
st.divider()

df = st.session_state.alerts
if df.empty:
    st.success("✅ No alerts found")
    st.stop()

# ---------------- CUSTOMER DRILLDOWN ----------------
df_view = df
if st.session_state.clicked_customer:
    df_view = df[df["Customer"] == st.session_state.clicked_customer]
    st.info(f"📍 Viewing **{st.session_state.clicked_customer}**")
    if st.button("🔄 Reset"):
        st.session_state.clicked_customer = None
        st.rerun()

# ---------------- KPIs ----------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Alerts", len(df_view), delta=None)
col2.metric("Active Now", len(df_view[df_view["Status"] == "Active"]), delta=None)
col3.metric("Resolved", len(df_view[df_view["Status"] == "Closed"]), delta=None)
col4.metric("Critical", len(df_view[df_view["priority"] == "CRITICAL"]), delta=None)

st.divider()

# ---------------- INSIGHTS SECTION ----------------
st.markdown("### 📊 Alert Summary & Insights")

col1, col2 = st.columns([1, 1])

with col1:
    st.markdown("**Key Findings:**")
    for insight in generate_insights(df_view, customer):
        st.markdown(f"<div class='insight-box'>{insight}</div>", unsafe_allow_html=True)

with col2:
    st.markdown("**Improvement Recommendations:**")
    recs = generate_recommendations(df_view)
    if recs:
        for rec in recs:
            st.markdown(f"<div class='warning-box'>{rec}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='success-box'>✅ Alert conditions look well-tuned</div>", unsafe_allow_html=True)

st.divider()

# ---------------- COMPARISON ----------------
if customer != "All Customers":
    st.markdown("### 📈 Historical Comparison")
    
    comparison = fetch_comparison_data(
        customer,
        CLIENTS[customer]["api_key"],
        CLIENTS[customer]["account_id"]
    )
    
    col1, col2 = st.columns(2)
    col1.metric("Last 7 Days", comparison.get("Last 7 Days", 0))
    col2.metric("Last 30 Days", comparison.get("Last 30 Days", 0))
    
    st.divider()

# ---------------- CUSTOMER CHART ----------------
if customer == "All Customers":
    st.markdown("### Alerts by Customer")

    selection = alt.selection_point(encodings=["x"], name="select_customer")

    cust_chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("Customer", sort="-y"),
            y="count()",
            tooltip=["Customer", "count()"],
            color=alt.condition(selection, alt.value("#0088CC"), alt.value("#CCCCCC"))
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

cond_chart = alt.Chart(df_view).mark_bar().encode(
    x=alt.X("conditionName", sort="-y", axis=alt.Axis(labelAngle=-30)),
    y="count()",
    tooltip=["conditionName", "count()"],
    color=alt.value("#FF9F1C")
).properties(height=250)

st.altair_chart(cond_chart, use_container_width=True)

st.divider()

# ---------------- ENTITY BREAKDOWN ----------------
st.markdown("### Alert Breakdown")

for cond, cnt in df_view["conditionName"].value_counts().items():
    with st.expander(f"{cond} ({cnt})"):
        subset = df_view[df_view["conditionName"] == cond]
        entity_df = subset["Entity"].value_counts().reset_index()
        entity_df.columns = ["Entity", "Count"]
        st.dataframe(entity_df, use_container_width=True, hide_index=True)

st.divider()

# ---------------- LOGS ----------------
st.markdown("### Live Alert Logs")

cols = ["start_time", "Customer", "Entity", "conditionName", "priority", "Status", "Duration"]

st.dataframe(
    df_view[cols].style.map(style_status, subset=["Status"]),
    use_container_width=True,
    hide_index=True
)
