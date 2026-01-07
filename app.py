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

.customer-card {
    background-color: #151821;
    border: 1px solid #2A2F3A;
    border-radius: 14px;
    padding: 18px;
    text-align: center;
}

.customer-card:hover {
    border-color: #FF5C5C;
}

.customer-count {
    font-size: 22px;
    font-weight: 700;
}

.customer-name {
    font-size: 14px;
    opacity: 0.85;
}
</style>
""", unsafe_allow_html=True)

# ---------------- CONFIG ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

# ---------------- CUSTOMER IMAGES ----------------
CUSTOMER_IMAGES = {
  "Aha": "logos/Aha.png",
    "PLIVE": "logos/plive.png",
    "CIGNAL": "logos/cignal.jpeg",
    "TM": "logos/tm.jpeg",
    "GAME": "logos/gotham_sports.jpeg",
    "AMD": "logos/localnow.png",
    "Univision": "logos/unow.jpeg",
    "CANELA": "logos/canela.png",
}

# ---------------- SESSION STATE ----------------
if "alerts" not in st.session_state:
    st.session_state.alerts = None
if "updated" not in st.session_state:
    st.session_state.updated = None
if "customer_filter" not in st.session_state:
    st.session_state.customer_filter = "All Customers"
if "navigate_to_customer" not in st.session_state:
    st.session_state.navigate_to_customer = None

# -------- SAFE NAVIGATION --------
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

st.divider()

# ---------------- ALERTS BY CUSTOMER (WITH LOGOS) ----------------
if customer == "All Customers":
    st.markdown("### Alerts by Customer")
    counts = df["Customer"].value_counts()

    cols_per_row = 4
    for i in range(0, len(counts), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, (cust, cnt) in enumerate(list(counts.items())[i:i+cols_per_row]):
            with cols[j]:
                st.markdown('<div class="customer-card">', unsafe_allow_html=True)

                img = CUSTOMER_IMAGES.get(cust)
                if img:
                    st.image(img, width=80)

                st.markdown(f'<div class="customer-count">{cnt}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="customer-name">{cust}</div>', unsafe_allow_html=True)

                if st.button("View Alerts", key=f"card_{cust}", use_container_width=True):
                    st.session_state.navigate_to_customer = cust
                    st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)
