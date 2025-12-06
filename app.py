import streamlit as st
import requests
import pandas as pd
import datetime
from PIL import Image

# --- PAGE SETUP ---
st.set_page_config(page_title="Quickplay Stability", layout="wide", page_icon="🔥")

# --- CUSTOM CSS (MODERN ORANGE & BLACK THEME) ---
st.markdown("""
<style>
    /* GLOBAL THEME */
    .stApp {
        background-color: #0E1117; /* High contrast dark background */
        color: #FAFAFA;
    }

    /* SIDEBAR STYLING */
    section[data-testid="stSidebar"] {
        background-color: #161B22; /* GitHub Dark styled sidebar */
        border-right: 1px solid #30363D;
    }
    
    /* METRIC CARDS (KPIs) */
    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        border-color: #FF9F1C; /* Orange glow on hover */
    }
    div[data-testid="stMetricLabel"] {
        color: #8B949E; /* Muted text for labels */
        font-size: 14px;
        font-weight: 500;
    }
    div[data-testid="stMetricValue"] {
        color: #FFFFFF;
        font-size: 28px;
        font-weight: 700;
    }

    /* CUSTOM PROGRESS BARS */
    .stProgress > div > div > div > div {
        background-image: linear-gradient(90deg, #FF9F1C, #FF6B6B); /* Orange gradient */
    }

    /* DATAFRAME & TABLES */
    div[data-testid="stDataFrame"] {
        border: 1px solid #30363D;
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* HEADERS & TYPOGRAPHY */
    h1, h2, h3 {
        color: #FAFAFA !important;
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    p, span, label {
        color: #C9D1D9 !important;
    }
    
    /* BUTTONS */
    div.stButton > button {
        background-color: #FF9F1C;
        color: #0E1117;
        font-weight: 600;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        transition: all 0.2s;
    }
    div.stButton > button:hover {
        background-color: #FFB74D;
        color: #0E1117;
        box-shadow: 0 0 10px rgba(255, 159, 28, 0.4);
    }

    /* CENTER LOGO */
    .logo-container {
        display: flex;
        justify_content: center;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. CLIENT CONFIGURATION ---
try:
    CLIENTS = st.secrets["clients"]
except FileNotFoundError:
    st.error("Secrets not configured! Please configure .streamlit/secrets.toml locally.")
    CLIENTS = {}

ENDPOINT = "https://api.newrelic.com/graphql"

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("🎛️ Controls")
    
    # Customer Selector
    customer_keys = list(CLIENTS.keys())
    customer_options = ["All Customers"] + customer_keys if customer_keys else ["No Clients Configured"]
    selected_view = st.selectbox("Select Customer", customer_options)

    st.write("") # Spacer

    # Status Filter (Styled Radio)
    st.markdown("### Status")
    status_filter = st.radio(
        "Status Filter", 
        ["All", "Active", "Closed"], 
        horizontal=True, 
        label_visibility="collapsed"
    )

    st.write("") # Spacer

    # Time Frame
    st.markdown("### Time Range")
    time_ranges = {
        "Last 60 Minutes": "SINCE 60 minutes ago",
        "Last 24 Hours": "SINCE 24 hours ago",
        "Last 3 Days": "SINCE 3 days ago",
        "Last 7 Days": "SINCE 7 days ago",
        "Last 30 Days": "SINCE 30 days ago"
    }
    time_options = list(time_ranges.keys()) + ["Custom Date Range"]
    selected_time_label = st.selectbox("Time Frame", time_options, label_visibility="collapsed")

    if selected_time_label == "Custom Date Range":
        col_d1, col_d2 = st.columns(2)
        start_date = col_d1.date_input("Start", datetime.date.today() - datetime.timedelta(days=1))
        end_date = col_d2.date_input("End", datetime.date.today())
        time_clause = f"SINCE '{start_date} 00:00:00' UNTIL '{end_date} 23:59:59'"
    else:
        time_clause = time_ranges[selected_time_label]
        
    st.divider()
    apply_btn = st.button("Apply Filters", type="primary", use_container_width=True)
    st.caption(f"Last updated: {datetime.datetime.now().strftime('%H:%M:%S')}")

# --- 3. LOGIC ---
def categorize_alert(row):
    text = (str(row['policyName']) + " " + str(row['conditionName'])).lower()
    infra_keywords = ['cpu', 'memory', 'disk', 'storage', 'network', 'host', 'server', 'load balancer', 'latency', 'k8s', 'kubernetes', 'pod', 'node', 'db', 'database', 'gcp']
    if any(k in text for k in infra_keywords): return 'Infra'
    return 'SOC'

def format_duration(td):
    total_seconds = int(td.total_seconds())
    if total_seconds < 60: return f"{total_seconds}s"
    m, s = divmod(total_seconds, 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h}h {m}m"
    return f"{m}m {s}s"

# Updated styler for better contrast in dark mode
def style_status_column(val):
    if val == 'Active':
        return 'color: #FF5252; font-weight: 800;'  # Bright Red
    elif val == 'Closed':
        return 'color: #69F0AE; font-weight: 700;'  # Bright Green
    return ''

# --- 4. DATA FETCHING ---
@st.cache_data(ttl=300, show_spinner=False)
def fetch_single_account(client_name, api_key, account_id, time_filter):
    query = f"""
    {{
      actor {{
        account(id: {account_id}) {{
          nrql(query: "SELECT timestamp, policyName, conditionName, priority, incidentId, event, entity.name FROM NrAiIncident WHERE event IN ('open', 'close') {time_filter} LIMIT MAX") {{
            results
          }}
        }}
      }}
    }}
    """
    headers = {"API-Key": api_key, "Content-Type": "application/json"}
    try:
        response = requests.post(ENDPOINT, json={"query": query}, headers=headers)
        if response.status_code == 200:
            data = response.json().get('data', {}).get('actor', {}).get('account', {}).get('nrql', {}).get('results', [])
            df = pd.DataFrame(data)
            if not df.empty:
                df['Customer'] = client_name
                # Normalize columns
                if 'entity.name' in df.columns: df.rename(columns={'entity.name': 'Entity'}, inplace=True)
                elif 'entityName' not in df.columns: df['Entity'] = 'System'
                return df
    except Exception:
        pass
    return pd.DataFrame()

# --- 5. MAIN APP LAYOUT ---

# --- HEADER SECTION ---
try:
    c1, c2, c3 = st.columns([1, 2, 1]) 
    with c2:
        st.image("logo.png", use_container_width=True) 
except Exception:
    st.markdown("<h1 style='text-align: center; color: #FF9F1C;'>🔥 Quickplay</h1>", unsafe_allow_html=True)

st.markdown("<h3 style='text-align: center; margin-top: -10px; opacity: 0.8;'>Stability & Incident Overview</h3>", unsafe_allow_html=True)
st.divider()

if not CLIENTS:
    st.warning("⚠️ Configuration Needed: Please add API keys to secrets.toml")
else:
    with st.spinner('Fetching live incident data...'):
        all_data = []
        targets = CLIENTS.items() if selected_view == "All Customers" else [(selected_view, CLIENTS[selected_view])]
        
        for name, creds in targets:
            df_client = fetch_single_account(name, creds['api_key'], creds['account_id'], time_clause)
            if not df_client.empty: all_data.append(df_client)

    if all_data:
        raw_df = pd.concat(all_data, ignore_index=True)
        raw_df['timestamp'] = pd.to_datetime(raw_df['timestamp'], unit='ms')
        if 'Entity' not in raw_df.columns: raw_df['Entity'] = 'N/A'

        # Aggregation Logic
        grouped = raw_df.groupby(['incidentId', 'Customer', 'policyName', 'conditionName', 'priority', 'Entity']).agg(
            start_time=('timestamp', 'min'),
            end_time=('timestamp', 'max'),
            event_count=('event', 'nunique')
        ).reset_index()

        grouped['Status'] = grouped['event_count'].apply(lambda x: 'Active' if x == 1 else 'Closed')
        now = datetime.datetime.now()
        grouped['Duration'] = grouped.apply(lambda x: format_duration((now - x['start_time']) if x['Status'] == 'Active' else (x['end_time'] - x['start_time'])), axis=1)
        grouped['Category'] = grouped.apply(categorize_alert, axis=1)
        
        # Filtering
        if status_filter == "Active":
            df_display = grouped[grouped['Status'] == 'Active']
        elif status_filter == "Closed":
            df_display = grouped[grouped['Status'] == 'Closed']
        else:
            df_display = grouped
        
        df_display = df_display.sort_values(by='start_time', ascending=False)

        # --- KPI CARDS ROW ---
        # Using columns to create a "Dashboard Card" look
        m1, m2, m3, m4 = st.columns(4)
        
        total_incidents = len(df_display)
        active_now = len(df_display[df_display['Status'] == 'Active'])
        infra_count = len(df_display[df_display['Category'] == 'Infra'])
        soc_count = len(df_display[df_display['Category'] == 'SOC'])

        m1.metric("Total Incidents", total_incidents, border=True)
        m2.metric("🔥 Active Now", active_now, delta=active_now if active_now > 0 else None, delta_color="inverse", border=True)
        m3.metric("🏗️ Infra Alerts", infra_count, border=True)
        m4.metric("🛡️ SOC Alerts", soc_count, border=True)

        st.markdown("###") # Spacing

        # --- VOLUME BY CUSTOMER ---
        if not df_display.empty:
            with st.container():
                st.subheader("📊 Customer Volume")
                cust_counts = df_display['Customer'].value_counts().reset_index()
                cust_counts.columns = ['Customer', 'Total Alerts']
                
                st.dataframe(
                    cust_counts,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Customer": st.column_config.TextColumn("Customer", width="medium"),
                        "Total Alerts": st.column_config.ProgressColumn(
                            "Volume",
                            format="%d",
                            min_value=0,
                            max_value=int(cust_counts['Total Alerts'].max()) if not cust_counts.empty else 100,
                        )
                    }
                )

        # --- BY ALERTS SECTION ---
        st.subheader("🔎 Alert Breakdown")
        
        if df_display.empty:
            st.success(f"No {status_filter.lower()} alerts found. Systems are stable! 🎉")
        else:
            top_alerts = df_display['conditionName'].value_counts()
            
            # Summary Table
            summary_df = top_alerts.reset_index()
            summary_df.columns = ['Alert Condition', 'Frequency']
            
            st.dataframe(
                summary_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Alert Condition": st.column_config.TextColumn("Condition Name", width="large"),
                    "Frequency": st.column_config.ProgressColumn(
                        "Count", 
                        format="%d", 
                        min_value=0, 
                        max_value=int(top_alerts.max())
                    )
                }
            )

            # Drill Down Expanders
            st.caption("👇 Click to expand specific alerts and see affected entities")
            for i, (alert_name, total_count) in enumerate(top_alerts.items()):
                # Dynamic Icon based on count urgency
                icon = "🔥" if i < 2 else "⚠️"
                
                with st.expander(f"{icon} **{alert_name}** — ({total_count} incidents)"):
                    subset = df_display[df_display['conditionName'] == alert_name]
                    entity_counts = subset['Entity'].value_counts().reset_index()
                    entity_counts.columns = ['Entity Name', 'Count']
                    
                    st.dataframe(
                        entity_counts, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "Entity Name": st.column_config.TextColumn("Affected Entity"),
                            "Count": st.column_config.NumberColumn("Incidents", format="%d")
                        }
                    )

        st.divider()

        # --- DETAILED LOGS TABLE ---
        st.subheader("📝 Live Incident Logs")
        
        common_config = {
            "start_time": st.column_config.DatetimeColumn("Time (UTC)", format="D MMM, HH:mm"),
            "Entity": st.column_config.TextColumn("Entity", width="medium"),
            "conditionName": st.column_config.TextColumn("Condition", width="large"),
            "Status": st.column_config.TextColumn("State", width="small"),
            "Duration": st.column_config.TextColumn("Duration", width="small"),
        }
        cols = ['start_time', 'Customer', 'Entity', 'conditionName', 'priority', 'Status', 'Duration']

        tab1, tab2 = st.tabs(["🏗️ **Infrastructure**", "🛡️ **Security (SOC)**"])
        
        with tab1:
            infra_df = df_display[df_display['Category'] == 'Infra']
            if not infra_df.empty:
                st.dataframe(
                    infra_df[cols].style.map(style_status_column, subset=['Status']), 
                    use_container_width=True, 
                    hide_index=True, 
                    column_config=common_config
                )
            else:
                st.info("No Infrastructure incidents recorded.")

        with tab2:
            soc_df = df_display[df_display['Category'] == 'SOC']
            if not soc_df.empty:
                st.dataframe(
                    soc_df[cols].style.map(style_status_column, subset=['Status']), 
                    use_container_width=True, 
                    hide_index=True, 
                    column_config=common_config
                )
            else:
                st.info("No SOC incidents recorded.")

    else:
        st.warning("No data returned from New Relic. Check your API keys or Time Frame.")
