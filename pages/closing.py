import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from printing_logic import trigger_thermal_print
from streamlit_local_storage import LocalStorage
import re
import json
import time
from gspread.exceptions import APIError

# ---------- Force Hide Side Bar ----------
st.set_page_config(page_title="KLAP Daily Closing", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        [data-testid="collapsedControl"] { display: none; }
    </style>
""", unsafe_allow_html=True)

# ---------- GOOGLE SHEETS CORE ----------

def get_gspread_client():
    try:
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Credential Error: {e}")
        return None

client = get_gspread_client()

# ---------- BRANCH CONFIG ----------
# Add/remove branches here only — everything else (dropdown, ID prefix,
# Google Sheet name, search lookup, PIN lookup) reads from this one place.
BRANCH_CONFIG = {
    "Cantt Branch":       {"prefix": "CANTT", "sheet": "KLAP Cantt Branch"},
    "DHA Branch":         {"prefix": "DHA",   "sheet": "KLAP DHA Branch"},
    "Pine Avenue Branch": {"prefix": "PINE",  "sheet": "KLAP Pine Avenue Branch"},
}

def get_sheet_title(branch_name):
    return BRANCH_CONFIG.get(branch_name, {}).get("sheet", "KLAP Cantt Branch")

def get_branch_prefix(branch_name):
    return BRANCH_CONFIG.get(branch_name, {}).get("prefix", "CANTT")

def resolve_sheet_from_id(search_id):
    """Match a closing ID (e.g. PINE290126CR) back to its branch sheet by prefix."""
    for cfg in BRANCH_CONFIG.values():
        if search_id.startswith(cfg["prefix"]):
            return cfg["sheet"]
    return "KLAP Cantt Branch"

def with_backoff(fn, *args, retries=3, **kwargs):
    """Runs a gspread call, retrying on 429 quota errors with exponential backoff."""
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except APIError as e:
            is_quota = "429" in str(e) or "Quota exceeded" in str(e)
            if not is_quota or attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)  # 1s, 2s, 4s

def batch_delete_rows(sheet, row_indices):
    """Deletes multiple rows in a single API call instead of one call per row."""
    if not row_indices:
        return
    requests = [
        {
            "deleteDimension": {
                "range": {
                    "sheetId": sheet.id,
                    "dimension": "ROWS",
                    "startIndex": idx - 1,  # 0-indexed, sheet rows are 1-indexed
                    "endIndex": idx,
                }
            }
        }
        for idx in sorted(row_indices, reverse=True)
    ]
    with_backoff(sheet.spreadsheet.batch_update, {"requests": requests})

def parse_money(val):
    if not val:
        return 0
    clean_val = re.sub(r"[^\d]", "", str(val).split(".")[0])
    return int(clean_val) if clean_val else 0

def upsert_sales_data(branch_name, daily_id, date_str, cash, card, fp, gross, cc_tips):
    """Saves/Updates the 'Sales' worksheet with Settlement vs POS reconciliation"""
    if client:
        try:
            sheet_title = get_sheet_title(branch_name)
            spreadsheet = client.open(sheet_title)

            try:
                sales_sheet = spreadsheet.worksheet("Sales")
            except gspread.exceptions.WorksheetNotFound:
                # 12 columns to accommodate the Settlement logic
                sales_sheet = spreadsheet.add_worksheet(title="Sales", rows="100", cols="12")
                sales_sheet.append_row([
                    "ID", "Date", "POS Cash", "POS Card", "Foodpanda", "POS Gross Total", 
                    "Settlement Card", "Cash-in-Hand", "Bank POS Fees", "Card Clearing", 
                    "FoodPanda Fees", "Foodpanda Clearing"
                ])

            # ---------- THE ADJUSTED MATH ----------
            
            # 1. Settlement Card (POS Card + CC Tip = Bank Statement Figure)
            settlement_card = card + cc_tips
            
            # 2. Cash-in-Hand (Pure POS Cash as a negative offset)
            # Per your instruction: We are NOT deducting cc_tips from the cash transfer logic
            neg_cash = cash * -1
            
            # 3. Bank Fees (Calculated on the full settlement amount)
            bank_fee = round(settlement_card * 0.0116, 2)
            neg_bank_fee = bank_fee * -1
            
            # 4. Card Clearing (Net amount hitting the bank)
            card_clearing = round((settlement_card - bank_fee) * -1, 2)
            
            # 5. Foodpanda Logic (35% Fee)
            fp_fee = round(fp * 0.35, 2)
            neg_fp_fee = fp_fee * -1
            fp_clearing = round((fp - fp_fee) * -1, 2)

            # ---------- UPSERT LOGIC ----------
            records = sales_sheet.get_all_values()
            if len(records) > 1:
                rows_to_delete = [i + 1 for i, row in enumerate(records) if row[0] == daily_id]
                batch_delete_rows(sales_sheet, rows_to_delete)

            # Map to Columns A through L
            new_row = [
                daily_id,         # A: ID
                date_str,         # B: Date
                cash,             # C: POS Cash
                card,             # D: POS Card
                fp,               # E: Foodpanda
                gross,            # F: POS Gross Total
                settlement_card,  # G: Settlement Card
                neg_cash,         # H: Cash-in-Hand
                neg_bank_fee,     # I: Bank POS Fees
                card_clearing,    # J: Card Clearing
                neg_fp_fee,       # K: FoodPanda Fees
                fp_clearing       # L: Foodpanda Clearing
            ]

            with_backoff(sales_sheet.append_row, new_row)
            return True
        except Exception as e:
            st.error(f"Sales Sheet Error: {e}")
    return False

def upsert_closing(branch_name, custom_id, data_rows):
    """Saves detailed expenses to the main sheet"""
    if client:
        try:
            sheet_title = get_sheet_title(branch_name)
            sheet = client.open(sheet_title).sheet1
            all_records = sheet.get_all_values()

            if len(all_records) > 1:
                rows_to_delete = [i + 1 for i, row in enumerate(all_records) if row[0] == custom_id]
                batch_delete_rows(sheet, rows_to_delete)

            final_rows = [[custom_id] + row for row in data_rows]
            with_backoff(sheet.append_rows, final_rows)
            return True
        except Exception as e:
            st.error(f"Expense Sheet Error: {e}")
    return False

# ---------- UI LOGIC ----------

if "expenses" not in st.session_state:
    st.session_state.expenses = []
if "exp_form_key" not in st.session_state:
    st.session_state.exp_form_key = 0
if "confirm_pending" not in st.session_state:
    st.session_state.confirm_pending = False

st.title("🍽️ KLAP Daily Closing")

# --- BRANCH / DATE SELECT (comes first so we know which PIN to check) ---
col_branch, col_date = st.columns(2)
branch = col_branch.selectbox("Select Branch", list(BRANCH_CONFIG.keys()))
date_selected = col_date.date_input("Closing Date", datetime.today())
date_str_display = date_selected.strftime("%d-%m-%y")   # used on the printed receipt only
date_str_sheet = date_selected.strftime("%m/%d/%Y")      # used for Google Sheet rows only

branch_prefix = get_branch_prefix(branch)
daily_id = f"{branch_prefix}{date_selected.strftime('%d%m%y')}CR"

# ---------- FEATURE 1: BRANCH PIN GATE ----------
if st.session_state.get("unlocked_branch") != branch:
    st.subheader(f"🔒 Enter PIN for {branch}")
    pin_entry = st.text_input("4-digit Branch PIN", max_chars=4, key="pin_entry", help="Numbers only")
    if st.button("Unlock"):
        correct_pin = st.secrets.get("branch_pins", {}).get(branch)
        if correct_pin and pin_entry == str(correct_pin):
            st.session_state.unlocked_branch = branch
            st.rerun()
        else:
            st.error("Incorrect PIN.")
    st.stop()

st.divider()

# --- SEARCH POPOVER ---
with st.popover("🔍 Search Past Closing"):
    search_id = st.text_input("ID (e.g. DHA290126CR)").upper().strip()
    if st.button("Load Data"):
        if client and search_id:
            try:
                target_sheet = resolve_sheet_from_id(search_id)
                sheet = client.open(target_sheet).sheet1
                records = sheet.get_all_values()
                matched_rows = [r for r in records if r[0] == search_id]
                if matched_rows:
                    st.session_state.expenses = [
                        {
                            "Date": r[1],
                            "Category": r[2],
                            "Description": r[3],
                            "Amount": int(r[4]),
                            "Bill": r[5],
                        }
                        for r in matched_rows if r[2] != "SALES_SUMMARY"
                    ]
                    st.success("Loaded!")
                    st.rerun()
                else:
                    st.error("Not found.")
            except Exception as e:
                st.error(f"Error: {e}")

st.divider()

# ---------- FEATURE 3: BROWSER-LOCAL DRAFT PERSISTENCE ----------
# Everything entered (revenue fields + expenses) is mirrored into the
# browser's localStorage, scoped to this branch+date. If the Streamlit
# session drops (wifi blip, tab backgrounded, app cold-starts) and the
# page reloads, the draft is restored automatically. It's only cleared
# once the closing is actually posted and printed.
localS = LocalStorage(key="klap_storage")
storage_key = f"klap_draft_{branch_prefix}_{date_selected.strftime('%d%m%y')}"

if st.session_state.get("loaded_draft_for") != storage_key:
    raw_draft = localS.getItem(storage_key)
    draft = {}
    if raw_draft:
        try:
            draft = json.loads(raw_draft) if isinstance(raw_draft, str) else raw_draft
        except (TypeError, ValueError):
            draft = {}

    st.session_state.gross_in = draft.get("gross", "")
    st.session_state.cash_in = draft.get("cash", "")
    st.session_state.card_in = draft.get("card", "")
    st.session_state.fp_in = draft.get("fp", "")
    st.session_state.tip_status = draft.get("tip_status", "No")
    st.session_state.tip_amt = draft.get("tip_amt", "")
    st.session_state.expenses = draft.get("expenses", [])
    st.session_state.loaded_draft_for = storage_key

    if draft:
        st.info("↩️ Restored previously entered data for this branch/date.")

def save_draft():
    payload = {
        "gross": st.session_state.get("gross_in", ""),
        "cash": st.session_state.get("cash_in", ""),
        "card": st.session_state.get("card_in", ""),
        "fp": st.session_state.get("fp_in", ""),
        "tip_status": st.session_state.get("tip_status", "No"),
        "tip_amt": st.session_state.get("tip_amt", ""),
        "expenses": st.session_state.expenses,
    }
    localS.setItem(storage_key, json.dumps(payload), key=f"set_{storage_key}")

def clear_draft():
    localS.deleteItem(storage_key, key=f"del_{storage_key}")

# REVENUE SUMMARY
st.subheader("💰 Revenue Summary")
gross_in = st.text_input("Gross Sale", placeholder="PKR", key="gross_in", on_change=save_draft)
c1, c2, c3 = st.columns(3)
cash_in = c1.text_input("Cash Sales", placeholder="PKR", key="cash_in", on_change=save_draft)
card_in = c2.text_input("Credit Card Sales", placeholder="PKR", key="card_in", on_change=save_draft)
fp_in = c3.text_input("Foodpanda Sales", placeholder="PKR", key="fp_in", on_change=save_draft)

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

# EXPENSE ENTRY
st.subheader("💸 Add New Expense")
predefined = ["Select Category", "Staff Food", "Demand Delivery", "Order Delivery", "Staff Rides", "Groceries", "Vegetables", "Generator", "Bevrages", "Repairs", "LPG", "Cleaning", "Boss Personal", "Other"]
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
                    "Date": date_str_sheet, "Category": cat_choice, "Description": desc, "Amount": amt, "Bill": bill_available,
                })
                st.session_state.exp_form_key += 1
                save_draft()
                st.rerun()

st.divider()

# Metrics & Tipping
tip_status = st.radio("Credit Card Tips?", ["No", "Yes"], horizontal=True, key="tip_status", on_change=save_draft)
cc_tips = parse_money(st.text_input("Tip Amount", key="tip_amt", on_change=save_draft)) if tip_status == "Yes" else 0
total_exp = sum(e["Amount"] for e in st.session_state.expenses)
expected_cash = cash - total_exp - cc_tips
st.metric("Final Cash in Hand", f"PKR {int(expected_cash):,}")

# ---------- FEATURE 2: "ARE YOU SURE?" CONFIRM BEFORE POSTING & PRINTING ----------
if not st.session_state.confirm_pending:
    if st.button("🖨️ Confirm & Print Closing", type="primary", use_container_width=True):
        if mismatch or gross == 0:
            st.error("Please verify Revenue Totals.")
        else:
            st.session_state.confirm_pending = True
            st.rerun()
else:
    st.warning(f"⚠️ Post closing **{daily_id}** — Cash in Hand: PKR {int(expected_cash):,}. This will save to Sheets and print the receipt. Continue?")
    col_yes, col_no = st.columns(2)
    confirmed = col_yes.button("✅ Yes, Post & Print", use_container_width=True)
    cancelled = col_no.button("❌ Cancel", use_container_width=True)

    if confirmed:
        rows = [[e["Date"], e["Category"], e["Description"], e["Amount"], e["Bill"]] for e in st.session_state.expenses]
        if cc_tips > 0:
            rows.append([date_str_sheet, "CC TIP", "Paid to staff", cc_tips, "No"])

        if upsert_closing(branch, daily_id, rows) and upsert_sales_data(
            branch, daily_id, date_str_sheet, cash, card, fp, gross, cc_tips
        ):
            st.success(f"Successfully posted! ID: {daily_id}")
            trigger_thermal_print(
                branch=branch, date_display=date_str_display, cash_sales=cash, card_sales=card,
                fp_sales=fp, cc_tips=cc_tips, expenses=st.session_state.expenses,
                expected_cash=expected_cash, closing_code=daily_id,
            )
            st.session_state.expenses = []
            clear_draft()
            st.session_state.confirm_pending = False
            # NOTE: no st.rerun() here on purpose — the receipt component needs
            # ~500ms for its embedded script to fire window.print() before the
            # page rerenders. Forcing an immediate rerun tears down that
            # component first and silently kills the print job. The page will
            # naturally refresh to a clean state on the user's next interaction.
    elif cancelled:
        st.session_state.confirm_pending = False
        st.rerun()

st.divider()

if st.session_state.expenses:
    st.subheader("📑 Current Expenses List")
    for i, e in enumerate(st.session_state.expenses):
        cols = st.columns([3, 4, 2, 2, 1])
        cols[0].write(f"**{e['Category']}**")
        cols[1].write(e["Description"])
        cols[2].write(f"PKR {e['Amount']:,}")
        cols[3].write(f"Bill: {e['Bill']}")
        if cols[4].button("🗑️", key=f"del_{i}"):
            st.session_state.expenses.pop(i)
            save_draft()
            st.rerun()
