import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components

# --- UI STYLING & PRINT CSS ---
st.set_page_config(page_title="KLAP Daily Closing", layout="centered")

st.markdown("""
<style>
    @media print {
        [data-testid="stSidebar"], [data-testid="stHeader"], .stButton, .stNumberInput, .stSelectbox, .stAlert, hr, .stMarkdown:not(.printable-receipt) {
            display: none !important;
        }
        .printable-receipt {
            visibility: visible !important;
            position: absolute;
            left: 0; top: 0;
            width: 80mm !important;
            font-family: 'Courier New', monospace !important;
            color: black !important;
        }
        body { background-color: white !important; }
    }
    .expense-row { border-bottom: 1px solid #444; padding: 10px 0; }
</style>
""", unsafe_allow_html=True)

# --- GOOGLE SHEETS CONNECTION ---
def post_to_gsheet(branch_name, data_rows):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
        sheet = client.open(sheet_title).sheet1
        sheet.append_rows(data_rows)
        return True
    except Exception as e:
        st.error(f"Sheet Error: {e}")
        return False

# --- APP LOGIC ---
st.title("🍽️ KLAP Daily Closing")

# 1. Branch & Date
col_b, col_d = st.columns(2)
with col_b:
    branch = st.selectbox("Select Branch", ["DHA Branch", "Cantt Lahore"])
with col_d:
    selected_date = st.date_input("Select Closing Date", datetime.now())
    # Pakistan Format: dd/mm/yyyy
    date_display = selected_date.strftime("%d/%m/%Y")

st.divider()

# 2. Sales Summary
st.subheader("💰 Revenue Summary")
total_sale = st.number_input("Total Sale (PKR)", min_value=0.0, step=1.0, value=None, placeholder="Enter Gross Amount")

c1, c2, c3 = st.columns(3)
cash_sales = c1.number_input("Cash Sales", min_value=0.0, value=None, placeholder="PKR")
card_sales = c2.number_input("Card Sales", min_value=0.0, value=None, placeholder="PKR")
fp_sales = c3.number_input("Foodpanda", min_value=0.0, value=None, placeholder="PKR")

# 3. Credit Card Tips
st.divider()
tip_status = st.radio("Were there any Credit Card Tips?", ["No", "Yes"], horizontal=True)
cc_tips = 0.0
if tip_status == "Yes":
    cc_tips = st.number_input("Enter Tip Amount (PKR)", min_value=0.0)

# 4. Cash Expenses
st.subheader("💸 Cash Expenses")
if 'expenses' not in st.session_state:
    st.session_state.expenses = []

predefined = ["Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill"]
cat_choice = st.selectbox("Category", predefined + ["Other..."])
final_cat = st.text_input("Custom Category Name") if cat_choice == "Other..." else cat_choice

exp_desc = st.text_input("Description", placeholder="e.g. Repairing AC")
exp_amt = st.number_input("Amount", min_value=0.0, key="exp_input", value=None, placeholder="PKR")

if st.button("Add Expense ➕"):
    if exp_amt and exp_amt > 0:
        st.session_state.expenses.append({
            "Date": date_display,
            "Category": final_cat,
            "Description": exp_desc,
            "Amount": exp_amt
        })
        st.rerun()

# Better Presentation of Added Expenses
st.markdown("### Added Entries")
total_expenses = 0.0
for i, exp in enumerate(st.session_state.expenses):
    exp_col = st.columns([2, 2, 3, 2, 1])
    exp_col[0].write(exp['Date'])
    exp_col[1].write(exp['Category'])
    exp_col[2].write(exp['Description'])
    exp_col[3].write(f"PKR {exp['Amount']:,.0f}")
    if exp_col[4].button("🗑️", key=f"del_{i}"):
        st.session_state.expenses.pop(i)
        st.rerun()
    total_expenses += exp['Amount']

# 5. Final Reconciliation
st.divider()
final_cash_sales = cash_sales if cash_sales else 0.0
expected_cash = final_cash_sales - total_expenses - cc_tips
st.metric("Final Cash in Hand", f"PKR {expected_cash:,.0f}")

# 6. Submit & Print
if st.button("🖨️ Confirm & Print Receipt"):
    # Build list for GSheet
    rows = [[e['Date'], f"[{e['Category']}] {e['Description']}", e['Amount']] for e in st.session_state.expenses]
    
    # If there were tips, add them as an expense line item
    if cc_tips > 0:
        rows.append([date_display, "[CC TIP] Paid to Staff", cc_tips])
    
    if post_to_gsheet(branch, rows):
        st.success("Data Sent to Google Sheets!")
        
        # HTML Receipt for Black Copper 85
        receipt_html = f"""
        <div class="printable-receipt" style="background-color:white; color:black; padding:15px; border:1px solid black; width:75mm;">
            <h2 style="text-align:center; margin:0;">KLAP</h2>
            <p style="text-align:center;">{branch}<br>Date: {date_display}</p>
            <hr style="border-top:1px dashed black;">
            <p>Cash Sale: <span style="float:right;">{final_cash_sales:,.0f}</span></p>
            <p>CC Tips: <span style="float:right;">({cc_tips:,.0f})</span></p>
            <p><b>Expenses:</b></p>
            {"".join([f"<p style='margin:0 0 0 10px; font-size:12px;'>{e['Category']}: {e['Amount']:,.0f}</p>" for e in st.session_state.expenses])}
            <hr style="border-top:1px dashed black;">
            <h3 style="text-align:center;">CASH IN HAND: {expected_cash:,.0f}</h3>
        </div>
        """
        st.markdown(receipt_html, unsafe_allow_html=True)
        components.html("<script>window.parent.print();</script>", height=0)
        st.session_state.expenses = []
