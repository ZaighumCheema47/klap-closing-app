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

def upsert_closing(branch_name, custom_id, data_rows):
    if client:
        try:
            sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
            sheet = client.open(sheet_title).sheet1
            all_records = sheet.get_all_values()
            
            if len(all_records) > 1:
                rows_to_delete = [i + 1 for i, row in enumerate(all_records) if row[0] == custom_id]
                for row_idx in reversed(rows_to_delete):
                    sheet.delete_rows(row_idx)

            final_rows = [[custom_id] + row for row in data_rows]
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

# --- SIDEBAR FOR RETRIEVAL ---
with st.sidebar:
    st.header("🔍 Retrieve Past Closing")
    search_id = st.text_input("Enter Closing ID (e.g., DHA290126CR)").upper().strip()
    if st.button("Load Data"):
        if client and search_id:
            try:
                target_sheet = "KLAP DHA Branch" if "DHA" in search_id else "KLAP Cantt Branch"
                sheet = client.open(target_sheet).sheet1
                records = sheet.get_all_values()
                matched_rows = [r for r in records if r[0] == search_id]
                
                if matched_rows:
                    temp_expenses = []
                    for row in matched_rows:
                        if row[2] not in ["SALES_SUMMARY", "CC TIP"]:
                            temp_expenses.append({
                                "Date": row[1],
                                "Category": row[2],
                                "Description": row[3],
                                "Amount": int(row[4]),
                                "Bill": row[5]
                            })
                    st.session_state.expenses = temp_expenses
                    st.success(f"Loaded data for {search_id}")
                    st.rerun()
                else:
                    st.error("ID not found.")
            except Exception as e:
                st.error(f"Search Error: {e}")

col_branch, col_date = st.columns(2)
branch = col_branch.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"])
date_selected = col_date.date_input("Closing Date", datetime.today())

# NEW ID FORMAT: BRANCH + DDMMYY + CR
branch_prefix = "DHA" if "DHA" in branch else "CANTT"
date_compact = date_selected.strftime("%d%m%y")
daily_id = f"{branch_prefix}{date_compact}CR"

st.caption(f"Current Closing ID: **{daily_id}**")
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

# CASH EXPENSES
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
                    "Date": date_selected.strftime("%d-%m-%y"), 
                    "Category": cat_choice, 
                    "Description": desc, 
                    "Amount": amt, 
                    "Bill": bill_available
                })
                st.session_state.exp_form_key += 1
                st.rerun()

st.divider()

tip_status = st.radio("Were there any Credit Card Tips?", ["No", "Yes"], horizontal=True)
cc_tips = parse_money(st.text_input("Tip Amount")) if tip_status == "Yes" else 0

total_exp = sum(e['Amount'] for e in st.session_state.expenses)
expected_cash = cash - total_exp - cc_tips
st.metric("Final Cash in Hand", f"PKR {int(expected_cash):,}")

# --- FIXED SUBMIT & PRINT TRIGGER ---
if st.button("🖨️ Confirm & Print Closing", type="primary", use_container_width=True):
    if mismatch or gross == 0:
        st.error("Check Revenue Totals before confirming.")
    else:
        rows = [[e['Date'], e['Category'], e['Description'], e['Amount'], e['Bill']] for e in st.session_state.expenses]
        rows.append([date_selected.strftime("%d-%m-%y"), "SALES_SUMMARY", f"Gross:{gross}", gross, "N/A"])
        if cc_tips > 0:
            rows.append([date_selected.strftime("%d-%m-%y"), "CC TIP", "Paid to staff", cc_tips, "No"])
            
        if upsert_closing(branch, daily_id, rows):
            st.success(f"G-Sheet Updated for ID: {daily_id}")
            
            # FIXED: Correct variable names sent to printing function
            trigger_thermal_print(
                branch=branch,
                date_display=date_selected.strftime("%d-%m-%y"),
                cash_sales=cash,
                card_sales=card,
                fp_sales=fp,
                cc_tips=cc_tips,
                expenses=st.session_state.expenses,
                expected_cash=expected_cash,
                closing_code=daily_id
            )
            st.session_state.expenses = []

st.divider()

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
