import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components

# --- 1. PRINT & UI STYLING ---
# This CSS ensures that only the receipt is visible when the printer is triggered
st.set_page_config(page_title="KLAP Daily Closing", layout="centered")

st.markdown("""
<style>
    @media print {
        /* Hide everything except the receipt area */
        [data-testid="stSidebar"], [data-testid="stHeader"], .stButton, .stNumberInput, .stSelectbox, .stAlert, hr, .stMarkdown:not(.printable-receipt) {
            display: none !important;
        }
        /* Format the receipt for 80mm Black Copper printer */
        .printable-receipt {
            visibility: visible !important;
            position: absolute;
            left: 0;
            top: 0;
            width: 80mm !important;
            font-family: 'Courier New', Courier, monospace !important;
            color: black !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        body { background-color: white !important; }
    }
</style>
""", unsafe_allow_html=True)

# --- 2. GOOGLE SHEETS CONNECTION ---
def post_to_gsheet(branch_name, data_rows):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # Pulling credentials from Streamlit Secrets
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        
        # Select sheet based on branch
        sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
        sheet = client.open(sheet_title).sheet1
        
        sheet.append_rows(data_rows)
        return True
    except Exception as e:
        st.error(f"Sheet Connection Error: {e}")
        return False

# --- 3. UI INTERFACE ---
st.title("🍽️ KLAP Daily Closing")

# Branch & Date Setup
col_b, col_d = st.columns(2)
with col_b:
    branch = st.selectbox("Select Branch", ["DHA Branch", "Cantt Lahore"])
with col_d:
    selected_date = st.date_input("Closing Date", datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

st.divider()

# Sales Entry
st.subheader("💰 Revenue Summary")
total_sale = st.number_input("Total Sale (Combined)", min_value=0.0, step=100.0)

c1, c2, c3 = st.columns(3)
cash_sales = c1.number_input("Cash Sales", min_value=0.0)
card_sales = c2.number_input("Card Sales", min_value=0.0)
fp_sales = c3.number_input("Foodpanda Sales", min_value=0.0)

# Tips Deduction
st.divider()
cc_tips = st.number_input("Credit Card Tips (Deducted from Cash)", min_value=0.0, help="Tips paid out to staff from the cash drawer.")

# Expenses Entry
st.subheader("💸 Cash Expenses")
if 'expense_entries' not in st.session_state:
    st.session_state.expense_entries = []

predefined = ["Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill"]
cat_choice = st.selectbox("Category", predefined + ["Other..."])

final_cat = cat_choice
if cat_choice == "Other...":
    final_cat = st.text_input("Type New Category")

exp_desc = st.text_input("Description (e.g. 'Repairing AC')")
exp_amt = st.number_input("Amount (Rs.)", min_value=0.0, key="exp_amt_input")

if st.button("Add Expense ➕"):
    if exp_amt > 0:
        st.session_state.expense_entries.append({
            "Date": date_str,
            "Description": f"[{final_cat}] {exp_desc}",
            "Amount": exp_amt
        })
        st.rerun()

# Expense Table
total_expenses = 0.0
if st.session_state.expense_entries:
    df_exp = pd.DataFrame(st.session_state.expense_entries)
    st.table(df_exp)
    total_expenses = df_exp["Amount"].sum()

# Calculations
st.divider()
expected_cash = cash_sales - total_expenses - cc_tips
st.metric("Expected Cash in Hand", f"Rs. {expected_cash:,.2f}")

# --- 4. SUBMISSION & PRINT TRIGGER ---
if st.button("Confirm Closing & Post to Google Sheets"):
    if not st.session_state.expense_entries and cash_sales == 0:
        st.warning("Please enter data before submitting.")
    else:
        # 1. Format for GSheets
        rows = [[date_str, e['Description'], e['Amount']] for e in st.session_state.expense_entries]
        
        # 2. Post Data
        if post_to_gsheet(branch, rows):
            st.success("Successfully posted to Google Sheets!")
            
            # 3. Create Receipt HTML
            receipt_html = f"""
            <div class="printable-receipt" style="background-color:white; color:black; padding:15px; font-family:monospace; border:1px solid black; width:75mm; margin:auto;">
                <h2 style="text-align:center; margin:0;">KLAP</h2>
                <p style="text-align:center; margin:5px 0;">{branch}<br>{date_str}</p>
                <hr style="border-top: 1px dashed black;">
                <p style="margin:2px 0;">Total Sale: <span style="float:right;">{total_sale:,.0f}</span></p>
                <p style="margin:2px 0;">Cash Sales: <span style="float:right;">{cash_sales:,.0f}</span></p>
                <p style="margin:2px 0;">Card Sales: <span style="float:right;">{card_sales:,.0f}</span></p>
                <p style="margin:2px 0;">Foodpanda: <span style="float:right;">{fp_sales:,.0f}</span></p>
                <hr style="border-top: 1px dashed black;">
                <p style="margin:2px 0;">CC Tips: <span style="float:right;">({cc_tips:,.0f})</span></p>
                <p style="margin:5px 0;"><b>EXPENSES:</b></p>
                {"".join([f"<p style='margin:0 0 0 10px; font-size:12px;'>{e['Description']}<span style='float:right;'>{e['Amount']:,.0f}</span></p>" for e in st.session_state.expense_entries])}
                <hr style="border-top: 1px dashed black;">
                <h3 style="text-align:center; margin:10px 0;">CASH IN HAND: {expected_cash:,.0f}</h3>
                <p style="text-align:center; font-size:10px;">End of Report</p>
            </div>
            """
            st.markdown(receipt_html, unsafe_allow_html=True)
            
            # 4. Trigger JavaScript Print
            components.html(
                """
                <script>
                    window.parent.print();
                </script>
                """,
                height=0,
            )
            
            # Clear state for next entry
            st.session_state.expense_entries = []
