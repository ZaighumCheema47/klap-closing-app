import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components

# --- 1. SEPARATED PRINTING MODULE ---
def trigger_thermal_print(branch, date_display, gross_sale, cash_sale, card_sale, fp_sale, cc_tips, expenses, expected_cash):
    # Formatted expenses block with digit separators and no decimals
    expenses_html = "".join([
        f"<div style='margin-bottom:10px; line-height:1.2; font-size:15px;'>"
        f"• <b>{e['Category']}</b>: {int(e['Amount']):,}<br>"
        f"<small style='font-size:13px; color:#555; padding-left:12px;'>{e['Description']}</small></div>" 
        for e in expenses
    ])
    
    receipt_html = f"""
    <style>
        @media print {{
            body * {{ visibility: hidden; }}
            #receipt-box, #receipt-box * {{ visibility: visible !important; }}
            #receipt-box {{
                position: absolute; left: 0; top: 0;
                width: 75mm !important; display: block !important;
            }}
            @page {{ margin: 0; }}
        }}
    </style>
    <div id="receipt-box" style="background-color:white; color:black; padding:20px; font-family:'Courier New', monospace; border:1px solid #000;">
        <h1 style="text-align:center; margin:0; font-size:28px;">KLAP</h1>
        <p style="text-align:center; margin:5px 0; font-size:16px;"><b>{branch.upper()}</b><br>Date: {date_display}</p>
        <hr style="border-top:1px dashed black;">
        <p style="font-size:16px;">Gross Sale: <span style="float:right;">{int(gross_sale):,}</span></p>
        <p style="font-size:16px;">Cash Sale: <span style="float:right;">{int(cash_sale):,}</span></p>
        <p style="font-size:16px;">Card Sale: <span style="float:right;">{int(card_sale):,}</span></p>
        <p style="font-size:16px;">Foodpanda: <span style="float:right;">{int(fp_sale):,}</span></p>
        <hr style="border-top:1px dashed black;">
        <p style="margin:10px 0 5px 0; font-weight:bold; font-size:16px;">EXPENSES:</p>
        {expenses_html}
        {"<p style='margin:10px 0; font-size:16px;'>CC Tips: <span style='float:right;'>(" + f"{int(cc_tips):,}" + ")</span></p>" if cc_tips > 0 else ""}
        <hr style="border-top:1px dashed black;">
        <div style="text-align:center; margin-top:10px;">
            <p style="margin:0; font-size:14px;">CASH IN HAND</p>
            <h2 style="margin:0; font-size:32px;">{int(expected_cash):,}</h2>
        </div>
        <p style="text-align:center; font-size:12px; margin-top:20px;">*** End of Report ***</p>
    </div>
    <script>setTimeout(function() {{ window.print(); }}, 700);</script>
    """
    components.html(receipt_html, height=0)

# --- 2. UI STYLING ---
st.set_page_config(page_title="KLAP Closing", layout="centered")
st.markdown("""
    <style>
        div[data-testid="stNumberInput"] button { display: none !important; }
        input[type=number] { -moz-appearance: textfield; }
    </style>
""", unsafe_allow_html=True)

# --- 3. GOOGLE SHEETS HANDLER ---
def post_to_gsheet(branch_name, data_rows):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
        client.open(sheet_title).sheet1.append_rows(data_rows)
        return True
    except Exception as e:
        st.error(f"Sheet Error: {e}"); return False

# --- 4. MAIN APP LOGIC ---
st.title("🍽️ KLAP Daily Closing")

col_branch, col_date = st.columns(2)
branch = col_branch.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"])
selected_date = col_date.date_input("Closing Date", datetime.now())
date_str = selected_date.strftime("%d/%m/%Y")

st.divider()

st.subheader("💰 Revenue Summary")
gross_sale = st.number_input("Gross Sale", min_value=0.0, step=1.0, value=None, placeholder="PKR")

c1, c2, c3 = st.columns(3)
cash_sales = c1.number_input("Cash Sales", min_value=0.0, step=1.0, value=None, placeholder="PKR")
card_sales = c2.number_input("Credit Card Sales", min_value=0.0, step=1.0, value=None, placeholder="PKR")
fp_sales = c3.number_input("Foodpanda Sales", min_value=0.0, step=1.0, value=None, placeholder="PKR")

# SALES VALIDATION CHECK
if gross_sale and cash_sales is not None and card_sales is not None and fp_sales is not None:
    current_total = cash_sales + card_sales + fp_sales
    if current_total != gross_sale:
        st.warning(f"⚠️ Sales Mismatch! Total of Cash+Card+FP is {current_total:,.0f}, but Gross Sale is {gross_sale:,.0f}")
    else:
        st.success("✅ Sales breakdown matches Gross Sale.")

st.divider()
tip_status = st.radio("Credit Card Tips?", ["No", "Yes"], horizontal=True)
cc_tips = st.number_input("Tip Amount", min_value=0.0, step=1.0, value=0.0) if tip_status == "Yes" else 0.0

st.subheader("💸 Cash Expenses")
if 'expenses' not in st.session_state: st.session_state.expenses = []

predefined = ["Select Category", "Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill", "Other..."]
cat_choice = st.selectbox("Category", predefined)

if cat_choice != "Select Category":
    desc = st.text_input("Description")
    amt = st.number_input("Amount", min_value=0.0, step=1.0, value=None, placeholder="PKR")
    bill = st.radio("Bill Available?", ["No", "Yes"], horizontal=True)
    
    if st.button("Add Expense ➕"):
        if amt:
            st.session_state.expenses.append({"Date": date_str, "Category": cat_choice, "Description": desc if desc else "-", "Amount": amt, "Bill": bill})
            st.rerun()

st.markdown("### Added Entries")
total_exp = 0.0
for i, e in enumerate(st.session_state.expenses):
    c = st.columns([3, 4, 2, 2, 1])
    c[0].write(f"**{e['Category']}**"); c[1].write(e['Description']); c[2].write(f"PKR {int(e['Amount']):,}"); c[3].write(f"Bill: {e['Bill']}")
    if c[4].button("🗑️", key=f"del_{i}"): st.session_state.expenses.pop(i); st.rerun()
    total_exp += e['Amount']

st.divider()
final_cash_sales = cash_sales if cash_sales else 0.0
expected_cash = final_cash_sales - total_exp - cc_tips
st.metric("Final Cash in Hand", f"PKR {int(expected_cash):,}")

if st.button("🖨️ Confirm & Print"):
    # VALIDATION BEFORE SUBMIT
    total_sales_check = (cash_sales if cash_sales else 0) + (card_sales if card_sales else 0) + (fp_sales if fp_sales else 0)
    if gross_sale and total_sales_check != gross_sale:
        st.error("Cannot confirm: Sales breakdown does not match Gross Sale.")
    else:
        rows = [[e['Date'], e['Category'], e['Description'], e['Amount'], e['Bill']] for e in st.session_state.expenses]
        if cc_tips > 0: rows.append([date_str, "CC TIP", "Paid to staff", cc_tips, "No"])
        
        if post_to_gsheet(branch, rows):
            st.success("Successfully posted to Google Sheets!")
            trigger_thermal_print(branch, date_str, (gross_sale if gross_sale else 0), (cash_sales if cash_sales else 0), (card_sales if card_sales else 0), (fp_sales if fp_sales else 0), cc_tips, st.session_state.expenses, expected_cash)
            st.session_state.expenses = []
