---
name: web-scraping
description: Reliable browser automation and data extraction for the map tools (Playwright on the AT&T/Mapbox map) — network-response capture, vector-tile decoding, anti-bot/stealth realities, and stability for long scraping runs. Use when building or debugging the precise hunter / fiber hunter / any Playwright capture, deciding how to pull data off a JS map, or hardening a scrape against blocks and flakiness.
---

# Web scraping & browser automation (for the map tools)

How to get data off a JavaScript map reliably. Ranked by what to reach for first.

## Get the DATA, not the pixels (preference order)
1. **Backend JSON via network capture (best).** The dots come from an AT&T
   backend request. Attach `page.on("response")` and parse the JSON — every
   address + lat/lng + status in one shot, no clicking, basemap-independent.
   Built as `precise_fiber_hunter --net`; `--api-substring` pins the endpoint
   once you see which URL returns leads. Parser: `extract_leads_from_json`.
   - Find the endpoint: run `--net` with no substring; it prints every URL that
     returned leads. Pick the AT&T one, re-run with `--api-substring`.
2. **Mapbox map object** (`queryRenderedFeatures` / `querySourceFeatures`) — the
   page-hook geo path. Viewport-tile-only and truncates at tile edges, so pan.
3. **Decode vector tiles** (`mapbox_vector_tile` / `vector-tile-base`, pip) if
   you capture raw `.mvt`/pbf tiles — point/line/poly as x/y relative to the
   tile's top-left; reproject to lng/lat. Use only if 1–2 fail.
4. **Click + read popup (last resort).** Slow (one dot at a time) and the only
   **unit-level** source when the data layer lacks it. The hunter's retry-spiral
   click path is the fallback.

## Reliability for long runs
- **Persistent context** keeps the login (`att_profile/`); auth survives ~hours
  and re-extends. Re-`--login` only when it expires.
- **Poll, don't sleep.** Wait for a condition (popup ready, response seen), not a
  fixed delay — see `wait_for_popup`. Fixed sleeps are slow and flaky.
- **Decouple slow work.** Never block the scan on enrichment/lookups (a timeout
  would stall it). Capture writes a file; `enrich_phones --watch` runs separately.
- **Resume + dedupe.** Re-runs skip already-captured rows (sheet/JSONL) so a
  crash is cheap. Keep the per-run `seen` set.
- **Throttle outbound** (Overpass ~1 req/s; paid Places metered) to avoid blocks
  and surprise cost.

## Anti-bot reality (don't overspend effort here)
- This map is a logged-in dealer tool, not a hostile anti-bot target, so heavy
  evasion is unnecessary. Keep it **headful + persistent + human-paced**.
- If a site does block: `playwright-stealth` (Python, maintained) hides obvious
  signals (navigator.webdriver, WebGL/codec fingerprints) **before page scripts
  run** — but it does NOT fix IP reputation, TLS fingerprinting, or behavioral
  analysis. Volume that's fine at 100/day fails at 10k/day on rep alone.
- We do not evade carrier/anti-bot to do anything abusive; capture feeds
  door-knock + DNC-scrubbed manual call only.

## Gotchas (learned)
- Automated Chromium shows the AT&T dots but not the Mapbox basemap tiles —
  fine, the tools read dots/data, never the street imagery.
- The map renders in-page behind a "Fiber Availability Map" button
  (`open_map_view`); a fresh load lands on the portal.
- Live runs need the HP (real browser + logins); the build container only
  unit-tests pure parsing.
