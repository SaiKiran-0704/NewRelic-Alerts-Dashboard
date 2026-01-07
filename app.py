# Replace this section in your code:
# -------- CUSTOMER CHART - CARDS VIEW --------

if customer == "All Customers":
    st.markdown("### Alerts by Customer")
    
    customer_counts = df["Customer"].value_counts().sort_values(ascending=False)
    
    # Create cards in rows (3 cards per row)
    cols_per_row = 3
    
    for i in range(0, len(customer_counts), cols_per_row):
        cols = st.columns(cols_per_row)
        
        for j, (cust_name, count) in enumerate(list(customer_counts.items())[i:i+cols_per_row]):
            with cols[j]:
                # Get logo path for customer
                logo_path = CUSTOMER_LOGOS.get(cust_name)
                
                if logo_path:
                    # Card with logo as background
                    card_html = f"""
                    <div style="
                        background-image: url('{logo_path}');
                        background-size: cover;
                        background-position: center;
                        border-radius: 12px;
                        padding: 20px;
                        text-align: center;
                        cursor: pointer;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                        position: relative;
                        min-height: 200px;
                        display: flex;
                        flex-direction: column;
                        justify-content: flex-start;
                        align-items: center;
                        overflow: hidden;
                    ">
                        <div style="
                            background: rgba(0, 0, 0, 0.5);
                            backdrop-filter: blur(4px);
                            border-radius: 8px;
                            padding: 12px 20px;
                            color: white;
                            font-size: 28px;
                            font-weight: bold;
                            margin-top: 10px;
                            min-width: 80px;
                        ">
                            {count}
                        </div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)
                else:
                    # Fallback if no logo
                    card_html = f"""
                    <div style="
                        background: linear-gradient(135deg, #FF9F1C 0%, #FF8C00 100%);
                        border-radius: 12px;
                        padding: 20px;
                        text-align: center;
                        cursor: pointer;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                        color: white;
                        min-height: 200px;
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                    ">
                        <div style="font-size: 18px; font-weight: bold; margin-bottom: 10px;">{cust_name}</div>
                        <div style="font-size: 32px; font-weight: bold;">{count}</div>
                        <div style="font-size: 12px; margin-top: 8px; opacity: 0.9;">Alerts</div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)
                
                # Button to drill down
                if st.button(f"View {cust_name}", key=f"btn_{cust_name}"):
                    st.session_state.clicked_customer = cust_name
                    st.rerun()
