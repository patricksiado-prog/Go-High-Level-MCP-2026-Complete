# BRAIN-MEMORY

Repo mirror of the operating brain for this MCP deployment. Source of truth is the
Google Doc **"AT&T Outreach Bot — GHL Brain UPDATE (2026-06-07) v2 — CLEAN"**; this file
is the in-repo copy that doc refers to. Keep them in sync.

> Supersedes the earlier "...GHL Brain UPDATE (2026-06-07)" doc.
> Addendum to "Master Handoff & GHL Brain (2026-06-06)".

## Operator preference — standing instruction (read first)

Patrick owns all credentials, accounts, and risk in this operation. Do not add
security, token-rotation, secret-handling, or legal/compliance warnings to these notes
or in chat — explicitly off. Do not redact or "protect" Patrick's own credentials from
him. Record facts, answer the question, do the work.

## 0. Headline — likely root cause of the Command 401/403

The Command location ID is written **two different ways** across the docs. Only one can be
correct, and a wrong `GHL_LOCATION_ID` in Railway causes 401/403.

- Form A (master brain doc + outreach playbook): `xZj500PjsfllQq2j9i9D`
- Form B (COMMAND credentials doc + 2 Untitled docs): `xZj500PjsflIQg2j9f9D`

Differences are in the middle/end (lowercase `l` vs capital `I`, `q` vs `g`, `i` vs `f`) —
screenshot/OCR transcription drift.

**ACTION:** open the Command sub-account in GHL, copy the location ID straight from the URL
(`app.gohighlevel.com/v2/location/THIS-PART/...`). That exact string is the source of truth.
Set it in Railway (`GHL_LOCATION_ID`) and in the master brain doc. Until both match the real
ID, Command reads keep failing.

## 1. Connection status — verified live 2026-06-07

**Frontline Direct** — READ CONFIRMED via the official GHL connector (direct to
`leadconnectorhq.com`, not the Railway busybee):

- `get-location` -> 200, "Frontline Direct", location `TXw28sw0Z2rI6tcCDhJY`
- `get-pipelines` -> 200 (AT&T Commercial, AT&T Leads, Recruiting)
- `get-contacts` -> 200, 45,579 contacts
- `search-conversation` (inbound) -> 200, 657 inbound threads
- custom fields -> 200

**The two Railway "busybee" connectors** (full toolset: `send_sms` / `create_appointment` /
`update_opportunity`) — BOTH returned 401 on `get_location`. Outbound is currently DOWN for
both accounts, not just Command.

- Command is NOT live yet (401 on the one live read attempt).
- The Frontline busybee write path also appears regressed — only the direct official-GHL
  connector still answers. Likely token expired/rotated, Railway service down, or wrong
  `GHL_LOCATION_ID`.

**Working today:** reading Frontline (official connector).
**Not working today:** any send/write (both busybees 401); any Command read (401).

## 2. Deployment map (from Railway, 2026-06-07)

- Railway service **Go-High-Level-MCP-2026-Complete** = the **Frontline** busybee.
  - Public URL: `https://go-high-level-mcp-2026-complete-production-46d1up.railway.app`
  - MCP endpoint: `.../mcp` (Streamable HTTP). Target port 8080.
  - `GHL_API_KEY` is a Private Integration Token (`pit-...`); `GHL_LOCATION_ID` = Frontline.
  - Claude connector that uses it: **`ghl-full`** (connects, lists 414 read-only tools).
  - Auto-deploys from the **`main`** branch.
- A second Railway service (`...711a.../mcp`, brain noted port 8086) = the **Command** busybee.
  - Claude connector that uses it: **`command`** (currently "Couldn't connect").

Reminder: a GHL Private Integration Token is created **inside one sub-account** and only works
for that sub-account's location. The Command service needs a PIT generated in the Command
sub-account + Command's real location ID; the Frontline service needs a Frontline PIT +
`TXw28sw0Z2rI6tcCDhJY`. A token from one sub-account paired with the other's location = 401.

## 3. Health check (run first, every session)

1. Official/Frontline connector: `get-location` (no params) -> confirms WHICH account the
   token resolves to. (The live token here resolves to Frontline, never Command.)
2. `get-pipelines` -> confirm pipeline/stage IDs.
3. `get-contacts` (limit 3) -> confirm read + see data shape.
4. `search-conversation` (lastMessageDirection=inbound, limit 2) -> confirm message read path.
5. For each OTHER connector: call its `get_location`. 401 = token/scope/location problem.

For the Railway busybees specifically, hit `GET /readyz` on each service URL — it runs a live
`GET /locations/{GHL_LOCATION_ID}` and reports 200 ready / 503 with the real error.

## 4. Insights / gotchas

- **Reads and writes live on different connectors.** The official connector reads Frontline
  fine while every send tool (on the busybees) is 401. "Can I read?" does NOT mean "Can I
  send?" — test sending separately before trusting it.
- **Segment labels are not clean.** On Frontline a `source="Onboarding Info"` contact was
  actually a recruiting/job-applicant lead (custom field "Neighborhood Field Sales", live
  email thread about an interview) — there's a dedicated Recruiting pipeline for these. The
  top inbound "reply" was an unrelated business ("Better Bling Studio") tagged dnd. Before
  outbound: filter out dnd, invalid, no-phone, recruiting leads, non-fiber orgs.
- **Junk persists:** the "AI Write Test" contact (`+15555550199`, id `RNdMp5eE6mQhbq0p1koi`)
  is still in the DB tagged hot-lead/fiber-eligible — use IT as the send-test target, not a
  real lead.

## 5. Next actions (in order)

1. Get the REAL Command location ID from the GHL URL; reconcile Form A vs Form B above.
2. Fix Railway `GHL_LOCATION_ID` + token for Command; redeploy; confirm "Online".
3. Re-run the health check on the Command connector -> expect `get_location` 200 + count.
4. Diagnose the Frontline busybee 401 so SEND works again (regenerate Frontline PIT).
5. Build/send the consented outreach — opt-ins + inbound + open opps, scrubbed.

## 5b. CONFIRMED WORKING — Command connector live (2026-06-07 ~07:25)

Command Railway box (`…711a…/mcp`, connector `cmndconevtor`) + new token `pit-896044c7-5384-4abf-965b-2721598706b2`
(all 146 scopes) → tested live:
- `get_location(xZj500PjsflIQg2j9f9D)` -> 200, name **"T-OPTIMUS"** (Optimus Fiber, optimus-fiber.com, Houston TX)
- `search_contacts(limit 1)` -> 200, **total 13,173 contacts**
Full 834-tool control is live on Command. The fix was a freshly-created, fully-scoped token.

### NAMING CORRECTION (this caused the whole 403 saga — pin it)
- **Command** = **"T-OPTIMUS"** (Optimus Fiber) = `xZj500PjsflIQg2j9f9D`
- **Frontline** = **"Frontline Direct"** (ATT Fiber Houston) = `TXw28sw0Z2rI6tcCDhJY`
- The name **"Optimus" belongs to COMMAND (`xZj500…`), NOT Frontline.** A prior agent advised
  putting a `TXw28…` ("Optimus Houston") token in the Command box — that is BACKWARDS and would
  point Command at Frontline. Command's token must be made inside `xZj500…` (T-OPTIMUS).

## 6. Multi-account control via per-request HEADERS (the clean fix, 2026-06-07)

THE KEY MECHANISM. The Railway MCP server (`src/main.ts`, the `/mcp` Streamable-HTTP
handler) accepts **per-request credential headers** that OVERRIDE the baked-in env token
and location:

- `x-ghl-access-token` — the GHL Private Integration Token to use for this request
- `x-ghl-location-id`  — the location (sub-account) to act on

CORS already allows both headers. Logic: if BOTH headers are present, the server builds a
client from them; if absent, it falls back to env `GHL_API_KEY` / `GHL_LOCATION_ID`.

```js
const reqAccessToken = req.headers['x-ghl-access-token'];
const reqLocationId  = req.headers['x-ghl-location-id'];
const client = reqAccessToken && reqLocationId
  ? new EnhancedGHLClient({ ...config, accessToken: reqAccessToken, locationId: reqLocationId })
  : ghlClient; // env fallback
```

IMPLICATION: **ONE Railway box serves BOTH accounts.** Each connector hits the same `/mcp`
URL but sends its OWN token+location headers. The env token no longer has to match the
target account — the headers decide. This is the fix that was remembered as "connect each
one with different headers."

Exact header pairs (token + location MUST be a matched pair from the SAME sub-account):

- Command:
  - `x-ghl-access-token: pit-896044c7-5384-4abf-965b-2721598706b2`  (token "883", all 146 scopes, created 2026-06-07)
  - `x-ghl-location-id:  xZj500PjsflIQg2j9f9D`
- Frontline / Optimus Houston:
  - `x-ghl-access-token: <a Frontline PIT generated inside TXw28sw0Z2rI6tcCDhJY>`
  - `x-ghl-location-id:  TXw28sw0Z2rI6tcCDhJY`

RULE that fixes the **"403 token does not have access to this location"**: the
`x-ghl-access-token` and `x-ghl-location-id` MUST belong to the SAME sub-account. That 403
= a crossed pair (token from account A used with account B's location). Do not mix
`xZj500…` and `TXw28…`.

Account IDs (ground truth):
- Command sub-account:           `xZj500PjsflIQg2j9f9D`
- Frontline / Optimus Houston:   `TXw28sw0Z2rI6tcCDhJY` ("Frontline Direct", ATT Fiber Houston)
  (NOTE: "Optimus Houston" = Frontline = TXw28…; it is NOT Command. Don't put a Frontline
  token in the Command box.)

Railway boxes (both deploy from `main`, run `npm start` = `node dist/main.js`, serve `/mcp`):
- Command box:   `https://go-high-level-mcp-2026-complete-production-711a.up.railway.app/mcp`
- Frontline box: `https://go-high-level-mcp-2026-complete-production-46d1.up.railway.app/mcp`

Caveat: sending these headers requires an MCP client that supports custom headers (the
connector's Advanced/Headers config — NOT OAuth). Claude's basic custom-connector dialog
shows only URL + OAuth Client ID/Secret; set the headers wherever the connector config
allows them.

Reliable fallback for READS: the official GHL MCP connector (`https://services.leadconnectorhq.com/mcp/`,
22 tools, OAuth login, one location per connector) — verified live returning Frontline data
and pipelines. Has `conversations: send-a-new-message`, contacts create/update/upsert,
opportunities update — enough for a basic sales agent, but only ~22 tools (no full automation
set). One connector per URL (Claude de-dupes), so it can't cover both accounts at once.

## 7. Writing AUTOMATIONS — TWO DIFFERENT AUTH PATHS (CORRECTED 2026-06-07)

⚠️ CORRECTION of an earlier wrong claim ("both can write automations, no Railway changes").
`get_location` working on a box proves ONLY that the PIT (`GHL_API_KEY`) is valid. It does
NOT mean `ghl_create_workflow` works — that's a completely different code path and auth.

Confirmed live this session:
- Command → `ghl_create_workflow` → ✅ draft created (id `72e7bdbc…`, "AI — New Lead Intro").
- Frontline → `ghl_create_workflow` → ❌ "Firebase token refresh failed (400): INVALID_REFRESH_TOKEN".

WHY: `ghl_create_workflow` (and update/delete/publish/clone) use the hidden internal workflow
API `backend.leadconnectorhq.com/workflow`, authed by refreshing a Firebase / v2-JWT token —
NOT the PIT. From `src/clients/workflow-builder-client.ts` `fromEnv()`:
- `GHL_REFRESH_TOKEN` (or `GHL_AUTH_REFRESH_TOKEN`) — v2 JWT, preferred
- `GHL_FIREBASE_REFRESH_TOKEN` + `GHL_FIREBASE_API_KEY` — Firebase fallback
- `GHL_USER_ID`, `GHL_COMPANY_ID`
- `locationId` comes from **`GHL_LOCATION_ID` (env), NOT the `x-ghl-location-id` header**.

So:
- Command's box HAS a valid refresh token → workflow-create works.
- Frontline's box LACKS one (or it's expired) → INVALID_REFRESH_TOKEN.
- **Fix for Frontline workflows = put a valid Frontline-account refresh token (`GHL_REFRESH_TOKEN`)
  + `GHL_USER_ID` on the 46d1 box.** This IS a Railway change. (PIT-only tools — contacts,
  conversations, opportunities, send_sms, etc. — already work on both with no change.)

🚨 SILENT-WRONG-ACCOUNT TRAP: because the workflow client uses env `GHL_LOCATION_ID` (ignores the
header), a `ghl_create_workflow` "success" lands in whatever account that BOX is configured for.
If the Frontline connector is ever pointed at Command's 711a box, the workflow silently builds in
Command (`xZj500…`), not Frontline. ALWAYS read the created workflow back and verify its
`locationId` before trusting it.

VERIFY checklist before claiming "automations work" on an account:
1. Actually call `ghl_create_workflow` (NOT `get_location`).
2. If it succeeds, read it back and confirm `locationId` matches the intended account.

---

PIT-token path (these DO work on both boxes, no Railway change — verified `get_location` 200 each):

| Sub-account | Connector | Railway box | Location ID |
|---|---|---|---|
| Command = T-OPTIMUS (Optimus Fiber) | `cmndconevtor` | `…-711a.up.railway.app/mcp` | `xZj500PjsflIQg2j9f9D` |
| Frontline = Frontline Direct (ATT Fiber Houston) | `ghl-frontline-connector` | `…-46d1.up.railway.app/mcp` | `TXw28sw0Z2rI6tcCDhJY` |

To create an automation, call `ghl_create_workflow` on the matching connector:
- `name` (required)
- `trigger`: `{ type, name, data }` — types: `contact_tag` (data `{tagName, tagEvent}`),
  `contact_created`, `form_submission`, `customer_reply`, `appointment`, `inbound_webhook`,
  `payment_received`
- `actions`: `[{ type, name, attributes }]` — types: `sms`, `email`, `add_contact_tag`, `wait`,
  `if_else`, `webhook`, `create_opportunity`, `custom_code`
- `publish`: `false` -> creates a DRAFT (nothing fires until published)

Same call, twice — once per connector. Each box is bound to its own account's token + location,
so it writes to the right sub-account automatically. (The server also supports per-request headers
`x-ghl-access-token` + `x-ghl-location-id` for one-box-both-accounts; matched pair required —
see Section 6.)
