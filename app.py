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

# ---------------- CLEAN UI THEME ----------------
st.markdown("""
<style>
.stApp {
    background-color: #0F1115;
    color: #E6E6E6;
}

#MainMenu, footer, header { visibility: hidden; }

section[data-testid="stSidebar"] {
    background-color: #151821;
    border-right: 1px solid #2A2F3A;
}

h1, h2, h3 {
    font-weight: 600;
}

.metric-card {
    background-color: #151821;
    border: 1px solid #2A2F3A;
    border-radius: 10px;
    padding: 20px;
}

.stDataFrame {
    border: 1px solid #2A2F3A;
    border-radius: 8px;
}

div.stButton > button {
    background-color: #FF9F1C;
    color: black;
    border-radius: 6px;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

# ---------------- CONFIG ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

# ---------------- SESSION ----------------
if "data" not in st.session_state:
    st.session_state.data = None
if "updated" not in st.session_state:
    st.session_state.updated = None

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("### Filters")

    customer = st.selectbox(
        "Customer",
        ["All Customers"] + list(CLIENTS.keys())
    )

    status = st.radio(
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

    apply = st.button("Apply")

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

def status_style(v):
    return "color:#FF5C5C;font-weight:600" if v == "Active" else "color:#6EE7B7;font-weight:600"

@st.cache_data(ttl=300)
def fetch_data(name, api_key, account_id, time_clause):
    query = f"""
    {{
      actor {{
        account(id: {account_id}) {{
          nrql(query: "SELECT timestamp, policyName, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {time_clause} LIMIT MAX") {{
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
if apply or st.session_state.data is None:
    all_rows = []
    targets = CLIENTS.items() if customer == "All Customers" else [(customer, CLIENTS[customer])]

    with st.spinner("Loading alerts…"):
        for name, cfg in targets:
            df = fetch_data(name, cfg["api_key"], cfg["account_id"], time_clause)
            if not df.empty:
                all_rows.append(df)

    if all_rows:
        raw = pd.concat(all_rows)
        raw["timestamp"] = pd.to_datetime(raw["timestamp"], unit="ms")

        grouped = raw.groupby(
            ["incidentId", "Customer", "conditionName", "priority", "Entity"]
        ).agg(
            start=("timestamp", "min"),
            end=("timestamp", "max"),
            events=("event", "nunique")
        ).reset_index()

        grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
        now = datetime.datetime.utcnow()
        grouped["Duration"] = grouped.apply(
            lambda r: format_duration(
                now - r.start if r.Status == "Active" else r.end - r.start
            ), axis=1
        )

        if status != "All":
            grouped = grouped[grouped["Status"] == status]

        st.session_state.data = grouped.sort_values("start", ascending=False)
        st.session_state.updated = datetime.datetime.now().strftime("%H:%M:%S")
    else:
        st.session_state.data = pd.DataFrame()

# ---------------- HEADER ----------------
st.markdown("## 🔥 Quickplay Alerts")
st.caption("Live alert overview — simple, clear, actionable")
st.divider()

df = st.session_state.data
if df.empty:
    st.success("No alerts found 🎉")
    st.stop()

# ---------------- KPIs ----------------
c1, c2 = st.columns(2)
c1.metric("Total Alerts", len(df))
c2.metric("Active Alerts", len(df[df["Status"] == "Active"]))

st.divider()

# ---------------- CHARTS ----------------
if customer == "All Customers":
    st.markdown("### Alerts by Customer")
    cust_chart = alt.Chart(df).mark_bar().encode(
        x=alt.X("Customer", sort="-y"),
        y="count()",
        tooltip=["Customer", "count()"],
        color=alt.value("#FF9F1C")
    ).properties(height=260)

    st.altair_chart(cust_chart, use_container_width=True)

st.markdown("### Alerts by Condition")
cond_chart = alt.Chart(df).mark_bar().encode(
    x=alt.X("conditionName", sort="-y", axis=alt.Axis(labelAngle=-40)),
    y="count()",
    tooltip=["conditionName", "count()"],
    color=alt.value("#FF9F1C")
).properties(height=300)

st.altair_chart(cond_chart, use_container_width=True)

st.divider()

# ---------------- TABLE ----------------
st.markdown("### Live Alerts")

display_cols = ["start", "Customer", "Entity", "conditionName", "priority", "Status", "Duration"]

st.dataframe(
    df[display_cols].style.map(status_style, subset=["Status"]),
    use_container_width=True,
    hide_index=True,
    column_config={
        "start": st.column_config.DatetimeColumn("Start Time (UTC)"),
        "conditionName": st.column_config.TextColumn("Condition"),
        "priority": st.column_config.TextColumn("Priority")
    }
)
