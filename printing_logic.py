import streamlit.components.v1 as components

def trigger_thermal_print(
    branch,
    date_display,
    cash_sales,
    card_sales,
    fp_sales,
    cc_tips,
    expenses,
    expected_cash,
    closing_code
):
    # Formatting each expense row: Description (Left), Amount (Right)
    expenses_html = "".join([
        f"""
        <div class="row">
            <div class="left">{e['Description']}</div>
            <div class="right">({e['Amount']:,})</div>
        </div>
        """
        for e in expenses
    ])

    receipt_html = f"""
    <style>
        @media print {{
            body * {{ visibility: hidden; }}
            #receipt, #receipt * {{ visibility: visible; }}
            #receipt {{
                position: absolute;
                left: 0;
                top: 0;
                width: 72mm; /* Standard Thermal Width */
            }}
            @page {{ margin: 0; }}
        }}

        #receipt {{
            font-family: 'Courier New', Courier, monospace;
            font-size: 14px;
            padding: 5px;
            color: #000;
        }}

        h1 {{ text-align:center; margin:0; font-size: 22px; }}
        .center {{ text-align:center; margin:2px 0; }}
        .line {{ border-top:1px dashed #000; margin:8px 0; }}
        .row {{ display:flex; justify-content:space-between; align-items: flex-start; margin-bottom: 2px; }}
        .left {{ text-align: left; flex: 1; padding-right: 5px; }}
        .right {{ text-align: right; white-space: nowrap; }}
        .total-box {{ border: 1px solid #000; padding: 5px; margin-top: 10px; }}
        .total-val {{ font-size:24px; text-align:center; font-weight: bold; }}
    </style>

    <div id="receipt">
        <h1>KLAP</h1>
        <div class="center">
            <b>{branch.upper()}</b><br>
            {date_display}<br>
            <small>ID: {closing_code}</small>
        </div>

        <div class="line"></div>
        <div class="center"><b>REVENUE</b></div>
        <div class="row"><span>Cash Sale</span><span>{cash_sales:,}</span></div>
        <div class="row"><span>Card Sale</span><span>{card_sales:,}</span></div>
        <div class="row"><span>Foodpanda</span><span>{fp_sales:,}</span></div>

        <div class="line"></div>
        <div class="center"><b>EXPENSES</b></div>
        {expenses_html if expenses else '<div class="center">No Expenses</div>'}

        {f'<div class="row"><span>CC Tips</span><span>({cc_tips:,})</span></div>' if cc_tips > 0 else ''}

        <div class="line"></div>
        <div class="total-box">
            <div class="center">CASH IN HAND</div>
            <div class="total-val">Rs. {int(expected_cash):,}</div>
        </div>

        <div class="center" style="margin-top:10px;">*** Thank You ***</div>
    </div>

    <script>setTimeout(()=>{{ window.print(); }}, 500);</script>
    """
    components.html(receipt_html, height=0)
