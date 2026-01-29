import streamlit.components.v1 as components

def trigger_thermal_print(branch, date_display, cash_sales, card_sales, fp_sales, cc_tips, expenses, expected_cash, closing_code):
    # Formatting expense rows
    expenses_html = "".join([
        f"""
        <div class="row">
            <div class="left">{e['Description'][:18].upper()}</div>
            <div class="right">({int(e['Amount']):,})</div>
        </div>
        """
        for e in expenses
    ])

    receipt_html = f"""
    <style>
        /* Force browser to remove all default headers/footers and margins */
        @media print {{
            @page {{ 
                margin: 0; 
                size: 80mm auto; 
            }}
            body {{ 
                margin: 0; 
                padding: 0; 
            }}
            #receipt {{
                visibility: visible !important;
                position: absolute;
                left: 3mm; /* Manual offset to stop left-side cutting */
                top: 0;
            }}
        }}

        #receipt {{
            font-family: 'Arial Black', Gadget, sans-serif;
            width: 68mm; /* Reduced width to stay inside printable track */
            padding: 2mm;
            color: #000;
            background-color: #fff;
            line-height: 1.2;
        }}

        h1 {{ 
            text-align: center; 
            margin: 0; 
            font-size: 28px; 
            font-weight: 900;
            border-bottom: 4px solid #000;
        }}

        .center {{ text-align: center; margin: 2px 0; font-weight: 900; font-size: 14px; }}
        
        .line {{ 
            border-top: 3px dashed #000; 
            margin: 8px 0; 
        }}
        
        .row {{ 
            display: flex; 
            justify-content: space-between; 
            align-items: flex-start;
            margin-bottom: 5px;
            font-size: 15px;
        }}
        
        .left {{ text-align: left; flex: 1; font-weight: 900; }}
        .right {{ text-align: right; min-width: 22mm; font-weight: 900; }}
        
        .total-box {{ 
            border: 4px solid #000; 
            padding: 8px; 
            margin-top: 10px; 
            text-align: center;
        }}
        
        .total-val {{ 
            font-size: 28px; 
            font-weight: 900; 
        }}

        .section-title {{
            text-decoration: underline;
            font-size: 18px;
            display: block;
            text-align: center;
            margin-bottom: 5px;
            font-weight: 900;
        }}
    </style>

    <div id="receipt">
        <h1>KLAP</h1>
        <div class="center">
            <span style="font-size: 18px;">{branch.upper()}</span><br>
            DATE: {date_display}<br>
            ID: {closing_code}
        </div>

        <div class="line"></div>
        <b class="section-title">REVENUE</b>
        <div class="row"><span>CASH SALE</span><span class="right">{int(cash_sales):,}</span></div>
        <div class="row"><span>CARD SALE</span><span class="right">{int(card_sales):,}</span></div>
        <div class="row"><span>FOODPANDA</span><span class="right">{int(fp_sales):,}</span></div>

        <div class="line"></div>
        <b class="section-title">EXPENSES</b>
        {expenses_html if expenses else '<div class="center">NO EXPENSES</div>'}
        
        {f'<div class="row"><span>CC TIPS</span><span class="right">({int(cc_tips):,})</span></div>' if cc_tips > 0 else ''}

        <div class="line"></div>
        <div class="total-box">
            <div style="font-size: 16px;">CASH IN HAND</div>
            <div class="total-val">Rs. {int(expected_cash):,}</div>
        </div>

        <div class="center" style="margin-top:15px; font-size: 12px;">
            *** END OF REPORT ***
        </div>
    </div>

    <script>
        window.onload = function() {{
            setTimeout(() => {{ window.print(); }}, 500);
        }};
    </script>
    """
    components.html(receipt_html, height=0)
