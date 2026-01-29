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
        # Pulling from Streamlit Secrets
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Credential Error: {e}")
        return None

client = get_gspread_client()

def parse_money(val):
    """
    Handles numbers with commas and decimals. 
    Uses regex to ensure numbers > 999 are processed correctly.
    """
    if not val: return 0
    clean_val = re.sub(r'[^\d]', '', str(val).split(".")[0])
    return int(clean_val) if clean_val else 0

def upsert_closing(branch_name, date_str, data_rows):
    """
    Assigns a unique ID to every day and branch. 
    If data already exists for that ID, it is removed before appending the new data.
    """
    if client:
        try:
            sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
            sheet = client.open(sheet_title).sheet1
            
            # Unique ID for the day/branch
            daily_id = f"{date_str}_{branch_name.replace(' ', '')}"
            
            all_records = sheet.get_all_values()
            
            # Remove existing entries with this ID to prevent duplicates
            if len(all_records) > 1:
                rows_to_delete = [i + 1 for i, row in enumerate(all_records) if row[0] == daily_id]
                for row_idx in reversed(rows_to_delete):
                    sheet.delete_rows(row_idx)

            # Prepend Daily ID to data
            final_rows = [[daily_id] + row for row in data_rows]
            sheet.append_rows(final_rows)
            return True
        except Exception as e:
            st.error(f"Sheet Error: {e}")
    return False

# ---------- UI SETUP ----------
st.set_page_config(page_title="KLAP Daily Closing", layout="centered")

# Session State Initialization
if "expenses" not in st.session_state:
    st.session_state.expenses = []
if "exp_form_key" not in st.session_state:
    st.session_state.exp_form_key = 0

st.title("🍽️ KLAP Daily Closing")

# Branch and Date Selection
col_branch, col_date = st.columns(2)
branch = col_branch.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"])
date_selected = col_date.date_input("Closing Date", datetime.today())
date_str = date_selected.strftime("%Y-%m-%d")

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

# Validation for Gross vs Sub-components
mismatch = (cash + card + fp) != gross
if gross > 0 and mismatch:
    st.error(f"⚠️ Mismatch! Total (Cash+Card+FP): {cash+card+fp:,} | Gross: {gross:,}")
elif gross > 0 and not mismatch:
    st.success("✅ Revenue totals match.")

st.divider()

# CASH EXPENSES
st.subheader("💸 Cash Expenses")

predefined = ["Select Category", "Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill", "Other..."]

# Sequential Validation Flow
cat_choice = st.selectbox(
    "1. Category", 
    predefined, 
    key=f"cat_{st.session_state.exp_form_key}"
)

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
                # Reset the form key to clear all sub-inputs
                st.session_state.exp_form_key += 1
                st.rerun()
            else:
                st.warning("Please enter a valid amount.")

# Display entries
total_exp = 0
for i, e in enumerate(st.session_state.expenses):
    cols = st.columns([3, 4, 2, 2, 1])
    cols[0].write(f"**{e['Category']}**")
    cols[1].write(e['Description'])
    cols[2].write(f"PKR {e['Amount']:,}")
    cols[3].write(f"Bill: {e['Bill']}")
    if cols[4].button("🗑️", key=f"del_{i}"):
        st.session_state.expenses.pop(i)
        st.rerun()
    total_exp += e['Amount']

# Tipping logic
st.divider()
tip_status = st.radio("Were there any Credit Card Tips?", ["No", "Yes"], horizontal=True)
cc_tips = 0
if tip_status == "Yes":
    cc_tips_in = st.text_input("Tip Amount")
    cc_tips = parse_money(cc_tips_in)

expected_cash = cash - total_exp - cc_tips
st.metric("Final Cash in Hand", f"PKR {int(expected_cash):,}")

# SUBMIT
if st.button("🖨️ Confirm & Print"):
    if mismatch:
        st.error("Error: Total of Cash/Card/FP must equal Gross Sale.")
    elif gross == 0:
        st.error("Error: Gross Sale cannot be zero.")
    else:
        # Prepare Rows for Google Sheets
        rows = [[e['Date'], e['Category'], e['Description'], e['Amount'], e['Bill']] for e in st.session_state.expenses]
        
        # Add a summary row for Sales record keeping
        rows.append([date_str, "SALES_SUMMARY", f"Gross:{gross}|Cash:{cash}|Card:{card}|FP:{fp}", gross, "N/A"])
        
        if cc_tips > 0:
            rows.append([date_str, "CC TIP", "Paid to staff", cc_tips, "No"])
            
        daily_id = f"{date_str}_{branch.replace(' ', '')}"
            
        if upsert_closing(branch, date_str, rows):
            st.success(f"Data for {date_str} successfully updated in Google Sheets!")
            
            # Resolved TypeError: Passing correct arguments to printing logic
            trigger_thermal_print(
                branch=branch,
                date_display=date_str,
                cash_sales=cash,
                card_sales=card,
                fp_sales=fp,
                cc_tips=cc_tips,
                expenses=st.session_state.expenses,
                expected_cash=expected_cash,
                closing_code=daily_id
            )
            # Clear current session after successful post
            st.session_state.expenses = []
