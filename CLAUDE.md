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
