# Project Brain — AT&T Fiber Outreach Operation

Operator: **Patrick William Siado**, AT&T fiber dealer (Frontline Direct / ATTFIBERHOUSTON.COM).
Booking/live line **832-247-4060** · sending # seen **832-952-0728** · email **patrickfiber@att.net**.
This repo IS the "busybee" — a GoHighLevel MCP Server (834 tools) deployed on Railway.

## GHL connections
- **Frontline Direct** — ✅ working (read+write verified). Location `TXw28sw0Z2rI6tcCDhJY`,
  company `pPN38xtDcG1oUzlklvvv`, phone +18328445183. ~45,579 contacts.
- **Command & Construct** — location `xZj500PjsfllQq2j9i9D`. Busybee deployed on Railway
  (project `fulfilling-growth`, domain `go-high-level-mcp-2026-complete-production-711a.up.railway.app`,
  `/mcp` endpoint). Connector "command" added & handshook (444 tools) but a live GHL read
  was never confirmed — verify with "use command, get the location" before trusting it.
- Connector name map: `command` = Command busybee · `ghl-full` = Frontline busybee ·
  `GH;` = official GHL MCP (services.leadconnectorhq.com/mcp, Frontline).
- How it works: one GHL Private Integration token (`pit-…`, in Railway env) per account =
  the access; each busybee pinned to one sub-account via `GHL_LOCATION_ID`. Connectors load
  at session start only. Sandbox blocks direct railway.app egress, so reach via connector.
- SECURITY: rotate the `pit-` token (was exposed in screenshots); keep busybee URL private.

## Pipelines & deal status (Frontline)
- **AT&T Leads** `ve4ERf2YoKvuUVQEZb85`: Lead `d2a32c56…` → Contacted `378c10e3…` →
  Follow-up `596c73c0…` → Closed/Won `148b783f…` → Lost `561d59e9…`.
- **AT&T Commercial** `BZb6jl8rDDeaurYHGZoh`: Leads → DND → Closed/WON `f2522927…` → Closed/LOST.
- **Recruiting** `rAJfLqjRIsUUUjZ7I85T` (hiring, ignore for sales).
- ~**15,600 open opportunities**. Very few closed/won (≈4-6). Lead-intake form `MQwcgmzOAhkOBIJbwO5s`.
- Custom field IDs: 2LYxZCyXOtjiFtnr4pSu, AHxP7IMCT54frDP0yDQv, akU9ECZMcCyGTj2d60v7 (market), wPsXFXwd1JsvTHXUO0mA.

## Lead intelligence (Frontline tags/segments)
- Leads are tagged by the rep who sent them: claire, ara, angela, shiella, maria, mike,
  blessie, faith, ruth, romeo, sean, james, kayla, sheika, nettie, zack, patrick.
- Source/area tags: dates (e.g. 04.10.2026), newfiber rs, speedy balandan, laporte-77571,
  cluteresi, dealmachine, maphunter leads, st-<street> (door routes), type-<industry>.
- Status tags: hot-lead/hot lead, interested, not interested, booked-appt, appt booked,
  sold, deal closed, xsold, invalid, wavv-bad-number, dnd, callback*, voicemail*.
- Data quality: many null/invalid phones; hot-lead/fiber-eligible tags polluted by AI test
  writes — verify before trusting. Test junk e.g. "AI Write Test" (+15555550199) should be cleaned.

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
- Reps on it: Walid Edwards, Regina Saldana, Patricia Munguia (and more).
- Yields **66 unique paid mobile numbers** and **393 unique paid customer names**
  (mostly residential AT&T Internet / Mobility).
- USE: cross-reference new lead lists against this to drop customers already paid out —
  match by MobileNumber (phone) or Customer Name.

## Team (lead-gen / setters / closers)
- **Chrestian Estrera ("Chris")** — sends commercial leads via WhatsApp.
- **Support** group — Chrestian, JL Pedrano, Rea post leads.
- **Rea**, **Michael Angelo Pangilinan** — WhatsApp lead senders.
- **Zack Woodring** ("Zack") — runs/closes deals in the field.
- **Claire** (+ crew) — work/own leads in GHL (e.g. "Mr. Kassow").
- Payroll reps: Walid Edwards, Regina Saldana, Patricia Munguia.

## Offers & flyer
- Fiber: **1 Gig in the $40s, 2 months free, free install, no contract**; AT&T Fiber **$35 All-in-One**.
- Bundle: ~**$20/mo** discount for AT&T wireless customers.
- Wireless: **5 unlimited lines $50/mo + iPhone 17**.
- Flyer tiers: Hyper-Gig $150, $80, 300 Mbps $65, $55; $100 gift card; WiFi 6 router, unlimited data.
- Flyer edits requested: add 832-247-4060 + patrickfiber@att.net; Visa→bill credit;
  −$25/12mo; −20% w/ cell; keep format/colors.

## Tools & misc
- Texting done outside Claude via **Sales Mate**. CRM = GoHighLevel. Hosting = Railway.
- Sending numbers have a history of carrier spam blocks (Twilio 30006) from cold blasting.
