# OPTIMUS Fiber Capture — Problem, Findings & Solution (AI handoff)

> Self-contained. Hand this to any AI/engineer to continue. Repo:
> `patricksiado-prog/Go-High-Level-MCP-2026-Complete`, branch
> `claude/optimus-map-tools-setup-6dcl6o`, code in `/optimus`.

## GOAL
From the AT&T dealer fiber map (`https://youachieve.att.com/yourefer/fiber`),
capture every **GREEN** (fiber-eligible non-customer = LEAD) and **GOLD**
(copper-upgrade) dot's exact **street address + lat/lng** into a Google Sheet
(id `1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA`, tab "Precise Fiber"), with
**NO clicking each dot**. GREY = existing fiber customer = skip.

## THE SITE — hard constraints (verified live 2026-06)
1. Fresh load = a PORTAL page; the map is behind a **"Fiber Availability Map"** button.
2. The basemap is Mapbox tiles, **but the map object is FULLY HIDDEN**. A live
   per-frame probe returned `hookedMaps:0`, `window.mapboxgl=false`,
   `window.maplibregl=false`, no reachable map instance in any frame. So
   `queryRenderedFeatures()` / `getSource()._data` are **impossible here** — do
   NOT spend time trying to read the map object.
3. The dots come from AT&T's **`serviceability` JSON endpoint** (the response URL
   contains `serviceability`). This is THE data feed.
4. The **"Search this area" button only appears AFTER you move/pan the map.**
   Checking for it on a still view returns "not found." Clicking it makes AT&T
   fetch the serviceability JSON for the current view.
5. Each feature in that JSON carries the street **address** (`siteAddress` /
   `serviceAddress` / `address`), `lat`/`lng`, `status`, `ban`. Proven: the older
   tools pulled **thousands** of real addresses from it.

## WHAT WORKS (confirmed, not theory)
- Capture via Playwright `page.on("response")`: when AT&T sends the serviceability
  JSON, the listener gets it → `json.loads(body)` → `extract_features()` → addresses.
- **PROOF:** a live run hit Google Sheets `[429] quota exceeded - write requests
  per minute` errors. That only happens if it **captured real addresses and tried
  to write them.** The capture is working; the bug was writing too fast.
- **Fix applied:** batch the sheet writes — `ws.append_rows(rows, value_input_option="RAW")`
  in chunks of 500 — instead of `append_row` per address. Kills the 429.

## FILE MAP (/optimus)
- `optimus_dot_detect.py` — canonical dot-colour RGB windows (GREEN `30,130,30`–
  `100,210,80`; GOLD; GRAY), `classify_status`, `zone_freshness`, pixel dot-find.
- `optimus_api_capture.py` — `ResponseSniffer` (page.on response) + **`extract_features`**
  (schema-tolerant JSON → `{address, lat, lng, ban, status}`; address must match
  `\d+\s+\S+`). THE proven extractor.
- `fiber_precise_pipeline.py` (MapMan) — PROVEN end-to-end: `search_zip` (TYPE the
  ZIP) → serviceability fetch → ResponseSniffer captures → extract_features → sheet.
  Motion = `focus_map` (click the canvas at 18%/22%) then keyboard.
- `fiber_zone_scanner.py` — headless multi-instance ZIP scanner, same capture, run
  with `--api-substring serviceability`.
- `fiber_hunter.py` (ORIGINAL, in the separate public repo `optimus-map-tools`) —
  the first hunter: motion is a **MOUSE DRAG** (`pyautogui.dragRel(-150,0)` from map
  centre, serpentine), pixel-colour detection, a **hand-calibrated** "Search this
  area" click. KEY: the working motion is a DRAG, not arrow keys.
- `precise_fiber_hunter.py` — current main. `NetCapture` (page.on response +
  extract_features), manual WATCH mode (user pans by hand, flush every 6s), batched
  writes, Drive telemetry (log + screenshot + `serviceability_raw.json`).

## THE FIX / SOLUTION (what completes it)
1. **CAPTURE (done):** in `precise_fiber_hunter.NetCapture.handle`, json-parse any
   response whose content-type is json OR whose URL looks like data
   (`serviceability`/`api`/`graphql`/`availab`/`fiber`/`.json`), then run
   `extract_features(data)` (+ the local `extract_leads_from_json`).
2. **TRIGGER reliably (recommended add):** after the "Search this area" click, do a
   deterministic wait instead of polling:
   ```python
   try:
       resp = page.wait_for_response(
           lambda r: "serviceability" in r.url.lower() and r.status == 200,
           timeout=8000)
       feats = extract_features(resp.json())   # addresses for this view
   except Exception:
       pass
   ```
3. **MOTION for auto-pan (the real fix to "it's not moving"):** use Playwright
   **mouse drag** — arrow keys and `map.panBy` do nothing because the map object is
   hidden:
   ```python
   box = page.locator(".mapboxgl-canvas, .maplibregl-canvas, canvas").first.bounding_box()
   cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
   page.mouse.move(cx, cy); page.mouse.down()
   page.mouse.move(cx - 220, cy, steps=12)      # drag left = pan right
   page.mouse.up(); time.sleep(1.0)
   ```
   Then click "Search this area" (now present) → `wait_for_response("serviceability")`.
4. **WRITE (done):** batched `append_rows`.
5. **VERIFY accuracy:** the raw feed is saved to `serviceability_raw.json` — inspect
   it to confirm the address field name + that addresses are real for the area.

## RECOMMENDED CLEAN AUTO FLOW (port MapMan + drag)
```
open map (click "Fiber Availability Map")
search_zip(zip)                      # TYPE the zip -> first serviceability fetch
loop over a grid of N cells:
    mouse-drag to the next patch      # proven motion (NOT arrow keys/panBy)
    click "Search this area"          # now visible after the drag
    resp = wait_for_response("serviceability")
    rows += extract_features(resp.json())   # GREEN/GOLD -> rows; skip GREY by status
flush rows -> ws.append_rows(rows)    # batched, no 429
```
This is exactly what `fiber_precise_pipeline.py` already does **minus the drag** —
so the complete fix = MapMan's `search_zip` + `ResponseSniffer` flow, with a
mouse-drag for motion, inside `precise_fiber_hunter.py`.

## STATUS / OPEN
- Backend capture: **WORKING** (429 proved it). Writes: **fixed** (batched).
- Motion: manual (user pans) works now; **auto-pan needs the mouse-drag** above.
- **Unverified:** address *accuracy* — Claude can't see the sheet (Google AI-blocks
  it) and the Drive telemetry needs the folder shared (edit) with the service account
  `fiberscanner@fiberscanner-493900.iam.gserviceaccount.com`. Raw data to check is in
  `serviceability_raw.json` on the PC.
- Auth note: AT&T login expires periodically; re-login via
  `python precise_fiber_hunter.py --login`. Service-account key project =
  `fiberscanner-493900`.
