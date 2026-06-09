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
  (Twilio `30006`), no consent trail. NOT usable for consented fiber outreach.
- The 45,579 fiber leads remain in **Frontline**. To use them from Command they must be
  **exported and imported** with DND/DNC/invalid flags preserved (consented subset first).

## 3. Phone setups (verified 2026-06-07)
- **Command** — 3 US local call numbers, account `active`, default **+13466840331**
  ("Patrick's number"); also +13466840217, +13613219339.
- **Frontline** — 21 numbers (TX/AL/AZ/OK/LA/MS) + Voice-AI inbound on several,
  default **+15043996804** ("New Orleans").
- These are voice/call lines. **Outreach is call + door only** (see §5).

## 4. Lead intelligence (Frontline)
- 45,579 contacts. Main pipeline `ve4ERf2YoKvuUVQEZb85` (early stage `378c10e3…`, form opt-in
  stage `d2a32c56…`). Lead form `MQwcgmzOAhkOBIJbwO5s` ("Onboarding Info").
- Segments: Kingsville batch (tags `newfiber rs`/`speedy balandan`, warm), Form opt-ins
  (consented, cleanest), Call-tracking junk (tag `invalid`), AI test junk (clean these).
- Do NOT trust `hot-lead`/`fiber-eligible` tags — polluted by test writes. Many null/invalid #s.
- La Porte upload = 319 skip-traced (222 DNC, 187 landline, 190 clean) → DOOR/CALL only.

## 5. Outreach guardrails (must follow)
- **Channels = phone call + door-knock ONLY.** The consent trail on these lists is unproven, so
  blasting them risks the AT&T dealership — work only consented/own contacts. Owning a list ≠ consent.
- Work Patrick's **own** prior relationships/customers and anyone who opts into **his** outreach.
  Skip dnd/null/invalid/DNC. Honor DNC on call lists; cold + DNC = door route.
- Personalized opener (call/door): Patrick w/ AT&T, fiber available, 1 Gig in the $40s, 2 months
  free, free install, ask for a day/time.
- Converse → confirm address → check eligibility → offer 2 windows → book → move opp to booked
  → tag `command-booked`. Live line **832-247-4060**.

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
  form opt-ins, and CSV imports belong to that team. **Do not migrate, pull, or work Frontline's
  recent leads into or out of Command.** Treat the Frontline 45,579 / recent opt-ins as off-limits.
- Patrick's legitimate audience = his **own** contacts (his prior data) plus anyone who opts in to
  **his** outreach going forward. Recent bulk/CSV/AI-test writes (Wichita auto shops, jeweler/
  realtor B2B scrape, call-tracking junk) are not consented opt-ins regardless of who loaded them.
- **La Porte upload `5181c4eb-6.6.xlsx` (319 rows): SKIP-TRACED, not opt-in.** 184/319 carry a
  DO NOT CALL flag; 135 are clean wireless / non-DNC; every row has at least one wireless line.
  Route = DOOR-KNOCK + manual CALL on the clean non-DNC subset only.
- Workable audience = **Patrick's own** prior relationships/customers and anyone who opts into his
  own outreach — worked by call/door. NOT Frontline's recent form opt-ins (that team's work).

## 9. Offers, flyer & contact points
AT&T offers (from flyer + promo sheet, verified 2026-06-07):
- Fiber flyer pricing (no contract, WiFi 6 router incl., unlimited data, no price change 12 mo):
  5-GIG $250 · 2-GIG $150 · 1-GIG $80 · 500 Mbps $65 · 300 Mbps $55 (per month).
- $35/mo with All in One; **$20/mo bundle discount for AT&T wireless customers**.
- **$100–$200 gift card included.**
- Promo bill credits (AT&T): new Fiber 1/5 GIG → $30/mo × 12; Fiber 300/500 Mbps → $15/mo × 12;
  Fiber 1 GIG → $200 Visa reward card; Fiber 5 GIG → $200 Visa; Hyperlocal 5 GIG → $55/mo;
  Hyperlocal 1 GIG → $45/mo (select zips incl. Houston TX, Dallas-Fort Worth, Atlanta GA).
- Pitch hook stays simple: "1 Gig in the $40s" (the hyperlocal 1-GIG $45/mo bill-credit framing).

Flyer edit spec: swap in Patrick's number + patrickfiber@att.net; Visa → bill credit; −$25/12mo;
−20% with cell line; keep existing format/colors.

Contact points: booking/live line **832-247-4060**; Frontline location line **+18328445183**.

Team/ops (structure only — payroll figures, full roster, and WhatsApp threads NOT in this repo):
Claire's crew works leads (e.g. Mr. Kassow); split into closers + setters; payroll ≈ closer
commission sheet × setter chat activity; tooling includes Sales Mate. Keep PII/financials in a
private doc, not this repo.
