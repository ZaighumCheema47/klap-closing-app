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
    """Fix: Properly handles numbers with commas and decimals (e.g., 1,500.00)"""
    if not val: return 0
    # Remove everything except digits
    clean_val = re.sub(r'[^\d]', '', str(val).split(".")[0])
    return int(clean_val) if clean_val else 0

def upsert_closing(branch_name, date_str, data_rows):
    """Objective 4: Deletes existing entries for this date/branch before adding new ones"""
    if client:
        try:
            sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
            sheet = client.open(sheet_title).sheet1
            
            # Create a unique Daily ID: e.g., "2026-01-29_DHA"
            daily_id = f"{date_str}_{branch_name}"
            
            # Fetch all records to check for duplicates
            all_records = sheet.get_all_values()
            
            # If sheet isn't empty, find rows with the same Daily ID and remove them
            if len(all_records) > 1:
                # Find indices of rows where the first column matches daily_id
                # (Reversed to avoid index shifting while deleting)
                rows_to_delete = [i + 1 for i, row in enumerate(all_records) if row[0] == daily_id]
                for row_idx in reversed(rows_to_delete):
                    sheet.delete_rows(row_idx)

            # Prepend the Daily ID to every row for tracking
            final_rows = [[daily_id] + row for row in data_rows]
            sheet.append_rows(final_rows)
            return True
        except Exception as e:
            st.error(f"Sheet Error: {e}")
    return False

# ---------- UI SETUP ----------
st.set_page_config(page_title="KLAP Daily Closing", layout="centered")

st.title("🍽️ KLAP Daily Closing")

# Branch and Date Selection
col_branch, col_date = st.columns(2)
branch = col_branch.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"])
date_selected = col_date.date_input("Closing Date", datetime.today())
date_str = date_selected.strftime("%Y-%m-%d") # Standardized format for IDs

st.divider()

# REVENUE SUMMARY
st.subheader("💰 Revenue Summary")
gross_in = st.text_input("Gross Sale", placeholder="PKR", key="gross")

c1, c2, c3 = st.columns(3)
cash_in = c1.text_input("Cash Sales", placeholder="PKR")
card_in = c2.text_input("Credit Card Sales", placeholder="PKR")
fp_in = c3.text_input("Foodpanda Sales", placeholder="PKR")

gross = parse_money(gross_in)
cash = parse_money(cash_in)
card = parse_money(card_in)
fp = parse_money(fp_in)

# Objective 3: Validation Logic
mismatch = (cash + card + fp) != gross
if gross > 0 and mismatch:
    st.error(f"⚠️ Mismatch! Total (Cash+Card+FP): {cash+card+fp:,} | Gross: {gross:,}")
elif gross > 0 and not mismatch:
    st.success("✅ Revenue totals match.")

st.divider()

# CASH EXPENSES
st.subheader("💸 Cash Expenses")
if "expenses" not in st.session_state:
    st.session_state.expenses = []

predefined = ["Select Category", "Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill", "Other..."]
cat_choice = st.selectbox("1. Category", predefined)

# Objective 2: Sequential Validation
if cat_choice != "Select Category":
    desc = st.text_input("2. Description (Required)")
    if desc:
        amt_in = st.text_input("3. Amount", placeholder="PKR")
        bill_available = st.radio("Bill Available?", ["No", "Yes"], horizontal=True)
        
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
if st.button("🖨️ Confirm & Update G-Sheet"):
    if mismatch:
        st.error("Error: You cannot submit while there is a Gross Sale mismatch.")
    elif gross == 0:
        st.error("Error: Gross Sale cannot be zero.")
    else:
        # Prepare Rows (Columns: Date, Category, Desc, Amount, Bill)
        rows = [[e['Date'], e['Category'], e['Description'], e['Amount'], e['Bill']] for e in st.session_state.expenses]
        
        # Add a summary row for Sales
        rows.append([date_str, "SALES_SUMMARY", f"Gross:{gross}|Cash:{cash}|Card:{card}|FP:{fp}", gross, "N/A"])
        
        if cc_tips > 0:
            rows.append([date_str, "CC TIP", "Paid to staff", cc_tips, "No"])
            
        if upsert_closing(branch, date_str, rows):
            st.success(f"Data for {date_str} updated successfully! Previous entries for this date were overwritten.")
            trigger_thermal_print(branch, date_str, gross, cash, card, fp, cc_tips, st.session_state.expenses, expected_cash)
            st.session_state.expenses = []
