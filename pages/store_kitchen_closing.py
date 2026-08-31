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
st.set_page_config(page_title="KLAP Store & Kitchen Closing", layout="centered", initial_sidebar_state="collapsed")

# The count is done on a phone, walking the kitchen one shelf at a time — so the
# entry screen is built for a thumb, not for a spreadsheet. Tighter page padding,
# larger number fields, and no tiny +/- steppers to mis-tap on a small screen.
st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        [data-testid="collapsedControl"] { display: none; }

        .block-container { padding-top: 2.5rem; padding-bottom: 4rem; }

        input[type="number"] { font-size: 1.05rem !important; font-weight: 600; }

        @media (max-width: 640px) {
            .block-container { padding-left: 0.75rem; padding-right: 0.75rem; }
            [data-testid="stNumberInputStepUp"],
            [data-testid="stNumberInputStepDown"] { display: none; }
            h1 { font-size: 1.5rem !important; }
        }
    </style>
""", unsafe_allow_html=True)

# ---------- GOOGLE SHEETS CORE ----------

@st.cache_resource(show_spinner=False)
def get_gspread_client():
    """Cached so the service-account handshake happens once per session, not on
    every rerun — Streamlit reruns the whole script on each keystroke."""
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

def parse_opt(val):
    """Like parse_num, but keeps 'not counted yet' distinct from a counted zero.
    A blank closing must never silently save as 0 — that reads as 'we used the lot'."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def r3(val):
    """Rounds before comparing — raw float math leaves dust like 0.1 + 0.2 != 0.3,
    which would otherwise flag perfectly clean rows as impossible."""
    return round(float(val), 3)

def fmt(val):
    """Trims trailing zeros so 12.0 reads as '12' but 2.25 keeps its precision."""
    if val is None:
        return "—"
    return f"{float(val):g}"

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

    Because nobody can type Consumption, it cannot be plugged to make the day
    look tidy. Returns (available, None) while the item is still uncounted."""
    available = d["Opening"] + d["Adjust"] + d["Received"]
    if d["Closing"] is None:
        return available, None
    return available, available - d["Wastage"] - d["StaffMeal"] - d["Closing"]

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

    # Header drift check costs nothing here — row 1 is already in hand.
    if values[0] != HEADER:
        if len(values) <= 1:
            with_backoff(ws.update, range_name="A1", values=[HEADER])
        else:
            st.warning(
                "⚠️ This worksheet was written by an older version of this page and its columns "
                f"no longer match. Rename or archive the existing "
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
    """Upserts the counted rows for this date (deletes any existing rows for it first)."""
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

# ---------- HEADER / SELECTION ----------

st.title("📦 Daily Stock Count")

with st.expander("⚙️ Branch, sheet & date", expanded=not st.session_state.get("sk_started")):
    branch = st.selectbox("Branch", list(BRANCH_CONFIG.keys()))
    sheet_type = st.radio("Count sheet", list(SHEET_TYPES.keys()), horizontal=True)
    date_selected = st.date_input("Closing date", datetime.today())

date_str_sheet = date_selected.strftime("%m/%d/%Y")

# ---------- BRANCH PIN GATE (shared with Daily Closing) ----------
if st.session_state.get("unlocked_branch") != branch:
    st.subheader(f"🔒 Enter PIN for {branch}")
    pin_entry = st.text_input("4-digit Branch PIN", max_chars=4, key="sk_pin_entry", help="Numbers only")
    if st.button("Unlock", use_container_width=True):
        correct_pin = st.secrets.get("branch_pins", {}).get(branch)
        if correct_pin and pin_entry == str(correct_pin):
            st.session_state.unlocked_branch = branch
            st.session_state.sk_started = True
            st.rerun()
        else:
            st.error("Incorrect PIN.")
    st.stop()

st.session_state.sk_started = True

cfg = SHEET_TYPES[sheet_type]
items = cfg["items"]
categories = list(dict.fromkeys(cat for cat, _, _ in items))
items_by_cat = {c: [(i, u) for cc, i, u in items if cc == c] for c in categories}

# ---------- LOAD / DRAFT STATE ----------
localS = LocalStorage(key="klap_sk_storage")
selection_key = f"{branch}|{sheet_type}|{date_selected.strftime('%d%m%y')}"
storage_key = f"sk_draft_v3_{selection_key}"

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
                "StaffMeal": parse_num(src.get("StaffMeal")), "Closing": parse_opt(src.get("Closing")),
                "Remarks": src.get("Remarks", "") or "",
            }
        else:
            data[item] = {
                "Opening": parse_num(prev_closing.get(item, 0)), "Adjust": 0.0, "Received": 0.0,
                "Wastage": 0.0, "StaffMeal": 0.0, "Closing": None, "Remarks": "",
            }

    st.session_state.sk_data = data
    st.session_state.sk_seed_mode = not has_history
    st.session_state.sk_loaded_for = selection_key
    st.session_state.sk_cat = categories[0]

    if existing:
        st.info(f"↩️ Loaded the saved count for {date_str_sheet}.")
    elif prev_closing:
        st.info("↩️ Opening stock carried forward from the previous count.")

seed_mode = st.session_state.get("sk_seed_mode", False)
data = st.session_state.sk_data

def save_draft():
    try:
        localS.setItem(storage_key, json.dumps(data), key=f"set_{storage_key}")
    except Exception:
        pass

# ---------- PROGRESS ----------
counted_items = [i for _, i, _ in items if data[i]["Closing"] is not None]
total_items = len(items)
done = len(counted_items)

st.caption(f"**{branch}** · {sheet_type} · {date_str_sheet}")
st.progress(done / total_items if total_items else 0.0, text=f"{done} of {total_items} items counted")

if seed_mode:
    st.warning(
        "🌱 **Opening balance** — no earlier count exists, so this is your baseline. "
        "Count each item and enter what is physically on the shelf right now. "
        "Every future day carries forward from these numbers, so take your time."
    )

# ---------- VIEW SWITCH ----------
view = st.radio(
    "View", ["📱 Count", "📋 Review & Save"], horizontal=True, label_visibility="collapsed"
)

# ================= COUNT VIEW (one category at a time) =================
if view == "📱 Count":

    def cat_label(c):
        picked = items_by_cat[c]
        n_done = sum(1 for i, _ in picked if data[i]["Closing"] is not None)
        mark = "✅" if n_done == len(picked) else ("🟡" if n_done else "⬜")
        return f"{mark} {c} — {n_done}/{len(picked)}"

    current = st.session_state.get("sk_cat", categories[0])
    if current not in categories:
        current = categories[0]

    chosen = st.selectbox(
        "Section", categories, index=categories.index(current),
        format_func=cat_label, key="sk_cat_picker",
    )
    if chosen != current:
        st.session_state.sk_cat = chosen
        current = chosen

    st.divider()

    for item, unit in items_by_cat[current]:
        d = data[item]
        available, consumption = compute(d)

        with st.container(border=True):
            head_l, head_r = st.columns([3, 1])
            head_l.markdown(f"**{item}**")
            head_r.markdown(
                f"<div style='text-align:right;opacity:.6;padding-top:.15rem'>{unit}</div>",
                unsafe_allow_html=True,
            )

            if seed_mode:
                # Baseline day: one number per item, nothing else to ask for.
                val = st.number_input(
                    "Stock on hand now", value=d["Closing"], min_value=0.0, step=1.0,
                    format="%.2f", key=f"seed_{item}", placeholder="Enter count",
                )
                d["Opening"] = parse_num(val)
                d["Closing"] = parse_opt(val)
                d["Adjust"] = d["Received"] = d["Wastage"] = d["StaffMeal"] = 0.0
            else:
                st.caption(f"Opening **{fmt(d['Opening'])}**  ·  Available **{fmt(available)}** {unit}")

                in_col, close_col = st.columns(2)
                d["Received"] = parse_num(in_col.number_input(
                    cfg["in_label"], value=d["Received"], min_value=0.0, step=1.0,
                    format="%.2f", key=f"rec_{item}",
                ))
                d["Closing"] = parse_opt(close_col.number_input(
                    "Closing count", value=d["Closing"], min_value=0.0, step=1.0,
                    format="%.2f", key=f"cls_{item}", placeholder="Count",
                ))

                with st.expander("Wastage · staff meal · adjustment · remarks"):
                    w_col, s_col = st.columns(2)
                    d["Wastage"] = parse_num(w_col.number_input(
                        "Wastage", value=d["Wastage"], min_value=0.0, step=1.0,
                        format="%.2f", key=f"wst_{item}",
                        help="Spoiled, burnt or discarded — kept separate so it doesn't look like theft.",
                    ))
                    d["StaffMeal"] = parse_num(s_col.number_input(
                        "Staff meal", value=d["StaffMeal"], min_value=0.0, step=1.0,
                        format="%.2f", key=f"stf_{item}",
                        help="Eaten by staff or given as a complimentary.",
                    ))
                    d["Adjust"] = parse_num(st.number_input(
                        "Adjustment (+/-)", value=d["Adjust"], step=1.0, format="%.2f",
                        key=f"adj_{item}",
                        help="Correction to opening stock. A reason in Remarks is required.",
                    ))
                    d["Remarks"] = st.text_input(
                        "Remarks / demand", value=d["Remarks"], key=f"rmk_{item}",
                    )

                available, consumption = compute(d)
                if consumption is None:
                    st.caption("Consumption — *not counted yet*")
                elif r3(consumption) < 0:
                    st.error(f"Counted {fmt(d['Closing'])} but only {fmt(available)} was available.")
                else:
                    st.caption(f"Consumption **{fmt(consumption)}** {unit}")

    save_draft()

    st.divider()
    idx = categories.index(current)
    prev_col, next_col = st.columns(2)
    if prev_col.button("◀ Previous", use_container_width=True, disabled=idx == 0):
        st.session_state.sk_cat = categories[idx - 1]
        st.rerun()
    if next_col.button("Next ▶", use_container_width=True, disabled=idx == len(categories) - 1):
        st.session_state.sk_cat = categories[idx + 1]
        st.rerun()

    if idx == len(categories) - 1:
        st.caption("Last section — switch to **📋 Review & Save** when you're done.")

# ================= REVIEW & SAVE =================
else:
    impossible_rows, adjust_no_reason, table = [], [], []

    for cat, item, unit in items:
        d = data[item]
        available, consumption = compute(d)
        if consumption is not None and r3(consumption) < 0:
            impossible_rows.append({"Item": item, "Available": available, "Counted": d["Closing"]})
        if r3(d["Adjust"]) != 0 and not str(d["Remarks"]).strip():
            adjust_no_reason.append({"Item": item, "Adjustment": d["Adjust"]})
        table.append({
            "": "✅" if d["Closing"] is not None else "⬜",
            "Item": item, "Unit": unit,
            "Opening": d["Opening"], "Recv": d["Received"], "Waste": d["Wastage"],
            "Staff": d["StaffMeal"], "Closing": d["Closing"], "Used": consumption,
            "Remarks": d["Remarks"],
        })

    blocking = bool(impossible_rows or adjust_no_reason) or done == 0

    if impossible_rows:
        st.error(
            f"❌ {len(impossible_rows)} item(s) were counted higher than what was available — "
            "physically impossible. Either a delivery was never entered in "
            f"**{cfg['in_label']}**, or it's a miscount. Fix these first: a wrong closing "
            "becomes tomorrow's wrong opening."
        )
        st.dataframe(pd.DataFrame(impossible_rows), hide_index=True, use_container_width=True)

    if adjust_no_reason:
        st.error(
            f"❌ {len(adjust_no_reason)} item(s) have an adjustment with no reason in Remarks. "
            "An unexplained adjustment is exactly what that field exists to prevent."
        )
        st.dataframe(pd.DataFrame(adjust_no_reason), hide_index=True, use_container_width=True)

    if done < total_items:
        st.info(
            f"ℹ️ {total_items - done} item(s) not counted. Only counted items are saved — "
            "their opening will carry forward from the last day they *were* counted, so a "
            "partial count is safe."
        )

    if not blocking:
        st.success(f"✅ {done} item(s) ready to save — the count is arithmetically sound.")
    elif done == 0:
        st.warning("Nothing counted yet.")

    with st.expander(f"Full sheet ({total_items} items)"):
        st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)

    st.divider()

    if st.button("💾 Save Stock Count", type="primary", use_container_width=True, disabled=blocking):
        saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for cat, item, unit in items:
            d = data[item]
            if d["Closing"] is None:
                continue  # never invent a count that nobody took
            available, consumption = compute(d)
            rows.append([
                date_str_sheet, cat, item, unit,
                d["Opening"], d["Adjust"], d["Received"], available,
                d["Wastage"], d["StaffMeal"], d["Closing"], consumption,
                d["Remarks"], saved_at,
            ])

        if save_inventory(branch, sheet_type, date_str_sheet, rows):
            st.success(f"Saved {len(rows)} item(s) for {branch} — {date_str_sheet}.")
            try:
                localS.deleteItem(storage_key, key=f"del_{storage_key}")
            except Exception:
                pass
            st.session_state.sk_loaded_for = None
            st.rerun()

    if blocking and done:
        st.caption("Saving is disabled until the errors above are resolved.")
