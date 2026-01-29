import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- GOOGLE SHEETS CONNECTION ---
def post_to_gsheet(branch_name, data_rows):
    try:
        # Define the scope
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        # Pulling credentials from Streamlit Secrets (for Cloud Hosting)
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        
        # Branch-specific sheet selection
        # Ensure these names match your actual Google Sheet file names exactly
        sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
        sheet = client.open(sheet_title).sheet1
        
        sheet.append_rows(data_rows)
        return True
    except Exception as e:
        st.error(f"Google Sheets Error: {e}")
        return False

# --- UI SETUP ---
st.set_page_config(page_title="KLAP Daily Closing", layout="centered")
st.title("🍽️ KLAP Daily Closing")

# 1. Branch & Date Selection
col_b, col_d = st.columns(2)
with col_b:
    branch = st.selectbox("Select Branch", ["DHA Branch", "Cantt Lahore"])
with col_d:
    selected_date = st.date_input("Select Closing Date", datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

st.divider()

# 2. Sales Summary
st.subheader("💰 Revenue Summary")
total_sale = st.number_input("Total Sale (Combined)", min_value=0.0, step=100.0)

c1, c2, c3 = st.columns(3)
cash_sales = c1.number_input("Cash Sales", min_value=0.0)
card_sales = c2.number_input("Card Sales", min_value=0.0)
fp_sales = c3.number_input("Foodpanda Sales", min_value=0.0)

# 3. Credit Card Tips Deduction
st.divider()
st.info("💡 CC Tips are deducted from the drawer cash because the restaurant pays the staff in cash for tips recorded on the machine.")
cc_tips = st.number_input("Credit Card Tips Amount", min_value=0.0)

# 4. Cash Expenses Section
st.subheader("💸 Cash Expenses")
if 'expense_entries' not in st.session_state:
    st.session_state.expense_entries = []

predefined = ["Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill"]
cat_choice = st.selectbox("Select Category", predefined + ["Add New Category..."])

final_cat = cat_choice
if cat_choice == "Add New Category...":
    final_cat = st.text_input("Type New Category Name")

exp_desc = st.text_input("Expense Details (e.g. 'Vendor payment')")
exp_amt = st.number_input("Amount (Rs.)", min_value=0.0, key="current_exp_amt")

if st.button("Add Expense ➕"):
    if exp_amt > 0 and final_cat:
        st.session_state.expense_entries.append({
            "Date": date_str,
            "Description": f"[{final_cat}] {exp_desc}",
            "Amount": exp_amt
        })
        st.rerun()

# Display Expense List
total_expenses = 0.0
if st.session_state.expense_entries:
    df_exp = pd.DataFrame(st.session_state.expense_entries)
    st.table(df_exp)
    total_expenses = df_exp["Amount"].sum()

# 5. Automated Calculations
st.divider()
# Logic: Cash sales minus expenses and tips payout
expected_cash = cash_sales - total_expenses - cc_tips
st.metric("Expected Cash in Hand", f"Rs. {expected_cash:,.2f}")

# 6. Submission & Formatting
if st.button("Confirm Closing & Post to Google Sheets"):
    if not st.session_state.expense_entries and cash_sales == 0:
        st.warning("Please enter sales or expenses before submitting.")
    else:
        # Prepare data for GSheets: [Date, Description, Amount]
        rows = [[date_str, e['Description'], e['Amount']] for e in st.session_state.expense_entries]
        
        # Add a summary row if needed
        # rows.append([date_str, "TOTAL DAILY EXPENSE", total_expenses])

        if post_to_gsheet(branch, rows):
            st.success(f"Data for {date_str} successfully posted to {branch} sheet!")
            
            # --- Print Formatting (Receipt Look) ---
            st.markdown(f"""
            <div style="background-color:white; color:black; padding:25px; font-family:monospace; border:2px solid black; width:350px; margin:auto;">
                <h2 style="text-align:center; margin-bottom:5px;">KLAP</h2>
                <p style="text-align:center; font-size:12px;">{branch}<br>DATE: {date_str}</p>
                <hr style="border-top: 1px dashed black;">
                <p>Total Sale: <span style="float:right;">{total_sale:,.0f}</span></p>
                <p>Cash Sales: <span style="float:right;">{cash_sales:,.0f}</span></p>
                <p>Card Sales: <span style="float:right;">{card_sales:,.0f}</span></p>
                <p>Foodpanda: <span style="float:right;">{fp_sales:,.0f}</span></p>
                <hr style="border-top: 1px dashed black;">
                <p>CC Tips Paid: <span style="float:right;">({cc_tips:,.0f})</span></p>
                <p><b>EXPENSES:</b></p>
                {"".join([f"<p style='font-size:11px; margin-left:10px;'>{e['Description']}<span style='float:right;'>{e['Amount']:,.0f}</span></p>" for e in st.session_state.expense_entries])}
                <hr style="border-top: 1px dashed black;">
                <h3 style="text-align:center;">CASH IN HAND: {expected_cash:,.0f}</h3>
                <p style="text-align:center; font-size:10px; margin-top:15px;">Report Generated Successfully</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Reset expenses for next entry
            st.session_state.expense_entries = []
