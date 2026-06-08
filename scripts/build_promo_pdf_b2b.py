#!/usr/bin/env python3
"""Build the BUSINESS (NDSb) AT&T fiber + wireless promo sheet as a one-page PDF.
All incentives framed as 'bill credit' (no 'Visa reward card')."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer)

BLUE = colors.HexColor("#0568ae"); CYAN = colors.HexColor("#00a8e0")
ORANGE = colors.HexColor("#d6480b"); LIGHT = colors.HexColor("#f1f7fb")
GREY = colors.HexColor("#7a8794"); LINE = colors.HexColor("#e3e8ee")
OUT = "docs/business-fiber-promo-sheet.pdf"

def P(text, **kw):
    st = ParagraphStyle("x", fontName=kw.get("font","Helvetica"), fontSize=kw.get("size",10),
                        textColor=kw.get("color", colors.HexColor("#14171a")),
                        leading=kw.get("leading", kw.get("size",10)+3),
                        spaceAfter=kw.get("after",0), spaceBefore=kw.get("before",0),
                        alignment=kw.get("align",0))
    return Paragraph(text, st)

def bullet(text):
    return P(f'<font color="#00a8e0"><b>✓</b></font>&nbsp; {text}', size=10, leading=14, after=2)

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5*inch, rightMargin=0.5*inch,
                        topMargin=0.45*inch, bottomMargin=0.4*inch)
W = doc.width; story = []

# Header
hdr = Table([[P("AT&T BUSINESS — FIBER &amp; WIRELESS", font="Helvetica-Bold", size=20, color=colors.white, leading=23)],
             [P("Business-grade fiber &middot; symmetrical speeds &middot; 99.9% reliability &middot; static IP available &middot; no annual contract on select plans",
                size=8.5, color=colors.white, leading=11, before=2)],
             [P("\U0001F4DE  Patrick Siado, AT&T Business &middot; 832-247-4060&nbsp;&nbsp;|&nbsp;&nbsp; ✉ patrickfiber@att.net",
                font="Helvetica-Bold", size=11, color=colors.white, before=6)]], colWidths=[W])
hdr.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),BLUE),("LEFTPADDING",(0,0),(-1,-1),16),
    ("RIGHTPADDING",(0,0),(-1,-1),16),("TOPPADDING",(0,0),(0,0),14),("BOTTOMPADDING",(0,-1),(-1,-1),14)]))
story += [hdr, Spacer(1,12)]

# Business Fiber pricing + bill credit
story.append(P("AT&T Business Fiber (ABF) — Pricing &amp; Bill Credits", font="Helvetica-Bold", size=14, color=BLUE, after=5))
rows = [[P("Speed",font="Helvetica-Bold",size=10,color=BLUE), P("Monthly",font="Helvetica-Bold",size=10,color=BLUE),
         P("New-customer bill credit",font="Helvetica-Bold",size=10,color=BLUE)]]
for sp,pr,bc in [("300 Mbps","$60/mo","$300"),("500 Mbps","$90/mo","$400"),
                 ("1 GIG","$120/mo","$500"),("2 GIG / 5 GIG","Call for pricing","$500")]:
    rows.append([P(sp,size=10), P(pr,font="Helvetica-Bold",size=11,color=BLUE),
                 P(f'<font color="#d6480b"><b>{bc} bill credit</b></font>',size=10)])
pt = Table(rows, colWidths=[1.5*inch,1.5*inch,W-3.0*inch])
pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),LIGHT),("LINEBELOW",(0,0),(-1,-1),0.6,LINE),
    ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),("LEFTPADDING",(0,0),(-1,-1),8),
    ("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
story += [pt, Spacer(1,4),
          P('Bill credit requires new ABF 300Mbps+ &middot; waived installation ($99) &middot; stacks with switcher &amp; All-in-One.', size=10, after=8)]

# Two columns
left = [P("\U0001F381 Fiber Promos", font="Helvetica-Bold", size=13, color=BLUE, after=4)]
for t in ['New ABF (300M+): up to <font color="#d6480b"><b>$500 bill credit</b></font>',
          'Switching providers? Up to <font color="#d6480b"><b>$750 bill credit</b></font> to cover your early-termination fee',
          'Waived installation (<b>$99</b>)',
          'No fiber yet? <b>Internet Air for Business</b>: <font color="#d6480b"><b>$360 bill credit</b></font> + free 5G gateway']:
    left.append(bullet(t))

right = [P("\U0001F4F1 Business Wireless", font="Helvetica-Bold", size=13, color=BLUE, after=4)]
for t in ['Port-in: <font color="#d6480b"><b>$360</b></font> &middot; New line: <font color="#d6480b"><b>$180</b></font> &middot; Private port-in: <font color="#d6480b"><b>$250</b></font> bill credits',
          'BYOD port-in: <font color="#d6480b"><b>$600 bill credit</b></font>',
          'Switcher smartphone reimbursement: up to <font color="#d6480b"><b>$800 bill credit</b></font>',
          'Waived activation fee']:
    right.append(bullet(t))
cols = Table([[left,right]], colWidths=[W/2.0-6, W/2.0-6])
cols.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(0,0),0),
    ("RIGHTPADDING",(0,0),(0,0),12),("LEFTPADDING",(1,0),(1,0),12)]))
story += [cols, Spacer(1,10)]

# Bundle band
story.append(P("\U0001F517 Bundle &amp; Save — All-in-One for Business", font="Helvetica-Bold", size=13, color=BLUE, after=4))
for t in ['<b>Fiber + Wireless:</b> save up to <font color="#d6480b"><b>$50/mo on fiber</b></font> ($50 on 1/2/5 GIG, $40 on 500M, $30 on 300M) <b>OR $30/mo on wireless</b>',
          '<b>ABF + Phone for Business:</b> Unlimited North America <font color="#d6480b"><b>$15/mo per line</b></font> (lines 1–6)',
          '<b>Internet Air / Wireless Broadband + Wireless:</b> save <font color="#d6480b"><b>$20/mo</b></font> on up to 6 lines']:
    story.append(bullet(t))
story.append(Spacer(1,12))

cta = Table([[P("Let's price out your business.", font="Helvetica-Bold", size=16, color=colors.white, align=1)],
             [P("Call or text Patrick — <b>832-247-4060</b> &middot; patrickfiber@att.net", size=12, color=colors.white, align=1, before=3)]], colWidths=[W])
cta.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),BLUE),("TOPPADDING",(0,0),(0,0),12),("BOTTOMPADDING",(0,-1),(-1,-1),12)]))
story += [cta, Spacer(1,6),
          P("Offers are limited-time and vary by address/market; eligibility &amp; terms apply. AT&T authorized dealer.", size=8, color=GREY, align=1)]

doc.build(story)
print("WROTE", OUT)
