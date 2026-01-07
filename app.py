import streamlit as st
import requests
import pandas as pd
import datetime

# ---- PAGE CONFIG ----
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
if "selected_customer" not in st.session_state:
    st.session_state.selected_customer = "All Customers"

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("### Filters")

    customer_options = ["All Customers"] + list(CLIENTS.keys())
    sidebar_customer = st.selectbox(
        "Customer",
        customer_options,
        index=customer_options.index(st.session_state.selected_customer)
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

# Update session state based on sidebar selection
st.session_state.selected_customer = sidebar_customer

# ---------------- HELPERS ----------------
def format_duration(td):
    s = int(td.total_seconds())
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"

def calculate_mttr(df):
    if df.empty:
        return "N/A"
    closed = df[df["Status"] == "Closed"]
    if len(closed) == 0:
        return "No resolved alerts yet"
    durations = []
    for d in closed["Duration"]:
        try:
            mins = 0
            for part in d.split():
                if 'd' in part: mins += int(part.replace('d',''))*1440
                elif 'h' in part: mins += int(part.replace('h',''))*60
                elif 'm' in part: mins += int(part.replace('m',''))
                elif 's' in part: mins += int(part.replace('s',''))/60
            durations.append(mins)
        except: pass
    if durations:
        avg = sum(durations)/len(durations)
        h = int(avg//60)
        m = int(avg%60)
        return f"{h}h {m}m" if h>0 else f"{m}m"
    return "N/A"

def get_alert_frequency(df, time_label):
    if df.empty: return "N/A"
    total = len(df)
    if "6 Hours" in time_label: return f"{total/6:.1f} per hour"
    if "24 Hours" in time_label: return f"{total/24:.1f} per hour"
    if "7 Days" in time_label: return f"{total/7:.1f} per day"
    if "1 Month" in time_label: return f"{total/30:.1f} per day"
    if "3 Months" in time_label: return f"{total/90:.1f} per day"
    return f"{total} total"

def get_resolution_rate(df):
    if df.empty: return "0%"
    total = len(df)
    resolved = len(df[df["Status"]=="Closed"])
    return f"{(resolved/total*100):.0f}%"

def get_top_3_entities(df):
    if df.empty or "Entity" not in df.columns: return []
    top = df["Entity"].value_counts().head(3)
    return [(e,c) for e,c in top.items()]

def calculate_alert_trend(df):
    if df.empty: return "N/A"
    n = len(df)
    if n>100: return "High volume"
    if n>50: return "Moderate volume"
    return "Low volume"

def generate_insights(df, time_label):
    if df.empty: return {
        "mttr":"N/A","frequency":"N/A","resolution_rate":"0%",
        "top_entities":[],"trend":"N/A","recommendations":["No alerts"],"top_condition":"N/A"
    }
    total = len(df)
    active = len(df[df["Status"]=="Active"])
    top_condition = "N/A"
    if "conditionName" in df.columns and not df["conditionName"].empty:
        top_condition = df["conditionName"].value_counts().index[0]
    recs = []
    if active/total>0.5:
        recs.append("🎯 High active rate (>50%) - Consider tuning thresholds")
    if top_condition != "N/A":
        top_count = df["conditionName"].value_counts().iloc[0]
        if top_count/total > 0.3:
            recs.append(f"🎯 '{top_condition}' causes {(top_count/total)*100:.0f}% of alerts - Needs investigation")
    if not recs: recs.append("✅ Alert conditions look well-tuned")
    return {
        "mttr": calculate_mttr(df),
        "frequency": get_alert_frequency(df,time_label),
        "resolution_rate": get_resolution_rate(df),
        "top_entities": get_top_3_entities(df),
        "trend": calculate_alert_trend(df),
        "recommendations": recs,
        "top_condition": top_condition
    }

# ---------------- FETCH ACCOUNT ----------------
@st.cache_data(ttl=300)
def fetch_account(name, api_key, account_id, time_clause):
    query = f"""
    {{
      actor {{
        account(id:{account_id}) {{
          nrql(query:"SELECT timestamp, conditionName, priority, incidentId, event, entity.name 
                        FROM NrAiIncident WHERE event IN ('open','close') {time_clause} LIMIT MAX") {{
            results
          }}
        }}
      }}
    }}
    """
    try:
        r = requests.post(ENDPOINT, json={"query": query}, headers={"API-Key": api_key})
        resp = r.json()

        results = (
            resp.get("data", {})
                .get("actor", {})
                .get("account", {})
                .get("nrql", {})
                .get("results", [])
        )

        if results:
            df = pd.DataFrame(results)
            df["Customer"] = name
            df.rename(columns={"entity.name":"Entity"}, inplace=True)
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error fetching data for {name}: {e}")
        return pd.DataFrame()

# ---------------- LOAD DATA ----------------
all_rows = []
targets = CLIENTS.items() if st.session_state.selected_customer=="All Customers" else [(st.session_state.selected_customer, CLIENTS[st.session_state.selected_customer])]

with st.spinner("Loading alerts…"):
    for name,cfg in targets:
        df = fetch_account(name,cfg["api_key"],cfg["account_id"],time_clause)
        if not df.empty: all_rows.append(df)

if all_rows:
    raw = pd.concat(all_rows)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"],unit="ms")
    grouped = raw.groupby(["incidentId","Customer","conditionName","priority","Entity"]).agg(
        start_time=("timestamp","min"),
        end_time=("timestamp","max"),
        events=("event","nunique")
    ).reset_index()
    grouped["Status"] = grouped["events"].apply(lambda x: "Active" if x==1 else "Closed")
    now=datetime.datetime.utcnow()
    grouped["Duration"]=grouped.apply(lambda r: format_duration((now-r.start_time) if r.Status=="Active" else (r.end_time-r.start_time)),axis=1)
    st.session_state.alerts = grouped.sort_values("start_time",ascending=False)
    st.session_state.updated=datetime.datetime.now().strftime("%H:%M:%S")
else:
    st.session_state.alerts=pd.DataFrame()
    st.info("No alerts found for the selected customers and time range 🎉")

df = st.session_state.alerts

# ---------------- HEADER ----------------
if st.session_state.selected_customer=="All Customers":
    st.markdown("## 🔥 Quickplay Alerts")
else:
    st.markdown(f"## 🔥 Quickplay Alerts — **{st.session_state.selected_customer}**")

st.divider()

if df.empty:
    st.stop()

# ---------------- DRILLDOWN ----------------
df_view = df if st.session_state.selected_customer=="All Customers" else df[df["Customer"]==st.session_state.selected_customer]

# ---------------- KPIs ----------------
c1,c2 = st.columns(2)
c1.metric("Total Alerts", len(df_view))
c2.metric("Active Alerts", len(df_view[df_view["Status"]=="Active"]))
st.divider()

# ---------------- SUMMARY & INSIGHTS ----------------
st.markdown("### 📊 Alert Metrics & Analysis")
metrics = generate_insights(df_view, time_label)
col1,col2,col3 = st.columns(3)
with col1:
    st.metric("Mean Time to Resolve",metrics["mttr"])
    st.metric("Alert Frequency",metrics["frequency"])
with col2:
    st.metric("Resolution Rate",metrics["resolution_rate"])
    st.metric("Volume Status",metrics["trend"])
with col3:
    st.markdown("**Top Affected Entities:**")
    if metrics["top_entities"]:
        for e,c in metrics["top_entities"]:
            st.markdown(f"• {e}: {c} alerts")
    else:
        st.markdown("• No entity data available")
st.divider()

st.markdown("**Top Alert Condition:**")
st.markdown(f"🔔 **{metrics['top_condition']}**" if metrics["top_condition"]!="N/A" else "No conditions detected")
st.markdown("**Recommendations:**")
for r in metrics["recommendations"]: st.markdown(f"• {r}")
st.divider()

# ---------------- CARDS ----------------
if st.session_state.selected_customer=="All Customers":
    st.markdown("### Alerts by Customer")
    counts = df["Customer"].value_counts().sort_values(ascending=False)
    cols_per_row=3
    for i in range(0,len(counts),cols_per_row):
        cols=st.columns(cols_per_row)
        for j,(cust,count) in enumerate(list(counts.items())[i:i+cols_per_row]):
            with cols[j]:
                if st.button(f"{count}\nAlerts\n\n{cust}", key=f"card_{cust}", use_container_width=True):
                    st.session_state.selected_customer=cust
                    st.rerun()

st.divider()

# ---------------- ENTITY BREAKDOWN ----------------
st.markdown("### Alert Details by Condition")
for cond,cnt in df_view["conditionName"].value_counts().items():
    with st.expander(f"{cond} ({cnt})"):
        subset = df_view[df_view["conditionName"]==cond]
        ent_summary = subset.groupby("Entity").size().reset_index(name="Count").sort_values("Count",ascending=False)
        st.dataframe(ent_summary,use_container_width=True,hide_index=True)
