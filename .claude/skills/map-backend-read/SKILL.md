---
name: map-backend-read
description: How the precise fiber hunter reads AT&T map dots from the Mapbox backend (queryRenderedFeatures) and colours each dot by sampling its own pixel — no clicking, no whole-screen guessing, no portal flip. Use when working on dot capture, debugging why the hunter captures 0 or misclassifies dots, the map<->portal flip, or wiring the address/status read for the AT&T fiber map.
---

# Reading map dots from the backend (no clicking)

The proven, flip-free way to capture AT&T fiber dots. Learned the hard way
(2026-06-15) after the click path kept flipping the view to the portal.

## The legend (what the colors mean — this is the whole game)
- **GREEN** = fiber-eligible, NOT a customer yet → **the lead.** Write it.
- **GOLD** = has AT&T copper, can upgrade to fiber → also a lead. Write it.
- **GREY** = already an AT&T fiber customer → skip (counted, not written).
- A view that is ~all grey = **MATURE** (built-out); almost no leads. Move to a
  newer neighbourhood (lots of green/gold, little grey).

## Why NOT clicking / NOT whole-screen pixel detection
- **Clicking dots flips the view.** On a portal/transition frame the whole-screen
  pixel detector reads the portal's blue buttons as "dots", then `click_dot`
  clicks them → navigates the portal → oscillation. Also `focus_map()` (click an
  "empty" point) and the popup-close click landed on nav.
- **The basemap adds noise.** Once the street basemap renders (light, with roads
  + labels), whole-screen detection finds 100+ false "grey dots" and misses the
  real green ones. It reported `0 green + 183 grey` on a visibly-green view.

## The right architecture (precise_fiber_hunter.py)
1. **Find the map object.** `MAPBOX_HOOK_JS` wraps `mapboxgl.Map` at page-init
   and pushes instances to `window.__optimusMaps`. The user logs in + opens the
   map long after load, so the hook re-wraps for **30 minutes**. If the map was
   loaded as a module (not `window.mapboxgl`), `MAPBOX_DOTS_JS` also **searches
   page globals** for any object with `queryRenderedFeatures`+`project`.
2. **Read dot locations from the backend.** `MAPBOX_DOTS_JS` →
   `queryRenderedFeatures()`, keep POINT features whose layer id is NOT basemap
   (skip road/label/water/poi/building/admin/…). For each: exact pixel via
   `map.project([lng,lat])`, plus `lng/lat`, `props`, and the map container rect.
3. **Colour each dot at its OWN pixel.** `drain_viewport_backend` takes ONE
   screenshot; for each dot it samples a ±4px window at `(rect.left+x, rect.top+y)`
   with `classify_pixel` → GREEN/GOLD/GREY/None (RGB windows from
   `optimus_dot_detect`). This never guesses on random screen pixels, so portal
   buttons can't masquerade as dots. If a feature carries a `status` property,
   that wins over the pixel.
4. **Write GREEN + GOLD** to the sheet (address from `props` if present, else the
   `(lat,lng)` pin). Skip GREY.
5. **Pan programmatically.** `pan_map_js` uses `map.panBy(...)` (no mouse/keys →
   can't hit nav), then `pan()` clicks the map-scoped **"Search this area"**
   button to load the new cell's dots. Sweep a grid (`--cols/--rows`), no zoom.

## Run modes
- Default = backend read, no clicking. Launcher: `--cols 3 --rows 3 --fast`
  (position the spot, press Enter, sweep a 3x3 block).
- `--probe` → after you position the map, dumps every layer + dot-feature
  property to `probe.json`. **Run this first on a new map** to confirm the hook
  attaches and to see which layer holds the dots and whether props carry the
  address/status. Wire `FEATURE_ADDRESS_KEYS` / `FEATURE_STATUS_KEYS` from it.
- `--allow-click` → re-enable the legacy pixel-detect + click capture (has the
  flip risk; only if the backend hook can't attach at all).

## If it captures 0 / says "map backend not live"
- The hook didn't attach. Run `--probe`, read `probe.json`:
  - `hookedMaps: 0` and globals search empty → the map isn't reachable from the
    page context (module-scoped, or in an iframe → query the frame, not page).
  - Point features exist but on a basemap layer only → loosen the layer filter /
    pin the real dot layer id.
  - Dots found but all classify None → the dot RGB windows don't match this
    basemap; sample a dot's real RGB from `probe.json` coords + a screenshot and
    widen `GREEN/GOLD/GRAY_MIN/MAX` in `optimus_dot_detect.py`.
- Address not in props → it only comes from the popup (a click). Accept the
  `(lat,lng)` pin for door-knock/route, or gate a click read behind `--allow-click`.

## Hard-won rules
- Never click the page to "focus" or "close" — use JS focus / `panBy` / Escape.
- Colour dots at their exact projected pixel, never by scanning the screen.
- The popup is the only unit-level **street** address source; the backend gives
  status + lat/lng reliably, street text only if the feature carries it.

## Research notes (Mapbox GL JS, verified 2026-06-15)
- `queryRenderedFeatures()` returns **only features rendered in the current
  viewport**, and truncates at tile edges — so you MUST pan to cover an area
  (we sweep a grid). For features beyond the viewport, `querySourceFeatures(srcId)`
  exists but is still zoom/view dependent.
- Accessing a third-party map needs a **reference** to the instance — there's no
  global registry. Our two-pronged grab (wrap `mapboxgl.Map` for 30 min + search
  `window` for an object with `queryRenderedFeatures`+`project`) is the standard
  way; if both fail the map is module-scoped or in an iframe (query the frame).
- KNOWN BUG: `queryRenderedFeatures` can return nothing on the newer **"Mapbox
  Standard"** style (mapbox-gl-js issue #13332). If `--probe` shows a map but 0
  point features, try `map.querySourceFeatures(<sourceId from probe>)` instead,
  or read the source's GeoJSON data directly via `map.getSource(id)._data`.
- Sources: <https://docs.mapbox.com/mapbox-gl-js/example/queryrenderedfeatures/>,
  <https://github.com/mapbox/mapbox-gl-js/issues/13332>,
  <https://github.com/mapbox/mapbox-gl-js/issues/7802>
