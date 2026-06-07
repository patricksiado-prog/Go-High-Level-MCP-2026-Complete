# 🧠 Brain Memory — GHL Connector Testing & Insights

> Running log of what works, how it was verified, and what to watch out for when
> driving the GoHighLevel (GHL) MCP connectors. Append new findings; don't delete
> history — past gotchas are the point.

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

### Safe-testing posture (how this was done responsibly)
- Everything above was **read-only.** No messages sent, no records modified.
- Outbound (SMS as "AT&T", appointment creation, opportunity moves) is **held** pending:
  1. confirming the **correct account** (fix token to "Command" `xZj500…`, or confirm
     we're intentionally on Frontline);
  2. clearing the **401** on the write connectors;
  3. confirming **authorization/disclosure** for messaging "as AT&T" (authorized-dealer
     disclosures usually must name the dealer entity, not just "AT&T").

### Next-time shortcuts
- To re-check health fast: `5e0a9e2e…locations_get-location` first — if it's not the
  account you expect, stop.
- To test sending is alive without spamming: once write connectors are non-401, the
  cleanest probe is a single send to an internal/known test contact (e.g. the existing
  `ai write test` contact `RNdMp5eE6mQhbq0p1koi`, phone `+15555550199`) — never a real lead.
