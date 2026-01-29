import streamlit as st
import streamlit.components.v1 as components

def trigger_thermal_print(branch, date_display, cash_sales, cc_tips, expenses, expected_cash):
    """
    Constructs the HTML for the 80mm thermal receipt and triggers the print dialog.
    """
    # 1. Build the individual expense lines
    expenses_html = "".join([
        f"<div style='margin-bottom:10px; line-height:1.2; font-size:15px;'>"
        f"• <b>{e['Category']}</b>: {e['Amount']:,.0f}<br>"
        f"<small style='font-size:13px; color:#555; padding-left:12px;'>{e['Description']}</small></div>" 
        for e in expenses
    ])
    
    # 2. Build the full Receipt Template
    receipt_html = f"""
    <style>
        @media print {{
            body * {{ visibility: hidden; }}
            #receipt-box, #receipt-box * {{ visibility: visible !important; }}
            #receipt-box {{
                position: absolute; left: 0; top: 0;
                width: 75mm !important; display: block !important;
            }}
            @page {{ margin: 0; }}
        }}
    </style>
    <div id="receipt-box" style="background-color:white; color:black; padding:20px; font-family:'Courier New', monospace; border:1px solid #000;">
        <h1 style="text-align:center; margin:0; font-size:28px;">KLAP</h1>
        <p style="text-align:center; margin:5px 0; font-size:16px;"><b>{branch.upper()}</b><br>Date: {date_display}</p>
        <hr style="border-top:1px dashed black;">
        <p style="font-size:16px;">Cash Sale: <span style="float:right;">{cash_sales:,.0f}</span></p>
        
        <p style="margin:10px 0 5px 0; font-weight:bold; font-size:16px;">EXPENSES:</p>
        {expenses_html}
        
        {"<p style='margin:10px 0; font-size:16px;'>CC Tips: <span style='float:right;'>(" + f"{cc_tips:,.0f}" + ")</span></p>" if cc_tips > 0 else ""}
        
        <hr style="border-top:1px dashed black;">
        <div style="text-align:center; margin-top:10px;">
            <p style="margin:0; font-size:14px;">CASH IN HAND</p>
            <h2 style="margin:0; font-size:32px;">{expected_cash:,.0f}</h2>
        </div>
        <p style="text-align:center; font-size:12px; margin-top:20px;">*** End of Report ***</p>
    </div>
    <script>
        setTimeout(function() {{ window.print(); }}, 700);
    </script>
    """
    return components.html(receipt_html, height=0)
