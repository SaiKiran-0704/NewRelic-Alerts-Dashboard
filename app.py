import streamlit as st

import requests

import pandas as pd

import datetime



# ---------------- PAGE CONFIG ----------------

st.set_page_config(

    page_title="Pulse | Quickplay Monitoring",

    layout="wide",

    page_icon="📡"

)



# ---------------- MODERN UI STYLING ----------------

st.markdown("""

<style>

    /* Main Background and Text */

    .stApp { background-color: #0E1117; color: #FFFFFF; }

    

    /* Custom KPI Cards */

    [data-testid="stMetric"] {

        background: linear-gradient(135deg, #1A1C23 0%, #111318 100%);

        border: 1px solid #30363D;

        border-radius: 12px;

        padding: 20px !important;

        box-shadow: 0 4px 6px rgba(0,0,0,0.3);

    }

    

    /* Glowing Status Badges */

    .status-active {

        color: #FF4B4B;

        font-weight: bold;

        text-shadow: 0 0 10px rgba(255, 75, 75, 0.4);

    }

    .status-closed {

        color: #00D166;

        font-weight: bold;

    }



    /* Sidebar Styling */

    section[data-testid="stSidebar"] {

        background-color: #161B22 !important;

        border-right: 1px solid #30363D;

    }



    /* Modern Buttons for Customers */

    .stButton>button {

        border-radius: 8px;

        border: 1px solid #30363D;

        background-color: #21262D;

        transition: all 0.3s ease;

    }

    .stButton>button:hover {

        border-color: #58A6FF;

        box-shadow: 0 0 10px rgba(88, 166, 255, 0.2);

    }

</style>

""", unsafe_allow_html=True)



# ---------------- CONFIG & DATA (KEEPING YOUR LOGIC) ----------------

CLIENTS = st.secrets.get("clients", {})

ENDPOINT = "https://api.newrelic.com/graphql"



# [Keep your existing session state and navigation logic here]

if "alerts" not in st.session_state: st.session_state.alerts = None

if "updated" not in st.session_state: st.session_state.updated = None

if "customer_filter" not in st.session_state: st.session_state.customer_filter = "All Customers"

if "navigate_to_customer" not in st.session_state: st.session_state.navigate_to_customer = None



if st.session_state.navigate_to_customer:

    st.session_state.customer_filter = st.session_state.navigate_to_customer

    st.session_state.navigate_to_customer = None



# ---------------- SIDEBAR ----------------

with st.sidebar:

    st.image("https://img.icons8.com/fluency/96/radar.png", width=60)

    st.title("Pulse Ops")

    st.markdown("---")

    

    customer = st.selectbox(

        "Customer Environment",

        ["All Customers"] + list(CLIENTS.keys()),

        key="customer_filter"

    )



    time_map = {

        "Last 6 Hours": "SINCE 6 hours ago",

        "Last 24 Hours": "SINCE 24 hours ago",

        "Last 7 Days": "SINCE 7 days ago"

    }

    time_label = st.selectbox("Time Window", list(time_map.keys()))

    

    if st.session_state.updated:

        st.caption(f"✨ Last sync: {st.session_state.updated}")



# [Keep your existing helper functions: format_duration, calculate_mttr, fetch_account]

# ... (Reference your original fetch logic here) ...



# ---------------- MAIN DASHBOARD UI ----------------

st.title("📡 Sentinel Dashboard")

st.markdown(f"**Current View:** `{customer}`")



# ---------------- KPI ROW ----------------

if st.session_state.alerts is not None:

    df = st.session_state.alerts

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    

    with kpi1:

        st.metric("Total Incidents", len(df))

    with kpi2:

        active_count = len(df[df.Status == "Active"])

        st.metric("Active Now", active_count, delta=active_count, delta_color="inverse")

    with kpi3:

        # Improved MTTR Calculation Display

        from __main__ import calculate_mttr # Ensure helper is accessible

        st.metric("Avg Resolution (MTTR)", calculate_mttr(df))

    with kpi4:

        st.metric("System Health", f"{(1 - (active_count/len(df) if len(df)>0 else 0))*100:.1f}%")



    st.markdown("---")



    # ---------------- CUSTOMER GRID (Visual Cards) ----------------

    if customer == "All Customers":

        st.subheader("Client Health Overview")

        counts = df["Customer"].value_counts()

        

        # Grid Layout

        cols = st.columns(4)

        for idx, (cust, cnt) in enumerate(counts.items()):

            with cols[idx % 4]:

                container = st.container()

                # Determine color based on alert volume

                color = "🔴" if cnt > 5 else "🟡" if cnt > 0 else "🟢"

                if st.button(f"{color} {cust}\n\n{cnt} Alerts", key=f"btn_{cust}", use_container_width=True):

                    st.session_state.navigate_to_customer = cust

                    st.rerun()



    # ---------------- DATA VIEW ----------------

    st.markdown("### 📝 Incident Log")

    

    # Styled Dataframe

    def style_status(val):

        color = '#FF4B4B' if val == "Active" else '#00D166'

        return f'color: {color}; font-weight: bold'



    # Apply styling to a subset for better UI

    display_df = df[['Status', 'Customer', 'conditionName', 'Entity', 'Duration', 'start_time']].copy()

    

    st.dataframe(

        display_df,

        use_container_width=True,

        hide_index=True,

        column_config={

            "Status": st.column_config.TextColumn("Status", width="small"),

            "start_time": st.column_config.DatetimeColumn("Detected At", format="D MMM, HH:mm"),

            "Duration": "Age/Duration ⏳"

        }

    )



else:

    st.info("Select a customer or refresh to load alert data.")
