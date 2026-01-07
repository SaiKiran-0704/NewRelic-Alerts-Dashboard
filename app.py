# ---------------- ALERTS BY CUSTOMER (WITH IMAGES) ----------------
if customer == "All Customers":
    st.markdown("### Alerts by Customer")
    counts = df["Customer"].value_counts()

    cols_per_row = 3
    for i in range(0, len(counts), cols_per_row):
        cols = st.columns(cols_per_row)

        for j, (cust, cnt) in enumerate(list(counts.items())[i:i + cols_per_row]):
            with cols[j]:
                image_url = CUSTOMER_IMAGES.get(
                    cust,
                    "https://cdn-icons-png.flaticon.com/512/847/847969.png"  # fallback
                )

                st.markdown('<div class="customer-card">', unsafe_allow_html=True)

                st.image(image_url, width=80)
                st.markdown(
                    f'<div class="customer-count">{cnt}</div>',
                    unsafe_allow_html=True
                )
                st.markdown(
                    f'<div class="customer-name">{cust}</div>',
                    unsafe_allow_html=True
                )

                if st.button(
                    "View Alerts",
                    key=f"card_{cust}",
                    use_container_width=True
                ):
                    st.session_state.navigate_to_customer = cust
                    st.rerun()

                st.markdown('</div>', unsafe_allow_html=True)
