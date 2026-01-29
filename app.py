import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
# Assuming you save the first block as printing_logic.py
# from printing_logic import trigger_thermal_print 

# --- RE-INTEGRATED PRINTING MODULE (For single-file convenience) ---
import streamlit.components.v1 as components
def trigger_thermal_print(branch, date, cash, tips, exp_list, total_cash):
    exp_html = "".join([f"<div style='margin-bottom:8px;'>• {e['Category']}: {e['Amount']:,.0f}<br><small>{e['Description']}</small></div>" for e in exp_list])
    receipt = f"<style>@media print {{ body * {{ visibility: hidden; }} #receipt-box, #receipt-box * {{ visibility: visible !important; }} #receipt-box {{ position: absolute; left: 0; top: 0; width: 75mm; }} }}</style><div id='receipt-box' style='padding:20px; font-family:monospace; background:white; color:black;'> <h1 style='text-align:center;'>KLAP</h1> <p style='text-align:center;'><b>{branch.upper()}</b><br>{date}</p><hr><p>Cash Sale: <span style='float:right;'>{cash:,.0f}</span></p><b>EXPENSES:</b>{exp_html} {'<p>CC Tips: <span style=float:right>('+f'{tips:,.0f}'+')</span></p>' if tips > 0 else ''}<hr><div style='text-align:center;'>CASH IN HAND<br><h2>{total_cash:,.0f}</h2></div></div><script>setTimeout(function(){{window.print();}},500);</script>"
    components.html(receipt, height=0)

# --- GOOGLE SHEETS HANDLER ---
def post_to_gsheet(branch_name, data_rows):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
        client.open(sheet_title).sheet1.append_rows(data_rows)
        return True
    except Exception as e:
        st.error(f"Error: {e}"); return False

# --- MAIN INTERFACE ---
st.set_page_config(page_title="KLAP Daily Closing", layout="centered")
st.markdown("<style>div[data-testid='stNumberInput'] button { display: none !important; }</style>", unsafe_allow_html=True)

st.title("🍽️ KLAP Daily Closing")
branch = st.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"])
date_str = st.date_input("Closing Date", datetime.now()).strftime("%d/%m/%Y")

# Sales Section
st.subheader("💰 Revenue Summary")
cash_sales = st.number_input("Cash Sales (PKR)", min_value=0.0, value=None, placeholder="Enter Cash Sales")
tip_status = st.radio("CC Tips?", ["No", "Yes"], horizontal=True)
cc_tips = st.number_input("Tip Amount", min_value=0.0, value=0.0) if tip_status == "Yes" else 0.0

# Expenses Section
st.subheader("💸 Cash Expenses")
if 'expenses' not in st.session_state: st.session_state.expenses = []
cat = st.selectbox("Category", ["Select Category", "Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill"])
desc = st.text_input("Description")
amt = st.number_input("Amount (PKR)", min_value=0.0, value=None, placeholder="Amount")
bill = st.radio("Bill Attached?", ["No", "Yes"], horizontal=True)

if st.button("Add Expense ➕"):
    if cat != "Select Category" and amt:
        st.session_state.expenses.append({"Date": date_str, "Category": cat, "Description": desc, "Amount": amt, "Bill": bill})
        st.rerun()

# Expense Table & Removal
total_exp = 0.0
for i, e in enumerate(st.session_state.expenses):
    c = st.columns([3, 4, 2, 2, 1])
    c[0].write(f"**{e['Category']}**"); c[1].write(e['Description']); c[2].write(f"{e['Amount']:,.0f}"); c[3].write(f"Bill: {e['Bill']}")
    if c[4].button("🗑️", key=f"d_{i}"): st.session_state.expenses.pop(i); st.rerun()
    total_exp += e['Amount']

# Reconciliation
st.divider()
expected_cash = (cash_sales if cash_sales else 0) - total_exp - cc_tips
st.metric("Final Cash in Hand", f"PKR {expected_cash:,.0f}")

# Final Action
if st.button("🖨️ Confirm & Print"):
    rows = [[e['Date'], e['Category'], e['Description'], e['Amount'], e['Bill']] for e in st.session_state.expenses]
    if cc_tips > 0: rows.append([date_str, "CC TIP", "Staff Payout", cc_tips, "No"])
    
    if post_to_gsheet(branch, rows):
        st.success("Successfully posted to Google Sheets!")
        trigger_thermal_print(branch, date_str, (cash_sales if cash_sales else 0), cc_tips, st.session_state.expenses, expected_cash)
        st.session_state.expenses = []
