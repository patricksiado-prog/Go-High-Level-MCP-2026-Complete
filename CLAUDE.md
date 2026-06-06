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

### Command & Construct — ⚠️ DEPLOYED, NOT ALWAYS CONNECTED
- Location ID: `xZj500PjsfllQq2j9i9D` (confirm spelling against GHL)
- Busybee deployed on Railway (project `fulfilling-growth` / production), service Online.
- Public domain: `go-high-level-mcp-2026-complete-production-711a.up.railway.app`
- MCP endpoint: `/mcp` (Streamable HTTP; `/sse` legacy). Default start = `node dist/main.js`.
- To USE it in a chat: add `https://...-711a.up.railway.app/mcp` as a connector, then
  START A NEW SESSION (connectors load at session start). It already works in sessions
  where that connector is added.
- NOTE: this sandbox blocks direct `railway.app` egress ("Host not in allowlist"),
  so Command must be reached via a wired MCP connector, not curl.

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
