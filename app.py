import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import streamlit.components.v1 as components

# --- 1. THE CALCULATOR MASK (FIXED FOR LARGE NUMBERS) ---
def inject_calculator_mask():
    components.html("""
    <script>
    const interval = setInterval(() => {
        const inputs = window.parent.document.querySelectorAll('input[aria-label]');
        inputs.forEach(input => {
            if (!input.dataset.maskSet) {
                input.addEventListener('input', function(e) {
                    // Remove commas to get raw number
                    let rawValue = e.target.value.replace(/,/g, "");
                    if (!isNaN(rawValue) && rawValue !== "") {
                        // Format with commas and set back to input
                        e.target.value = Number(rawValue).toLocaleString('en-US');
                    }
                });
                input.dataset.maskSet = "true";
            }
        });
    }, 500);
    </script>
    """, height=0)

# Helper to convert "135,450" back to 135450 for math
def to_int(val):
    if not val: return 0
    try:
        return int(str(val).replace(",", "").split(".")[0])
    except:
        return 0

# --- 2. PRINTING MODULE ---
def trigger_thermal_print(branch, date_display, gross, cash, card, fp, tips, expenses, expected):
    exp_html = "".join([
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
            #receipt-box {{ position: absolute; left: 0; top: 0; width: 75mm !important; }}
            @page {{ margin: 0; }}
        }}
    </style>
    <div id="receipt-box" style="background-color:white; color:black; padding:20px; font-family:'Courier New', monospace; border:1px solid #000;">
        <h1 style="text-align:center; margin:0; font-size:28px;">KLAP</h1>
        <p style="text-align:center; margin:5px 0; font-size:16px;"><b>{branch.upper()}</b><br>Date: {date_display}</p>
        <hr style="border-top:1px dashed black;">
        <p style="font-size:16px;">Gross Sale: <span style="float:right;">{int(gross):,}</span></p>
        <p style="font-size:16px;">Cash Sale: <span style="float:right;">{int(cash):,}</span></p>
        <p style="font-size:16px;">Card Sale: <span style="float:right;">{int(card):,}</span></p>
        <p style="font-size:16px;">Foodpanda: <span style="float:right;">{int(fp):,}</span></p>
        <hr style="border-top:1px dashed black;">
        <p style="margin:10px 0 5px 0; font-weight:bold; font-size:16px;">EXPENSES:</p>
        {exp_html}
        {"<p style='margin:10px 0; font-size:16px;'>CC Tips: <span style='float:right;'>(" + f"{int(tips):,}" + ")</span></p>" if tips > 0 else ""}
        <hr style="border-top:1px dashed black;">
        <div style="text-align:center; margin-top:10px;">
            <p style="margin:0; font-size:14px;">CASH IN HAND</p>
            <h2 style="margin:0; font-size:32px;">{int(expected):,}</h2>
        </div>
    </div>
    <script>setTimeout(function() {{ window.print(); }}, 700);</script>
    """
    components.html(receipt_html, height=0)

# --- 3. UI & SHEETS ---
st.set_page_config(page_title="KLAP Closing", layout="centered")
inject_calculator_mask()

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

# --- 4. APP ---
st.title("🍽️ KLAP Daily Closing")

col_branch, col_date = st.columns(2)
branch = col_branch.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"])
date_str = col_date.date_input("Closing Date", datetime.now()).strftime("%d/%m/%Y")

st.subheader("💰 Revenue Summary")
# Using text_input for the "Calculator" feel without limits
gross_in = st.text_input("Gross Sale", placeholder="PKR")
c1, c2, c3 = st.columns(3)
cash_in = c1.text_input("Cash Sales", placeholder="PKR")
card_in = c2.text_input("Card Sales", placeholder="PKR")
fp_in = c3.text_input("Foodpanda", placeholder="PKR")

# Convert to integers for math
gross = to_int(gross_in)
cash = to_int(cash_in)
card = to_int(card_in)
fp = to_int(fp_in)

if gross and (cash+card+fp) != gross:
    st.warning(f"⚠️ Mismatch! (Total: {cash+card+fp:,} vs Gross: {gross:,})")

st.divider()
tip_status = st.radio("CC Tips?", ["No", "Yes"], horizontal=True)
cc_tips = to_int(st.text_input("Tip Amount", "0")) if tip_status == "Yes" else 0

st.subheader("💸 Cash Expenses")
if 'expenses' not in st.session_state: st.session_state.expenses = []
predefined = ["Select Category", "Staff Food", "Cleaner", "Rickshaw/Fuel", "Pepsi/LPG", "Maintenance", "Utility Bill", "Other..."]
cat = st.selectbox("Category", predefined)

if cat != "Select Category":
    desc = st.text_input("Description")
    amt_in = st.text_input("Amount", placeholder="PKR")
    bill = st.radio("Bill Available?", ["No", "Yes"], horizontal=True)
    if st.button("Add Expense ➕"):
        if to_int(amt_in) > 0:
            st.session_state.expenses.append({"Date": date_str, "Category": cat, "Description": desc if desc else "-", "Amount": to_int(amt_in), "Bill": bill})
            st.rerun()

st.markdown("### Added Entries")
total_exp = 0
for i, e in enumerate(st.session_state.expenses):
    c = st.columns([3, 4, 2, 2, 1])
    c[0].write(f"**{e['Category']}**"); c[1].write(e['Description']); c[2].write(f"PKR {e['Amount']:,}"); c[3].write(f"Bill: {e['Bill']}")
    if c[4].button("🗑️", key=f"del_{i}"): st.session_state.expenses.pop(i); st.rerun()
    total_exp += e['Amount']

st.divider()
expected_cash = cash - total_exp - cc_tips
st.metric("Final Cash in Hand", f"PKR {int(expected_cash):,}")

if st.button("🖨️ Confirm & Print"):
    if gross and (cash + card + fp) != gross:
        st.error("Sales breakdown mismatch!")
    else:
        rows = [[e['Date'], e['Category'], e['Description'], e['Amount'], e['Bill']] for e in st.session_state.expenses]
        if cc_tips > 0: rows.append([date_str, "CC TIP", "Staff Payout", cc_tips, "No"])
        if post_to_gsheet(branch, rows):
            st.success("Posted Successfully!")
            trigger_thermal_print(branch, date_str, gross, cash, card, fp, cc_tips, st.session_state.expenses, expected_cash)
            st.session_state.expenses = []
