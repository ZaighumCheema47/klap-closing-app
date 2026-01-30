import streamlit as st

# ---------- Force Hide Side Bar ----------

st.set_page_config(initial_sidebar_state="collapsed") #

st.markdown("""
    <style>
        [data-testid="stSidebar"] {
            display: none;
        }
        [data-testid="collapsedControl"] {
            display: none;
        }
    </style>
""", unsafe_allow_html=True) #

# ---------- GEMINI ---------





st.set_page_config(page_title="KLAP Management System", layout="centered")

# Custom CSS for big, easy-to-tap buttons
st.markdown("""
    <style>
    div.stButton > button:first-child {
        height: 150px;
        font-size: 24px;
        font-weight: bold;
        border-radius: 15px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🍽️ KLAP Dashboard")
st.write("Select a module to continue:")

col1, col2 = st.columns(2)

with col1:
    if st.button("📝\nDaily Closing", use_container_width=True):
        st.switch_page("pages/closing.py")

with col2:
    if st.button("🧾\nBilling (New)", use_container_width=True):
        st.switch_page("pages/billing.py")
