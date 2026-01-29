import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from printing_logic import trigger_thermal_print
import re
from pathlib import Path

# ---------- BRANDING & AESTHETICS ----------
st.set_page_config(page_title="KLAP | Daily Closing", page_icon="🍕", layout="centered")

# Custom KLAP CSS
st.markdown("""
    <style>
    /* Main Branding Colors */
    :root {
        --klap-orange: #FF5722;
        --klap-dark: #0E1117;
    }
    
    /* Center and Style Title */
    h1 {
        color: var(--klap-orange) !important;
        text-transform: uppercase;
        letter-spacing: 3px;
        font-weight: 900;
        text-align: center;
        margin-bottom: 0px !important;
    }
    
    /* Branded Buttons */
    div.stButton > button {
        background-color: var(--klap-orange) !important;
        color: white !important;
        font-weight: 800 !important;
        border-radius: 12px !important;
        border: none !important;
        text-transform: uppercase;
        transition: 0.3s;
    }
    
    div.stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0px 4px 15px rgba(255, 87, 34, 0.4);
    }

    /* Professional Metric Styling */
    [data-testid="stMetricValue"] {
        color: var(--klap-orange);
        font-weight: 900;
    }
    
    /* Clean up borders */
    .stTextInput>div>div>input {
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

# Logo Support (Assumes you upload klap_logo.png to your branch)
if Path("klap_logo.png").exists():
    st.logo("klap_logo.png", size="large")

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

def upsert_sales_data(branch_name, daily_id, date_str, cash, card, fp, gross):
    if client:
        try:
            sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
            spreadsheet = client.open(sheet_title)
            try:
                sales_sheet = spreadsheet.worksheet("Sales")
            except:
                sales_sheet = spreadsheet.add_worksheet(title="Sales", rows="100", cols="10")
                sales_sheet.append_row(["ID", "Date", "Cash", "Card", "Foodpanda", "Gross"])

            records = sales_sheet.get_all_values()
            if len(records) > 1:
                rows_to_delete = [i + 1 for i, row in enumerate(records) if row[0] == daily_id]
                for idx in reversed(rows_to_delete):
                    sales_sheet.delete_rows(idx)
            
            sales_sheet.append_row([daily_id, date_str, cash, card, fp, gross])
            return True
        except Exception as e:
            st.error(f"Sales Sheet Error: {e}")
    return False

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
            st.error(f"Expense Sheet Error: {e}")
    return False

# ---------- MAIN UI ----------
if "expenses" not in st.session_state:
    st.session_state.expenses = []
if "exp_form_key" not in st.session_state:
    st.session_state.exp_form_key = 0

# Top Bar with Title and Hidden Search
col_t, col_s = st.columns([4, 1])
with col_t:
    st.title("KLAP CLOSING")
with col_s:
    with st.popover("🔍"):
        search_id = st.text_input("Enter ID").upper().strip()
        if st.button("Load"):
            if client and search_id:
                try:
                    target = "KLAP DHA Branch" if "DHA" in search_id else "KLAP Cantt Branch"
                    sheet = client.open(target).sheet1
                    records = sheet.get_all_values()
                    matched = [r for r in records if r[0] == search_id]
                    if matched:
                        st.session_state.expenses = [
                            {"Date": r[1], "Category": r[2], "Description": r[3], "Amount": int(r[4]), "Bill": r[5]}
                            for r in matched if r[2] != "SALES_SUMMARY"
                        ]
                        st.success("Loaded!")
                        st.rerun()
                    else: st.error("Not found")
                except Exception as e: st.error(f"Error: {e}")

# Selection Area
col_b, col_d = st.columns(2)
branch = col_b.selectbox("Branch", ["Cantt Branch", "DHA Branch"])
date_selected = col_d.date_input("Date", datetime.today())
date_str_display = date_selected.strftime("%d-%m-%y")

# ID Logic
branch_prefix = "DHA" if "DHA" in branch else "CANTT"
daily_id = f"{branch_prefix}{date_selected.strftime('%d%m%y')}CR"

st.divider()

# Revenue Summary
with st.container(border=True):
    st.subheader("💰 Revenue Summary")
    gross_in = st.text_input("Gross Sale", placeholder="PKR")
    c1, c2, c3 = st.columns(3)
    cash_in = c1.text_input("Cash", placeholder="PKR")
    card_in = c2.text_input("Card", placeholder="PKR")
    fp_in = c3.text_input("Panda", placeholder="PKR")

    gross = parse_money(gross_in)
    cash = parse_money(cash_in)
    card = parse_money(card_in)
    fp = parse_money(fp_in)

    if gross > 0 and (cash + card + fp) != gross:
        st.error(f"Mismatch! Difference: {(cash+card+fp)-gross:,}")

# Expenses Area
st.subheader("💸 Add Expense")
predefined = ["Select Category", "Staff", "Rides", "Inventory", "Generator", "Bevrages", "Maintenance", "Utilities", "Cleaning", "Other..."]
cat = st.selectbox("Category", predefined, key=f"cat_{st.session_state.exp_form_key}")

if cat != "Select Category":
    desc = st.text_input("Description", key=f"desc_{st.session_state.exp_form_key}")
    if desc:
        amt_in = st.text_input("Amount", key=f"amt_{st.session_state.exp_form_key}")
        bill = st.radio("Bill?", ["No", "Yes"], horizontal=True, key=f"bill_{st.session_state.exp_form_key}")
        if st.button("Add ➕"):
            amt = parse_money(amt_in)
            if amt > 0:
                st.session_state.expenses.append({
                    "Date": date_str_display, "Category": cat, "Description": desc, "Amount": amt, "Bill": bill
                })
                st.session_state.exp_form_key += 1
                st.rerun()

st.divider()

# Finalization
tip_status = st.radio("CC Tips?", ["No", "Yes"], horizontal=True)
cc_tips = parse_money(st.text_input("Tip Amount")) if tip_status == "Yes" else 0
total_exp = sum(e['Amount'] for e in st.session_state.expenses)
expected_cash = cash - total_exp - cc_tips

st.metric("Cash in Hand", f"Rs. {int(expected_cash):,}")

if st.button("CONFIRM & PRINT", type="primary", use_container_width=True):
    if (cash + card + fp) == gross and gross > 0:
        rows = [[e['Date'], e['Category'], e['Description'], e['Amount'], e['Bill']] for e in st.session_state.expenses]
        if cc_tips > 0: rows.append([date_str_display, "CC TIP", "Staff Tip", cc_tips, "No"])
        
        if upsert_closing(branch, daily_id, rows) and upsert_sales_data(branch, daily_id, date_str_display, cash, card, fp, gross):
            st.success("Closing Recorded!")
            trigger_thermal_print(branch, date_str_display, cash, card, fp, cc_tips, st.session_state.expenses, expected_cash, daily_id)
            st.session_state.expenses = []
    else: st.error("Revenue totals must match gross.")

st.divider()
if st.session_state.expenses:
    for i, e in enumerate(st.session_state.expenses):
        cols = st.columns([3, 4, 2, 1])
        cols[0].write(f"**{e['Category']}**")
        cols[1].write(e['Description'])
        cols[2].write(f"{e['Amount']:,}")
        if cols[3].button("🗑️", key=f"del_{i}"):
            st.session_state.expenses.pop(i)
            st.rerun()
