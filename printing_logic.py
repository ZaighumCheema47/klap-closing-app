import streamlit.components.v1 as components

def trigger_thermal_print(branch, date_display, cash_sales, card_sales, fp_sales, cc_tips, expenses, expected_cash, closing_code):
    # Formatting expense rows with maximum thickness
    expenses_html = "".join([
        f"""
        <div class="row">
            <div class="left">{e['Description'][:20].upper()}</div>
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
                width: 80mm;
            }}
            @page {{ margin: 0; size: 80mm auto; }}
        }}

        #receipt {{
            /* Using a thick-stroke Sans-Serif font for better thermal 'burn' */
            font-family: 'Arial Black', 'Arial', sans-serif;
            font-size: 15px; 
            font-weight: 900; /* Maximum thickness */
            line-height: 1.3;
            width: 74mm;
            padding: 2mm;
            color: #000000;
            -webkit-print-color-adjust: exact;
        }}

        h1 {{ 
            text-align:center; 
            margin:0; 
            font-size: 32px; 
            font-weight: 900;
            border-bottom: 3px solid #000;
            margin-bottom: 5px;
        }}

        .center {{ text-align:center; margin:4px 0; font-weight: 900; }}
        
        /* Thicker dashed line */
        .line {{ 
            border-top: 3px dashed #000; 
            margin: 12px 0; 
        }}
        
        .row {{ 
            display: flex; 
            justify-content: space-between; 
            align-items: flex-start;
            margin-bottom: 6px;
        }}
        
        .left {{ text-align: left; flex: 1; letter-spacing: 0.5px; }}
        .right {{ text-align: right; min-width: 25mm; }}
        
        /* High-Visibility Box for Cash in Hand */
        .total-box {{ 
            border: 4px solid #000; 
            padding: 10px; 
            margin-top: 15px; 
            text-align: center;
        }}
        .total-val {{ 
            font-size: 30px; 
            font-weight: 900; 
        }}

        .section-title {{
            text-decoration: underline;
            font-size: 18px;
            margin-bottom: 8px;
            display: block;
            text-align: center;
        }}
    </style>

    <div id="receipt">
        <h1>KLAP</h1>
        <div class="center">
            <span style="font-size: 20px;">{branch.upper()}</span><br>
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
            <div style="font-size: 18px; letter-spacing: 1px;">CASH IN HAND</div>
            <div class="total-val">Rs. {int(expected_cash):,}</div>
        </div>

        <div class="center" style="margin-top:20px; font-size: 14px;">
            *** END OF REPORT ***
        </div>
    </div>

    <script>
        setTimeout(() => {{ 
            window.print(); 
        }}, 800);
    </script>
    """
    components.html(receipt_html, height=0)
