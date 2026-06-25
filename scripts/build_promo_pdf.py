#!/usr/bin/env python3
"""Build the consumer AT&T fiber promo sheet as a clean one-page PDF (reportlab)."""
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer)

BLUE = colors.HexColor("#0568ae")
CYAN = colors.HexColor("#00a8e0")
ORANGE = colors.HexColor("#d6480b")
LIGHT = colors.HexColor("#f1f7fb")
GREY = colors.HexColor("#7a8794")
LINE = colors.HexColor("#e3e8ee")

OUT = "docs/consumer-fiber-promo-sheet.pdf"

def P(text, **kw):
    st = ParagraphStyle("x", fontName=kw.get("font", "Helvetica"),
                        fontSize=kw.get("size", 10), textColor=kw.get("color", colors.HexColor("#14171a")),
                        leading=kw.get("leading", kw.get("size", 10) + 3),
                        spaceAfter=kw.get("after", 0), spaceBefore=kw.get("before", 0),
                        alignment=kw.get("align", 0))
    return Paragraph(text, st)

def bullet(text):
    return P(f'<font color="#00a8e0"><b>✓</b></font>&nbsp; {text}', size=10, leading=14, after=2)

doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.5*inch, rightMargin=0.5*inch,
                        topMargin=0.45*inch, bottomMargin=0.4*inch)
W = doc.width
story = []

# ---- Header band ----
hdr_inner = [
    [P("AT&T FIBER — HOME INTERNET", font="Helvetica-Bold", size=21, color=colors.white, leading=24)],
    [P("Equal upload &amp; download speeds &middot; WiFi 6 router included &middot; Unlimited data &middot; No annual contract &middot; No price increase for 12 months",
       size=8.5, color=colors.white, leading=11, before=2)],
    [P("\U0001F4DE  Patrick Siado &middot; 832-247-4060&nbsp;&nbsp;|&nbsp;&nbsp; ✉ patrickfiber@att.net",
       font="Helvetica-Bold", size=11, color=colors.white, before=6)],
]
hdr = Table(hdr_inner, colWidths=[W])
hdr.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,-1), BLUE),
    ("LEFTPADDING", (0,0), (-1,-1), 16), ("RIGHTPADDING", (0,0), (-1,-1), 16),
    ("TOPPADDING", (0,0), (0,0), 14), ("BOTTOMPADDING", (0,-1), (-1,-1), 14),
]))
story += [hdr, Spacer(1, 12)]

# ---- Pricing table ----
story.append(P("Plans &amp; Monthly Pricing", font="Helvetica-Bold", size=14, color=BLUE, after=5))
rows = [[P("Speed", font="Helvetica-Bold", size=10, color=BLUE),
         P("Monthly", font="Helvetica-Bold", size=10, color=BLUE),
         P("Best for", font="Helvetica-Bold", size=10, color=BLUE)]]
for sp, pr, bf in [("300 Mbps","$55","Browsing & streaming, 1–3 devices"),
                   ("500 Mbps","$65","Family streaming & work-from-home"),
                   ("1 GIG","$80","Heavy household & gaming"),
                   ("2 GIG","$150","Power users & large homes"),
                   ("5 GIG","$250","Maximum performance")]:
    rows.append([P(sp, size=10), P(pr, font="Helvetica-Bold", size=11, color=BLUE), P(bf, size=10)])
pt = Table(rows, colWidths=[1.4*inch, 1.0*inch, W-2.4*inch])
pt.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), LIGHT),
    ("LINEBELOW", (0,0), (-1,-1), 0.6, LINE),
    ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING", (0,0), (-1,-1), 8),
    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
]))
story += [pt, Spacer(1, 4),
          P('$35/mo with All-in-One &middot; <font color="#d6480b"><b>−20/mo</b></font> when bundled with AT&T wireless.', size=10, after=8)]

# ---- Two columns: Promos | Wireless+Bundle ----
left = [P("\U0001F381 Current Promos", font="Helvetica-Bold", size=13, color=BLUE, after=4)]
for t in ['GIG speeds (1/2/5): save <font color="#d6480b"><b>$30/mo for 12 mo</b></font>',
          '300 Mbps+: save <font color="#d6480b"><b>$15/mo for 12 mo</b></font>',
          '1 GIG: <font color="#d6480b"><b>$200</b></font> reward card',
          '5 GIG: <font color="#d6480b"><b>$200</b></font> Visa reward card',
          '<font color="#d6480b"><b>$100–$200 gift card</b></font> included',
          'Hyperlocal: 1 GIG <font color="#d6480b"><b>~$45/mo</b></font> &middot; 5 GIG <font color="#d6480b"><b>−55/mo</b></font>',
          'Copper→Fiber: 1 GIG+ −10/mo &middot; 5 GIG+ <font color="#d6480b"><b>$100</b></font> card']:
    left.append(bullet(t))

right = [P("\U0001F4F1 Add Wireless &amp; Save", font="Helvetica-Bold", size=13, color=BLUE, after=4)]
for t in ['Choice Switcher (port-in): <font color="#d6480b"><b>$250</b></font> bill credits or reward card',
          'BYOD port-in: <font color="#d6480b"><b>$360 or $180</b></font> bill credits',
          'Waived activation fee']:
    right.append(bullet(t))
right.append(Spacer(1,6))
right.append(P("\U0001F517 Bundle (Wireless + Fiber)", font="Helvetica-Bold", size=13, color=BLUE, after=4))
for t in ['Converged monthly discounts',
          '<b>55+:</b> save <font color="#d6480b"><b>$20/mo per line</b></font>',
          'Select markets: extra wireless line <font color="#d6480b"><b>free</b></font>']:
    right.append(bullet(t))

cols = Table([[left, right]], colWidths=[W/2.0-6, W/2.0-6])
cols.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                          ("LEFTPADDING",(0,0),(0,0),0), ("RIGHTPADDING",(0,0),(0,0),12),
                          ("LEFTPADDING",(1,0),(1,0),12)]))
story += [cols, Spacer(1, 12)]

# ---- CTA band ----
cta = Table([[P("Ready to check your address?", font="Helvetica-Bold", size=16, color=colors.white, align=1)],
             [P("Call or text Patrick — <b>832-247-4060</b> &middot; patrickfiber@att.net", size=12, color=colors.white, align=1, before=3)]],
            colWidths=[W])
cta.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),BLUE),
                         ("TOPPADDING",(0,0),(0,0),12),("BOTTOMPADDING",(0,-1),(-1,-1),12)]))
story += [cta, Spacer(1, 6),
          P("Offers are limited-time and vary by address/market. Ask about your exact availability and promo eligibility. AT&T authorized dealer.",
            size=8, color=GREY, align=1)]

doc.build(story)
print("WROTE", OUT)
