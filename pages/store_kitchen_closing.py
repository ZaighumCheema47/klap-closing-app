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

@st.cache_resource(show_spinner=False)
def get_gspread_client():
    """Cached so the service-account handshake happens once per session, not on
    every rerun — the grid reruns the whole script on each cell edit."""
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

def r3(val):
    """Rounds to 3dp before comparing — raw float math produces dust like
    0.1 + 0.2 != 0.3, which would otherwise flag clean rows as impossible."""
    return round(float(val), 3)

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
    ("GROCERIES", "Milk 01-Ltr", "Ltrs"), ("GROCERIES", "Cream", "Pkts"), ("GROCERIES", "Maida", "Kg"),
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
    "Kitchen": {"items": KITCHEN_ITEMS, "worksheet": "Kitchen Inventory", "in_label": "Received"},
}

HEADER = [
    "Date", "Category", "Item", "Unit",
    "Opening Stock", "Adjustment", "Received", "Available",
    "Wastage", "Staff Meal", "Closing Stock", "Consumption (Derived)",
    "Remarks / Demand", "Saved At",
]

# Column positions in the sheet row, so the readers below stay readable.
C_DATE, C_ITEM = 0, 2
C_OPENING, C_ADJUST, C_RECEIVED = 4, 5, 6
C_WASTAGE, C_STAFF, C_CLOSING = 8, 9, 10
C_REMARKS = 12

def compute(d):
    """The whole point of the sheet: consumption is DERIVED, never typed.

        Available   = Opening + Adjustment + Received
        Consumption = Available - Wastage - Staff Meal - Closing

    Because nobody can type Consumption, it cannot be plugged to make the
    day look tidy — the only inputs are what physically arrived and what is
    physically on the shelf."""
    available = d["Opening"] + d["Adjust"] + d["Received"]
    consumption = available - d["Wastage"] - d["StaffMeal"] - d["Closing"]
    return available, consumption

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
        with_backoff(ws.append_row, HEADER)
        return ws

def load_sheet_state(branch_name, sheet_type, target_date, date_str):
    """One read of the worksheet answers all three questions we have:
       - is there a saved count for this exact date? (edit mode)
       - what did each item close at on the most recent earlier date? (carry-forward)
       - is there any history at all before this date? (first-ever count / seed mode)"""
    ws = get_or_create_worksheet(branch_name, sheet_type)
    if not ws:
        return {}, {}, False
    values = with_backoff(ws.get_all_values)
    if not values:
        return {}, {}, False

    # Header drift check costs nothing here — we already have row 1 in hand.
    if values[0] != HEADER:
        if len(values) <= 1:
            with_backoff(ws.update, range_name="A1", values=[HEADER])
        else:
            st.warning(
                "⚠️ This worksheet was written by an older version of this page and its "
                "columns no longer match. Rename or archive the existing "
                f"'{SHEET_TYPES[sheet_type]['worksheet']}' tab so a fresh one can be created."
            )

    existing, latest = {}, {}  # latest: item -> (date, closing)
    has_history = False
    for row in values[1:]:
        if len(row) <= C_REMARKS:
            continue
        if row[C_DATE] == date_str:
            existing[row[C_ITEM]] = {
                "Opening": row[C_OPENING], "Adjust": row[C_ADJUST], "Received": row[C_RECEIVED],
                "Wastage": row[C_WASTAGE], "StaffMeal": row[C_STAFF], "Closing": row[C_CLOSING],
                "Remarks": row[C_REMARKS],
            }
        try:
            row_date = datetime.strptime(row[C_DATE], "%m/%d/%Y").date()
        except ValueError:
            continue
        if row_date < target_date:
            has_history = True
            item = row[C_ITEM]
            prev = latest.get(item)
            if prev is None or row_date > prev[0]:
                latest[item] = (row_date, row[C_CLOSING])

    return existing, {k: v[1] for k, v in latest.items()}, has_history

def save_inventory(branch_name, sheet_type, date_str, rows):
    """Upserts every item row for this date (deletes any existing rows for the date first)."""
    ws = get_or_create_worksheet(branch_name, sheet_type)
    if not ws:
        return False
    try:
        all_values = with_backoff(ws.get_all_values)
        if len(all_values) > 1:
            to_delete = [i + 1 for i, r in enumerate(all_values) if r and r[0] == date_str]
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
storage_key = f"sk_draft_v2_{selection_key}"

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

    existing, prev_closing, has_history = load_sheet_state(branch, sheet_type, date_selected, date_str_sheet)

    data = {}
    for cat, item, unit in items:
        src = draft.get(item) or existing.get(item)
        if src:
            data[item] = {
                "Opening": parse_num(src.get("Opening")), "Adjust": parse_num(src.get("Adjust")),
                "Received": parse_num(src.get("Received")), "Wastage": parse_num(src.get("Wastage")),
                "StaffMeal": parse_num(src.get("StaffMeal")), "Closing": parse_num(src.get("Closing")),
                "Remarks": src.get("Remarks", "") or "",
            }
        else:
            data[item] = {
                "Opening": parse_num(prev_closing.get(item, 0)), "Adjust": 0.0, "Received": 0.0,
                "Wastage": 0.0, "StaffMeal": 0.0, "Closing": 0.0, "Remarks": "",
            }

    st.session_state.sk_data = data
    st.session_state.sk_seed_mode = not has_history
    st.session_state.sk_loaded_for = selection_key

    if existing:
        st.info(f"↩️ Loaded the saved {sheet_type} count for {date_str_sheet}.")
    elif prev_closing:
        st.info("↩️ Opening Stock carried forward from the previous count.")

seed_mode = st.session_state.get("sk_seed_mode", False)

def save_draft():
    try:
        localS.setItem(storage_key, json.dumps(st.session_state.sk_data), key=f"set_{storage_key}")
    except Exception:
        pass

st.caption(f"{sheet_type} count sheet · {branch} · {date_str_sheet}")

if seed_mode:
    st.warning(
        "🌱 **Baseline count** — there is no earlier count on record, so **Opening Stock is open "
        "for entry this once**. Count every item physically and type what is actually on the shelf "
        "into Opening Stock. Every future day carries forward from here, so take the time to get it right."
    )
else:
    st.caption(
        "Opening Stock is locked — it carries forward from the last count so the day-to-day chain "
        "can't be broken. Genuine corrections (found stock, a delivery booked to the wrong day, a new "
        "item) go in **Adjustment**, which requires a reason in Remarks. **Consumption is calculated**, "
        "not typed: Opening + Adjustment + Received − Wastage − Staff Meal − Closing."
    )

# ---------- CATEGORY GRIDS ----------
COLUMN_ORDER = ["Item", "Unit", "Opening", "Adjust", "Received", "Available",
                "Wastage", "StaffMeal", "Closing", "Consumption", "Remarks"]

locked_cols = ["Item", "Unit", "Available", "Consumption"]
if not seed_mode:
    locked_cols.append("Opening")

impossible_rows = []      # closing + wastage + staff meal exceeds what was available
adjust_no_reason = []     # adjustment entered with no explanation
untouched = 0             # rows with no movement at all — a hint the count wasn't done

for cat in categories:
    cat_items = [(item, unit) for c, item, unit in items if c == cat]
    df_rows = []
    for item, unit in cat_items:
        d = st.session_state.sk_data[item]
        available, consumption = compute(d)
        df_rows.append({
            "Item": item, "Unit": unit,
            "Opening": d["Opening"], "Adjust": d["Adjust"], "Received": d["Received"],
            "Available": available,
            "Wastage": d["Wastage"], "StaffMeal": d["StaffMeal"], "Closing": d["Closing"],
            "Consumption": consumption,
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
            column_order=COLUMN_ORDER,
            disabled=locked_cols,
            column_config={
                "Item": st.column_config.TextColumn("Item", width="medium"),
                "Unit": st.column_config.TextColumn("Unit", width="small"),
                "Opening": st.column_config.NumberColumn("Opening", min_value=0, format="%.2f", width="small"),
                "Adjust": st.column_config.NumberColumn(
                    "Adjustment", format="%.2f", width="small",
                    help="Correction to opening stock (+/-). A reason in Remarks is required.",
                ),
                "Received": st.column_config.NumberColumn(
                    cfg["in_label"], min_value=0, format="%.2f", width="small",
                    help="Stock received from the store or a vendor today.",
                ),
                "Available": st.column_config.NumberColumn(
                    "Available", format="%.2f", width="small",
                    help="Calculated: Opening + Adjustment + Received.",
                ),
                "Wastage": st.column_config.NumberColumn(
                    "Wastage", min_value=0, format="%.2f", width="small",
                    help="Spoiled, burnt or discarded. Keeping this separate stops it looking like theft.",
                ),
                "StaffMeal": st.column_config.NumberColumn(
                    "Staff Meal", min_value=0, format="%.2f", width="small",
                    help="Consumed by staff or given as a complimentary.",
                ),
                "Closing": st.column_config.NumberColumn(
                    "Closing", min_value=0, format="%.2f", width="small",
                    help="What you physically counted on the shelf.",
                ),
                "Consumption": st.column_config.NumberColumn(
                    "Consumption", format="%.2f", width="small",
                    help="Calculated, not typed: Available − Wastage − Staff Meal − Closing.",
                ),
                "Remarks": st.column_config.TextColumn("Remarks / Demand", width="medium"),
            },
        )

        # push edits back into session state; everything derived is recomputed from them
        for _, row in edited.iterrows():
            item = row["Item"]
            d = {
                "Opening": parse_num(row["Opening"]), "Adjust": parse_num(row["Adjust"]),
                "Received": parse_num(row["Received"]), "Wastage": parse_num(row["Wastage"]),
                "StaffMeal": parse_num(row["StaffMeal"]), "Closing": parse_num(row["Closing"]),
                "Remarks": row["Remarks"] or "",
            }
            st.session_state.sk_data[item] = d

            available, consumption = compute(d)
            if r3(consumption) < 0:
                impossible_rows.append({"Item": item, "Available": available, "Short by": -consumption})
            if r3(d["Adjust"]) != 0 and not str(d["Remarks"]).strip():
                adjust_no_reason.append({"Item": item, "Adjustment": d["Adjust"]})
            if all(r3(d[k]) == 0 for k in ("Adjust", "Received", "Wastage", "StaffMeal")) and r3(consumption) == 0:
                untouched += 1

save_draft()

# ---------- REVIEW BEFORE SAVING ----------
st.divider()
st.subheader("🔎 Review")

blocking = bool(impossible_rows or adjust_no_reason)

if impossible_rows:
    st.error(
        f"❌ {len(impossible_rows)} item(s) count higher than what was available. That is physically "
        "impossible, so it is either a delivery that was never entered in Received, or a miscount. "
        "Fix these before saving — a wrong closing figure becomes tomorrow's wrong opening."
    )
    st.dataframe(pd.DataFrame(impossible_rows), hide_index=True, use_container_width=True)

if adjust_no_reason:
    st.error(
        f"❌ {len(adjust_no_reason)} item(s) have an Adjustment with no reason in Remarks. "
        "An unexplained adjustment is exactly what this column exists to prevent."
    )
    st.dataframe(pd.DataFrame(adjust_no_reason), hide_index=True, use_container_width=True)

if not blocking:
    st.success("✅ Nothing blocking — the count is arithmetically sound.")

if untouched:
    st.caption(
        f"ℹ️ {untouched} of {len(items)} items show no movement at all today "
        "(nothing received, nothing consumed). Normal for slow-moving stock — worth a second look "
        "if the number is high."
    )

st.divider()

# ---------- SAVE ----------
if st.button("💾 Save Inventory Count", type="primary", use_container_width=True, disabled=blocking):
    saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for cat, item, unit in items:
        d = st.session_state.sk_data[item]
        available, consumption = compute(d)
        rows.append([
            date_str_sheet, cat, item, unit,
            d["Opening"], d["Adjust"], d["Received"], available,
            d["Wastage"], d["StaffMeal"], d["Closing"], consumption,
            d["Remarks"], saved_at,
        ])

    if save_inventory(branch, sheet_type, date_str_sheet, rows):
        st.success(f"Saved {sheet_type} count for {branch} — {date_str_sheet}.")
        try:
            localS.deleteItem(storage_key, key=f"del_{storage_key}")
        except Exception:
            pass
        st.session_state.sk_loaded_for = None
        st.rerun()

if blocking:
    st.caption("Saving is disabled until the errors above are resolved.")
