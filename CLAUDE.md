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
