import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from printing_logic import trigger_thermal_print

# ---------- GOOGLE SHEETS (FIXED CREDENTIAL SYSTEM) ----------
def get_gspread_client():
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # Pulling from Streamlit Secrets instead of a local file
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Credential Error: {e}")
        return None

client = get_gspread_client()

# ---------- HELPERS ----------
def parse_money(val):
    # Removes commas and handles whole numbers only
    if not val: return 0
    clean_val = str(val).replace(",", "").split(".")[0]
    return int(clean_val) if clean_val.isdigit() else 0

def upsert_closing(branch_name, data_rows):
    if client:
        try:
            # Select sheet based on branch
            sheet_title = "KLAP DHA Branch" if "DHA" in branch_name else "KLAP Cantt Branch"
            sheet = client.open(sheet_title).sheet1
            sheet.append_rows(data_rows)
            return True
        except Exception as e:
            st.error(f"Sheet Error: {e}")
    return False

# ---------- UI SETUP ----------
st.set_page_config(page_title="KLAP Daily Closing", layout="centered")

# LIVE CALCULATOR MASK (JavaScript for typing separators)
import streamlit.components.v1 as components
components.html("""
<script>
    const inputs = window.parent.document.querySelectorAll('input[aria-label]');
    inputs.forEach(input => {
        input.addEventListener('input', function(e) {
            let rawValue = e.target.value.replace(/,/g, "");
            if (!isNaN(rawValue) && rawValue !== "") {
                e.target.value = Number(rawValue).toLocaleString('en-US');
            }
        });
    });
</script>
""", height=0)

st.title("🍽️ KLAP Daily Closing")

# ALIGNED: Branch and Date
col_branch, col_date = st.columns(2)
branch = col_branch.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"])
date_selected = col_date.date_input("Closing Date", datetime.today())
date_str = date_selected.strftime("%d/%m/%Y")

st.divider()

# SALES SUMMARY
st.subheader("💰 Revenue Summary")
gross_in = st.text_input("Gross Sale", placeholder="PKR")
c1, c2, c3 = st.columns(3)
cash_in = c1.text_input("Cash Sales", placeholder="PKR")
card_in = c2.text_input("Credit Card Sales", placeholder="PKR")
fp_in = c3.text_input("Foodpanda Sales", placeholder="PKR")

# Math Conversion
gross = parse_money(gross_in)
cash = parse_money(cash_in)
card = parse_money(card_in)
fp = parse_money(fp_in)

if gross and (cash + card + fp) != gross:
    st.warning(f"⚠️ Mismatch! Total of Cash+Card+FP is {cash+card+fp:,}, but Gross is {gross:,}")

st.divider()
tip_status = st.radio("Were there any Credit Card Tips?", ["No", "Yes"], horizontal=True)
cc_tips_in = st.text_input("Tip Amount", "0") if tip_status == "Yes" else "0"
cc_tips = parse_money(cc_tips_raw if 'cc_tips_raw' in locals() else cc_tips_in)

# CASH EXPENSES
st.subheader("💸 Cash Expenses")
if "expenses" not in st.session_state:
    st.session_state.expenses = []

predefined = ["Select Category", "Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill", "Other..."]
cat_choice = st.selectbox("Category", predefined)

if cat_choice != "Select Category":
    desc = st.text_input("Description")
    amt_in = st.text_input("Amount", placeholder="PKR")
    bill_available = st.radio("Bill Available?", ["No", "Yes"], horizontal=True)
    
    if st.button("Add Expense ➕"):
        amt = parse_money(amt_in)
        if amt > 0:
            st.session_state.expenses.append({
                "Date": date_str, "Category": cat_choice, 
                "Description": desc if desc else "-", "Amount": amt, 
                "Bill": bill_available
            })
            st.rerun()

# DISPLAY ADDED ENTRIES
st.markdown("### Added Entries")
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

st.divider()
expected_cash = cash - total_exp - cc_tips
st.metric("Final Cash in Hand", f"PKR {int(expected_cash):,}")

# CONFIRM & PRINT
if st.button("🖨️ Confirm & Print Receipt"):
    if gross and (cash + card + fp) != gross:
        st.error("Cannot confirm: Sales breakdown mismatch.")
    else:
        # Prepare rows for GSheet: Date, Category, Description, Amount, Bill
        rows = [[e['Date'], e['Category'], e['Description'], e['Amount'], e['Bill']] for e in st.session_state.expenses]
        if cc_tips > 0:
            rows.append([date_str, "CC TIP", "Paid to staff", cc_tips, "No"])
            
        if upsert_closing(branch, rows):
            st.success("Successfully posted to Google Sheets!")
            trigger_thermal_print(branch, date_str, gross, cash, card, fp, cc_tips, st.session_state.expenses, expected_cash)
            st.session_state.expenses = []
