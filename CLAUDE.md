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

### Command & Construct — 🟡 CONNECTED, BUT TOKEN SCOPE BROKEN (token fix needed)
- Location ID: `xZj500PjsfllQq2j9i9D` (confirm spelling against GHL)
- Busybee deployed on Railway (project `fulfilling-growth` / production), service Online.
- Public domain: `go-high-level-mcp-2026-complete-production-711a.up.railway.app`
- MCP endpoint: `/mcp` (Streamable HTTP; `/sse` legacy). Default start = `node dist/main.js`.
- 2026-06-06: custom connector named `command` added in Claude and HANDSHOOK successfully
  — 444 tools loaded. Transport/connection CONFIRMED.
- 2026-06-06 LIVE READ RESULT: the confirmation read was run via the `command` connector.
  `search_contacts` returned **`403 — The token does not have access to this location`**,
  both when targeting `xZj500PjsfllQq2j9i9D` and with no location filter at all. So the
  connection is fine; the `pit-` token configured in Command's Railway service is NOT
  authorized for the Command sub-account (or any location). This is the "fix token scopes"
  branch, not a connection problem.
- FIX (do alongside the required rotation): in GHL **inside the Command & Construct
  sub-account** (not agency, not Frontline) → Settings → Private Integrations → create a
  fresh `pit-` token with at least `contacts.readonly` (add write scopes as needed) →
  update `GHL_API_KEY`/token env var in Command's Railway service → redeploy → re-run the
  test line below. A number back = Command is fully live.
- TEST LINE (run in a NEW session where `command` is loaded): "use the command connector,
  read location `xZj500PjsfllQq2j9i9D` and give the contact count."
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
