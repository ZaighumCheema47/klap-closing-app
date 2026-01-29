import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components

# --- 1. ENHANCED PRINT & UI STYLING ---
st.set_page_config(page_title="KLAP Daily Closing", layout="centered")

st.markdown("""
<style>
    /* HIDE PLUS/MINUS BUTTONS ON NUMBER INPUTS */
    div[data-testid="stNumberInput"] button { display: none !important; }
    input[type=number] { -moz-appearance: textfield; }
    
    /* PRINTING LOGIC */
    @media print {
        /* Hide everything by default */
        body * { visibility: hidden; }
        /* Only show the element with id 'printable-receipt' */
        #printable-receipt, #printable-receipt * {
            visibility: visible !important;
        }
        #printable-receipt {
            position: absolute;
            left: 0;
            top: 0;
            width: 80mm !important;
            display: block !important;
        }
        /* Remove browser headers/footers */
        @page { margin: 0; }
    }
    .expense-row { border-bottom: 1px solid #eee; padding: 10px 0; }
</style>
""", unsafe_allow_html=True)

# --- 2. GOOGLE SHEETS CONNECTION ---
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

# --- 3. APP LOGIC ---
st.title("🍽️ KLAP Daily Closing")

col_b, col_d = st.columns(2)
with col_b:
    branch = st.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"])
with col_d:
    selected_date = st.date_input("Select Closing Date", datetime.now())
    date_display = selected_date.strftime("%d/%m/%Y")

st.divider()

st.subheader("💰 Revenue Summary")
total_sale = st.number_input("Total Sale (PKR)", min_value=0.0, step=1.0, value=None, placeholder="Enter Gross Amount")

c1, c2, c3 = st.columns(3)
cash_sales = c1.number_input("Cash Sales", min_value=0.0, value=None, placeholder="PKR")
card_sales = c2.number_input("Card Sales", min_value=0.0, value=None, placeholder="PKR")
fp_sales = c3.number_input("Foodpanda", min_value=0.0, value=None, placeholder="PKR")

st.divider()
tip_status = st.radio("Were there any Credit Card Tips?", ["No", "Yes"], horizontal=True)
cc_tips = 0.0
if tip_status == "Yes":
    cc_tips = st.number_input("Enter Tip Amount (PKR)", min_value=0.0, value=None, placeholder="Tip Amount")

st.subheader("💸 Cash Expenses")
if 'expenses' not in st.session_state:
    st.session_state.expenses = []

predefined = ["Select Category", "Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill"]
cat_choice = st.selectbox("Category", predefined)

# Form for adding expenses to ensure validation
with st.container():
    final_cat = st.text_input("New Category Name") if cat_choice == "Other..." else cat_choice
    exp_desc = st.text_input("Description", placeholder="e.g. Repairing AC")
    
    col_amt, col_bill = st.columns([2, 1])
    exp_amt = col_amt.number_input("Amount (PKR)", min_value=0.0, value=None, placeholder="PKR")
    has_bill = col_bill.radio("Bill Attached?", ["No", "Yes"], horizontal=True)

    if st.button("Add Expense ➕"):
        if cat_choice == "Select Category":
            st.error("Please select a valid Category first.")
        elif not exp_amt:
            st.error("Please enter an Amount.")
        else:
            st.session_state.expenses.append({
                "Date": date_display,
                "Category": final_cat,
                "Description": exp_desc if exp_desc else "-",
                "Amount": exp_amt,
                "Bill": has_bill
            })
            st.rerun()

# 4. DATA PRESENTATION
st.markdown("### Added Entries")
total_expenses = 0.0
if st.session_state.expenses:
    # Display headers
    h1, h2, h3, h4, h5, h6 = st.columns([2, 2, 3, 2, 1, 1])
    h1.write("**Date**")
    h2.write("**Cat**")
    h3.write("**Desc**")
    h4.write("**PKR**")
    h5.write("**Bill**")
    
    for i, exp in enumerate(st.session_state.expenses):
        r1, r2, r3, r4, r5, r6 = st.columns([2, 2, 3, 2, 1, 1])
        r1.write(exp['Date'])
        r2.write(exp['Category'])
        r3.write(exp['Description'])
        r4.write(f"{exp['Amount']:,.0f}")
        r5.write(exp['Bill'])
        if r6.button("🗑️", key=f"del_{i}"):
            st.session_state.expenses.pop(i)
            st.rerun()
        total_expenses += exp['Amount']
else:
    st.info("No entries added.")

st.divider()
final_cash_sales = cash_sales if cash_sales else 0.0
expected_cash = final_cash_sales - total_expenses - (cc_tips if cc_tips else 0)
st.metric("Final Cash in Hand", f"PKR {expected_cash:,.0f}")

# 5. SUBMIT & PRINT
if st.button("🖨️ Confirm Closing & Print Receipt"):
    # Date, Category, Description, Amount, Bill
    rows = [[e['Date'], e['Category'], e['Description'], e['Amount'], e['Bill']] for e in st.session_state.expenses]
    
    if cc_tips and cc_tips > 0:
        rows.append([date_display, "CC TIP", "Paid to staff", cc_tips, "N/A"])
    
    if post_to_gsheet(branch, rows):
        st.success("Successfully posted to Google Sheets!")
        
        # REFINED RECEIPT HTML
        receipt_html = f"""
        <div id="printable-receipt" style="background-color:white; color:black; padding:20px; font-family:'Courier New', monospace; width:75mm; border:1px solid #ccc;">
            <h1 style="text-align:center; margin:0; font-size:28px;">KLAP</h1>
            <p style="text-align:center; margin:5px 0; font-size:16px;"><b>{branch.upper()}</b><br>Date: {date_display}</p>
            <hr style="border-top:1px dashed black;">
            <p style="font-size:16px;">Cash Sale: <span style="float:right;">{final_cash_sales:,.0f}</span></p>
            
            <p style="margin:10px 0 5px 0; font-weight:bold; font-size:16px;">EXPENSES:</p>
            {"".join([f"<div style='margin-bottom:8px; line-height:1.2; font-size:15px;'>• {e['Category']}: {e['Amount']:,.0f}<br><small style='font-size:13px; color:#555;'>&nbsp;&nbsp;{e['Description']}</small></div>" for e in st.session_state.expenses])}
            
            {"<p style='margin:10px 0; font-size:16px;'>CC Tips: <span style='float:right;'>(" + f"{cc_tips:,.0f}" + ")</span></p>" if cc_tips > 0 else ""}
            
            <hr style="border-top:1px dashed black;">
            <div style="text-align:center; margin-top:10px;">
                <p style="margin:0; font-size:14px;">CASH IN HAND</p>
                <h2 style="margin:0; font-size:32px;">{expected_cash:,.0f}</h2>
            </div>
            <p style="text-align:center; font-size:12px; margin-top:20px;">*** End of Report ***</p>
        </div>
        """
        st.markdown(receipt_html, unsafe_allow_html=True)
        
        # Precisely trigger print for the specific ID
        components.html("""
            <script>
                setTimeout(function() {
                    window.print();
                }, 500);
            </script>
        """, height=0)
        
        st.session_state.expenses = []
