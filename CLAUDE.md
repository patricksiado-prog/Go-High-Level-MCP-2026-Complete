# Project Brain — Data Assets

## Master leads list (678 leads — paid/payroll removed)
- File: `Leads.xlsx`. Columns: **Name, Phone, Address, Type, Notes**.
- **217 COMMERCIAL** — from WhatsApp chats with the lead-gen team: Chrestian Estrera
  ("Chris"), the Support group, Rea, and Michael Angelo Pangilinan. Notes hold the owner
  spoken to, current carrier to beat, pain point, and best time to visit.
- **461 RESIDENTIAL** — La Porte "Opted-In Leads Final" (Name, Address, Phone, carrier).
- Built by merging all sources, deduping by phone (744 raw -> 678), and removing the
  4 GHL Closed/Won + payroll matches.
- WhatsApp leads are NOT tagged in GHL — that's why they don't appear under a rep tag.
- Drive index: https://docs.google.com/document/d/1u5UtS8kaQ9X7KVIJqKT9kpkggNXPckESPuGkeYpevSo/edit

## Payroll / commission sheet (already-paid customers)
- Google Sheet: https://docs.google.com/spreadsheets/d/1UoqH7I4Gt8MCNa2yYR4ZsksriOOQeLMcaZY6XHrdeqY/edit
- **1,118 commission rows.** Columns: SalesRep, ATTUID, Dealer Code, AccountNumber,
  Customer ID, MobileNumber, Customer Name, Service, Doc Date, Doc Number, Paid, Reserve, Total.
- Reps on it include: Walid Edwards, Regina Saldana, Patricia Munguia (and more).
- Yields **66 unique paid mobile numbers** and **393 unique paid customer names**
  (mostly residential AT&T Internet / Mobility).
- USE: cross-reference new lead lists against this to drop customers already paid out —
  match by MobileNumber (phone) or Customer Name.
