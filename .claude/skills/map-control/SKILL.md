---
name: map-control
description: How Claude drives the AT&T dealer fiber map (Mapbox GL JS on OpenStreetMap tiles), captures lead data, saves it to Google Drive/Sheets, reads it back, and acts on it in GoHighLevel. Use this when building or running the closed loop of Claude controlling the map, the captured data feeding back to Claude, and storage/integration across Drive, Google APIs, and GHL.
---

# Claude-controlled map → Drive → GHL loop

This is the architecture for "Claude controls the map, the data feeds back to
Claude, and it's saved on Drive." Most of it already exists in `/optimus`;
this skill keeps the design honest and repeatable.

## What the map actually is (research-confirmed)
- The dealer map is **Mapbox GL JS** rendering **OpenStreetMap** street tiles.
  The streets are OSM; the **fiber dots (green/gold/grey) are AT&T's own data
  layer**, not OSM. So OSM/Overpass/Nominatim do NOT give fiber data or unit
  numbers — the fiber truth lives in AT&T's backend + the popup.
- `queryRenderedFeatures` / `querySourceFeatures` only return features in the
  **currently loaded viewport tiles**, and truncate at tile boundaries. You
  cannot dump a whole city in one call — hence pan/zoom (precise_fiber_hunter)
  OR read the backend tile/JSON endpoint (fiber_precise_pipeline --api-substring).

## The loop (each arrow already has a tool)
1. **Claude controls the map** — Claude Code on the HP drives **Playwright**
   (headful, persistent profile `att_profile/` keeps the AT&T login). It pans
   with arrow keys, clicks "Search this area", reads dots. This is
   `precise_fiber_hunter.py` (+ `--fresh`) and `fiber_precise_pipeline.py`.
2. **Capture** — addresses from the Mapbox geo features (`queryRenderedFeatures`
   via the page hook) or the backend JSON; lat/lng included.
3. **Enrich** — `enrich_phones.py` → Google **Places API** attaches business
   name + phone (the Google Cloud billing Zack is setting up).
4. **Save to Drive** — tools write the **"Precise Fiber" Google Sheet**
   (gspread + `google_creds.json`) and local `*.jsonl`. Artifacts also live in
   the Drive "Optimus Installer" / project folders.
5. **Data feeds back to Claude** — a chat session reads the Sheet/Drive via the
   **Sheets + Drive MCP connectors** (read the captured rows, summarize, QA).
6. **Act in GHL** — `ghl_loader.py` (or the **GHL MCP**) upserts contacts +
   AT&T Commercial opportunities and enrolls them in the power-dialer workflow.

## Integration inventory (what's already connected)
- **GHL MCP** — contacts, opportunities, workflows, SMS/email (used live).
- **Google Sheets + Drive MCP** — read captures, write/organize files.
- **Google APIs** — Places (phones, billed via Zack's Cloud project),
  Sheets/Drive (storage), all keyed by env vars / `google_creds.json`.
- **Windsor MCP** — GHL analytics if reporting is needed.
- Secrets live in env / the HP's `~/Optimus/`, never in the repo or on Drive.

## Two control modes — pick per task
- **Autonomous (Claude Code + Playwright on the HP):** Claude writes/runs the
  pan-click-capture itself. Best for ad-hoc or new areas. Keep the session
  headful + persistent so the login survives.
- **Scripted (the committed tools):** `precise_fiber_hunter.py` etc. run the
  same loop deterministically on a schedule. Best for the weekly run. Prefer
  this for volume; reserve live Claude-driving for exploration/debugging.

## Gotchas (learned, don't relearn)
- Viewport-only queries → you MUST pan/zoom or hit the backend; no single dump.
- The popup is the only **unit-level** address source (OSM has no units).
- Map/skip-traced output = door-knock + DNC-scrubbed manual call only; never
  cold-text. Places gives a phone, not consent.
- A live run needs the HP (real browser + logins); the build container can only
  test pure logic.

### Live-confirmed on the HP (2026-06-13) — don't relearn
- **URL:** the map renders **in-page at `youachieve.att.com/yourefer/fiber`**
  (same URL as the portal). A fresh load lands on the PORTAL; the dot map is
  behind a **"Fiber Availability Map"** button — `open_map_view()` clicks it.
- **Automated Chromium shows the DOTS but NOT the basemap tiles.** That's
  normal and fine — the hunter reads dot color + popup, never the street
  imagery. "Just dots on white" = working, not broken.
- **Login** is captured once via `--login` into the persistent `att_profile/`
  profile; after that the scan browser is already signed in.
- **Popup format confirmed:** `FIBER ELIGIBLE` / `Address: 8 GREENWAY PLZ UNIT
  1111` / `CREATE REFERRAL` — matches the parser's ADDRESS_REGEX exactly.

## Improvements roadmap (researched 2026-06-13) — best first
1. **Network capture (biggest win).** The dots come from an AT&T backend
   request. Attach a Playwright `page.on("response")` listener that watches for
   that endpoint and dumps its JSON — you get **every** address + lat/lng +
   status for the loaded area in one shot, no clicking, no popup parsing, and
   it doesn't care that the basemap didn't paint. This is the robust version of
   `fiber_precise_pipeline --api-substring`, folded into the hunter as a passive
   listener. To find the endpoint: run with the listener logging every response
   URL, pan once, and grep the URLs that fire when dots load.
2. **`querySourceFeatures` over `queryRenderedFeatures`.** querySourceFeatures
   returns features even when hidden/overlapped (more complete), at the cost of
   needing dedup across tiles — pair it with the existing address de-dupe.
3. **Auto-snake until empty.** Keep panning a FRESH cluster until no NEW
   addresses appear, instead of a fixed cols×rows grid, so zone edges aren't
   missed.
4. **HAR fallback.** If the endpoint is obfuscated, record a HAR of a manual
   pan and read the dot payloads out of it offline.
