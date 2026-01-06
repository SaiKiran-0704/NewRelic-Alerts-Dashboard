import streamlit as st
import requests
import pandas as pd
import datetime
import altair as alt
from PIL import Image

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Quickplay Stability",
    layout="wide",
    page_icon="🔥",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS ---
st.markdown("""
<style>
.stApp { background-color: #0E1117; color: #FAFAFA; }
button[data-testid="sidebar-toggle"] { display: none !important; }
#MainMenu, header, footer { visibility: hidden !important; }

section[data-testid="stSidebar"] {
    background-color: #161B22;
    border-right: 1px solid #30363D;
}

div[data-testid="stMetric"] {
    background-color: #161B22;
    border: 1px solid #30363D;
    padding: 20px;
    border-radius: 10px;
}

div[data-testid="stMetricLabel"] { color: #8B949E; }
div[data-testid="stMetricValue"] { color: #FFFFFF; font-size: 28px; font-weight: 700; }

.stProgress > div > div > div > div {
    background-image: linear-gradient(90deg, #FF9F1C, #FF6B6B);
}

div[data-testid="stDataFrame"] {
    border: 1px solid #30363D;
    border-radius: 8px;
}

h1, h2, h3 { color: #FAFAFA !important; }
p, span, label { color: #C9D1D9 !important; }

div.stButton > button {
    background-color: #FF9F1C;
    color: #0E1117;
    font-weight: 600;
    border-radius: 6px;
}
</style>
""", unsafe_allow_html=True)

# --- CLIENT CONFIG ---
try:
    CLIENTS = st.secrets["clients"]
except Exception:
    st.error("Secrets not configured")
    CLIENTS = {}

ENDPOINT = "https://api.newrelic.com/graphql"

# --- SESSION STATE ---
st.session_state.setdefault("alert_data", None)
st.session_state.setdefault("last_updated", None)

# --- SIDEBAR ---
with st.sidebar:
    with st.form("filters"):
        customers = ["All Customers"] + list(CLIENTS.keys())
        selected_customer = st.selectbox("Customer", customers)

        status_filter = st.radio(
            "Status",
            ["All", "Active", "Closed"],
            horizontal=True
        )

        time_ranges = {
            "Last 60 Minutes": "SINCE 60 minutes ago",
            "Last 6 Hours": "SINCE 6 hours ago",
            "Last 24 Hours": "SINCE 24 hours ago",
            "Last 7 Days": "SINCE 7 days ago",
            "Last 30 Days": "SINCE 30 days ago",
        }

        time_label = st.selectbox("Time Range", list(time_ranges.keys()))
        time_clause = time_ranges[time_label]

        submitted = st.form_submit_button("Apply Filters", use_container_width=True)

    if st.session_state["last_updated"]:
        st.caption(f"Last updated: {st.session_state['last_updated']}")

# --- HELPERS ---
def format_duration(td):
    secs = int(td.total_seconds())
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"

def style_status(val):
    if val == "Active":
        return "color:#FF5252;font-weight:800;"
    return "color:#69F0AE;font-weight:700;"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_account(name, api_key, account_id, time_filter):
    query = f"""
    {{
      actor {{
        account(id: {account_id}) {{
          nrql(query: "SELECT timestamp, policyName, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open','close') {time_filter} LIMIT MAX") {{
            results
          }}
        }}
      }}
    }}
    """
    headers = {"API-Key": api_key}
    r = requests.post(ENDPOINT, json={"query": query}, headers=headers)
    data = r.json()["data"]["actor"]["account"]["nrql"]["results"]
    df = pd.DataFrame(data)
    if not df.empty:
        df["Customer"] = name
        df.rename(columns={"entity.name": "Entity"}, inplace=True)
    return df

# --- DATA LOAD ---
if submitted or st.session_state["alert_data"] is None:
    with st.spinner("Fetching alerts..."):
        frames = []
        targets = CLIENTS.items() if selected_customer == "All Customers" else [(selected_customer, CLIENTS[selected_customer])]

        for name, c in targets:
            df = fetch_account(name, c["api_key"], c["account_id"], time_clause)
            if not df.empty:
                frames.append(df)

        if frames:
            df = pd.concat(frames)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

            grouped = df.groupby(
                ["incidentId", "Customer", "policyName", "conditionName", "priority", "Entity"]
            ).agg(
                start_time=("timestamp", "min"),
                end_time=("timestamp", "max"),
                events=("event", "nunique")
            ).reset_index()

            grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x == 1 else "Closed")
            now = datetime.datetime.utcnow()

            grouped["Duration"] = grouped.apply(
                lambda x: format_duration((now - x.start_time) if x.Status == "Active" else (x.end_time - x.start_time)),
                axis=1
            )

            if status_filter != "All":
                grouped = grouped[grouped["Status"] == status_filter]

            st.session_state["alert_data"] = grouped.sort_values("start_time", ascending=False)
            st.session_state["last_updated"] = datetime.datetime.now().strftime("%H:%M:%S")
        else:
            st.session_state["alert_data"] = pd.DataFrame()

# --- HEADER ---
try:
    st.image("logo.png", use_container_width=True)
except Exception:
    st.markdown("<h1 style='text-align:center;color:#FF9F1C;'>🔥 Quickplay</h1>", unsafe_allow_html=True)

st.markdown("<h2 style='text-align:center;'>Alerts Overview</h2>", unsafe_allow_html=True)
st.divider()

df_main = st.session_state["alert_data"]

if df_main.empty:
    st.success("No alerts found 🎉")
    st.stop()

# --- KPI METRICS (NO SOC / INFRA) ---
c1, c2 = st.columns(2)
c1.metric("Total Alerts", len(df_main))
c2.metric("🔥 Active Alerts", len(df_main[df_main["Status"] == "Active"]))

st.divider()

# --- CUSTOMER CHART ---
if selected_customer == "All Customers":
    st.subheader("📊 Alerts by Customer")

    chart = alt.Chart(df_main).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("Customer:N", sort="-y", title=None),
        y=alt.Y("count()", title="Alerts"),
        tooltip=["Customer", "count()"],
        color=alt.value("#FF9F1C")
    ).properties(height=320)

    st.altair_chart(chart, use_container_width=True)

st.divider()

# --- ALERT SUMMARY ---
st.subheader("🔎 Alert Breakdown")

summary = df_main["conditionName"].value_counts().reset_index()
summary.columns = ["Condition", "Count"]

st.dataframe(
    summary,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Count": st.column_config.ProgressColumn("Count", min_value=0, max_value=int(summary["Count"].max()))
    }
)

st.divider()

# --- ALERT LOGS (SINGLE VIEW) ---
st.subheader("📝 Live Alert Logs")

cols = ["start_time", "Customer", "Entity", "conditionName", "priority", "Status", "Duration"]

st.dataframe(
    df_main[cols].style.map(style_status, subset=["Status"]),
    use_container_width=True,
    hide_index=True,
    column_config={
        "start_time": st.column_config.DatetimeColumn("Time (UTC)", format="D MMM, HH:mm"),
        "conditionName": st.column_config.TextColumn("Condition", width="large"),
    }
)
