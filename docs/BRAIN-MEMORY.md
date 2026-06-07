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
