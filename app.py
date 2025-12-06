import streamlit as st
import requests
import pandas as pd
import datetime
import altair as alt

# --- PAGE SETUP ---
st.set_page_config(page_title="Alerts Summary", layout="wide", page_icon="🛡️")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .main > div { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# --- 1. CLIENT CONFIGURATION ---
    try:
    CLIENTS = st.secrets["clients"]
except FileNotFoundError:
    st.error("Secrets not configured!")
    CLIENTS = {}

ENDPOINT = "https://api.newrelic.com/graphql"

# --- 2. SIDEBAR ---
with st.sidebar:
    st.header("🎛️ Dashboard Controls")
    customer_keys = list(CLIENTS.keys())
    customer_options = ["All Customers"] + customer_keys if customer_keys else ["No Clients Configured"]
    
    selected_view = st.selectbox("Select Customer", customer_options)

    time_ranges = {
        "Last 60 Minutes": "SINCE 60 minutes ago",
        "Last 24 Hours": "SINCE 24 hours ago",
        "Last 3 Days": "SINCE 3 days ago",
        "Last 7 Days": "SINCE 7 days ago",
        "Last 30 Days": "SINCE 30 days ago"
    }
    selected_time_label = st.selectbox("Time Frame", list(time_ranges.keys()))
    time_clause = time_ranges[selected_time_label]
    st.divider()

# --- 3. LOGIC ---
def categorize_alert(row):
    text_to_search = (str(row['policyName']) + " " + str(row['conditionName'])).lower()
    if 'gcp' in text_to_search: return 'Infra'
    infra_keywords = ['cpu', 'memory', 'disk', 'storage', 'network', 'host', 'server', 'load balancer', 'latency', 'k8s', 'kubernetes', 'pod', 'node', 'db', 'database']
    if any(keyword in text_to_search for keyword in infra_keywords): return 'Infra'
    return 'SOC'

def format_duration(td):
    total_seconds = int(td.total_seconds())
    if total_seconds < 60: return f"{total_seconds}s"
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0: return f"{hours}h {minutes}m"
    return f"{minutes}m {seconds}s"

# --- COLOR STYLING FUNCTION ---
def style_status_column(val):
    if val == 'Active':
        return 'color: #d32f2f; font-weight: bold;'  # Red
    elif val == 'Closed':
        return 'color: #2e7d32; font-weight: bold;'  # Green
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
                if 'entity.name' in df.columns: df.rename(columns={'entity.name': 'Entity'}, inplace=True)
                elif 'entityName' not in df.columns: df['Entity'] = 'System'
                return df
    except Exception:
        pass
    return pd.DataFrame()

# --- 5. MAIN APP ---
st.title("🛡️ Alerts Summary")

if not CLIENTS:
    st.info("⚠️ Please configure the CLIENTS dictionary in the code to see data.")
else:
    st.markdown(f"Overview for **{selected_view}** over **{selected_time_label}**")

    with st.spinner('Syncing with New Relic...'):
        all_data = []
        targets = CLIENTS.items() if selected_view == "All Customers" else [(selected_view, CLIENTS[selected_view])]
        
        for name, creds in targets:
            df_client = fetch_single_account(name, creds['api_key'], creds['account_id'], time_clause)
            if not df_client.empty: all_data.append(df_client)

    if all_data:
        raw_df = pd.concat(all_data, ignore_index=True)
        raw_df['timestamp'] = pd.to_datetime(raw_df['timestamp'], unit='ms')
        if 'Entity' not in raw_df.columns: raw_df['Entity'] = 'N/A'

        # Processing
        grouped = raw_df.groupby(['incidentId', 'Customer', 'policyName', 'conditionName', 'priority', 'Entity']).agg(
            start_time=('timestamp', 'min'),
            end_time=('timestamp', 'max'),
            event_count=('event', 'nunique')
        ).reset_index()

        grouped['Status'] = grouped['event_count'].apply(lambda x: 'Active' if x == 1 else 'Closed')
        now = datetime.datetime.now()
        grouped['Duration'] = grouped.apply(lambda x: format_duration((now - x['start_time']) if x['Status'] == 'Active' else (x['end_time'] - x['start_time'])), axis=1)
        grouped['Category'] = grouped.apply(categorize_alert, axis=1)
        
        # Sort logs by time
        df_display = grouped.sort_values(by='start_time', ascending=False)

        # --- UI: TOTAL ALERTS BY CUSTOMER ---
        if not df_display.empty:
            st.subheader("👥 Volume by Customer")
            
            cust_counts = df_display['Customer'].value_counts().reset_index()
            cust_counts.columns = ['Customer', 'Total Alerts']
            
            st.dataframe(
                cust_counts,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Customer": st.column_config.TextColumn("Customer Name", width="medium"),
                    "Total Alerts": st.column_config.ProgressColumn(
                        "Incident Count",
                        format="%d",
                        min_value=0,
                        max_value=int(cust_counts['Total Alerts'].max()) if not cust_counts.empty else 100,
                    )
                }
            )
            st.divider()

        # --- UI: INTERACTIVE CHART & BY ALERTS ---
        col_chart, col_drill = st.columns([2, 1])

        with col_chart:
            st.subheader(f"📊 Volume ({selected_time_label})")
            
            # --- ALTAIR INTERACTIVE CHART ---
            
            if "Minutes" in selected_time_label:
                time_unit = 'yearmonthdatehoursminutes' 
                x_format = '%H:%M'
                tooltip_format = '%H:%M'
                
            elif "30 Days" in selected_time_label:
                time_unit = 'yearweek'
                x_format = 'Week %U'
                tooltip_format = '%d %b'
                
            else:
                time_unit = 'yearmonthdate'
                x_format = '%d %b'
                tooltip_format = '%d %b'

            selection = alt.selection_point(fields=['conditionName'], bind='legend')

            chart = alt.Chart(df_display).mark_area(interpolate='monotone').encode(
                x=alt.X('start_time', title='Time', timeUnit=time_unit, axis=alt.Axis(format=x_format, labelOverlap=True)),
                y=alt.Y('count()', title='Incident Count', stack=True),
                color=alt.Color('conditionName', legend=alt.Legend(title="Alert Type", orient='bottom', columns=1)),
                opacity=alt.condition(selection, alt.value(0.7), alt.value(0.05)),
                tooltip=[
                    alt.Tooltip('conditionName', title='Alert'),
                    alt.Tooltip('count()', title='Count'),
                    alt.Tooltip('start_time', title='Time', format=tooltip_format, timeUnit=time_unit)
                ]
            ).add_params(
                selection
            ).properties(
                height=400
            ).interactive()

            st.altair_chart(chart, use_container_width=True)

        with col_drill:
            st.subheader("🔎 By Alerts")
            
            top_alerts = df_display['conditionName'].value_counts().head(10)

            if top_alerts.empty:
                st.info("No alerts to display.")
            else:
                # 1. SUMMARY TABLE (Alert + Count)
                summary_df = top_alerts.reset_index()
                summary_df.columns = ['Alert Name', 'Count']
                
                st.dataframe(
                    summary_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Alert Name": st.column_config.TextColumn("Alert Condition", width="medium"),
                        "Count": st.column_config.ProgressColumn(
                            "Frequency", 
                            format="%d", 
                            min_value=0, 
                            max_value=int(top_alerts.max())
                        )
                    }
                )
                
                st.write("---")
                st.caption("Drill Down (Affected Entities)")

                # 2. EXPANDERS (Dropdowns)
                for i, (alert_name, total_count) in enumerate(top_alerts.items()):
                    icon = "🔥" if i == 0 else "🚨"
                    # Simplified label since the table above has the stats
                    label_text = f"{icon} {alert_name}"
                    
                    with st.expander(label_text):
                        subset = df_display[df_display['conditionName'] == alert_name]
                        entity_counts = subset['Entity'].value_counts().reset_index()
                        entity_counts.columns = ['Entity Name', 'Count']
                        
                        st.dataframe(
                            entity_counts, 
                            use_container_width=True, 
                            hide_index=True,
                            column_config={
                                "Count": st.column_config.ProgressColumn(
                                    "Impact", 
                                    format="%d", 
                                    max_value=int(total_count)
                                )
                            }
                        )

        st.divider()

        # --- UI: DETAILED LOGS (WITH COLORS) ---
        st.subheader("📝 Detailed Logs")
        
        common_config = {
            "start_time": st.column_config.DatetimeColumn("Time", format="D MMM, HH:mm"),
            "Entity": st.column_config.TextColumn("Entity Name", width="medium"),
            "conditionName": st.column_config.TextColumn("Alert Description", width="large"),
            "Status": st.column_config.TextColumn("Status", width="small"),
        }
        cols = ['start_time', 'Customer', 'Entity', 'conditionName', 'priority', 'Status', 'Duration']

        tab1, tab2 = st.tabs(["🏗️ **Infra Alerts**", "🛡️ **SOC Alerts**"])
        
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
                st.success("No Infrastructure alerts.")

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
                st.success("No SOC alerts.")

    else:
        st.warning("No alerts found for the selected criteria.")
