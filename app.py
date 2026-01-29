import streamlit as st
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from printing_logic import trigger_thermal_print

# ---------- HELPERS ----------
def parse_money(val: str) -> int:
    val = val.replace(",", "").strip()
    return int(val) if val.isdigit() else 0

def money_input(label: str, key: str):
    raw = st.text_input(label, value="", key=key, placeholder="e.g. 15,000")
    value = parse_money(raw)
    if value > 0:
        st.caption(f"PKR {value:,}")
    return value

# ---------- PAGE ----------
st.set_page_config(page_title="KLAP Closing", layout="centered")
st.title("🍽️ KLAP Daily Closing")

# ---------- HEADER ----------
col1, col2 = st.columns(2)
branch = col1.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"])
date = col2.date_input("Closing Date", datetime.now())
date_str = date.strftime("%d/%m/%Y")

st.divider()

# ---------- SALES ----------
st.subheader("💰 Revenue Summary")

gross_sale = money_input("Gross Sale", "gross")
cash_sales = money_input("Cash Sales", "cash")
card_sales = money_input("Card Sales", "card")
fp_sales = money_input("Foodpanda Sales", "fp")

if cash_sales + card_sales + fp_sales != gross_sale:
    st.warning("⚠️ Sales breakdown does not match Gross Sale")
else:
    st.success("✅ Sales breakdown matches")

st.divider()

# ---------- TIPS ----------
tip_status = st.radio("Credit Card Tips?", ["No", "Yes"], horizontal=True)
cc_tips = money_input("Tip Amount", "tips") if tip_status == "Yes" else 0

# ---------- EXPENSES ----------
st.subheader("💸 Cash Expenses")

if "expenses" not in st.session_state:
    st.session_state.expenses = []

category = st.selectbox(
    "Category",
    ["Select Category", "Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill", "Other"]
)

if category != "Select Category":
    desc = st.text_input("Description")
    amt = money_input("Amount", "expense_amt")
    bill = st.radio("Bill Available?", ["No", "Yes"], horizontal=True)

    if st.button("Add Expense ➕") and amt > 0:
        st.session_state.expenses.append({
            "Date": date_str,
            "Category": category,          # kept for accounting
            "Description": desc or "-",    # printed
            "Amount": amt,
            "Bill": bill
        })
        st.rerun()

st.markdown("### Added Entries")

total_exp = 0
for i, e in enumerate(st.session_state.expenses):
    c = st.columns([3, 4, 2, 2, 1])
    c[0].write(e["Category"])
    c[1].write(e["Description"])
    c[2].write(f"PKR {e['Amount']:,}")
    c[3].write(e["Bill"])
    if c[4].button("🗑️", key=f"del_{i}"):
        st.session_state.expenses.pop(i)
        st.rerun()
    total_exp += e["Amount"]

st.divider()

expected_cash = cash_sales - total_exp - cc_tips
st.metric("Final Cash in Hand", f"PKR {expected_cash:,}")

# ---------- CONFIRM ----------
if st.button("🖨️ Confirm & Print"):
    if cash_sales + card_sales + fp_sales != gross_sale:
        st.error("Fix sales mismatch before confirming.")
    else:
        trigger_thermal_print(
            branch,
            date_str,
            cash_sales,
            cc_tips,
            st.session_state.expenses,
            expected_cash
        )
        st.session_state.expenses = []
