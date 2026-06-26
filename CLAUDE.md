# Project Brain — GHL Connection Map

Operator: Patrick William Siado (AT&T Fiber dealer). This repo IS the "busybee" —
the GoHighLevel MCP Server (834 tools) deployed on Railway.

## Connection status (Frontline verified 2026-06-06; Command verified live 2026-06-26)

### Frontline Direct — ✅ WORKING
- Location ID: `TXw28sw0Z2rI6tcCDhJY`
- Company ID: `pPN38xtDcG1oUzlklvvv`
- Website: ATTFIBERHOUSTON.COM
- Confirmed live: `get-location` → 200; `search_contacts` → 45,579 contacts (2026-06-06),
  grown to **50,191** contacts (re-verified 2026-06-26); test SMS delivered.
- Reachable via the GHL connectors wired into the session (official GHL + Frontline busybee).
- Read AND write both confirmed.

### Command & Construct ("Connect & Comm" / Optimus) — ✅ WORKING (verified live 2026-06-26)
- **Location ID: `xZj500PjsflIQg2j9f9D`** ← capital-`I`, `g`, `f`. This is the REAL id
  (matches the Drive doc "COMMAND - GHL credentials"). The earlier `xZj500PjsfllQq2j9i9D`
  in this brain was a MIS-TRANSCRIPTION (confusable chars `I`↔`l`, `g`↔`q`, `f`↔`i`) and
  always 401/403'd. Confirmed correct because the live read returns this id verbatim.
- Busybee deployed on Railway (project `fulfilling-growth` / production), service Online.
- Public domain: `go-high-level-mcp-2026-complete-production-711a.up.railway.app`
- MCP endpoint: `/mcp` (Streamable HTTP; `/sse` legacy). Default start = `node dist/main.js`.
- 2026-06-26 LIVE READ RESULT: `cmndconevtor` (Command busybee) `search_contacts` → 200,
  **`total: 16,574` contacts**, locationId `xZj500PjsflIQg2j9f9D`. Read CONFIRMED.
- History: 2026-06-06 → 2026-06-26 this returned 401/403 ("token does not have access to
  this location") on every tool. Root cause was the token↔location pair in Command's
  Railway env. Fixed by setting the correct token + correct location id and redeploying.
  Lesson: "Online" on Railway and "99+ tools" on the connector both mean CONNECTED, not
  AUTHORIZED — only a live read returning data proves it works.
- Token resolution (src/main.ts:92-98): request headers `x-ghl-access-token` +
  `x-ghl-location-id` (BOTH together) override; else Railway env `GHL_API_KEY` +
  `GHL_LOCATION_ID`. The server does NOT read `Authorization: Bearer` for GHL auth.
- TEST LINE: "use the command connector, search_contacts and give the contact count."
  A number back (16,574-ish) = live. 401/403 = token/location pair broke again.
- Connectors load at SESSION START only: a connector added mid-session won't appear until
  a fresh chat.

### Connector name map (per Claude session — names rotate; current 2026-06-26)
- `cmndconevtor` (aka `command`) = Command/Optimus busybee (Railway, loc `xZj500PjsflIQg2j9f9D`) ✅
- `ghl-frontline-connector` (aka `ghl-full`) = Frontline busybee (Railway, loc `TXw28sw0Z2rI6tcCDhJY`) ✅
- `ghl_connect` (aka `GH;`) = official GHL MCP (`services.leadconnectorhq.com/mcp`, Frontline) ✅
- NOTE: `apibusybee` is a DIFFERENT product (BusyBee task/project manager) — NOT a GHL busybee.

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

## How Frontline works (the proven template)

The architecture is dead simple — it's one token per account.

Two connectors, both pointed at Frontline (location `TXw28sw0Z2rI6tcCDhJY`):
- `GH;` = GoHighLevel's official hosted MCP server (`services.leadconnectorhq.com/mcp`).
  ~22 read + 14 write tools.
- `ghl-full` = the busybee — the Railway deployment of THIS repo (`node dist/main.js`,
  served at `/mcp`). Exposes the full 834-tool surface.

How it authenticates: there is no login per call. The connector carries a GHL Private
Integration token (`pit-…`) in the `Authorization: Bearer` header. That token IS the
access — whatever the token is allowed to do, the connector can do.

How it knows which account: the busybee is pinned to ONE sub-account via the
`GHL_LOCATION_ID` environment variable in Railway. Frontline's service has
`GHL_LOCATION_ID = TXw28sw0Z2rI6tcCDhJY`. That's why one Railway service = one account.
(This is also why the Frontline busybee returns Frontline data even when you pass a
different `locationId` — the env-pinned location wins.)

Proven working, read + write:
- `get-location` → 200 ("Frontline Direct")
- `search_contacts` → 45,579 contacts
- `send-a-new-message` (SMS) → delivered to a real phone

How to actually use it: just call the GHL tools — `search_contacts`, `get_contact`,
`conversations send-a-new-message`, etc. They automatically act on Frontline because that's
what the token + `GHL_LOCATION_ID` resolve to. No need to pass the location for most calls.

KEY INSIGHT: Command is the exact same thing, cloned. Same repo, same `/mcp` endpoint, same
token-in-header auth. The only differences are (a) a different Railway service with
(b) `GHL_LOCATION_ID = xZj500PjsfllQq2j9i9D` and (c) Command's own `pit-` token. So if
Frontline works, Command works the instant its token has the right scopes — nothing else is
different. (As of 2026-06-06 that token returns 403; see the Command section above.)

## Session log — 2026-06-07 (live diagnosis of Command)

### What was verified live this session
- ✅ **Frontline fully working through BOTH connectors.** `GH;` (official) `locations_get-location`
  → 200 "Frontline Direct". `GH;` `contacts_get-contacts` → `meta.total: 45,579`. `ghl-full`
  (busybee) `search_contacts` → `total: 45,579`. Same location `TXw28sw0Z2rI6tcCDhJY`, identical
  data. Read confirmed on both.
- ❌ **Command STILL FAILS.** Ran the confirmation read ~6 times via `command`: `get_location`,
  `search_contacts`, `get_pipelines`, `get_location_tags`, `get_calendars`, `get_users` — every
  one returns **401** ("Request failed with status code 401") or **403** ("The token does not
  have access to this location"). Tested with BOTH location-ID spellings (see below). Operator
  reported "Online"/"working" in the Railway/connector UI, but the live GHL read is still 401 as
  of 2026-06-07. Connected ≠ authorized.

### Connector → MCP server map this session (UUIDs, in case names rotate)
- `command`  = `40b566b8-36d0-4b4c-92e5-4267cf50ea41` (Command busybee — 833 tools, token 401/403)
- `ghl-full` = `6cf38bf0-772f-4d3e-bad9-0f8955f5ded3` (Frontline busybee — 833 tools, WORKS)
- `GH;`      = `5e0a9e2e-6b99-4950-987a-f64eae3e8d74` (official GHL MCP, Frontline-scoped, WORKS)
- Also wired: Gmail, Google Calendar, Google Drive, Make (Integromat).

### DISCOVERY 1 — "Online" and "99+ tools" do NOT mean it works
Three independent layers; Command passes the first two and fails the third:
1. Railway "Online" = the Node process booted & is serving HTTP. (A bad token still boots fine.)
2. Connector "99+ tools" badge = Claude reached `/mcp` and listed the toolbox. (No ↗ error icon.)
3. Live GHL call = sends the `pit-` token to GoHighLevel → **401**. ← this is the only proof of
   "works", and it's the one failing. The 401 comes back THROUGH the online server FROM GHL
   (a down server would be "connection refused", not 401).

### DISCOVERY 2 — how the busybee actually resolves its token (src/main.ts:92-98)
```
const reqAccessToken = req.headers['x-ghl-access-token'];
const reqLocationId  = req.headers['x-ghl-location-id'];
client = (reqAccessToken && reqLocationId)
  ? new EnhancedGHLClient({...config, accessToken: reqAccessToken, locationId: reqLocationId})
  : ghlClient;  // fallback = Railway env GHL_API_KEY + GHL_LOCATION_ID
```
- Two (and only two) token sources: **(a)** request headers `x-ghl-access-token` + `x-ghl-location-id`
  (BOTH required together), else **(b)** Railway env `GHL_API_KEY` + `GHL_LOCATION_ID`.
- ⚠️ **CORRECTION to the brain:** the busybee does **NOT** read `Authorization: Bearer` for GHL
  auth. Only `x-ghl-access-token`/`x-ghl-location-id` headers or the env vars. If the `command`
  connector was set up in Claude with just an `Authorization: Bearer pit-…` header expecting that
  to pass the token, **it does nothing** — server ignores it and falls back to Railway env.
- `search_contacts`/most tools use the **env-pinned** location and ignore a passed `locationId`
  (proven: passing Command's ID to `ghl-full` still returned Frontline's data). So the Command
  403 "token does not have access to this location" is about the **pair sitting in Railway**, not
  about the ID I pass in. ⇒ The token in Command's Railway `GHL_API_KEY` cannot access the
  location in Command's Railway `GHL_LOCATION_ID`.

### DISCOVERY 3 — the Command location ID has been mis-transcribed (two versions, both fail)
- This brain / earlier handoff: `xZj500PjsfllQq2j9i9D`
- Google Drive doc "COMMAND - GHL credentials (write token + location)": `xZj500PjsflIQg2j9f9D`
- They differ in 3 confusable chars (`l`↔`I`, `q`↔`g`, `i`↔`f`). BOTH return 401/403, so neither
  may be exact. **The real location ID must be copied verbatim from the GHL URL while inside the
  Command & Construct sub-account — stop hand-typing it from screenshots.**

### Command credentials on file (Google Drive — DO NOT commit secrets to git)
- Doc: **"COMMAND - GHL credentials (write token + location)"** (Drive), created 2026-06-06.
- Integration name: `claude-write-command` (doc says ALL scopes incl. WRITE).
- Token: `pit-3cb2e2f7-…-…e750` (full value in the Drive doc + Railway only — kept masked here).
- Companion doc: **"COMMAND SETUP - Claude controls Command (step-by-step)"** (Drive).
- Master brain docs in Drive: "AT&T Outreach Bot — Master Handoff & GHL Brain (2026-06-06)",
  "OPTIMUS BRAIN - Full System Knowledge Base", "OPTIMUS — MASTER BRAIN CONSOLIDATED 2026-05-31".

### Most likely root cause (in priority order) + the fix
1. **Token born in the wrong place.** A `pit-` token is scoped to ONE sub-account; scopes don't
   matter if it was generated at the agency level or in Frontline — it will 401/403 on Command
   forever. ⇒ Generate the token INSIDE the Command & Construct sub-account.
2. **Token revoked/rotated** in GHL but Railway still holds the old value ⇒ 401. Confirm
   `claude-write-command` is still active.
3. **Mismatched/typo'd `GHL_LOCATION_ID`** in Railway (see Discovery 3).
THE FIX: in the **Command & Construct sub-account** → Settings → Private Integrations → create a
fresh token; on that same screen copy BOTH the token AND the exact location ID (no retyping) →
set Railway (Command service) `GHL_API_KEY` + `GHL_LOCATION_ID` to those → redeploy → re-run:
"use the command connector, get the location and tell me the name and ID." A name back
("Connect & Comm" / Command & Construct) = fully live. Still 401 = token is still wrong-account.
