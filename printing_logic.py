import streamlit.components.v1 as components

def trigger_thermal_print(branch, date_display, cash_sales, cc_tips, expenses, expected_cash):

    # Expense rows: description LEFT, amount RIGHT
    expenses_html = "".join([
        f"""
        <div class="row">
            <div class="left">{e['Description']}</div>
            <div class="right">({int(e['Amount']):,})</div>
        </div>
        """
        for e in expenses
    ])

    receipt_html = f"""
    <style>
        @media print {{
            body * {{ visibility: hidden; }}
            #receipt-box, #receipt-box * {{ visibility: visible !important; }}
            #receipt-box {{
                position: absolute;
                left: 0;
                top: 0;
                width: 75mm;
                margin: 0;
                padding: 0;
            }}
            @page {{ margin: 0; }}
        }}

        #receipt-box {{
            font-family: 'Courier New', monospace;
            font-size: 14px;
            padding: 12px;
            color: #000;
        }}

        h1 {{
            text-align: center;
            font-size: 26px;
            margin: 0;
        }}

        .center {{
            text-align: center;
            margin: 6px 0;
        }}

        .line {{
            border-top: 1px dashed #000;
            margin: 8px 0;
        }}

        .row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 4px;
        }}

        .left {{
            width: 70%;
            text-align: left;
            word-wrap: break-word;
        }}

        .right {{
            width: 30%;
            text-align: right;
            white-space: nowrap;
        }}

        .total {{
            text-align: center;
            font-size: 30px;
            margin-top: 4px;
        }}
    </style>

    <div id="receipt-box">
        <h1>KLAP</h1>
        <div class="center">
            <b>{branch.upper()}</b><br>
            Date: {date_display}
        </div>

        <div class="line"></div>

        <div class="row">
            <div class="left">Cash Sale</div>
            <div class="right">{int(cash_sales):,}</div>
        </div>

        <div class="line"></div>

        <b>EXPENSES</b><br><br>
        {expenses_html}

        {f"""
        <div class="row">
            <div class="left">CC Tips</div>
            <div class="right">({int(cc_tips):,})</div>
        </div>
        """ if cc_tips > 0 else ""}

        <div class="line"></div>

        <div class="center">CASH IN HAND</div>
        <div class="total">{int(expected_cash):,}</div>

        <div class="center" style="margin-top:12px; font-size:11px;">
            *** End of Report ***
        </div>
    </div>

    <script>
        setTimeout(function() {{ window.print(); }}, 500);
    </script>
    """

    components.html(receipt_html, height=0)
