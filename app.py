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

# ---------------- UI THEME ----------------
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
    st.session_state.alerts = pd.DataFrame()
if "updated" not in st.session_state:
    st.session_state.updated = None
if "clicked_customer" not in st.session_state:
    st.session_state.clicked_customer = None

# ---------------- SIDEBAR (AUTO REACTIVE) ----------------
with st.sidebar:
    st.markdown("### Filters")

    customer_filter = st.selectbox(
        "Customer",
        ["All Customers"] + list(CLIENTS.keys())
    )

    status_filter = st.radio(
        "Status",
        ["All", "Active", "Closed"],
        horizontal=True
    )

    time_map = {
        "Last 6 Hours": "SINCE 6 hours ago",
        "Last 24 Hours": "SINCE 24 hours ago",
        "Last 7 Days": "SINCE 7 days ago"
    }
    time_label = st.selectbox("Time Range", list(time_map.keys()))
    time_clause = time_map[time_label]

    if st.session_state.updated:
        st.caption(f"Updated at {st.session_state.updated}")

# Reset click selection if dropdown not All Customers
if customer_filter != "All Customers":
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
rows = []
targets = CLIENTS.items() if customer_filter == "All Customers" else [(customer_filter, CLIENTS[customer_filter])]

with st.spinner("Loading alerts…"):
    for name, cfg in targets:
        df = fetch_account(name, cfg["api_key"], cfg["account_id"], time_clause)
        if not df.empty:
            rows.append(df)

if rows:
    raw = pd.concat(rows)
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

# ---------------- APPLY CLICK FILTER ----------------
df_view = df.copy()
if st.session_state.clicked_customer:
    df_view = df[df["Customer"] == st.session_state.clicked_customer]
    st.info(f"📍 Viewing alerts for **{st.session_state.clicked_customer}**")
    if st.button("🔄 Reset to All Customers"):
        st.session_state.clicked_customer = None
        st.experimental_rerun()

# ---------------- KPIs ----------------
c1, c2 = st.columns(2)
c1.metric("Total Alerts", len(df_view))
c2.metric("Active Alerts", len(df_view[df_view["Status"] == "Active"]))

st.divider()

# ---------------- CUSTOMER CHART (STATE-DRIVEN HIGHLIGHT) ----------------
if customer_filter == "All Customers":
    st.markdown("### Alerts by Customer (click to filter)")

    customer_counts = (
        df.groupby("Customer")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )

    customer_counts["opacity"] = customer_counts["Customer"].apply(
        lambda c: 1.0 if st.session_state.clicked_customer in (None, c) else 0.25
    )
    customer_counts["color"] = customer_counts["Customer"].apply(
        lambda c: "#FF9F1C" if st.session_state.clicked_customer in (None, c) else "#555555"
    )

    chart = alt.Chart(customer_counts).mark_bar().encode(
        x=alt.X("Customer", sort="-y"),
        y="count",
        tooltip=["Customer", "count"],
        color=alt.Color("color:N", scale=None),
        opacity=alt.Opacity("opacity:Q", scale=None)
    ).properties(height=260)

    event = st.altair_chart(chart, use_container_width=True, on_select="rerun")

    if event.selection:
        selected = list(event.selection.values())
        if selected and "Customer" in selected[0][0]:
            st.session_state.clicked_customer = selected[0][0]["Customer"]
            st.experimental_rerun()

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
