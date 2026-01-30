import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import gspread

# MUST be the first line
st.set_page_config(page_title="KLAP Master Hub", layout="wide")

# --- SHARED AUTHENTICATION CORE ---
# This ensures both Closing and Billing modules use the same credentials
def get_gcp_creds():
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    return Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], 
        scopes=SCOPES
    )

# --- NAVIGATION LOGIC ---
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
# We use st.container to keep the 'Back' button consistently at the top
else:
    with st.container():
        if st.button("⬅️ Back to Hub", key="back_btn"):
            switch_to("Hub")
    
    st.divider()

    if st.session_state.active_module == "Closing":
        import closing_module
        closing_module.run_closing()

    elif st.session_state.active_module == "Billing":
        import billing_module
        billing_module.run_billing()
