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

---

# KEY CODE (paste-able; this is the heart of it)

## 1. The proven extractor — `extract_features` (optimus_api_capture.py)
Walks ANY JSON (flat dict, list, or GeoJSON `{geometry,properties}`) and pulls
out `{address, lat, lng, ban, status}`. The address must "look like" an address
(starts with a house number, regex `\d+\s+\S+`). This is what turns AT&T's
serviceability JSON into rows. Field-name candidates are below — extend
`ADDRESS_KEYS`/`STATUS_KEYS` if AT&T uses a different key.

```python
import re
ADDRESS_KEYS = ("address","formattedaddress","fulladdress","addressline1",
                "streetaddress","siteaddress","serviceaddress","addr")
LAT_KEYS = ("lat","latitude"); LNG_KEYS = ("lng","lon","long","longitude")
BAN_KEYS = ("ban","subscriberban","billingaccountnumber","billingaccount","accountnumber")
STATUS_KEYS = ("status","dotcolor","color","serviceablestatus","customertype",
               "customerstatus","fiberstatus","servicestatus","eligibility","markercolor")
_ADDRESS_SHAPE = re.compile(r"\d+\s+\S+")          # "13911 E CYPRESS ..."

def _norm_key(k): return re.sub(r"[^a-z]", "", str(k).lower())
def _get_first(d, names):
    for k, v in d.items():
        if _norm_key(k) in names and v not in (None, ""): return v
    return None
def _as_float(v):
    try: return float(v)
    except (TypeError, ValueError): return None
def _looks_like_address(v): return isinstance(v, str) and bool(_ADDRESS_SHAPE.search(v))

def extract_features(obj, out=None):
    if out is None: out = []
    if isinstance(obj, list):
        for it in obj: extract_features(it, out)
        return out
    if not isinstance(obj, dict): return out
    addr = _get_first(obj, ADDRESS_KEYS); lat = _as_float(_get_first(obj, LAT_KEYS))
    lng = _as_float(_get_first(obj, LNG_KEYS)); ban = _get_first(obj, BAN_KEYS)
    status = _get_first(obj, STATUS_KEYS)
    props = obj.get("properties")
    if isinstance(props, dict):
        addr = addr or _get_first(props, ADDRESS_KEYS); ban = ban or _get_first(props, BAN_KEYS)
        status = status or _get_first(props, STATUS_KEYS)
        if lat is None or lng is None:
            lat = lat if lat is not None else _as_float(_get_first(props, LAT_KEYS))
            lng = lng if lng is not None else _as_float(_get_first(props, LNG_KEYS))
    geom = obj.get("geometry")
    if (lat is None or lng is None) and isinstance(geom, dict):
        c = geom.get("coordinates")
        if isinstance(c, list) and len(c) >= 2 and _as_float(c[0]) is not None:
            lng, lat = float(c[0]), float(c[1])           # GeoJSON = [lng, lat]
    if lat is not None and not (-90 <= lat <= 90): lat = None
    if lng is not None and not (-180 <= lng <= 180): lng = None
    if _looks_like_address(addr):
        out.append({"address": re.sub(r"\s+"," ",addr).strip(), "lat": lat, "lng": lng,
                    "ban": str(ban).strip() if ban else None,
                    "status": str(status).strip() if status else None})
    else:
        for v in obj.values():
            if isinstance(v, (dict, list)): extract_features(v, out)
    return out
```

## 2. The capture (what precise_fiber_hunter does now)
```python
captured = []                                  # rows to write
def on_response(resp):
    try:
        url = resp.url.lower()
        ct  = (resp.headers or {}).get("content-type","").lower()
        if "json" not in ct and not any(k in url for k in
            ("serviceability","/api/","graphql","availab","fiber",".json")):
            return
        body = resp.body()
        if not body or len(body) > 8*1024*1024: return
        data = json.loads(body)
        for f in extract_features(data):
            captured.append(f)                 # f = {address,lat,lng,ban,status}
    except Exception:
        pass
page.on("response", on_response)               # attach BEFORE navigating
```

## 3. THE FIX — reliable trigger + the proven MOUSE-DRAG motion
Arrow keys and `map.panBy` do nothing here (map object hidden). Drag the canvas.
```python
def focus_and_drag(page, dx=-220):
    box = page.locator(".mapboxgl-canvas, .maplibregl-canvas, canvas").first.bounding_box()
    cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
    page.mouse.move(cx, cy); page.mouse.down()
    page.mouse.move(cx + dx, cy, steps=12)     # drag left -> pans the map right
    page.mouse.up(); time.sleep(1.0)

def click_search_this_area(page):              # button only exists AFTER a drag
    for label in ("Search this area","Search area","Redo search here","Search here"):
        b = page.get_by_text(label, exact=False)
        if b.count() > 0: b.first.click(); return True
    return False

def grab_this_view(page):                      # deterministic capture
    click_search_this_area(page)
    try:
        resp = page.wait_for_response(
            lambda r: "serviceability" in r.url.lower() and r.status == 200, timeout=8000)
        return extract_features(resp.json())
    except Exception:
        return []
```

## 4. Proven reference — MapMan's trigger + motion (fiber_precise_pipeline.py)
`search_zip` TYPES the zip into the search box and hits Enter — THIS is the first
serviceability fetch. `focus_map` clicks the canvas at 18%/22% before keyboard.
```python
def search_zip(page, zipc):
    geo = page.locator(".mapboxgl-ctrl-geocoder--input, input[placeholder*='Search' i],"
                       "input[type='search'], input[type='text']")
    geo.first.click(); geo.first.fill(""); geo.first.type(zipc, delay=60)
    time.sleep(1.5); geo.first.press("Enter"); time.sleep(4.0)   # centers + fetches

def focus_map(page):                            # "must click the map before +/-"
    cv = page.locator(".mapboxgl-canvas, canvas").first; box = cv.bounding_box()
    page.mouse.click(box["x"]+box["width"]*0.18, box["y"]+box["height"]*0.22)
    page.keyboard.press("Escape")
```

## 5. The batched write (don't append_row per address -> 429)
```python
import gspread
ws.append_rows(rows, value_input_option="RAW")  # rows = list of lists, chunk at 500
```

## RECOMMENDED COMPLETE AUTO LOOP
```
goto(MAP_URL); page.on("response", on_response)
click "Fiber Availability Map"; search_zip(zip)          # first fetch
for each cell in an NxN grid:
    focus_and_drag(page)                                  # PROVEN motion
    rows += grab_this_view(page)                          # search + wait_for_response
ws.append_rows(rows)                                      # batched
# rows are dicts -> map status to GREEN/GOLD/GREY via classify_status; write GREEN+GOLD.
```
