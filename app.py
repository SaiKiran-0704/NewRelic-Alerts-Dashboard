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

# --- CUSTOM CSS (FINAL CLEAN UI & THEME) ---
st.markdown("""
<style>
    /* GLOBAL THEME */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }

    /* 🛑 HIDE SIDEBAR COLLAPSE BUTTON (>>) 🛑 */
    button[data-testid="sidebar-toggle"] {
        display: none !important;
    }

    /* 🛑 HIDE STREAMLIT UI ELEMENTS 🛑 */
    #MainMenu, header, footer {
        visibility: hidden !important;
    }
    
    /* SIDEBAR STYLING */
    section[data-testid="stSidebar"] {
        background-color: #161B22; 
        border-right: 1px solid #30363D;
    }
    
    /* METRIC CARDS */
    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
    }
    div[data-testid="stMetricLabel"] { color: #8B949E; font-size: 14px; font-weight: 500; }
    div[data-testid="stMetricValue"] { color: #FFFFFF; font-size: 28px; font-weight: 700; }

    /* DATAFRAME & TABLES */
    div[data-testid="stDataFrame"] {
        border: 1px solid #30363D;
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* TEXT ELEMENTS */
    h1, h2, h3 { color: #FAFAFA !important; font-family: 'Inter', sans-serif; font-weight: 700; }
    p, span, label { color: #C9D1D9 !important; }
    
    /* BUTTONS */
    div.stButton > button {
        background-color: #FF9F1C;
        color: #0E1117;
        font-weight: 600;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. CLIENT CONFIGURATION ---
try:
    CLIENTS = st.secrets["clients"]
except Exception:
    st.error("Secrets not configured! Please configure .streamlit/secrets.toml locally.")
    CLIENTS = {}

ENDPOINT = "https://api.newrelic.com/graphql"

# --- 2. SESSION STATE ---
if 'alert_data' not in st.session_state:
    st.session_state['alert_data'] = None
if 'last_updated' not in st.session_state:
    st.session_state['last_updated'] = None

# --- 3. SIDEBAR CONTROLS ---
with st.sidebar:
    with st.form("filter_form"):
        customer_keys = list(CLIENTS.keys())
        customer_options = ["All Customers"] + customer_keys if customer_keys else ["No Clients Configured"]
        selected_view = st.selectbox("Select Customer", customer_options, index=0)

        st.write("") 

        st.markdown("### Status")
        status_filter = st.radio("Status Filter", ["All", "Active", "Closed"], horizontal=True, label_visibility="collapsed", index=0)

        st.write("") 

        st.markdown("### Time Range")
        time_ranges = {
            "Last 60 Minutes": "SINCE 60 minutes ago",
            "Last 6 Hours": "SINCE 6 hours ago",
            "Last 24 Hours": "SINCE 24 hours ago",
            "Last 7 Days": "SINCE 7 days ago"
        }
        time_options = list(time_ranges.keys()) + ["Custom Date Range"]
        selected_time_label = st.selectbox("Time Frame", time_options, label_visibility="collapsed", index=1)

        if selected_time_label == "Custom Date Range":
            col_d1, col_d2 = st.columns(2)
            start_date = col_d1.date_input("Start", datetime.date.today() - datetime.timedelta(days=1))
            end_date = col_d2.date_input("End", datetime.date.today())
            time_clause = f"SINCE '{start_date} 00:00:00' UNTIL '{end_date} 23:59:59'"
        else:
            time_clause = time_ranges[selected_time_label]
            
        st.divider()
        submitted = st.form_submit_button("Apply Filters", type="primary", use_container_width=True)

# --- 4. HELPER FUNCTIONS ---
def format_duration(td):
    total_seconds = int(td.total_seconds())
    if total_seconds < 60: return f"{total_seconds}s"
    m, s = divmod(total_seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h > 0 else f"{m}m {s}s"

def style_status_column(val):
    if val == 'Active': return 'color: #FF5252; font-weight: 800;'  
    elif val == 'Closed': return 'color: #69F0AE; font-weight: 700;' 
    return ''

@st.cache_data(ttl=300, show_spinner=False)
def fetch_single_account(client_name, api_key, account_id, time_filter):
    query = f"{{ actor {{ account(id: {account_id}) {{ nrql(query: \"SELECT timestamp, policyName, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open', 'close') {time_filter} LIMIT MAX\") {{ results }} }} }} }}"
    headers = {"API-Key": api_key, "Content-Type": "application/json"}
    try:
        response = requests.post(ENDPOINT, json={"query": query}, headers=headers)
        if response.status_code == 200:
            data = response.json().get('data', {}).get('actor', {}).get('account', {}).get('nrql', {}).get('results', [])
            df = pd.DataFrame(data)
            if not df.empty:
                df['Customer'] = client_name
                df.rename(columns={'entity.name': 'Entity'}, inplace=True) if 'entity.name' in df.columns else None
                return df
    except: pass
    return pd.DataFrame()

# --- 5. MAIN LOGIC ---
if submitted or st.session_state['alert_data'] is None:
    with st.spinner('Fetching live alerts...'):
        all_data = []
        targets = CLIENTS.items() if selected_view == "All Customers" else [(selected_view, CLIENTS[selected_view])]
        for name, creds in targets:
            df_client = fetch_single_account(name, creds['api_key'], creds['account_id'], time_clause)
            if not df_client.empty: all_data.append(df_client)

        if all_data:
            raw_df = pd.concat(all_data, ignore_index=True)
            raw_df['timestamp'] = pd.to_datetime(raw_df['timestamp'], unit='ms')
            grouped = raw_df.groupby(['incidentId', 'Customer', 'policyName', 'conditionName', 'priority']).agg(
                start_time=('timestamp', 'min'), end_time=('timestamp', 'max'), event_count=('event', 'nunique'),
                Entity=('Entity', 'first') if 'Entity' in raw_df.columns else ('incidentId', 'first')
            ).reset_index()

            grouped['Status'] = grouped['event_count'].apply(lambda x: 'Active' if x == 1 else 'Closed')
            now = datetime.datetime.now()
            grouped['Duration'] = grouped.apply(lambda x: format_duration((now - x['start_time']) if x['Status'] == 'Active' else (x['end_time'] - x['start_time'])), axis=1)
            
            if status_filter != "All": grouped = grouped[grouped['Status'] == status_filter]
            st.session_state['alert_data'] = grouped.sort_values(by='start_time', ascending=False)
            st.session_state['last_updated'] = now.strftime('%H:%M:%S')
            st.session_state['current_view_selection'] = selected_view
        else:
            st.session_state['alert_data'] = pd.DataFrame()

# --- 6. DISPLAY ---
try:
    c1, c2, c3 = st.columns([1, 2, 1]) 
    with c2: st.image("logo.png", use_container_width=True) 
except:
    st.markdown("<h1 style='text-align: center; color: #FF9F1C; font-size: 80px; margin-bottom: 0px;'>🔥 Quickplay</h1>", unsafe_allow_html=True)

st.markdown("<h2 style='text-align: center; margin-top: -10px; opacity: 0.8;'>Alerts Overview</h2>", unsafe_allow_html=True)
st.divider()

if not st.session_state['alert_data'].empty:
    df_main = st.session_state['alert_data']
    
    # Updated KPI Section (Only Total and Active)
    m1, m2 = st.columns(2)
    m1.metric("Total Alerts", len(df_main))
    m2.metric("🔥 Active Now", len(df_main[df_main['Status'] == 'Active']))

    if st.session_state.get('current_view_selection') == "All Customers":
        st.subheader("📊 Alert Volume by Customer")
        chart = alt.Chart(df_main).mark_bar(color='#FF9F1C').encode(
            x=alt.X('Customer', sort='-y', title=None),
            y=alt.Y('count()', title='Alert Count'),
            tooltip=['Customer', 'count()']
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)

    # Simplified Logs Section (Unified Table)
    st.subheader("📝 Live Alert Logs")
    common_config = {"start_time": st.column_config.DatetimeColumn("Time (UTC)", format="D MMM, HH:mm")}
    cols = ['start_time', 'Customer', 'Entity', 'conditionName', 'priority', 'Status', 'Duration']
    
    st.dataframe(
        df_main[cols].style.map(style_status_column, subset=['Status']), 
        use_container_width=True, 
        hide_index=True, 
        column_config=common_config
    )
else:
    st.success("No alerts found matching your criteria. 🎉")
