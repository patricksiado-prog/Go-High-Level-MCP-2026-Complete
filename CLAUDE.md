# AT&T Fiber Outreach — GHL Busybee Brain (CLAUDE.md)

> **RULE — EVERY distributed program MUST auto-update from GitHub on launch.** No
> recipient should ever run stale code. Each program calls `self_update()` as the
> first line of `main()`: from inside the repo it does `git fetch` + `reset --hard
> origin/<branch>` (via `_find_git()` so it works even when git isn't on PATH); a
> standalone single-file copy re-downloads itself from the GitHub raw URL; then it
> re-execs once (guarded by a `*_NO_UPDATE=1` env var). Launchers also pull each run.
> Covered: precise_fiber_hunter.py, maps_scraper_standalone.py, dialer_loader.py.
> When you add ANY new runnable program, wire in self_update the same way.

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

- **FILE MAP & SOLUTION (2026-06-17 — after reading every tool + Mapbox research).**
  - **optimus_dot_detect.py** ("dot extractor") = canonical dot-colour RGB windows
    (GREEN 30,130,30–100,210,80 / GOLD / GRAY), `zone_freshness`, `classify_status`,
    pixel dot-find (`find_dots_in_array`, scipy connected-components + shape filter).
  - **optimus_api_capture.py** = `ResponseSniffer` (page.on response) + `extract_features`
    (schema-tolerant JSON → address/lat/lng/ban/status; address must match `\d+\s+\S+`).
    The PROVEN backend reader.
  - **fiber_precise_pipeline.py (MapMan)** = PROVEN: `search_zip` (TYPE the ZIP) →
    serviceability fetch → ResponseSniffer captures → extract_features → writes sheet.
    Motion = `focus_map` (click the canvas at 18%/22%) then keyboard.
  - **fiber_zone_scanner.py** = headless multi-instance ZIP scanner, same backend capture.
  - **fiber_hunter.py (ORIGINAL, in the `optimus-map-tools` repo)** = the first "fiber
    hunter": motion is a **MOUSE DRAG** (`pyautogui.dragRel`, 150px from map centre,
    serpentine), pixel-colour dot detect, and a **manually-calibrated "Search this area"**
    click. So "motion exists in fiber hunter" = the DRAG, not arrow keys.
  - **precise_fiber_hunter.py (current main)** = `NetCapture` (page.on response) +
    extract_features; manual WATCH mode (user pans, it flushes every 6s); BATCHED sheet
    writes; Drive telemetry (log + screenshot + raw json).
  - **CONFIRMED WORKING (2026-06-16):** the backend grab WORKS — a live run hit Google
    Sheets `[429] write-requests-per-minute` errors, which PROVES it captured real
    addresses off the serviceability feed and tried to write them. Fixed by BATCHING
    (`append_rows`, chunk 500) instead of `append_row` per address.
  - **SOLUTION / refinements:** (1) capture = `page.on("response")` → serviceability JSON
    → `extract_features` (done, working). (2) Trigger reliably: the serviceability fetch
    fires on pan + "Search this area" (button only appears AFTER you move the map); the
    deterministic version is `page.wait_for_response(lambda r: "serviceability" in r.url)`
    right after the search click. (3) Auto-motion should use Playwright **mouse drag**
    (`mouse.move`/`down`/`move`/`up`) — the proven motion; arrow keys / `panBy` do nothing
    here because the map object is hidden. (4) Verify accuracy via `serviceability_raw.json`
    / the sheet (sheet is AI-blocked to Claude until the Drive log/folder is shared).
  - Research (Playwright): passive `page.on("response")` + targeted `wait_for_response`
    is the standard pattern for scraping a site's hidden JSON API. Sources:
    playwright.dev/python/docs/mock; the dots are NOT readable from the map object.

- **CURRENT OBJECTIVE & APPROACH (2026-06-16) — read this first.**
  - **GOAL:** from the AT&T dealer fiber map (`youachieve.att.com/yourefer/fiber`),
    capture every GREEN (eligible non-customer = lead) and GOLD (copper-upgrade)
    dot's exact street address + lat/lng into the Google Sheet ("Precise Fiber"
    tab), so Patrick can door-knock / DNC-scrubbed-call them. GREY = existing fiber
    customer = skip.
  - **HOW (current best path):** the page hides the map object (no
    mapboxgl/maplibregl global), so we CANNOT read the map object. BUT the dots come
    from AT&T's **`serviceability` JSON endpoint**, and the existing proven tools
    (`fiber_precise_pipeline.py`, `fiber_zone_scanner.py` + `optimus_api_capture.extract_features`)
    already decode that. So: trigger the fetch (search/position/pan), capture the
    serviceability JSON off the wire with `NetCapture`, run `extract_features` →
    addresses. NO clicking when this works.
  - **MOTION (fixed 2026-06-16):** the map only pans the PROVEN way — `focus_map()`
    clicks the map CANVAS (bbox 18%/22%) to focus, THEN arrow keys. The old
    programmatic `panBy` did nothing (needs the hidden map object) → "it's not
    moving." Ported the working motion from `fiber_precise_pipeline.focus_map`.
  - **PATRICK'S HARD CONSTRAINTS:** (1) ONE program = `precise_fiber_hunter.py`; do
    NOT send him to a second tool. (2) ONE login (the existing `att_profile`); never
    make him log in again. (3) ONE command, unchanged (`python precise_fiber_hunter.py`);
    never make him copy a new command to Drive. (4) Prefer the server/serviceability
    grab; clicking is the explicit fallback only. (5) He can't see program output —
    only his screenshots reach Claude (Drive telemetry blocked: service account can't
    create files in personal Gmail Drive; the sheet is AI-blocked).
  - **OPEN QUESTION / NEXT:** does the serviceability fetch fire reliably during
    capture in manual mode? Proven tools trigger it via `search_zip` (type the ZIP).
    If a normal run still captures 0, the fix is to type the area into the search box
    to force the fetch while `NetCapture` is listening — bring that into
    `precise_fiber_hunter` so it stays one-command. Confirm via the next screenshot
    (look for `viewport (network): +N captured OFF THE SERVER`).

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
- **CAPTURE ORDER (Patrick's approved flow, 2026-06-15):** position → Enter → the
  hunter PANS + presses "Search this area" (this is the fetch that puts the dot data
  on the wire) → (1) try to grab the addresses OFF THE SERVER via `NetCapture` (no
  clicking) → (2) ONLY if the address didn't materialize on the wire, fall back to
  clicking each green/gold dot's popup. Server-first, clicking is the explicit
  fallback (Patrick OK'd it: "if not then clicking") — NOT the default. The win is
  pinning the server feed so clicking retires; until then clicking keeps leads
  flowing. Always prefer/try the server grab first on every patch.
- **THE DOT ENDPOINT = `serviceability` JSON (known from the existing tools!).** The
  working pipeline (`fiber_precise_pipeline.py`, `fiber_zone_scanner.py`) already
  capture the AT&T dot layer via `--api-substring serviceability` and parse it with
  `optimus_api_capture.extract_features` (schema-tolerant: pulls address/lat/lng/ban/
  status from the JSON; address must match `\d+\s+\S+`). `precise_fiber_hunter`'s
  NetCapture now imports + runs that same `extract_features` on every JSON response,
  so when the map fetches serviceability data the addresses decode off the server, no
  clicking. The map fetch fires on search/positioning (and possibly on pan); the
  trigger to re-fetch on a programmatic pan is the remaining unknown ("Search this
  area" button text wasn't found live — see `dump_clickables` output). If a normal
  run still gets 0, the serviceability fetch isn't firing during capture → trigger it
  via the search box / a `--zip`, or just run the proven `fiber_precise_pipeline.py
  --zip <z> --api-substring serviceability`.
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

- **SESSION 2026-06-17 — what got built/learned (read this; supersedes stale bits above).**
  - **CLAUDE *CAN* READ THE SHEET.** The old "sheet is AI-blocked" note is WRONG. The
    Drive MCP is connected to Patrick's own Google account, so `read_file_content` on
    `SHEET_ID 1FhO2BTM…` returns the live data (Precise Fiber rows, Hunter Status
    heartbeats, the old MapMan tab). This is the real feedback channel — no screenshots
    needed for data. (The OPTIMUS_HUNTER_LOG.txt / SHOT.png telemetry files stay EMPTY:
    the service account can't write to Patrick-owned files unless he shares the folder
    with `fiberscanner@…iam.gserviceaccount.com`, which he never did. Don't rely on them —
    read the sheet instead.) Drive read returns ~274k chars max (truncates a huge sheet);
    use python/jq on the saved tool-result file for counts.
  - **Drive MCP limits:** I can READ files + CREATE files in Patrick's Drive, but CANNOT
    set sharing (no permission tool → Patrick must "Anyone with link → Viewer" anything I
    make) and CANNOT update a file in place (no update tool → every change = a NEW file
    with a NEW id; that's why links churned). Stable distribution = thin launcher that
    re-downloads a FIXED guts id each run; publish updates via Drive **Manage versions**
    (keeps the id + link).
  - **PRECISE HUNTER — fast auto-sweep shipped & confirmed working.** Manual mode now
    SWEEPS instead of reading one stationary view (that was the `+0 this pass` bug seen in
    Hunter Status pass 346–353). `mouse_drag()` = the PROVEN fiber_hunter motion (drag the
    canvas; arrow keys/panBy do nothing). `sweep_backend()` drags cell-to-cell across a
    grid, flushing the serviceability backend each cell. Root-cause of "not panning":
    the map canvas can be in a FRAME — `_map_canvas_box` now searches page+frames, and
    falls back to dragging the VIEWPORT map-region (page.mouse, frame-independent) so it
    ALWAYS pans. Tunables: `DRAG_FRAC=0.45` (pan distance), `--fast` pacing
    (WAIT_AFTER_PAN 0.2 / SEARCH_SETTLE 0.25). Default `--cols 3 --rows 3`.
    LIVE RESULT: Precise Fiber went 312 → 1876 across 155+ River Oaks streets = sweep
    works. Verified 3108 Locke Ln earlier.
  - **SHEET = leads only.** Dot Color column writes **GREEN** (lead) / **ORANGE**
    (copper upgrade); **GREY (existing customer) is SKIPPED entirely** (both write paths).
  - **PHONE ENRICHMENT runs in-process** (`_start_enrichment` daemon thread →
    `enrich_phones.run(watch=True)`), reprocesses the whole `precise_addresses.jsonl`
    backlog, writes name+phone to an **"Enriched Leads"** tab. Excludes government/civic +
    big-box chains (`_is_callable_prospect`). Columns Patrick wants = Category, Email,
    Name, Address, Phone. Auto-uses Google Places when `GOOGLE_PLACES_API_KEY` is set (no
    flag). **HARD TRUTH:** free OSM/Places/Maps only have BUSINESS phones — houses have NO
    free public number anywhere; residential phones = SKIP-TRACING only (like La Porte).
  - **COMMERCIAL vs RESIDENTIAL split = `commercial_split.py`.** The scalable MapMan way:
    bulk-scrape every business in a ZIP by category, then cross-reference to the captured
    fiber addresses. Match = COMMERCIAL (name+phone → Commercial Leads tab); no match =
    RESIDENTIAL (door-knock → Residential Leads tab). `normalize_address()` (tested) lines
    up "3266 Locke Lane, Houston TX" with "3266 LOCKE LN". Category sets QUICK(20)/
    NORMAL(47)/DEEP(155), small/in-home focus (home-based biz sit at residential
    addresses — searching them catches them). `MAPMAN.bat` = one-click (ZIPs + depth →
    scrape → split into sheet); prefers gosom exe, falls back to the built-in scraper.
  - **THE SCRAPER.** `gosom/google-maps-scraper` (MIT, no key, prebuilt Win binary) is the
    proven open-source tool — it reads Google's hidden JSON data feed (fast, block-
    resistant: bulk category searches, not 20k one-by-one lookups). Its easy install is
    Docker though. So also built **our own** Playwright scraper: `optimus/maps_scraper.py`
    (in-suite) and `optimus/standalone/maps_scraper_standalone.py` (the standalone product:
    prompts ZIPs, embedded categories, CSV **or** Google Sheet "Maps Businesses" tab,
    VERSION stamp). Can't test scrapers from the sandbox (network 403 on Google/Overpass).
  - **STANDALONE SCRAPER PRODUCT (Drive-hosted, self-installing, auto-updating).**
    PERMANENT launcher link = Drive id **`1uOR6ijmlQXy61dcoDD1gr7cE9ibLnah1`**
    ("START - Maps Scraper.bat"). It installs Python+Playwright itself, then RE-DOWNLOADS
    the **guts** each run from Drive id **`1jRFrgO-2kkqCWrwF0MN1uUFv81vDMEEy`**
    ("SCRAPER GUTS (update this one)") → auto-update with nothing for the user but the
    link. People need NO GitHub/git. To update without changing the link: Drive Manage-
    versions on the guts file. **CORRECTION 2026-06-18: the repo is PUBLIC** (the old
    "repo is PRIVATE" claim here was wrong — verified raw GitHub serves the files with
    no auth). So the Drive-guts indirection is no longer needed: distribute purely from
    GitHub raw (see "DISTRIBUTION = PURE GITHUB" below). This Drive-guts path still works
    but is legacy; prefer the GitHub launcher commands.
    Old duplicate launcher/guts uploads litter the "OPTIMUS SETUP" folder — delete by hand.
  - **GitHub scope:** this session can only touch `go-high-level-mcp-2026-complete`. The
    `optimus-map-tools` repo (the ORIGINAL fiber_hunter + MapMan) is DENIED — can't read
    it. `list_repos`/`add_repo` tools not available here. gosom source IS readable (public)
    via WebFetch.
  - **NEXT / OPEN:** (1) prove the standalone scraper on Patrick's PC (was mid-run:
    `[2/3] Browser engine` = chromium download, slow first time). (2) DIALER: wire
    scraped Commercial Leads → `business_score` → `ghl_loader` (already builds AT&T
    Commercial opps + enrolls the "Optimus Fiber Biz — Power Dialer Queue" workflow,
    human-on-every-call). Missing glue = an adapter from the scraper CSV to ghl_loader's
    scored-dict input, + GHL_PIT_TOKEN, + power-dialer/number enabled in Command, + DNC
    scrub. (3) emails drafted in Gmail to `Js@frontlinedirectsales.com` (Jim): Google
    Cloud Places-API setup + installer — Patrick to review/send.

- **SESSION 2026-06-18 — what got built/learned (read this; latest).**
  - **COMBO LOGIC NOW LIVES IN THE HUNTER (done, pushed).** Per Patrick: the scraper
    stays a SEPARATE standalone program that fills the **"Maps Businesses"** tab; the
    cross-reference/combine piece runs INSIDE `precise_fiber_hunter.py`. As the hunter
    captures each GREEN/GOLD address it matches it against the scraped businesses
    (loaded once into an in-memory dict keyed by normalized address) and writes hits
    **live** to **"Fiber Green Biz"** (green dot + biz) / **"Upgrade Orange Biz"**
    (gold/orange dot + biz). Cols = Business Name · Phone · Address · Website · Category.
    Implementation in the hunter: constants `MAPS_TAB/GREEN_BIZ_TAB/ORANGE_BIZ_TAB`,
    `_norm_addr` (HOUSE|STREET CORE; strips unit/city/zip, standardizes suffix),
    `init_bizmatch(ws)` (called once in main after `open_sheet()` — loads businesses +
    opens the two tabs + dedupe seen-sets), `match_leads_to_biz(new_records)` (called
    from `NetCapture.flush` after the Precise Fiber write — batched `append_rows`, one
    call per tab), and `_backlog_match()` (one-time startup pass over
    `precise_addresses.jsonl` so leads captured BEFORE the scraper ran still get a
    business name+phone). Removed the old end-of-run `run_bizmatch()` + the
    `commercial_split` import. `--no-match` disables it. The match itself is O(1) dict
    lookups (instant at any scale); only real throttle is the shared Sheets write
    quota, already handled by batching.
  - **SCRAPER NOW HEADLESS BY DEFAULT (done, pushed; v1.6→v1.7).** The Google Maps
    browser was launching VISIBLE (`headless=False`) and covering Patrick's screen.
    Now `headless=not SCRAPER_SHOW` — runs hidden in the background, writes to the
    sheet/CSV, PC stays usable. `SCRAPER_SHOW=1` forces the window back (occasionally
    more block-resistant). Prints "Running in the background (no window)". Old runs
    already open stay visible — the hidden default only applies to the NEXT launch
    (the launcher git-pulls each run, so just re-run, no reinstall).
  - **UI HELP given:** minimizing a Chromium/Command-Prompt window does NOT pause
    Playwright — it keeps scraping. The scraper's Command Prompt (text log) and the
    Chrome/Maps window are TWO separate windows; minimize both to clear the screen.
    The scraper writes incrementally + resumes, so restart loses nothing.
  - **HOW TO START THE HUNTER (Patrick asked):** day-to-day = double-click
    **START OPTIMUS.bat** (`%USERPROFILE%\optimus\START OPTIMUS.bat`) — it git-pulls,
    does the one-time AT&T login, then runs the hunter. Raw command (skips
    auto-update): `cd /d "%USERPROFILE%\optimus\repo\optimus"` then
    `python precise_fiber_hunter.py` — NO `--zip`, NO flags; you pan/zoom the map by
    hand, press Enter, it sweeps that area continuously until you close it. (Patrick
    explicitly dislikes the `--zip` arg — don't suggest it as the normal path.)
  - **DISTRIBUTION = PURE GITHUB, NO DRIVE LAUNCHER SHARING (decided 2026-06-18,
    verified live).** The repo IS PUBLIC (confirmed: raw.githubusercontent.com serves
    files with no auth; `git clone https://github.com/...` works for anyone with no
    GitHub account). So drop the Drive-hosted launcher copies entirely — the launchers
    already live in the repo and are downloaded straight from GitHub raw. The three
    Drive launcher files (`1pQRDC2Xh-YaZ3MLT5QurtKqQbajll77W` hunter /
    `1uuWqUMXAGElvBtUfAuqRraiEiiaRbLGJ` scraper / `17RzE0ri5MZHj8YgGir8rVyKp_gqT4VX1`
    dialer) were all still **Restricted (owner-only)** and are now unnecessary —
    don't bother sharing them. Recipients get a one-line `curl` command (or the raw
    link) that downloads the launcher `.bat` and runs it; the launcher then pulls the
    rest of the code from the public repo every run. Raw launcher paths on branch
    `claude/optimus-map-tools-setup-6dcl6o`: hunter = `optimus/install/START OPTIMUS.bat`,
    scraper = `optimus/standalone/SCRAPER_SETUP.bat`, dialer = `optimus/install/START DIALER.bat`.
  - **THE ONLY DRIVE DEPENDENCIES LEFT (both already shared correctly, verified
    2026-06-18):** the Google service-account key (`1upYH4h2VsmOwO82v9CVjMpE6IzV-5dIs`,
    shared Anyone-with-link → **Viewer**) which the launchers download so the programs
    can write the sheet; and the leads SHEET (`1FhO2BTM…`, shared Anyone-with-link →
    **Editor**) which is how the programs write and how Claude reads it. Code never needs
    Drive again.
  - **DIALER LINK BUILT (done, pushed + uploaded).** `dialer_loader.py` (in optimus/,
    not standalone — needs `ghl_loader`+`business_score`) reads the hunter's
    **"Fiber Green Biz"** + **"Upgrade Orange Biz"** tabs, maps green→`STATUS_LEAD` /
    orange→`STATUS_COPPER_UPGRADE`, scores with `business_score.rank_businesses`
    (drops no-phone/DNC/customer), DNC-scrubs against `~/optimus/dnc.txt`, then calls
    `ghl_loader.load_businesses(..., commit=True)` → upserts contacts + AT&T Commercial
    opps + enrolls the Power Dialer Queue workflow (`DIALER_WORKFLOW_ID
    41e00387-a766-4975-bbcd-627c684a3ee1`). DRY PREVIEW first, asks before any live
    write. Token: env `GHL_PIT_TOKEN` else cached `~/optimus/ghl_token.txt` (prompts
    once). Launcher `install/START DIALER.bat` = repo-clone pattern (like the hunter).
    Drive link id = **`17RzE0ri5MZHj8YgGir8rVyKp_gqT4VX1`** ("START - GHL Power Dialer
    (OPTIMUS).bat") — Patrick must share Anyone-with-link→Viewer. KEY: it does NOT
    place calls — it STAGES + ORDERS the queue; dialing stays human-on-every-call in
    GHL (TCPA). Prereqs in Command (set in GHL UI, not by script): power dialer / a
    calling number enabled + the Power Dialer Queue workflow published (was published
    2026-06-12). Phone landline/wireless type is unknown from Maps (phone_type=None →
    mid phone score); a real landline/wireless classify would need skip-trace data.
  - **DIALER FIX 2026-06-18 (root cause of "queue empty / nothing happens").** GHL's
    Manual Call / power-dialer queue surfaces a lead to the **CONTACT'S OWNER**, not the
    opportunity owner. `ghl_loader` was only setting `assignedTo` on the opportunity, so
    every lead defaulted to whoever happened to own the contact (the 29 all sat on Zack
    `qOa2OVzPabolfU9xjVXM` — only HE saw them in Conversations > Manual Actions). FIXED:
    `contact_payload(..., assigned_to=)` now stamps the CONTACT, and `dialer_loader` by
    default round-robins across **ALL active Command users** (`fetch_all_agents` → GET
    `/users/?locationId=`); `--agents <ids>` overrides. `--reassign` re-spreads
    already-loaded leads (ignores the dedupe state; upsert re-owns by phone, no dupes) —
    the one-time command to redistribute the existing 29: `python dialer_loader.py
    --reassign`. Command users (2026-06-18): ARA `jBmInXreGR2oskVXax0h`, ED SALDANNA
    `lQ7gVrSONTWMAv4ZsEdO`, joshua Bulter `7c9QLWsTDyTALTMj0ast`, Romeo `J3PkeoYp8TNXMNNcaN4l`,
    Zack `qOa2OVzPabolfU9xjVXM`. **Sheika is NOT a Command user** — she must be added in
    Settings > Team (needs her email + a seat) before she can dial / be in the round-robin.
  - **POST-CALL = native "load next call" (Patrick's call 2026-06-18).** No auto-SMS after
    dispositioning — the power dialer already advances to the next contact when the rep
    removes the Manual Action task (GHL only progresses the workflow on task delete, not on
    calling from elsewhere). The two draft "Post-Call — Follow-up Text" workflows
    (`bd37d7e2…` has Wait+SMS but NO trigger; `685383f2…` is an empty shell) stay OFF. If
    revisited: a post-call text needs a **Call Status** trigger (no-answer/VM/busy) or a
    **Call Details + Custom Disposition** trigger; "only if cell" needs a paid line-type
    lookup (Twilio Lookup ~1¢/#) — not native, and most Maps biz numbers are landline/VoIP.

- **SESSION 2026-06-19 — what got built/learned (latest; read this).**
  - **GREEN LEADS LOADED TO BOTH ACCOUNTS (live, via MCP).** The "Fiber Green Biz" tab
    has many repeat rows (the hunter re-matches the same biz every sweep + backlog re-match)
    but dedups by phone to the real count: grew **65 → 111 → 122 unique** this session.
    Loaded into **Command/Optimus**: all 122 upserted (round-robin across the 5 Command
    users `jBmIn…/lQ7gV…/7c9QL…/J3Pke…/qOa2O…`), enrolled in the Power Dialer Queue
    workflow `41e00387…`, **AND a pitch note added to each** (the AT&T fiber call script).
    Loaded into **Frontline**: **121/122** upserted (round-robin across the 14 Frontline
    users), tagged `green-houston` (one, The Goddard School +17138046550, kept getting
    "Denied by user" — skipped). Upsert merges by phone = no dupes; re-run loads only new.
  - **FRONTLINE AUTODIALER IS BLOCKED ON ONE THING: no Manual Call workflow, and I can't
    create it via API.** Frontline (loc `TXw28sw0Z2rI6tcCDhJY`) HAS an "AT&T Commercial"
    pipeline (`BZb6jl8rDDeaurYHGZoh`) and 14 users, and **official-API writes work**
    (upsert_contact/opp succeed — proven). But `ghl_create_workflow` fails with **Firebase
    `INVALID_REFRESH_TOKEN`** (the internal-API token on that connector is stale), so the
    power-dialer (Manual Call) workflow must be **built in the Frontline UI** (Automation →
    Workflows → Manual Call action + a Contact-Tag trigger on `green-houston`), or reconnect
    the Frontline connector and Claude can create it. Until then Frontline leads are worked
    from **Contacts → filter `green-houston`** (assigned per-user), not the Manual Actions
    autodialer. Frontline 14 user ids captured in this session's transcript.
  - **MCP CONNECTOR NAMES CHURN ACROSS RECONNECTS.** Command busybee has appeared as
    `mcp__40b566b8…`, `mcp__cmndconevtor…`; Frontline as `mcp__6cf38bf0…`,
    `mcp__ghl-frontline-connector…`. Verify which is which by a read (Command = loc
    `xZj500…`, Frontline = `TXw28sw0…`) before writing. They also drop/reconnect mid-session.
  - **BUSYBEE RAILWAY URLs (record these — the Frontline one was missing the whole time
    and caused a multi-hour wild-goose chase 2026-06-25).** Two SEPARATE Railway deploys,
    each pinned to one location, DIFFERENT URLs:
    - **Optimus/Command** (Railway project `fulfilling-growth`): `https://go-high-level-mcp-2026-complete-production-711a.up.railway.app/mcp`
    - **Frontline** (Railway project `loving-heart`): `https://go-high-level-mcp-2026-complete-production-46d1.up.railway.app/mcp`
    The Claude **Frontline connector MUST point at the `46d1` URL** (loving-heart). If it's
    pointed at `711a` or an old box, contacts/reads still work (per-request header override)
    but **workflow creation fails with `INVALID_REFRESH_TOKEN`** — that exact symptom = wrong
    URL, not bad creds. Both deploys share IDENTICAL `GHL_FIREBASE_API_KEY`
    (`AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE`) + `GHL_FIREBASE_REFRESH_TOKEN`
    (`AMf-vBx2m4c2P_iAMQLsa…`, Patrick's login — verified matching); only `GHL_LOCATION_ID`
    + `GHL_API_KEY` differ. Connectors load at SESSION START, so after fixing the connector
    URL, open a FRESH chat for it to take effect.
  - **FRONTLINE INVALID_REFRESH_TOKEN — DEFINITIVELY DIAGNOSED 2026-06-25 (supersedes the
    "wrong URL" theory above).** Tested both busybees live in one session with the connectors
    loaded (Optimus = `40b566b8…` loc `xZj500…`; Frontline = `6cf38bf0…` loc `TXw28sw0…`):
    - Frontline `ghl_list_workflows` → **200, reads fine** (so the 46d1 URL is correct, the box
      is live + bound to the right location, and the PIT/read auth is healthy). The URL was NEVER
      the problem — that earlier note is WRONG.
    - Frontline `ghl_create_workflow` → **still 400 `INVALID_REFRESH_TOKEN`**.
    - Optimus `ghl_create_workflow` → **SUCCEEDS** (created + deleted a throwaway, live token
      refresh).
    READS and CREATES use DIFFERENT auth paths in the busybee: reads = PIT token (works on both);
    creates = the Firebase refresh flow (`securetoken.googleapis.com/v1/token?key=API_KEY` +
    `refresh_token`). That endpoint is STATELESS — same key + same refresh-token value returns the
    same result no matter which Railway box calls it. So: the identical token works from Optimus
    but is rejected from Frontline ⇒ **the value actually running on the 46d1 box is NOT the same
    bytes as Optimus's**, even though Patrick's notes Doc shows them matching. Cause is a corrupted/
    stale copy in the loving-heart `GHL_FIREBASE_REFRESH_TOKEN` var: a hidden typo/truncation/
    trailing-newline, the old "L"-bleed value, OR the running deploy predates Patrick's correction
    (Railway loads env only on redeploy). NOT a shared-token conflict, NOT the URL.
    **BULLETPROOF FIX (don't hand-compare 200 chars):** in Railway, COPY the *working* value from
    fulfilling-growth/Optimus `GHL_FIREBASE_REFRESH_TOKEN` (copy icon, not manual-select) and PASTE
    it over loving-heart/Frontline's `GHL_FIREBASE_REFRESH_TOKEN` (also re-paste `GHL_FIREBASE_API_KEY`
    to be safe); ensure no trailing space/newline; REDEPLOY loving-heart and wait for a fresh green
    deploy stamped AFTER the save. The token lives server-side (read per-request from the box env, not
    a chat-session header), so once 46d1 redeploys with the good value, the SAME connector's next
    `ghl_create_workflow` works — no need to reopen the chat to test the create fix.
  - **HEADER-ROUTING FIX (the real one Patrick remembered — "it's headers / how you communicate
    to each one"; shipped 2026-06-25, branch `claude/optimus-map-tools-setup-6dcl6o`).** The
    documented per-account pattern lives in `docs/tooling/client-config-generator.md`: ONE MCP
    server entry per location, each carrying its own `Authorization`/`X-GHL-Location-ID` headers.
    The busybee already honored `x-ghl-location-id` + `x-ghl-access-token` for every PIT tool
    (`main.ts` `/mcp`) — but the **workflow builder was frozen to ENV at startup**
    (`WorkflowBuilderTools` ctor called `fromEnv()` once), so workflow CREATE ignored the headers
    and always used the box's env Firebase/JWT token + env location. That blind spot = the whole
    "Frontline can't create workflows" bug. FIX (4 small edits, build green):
    1. `workflow-builder-client.ts` — added `setLocation(locationId)` + `targetLocationId` getter
       (retarget the create/read location at runtime without touching auth).
    2. `workflow-builder-tools.ts` — ctor now takes `locationOverride?` and applies it via
       `setLocation` after `fromEnv()`.
    3. `tool-registry.ts` — reads `ghl.getConfig().locationId` (the per-request client's location)
       and passes it into `new WorkflowBuilderTools(loc)`. No header → equals env location → no
       behavior change.
    4. `main.ts` `/mcp` — token now accepted from `x-ghl-access-token` **OR** `Authorization:
       Bearer` (the doc shows the Authorization form, the server previously only read
       `x-ghl-access-token` → silent mismatch); also accept `x-ghl-locationid` alias.
    NET EFFECT: point the **Frontline connector at the WORKING Optimus box** (`…711a…/mcp`) and
    keep its `x-ghl-location-id: TXw28sw0…` + `x-ghl-access-token: <Frontline PIT>` headers →
    PIT tools act on Frontline (per-request token), and workflow CREATE runs on **Optimus's good
    Firebase/JWT token but targets Frontline's location**. No fresh Frontline token, no Railway
    env surgery on 46d1. DEPLOY: redeploy the fulfilling-growth/Optimus box with this code, then
    repoint the Frontline connector URL 46d1→711a (keep its headers). DEPENDENCY: Patrick's login
    (the token the Optimus box runs on) must have automation rights in the Frontline location; if
    not, create fails with a PERMISSION error (not INVALID_REFRESH_TOKEN) and Frontline needs its
    own valid token instead.
  - **LIVE TEST 2026-06-25 (after header fix pushed) — two findings.** Created the starter draft
    "AI — New Lead Intro (DRAFT)" (trigger `ai-test` tag → SMS → tag `ai-contacted`) in both via
    the now-loaded connectors (`cmndconevtor`=Command/xZj500, `ghl-frontline-connector`=Frontline/
    TXw28sw0):
    1. **Frontline STILL `INVALID_REFRESH_TOKEN`.** The header fix is pushed to GitHub but the
       LIVE Railway box that connector hits is still running OLD code / dead token. Tools listing
       in the connector ≠ fix deployed. Frontline workflow-create stays blocked until the
       fulfilling-growth/Optimus box is REDEPLOYED with the header-routing code AND the Frontline
       connector points at that box (…711a…/mcp) with its TXw28sw0 location header.
    2. **WORKFLOW-BUILDER TRIGGER BUG (affects BOTH accounts, not auth).** Command authenticated
       fine and created the workflow + both actions (`ghl_update_workflow_actions` with actions
       only = 200), but ANY call carrying a trigger 500s: `WORKFLOW_SAVE_FAILED / 5 NOT_FOUND: No
       document to update: .../triggers/<id>`. Root cause in `workflow-builder-client.updateWorkflow`:
       it puts the new trigger in `newTriggers` with a fresh `randomUUID()` id + `triggersChanged:
       true`, but the GHL backend tries to UPDATE (firestore) that trigger doc instead of creating
       it — there's a `createdSteps` array for new ACTIONS but no equivalent "created triggers"
       signal, so triggers default to update→404. Actions have no such problem. WORKAROUND until
       fixed: build the workflow + actions via the busybee, then add the trigger by hand in the GHL
       UI (Workflow → Add Trigger → Contact Tag → the tag) — 5-second dropdown. REAL FIX (deferred):
       capture the GHL UI's actual workflow-save payload from the browser network tab to see how it
       signals a NEW trigger, then mirror that (likely a created-triggers list or a per-trigger
       "isNew"/no-id-means-create convention) instead of the blind `newTriggers` PUT.
  - **ROBUST INSTALLERS (dodge the #1 Windows trap).** New `optimus/install/INSTALL_HUNTER.bat`
    and `INSTALL_SCRAPER.bat`: install Python from **python.org with PrependPath=1** (kills
    the Microsoft-Store "Python not found / App execution alias" trap that blocked the team),
    pull latest code (hunter = repo zip, scraper = raw .py), install deps + chromium + the
    Google key, then launch. Use `py` (lands in C:\Windows, always on PATH). One-paste:
    `curl -L -o "%USERPROFILE%\Desktop\INSTALL_HUNTER.bat" "<raw .../optimus/install/INSTALL_HUNTER.bat>" && "%USERPROFILE%\Desktop\INSTALL_HUNTER.bat"` (same for SCRAPER). Also uploaded to the
    "OPTIMUS SETUP" Drive folder: INSTALL HUNTER.bat=`1VUj_lzUrmnTcYH1UZ6JnNNJK2xzRYVUd`,
    INSTALL SCRAPER.bat=`1IuKrdY40deAo-WCg2-T-R3Gp_1DBsgUk`.
  - **TEAM "REQUEST ACCESS" FLOOD = restricted Drive .bats.** Inbox is full of Google
    "Share an item? … requesting access to Google Maps Scraper SETUP.bat" (Romeo, Zack,
    Edward, Ara, Rodelio, Dave, Lalitha) — the Drive launcher copies are owner-only. FIX:
    send the team the **GitHub install command** (needs zero Drive access) instead of the
    Drive link, or share those Drive files Anyone-with-link→Viewer. Gmail draft to
    `budonk3y@gmail.com` with the GitHub installer was created (Gmail MCP only drafts).
  - **"No google_creds.json" scraper error** = the key didn't download → scraper writes CSV
    only, not the sheet. The robust installer fetches the key; manual fallback = download key
    `1upYH4h2…` and drop it as `google_creds.json` in `%USERPROFILE%\maps_scraper\`.
  - **HUNTER FINDS 0 / ALL-GREY = mature area, not a bug.** Green count stalls when the hunter
    sits in built-out (all-grey) inner-loop ZIPs (77002/77027/77098/77005/77046 = worked out).
    To grow matches: run hunter on **fresh fiber** (La Porte 77571 confirmed fresh; growth
    suburbs 77449 Katy/77433 Cypress/77386 Spring/77584 Pearland) AND run the **scraper on the
    same ZIP** (a green-BIZ match needs both the dot captured AND the business scraped).
  - **SMS PROMO UPDATE (use these in the post-call/Random-Split texts).** Added to the offer
    set: **$500 Visa reward card**, **cell service from $15/mo**, **iPhone 17 for $4/mo** —
    on top of the brain's fiber promos (1 Gig in the $40s, 2-Gig $150, 5-Gig $250, $200/$500
    Visa, 2 mo free, free install, no contract, WiFi 6, +$20/mo with AT&T wireless). 10
    randomized variants drafted. COMPLIANCE: these are scraped biz numbers → texting them
    conflicts with the "call/door only, never cold-text" hard rule; recommended firing the
    text only on an **"Interested" disposition (cell-checked)** = consented, not after every call.
  - **dialer_loader now account-switchable** (env `GHL_LOCATION_ID`/`GHL_PIPELINE_ID`/
    `GHL_DIALER_WORKFLOW_ID`, defaults Command) so the same loader can target Frontline; and
    `--reassign` re-spreads already-loaded leads round-robin. (Pushed earlier 2026-06-18/19.)

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

## 11. HOW THE PROGRAMS ARE BUILT (architecture) + SESSION 2026-06-25 LOG

### 11a. How the two programs work (the whole pipeline in plain terms)
The Optimus toolkit was written by Claude across sessions; it lives in `optimus/`. The loop:
**Hunter captures fiber dots + Scraper captures businesses (SAME ZIP) → cross-match → "Fiber
Green Biz" tab → dedupe by phone → load into the GHL Command power dialer (round-robin 5 reps).**

- **precise_fiber_hunter.py (the Fiber Hunter).** Playwright drives the AT&T dealer map
  (`youachieve.att.com/yourefer/fiber`) in a saved-login Chromium profile (`att_profile/`,
  logged in once via `--login`). It does NOT read the map object (fully hidden — no
  mapboxgl global); instead **`NetCapture` (`page.on("response")`) grabs AT&T's `serviceability`
  JSON off the wire** and decodes it with `optimus_api_capture.extract_features` (address/lat/
  lng/status; address must match `\d+\s+\S+`); it also decodes non-basemap Mapbox vector tiles.
  Manual run: position the map, press Enter → **`sweep_backend()` drags the map canvas cell-to-
  cell** across a grid (`mouse_drag()` = the proven motion; arrow-keys/panBy do nothing on this
  site; the canvas can be in a frame, so `_map_canvas_box` searches page+frames and falls back
  to dragging the viewport region). Each cell triggers the serviceability fetch → captures
  GREEN (lead) + GOLD (copper upgrade) addresses → writes the **"Precise Fiber"** tab (Address,
  Dot Color, Captured At, Business, Phone); GREY (existing customer) is skipped. Batched
  `append_rows` (chunk 500) to dodge the Sheets 429 quota. Heartbeats → **"Hunter Status"** tab.
  `self_update()` is the first line of `main()` (git pull + re-exec once; guard `OPTIMUS_NO_UPDATE=1`).
- **THE IN-HUNTER CROSS-MATCH (the money step).** As the hunter captures each GREEN/GOLD
  address it matches it against the scraped businesses, loaded once into an in-memory dict keyed
  by normalized address (`_norm_addr` = HOUSE|STREET-CORE; strips unit/city/zip, standardizes the
  suffix). Hits write live to **"Fiber Green Biz"** (green dot + biz) / **"Upgrade Orange Biz"**
  (gold). Hooks: `init_bizmatch(ws)` (once in main), `match_leads_to_biz(new)` (per flush),
  `_backlog_match()` (one-time pass at startup over `precise_addresses.jsonl` so dots captured
  BEFORE the scraper ran still match). Match = O(1) dict lookup. **KEY CONSEQUENCE: the match
  runs at hunter STARTUP — so scrape a ZIP first, THEN (re)start the hunter to convert the dots.**
- **maps_scraper_standalone.py (the Maps Scraper).** Standalone Playwright Google-Maps scraper
  (reads Google's hidden JSON list feed). Prompts for ZIPs, embedded category sets
  (Light ~20 / Heavy ~47 / Deep ~155), **headless by default** (`headless=not SCRAPER_SHOW`),
  writes the **"Maps Businesses"** tab (or CSV if no Google key). VERSION-stamped, self-updates
  from GitHub raw. Deep mode is slow (155 categories/ZIP) — that's why it can sit on one ZIP for
  hours; use Heavy for speed.
- **Supporting scripts (all in `optimus/`):** `optimus_api_capture.py` (`extract_features`, the
  serviceability JSON reader) · `optimus_dot_detect.py` (pixel dot-colour RGB windows) ·
  `enrich_phones.py` (OSM→Google-Places phone lookup → "Enriched Leads") · `business_score.py`
  (rank/score, drops no-phone/customer) · `ghl_loader.py` (→ GHL contacts + AT&T Commercial opps
  + power-dialer workflow) · `dialer_loader.py` (reads the green-biz tabs → ghl_loader, round-
  robins owners, `--reassign`) · `commercial_split.py` (commercial vs residential) ·
  `fiber_zone_scanner.py` / `fiber_precise_pipeline.py` (headless ZIP scanners) · `optimus_targets.py`.

### 11b. Distribution (how the team installs — built/finalized this session)
- **`optimus/install/INSTALL_OPTIMUS.bat`** = ONE installer for BOTH programs: installs Python
  from python.org (PrependPath=1, dodges the Microsoft-Store "python not found" trap), pulls the
  Hunter (repo zip) + Scraper (raw .py) from the **public** GitHub repo, installs deps + chromium
  + the Google service-account key (public Drive link, so NO Drive access needed), and creates the
  **two Desktop icons** (Optimus Fiber Hunter + Optimus Maps Scraper). All 12 python scripts ship
  inside `optimus_hunter`. Re-run to refresh; programs also self-update each launch.
- **Click-to-download release link (built this session via a GitHub Action).** Pure GitHub raw
  `.bat` links open as text in a browser (annoying), and the GitHub MCP has no create-release
  tool — so I committed `.github/workflows/make-installer-release.yml` (uses
  `softprops/action-gh-release`) which, on push, publishes/updates the **"installer" release** with
  `INSTALL_OPTIMUS.bat` attached as a real downloadable asset. Verified live (HTTP 200,
  application/octet-stream). Permanent team link:
  `https://github.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/releases/download/installer/INSTALL_OPTIMUS.bat`
  (release page: `.../releases/tag/installer`). The Action re-publishes the same link whenever the
  installer changes, so the link never goes stale.
- Drive copies of the install instructions: Google Doc "Optimus Fiber Tools — Install (Link +
  Instructions)" (id `1KAb8SftkL3zD42iO68MV8Ulc4DnVTZ4Q_omfMdccCFg`) and the full operating guide
  "Optimus Fiber Pipeline — Handoff & Operating Guide" (id `1rqnrNS8h2mk6O31NLbN9Z-G0VhAzmQJR01OMHZaKEzo`).

### 11c. How to ANALYZE the data (the method used this session)
- Read the leads sheet (`1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA`, "ATT FIBER LEADS") via
  Drive `download_file_content` with `exportMimeType: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  → save base64 → parse with python/openpyxl (too big to read inline; CSV export only returns the
  FIRST tab, so use xlsx for all tabs).
- **Real match count = dedupe "Fiber Green Biz" by the LAST 10 DIGITS OF PHONE.** That tab has
  thousands of duplicate rows (the hunter re-writes each match every sweep); raw row count ≠ leads.
- **Where to scrape next:** hunter dot addresses are STREET-ONLY (no ZIP), so group GREEN dots by
  street name to find dense clusters; group "Maps Businesses" by ZIP (their addresses carry ZIPs)
  to see scraper coverage. GAP = many dots + few scraped = best target. Confirmed top gap =
  **77046 Greenway (~1,500 dots, only ~12 scraped)**, then 77024 / 77092 / 77098.
- Hunter health from "Hunter Status": `"continuous: N cells, 0 leads"` = parked in a built-out
  all-grey area (move it); high lead counts = fresh fiber (good).

### 11d. This session's actions / state
- **Loaded green-biz matches into the Command dialer via MCP** (upsert_contact + assignedTo
  round-robin across the 5 reps + add_contact_to_workflow `41e00387` + pitch note): +16 then +77,
  bringing the loaded pool to ~215. Round-robin reps: `jBmInXreGR2oskVXax0h`/`lQ7gVrSONTWMAv4ZsEdO`/
  `7c9QLWsTDyTALTMj0ast`/`J3PkeoYp8TNXMNNcaN4l`/`qOa2OVzPabolfU9xjVXM`.
- **Match count:** 138 → 215 → **217 unique** (last confirmed). Almost all came from re-scraping
  **77027** (deep, 477 → ~1,030 businesses). Dots grew to **76k+** but matches stay flat until the
  scraper covers a NEW dot-rich ZIP — the scraper was **stalled** (Maps Businesses frozen ~3,624).
- **DIALER MISTAKE + RULE (important).** Another chat mistakenly loaded ~**1,328 raw scraped
  businesses from the "Maps Businesses" tab** (which contains NON-Houston data — OKC 405/580 ZIP
  73102, New Orleans 504 ZIP 70112/70114) into the Command power dialer. That chat reversed it via
  `remove_contact_from_workflow` (it kept its enrolled-id "fb_rem" files). **HARD RULE: load the
  dialer ONLY from "Fiber Green Biz" (fiber-matched leads), NEVER from "Maps Businesses" (raw
  scrape, includes other cities).** The scraper's non-Houston rows should be cleaned out of that tab.
- **Drive MCP gets "session expired" on a long chat** (token goes stale and won't refresh) — when
  the sheet read keeps failing, the fix is a FRESH chat, not retrying. The GHL connector stays fine.

### 11e. SESSION 2026-07-01 — hunter "stopped panning" diagnosed + fixed, tester + backend monitor built

> **TODAY'S PROBLEM (2026-07-01):** the precise hunter "stopped / won't pan / motion feels slower"
> (Patrick AND Ara hit it), and matches have been flat. The map isn't visibly moving when it should
> be sweeping.
>
> **WHAT WE PROVED:** it's NOT a code change — the hunter's last edit was 2026-06-18 and the working
> tree is clean (nobody touched it). And the sweep loop can't stall on its own (it fires a drag every
> cell forever until the browser closes). So "stopped panning" = the drag IS being issued but the MAP
> ISN'T MOVING → a GESTURE failure, or AT&T changed their site.
>
> **HOW WE'RE CORRECTING IT (the loop, agreed with Patrick):**
> 1. Hardened the pan gesture + added portal auto-recovery in code (pushed — see below).
> 2. Built `att_test.py` (RUN_TEST.bat) — a PASS/FAIL health-check whose `PAN MOVES` line settles
>    "us vs AT&T" in 30s.
> 3. Baked a **backend F12 monitor** into the hunter that writes what the map does on the wire to a
>    **"Backend Capture"** sheet tab. **THE WORKING LOOP: Patrick runs the hunter → Claude READS the
>    Backend Capture tab (via Drive MCP) → uses the real endpoint/pan-fetch signal to build sturdier
>    motion,** instead of guessing. Next time: read that tab first, check if the serviceability
>    fetch's hit-count CLIMBS per pan (motion working) or is FLAT (pan not triggering the fetch →
>    retune drag/timing), and whether the dot endpoint got renamed.
> 4. Researched + added the `mapbox-extraction` skill (recover the hidden map object) as the path to
>    retire pixel/tile guessing entirely.
>
> **SPEED IS ALSO CRITICAL (Patrick, 2026-07-01) — motion must be FAST *and* sturdy, not one or the
> other.** So: (a) the pan-gesture holds I added are only ~100ms/pan — keep them (they're what makes
> the drag land) but don't add more. (b) The backend monitor now writes in a BACKGROUND THREAD
> (`_backend_busy` skip-if-in-flight) so the F12 snapshot NEVER stalls the sweep — the sheet write is
> off the hot path. (c) Real speed tuning is DATA-DRIVEN from the Backend Capture tab: find the
> MINIMUM `SEARCH_SETTLE`/`WAIT_AFTER_PAN` at which the serviceability hit-count still climbs per pan
> (fetch still fires), and set pacing to that floor — don't guess (too-tight caused the old
> "captured 0"). Per-cell budget today ≈ SEARCH_SETTLE(0.3) + drag(~0.3) ≈ 0.6s + flush; shave via
> the backend signal, not by removing the holds. Recovering the hidden map object (mapbox-extraction
> skill) is ALSO a speed win — one `querySourceFeatures` read per view beats per-cell pixel scans.

- **"Precise hunter stopped / won't pan / slower" (Patrick + Ara saw it) is NOT a code change.** Git
  history confirms: the hunter's last change was **2026-06-18** (`02ba61a`), working tree clean, no
  local edits, and the last MOTION change was 2026-06-17. Nobody touched it. So the breakage is
  external (AT&T site) or environmental (Scout sharing `att_profile`, stuck Chromium, all-grey area).
- **KEY INSIGHT — the sweep loops can't stop themselves.** `sweep_continuous`/`sweep_grid`/
  `sweep_backend` fire a drag EVERY cell and only quit when `mouse_drag` returns False, which only
  happens when the browser is CLOSED (`page.mouse` throws). `_viewport_map_box` always returns a box,
  so mouse_drag never returns False for a "missing canvas." Therefore "stopped panning" = the drag is
  STILL being issued but the MAP isn't moving in response. It's a GESTURE failure, not a dead loop.
- **PAN GESTURE HARDENED (pushed `3177221`).** Root cause candidate #1: the drag was a too-fast flick
  (`down → move(steps=4) → up`, no hold) which Mapbox can read as a CLICK (pans nothing) instead of a
  drag. FIX in `mouse_drag`: hold ~60ms after `down` so the grab registers, move in TWO staged
  segments while held (`steps=6` each), settle ~40ms before `up` so the pan commits. Same distance
  (`DRAG_FRAC=0.45`), just an unambiguous drag now.
- **PORTAL AUTO-RECOVERY (same commit).** Root cause candidate #2: if a "Search this area" click lands
  on nav the view flips map→portal, and every drag after that hits the portal (doesn't pan) forever.
  FIX: `sweep_continuous` + `sweep_grid` now re-check `on_map` each cell and call `open_map_view()` to
  flip back if it's on the portal (prints `(view flipped to portal -- re-opening the map)`).
- **STILL UNPROVEN from the sandbox:** whether AT&T changed their site (candidate #3 — the
  screen-region drag fallback landing off a shifted layout). That's what `att_test.py` answers.
- **`att_test.py` — AT&T MAP HEALTH CHECK (us vs them), pushed `f3a82c4`.** Reuses the hunter's OWN
  helpers (open_map_view/on_map/_map_canvas_box/find_map_dots/mouse_drag/search_this_area/NetCapture)
  to run a PASS/FAIL checklist: PAGE LOADS · LOGGED IN · MAP OPENS · MAP CANVAS · DOTS RENDER · PAN
  MOVES (screenshot-hash before/after a drag) · SEARCH CONTROL · SERVICEABILITY FEED. Prints a VERDICT
  naming the culprit (THEM/login, likely-THEM map change, PAN broke, feed renamed, or ALL-CLEAR),
  writes an **"AT&T Test"** sheet tab + `att_test_report.txt` + dumps every endpoint to
  net_responses.log (so a renamed dot feed shows). Launcher `optimus/install/RUN_TEST.bat`. Run it
  ALONE (shares att_profile). One-paste curl of RUN_TEST.bat in chat. **If PAN MOVES still FAILs after
  the gesture fix → it's AT&T's layout; re-anchor the drag region.**
- **BACKEND F12 MONITOR baked INTO the hunter (pushed `5508df9`) — Patrick's "add it to the program,
  I don't wanna install anything else."** New `dump_backend(ws, cap)` writes the live NetCapture state
  to a **"Backend Capture"** tab (overwritten each pass): every endpoint the map hit (biggest first =
  the dot/address feed), the vector-tile FIELD names (dot schema), and #addresses parsed off the wire
  + samples (status/lat/lng). Fires early (cell 4) then every 15 cells in BOTH sweeps, next to the
  status heartbeat. **ON by default** (`--no-backend` off); NetCapture already runs `debug=True` so
  `seen_urls`/`tile_keys` populate. So Claude reads the backend from the sheet — no screenshot, no F12.
  (The standalone `backend_probe.py` still exists but the in-hunter monitor is the no-extra-install path.)
- **MATCH OUTPUT UNIFIED across hunter + scraper (pushed `be5eb13`).** Confirmed BOTH programs run
  IDENTICAL matching (same `_norm_addr` HOUSE|STREET key, same "Fiber Green Biz"/"Upgrade Orange Biz"
  tabs, same `["Business Name","Phone","Address","Website","Category"]` header + row, same green/orange
  split + dedup-by-address). Patrick's guess that the scraper lacked matching was WRONG — the scraper's
  `init_match()` reads the "Precise Fiber" tab and `_match_new()` matches each scraped business; the
  hunter's `init_bizmatch()`/`match_leads_to_biz()` matches each captured dot. They match from opposite
  ends into the SAME tabs. Only the console WORDING differed; now both print `COMBO MATCH ON: …` on load
  and `MATCH  +N green (fiber lead + business), +N orange (upgrade + business)  [total matches: T]` per
  hit, with a running total.
- **LIVE RUN 2026-07-01 (Patrick's screenshots) — two real causes of "it stopped," both now fixed.**
  Console showed the sweep panning (PAN right/down/left/up) but EVERY drag "from (683,384)" (same
  point) and the total FLATLINED at 13 after cell 4 (`+11`, `+2`, then `+0,+0,+0`), with several
  "(no 'search this area' control found this view)". That's the map NOT actually moving on the
  too-fast flick = the OLD pan code (the run predated the gesture fix). ALSO: the `[none]/[cache]`
  spam in the log = the background **enrichment thread**, which ALSO writes to the sheet, so it
  competes with the sweep for the Sheets write quota (60/min) → 429 throttle → the flush stalls →
  looks frozen. FIXES: (1) hardened pan gesture (already pushed) makes the drag actually pan; (2)
  **enrichment is now OFF by default** (opt-in `--enrich`) — it was low value anyway (captures in the
  shot were a single commercial building `605 NW 13TH ST` with many suites, all "no phone"; houses
  have no free phone; business phones come from the scraper match). Patrick's instinct that "the free
  enrichment is messing things up" was PARTLY right — it wasn't the pan stall, but it was a real
  sheet-quota/stall + console-noise source. Patrick must RESTART to pull all of it (his run showed old
  "business match ON" wording). NOTE he was hunting **OKC 73106 (NW 13th St), not Houston** — fine for
  proving capture, but those matches must NOT feed the Houston dialer.
- **OKC IS A REAL MARKET (Patrick, 2026-07-01: "we do lots of biz there").** He ran the scraper on
  **73106 (Oklahoma City)** from a different PC and noticed the "alternative ZIPs" (the auto-advance
  list) were missing/different. Cause: the scraper's auto-advance `NEXT_ZIPS` was hard-coded to
  **Houston** (77027, 77098, …), and `maps_zips_done.json` is per-machine (fresh PC = no memory).
  Entering an OKC ZIP would have rolled straight into Houston ZIPs → mixing both cities in
  "Maps Businesses" → polluting the Houston dialer. FIX (pushed): scraper auto-advance is now
  **region-aware** — `region_for(zip)` picks the metro from the first ZIP entered: `HOUSTON_ZIPS`,
  new `OKC_ZIPS` (OKC/Edmond/Norman/Moore/MWC), or NO auto-advance for an unknown metro (scrape only
  what's typed). Houston stays Houston, OKC stays OKC. **OPEN / NEXT DECISION:** OKC green-biz matches
  still land in the SAME "Fiber Green Biz" tab and `dialer_loader` loads that into the **Houston**
  Command GHL (Houston reps). So OKC needs its OWN dialer lane — its own GHL sub-account/reps, or at
  minimum a city tag + a separate load — before OKC matches get dialed. Don't feed OKC into the
  Houston power dialer. (Patrick to say whether OKC has its own GHL account/team.)
- **SCRAPER SPEED — research + roadmap (Patrick asked "can it go faster?", 2026-07-01).** Current
  standalone scraper is Playwright, SEQUENTIAL, and its #1 time sink is the **per-place `page.goto(href)`**
  (`scrape_query` lines ~210-230): for EVERY business it navigates to that business's Maps page (wait
  1100ms) just to read phone/website. Deep=155 categories/ZIP × ~20 places each = thousands of page
  loads. **IMAGE-BLOCKING now OPT-IN after a research check (`bc9de4f`, supersedes `d8eddf7`).**
  Patrick pushed back ("the popular OSS one doesn't do it for a reason"). Verdict: resource-blocking
  IS mainstream (omkarcloud's **Botasaurus** ships `block_resources`; ~4s/12MB to ~1s/100KB) BUT
  anti-bot guidance flags it as a **bot-detection metric** (a real browser loads images; one that
  never does looks automated) and **Google Maps is an aggressive detector**; gosom doesn't rely on it
  (its speed = Go + concurrency). The proven scraper works WITHOUT it, so it's gated behind
  **`SCRAPER_BLOCK_IMAGES=1`, default OFF** (unchanged behavior); opt in to test + watch for blocks.
  LESSON: validate a speed hack against real anti-bot experience before defaulting it on.
  **IMMEDIATE, zero-code:** use **Heavy (47 cats)** not **Deep (155)** → ~3x fewer searches. **Bigger
  levers (need live testing — can't test scrapers from the sandbox, Google 403s here):** (1) **read
  phone/website from the search feed's embedded JSON** (`APP_INITIALIZATION_STATE` / the pb-protobuf
  nested-array) instead of visiting each place page — kills the per-place goto entirely = the biggest
  win AND fewer requests; this is how the fastest tool works. (2) **Concurrency** — parallel place
  visits via multiple pages/contexts (async Playwright, 5-10x) BUT raises block risk. (3) trim the
  fixed waits (2500/1400/1100ms). **Fastest existing OSS = `gosom/google-maps-scraper` (Go)** — reads
  Google's internal JSON, `-c` concurrency flag; but needs Go/Docker (team can't easily). Python OSS:
  `omkarcloud/google-maps-scraper` + `botasaurus` (async/parallel). Sources: scrap.io GH scraper guide,
  serpapi pb-decoder, scrape.do tbm=map JSON. Decision on the big rewrite (embedded-JSON vs concurrency)
  deferred; resource-block + Heavy-mode are the wins for now.
  **>>> PARKED (Patrick, 2026-07-01: "put this in the brain, mess w it later"). Current state = the
  scraper is left as its PROVEN, reliable self (image-blocking OFF by default; Deep stays for full
  coverage — Patrick wants ALL businesses, not fewer categories). Nothing more shipped. WHEN WE
  RESUME: the ONE safe speedup that keeps full Deep coverage AND doesn't raise block risk is the
  embedded-JSON read (read phone/website from the search page's `APP_INITIALIZATION_STATE` instead of
  visiting each business page). Build it as a FAST-PATH-WITH-FALLBACK (if the JSON read fails, fall
  back to the current per-place visit so it can't lose/false data), and VALIDATE on one test ZIP
  (compare JSON-path phones vs per-place phones) BEFORE making it default. Do NOT blind-ship a Maps
  JSON parser (wrong-phone risk). Concurrency + wait-trims raise block risk — lower priority. <<<**
- **"WE'RE GOING TO BE WORKING EVERYWHERE" (Patrick, 2026-07-01).** The pipeline must scale to MANY
  metros, not just Houston/OKC. Already handled: the scraper's `nearby_zips` fallback means ANY ZIP in
  ANY metro auto-advances outward (Houston/OKC just have hand-tuned curated orders on top). Confirmed
  live: entering **73132** → `Metro: Oklahoma City` + plan `73132, 73106, 73103, … +83 more` (all OKC,
  no Houston bleed). **OPEN SCALABILITY GAP (flag before multi-city dialer loads):** all cities pile
  into the SAME "Maps Businesses"/"Fiber Green Biz" tabs, so the wrong city's leads can reach the wrong
  team's dialer. Separation is currently enforced by hand at load time — won't scale. Clean fix =
  **tag every scraped row + match with its market (ZIP/city)** so each dialer filters to its own city
  (needs a new column + a `dialer_loader` update to read it). Offered; Patrick to say now vs. when the
  2nd city gets a dialer.
- **NATIONWIDE VISION (Patrick, 2026-07-01) — PARKED, build later.** Goal: take the software
  nationwide to auto-find two "buy-now" signals and point the hunter/scraper at them: (1) **new AT&T
  fiber** just lit, and (2) **cable-ISP outages** (Comcast/Spectrum/Cox down = frustrated customers
  ready to switch). Architecture = NATIONAL SIGNALS → target queue → hunter + scraper (the region
  system built today, Houston/OKC, is the seed — generalize the ZIP→metro registry to all metros).
  Research done 2026-07-01: **new-fiber signal is buildable for free** via the **FCC National Broadband
  Map / BDC API** (`broadbandmap.fcc.gov`, `broadbandmap.com/developers`) — query provider + technology
  (fiber/cable/DSL) by location nationwide → find where AT&T fiber is newly available + where cable is
  the only option (the `fiber-signals` skill already documents BDC). **Cable-outage signal** = harder:
  **Downdetector** is the gold standard (ZIP-level, ~60s refresh) but its API is **PAID** + Cloudflare-
  protected (unofficial scrapers unreliable); free alternatives = provider status maps (Xfinity/
  Spectrum/Cox) + Reddit/X outage chatter (coarser). DECISION on the outage data source (free signals
  vs paid Downdetector) deferred. **What Patrick DID want now (done):** the scraper keeps going to the
  "next logical place" after the curated metro — `nearby_zips()` auto-advances to the numerically
  nearest ZIPs (same/adjacent SCF = geographic), expanding outward, so it never just stops. When the
  nationwide build resumes, start with the FCC new-fiber engine (free, clear value), then revisit the
  outage source.
- **NEW SKILL `mapbox-extraction` (researched + added 2026-07-01).** Codifies how to pull
  dot/feature data off a Mapbox map that HIDES its instance — the exact AT&T dead-end the brain
  called "IMPOSSIBLE." Research finding: it is NOT impossible; the standard escape hatches are (1)
  a **constructor hook** via `page.add_init_script` wrapping `mapboxgl/maplibregl.Map` so instances
  self-register (only works if a global is ever set — AT&T's bundle sets none), and (2) for a
  BUNDLED build with no global, a **canvas `getContext` hook + React-fiber walk**: catch the WebGL
  canvas as Mapbox creates it, then BFS the React fiber tree near `.mapboxgl-map` for the object
  that has `queryRenderedFeatures`+`getStyle`, register it to `window.__optimusMaps`, then read via
  `querySourceFeatures` (all loaded-tile features, more complete than queryRenderedFeatures) +
  `m.project()` for each dot's exact pixel. Hooks MUST be injected BEFORE `page.goto`. Fallbacks
  stay: network capture (the floor, always works — dots crossed the wire) + `mapbox-vector-tile`
  protobuf decode (tile-local→lng/lat web-mercator). NEXT worth trying on AT&T: inject the
  getContext+fiber-walk recovery to see if the hidden map becomes readable (would beat pixel/tile
  guessing). Skill file: `.claude/skills/mapbox-extraction/SKILL.md`.
