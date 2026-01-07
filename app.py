import streamlit as st
import requests
import pandas as pd
import datetime

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
if "customer_filter" not in st.session_state:
    st.session_state.customer_filter = "All Customers"
if "navigate_to_customer" not in st.session_state:
    st.session_state.navigate_to_customer = None

# -------- SAFE NAVIGATION (MUST BE BEFORE SIDEBAR) --------
if st.session_state.navigate_to_customer:
    st.session_state.customer_filter = st.session_state.navigate_to_customer
    st.session_state.navigate_to_customer = None

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

# ---------------- HELPERS ----------------
def format_duration(td):
    s = int(td.total_seconds())
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"

def calculate_mttr(df):
    closed = df[df["Status"] == "Closed"]
    if closed.empty:
        return "N/A"
    mins = []
    for d in closed["Duration"]:
        total = 0
        for p in d.split():
            if "h" in p:
                total += int(p.replace("h","")) * 60
            elif "m" in p:
                total += int(p.replace("m",""))
        mins.append(total)
    avg = sum(mins) / len(mins)
    return f"{int(avg//60)}h {int(avg%60)}m" if avg >= 60 else f"{int(avg)}m"

def get_resolution_rate(df):
    if df.empty:
        return "0%"
    return f"{(len(df[df.Status=='Closed'])/len(df))*100:.0f}%"

def generate_alert_summary(df, customer_name):
    if df.empty:
        return "### 🧠 Alert Summary\n\nNo alerts detected in this period."

    total = len(df)
    active = len(df[df["Status"] == "Active"])
    resolved = total - active

    top_condition = df["conditionName"].value_counts().idxmax()
    top_entity = df["Entity"].value_counts().idxmax()

    active_ratio = active / total

    if active_ratio > 0.6:
        health = "🚨 **Critical**"
        action = "Immediate investigation required. Too many active alerts."
    elif active_ratio > 0.3:
        health = "⚠️ **Needs Attention**"
        action = "Monitor closely and review alert thresholds."
    else:
        health = "✅ **Healthy**"
        action = "Alerting looks stable."

    scope = "All Customers" if customer_name == "All Customers" else customer_name

    return f"""
### 🧠 Alert Summary

- **Scope:** **{scope}**
- **Total Alerts:** {total}
- **Active Alerts:** {active} | **Resolved:** {resolved}
- **Alert Health:** {health}

**Most Frequent Condition:** `{top_condition}`  
**Most Impacted Entity:** `{top_entity}`  

**Recommendation:** {action}
"""

# ---------------- DATA FETCH ----------------
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

    grouped["Status"] = grouped["events"].apply(
        lambda x: "Active" if x == 1 else "Closed"
    )

    now = datetime.datetime.utcnow()
    grouped["Duration"] = grouped.apply(
        lambda r: format_duration(
            (now - r.start_time) if r.Status == "Active"
            else (r.end_time - r.start_time)
        ),
        axis=1
    )

    st.session_state.alerts = grouped.sort_values("start_time", ascending=False)
    st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts = pd.DataFrame()

# ---------------- HEADER ----------------
st.markdown(
    "## 🔥 Quickplay Alerts"
    if customer == "All Customers"
    else f"## 🔥 Quickplay Alerts — **{customer}**"
)

st.divider()

df = st.session_state.alerts
if df.empty:
    st.success("No alerts found 🎉")
    st.stop()

# ---------------- KPIs ----------------
c1, c2 = st.columns(2)
c1.metric("Total Alerts", len(df))
c2.metric("Active Alerts", len(df[df.Status == "Active"]))

# ---------------- ALERT SUMMARY ----------------
st.divider()
st.markdown(generate_alert_summary(df, customer))
st.divider()

# ---------------- ALERTS BY CUSTOMER ----------------
if customer == "All Customers":
    st.markdown("### Alerts by Customer")
    counts = df["Customer"].value_counts()

    cols_per_row = 3
    for i in range(0, len(counts), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, (cust, cnt) in enumerate(list(counts.items())[i:i+cols_per_row]):
            with cols[j]:
                if st.button(
                    f"{cnt}\nAlerts\n\n{cust}",
                    key=f"card_{cust}",
                    use_container_width=True
                ):
                    st.session_state.navigate_to_customer = cust
                    st.rerun()

st.divider()

# ---------------- ENTITY BREAKDOWN ----------------
st.markdown("### Alert Details by Condition")
for cond, cnt in df["conditionName"].value_counts().items():
    with st.expander(f"{cond} ({cnt})"):
        subset = df[df["conditionName"] == cond]
        entity_summary = (
            subset.groupby("Entity")
            .size()
            .reset_index(name="Count")
            .sort_values("Count", ascending=False)
        )
        st.dataframe(entity_summary, use_container_width=True, hide_index=True)
