import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from streamlit_local_storage import LocalStorage
import json
import time
from gspread.exceptions import APIError

# ---------- Force Hide Side Bar ----------
st.set_page_config(page_title="KLAP Store & Kitchen Closing", layout="wide", initial_sidebar_state="collapsed")

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

# ---------- BRANCH CONFIG (same branches/sheets as Daily Closing) ----------
BRANCH_CONFIG = {
    "Cantt Branch":       {"prefix": "CANTT", "sheet": "KLAP Cantt Branch"},
    "DHA Branch":         {"prefix": "DHA",   "sheet": "KLAP DHA Branch"},
    "Pine Avenue Branch": {"prefix": "PINE",  "sheet": "KLAP Pine Avenue Branch"},
}

def get_sheet_title(branch_name):
    return BRANCH_CONFIG.get(branch_name, {}).get("sheet", "KLAP Cantt Branch")

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

def parse_num(val):
    """Parses a number typed into a stock cell; blank/invalid -> 0."""
    if val in (None, ""):
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0

# ---------- ITEM MASTER (from "Store & Kitchen Daily Closing.xlsx") ----------

# NOTE: The workbook's "Store" tab is not currently present (only "Kitchen"
# exists as of the last review). Store tracking is left out until that tab
# comes back — re-add a STORE_ITEMS list + "Store" entry in SHEET_TYPES then.
KITCHEN_ITEMS = [
    ("MEAT", "Beef", "KG"), ("MEAT", "Beef Pepperoni ( 200-Gram )", "KG"), ("MEAT", "Beef Bacon", "KG"),
    ("CHICKEN", "Burger Chicken", "KG"), ("CHICKEN", "Pizza Chicken", "KG"),
    ("BUNS & DOUGH", "Buns", "Nos"), ("BUNS & DOUGH", "Dough", "Nos"),
    ("CHEESE", "Cheese Slice Yellow", "KG"), ("CHEESE", "Cheese Slice White", "KG"), ("CHEESE", "Pizza Cheese", "KG"),
    ("FRIES", "Fries", "Kg"),
    ("SAUCE", "Pizza Sauce", "Kg"), ("SAUCE", "Bang Bang Dips Sauce", "Kg"), ("SAUCE", "Right Back Sauce", "Kg"),
    ("SAUCE", "Bang Bang For Burger Sauce", "Kg"), ("SAUCE", "Butter Mushroom Sauce", "Kg"),
    ("SAUCE", "BBQ Sauce", "Kg"), ("SAUCE", "Garlic Aioli Sauce", "Kg"), ("SAUCE", "Chicken Marination Premix", "Pkts"),
    ("SAUCE", "Empress Masala", "Kg"),
    ("MASALA", "Chicken Powder", "Kg"), ("MASALA", "Black Pepper", "Kg"), ("MASALA", "Paprika Powder", "Kg"),
    ("MASALA", "Garlic Powder", "Kg"), ("MASALA", "Onion Powder", "Kg"), ("MASALA", "Red Chilli Powder", "Kg"),
    ("MASALA", "Chilli Flakes", "Kg"), ("MASALA", "Baking Powder", "Kg"), ("MASALA", "Salt", "Kg"),
    ("MASALA", "Sugar", "Kg"), ("MASALA", "Pistachio", "Kg"), ("MASALA", "Cashew", "Kg"),
    ("VEGETABLES", "Tomatoes", "Kg"), ("VEGETABLES", "Rocket Leaves", "Kg"), ("VEGETABLES", "Okra", "Kg"),
    ("VEGETABLES", "Basil Leaves", "Kg"), ("VEGETABLES", "Garlic", "Kg"), ("VEGETABLES", "Onion", "Kg"),
    ("VEGETABLES", "Ice Berg", "Kg"), ("VEGETABLES", "Baby Potatoes", "Kg"), ("VEGETABLES", "Mushrooms", "Pkts"),
    ("VEGETABLES", "Cucumber", "Kg"), ("VEGETABLES", "Lemon", "Kg"), ("VEGETABLES", "Mint", "Pcs"),
    ("VEGETABLES", "Green Chillies", "Kg"),
    ("GROCERIES", "Young's Mayonese", "KG"), ("GROCERIES", "Peri Peri Mild", "Bottle"),
    ("GROCERIES", "Baffalo Sauce", "Bottle"), ("GROCERIES", "Knorr Ketchup", "Kg"), ("GROCERIES", "Mustard", "Kg"),
    ("GROCERIES", "Milk", "Ltrs"), ("GROCERIES", "Cream", "Pkts"), ("GROCERIES", "Maida", "Kg"),
    ("GROCERIES", "Honey", "Kg"), ("GROCERIES", "Vineger", "Kg"), ("GROCERIES", "Jalapenoes", "Tin"),
    ("GROCERIES", "Butter Margrin", "Kg"), ("GROCERIES", "Oil 1 Liter", "Ltrs"), ("GROCERIES", "Oil Tin", "Ltrs"),
    ("GROCERIES", "Olive Oil", "Ltrs"),
    ("ALUMUNIUM FOIL", "Alumunium Foil", "Roll"), ("ALUMUNIUM FOIL", "Black Olives", "Tin"), ("ALUMUNIUM FOIL", "F2", "Pcs"),
    ("ICED DRINKS", "Peach FIZZ", "ML"), ("ICED DRINKS", "Blackberry FIZZ", "ML"), ("ICED DRINKS", "Apple FIZZ", "ML"),
    ("PACKAGING", "Pizza Tray ( Dine In )", "Nos"), ("PACKAGING", "Pizza Box", "Nos"),
    ("PACKAGING", "Take Away Bags", "Nos"), ("PACKAGING", "Fries Pouch ( Cup )", "Nos"),
    ("PACKAGING", "Baby Loader Box", "Nos"), ("PACKAGING", "Glass ( Drinks )", "Nos"), ("PACKAGING", "Butter Paper", "Nos"),
    ("DRINKS", "Pepsi Can", "Can"), ("DRINKS", "Pepsi Diet Can", "Can"), ("DRINKS", "7up Can", "Can"),
    ("DRINKS", "7up Diet Can", "Can"), ("DRINKS", "Mirinda Can", "Can"), ("DRINKS", "Mirinda Diet", "Can"),
    ("DRINKS", "7up 1.5 Liter", "Ltr"), ("DRINKS", "Murrey Sparkling Water", "Bottle"),
    ("DRINKS", "Big Apple", "Can"), ("DRINKS", "Lemon Malt", "Can"), ("DRINKS", "Peach Malt", "Can"),
    ("GAS", "LPG Cylender", "Nos"),
]

SHEET_TYPES = {
    "Kitchen": {"items": KITCHEN_ITEMS, "worksheet": "Kitchen Inventory", "in_label": "Received Items", "out_label": "Used"},
}

HEADER = [
    "Date", "Category", "Item", "Unit", "Opening Stock", "In (Purchases/Received)",
    "Total", "Out (Issued/Used)", "Closing Stock", "Difference", "Remarks / Demand",
]

# ---------- SHEET HELPERS ----------

def get_or_create_worksheet(branch_name, sheet_type):
    if not client:
        return None
    spreadsheet = client.open(get_sheet_title(branch_name))
    title = SHEET_TYPES[sheet_type]["worksheet"]
    try:
        return spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows="4000", cols=str(len(HEADER)))
        ws.append_row(HEADER)
        return ws

def fetch_day_records(branch_name, sheet_type, date_str_sheet):
    """Returns {item_name: row_dict} for an already-saved date, or {} if none."""
    ws = get_or_create_worksheet(branch_name, sheet_type)
    if not ws:
        return {}
    records = ws.get_all_values()
    if len(records) < 2:
        return {}
    out = {}
    for r in records[1:]:
        if len(r) >= 11 and r[0] == date_str_sheet:
            out[r[2]] = {
                "Opening": r[4], "In": r[5], "Out": r[7], "Closing": r[8], "Remarks": r[10],
            }
    return out

def fetch_previous_closing(branch_name, sheet_type, before_date):
    """Returns {item_name: closing_stock} from the most recent saved date strictly before `before_date`."""
    ws = get_or_create_worksheet(branch_name, sheet_type)
    if not ws:
        return {}
    records = ws.get_all_values()
    if len(records) < 2:
        return {}
    latest_per_item = {}  # item -> (date_obj, closing_val)
    for r in records[1:]:
        if len(r) < 11:
            continue
        try:
            row_date = datetime.strptime(r[0], "%m/%d/%Y").date()
        except ValueError:
            continue
        if row_date >= before_date:
            continue
        item = r[2]
        prev = latest_per_item.get(item)
        if prev is None or row_date > prev[0]:
            latest_per_item[item] = (row_date, r[8])
    return {item: val for item, (_, val) in latest_per_item.items()}

def save_inventory(branch_name, sheet_type, date_str_sheet, rows):
    """Upserts every item row for this date (deletes any existing rows for the date first)."""
    ws = get_or_create_worksheet(branch_name, sheet_type)
    if not ws:
        return False
    try:
        all_values = ws.get_all_values()
        if len(all_values) > 1:
            to_delete = [i + 1 for i, r in enumerate(all_values) if r and r[0] == date_str_sheet]
            batch_delete_rows(ws, to_delete)
        with_backoff(ws.append_rows, rows)
        return True
    except Exception as e:
        st.error(f"Inventory Sheet Error: {e}")
        return False

# ---------- UI ----------

st.title("📦 KLAP Store & Kitchen Daily Closing")

col_branch, col_type, col_date = st.columns(3)
branch = col_branch.selectbox("Select Branch", list(BRANCH_CONFIG.keys()))
sheet_type = col_type.radio("Count Sheet", list(SHEET_TYPES.keys()), horizontal=True)
date_selected = col_date.date_input("Closing Date", datetime.today())
date_str_sheet = date_selected.strftime("%m/%d/%Y")

# ---------- BRANCH PIN GATE (shared with Daily Closing) ----------
if st.session_state.get("unlocked_branch") != branch:
    st.subheader(f"🔒 Enter PIN for {branch}")
    pin_entry = st.text_input("4-digit Branch PIN", max_chars=4, key="sk_pin_entry", help="Numbers only")
    if st.button("Unlock"):
        correct_pin = st.secrets.get("branch_pins", {}).get(branch)
        if correct_pin and pin_entry == str(correct_pin):
            st.session_state.unlocked_branch = branch
            st.rerun()
        else:
            st.error("Incorrect PIN.")
    st.stop()

st.divider()

cfg = SHEET_TYPES[sheet_type]
items = cfg["items"]
categories = list(dict.fromkeys(cat for cat, _, _ in items))  # preserves first-seen order

# ---------- LOAD / DRAFT STATE ----------
localS = LocalStorage(key="klap_sk_storage")
selection_key = f"{branch}|{sheet_type}|{date_selected.strftime('%d%m%y')}"
storage_key = f"sk_draft_{selection_key}"

if st.session_state.get("sk_loaded_for") != selection_key:
    raw_draft = None
    try:
        raw_draft = localS.getItem(storage_key)
    except Exception:
        raw_draft = None
    draft = {}
    if raw_draft:
        try:
            draft = json.loads(raw_draft) if isinstance(raw_draft, str) else raw_draft
        except (TypeError, ValueError):
            draft = {}

    existing = fetch_day_records(branch, sheet_type, date_str_sheet)
    prev_closing = fetch_previous_closing(branch, sheet_type, date_selected) if not existing else {}

    data = {}
    for cat, item, unit in items:
        if item in draft:
            d = draft[item]
            data[item] = {"Opening": d.get("Opening", 0), "In": d.get("In", 0), "Out": d.get("Out", 0), "Closing": d.get("Closing", 0), "Remarks": d.get("Remarks", "")}
        elif item in existing:
            e = existing[item]
            data[item] = {"Opening": parse_num(e["Opening"]), "In": parse_num(e["In"]), "Out": parse_num(e["Out"]), "Closing": parse_num(e["Closing"]), "Remarks": e["Remarks"]}
        else:
            data[item] = {"Opening": parse_num(prev_closing.get(item, 0)), "In": 0, "Out": 0, "Closing": 0, "Remarks": ""}

    st.session_state.sk_data = data
    st.session_state.sk_loaded_for = selection_key
    if existing:
        st.info(f"↩️ Loaded previously saved {sheet_type} closing for {date_str_sheet}.")
    elif prev_closing:
        st.info("↩️ Opening Stock pre-filled from the previous saved day's Closing Stock.")

def save_draft():
    payload = dict(st.session_state.sk_data)
    try:
        localS.setItem(storage_key, json.dumps(payload), key=f"set_{storage_key}")
    except Exception:
        pass

st.caption(f"{sheet_type} count sheet · {branch} · {date_str_sheet}")

# ---------- CATEGORY GRIDS ----------
grand_total_diff = 0
mismatched_items = []

for cat in categories:
    cat_items = [(item, unit) for c, item, unit in items if c == cat]
    df_rows = []
    for item, unit in cat_items:
        d = st.session_state.sk_data[item]
        df_rows.append({
            "Item": item, "Unit": unit,
            "Opening": d["Opening"], cfg["in_label"]: d["In"],
            cfg["out_label"]: d["Out"], "Closing": d["Closing"],
            "Remarks": d["Remarks"],
        })
    df = pd.DataFrame(df_rows)

    with st.expander(f"{cat}  ({len(cat_items)} items)"):
        edited = st.data_editor(
            df,
            key=f"editor_{sheet_type}_{cat}",
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            disabled=["Item", "Unit"],
            column_config={
                "Opening": st.column_config.NumberColumn("Opening Stock", min_value=0, step=1),
                cfg["in_label"]: st.column_config.NumberColumn(cfg["in_label"], min_value=0, step=1),
                cfg["out_label"]: st.column_config.NumberColumn(cfg["out_label"], min_value=0, step=1),
                "Closing": st.column_config.NumberColumn("Closing Stock", min_value=0, step=1),
                "Remarks": st.column_config.TextColumn("Remarks / Demand"),
            },
        )

        # write edits back into session state + compute Total/Difference for the preview
        preview_rows = []
        for _, row in edited.iterrows():
            item = row["Item"]
            opening = parse_num(row["Opening"])
            in_amt = parse_num(row[cfg["in_label"]])
            out_amt = parse_num(row[cfg["out_label"]])
            closing = parse_num(row["Closing"])
            remarks = row["Remarks"] or ""

            st.session_state.sk_data[item] = {"Opening": opening, "In": in_amt, "Out": out_amt, "Closing": closing, "Remarks": remarks}

            total = opening + in_amt
            difference = total - out_amt - closing
            if difference != 0:
                mismatched_items.append((item, difference))
            grand_total_diff += difference
            preview_rows.append({"Item": item, "Total": total, "Difference": difference})

        st.dataframe(pd.DataFrame(preview_rows), hide_index=True, use_container_width=True)

save_draft()

# ---------- DISCREPANCY SUMMARY ----------
if mismatched_items:
    st.warning(f"⚠️ {len(mismatched_items)} item(s) have a non-zero Difference (Total − Out − Closing). Review before saving.")
    with st.expander("View discrepancies"):
        st.dataframe(pd.DataFrame(mismatched_items, columns=["Item", "Difference"]), hide_index=True, use_container_width=True)
else:
    st.success("✅ All items reconcile (Difference = 0).")

st.divider()

# ---------- SAVE ----------
if st.button("💾 Save Inventory Count", type="primary", use_container_width=True):
    rows = []
    for cat, item, unit in items:
        d = st.session_state.sk_data[item]
        total = d["Opening"] + d["In"]
        difference = total - d["Out"] - d["Closing"]
        rows.append([
            date_str_sheet, cat, item, unit,
            d["Opening"], d["In"], total, d["Out"], d["Closing"], difference, d["Remarks"],
        ])

    if save_inventory(branch, sheet_type, date_str_sheet, rows):
        st.success(f"Saved {sheet_type} closing for {branch} — {date_str_sheet}.")
        try:
            localS.deleteItem(storage_key, key=f"del_{storage_key}")
        except Exception:
            pass
        st.session_state.sk_loaded_for = None
        st.rerun()
