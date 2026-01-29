import streamlit.components.v1 as components

def trigger_thermal_print(
    branch,
    date_display,
    cash_sales,
    card_sales,
    fp_sales,
    expenses,
    cc_tips,
    expected_cash,
    closing_code
):
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
                width: 75mm;
            }}
            @page {{ margin: 0; }}
        }}

        #receipt {{
            font-family: Courier New, monospace;
            font-size: 13px;
            padding: 10px;
        }}

        h1 {{ text-align:center; margin:0; }}
        .center {{ text-align:center; margin:4px 0; }}
        .line {{ border-top:1px dashed #000; margin:6px 0; }}
        .row {{ display:flex; justify-content:space-between; }}
        .right {{ text-align:right; }}
        .total {{ font-size:28px; text-align:center; }}
    </style>

    <div id="receipt">
        <h1>KLAP</h1>
        <div class="center">
            <b>{branch.upper()}</b><br>
            {date_display}<br>
            {closing_code}
        </div>

        <div class="line"></div>

        <div class="row"><span>Cash Sale</span><span>{cash_sales:,}</span></div>
        <div class="row"><span>Card Sale</span><span>{card_sales:,}</span></div>
        <div class="row"><span>Foodpanda</span><span>{fp_sales:,}</span></div>

        <div class="line"></div>
        <b>EXPENSES</b><br>
        {expenses_html}

        {f'<div class="row"><span>CC Tips</span><span>({cc_tips:,})</span></div>' if cc_tips else ''}

        <div class="line"></div>
        <div class="center">CASH IN HAND</div>
        <div class="total">{expected_cash:,}</div>

        <div class="center">*** End ***</div>
    </div>

    <script>setTimeout(()=>window.print(),500)</script>
    """

    components.html(receipt_html, height=0)
