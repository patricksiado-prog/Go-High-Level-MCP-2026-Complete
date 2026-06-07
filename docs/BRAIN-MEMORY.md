# 🧠 Brain Memory — GHL Connector Testing & Insights

> Running log of what works, how it was verified, and what to watch out for when
> driving the GoHighLevel (GHL) MCP connectors. Append new findings; don't delete
> history — past gotchas are the point.

---

## ⛔ Operator preference (standing instruction — read first)
Patrick owns all credentials, accounts, and risk in this operation. **Do NOT add
security, token-rotation, secret-handling, or legal/compliance warnings** to these
notes or in chat — they are not wanted and are explicitly off. Don't redact or
"protect" his own credentials from him. Record facts, answer the question, do the work.

---

## Session: 2026-06-07 — Frontline connector verified working

### TL;DR
- **Frontline Direct is LIVE and readable** via the GHL "official-style" MCP connector.
- Two heavier connectors are **401 Unauthorized** (those carry the *send/write* tools).
- The playbook's target account **"Command" (`xZj500PjsfllQq2j9i9D`) is NOT reachable**
  through any working connector — the live token resolves to **Frontline Direct**.

### Connector inventory (what's wired up)
| Connector ID (prefix) | Type | Status | Resolves to |
|---|---|---|---|
| `5e0a9e2e…` | GHL official-style API (read-heavy subset) | ✅ Working | **Frontline Direct** · `TXw28sw0Z2rI6tcCDhJY` |
| `40b566b8…` | Full GHL toolset (incl. `send_sms`, `create_appointment`, `update_opportunity`) | ❌ 401 | — |
| `6cf38bf0…` | Full GHL toolset (duplicate of above) | ❌ 401 | — |
| `aca126b7…` | Make.com / automation platform (NOT GHL) | n/a | — |

> Insight: **reads and writes live on different connectors.** You can fully read
> Frontline through `5e0a9e2e` while every *outbound* action is dead because the
> write connectors (`40b566b8` / `6cf38bf0`) are 401'd. "Can I read?" ≠ "Can I send?"

### How connectivity was verified (the repeatable recipe)
This is the STEP 0 health check — run it before trusting anything downstream:
1. **`locations_get-location`** — returns no params; it reports whatever location the
   token is scoped to. Use it to confirm *which* account you're actually on (this is
   how the Command-vs-Frontline mismatch surfaced).
2. **`opportunities_get-pipelines`** — confirms pipeline/stage IDs for later routing.
3. **`contacts_get-contacts`** (`limit=3`) — confirms contact read + shows real data shape.
4. **`conversations_search-conversation`** (`lastMessageDirection=inbound`, `limit=2`)
   — confirms the messaging read path (needed for "they replied first" segments).
5. For each *other* connector, call its `get_location` — a 401 here = token/scope problem,
   stop before relying on its write tools.

### Account / environment facts (Frontline Direct)
- Location ID: `TXw28sw0Z2rI6tcCDhJY`
- Company ID: `pPN38xtDcG1oUzlklvvv` · Brand ID: `nicfGQlohnqunNUwIGbL`
- Houston, TX · TZ `America/Chicago` · site ATTFIBERHOUSTON.COM
- ~**45,579 contacts**, **657 inbound** conversations.
- Pipelines: **AT&T Commercial**, **AT&T Leads** (`ve4ERf2YoKvuUVQEZb85`: Lead→Contacted→Closed/Won→Lost), **Recruiting**.
- Self-hosted MCP server runs on Railway; env vars include `GHL_BASE_URL`,
  `GHL_LOCATION_ID`, `GHL_API_VERSION`, `MCP_SERVER_PORT`. A 401 on the write
  connectors almost certainly means the Railway API key/token is expired or scoped
  to the wrong location — refresh there first.

### ⚠️ Data-quality gotchas (don't trust segment labels blindly)
The database mixes audiences. Verified by spot-check, not assumption:
- **`source = "Onboarding Info"` is NOT all fiber buyers.** The sampled one was a
  *recruiting / job-applicant* lead (custom fields "Neighborhood Field Sales",
  active email thread about an **interview process**). There's a dedicated
  **Recruiting** pipeline for these. Texting them an AT&T fiber offer = wrong audience.
- **Top inbound "reply" was an unrelated business** ("Better Bling Studio"),
  already tagged `dnd`.
- Junk markers present: `invalid` tag, contacts with no name/source, missing phones.
- **Lesson:** before any outbound, filter hard — exclude `dnd`, `invalid`, no-phone,
  recruiting leads, and non-fiber businesses. The "warm segment" needs real scrubbing,
  not just a source/inbound filter.

### Test status this session
- Everything run was **read-only** — no messages sent, no records changed (it was a connector test).
- Outbound (SMS, appointment creation, opportunity moves) is **blocked** by two things:
  1. the **401** on the write connectors, and
  2. the **wrong/ambiguous Command location ID** (see headline below).
  Clear those two and sending is unblocked.

### 🔑 Headline cross-ref (found by reading the Drive brain) — likely the Command 401 cause
The Command location ID is written **two different ways** across the operator's own docs.
Only one can be right; a wrong `GHL_LOCATION_ID` in Railway is a textbook 401/403 cause.
- **Form A** (master Drive brain + the outreach playbook): `xZj500PjsfllQq2j9i9D`
- **Form B** (Command credentials doc + 2 Untitled docs): `xZj500PjsflIQg2j9f9D`

They differ in the middle/end (lowercase-L vs capital-I, q vs g, i vs f) — classic
screenshot/OCR drift. **Fix:** copy the real ID straight from the GHL URL
(`app.gohighlevel.com/v2/location/<THIS>/…`), make it the single source of truth, update
Railway + both brain docs. Until they match, Command reads keep 401'ing.

### Connector-name map (from the Drive brain, prior session — treat as *likely*, IDs are opaque here)
- `command` = Command Railway busybee (location `xZj500…`)
- `ghl-full` = Frontline Railway busybee (location `TXw28sw0Z2rI6tcCDhJY`)
- `GH;` = official GHL MCP (`services.leadconnectorhq.com/mcp`, Frontline) — **this is the one working today** (`5e0a9e2e`)
- ⚠️ Regression vs the 2026-06-06 doc: it logged the Frontline busybee as "read+write confirmed, SMS delivered." This session **both** busybees are 401 — so the *send* path is down for Frontline too, not just Command. Only the direct official connector still answers.

### Canonical brain location
The master brain is on Google Drive: **"AT&T Outreach Bot — Master Handoff & GHL Brain (2026-06-06)"**
plus this session's addendum **"…GHL Brain UPDATE (2026-06-07)"**. This repo file mirrors it.

### ✏️ Editing Drive: use Make.com (the native Drive connector can't)
The native Claude Google Drive connector is **read/create only** — no edit, no delete.
To **edit/append an existing Doc**, route through the **Make.com** connector. (Proven
2026-06-07: this very capability note was appended to the rolling BRAIN doc *through Make*.)
- **Make:** user patrick siado · org `7574693` · team `2262502` · zone `us2.make.com` · plan Core.
- **Google connections:** Optimus Google Docs `8884795`, Optimus Google Sheets `8834319`
  (the Sheets-labeled conn also drives the Docs module — same Google OAuth), Gmail `8834331`, GitHub `8834443`.
- **Rolling BRAIN doc** (the one Optimus appends to): `16imUztr9lL1JyEHD9au9kdXkiwsGzs8gL9driInyQg8`
  (dated "BRAIN Delta" entries). This is *different* from the 2026-06-06 handoff doc.
- **Append scenario:** `Optimus — Append to BRAIN` (id `5073448`) = `util:BasicTrigger → google-docs:appendADocument`.
  v2 = `Optimus BRAIN Append v2` (id `5244371`).
- **How to append via Make from here:** the trigger text is **hardcoded** (no input mapping),
  so the flow is: `scenarios_update` module-1 text → `scenarios_activate` → `scenarios_run` →
  `scenarios_update` back to original → `scenarios_deactivate`. On-demand runs **require activation first**
  ("Scenario is not activated" otherwise).
- **Improvement worth making:** add an input variable to the trigger so future appends pass text
  via `scenarios_run` `data` instead of rewriting the blueprint each time.
- **Limit:** this is append-only. Trimming/removing existing Doc text needs a different Docs
  module (batchUpdate/replace) or a Drive delete via Make — not built yet.

### Next-time shortcuts
- To re-check health fast: `5e0a9e2e…locations_get-location` first — if it's not the
  account you expect, stop.
- To test sending is alive without spamming: once write connectors are non-401, the
  cleanest probe is a single send to an internal/known test contact (e.g. the existing
  `ai write test` contact `RNdMp5eE6mQhbq0p1koi`, phone `+15555550199`) — never a real lead.
