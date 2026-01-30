import streamlit as st

# MUST be the first line in the main entry file
st.set_page_config(page_title="KLAP Master Hub", layout="wide")

# Initialize state to track which module is open
if "active_module" not in st.session_state:
    st.session_state.active_module = "Hub"

def switch_to(module_name):
    st.session_state.active_module = module_name
    st.rerun()

# --- LANDING PAGE UI ---
if st.session_state.active_module == "Hub":
    st.title("🚀 KLAP Operations Hub")
    st.subheader("Select a Department")
    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.info("### 📊 Closing\nDaily sales & expenses reporting.")
        if st.button("Open Closing Module", use_container_width=True, type="primary"):
            switch_to("Closing")

    with col2:
        st.success("### 🧾 Billing\nVendor supply bills & AI extraction.")
        if st.button("Open Billing Module", use_container_width=True, type="primary"):
            switch_to("Billing")

    with col3:
        st.warning("### 📦 Inventory\nStock management (Coming Soon).")
        st.button("Inventory Locked", use_container_width=True, disabled=True)

# --- MODULE ROUTING ---
elif st.session_state.active_module == "Closing":
    import closing_module
    if st.button("⬅️ Back to Hub"): switch_to("Hub")
    closing_module.run_closing()

elif st.session_state.active_module == "Billing":
    import billing_module
    if st.button("⬅️ Back to Hub"): switch_to("Hub")
    billing_module.run_billing()
