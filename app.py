import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from printing_logic import trigger_thermal_print
import re

# ---------- GOOGLE SHEETS CORE ----------
def get_gspread_client():
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Credential Error: {e}")
        return None

client = get_gspread_client()

def parse_money(val):
    if not val: return 0
    clean_val = re.sub(r'[^\d]', '', str(val).split(".")[0])
    return int(clean_val) if clean_val else 0

def upsert_closing(branch_name, date_str, data_rows):
    if client:
        try:
            sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
            sheet = client.open(sheet_title).sheet1
            daily_id = f"{date_str}_{branch_name.replace(' ', '')}"
            all_records = sheet.get_all_values()
            
            if len(all_records) > 1:
                rows_to_delete = [i + 1 for i, row in enumerate(all_records) if row[0] == daily_id]
                for row_idx in reversed(rows_to_delete):
                    sheet.delete_rows(row_idx)

            final_rows = [[daily_id] + row for row in data_rows]
            sheet.append_rows(final_rows)
            return True
        except Exception as e:
            st.error(f"Sheet Error: {e}")
    return False

# ---------- UI SETUP ----------
st.set_page_config(page_title="KLAP Daily Closing", layout="centered")

if "expenses" not in st.session_state:
    st.session_state.expenses = []
if "exp_form_key" not in st.session_state:
    st.session_state.exp_form_key = 0

st.title("🍽️ KLAP Daily Closing")

# Branch and Date Selection
col_branch, col_date = st.columns(2)
branch = col_branch.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"])
date_selected = col_date.date_input("Closing Date", datetime.today())
date_str = date_selected.strftime("%d-%m-%y")

st.divider()

# REVENUE SUMMARY
st.subheader("💰 Revenue Summary")
gross_in = st.text_input("Gross Sale", placeholder="PKR")

c1, c2, c3 = st.columns(3)
cash_in = c1.text_input("Cash Sales", placeholder="PKR")
card_in = c2.text_input("Credit Card Sales", placeholder="PKR")
fp_in = c3.text_input("Foodpanda Sales", placeholder="PKR")

gross = parse_money(gross_in)
cash = parse_money(cash_in)
card = parse_money(card_in)
fp = parse_money(fp_in)

mismatch = (cash + card + fp) != gross
if gross > 0 and mismatch:
    st.error(f"⚠️ Mismatch! Total: {cash+card+fp:,} | Gross: {gross:,}")
elif gross > 0 and not mismatch:
    st.success("✅ Revenue totals match.")

st.divider()

# CASH EXPENSES - ENTRY SECTION
st.subheader("💸 Add New Expense")
predefined = ["Select Category", "Staff", "Rides", "Inventory", "Generator", "Bevrages", "Maintenance", "Utilities", "Cleaning", "Other..."]

cat_choice = st.selectbox("1. Category", predefined, key=f"cat_{st.session_state.exp_form_key}")

if cat_choice != "Select Category":
    desc = st.text_input("2. Description (Required)", key=f"desc_{st.session_state.exp_form_key}")
    if desc:
        amt_in = st.text_input("3. Amount", placeholder="PKR", key=f"amt_{st.session_state.exp_form_key}")
        bill_available = st.radio("Bill Available?", ["No", "Yes"], horizontal=True, key=f"bill_{st.session_state.exp_form_key}")
        
        if st.button("Add Expense ➕"):
            amt = parse_money(amt_in)
            if amt > 0:
                st.session_state.expenses.append({
                    "Date": date_str, 
                    "Category": cat_choice, 
                    "Description": desc, 
                    "Amount": amt, 
                    "Bill": bill_available
                })
                st.session_state.exp_form_key += 1
                st.rerun()
            else:
                st.warning("Please enter a valid amount.")

st.divider()

# Tipping and Cash Metric
tip_status = st.radio("Were there any Credit Card Tips?", ["No", "Yes"], horizontal=True)
cc_tips = 0
if tip_status == "Yes":
    cc_tips_in = st.text_input("Tip Amount")
    cc_tips = parse_money(cc_tips_in)

total_exp = sum(e['Amount'] for e in st.session_state.expenses)
expected_cash = cash - total_exp - cc_tips

st.metric("Final Cash in Hand", f"PKR {int(expected_cash):,}")

# --- SUBMIT BUTTON ---
if st.button("🖨️ Confirm & Print Closing", type="primary", use_container_width=True):
    if mismatch or gross == 0:
        st.error("Check Revenue Totals before confirming.")
    else:
        rows = [[e['Date'], e['Category'], e['Description'], e['Amount'], e['Bill']] for e in st.session_state.expenses]
        rows.append([date_str, "SALES_SUMMARY", f"Gross:{gross}", gross, "N/A"])
        if cc_tips > 0:
            rows.append([date_str, "CC TIP", "Paid to staff", cc_tips, "No"])
            
        daily_id = f"{date_str}_{branch.replace(' ', '')}"
        if upsert_closing(branch, date_str, rows):
            st.success(f"Data for {date_str} updated!")
            trigger_thermal_print(branch, date_str, cash, card, fp, cc_tips, st.session_state.expenses, expected_cash, daily_id)
            st.session_state.expenses = []
            st.rerun()

st.divider()

# --- ADDED ENTRIES LIST (CLEAN VERSION AT BOTTOM) ---
if st.session_state.expenses:
    st.subheader("📑 Current Expenses List")
    for i, e in enumerate(st.session_state.expenses):
        cols = st.columns([3, 4, 2, 2, 1])
        cols[0].write(f"**{e['Category']}**")
        cols[1].write(e['Description'])
        cols[2].write(f"PKR {e['Amount']:,}")
        cols[3].write(f"Bill: {e['Bill']}")
        if cols[4].button("🗑️", key=f"del_{i}"):
            st.session_state.expenses.pop(i)
            st.rerun()
