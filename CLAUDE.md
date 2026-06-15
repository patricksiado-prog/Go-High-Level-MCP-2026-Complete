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

### Corrections verified 2026-06-07 (supersede the Drive doc)
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
  (Twilio `30006`), no consent trail. NOT usable for a consented fiber SMS campaign.
- The 45,579 fiber leads remain in **Frontline**. To use them from Command they must be
  **exported and imported** with DND/DNC/invalid flags preserved (consented subset first).

## 3. Phone / SMS setups (re-verified 2026-06-12)
- **Command** — 4 SMS-capable US local numbers, account `active`, default **+13466840331**
  ("Patrick's number"); also +13466840217 ("LILITHA"), +13613219339 ("SHIKA"),
  +12819035606 ("Patrick's number 2", added 6/11).
- **Frontline** — 22 SMS-capable numbers (TX/AL/AZ/OK/LA/MS + one toll-free 833) + Voice-AI
  inbound on several, default **+15043996804** ("New Orleans").
- **A2P 10DLC: APPROVED on both** — operator confirmed 2026-06-12. (`bundleSid: null` in the
  numbers API is NOT an A2P signal; A2P campaign status lives at the Twilio messaging-service
  level.) 2026-06-12 two-way line test: all 22 Frontline lines delivered into Command except
  the **toll-free +18337567333** (no answer received — likely needs toll-free verification).
- **Command's "Auto AI SMS Reply" workflow is live** — it auto-answers inbound SMS on
  Patrick's number (asks for service address, routes to 832-247-4060). Mind AI↔AI loops when
  texting between the two accounts; Frontline has a workflow that auto-DNDs unknown inbounds.
- Line-test artifacts tagged `sms-line-test` (22 contacts in Command, 1 in Frontline) — safe
  to bulk-delete.

## 4. Lead intelligence (Frontline)
- 45,579 contacts. Main pipeline `ve4ERf2YoKvuUVQEZb85` (early stage `378c10e3…`, form opt-in
  stage `d2a32c56…`). Lead form `MQwcgmzOAhkOBIJbwO5s` ("Onboarding Info").
- Segments: Kingsville batch (tags `newfiber rs`/`speedy balandan`, warm), Form opt-ins
  (consented, cleanest), Call-tracking junk (tag `invalid`), AI test junk (clean these).
- The `hot-lead`/`fiber-eligible` tags are polluted by test writes — treat them as unreliable.
  Many null/invalid numbers.
- La Porte upload = 319 skip-traced (222 DNC, 187 landline, 190 clean) → door/call route.

## 5. Outreach playbook
- SMS audience: consented / opted-in / inbound contacts (forms, replies, YES). Skip
  dnd/null/invalid/DNC. Cold and DNC lists are door/call routes, not SMS.
- Opener: Patrick w/ AT&T, fiber available, 1 Gig in the $40s, 2 months free, free install,
  ask for a day/time. GHL auto-appends opt-out — don't add or strip STOP.
- Flow: converse → confirm address → check eligibility → offer 2 windows → book → move opp to
  booked → tag `command-booked`. YES routes live to 832-247-4060; STOP scrubs via workflow.
- Send from one A2P-registered number, throttled and logged. (Single number + consented list is
  both the deliverable setup and what keeps the AT&T dealership clean; owning a list ≠ consent.)

## 6. Code / deploy
- Curated lead-finder bug fixed on branch `claude/integration-command-control-opts-ULUBC`:
  `crm_find_unworked_leads`/`crm_contact_workspace` searched contacts via GET (→400) and
  omitted the form-submissions `limit` (→422). Fixed: contact search → POST `{locationId,
  pageLimit}`, form submissions `limit=20`. **Live Railway still runs old code until redeployed.**
- Follow-up agent + recipe added: `examples/agents/customer-follow-up-assistant.md`,
  `examples/recipes/customer-follow-up.json`.
- **Optimus map toolkit** (`/optimus`, branch `claude/optimus-map-tools-setup-6dcl6o`):
  precise_fiber_hunter (clicks every dot / Mapbox geo fast path / `--fresh` new-zone mode),
  enrich_phones (free OSM first → paid Places only on miss, cached, `--watch`), business_score,
  ghl_loader (→ AT&T Commercial + power-dialer workflow). Installer + GitHub updater on Drive
  ("Optimus Installer"). Skills: optimus-fiber, project-tracker, map-control. Status board:
  `PROJECT_STATUS.md`.
- **AT&T fiber map — live-confirmed 2026-06-13:** renders in-page at
  `youachieve.att.com/yourefer/fiber`; fresh load = portal, map is behind a "Fiber Availability
  Map" button (`open_map_view()` clicks it). The automated Chromium shows the **dots but not the
  basemap tiles** — normal, the hunter only needs dots. Login saved once via `--login` into
  `att_profile/`. Popup = `FIBER ELIGIBLE / Address: … / CREATE REFERRAL`.
- **Dots are MAPBOX VECTOR TILES (x-protobuf), not JSON** (confirmed live 2026-06-14 via
  `--net-debug` → `net_responses.log`). So `--net` JSON capture returned 0 and fell back to
  clicking. Fix shipped: `NetCapture` now also pulls protobuf tile bodies and decodes them
  (`decode_vector_tile`, needs `mapbox-vector-tile`), converting each dot's tile-local point to
  exact lng/lat (web-mercator). `--net-debug` prints the tile's property field names so the
  address-bearing key can be pinned. If a tile carries only geometry (no street text), the
  click/popup path still fills the address.
- **UPDATE ARCHITECTURE (efficient self-update — do NOT make Patrick reinstall).** Three layers,
  all auto-pulling from GitHub branch `claude/optimus-map-tools-setup-6dcl6o`:
  1. `precise_fiber_hunter.py` runs `self_update()` at the top of `main()` every launch — `git
     pull`, and re-exec once if its own file changed (guards: `OPTIMUS_NO_UPDATE=1`,
     `--no-update`, `GIT_TERMINAL_PROMPT=0`). So the *program* is always latest with zero user
     action.
  2. `optimus/install/go.bat` holds the RUN logic and lives in the repo, so `git pull` refreshes
     it every run.
  3. `optimus/install/OPTIMUS.bat` is a THIN permanent on-switch (install basics + `git pull` +
     `call go.bat`). Because behavior lives in go.bat, the on-switch never goes stale and is
     downloaded only ONCE. Rule: never tell Patrick to re-download a launcher for a code fix —
     only a change to OPTIMUS.bat *itself* needs a re-download, and that's now rare-to-never.
  Lesson learned the hard way: a running `.bat` can't rewrite its own file mid-run, which is the
  *only* reason a launcher can't self-update — so keep launchers thin and put all logic in
  repo-side files the program/go.bat pull.
- **Run modes:** `--auto` = unattended (no Enter pauses); without it = MANUAL (opens map, waits
  for Patrick to position + press Enter, then scans the CURRENT view — no auto-ZIP-jump, set
  `searched=True`). `--loop SECS` re-scans in place (no reload/portal flip). `--fast` tightens
  pacing. Default launcher flow is MANUAL + `--loop 30`, NO outer reopen loop (Patrick disliked
  the browser closing/reopening — "stop telling it to reset"). Closing the browser stops cleanly.
- **Live status:** `report_status()` writes heartbeats (started/sleeping/done/error) to a
  **"Hunter Status"** tab in the same Google Sheet (on Drive) + local `run_status.json`, so the
  run is observable without the terminal. Drive installer folder: **"OPTIMUS SETUP - CLICK HERE"**
  (id `1IOWTZiDakRuzXtGGYgRCxPxXHNNZkaPc`) holds `OPTIMUS.bat` + a "READ ME" doc. (No Drive
  delete tool available — old duplicate uploads must be removed by hand.)
- **FINAL CAPTURE ARCHITECTURE (2026-06-15) — backend read, no clicking.** The
  clicking path kept flipping the view to the portal (whole-screen pixel detection
  read the portal's blue buttons as "dots" and clicked them; `focus_map`/popup-close
  clicks hit nav). Replaced with `drain_viewport_backend`: read every non-basemap
  POINT feature from the Mapbox map (`MAPBOX_DOTS_JS` → `queryRenderedFeatures`,
  exact `map.project` pixel + lng/lat + props), colour each dot by sampling ITS OWN
  pixel (`classify_pixel`, ±4px), write GREEN+GOLD, skip GREY. Map grabbed via the
  30-min `mapboxgl.Map` hook AND a `window`-globals search (module-loaded maps).
  Pan is programmatic (`pan_map_js` → `panBy`, no clicks) then "Search this area".
  Default run = `--cols 3 --rows 3 --fast` (position spot, press Enter, sweep 3x3,
  no zoom). `--allow-click` = old click path; `--probe` dumps map layers/props to
  `probe.json`. Skill: **map-backend-read**. Legend: GREEN=lead, GOLD=upgrade,
  GREY=existing customer (skip); all-grey view = MATURE (go to a newer area).
- **HARD RULE — NEVER CLICK THE DOTS by default.** Patrick was explicit (2026-06-15):
  the hunter must grab dots from the backend/server only, no clicking. Clicking is
  `--allow-click` opt-in ONLY. Do not re-enable the click path in the default flow,
  ever — even as a "fallback". If the server grab isn't working yet, leave the pass
  EMPTY and report the endpoints; don't fall back to clicking.
- **LIVE FINDING (2026-06-15 HP probe): the map object is FULLY HIDDEN.** Frame probe
  showed `hookedMaps:0`, `mapboxgl=false`, `maplibregl=false`, `maps=0` in BOTH frames
  (one is `about:blank`, the real one is `youachieve.att.com/yourefer/fiber`), yet dots
  render and the basemap is Mapbox tiles. So the map lib is bundled with NO window
  global and NO reachable instance — the backend-OBJECT read (`queryRenderedFeatures` /
  `getSource._data`) is IMPOSSIBLE on this site. Stop trying to read the map object.
- **THE PATH = NETWORK CAPTURE (no clicking).** The dots come from AT&T's server over
  the wire; `NetCapture` (now ALWAYS on, `page.on("response")`) decodes JSON +
  non-basemap vector tiles into leads. Pressing "Search this area" triggers the load
  that NetCapture reads. NEXT STEP: need the dot-data endpoint — a normal run with no
  decode prints every URL + writes `net_responses.log`; pin AT&T's dot URL there and
  point `--api-substring` / the JSON/tile parser at it. Telemetry to read this remotely
  is blocked (service account can't write to a personal-Gmail Drive; sheet is AI-blocked)
  — so getting that endpoint list currently needs a screenshot from Patrick.

## 7. Creds & accounts (Patrick's own — keep it simple)
- These are Patrick's accounts and creds. Copying or downloading `google_creds.json` to the
  right path on his own device is **routine setup, not a high-stakes event** — just do it and
  move on. Don't add friction or re-cite an old "handle creds extra-carefully" note; the fiber
  map data isn't sensitive and he isn't worried about it.
- Correctness tip (not security): put `google_creds.json` on a device by copying/downloading
  the real file, not by hand-rebuilding the JSON — a past hand-rebuild corrupted the private
  key (~90 min lost).
- Canonical key = fiberscanner-493900 on Drive (id `1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs`); the
  hunter auto-picks the valid fiberscanner copy among scattered ones. Normal hygiene only: the
  live key lives on the device / in env, not pasted into the repo.

## 8. Account custody & audience (2026-06-07)
- Command & Construct is Patrick's account; Frontline is a separate team's. Frontline's recent
  leads, form opt-ins, and CSV imports belong to that team — don't migrate, pull, or text them
  into or out of Command. The Frontline 45,579 / recent opt-ins are off-limits.
- Patrick's audience = his own prior contacts plus anyone who opts into his outreach going
  forward. Recent bulk/CSV/AI-test writes (Wichita shops, jeweler/realtor B2B scrape,
  call-tracking junk) aren't opt-ins, whoever loaded them.
- La Porte upload `5181c4eb-6.6.xlsx` (319 rows) is skip-traced, not opt-in: 184 carry a
  do-not-call flag, 135 are clean wireless / non-DNC. Route = door-knock + manual call on the
  clean non-DNC subset (not an SMS drip).
- Textable audience = Patrick's own opt-ins/customers, from one registered number, throttled,
  opt-out intact — not Frontline's recent form opt-ins.

## 9. AT&T fiber SMS templates (consent-based)
Source: Patrick's "GHL SMS Outreach Templates" doc
(`1P-x2HmEP3Hk0UwUnR7-0dI3B8Du_2XJN_3_AJXiyZ0k`). For opted-in / inbound / warm contacts. GHL
auto-appends opt-out; don't add or strip STOP. Offer baked in: 1 Gig in the $40s · 2 months
free · free install · no contract. Booking/live line **832-247-4060**.

- **Opener (form opt-in):** "Hi {{contact.first_name}}, it's Patrick with AT&T — you reached out
  about fiber. Good news, it's available at your address: 1 Gig starting in the $40s, 2 months
  free, free install, no contract. Want me to grab you a quick install window? What day works?"
- **Opener (warm opp):** "Hi {{contact.first_name}}, Patrick with AT&T here — following up on
  AT&T fiber for your place. It's live in your area: 1 Gig in the $40s, 2 months free + free
  install, no contract. Want me to lock in an install time? What day's best?"
- **Confirm address:** "Perfect! Quick check — is {{contact.address1}} the install address? Once
  I confirm it's fiber-ready I'll grab you the next available window."
- **Two windows:** "You're all set — fiber's available there. I've got two openings: {{option_1}}
  or {{option_2}}. Which works better for you?"
- **Confirm appt:** "Done! You're booked for {{appt_date}} at {{appt_time}}. You'll get a
  confirmation + reminder. If anything comes up, text me here or call 832-247-4060."
- **Follow-up (send ONCE, then stop):** "Hi {{contact.first_name}}, Patrick w/ AT&T — just
  circling back on the fiber install. Still want me to hold a spot for you?"

Reply routing: YES/interested → continue booking, hand live calls to 832-247-4060. STOP → existing
STOP workflow scrubs, never re-text. No reply after ONE follow-up → move to call/door, stop texting.
Recipe: `examples/recipes/att-fiber-consented-drip.json`.

## 10. Offers, flyer & contact points
AT&T offers (from flyer + promo sheet, verified 2026-06-07):
- Fiber flyer pricing (no contract, WiFi 6 router incl., unlimited data, no price change 12 mo):
  5-GIG $250 · 2-GIG $150 · 1-GIG $80 · 500 Mbps $65 · 300 Mbps $55 (per month).
- $35/mo with All in One; **$20/mo bundle discount for AT&T wireless customers**.
- **$100–$200 gift card included.**
- Promo bill credits (AT&T): new Fiber 1/5 GIG → $30/mo × 12; Fiber 300/500 Mbps → $15/mo × 12;
  Fiber 1 GIG → $200 Visa reward card; Fiber 5 GIG → $200 Visa; Hyperlocal 5 GIG → $55/mo;
  Hyperlocal 1 GIG → $45/mo (select zips incl. Houston TX, Dallas-Fort Worth, Atlanta GA).
- SMS hook stays simple: "1 Gig in the $40s" (the hyperlocal 1-GIG $45/mo bill-credit framing).

Flyer edit spec: swap in Patrick's number + patrickfiber@att.net; Visa → bill credit; −$25/12mo;
−20% with cell line; keep existing format/colors.

Contact points: booking/live line **832-247-4060**; sending number **832-952-0728** (Frontline
`+18329520728`, "TX number 3"); Frontline location line **+18328445183**.

Team/ops (structure only — payroll figures, full roster, and WhatsApp threads NOT in this repo):
Claire's crew works leads (e.g. Mr. Kassow); split into closers + setters; payroll ≈ closer
commission sheet × setter chat activity; tooling includes Sales Mate. Keep PII/financials in a
private doc, not this repo.
