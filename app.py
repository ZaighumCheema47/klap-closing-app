import streamlit as st
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from printing_logic import trigger_thermal_print

# ---------- GOOGLE SHEETS ----------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
client = gspread.authorize(CREDS)
sheet = client.open("KLAP_Daily_Closings").worksheet("Closings")

# ---------- HELPERS ----------
def parse_money(val):
    return int(val.replace(",", "")) if val and val.replace(",", "").isdigit() else 0

def next_closing_code(branch, date_str):
    records = sheet.get_all_records()
    prefix = f"KLAP-{branch[:5].upper()}-{date_str.replace('/','')}"
    seq = sum(1 for r in records if r["Closing Code"].startswith(prefix)) + 1
    return f"{prefix}-{seq:02d}"

def upsert_closing(data):
    records = sheet.get_all_records()
    for i, r in enumerate(records, start=2):
        if r["Closing Code"] == data["Closing Code"]:
            sheet.update(f"A{i}:N{i}", [list(data.values())])
            return
    sheet.append_row(list(data.values()))

# ---------- UI ----------
st.set_page_config(layout="centered")
st.title("KLAP Daily Closing")

branch = st.selectbox("Branch", ["Cantt Branch", "DHA Branch"])
date = st.date_input("Date", datetime.today())
date_str = date.strftime("%d/%m/%Y")

st.subheader("Sales")
c1, c2, c3 = st.columns(3)
cash = parse_money(c1.text_input("Cash", ""))
card = parse_money(c2.text_input("Card", ""))
fp = parse_money(c3.text_input("Foodpanda", ""))

st.subheader("Cash Expenses")

if "expenses" not in st.session_state:
    st.session_state.expenses = []

category = st.selectbox("Category", ["Select", "Staff Food", "Fuel", "Maintenance", "Other"])

if category != "Select":
    desc = st.text_input("Description")
    if desc:
        amt = parse_money(st.text_input("Amount"))
        if amt > 0 and st.button("Add Expense"):
            st.session_state.expenses.append({
                "Category": category,
                "Description": desc,
                "Amount": amt
            })
            st.rerun()

total_exp = sum(e["Amount"] for e in st.session_state.expenses)
expected_cash = cash - total_exp

st.metric("Expected Cash", f"{expected_cash:,}")

if st.button("Confirm & Print"):
    closing_code = next_closing_code(branch, date_str)

    data = {
        "Closing Code": closing_code,
        "Date": date_str,
        "Branch": branch,
        "Cash Sales": cash,
        "Card Sales": card,
        "Foodpanda Sales": fp,
        "Total Expenses": total_exp,
        "Expected Cash": expected_cash
    }

    upsert_closing(data)

    trigger_thermal_print(
        branch,
        date_str,
        cash,
        card,
        fp,
        st.session_state.expenses,
        0,
        expected_cash,
        closing_code
    )

    st.session_state.expenses = []
