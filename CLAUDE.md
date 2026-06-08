# AT&T Fiber Outreach — GHL Busybee Brain (CLAUDE.md)

> Operator: Patrick William Siado (AT&T Fiber dealer).
> This repo IS the "busybee" — the GoHighLevel MCP server (834 tools) deployed on Railway.
> Companion brain: Google Drive doc "AT&T Outreach Bot — Master Handoff & GHL Brain"
> (id `1p4snumbYz0Cim-gHM55DuL7qz-SdTRexFUxNu3Ualq8`).
> Last verified live: 2026-06-07.

## 1. Accounts & connectors

| Connector | Busybee | Location ID | Company | Notes |
|---|---|---|---|---|
| `command`  | Command & Construct | `xZj500PjsflIQg2j9f9D` | — | Railway `fulfilling-growth/production`, domain `…711a.up.railway.app/mcp` |
| `ghl-full` | Frontline Direct | `TXw28sw0Z2rI6tcCDhJY` | `pPN38xtDcG1oUzlklvvv` | Website ATTFIBERHOUSTON.COM |
| `GH;`      | Official GHL MCP (Frontline) | `TXw28sw0Z2rI6tcCDhJY` | `pPN38xtDcG1oUzlklvvv` | `services.leadconnectorhq.com/mcp`, OAuth |

- One GHL Private Integration token (`pit-…`) per account = the access. Pinned to ONE
  sub-account via `GHL_LOCATION_ID` in Railway env. Connectors load at SESSION START only.

### ⚠️ Corrections verified 2026-06-07 (supersede the Drive doc)
- **Command location ID is `xZj500PjsflIQg2j9f9D`** — the Drive doc's `xZj500PjsfllQq2j9i9D`
  is a transcription error (confused `l`/`I`, `q`/`g`, `i`/`f`). The ID here is what the live
  deployed busybee uses and what GHL accepts.
- **Command is LIVE** (was "pending"): token authenticates — contacts, pipelines, and phone
  numbers all read 200. The ONLY failure is `get_location` → **401**, i.e. the `pit-` token is
  missing the **`View Locations` (locations.readonly)** scope. Add that scope in GHL; no token
  string change needed. Frontline's busybee has the same gap on `get_location`.
- **The `command` connector is currently missing** from Patrick's Claude Connectors list; the
  dead duplicate `ghl-full` (↗ "Failed to start MCP authorization") is still present and should
  be removed. Re-add `command` and restart the session to reload it.

## 2. Migration status (Frontline → Command)
- **Config/pipelines: moved via snapshot.** Command now has pipeline **"AT&T Leads"**
  (`2V9thfxQpuhn6ZP0Peqt`, cloned from Frontline's `ve4ERf2YoKvuUVQEZb85`; stages
  Lead/Contacted/Closed-Won/Lost) plus **"AT&T Commercial"** (`trc5dwodtc1LBYHikmiK`).
- **Contacts: NOT moved.** Snapshots do not carry contacts. Command holds only **4,983**
  contacts, and they are an **old 2026-05-08 CSV scrape of Wichita, KS auto-repair shops**
  (tags `wichita`/`romeo`, `medium: csv_import`) — no names/emails, some landlines
  (Twilio `30006`), no consent trail. NOT usable for a consented fiber SMS campaign.
- The 45,579 fiber leads remain in **Frontline**. To use them from Command they must be
  **exported and imported** with DND/DNC/invalid flags preserved (consented subset first).

## 3. Phone / SMS setups (verified 2026-06-07)
- **Command** — 3 SMS-capable US local numbers, account `active`, default **+13466840331**
  ("Patrick's number"); also +13466840217, +13613219339.
- **Frontline** — 21 SMS-capable numbers (TX/AL/AZ/OK/LA/MS) + Voice-AI inbound on several,
  default **+15043996804** ("New Orleans").
- **A2P 10DLC unconfirmed on both** (`bundleSid: null`). Capability ≠ registration — verify the
  Trust Center shows **Approved** before any volume, or US carriers will filter outbound.

## 4. Lead intelligence (Frontline)
- 45,579 contacts. Main pipeline `ve4ERf2YoKvuUVQEZb85` (early stage `378c10e3…`, form opt-in
  stage `d2a32c56…`). Lead form `MQwcgmzOAhkOBIJbwO5s` ("Onboarding Info").
- Segments: Kingsville batch (tags `newfiber rs`/`speedy balandan`, warm), Form opt-ins
  (consented, cleanest), Call-tracking junk (tag `invalid`), AI test junk (clean these).
- Do NOT trust `hot-lead`/`fiber-eligible` tags — polluted by test writes. Many null/invalid #s.
- La Porte upload = 319 skip-traced (222 DNC, 187 landline, 190 clean) → DOOR/CALL, not SMS.

## 5. Outreach guardrails (must follow)
- Consented/opted-in/inbound contacts ONLY (forms, replies, YES). Skip dnd/null/invalid/DNC.
- Cold + DNC lists = door/call routes, never SMS blasts. No filter-evasion message variants.
- Personalized opener: Patrick w/ AT&T, fiber available, 1 Gig in the $40s, 2 months free,
  free install, ask for a day/time. GHL auto-appends opt-out — do not add/strip STOP.
- Converse → confirm address → check eligibility → offer 2 windows → book → move opp to booked
  → tag `command-booked`. YES routes live to 832-247-4060; STOP scrubs via workflow.
- TCPA: texting DNC/non-consented = $500–$1,500 per message. Throttle and log.
- **No number randomization / sender rotation to evade carrier filters (snowshoeing).** It is a
  10DLC + carrier-policy violation and detection evasion, and risks the AT&T dealership. Drips
  send from a single A2P-registered number to consented contacts only. Owning a list ≠ consent.

## 6. Code / deploy
- Curated lead-finder bug fixed on branch `claude/integration-command-control-opts-ULUBC`:
  `crm_find_unworked_leads`/`crm_contact_workspace` searched contacts via GET (→400) and
  omitted the form-submissions `limit` (→422). Fixed: contact search → POST `{locationId,
  pageLimit}`, form submissions `limit=20`. **Live Railway still runs old code until redeployed.**
- Follow-up agent + recipe added: `examples/agents/customer-follow-up-assistant.md`,
  `examples/recipes/customer-follow-up.json`.

## 7. Security
- Rotate the exposed `pit-` token in GHL (was shown in screenshots/docs). Keep it in Railway
  env only. The public busybee URL has NO auth — URL = full account access. Keep it private.

## 8. Operator context & account custody (added 2026-06-07)
- **Command & Construct is Patrick's** account to run. **Frontline is a separate team's.**
  Patrick will NOT take Frontline work done in the last few months — the recent Frontline leads,
  form opt-ins, and CSV imports belong to that team. **Do not migrate, pull, or text Frontline's
  recent work into or out of Command.** Treat the Frontline 45,579 / recent opt-ins as off-limits.
- Patrick's legitimate audience = his **own** contacts (his prior data) plus anyone who opts in to
  **his** outreach going forward. Recent bulk/CSV/AI-test writes (Wichita auto shops, jeweler/
  realtor B2B scrape, call-tracking junk) are not consented opt-ins regardless of who loaded them.
- **La Porte upload `5181c4eb-6.6.xlsx` (319 rows): SKIP-TRACED, not opt-in.** 184/319 carry a
  DO NOT CALL flag; 135 are clean wireless / non-DNC; every row has at least one wireless line.
  Route = DOOR-KNOCK + manual CALL on the clean non-DNC subset. **Never an SMS drip.**
- Textable audience = **Patrick's own** opt-ins/customers (his prior relationship or people who
  opt in to his own outreach) — from one registered number, throttled, opt-out intact. NOT
  Frontline's recent form opt-ins (that team's work).

## 9. AT&T fiber SMS templates (consent-based)
Source: Patrick's "GHL SMS Outreach Templates" doc
(`1P-x2HmEP3Hk0UwUnR7-0dI3B8Du_2XJN_3_AJXiyZ0k`). Opted-in / inbound / warm only — never cold or
DNC. GHL auto-appends opt-out; do NOT add/strip STOP. Offer baked in: 1 Gig in the $40s · 2
months free · free install · no contract. Booking/live line **832-247-4060**.

- **Opener (form opt-in):** "Hi {{contact.first_name}}, it's Patrick with AT&T — you reached out
  about fiber. Good news, it's available at your address: 1 Gig starting in the $40s, 2 months
  free, free install, no contract. Want me to grab you a quick install window? What day works?"
- **Opener (warm opp):** "Hi {{contact.first_name}}, Patrick with AT&T here — following up on
  AT&T fiber for your place. It's live in your area: 1 Gig in the $40s, 2 months free + free
  install, no contract. Want me to lock in an install time? What day's best?"
- **Confirm address:** "Perfect! Quick check — is {{contact.address1}} the install address? Once
  I confirm it's fiber-ready I'll grab you the next available window."
- **Two windows:** "You're all set — fiber's available there. I've got two openings: {{option_1}}
  or {{option_2}}. Which works better for you?"
- **Confirm appt:** "Done! You're booked for {{appt_date}} at {{appt_time}}. You'll get a
  confirmation + reminder. If anything comes up, text me here or call 832-247-4060."
- **Follow-up (send ONCE, then stop):** "Hi {{contact.first_name}}, Patrick w/ AT&T — just
  circling back on the fiber install. Still want me to hold a spot for you?"

Reply routing: YES/interested → continue booking, hand live calls to 832-247-4060. STOP → existing
STOP workflow scrubs, never re-text. No reply after ONE follow-up → move to call/door, stop texting.
Recipe: `examples/recipes/att-fiber-consented-drip.json`.

## 10. Offers, flyer & contact points
AT&T offers (from flyer + promo sheet, verified 2026-06-07):
- Fiber flyer pricing (no contract, WiFi 6 router incl., unlimited data, no price change 12 mo):
  5-GIG $250 · 2-GIG $150 · 1-GIG $80 · 500 Mbps $65 · 300 Mbps $55 (per month).
- $35/mo with All in One; **$20/mo bundle discount for AT&T wireless customers**.
- **$100–$200 gift card included.**
- Promo bill credits (AT&T): new Fiber 1/5 GIG → $30/mo × 12; Fiber 300/500 Mbps → $15/mo × 12;
  Fiber 1 GIG → $200 Visa reward card; Fiber 5 GIG → $200 Visa; Hyperlocal 5 GIG → $55/mo;
  Hyperlocal 1 GIG → $45/mo (select zips incl. Houston TX, Dallas-Fort Worth, Atlanta GA).
- SMS hook stays simple: "1 Gig in the $40s" (the hyperlocal 1-GIG $45/mo bill-credit framing).

Flyer edit spec: swap in Patrick's number + patrickfiber@att.net; Visa → bill credit; −$25/12mo;
−20% with cell line; keep existing format/colors.

Contact points: booking/live line **832-247-4060**; sending number **832-952-0728** (Frontline
`+18329520728`, "TX number 3"); Frontline location line **+18328445183**.

Team/ops (structure only — payroll figures, full roster, and WhatsApp threads NOT in this repo):
Claire's crew works leads (e.g. Mr. Kassow); split into closers + setters; payroll ≈ closer
commission sheet × setter chat activity; tooling includes Sales Mate. Keep PII/financials in a
private doc, not this repo.
