# Project Brain — GHL Connection Map

Operator: Patrick William Siado (AT&T Fiber dealer). This repo IS the "busybee" —
the GoHighLevel MCP Server (834 tools) deployed on Railway.

## Connection status (verified 2026-06-06)

### Frontline Direct — ✅ WORKING
- Location ID: `TXw28sw0Z2rI6tcCDhJY`
- Company ID: `pPN38xtDcG1oUzlklvvv`
- Website: ATTFIBERHOUSTON.COM
- Confirmed live: `get-location` → 200; `search_contacts` → 45,579 contacts; test SMS delivered.
- Reachable via the GHL connectors wired into the session (official GHL + Frontline busybee).
- Read AND write both confirmed.

### Command & Construct — ✅ CONNECTOR ADDED & REACHABLE (live read pending in fresh session)
- Location ID: `xZj500PjsfllQq2j9i9D` (confirm spelling against GHL)
- Busybee deployed on Railway (project `fulfilling-growth` / production), service Online.
- Public domain: `go-high-level-mcp-2026-complete-production-711a.up.railway.app`
- MCP endpoint: `/mcp` (Streamable HTTP; `/sse` legacy). Default start = `node dist/main.js`.
- 2026-06-06: custom connector named `command` added in Claude and HANDSHOOK successfully
  — 444 read-only tools loaded into the connector panel. Transport/connection CONFIRMED.
- STILL PENDING: a live GHL read against `xZj500PjsfllQq2j9i9D` to confirm the busybee's
  token is actually scoped for Command (could 401/403 if scopes are missing). Run it in a
  NEW session where `command` is loaded. Test line: "use the command connector, read
  location xZj500PjsfllQq2j9i9D and give the contact count."
- Connectors load at SESSION START only: `command` will NOT appear in a chat where it was
  added mid-session — open a fresh chat to use it.
- This sandbox blocks direct `railway.app` egress ("Host not in allowlist"), so Command is
  reachable only via the wired `command` MCP connector, not curl.

### Connector name map (per Claude session)
- `command` = Command busybee (Railway, location `xZj500PjsfllQq2j9i9D`)
- `ghl-full` = Frontline busybee (Railway, location `TXw28sw0Z2rI6tcCDhJY`)
- `GH;` = official GHL MCP (`services.leadconnectorhq.com/mcp`, Frontline)

## Important notes
- Connectors are per-session. A connector added mid-session does not appear until a new chat.
- SECRETS: GHL Private Integration token lives in Railway env vars only. Do NOT commit it.
  The `pit-...` token was exposed in screenshots/docs — rotate it in GHL.
- Keep the public busybee URL private; it has no auth — the URL = full account access.

## Outreach guardrails
- Send messages only to consented / opted-in / inbound contacts (forms, replies, YES).
- Cold + DNC-flagged lists: use as door-knock / call routes, not SMS blasts.
- Do not generate randomized message variants to evade carrier spam filters.
- GHL auto-appends opt-out; honor STOP via the existing workflow.

## Lead Intelligence (discovered 2026-06-06 via Frontline busybee)

### Frontline contact database
- 45,579 contacts total (location `TXw28sw0Z2rI6tcCDhJY`).
- Main sales pipeline: `ve4ERf2YoKvuUVQEZb85`. Stages seen:
  - `378c10e3-e9db-4f4b-abbd-4f0eaee101d1` (early — door/CSV-import leads)
  - `d2a32c56-115e-4293-9e3b-5b12fd9ad4bc` (form opt-in leads)
- Lead-intake form ID: `MQwcgmzOAhkOBIJbwO5s` ("Onboarding Info" / Neighborhood Field Sales).
- Custom field IDs in use: `2LYxZCyXOtjiFtnr4pSu`, `AHxP7IMCT54frDP0yDQv`,
  `akU9ECZMcCyGTj2d60v7` (market/city), `wPsXFXwd1JsvTHXUO0mA`.
- Rep user IDs seen on assignments: `7c9QLWsTDyTALTMj0ast`, `X0RyOdp9VYnrdRFQUM1U`.

### Segments observed (by tag/source)
- **Kingsville TX fiber batch** — tags `newfiber rs` + `speedy balandan`, CSV-imported
  2026-06-05; addresses on E Lott / E Kenedy / E Huisache Ave (78363) + Corpus Christi.
  Many carry OPEN opportunities → warm, worth calling.
- **Form opt-ins** — source "Onboarding Info" via form `MQwcgmzOAhkOBIJbwO5s`; custom-tagged
  "Neighborhood Field Sales" + market (e.g., Biloxi MS). These ASKED for contact →
  cleanest segment to text/call (consented).
- **Call-tracking / voice-AI leads** — contacts named after raw phone numbers, tags
  `invalid` / `couldn't find caller name`. High junk rate; many invalid/null numbers.
- **Test/junk** — e.g., "AI Write Test" (`+15555550199`, tags ai-write-test / att-air /
  hot-lead / fiber-eligible / claude-write-confirmed), created by prior AI write tests.
  SHOULD BE CLEANED so it stops polluting the hot-lead/fiber-eligible tags.

### Data-quality flags
- Many records have null phone or invalid numbers (call-tracking artifacts).
- `hot-lead` / `fiber-eligible` tags are polluted by AI test writes — do NOT trust those
  tags for targeting without verifying the contact is real and opted-in.

### Uploaded list: La Porte TX (`a49872fa-6.6.xlsx`) — skip-traced, NOT opt-in
- 319 consumer records (property + phone append), La Porte 77571 area.
- 222 numbers flagged DO NOT CALL; 187 landline/non-wireless.
- 190 contacts reachable on 239 clean (non-DNC wireless) numbers. Carriers: T-Mobile /
  Verizon / AT&T Mobility.
- A DNC-scrubbed import CSV (190 rows, tag `laporte-fiber`) was produced this session.
- This is COLD data with no consent → use as a DOOR-KNOCK / CALL route, not an SMS blast.

### Where the real warm leads are (actionable)
- Open opportunities in pipeline `ve4ERf2YoKvuUVQEZb85` (Kingsville batch + form leads).
- Form opt-ins (source "Onboarding Info") = highest intent and consented → contact first.
- Work these by phone + booking flow, not cold SMS.

## How it works (architecture)
- The busybee = this repo's code (`node dist/main.js`) serving MCP at `/mcp` (Streamable
  HTTP) and `/sse` (legacy). Exposes 834 tools (802 raw API + 32 curated workflows).
- Auth = a single GHL Private Integration token (`pit-...`) sent as `Authorization: Bearer`.
  The token IS the permission set — no per-call login. 401/403 = token missing scopes.
- Each busybee is pinned to ONE sub-account via `GHL_LOCATION_ID`. One Railway service =
  one GHL location. Multi-account = one service per account (current setup), OR an
  agency/Company token with agency scopes + pass locationId per call.
- Tool profiles: `full` (834, default) / `curated` (32) / `raw` (802) via `GHL_TOOL_PROFILE`.
- Two Frontline connectors: `GH;` = GHL official hosted MCP (`services.leadconnectorhq.com/mcp`);
  `ghl-full` = the Railway busybee. Both point at Frontline.
- A dead duplicate `ghl-full` connector ("Failed to start MCP authorization") should be
  deleted — leftover from setup.

## Railway deployment
- Project `fulfilling-growth` / production. Service "Go-High-Level-MCP-2026-Complete"
  (service id `1cba30cf-bf3a-4475-83e1-321c8aa42621`).
- Command public domain: `go-high-level-mcp-2026-complete-production-711a.up.railway.app`
- Env vars: GHL_API_KEY (pit- token, SECRET), GHL_API_VERSION=2021-07-28,
  GHL_BASE_URL=https://services.leadconnectorhq.com, GHL_LOCATION_ID, MCP_SERVER_PORT=8000, NODE_ENV.
- Add a busybee to Claude: Settings → Connectors → Add custom connector → Remote MCP server
  URL = the `…/mcp` domain, no OAuth. Loads at NEXT session start.

## Verification status (be honest in handoffs)
- Frontline: VERIFIED live (get-location 200, 45,579 contacts, SMS delivered).
- Command: connector handshook (tools loaded) = transport OK, but a live GHL read against
  `xZj500PjsfllQq2j9i9D` is NOT yet confirmed. Run "Using command, get the location" to
  prove the token is scoped before trusting Command for sends.

## Operator
- Patrick William Siado, AT&T. Cell / booking number: 832-247-4060.

## Artifacts produced (2026-06-06)
- DNC-scrubbed La Porte CSV: 190 clean wireless contacts, tag `laporte-fiber`
  (door/call route — cold, not for SMS).
- Google Drive handoff doc "AT&T Outreach Bot — Master Handoff & GHL Brain (2026-06-06)"
  (Google Doc id `1p4snumbYz0Cim-gHM55DuL7qz-SdTRexFUxNu3Ualq8`).

## Command outreach playbook (consent-based)
0. Confirm account: "Using command, get the location" → expect xZj500…
1. Pull ONLY consented/warm: form opt-ins (source "Onboarding Info"), open opps in pipeline
   `ve4ERf2YoKvuUVQEZb85`, inbound repliers. Skip dnd / null / `invalid`.
2. Open with a personalized (NOT randomized) message: identify as Patrick w/ AT&T, fiber
   available, 1 Gig in the $40s, 2 months free, free install; ask for a day/time. GHL
   auto-appends opt-out — do not add or strip STOP.
3. Converse & book: confirm address → check eligibility → offer 2 windows → create
   appointment → move opp to booked stage → tag `command-booked` + note.
4. Replies: YES → book + route live to 832-247-4060; STOP → existing workflow scrubs;
   no reply after 1 follow-up → hand to call/door route.
- Guardrails: consented only, no cold/DNC, no filter-evasion variants, throttle, log all.

## Business context, offers & team (from this session + screenshots)

### AT&T offers seen (use in outreach + flyer)
- Fiber: **1 Gig in the $40s, 2 months free, free install, no contract.**
- AT&T Fiber **$35/mo with All in One**.
- Bundle: **~$20/mo discount for AT&T wireless customers**.
- Wireless: **5 unlimited lines $50/mo + the new iPhone 17**.
- Flyer pricing tiers: Hyper-Gig **$150**, **$80**, 300 Mbps **$65**, **$55**; **$100 gift card**.
- Perks: no price changes, WiFi 6 router included, unlimited data for life, no contracts.

### Flyer edit spec (requested in the "at&t payroll" chat)
- Add phone **832-247-4060** + email **patrickfiber@att.net**.
- Remove "no price change at 12 months."
- Change "**$100–$200 Visa**" → "**$100–$200 bill credit**."
- Add "**−$25 off for 12 months**" at the top; "**−20% w/ cell**."
- Keep same format/colors. Check current AT&T new-customer fiber promos before finalizing.

### Numbers / emails on file
- Booking / live hand-off line: **832-247-4060**.
- A sending number seen in test texts: **832-952-0728**.
- Frontline phone on the GHL location: **+18328445183**.
- Emails: **patrickfiber@att.net** / PATRCKFIBER@ATT.NET; account login patricksiado@gmail.com.

### Team & ops (PARTIAL — confirm/expand)
- **Claire / Claire's crew** work leads (e.g., "Mr. Kassow" on Frontline, added ~June 4).
- Roles referenced: **closers + setters**. Payroll/commission audit = AT&T commission sheet
  (closer side) cross-checked against chat activity (setter side).
- Texting tool used outside Claude: **Sales Mate**.
- History: carrier spam blocks / STOP replies / Twilio 30006 from prior cold blasting.

### GAPS — NOT in my possession (paste these to capture them)
- The actual **WhatsApp transcripts**, detailed **payroll/commission numbers**, and the full
  **team roster** are NOT available to me. Paste them into a chat and they can be added here.
