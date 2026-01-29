import streamlit.components.v1 as components

def trigger_thermal_print(branch, date_display, cash_sales, card_sales, fp_sales, cc_tips, expenses, expected_cash, closing_code):
    # Formatting expense rows: Description (Left) and Amount (Right)
    # Using a 22-character limit for descriptions to prevent overlap on 80mm paper
    expenses_html = "".join([
        f"""
        <div class="row">
            <div class="left">{e['Description'][:22]}</div>
            <div class="right">({int(e['Amount']):,})</div>
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
                width: 80mm; /* Adjusted for Black Copper BC-85AC */
            }}
            @page {{ margin: 0; size: 80mm auto; }}
        }}

        #receipt {{
            font-family: 'Courier New', Courier, monospace;
            font-size: 14px;
            line-height: 1.4;
            width: 76mm;
            padding: 2mm;
            color: #000;
        }}

        h1 {{ text-align:center; margin:0; font-size: 24px; letter-spacing: 2px; }}
        .center {{ text-align:center; margin:4px 0; }}
        .line {{ border-top:1px dashed #000; margin:10px 0; }}
        
        /* Flexbox for perfect Left/Right alignment */
        .row {{ 
            display: flex; 
            justify-content: space-between; 
            align-items: flex-start;
            margin-bottom: 4px;
        }}
        
        .left {{ text-align: left; flex: 1; }}
        .right {{ text-align: right; min-width: 25mm; font-weight: bold; }}
        
        .total-box {{ 
            border: 2px solid #000; 
            padding: 8px; 
            margin-top: 15px; 
            text-align: center;
        }}
        .total-val {{ font-size: 26px; font-weight: bold; }}
    </style>

    <div id="receipt">
        <h1>KLAP</h1>
        <div class="center">
            <b>{branch.upper()}</b><br>
            {date_display}<br>
            <small>ID: {closing_code}</small>
        </div>

        <div class="line"></div>
        <div class="center"><b>--- REVENUE ---</b></div>
        <div class="row"><span>Cash Sale</span><span class="right">{int(cash_sales):,}</span></div>
        <div class="row"><span>Card Sale</span><span class="right">{int(card_sales):,}</span></div>
        <div class="row"><span>Foodpanda</span><span class="right">{int(fp_sales):,}</span></div>

        <div class="line"></div>
        <div class="center"><b>--- EXPENSES ---</b></div>
        {expenses_html if expenses else '<div class="center">No Expenses Recorded</div>'}
        
        {f'<div class="row"><span>CC Tips</span><span class="right">({int(cc_tips):,})</span></div>' if cc_tips > 0 else ''}

        <div class="line"></div>
        <div class="total-box">
            <div style="font-size: 16px;">CASH IN HAND</div>
            <div class="total-val">Rs. {int(expected_cash):,}</div>
        </div>

        <div class="center" style="margin-top:15px; font-size: 12px;">
            *** End of Report ***<br>
            Thank You for Visiting KLAP
        </div>
    </div>

    <script>
        // Trigger print with a slight delay to ensure CSS loads
        setTimeout(() => {{ 
            window.print(); 
        }}, 800);
    </script>
    """
    components.html(receipt_html, height=0)
