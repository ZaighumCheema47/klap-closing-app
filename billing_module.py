import streamlit as st
import google.generativeai as genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import gspread
import json
import io
import pandas as pd
from datetime import datetime

def run_billing():
    # --- AUTH HELPERS ---
    def get_services():
        from main import get_gcp_creds # Inherit creds from hub
        creds = get_gcp_creds()
        drive = build('drive', 'v3', credentials=creds)
        sheets = build('sheets', 'v4', credentials=creds)
        gs = gspread.authorize(creds)
        return drive, sheets, gs

    drive_service, _, gs_client = get_services()

    # --- VENDOR DATA FROM GSHEETS ---
    def load_vendors_from_sheet(branch):
        sheet_id = st.secrets[f"SPREADSHEET_ID_{branch.replace(' Branch', '').upper()}"]
        doc = gs_client.open_by_key(sheet_id)
        try:
            ws = doc.worksheet("Vendors")
        except gspread.exceptions.WorksheetNotFound:
            ws = doc.add_worksheet(title="Vendors", rows="100", cols="4")
            ws.append_row(["Vendor Name", "Category", "Payment", "Prompt"])
            return {}
        
        records = ws.get_all_records()
        return {r["Vendor Name"]: r for r in records}

    # --- UI RENDER ---
    st.header("🧾 Supply Billing & AI Extraction")
    
    branch = st.selectbox("Select Branch", ["Cantt Branch", "DHA Branch"], key="bill_branch")
    vendors = load_vendors_from_sheet(branch)

    tab1, tab2 = st.tabs(["📝 New Bill", "🛠 Vendor Manager"])

    with tab2:
        st.subheader("Manage Vendor Profiles")
        with st.expander("➕ Add New Vendor"):
            v_name = st.text_input("Business Name")
            v_cat = st.selectbox("Category", ["Beef", "Chicken", "Groceries", "Dairy", "Plastic", "Other"])
            v_pay = st.selectbox("Default Terms", ["Credit", "Cash"])
            v_prompt = st.text_area("AI Context", placeholder="e.g. This is a chicken vendor, weight is in KG.")
            
            if st.button("Save to Google Sheets"):
                sheet_id = st.secrets[f"SPREADSHEET_ID_{branch.replace(' Branch', '').upper()}"]
                ws = gs_client.open_by_key(sheet_id).worksheet("Vendors")
                ws.append_row([v_name, v_cat, v_pay, v_prompt])
                st.success("Vendor added to Master Sheet!")
                st.rerun()

    with tab1:
        if not vendors:
            st.warning("Please add a vendor in the Manager tab first.")
        else:
            v_select = st.selectbox("Select Vendor", list(vendors.keys()))
            selected_v = vendors[v_select]
            
            col1, col2 = st.columns(2)
            date = col1.date_input("Bill Date", datetime.now())
            pay_type = col2.radio("Payment", ["Cash", "Credit"], 
                                  index=0 if selected_v['Payment'] == "Cash" else 1)

            uploaded_file = st.file_uploader("Upload Bill Image", type=['jpg', 'jpeg', 'png'])

            if uploaded_file:
                img_bytes = uploaded_file.read()
                st.image(img_bytes, width=300)

                if st.button("🚀 Process with Gemini AI"):
                    with st.spinner("AI is reading the bill..."):
                        # Gemini Logic here (reuse your previous extract_bill_with_ai function)
                        pass
                        if uploaded_file:
    img_bytes = uploaded_file.read()
    st.image(img_bytes, width=300)

    if st.button("🚀 Process with Gemini AI"):
        with st.spinner("AI is reading the bill..."):
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"Analyze this bill. Vendor: {v_select}. {selected_v['Prompt']}. Return ONLY raw JSON: {{'items': [{{'description': 'name', 'qty': 0, 'rate': 0, 'amount': 0}}], 'grand_total': 0}}"
            
            response = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": img_bytes}])
            st.session_state['current_bill'] = json.loads(response.text.replace('```json', '').replace('```', '').strip())

    if 'current_bill' in st.session_state:
        edited_df = st.data_editor(pd.DataFrame(st.session_state['current_bill']['items']), num_rows="dynamic")
        
        if st.button("✅ Save to Master Sheet"):
            # 1. Access the "Billing" tab in your Branch Master Sheet
            sheet_id = st.secrets[f"SPREADSHEET_ID_{branch.replace(' Branch', '').upper()}"]
            doc = gs_client.open_by_key(sheet_id)
            
            try:
                billing_ws = doc.worksheet("Billing")
            except gspread.exceptions.WorksheetNotFound:
                billing_ws = doc.add_worksheet(title="Billing", rows="100", cols="8")
                billing_ws.append_row(["Date", "Vendor", "Item", "Qty", "Rate", "Amount", "Pay Type", "Drive Link"])

            # 2. Append rows to Billing sheet
            rows_to_save = [[str(date), v_select, r['description'], r['qty'], r['rate'], r['amount'], pay_type, "Link pending"] for _, r in edited_df.iterrows()]
            billing_ws.append_rows(rows_to_save)
            
            st.success("Successfully saved to Billing tab!")
            del st.session_state['current_bill']
