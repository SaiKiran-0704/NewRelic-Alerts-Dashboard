import streamlit as st
import requests
import pandas as pd
import datetime

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Quickplay Pulse",
    layout="wide",
    page_icon="🔥",
    initial_sidebar_state="expanded" 
)

# ---------------- PREMIUM LOGO & UI OVERHAUL (CSS ONLY) ----------------
st.markdown("""
<style>
    /* Global Styles & Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    .stApp { 
        background: radial-gradient(circle at 50% 0%, #1a1c23 0%, #0a0c10 100%);
        color: #e0e0e0; 
        font-family: 'Inter', sans-serif; 
    }

    /* Hide Sidebar Collapse Action */
    button[kind="headerNoPadding"] { display: none !important; }

    /* Permanent Glassmorphism Sidebar */
    section[data-testid="stSidebar"] {
        width: 400px !important;
        background: rgba(22, 27, 34, 0.95) !important;
        border-right: 1px solid rgba(243, 112, 33, 0.3);
        position: fixed;
        backdrop-filter: blur(15px);
    }

    /* Sidebar Logo Styling */
    .sidebar-logo-container {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 10px 0;
        text-shadow: 0 0 15px rgba(243, 112, 33, 0.4);
    }
    .sidebar-logo-text { 
        color: #F37021; 
        font-weight: 800; 
        font-size: 2.4rem; 
        letter-spacing: -2px;
    }

    /* Pulse Monitoring - Glowing Orange Header */
    .center-header {
        text-align: center;
        color: #F37021; 
        font-weight: 800;
        font-size: 4rem;
        margin: 20px 0;
        text-shadow: 0 0 25px rgba(243, 112, 33, 0.5);
        letter-spacing: -1.5px;
    }

    /* Glass KPI Cards with Animated Glow Borders */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.03) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 20px !important;
        padding: 30px !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.8) !important;
        transition: transform 0.3s ease, border 0.3s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        border: 1px solid rgba(243, 112, 33, 0.5) !important;
    }

    /* KPI Value & Delta Styling */
    div[data-testid="stMetricValue"] > div {
        font-size: 3.8rem !important;
        font-weight: 800 !important;
        color: #ffffff !important;
    }
    div[data-testid="stMetricDelta"] {
        background: rgba(255, 255, 255, 0.05);
        padding: 4px 10px;
        border-radius: 8px;
    }

    /* Customer Tiles - Cyberpunk Grid Style */
    .stButton>button {
        background: linear-gradient(145deg, #161b22, #0d1117) !important;
        border: 1px solid #30363d !important;
        color: #c9d1d9 !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        height: 70px !important;
        box-shadow: 3px 3px 10px rgba(0,0,0,0.3);
    }
    .stButton>button:hover {
        border-color: #F37021 !important;
        color: #F37021 !important;
        box-shadow: 0 0 15px rgba(243, 112, 33, 0.2);
    }

    /* Sidebar Widgets - Premium Dark Inputs */
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"],
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
        background-color: #0d1117 !important;
        border-radius: 12px !important;
        border: 1px solid #30363d !important;
    }

    /* Action Button - Neon Orange Glow */
    [data-testid="stSidebar"] .stButton>button {
        background: #F37021 !important;
        color: white !important;
        box-shadow: 0 0 20px rgba(243, 112, 33, 0.3) !important;
        border: none !important;
        font-size: 1.2rem !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------- REMAINDER OF YOUR LOGIC (UNCHANGED) ----------------
# ... (Keep all your config, helpers, sidebar logic, and load/process logic exactly as they are) ...

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.markdown("""
        <div class="sidebar-logo-container">
            <span style="font-size: 2.5rem;">🔥</span>
            <span class="sidebar-logo-text">quickplay</span>
        </div>
    """, unsafe_allow_html=True)
    st.divider()
    
    # Existing Customer selection logic
    customer_options = ["All Customers"] + list(st.secrets.get("clients", {}).keys())
    customer_selection = st.selectbox("Customer", customer_options, key="customer_filter")
    status_choice = st.radio("Alert Status", ["All", "Active", "Closed"], horizontal=True)
    time_label = st.selectbox("Time Window", ["6 Hours", "24 Hours", "7 Days", "30 Days", "60 Days", "90 Days"])

    if st.button("🔄 Force Refresh Pulse"):
        st.cache_data.clear()
        st.rerun()

# (The logic for fetch_account_with_history, Loading & processing, and Main Content remains identical)
# ...
