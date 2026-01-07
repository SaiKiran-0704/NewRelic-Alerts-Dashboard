import streamlit as st
import requests
import pandas as pd
import datetime

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Quickplay Pulse",
    layout="wide",
    page_icon="🔥"
)

# ---------------- CLEAN & BRANDED UI ----------------
st.markdown("""
<style>
    /* Dark Theme with Quickplay Accents */
    .stApp { background-color:#0F1115; color:#E6E6E6; }
    
    /* Header Styling */
    .main-header {
        color: #F37021; /* Quickplay Orange */
        font-weight: 800;
        margin-bottom: 0px;
    }
    
    /* Remove unnecessary spacing at top */
    .block-container { padding-top: 2rem; }

    /* KPI Card Refinement */
    div[data-testid="stMetric"] {
        background-color:#161B22;
        border: 1px solid #30363D;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }
    
    /* Highlight Active Metric */
    div[data-testid="stMetric"]:nth-child(2) {
        border-top: 3px solid #F37021;
    }

    /* Modern Table/Dataframe */
    .stDataFrame {
        border: 1px solid #30363D;
        border-radius: 8px;
    }

    /* Sidebar glassmorphism */
    section[data-testid="stSidebar"] {
        background-color:#151821;
        border-right:1px solid #2A2F3A;
    }
    
    /* Button Grid for Customers */
    .stButton>button {
        background-color: #1C2128;
        border: 1px solid #30363D;
        color: white;
        transition: 0.3s;
    }
    .stButton>button:hover {
        border-color: #F37021;
        color: #F37021;
    }

    /* Expander Styling for Groups */
    .stExpander {
        border: 1px solid #30363D !important;
        background-color: #111418 !important;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------- CONFIG & DATA LOGIC ----------------
CLIENTS = st.secrets.get("clients", {})
ENDPOINT = "https://api.newrelic.com/graphql"

if "alerts" not in st.session_state: st.session_state.alerts = None
if "updated" not in st.session_state: st.session_state.updated = None
if "customer_filter" not in st.session_state: st.session_state.customer_filter = "All Customers"
if "navigate_to_customer" not in st.session_state: st.session_state.navigate_to_customer = None

if st.session_state.navigate_to_customer:
    st.session_state.customer_filter = st.session_state.navigate_to_customer
    st.session_state.navigate_to_customer = None

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("<h1 style='color:#F37021; font-size: 28px;'>🔥 quickplay</h1>", unsafe_allow_html=True)
    st.caption("Pulse Monitoring v1.0")
    st.divider()
    
    customer = st.selectbox(
        "Client Selector",
        ["All Customers"] + list(CLIENTS.keys()),
        key="customer_filter"
    )

    time_map = {
        "6 Hours": "SINCE 6 hours ago",
        "24 Hours": "SINCE 24 hours ago",
        "7 Days": "SINCE 7 days ago",
        "30 Days": "SINCE 30 days ago"
    }
    time_label = st.selectbox("Time Window", list(time_map.keys()))
    time_clause = time_map[time_label]

    if st.session_state.updated:
        st.markdown(f"**Last Sync:** `{st.session_state.updated}`")

# ---------------- HELPERS ----------------
def format_duration(td):
    s = int(td.total_seconds())
    if s < 60: return f"{s}s"
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else f"{m}m {s}s"

def calculate_mttr(df):
    closed = df[df["Status"] == "Closed"]
    if closed.empty: return "N/A"
    mins = []
    for d in closed["Duration"]:
        total = 0
        parts = d.split()
        for p in parts:
            if "h" in p: total += int(p.replace("h","")) * 60
            elif "m" in p: total += int(p.replace("m",""))
        mins.append(total)
    avg = sum(mins) / len(mins)
    return f"{int(avg//60)}h {int(avg%60)}m" if avg >= 60 else f"{int(avg)}m"

def get_resolution_rate(df):
    if df.empty: return "0%"
    return f"{(len(df[df.Status=='Closed'])/len(df))*100:.0f}%"

@st.cache_data(ttl=300)
def fetch_account(name, api_key, account_id, time_clause):
    query =
