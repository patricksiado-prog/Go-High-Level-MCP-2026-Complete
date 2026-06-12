#!/usr/bin/env python3
"""
PRECISE FIBER HUNTER v0.4 (click-every-dot exact-address grabber)
=============================================================================
Drives the AT&T fiber map in a real Chromium window (Playwright), clicks each
dot, reads the EXACT address from the popup (confirmed live 2026-06-12:
"FIBER ELIGIBLE / Address: 8 GREENWAY PLZ UNIT 1111 / CREATE REFERRAL"),
records it, then pans to the next viewport. Snake pattern across a grid.

CHANGES v0.4 -> v0.5 (Mapbox fast path -- the OSM research conclusion):
 The dealer map is Mapbox GL JS on OpenStreetMap tiles. The dots are GeoJSON
 features INSIDE the page's map object, so instead of color-hunting pixels we
 hook mapboxgl.Map at page-init and ask the map directly:
   - queryRenderedFeatures() -> every dot's exact lng/lat + properties
   - if a feature carries the address in its properties -> record it with
     ZERO clicking;
   - else map.project(lnglat) -> exact CSS click pixel for that marker (no
     centroid guessing), then the v0.4 popup read.
 Pixel detection remains the automatic fallback when the hook finds nothing.
 (Nominatim reverse-geocoding was researched and REJECTED for this: the
 public API forbids systematic grid/bulk queries at 1 req/s, and OSM has no
 unit numbers -- the popup is the only unit-level source.)

CHANGES v0.3 -> v0.4 (the click-each-dot retool, from live screenshots
2026-06-12, Greenway Plaza / Edloe St session):
 1. CLICKS EVERY DOT, not just green. GREEN (lead) and GOLD (copper-upgrade)
    are both clicked and recorded with their legend status; GRAY (existing
    fiber customer) is detected but skipped and counted.
 2. RETRY CLICKS. The dots are ~6-10 px wide; one centroid click can miss the
    marker hit-zone and the address is silently lost. Now each dot gets up to
    5 attempts in a tiny spiral (center, then ±3 px offsets), verifying the
    popup actually opened after each attempt.
 3. POPUP POLLING. Fixed 1.1 s sleeps are gone -- the popup is polled every
    150 ms (up to 2.5 s) for the READY hints, so hits are fast and misses
    retry immediately.
 4. JSONL HANDOFF. Every capture is also appended to precise_addresses.jsonl
    {address, dot_status, popup_status, ban, area, ts} so business_score.py /
    ghl_loader.py can consume the run without Google Sheets in the middle.

CHANGES v0.2 -> v0.3 (accuracy fixes, ported from fiber_precise_pipeline):
 1. HiDPI FIX. v0.2 clicked at SCREENSHOT pixel coordinates. On HiDPI/scaled
    displays the screenshot is larger than the CSS viewport, so every click
    missed its dot (or hit a neighbor). Now:
      - device_scale_factor=1 on the browser context, AND
      - belt-and-suspenders sx/sy scaling from screenshot dims -> viewport
    so screenshot px always map onto click px.
 2. THRESHOLDS UNIFIED. v0.2's HSV window (OpenCV hue 70-95 = 140-190 real
    degrees) was teal/cyan -- it did NOT match the pipeline's proven RGB box
    and could find 0 dots on the same screen. Detection now imports the ONE
    canonical detector from optimus_dot_detect.py (numpy/PIL/scipy; the
    OpenCV dependency is gone).
 3. "Search this area" clicked after every pan -- without it the new view's
    dots never load (confirmed live, 77070, 2026-05-31), so v0.2 was often
    snake-scanning a map with stale or no dots.

KEPT FROM v0.2:
 - --zoom-in / --zoom-out flags (buttons, then keyboard, then wheel)
 - drain every dot in a viewport BEFORE panning; snake across the grid
 - RESUME: re-runs skip addresses already in the sheet
 - popup close fallback: x button -> empty map corner -> Escape

NOTE: for single-ZIP outage scans prefer fiber_precise_pipeline.py with
--api-substring -- it reads the map's backend JSON (exact address + lat/lng
+ BAN, no clicking at all). This hunter remains the wide-area grid tool and
the fallback when the API capture path is down.

COMPLIANCE (do not edit around this):
 Output feeds DOOR-KNOCK + DNC-SCRUBBED MANUAL CALL routes only. Map or
 skip-traced numbers are NEVER cold-texted (TCPA $500-$1,500 per text).

URL: https://youachieve.att.com/yourefer/fiber
SHEET: 1FhO... tab 'Precise Fiber'

DEPLOY (HP desktop only):
    pip install playwright numpy pillow scipy gspread google-auth
    python -m playwright install chromium

RUN:
    Log in once:   python precise_fiber_hunter.py --login
    Dry test:      python precise_fiber_hunter.py --zip 77447 --dry
    Real scan:     python precise_fiber_hunter.py --zip 77447 --cols 4 --rows 3 --zoom-in 3
    Broader sweep: python precise_fiber_hunter.py --zip 77447 --zoom-out 2 --cols 5 --rows 5
=============================================================================
"""

import os, sys, time, argparse, re

import json

from optimus_dot_detect import (GREEN_MIN, GREEN_MAX, GOLD_MIN, GOLD_MAX,
                                GRAY_MIN, GRAY_MAX, classify_status,
                                ADDRESS_REGEX, STATUS_REGEX, BAN_REGEX,
                                ELIGIBLE_REGEX, POPUP_READY_HINTS,
                                find_dots_in_png_bytes)

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
MAP_URL = "https://youachieve.att.com/yourefer/fiber"
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "att_profile")

SHEET_ID = "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA"  # ATT FIBER LEADS (production)
OUT_TAB = "Precise Fiber"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

VIEWPORT = {"width": 1366, "height": 768}

# --- map viewport region of the screen (fractions of the window) ---
MAP_TOP_FRAC = 0.18
MAP_BOTTOM_FRAC = 0.96
MAP_LEFT_FRAC = 0.02
MAP_RIGHT_FRAC = 0.98

# --- pacing (seconds) ---
WAIT_AFTER_PAN = 1.5
WAIT_AFTER_ZOOM = 1.5
PAN_PRESSES = 6
POPUP_POLL_INTERVAL = 0.15    # poll the popup instead of fixed sleeps
POPUP_POLL_TIMEOUT = 2.5      # per click attempt
CLICK_OFFSETS = [(0, 0), (3, 0), (-3, 0), (0, 3), (0, -3)]   # retry spiral

JSONL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "precise_addresses.jsonl")

# ----------------------------------------------------------------------------
# Mapbox GL fast path: hook the map object at page init, then query the dots
# as GeoJSON features instead of hunting pixels.
# ----------------------------------------------------------------------------
MAPBOX_HOOK_JS = """
(() => {
  window.__optimusMaps = window.__optimusMaps || [];
  const hook = () => {
    try {
      if (window.mapboxgl && window.mapboxgl.Map && !window.mapboxgl.Map.__optimusHooked) {
        const Orig = window.mapboxgl.Map;
        const Wrapped = function(...args) {
          const m = new Orig(...args);
          window.__optimusMaps.push(m);
          return m;
        };
        Wrapped.prototype = Orig.prototype;
        Object.setPrototypeOf(Wrapped, Orig);
        Wrapped.__optimusHooked = true;
        window.mapboxgl.Map = Wrapped;
      }
    } catch (e) {}
  };
  hook();
  const t = setInterval(hook, 200);
  setTimeout(() => clearInterval(t), 30000);
})();
"""

MAPBOX_QUERY_JS = """
() => {
  const m = (window.__optimusMaps || [])[0];
  if (!m || !m.queryRenderedFeatures) return null;
  let feats;
  try { feats = m.queryRenderedFeatures(); } catch (e) { return null; }
  const out = [];
  const seen = new Set();
  for (const f of feats) {
    if (!f.geometry || f.geometry.type !== 'Point') continue;
    const p = f.properties || {};
    const blob = JSON.stringify(p).toLowerCase();
    if (!(blob.includes('address') || blob.includes('fiber') ||
          blob.includes('eligib') || blob.includes('referral'))) continue;
    const [lng, lat] = f.geometry.coordinates;
    const key = lng.toFixed(6) + ',' + lat.toFixed(6);
    if (seen.has(key)) continue;
    seen.add(key);
    const px = m.project([lng, lat]);
    out.push({lng, lat, x: px.x, y: px.y, props: p,
              layer: (f.layer && f.layer.id) || ''});
  }
  return out;
}
"""

# property keys that may carry the address / status straight in the feature
FEATURE_ADDRESS_KEYS = ["address", "addr", "full_address", "serviceaddress",
                        "service_address", "location"]
FEATURE_STATUS_KEYS = ["status", "customer_status", "customertype",
                       "customer_type", "eligibility", "type"]


def query_map_features(page):
    """Ask the hooked Mapbox map for its dot features. Returns a list of
    dicts {lng, lat, x, y, props} or None when the hook isn't live."""
    try:
        feats = page.evaluate(MAPBOX_QUERY_JS)
    except Exception:
        return None
    return feats or None


def feature_address(props):
    """Pull an address straight out of feature properties, if present."""
    if not props:
        return None
    low = {str(k).lower(): v for k, v in props.items()}
    for k in FEATURE_ADDRESS_KEYS:
        v = low.get(k)
        if v and isinstance(v, str) and len(v.strip()) >= 6:
            return " ".join(v.split())[:160]
    return None


def feature_status_text(props):
    if not props:
        return None
    low = {str(k).lower(): v for k, v in props.items()}
    for k in FEATURE_STATUS_KEYS:
        v = low.get(k)
        if v and isinstance(v, str):
            return v
    return None

# --- popup parsing (canonical regexes from optimus_dot_detect) ---
POPUP_KEYS = {
    "eligible": re.compile(ELIGIBLE_REGEX, re.I),
    "address": re.compile(ADDRESS_REGEX, re.I | re.S),
    "status": re.compile(STATUS_REGEX, re.I | re.S),
    "ban": re.compile(BAN_REGEX, re.I),
}

# popup container selectors (scoped read; falls back to body if none match)
POPUP_SELECTORS = [".gm-style-iw", "[role='dialog']", ".popup", ".info-window",
                   ".mapboxgl-popup-content"]

SEARCH_THIS_AREA = "Search this area"


def _need(mod, pip_name=None):
    try:
        return __import__(mod)
    except Exception:
        print("MISSING: %s -> pip install %s" % (mod, pip_name or mod))
        sys.exit(1)


_need("numpy")
_need("PIL", "pillow")
_need("scipy")
_need("playwright", "playwright")
from playwright.sync_api import sync_playwright


# ----------------------------------------------------------------------------
# sheet
# ----------------------------------------------------------------------------
def open_sheet():
    import gspread
    from google.oauth2.service_account import Credentials
    creds_file = None
    for p in ["google_creds.json",
              r"C:\Users\patri\Optimus\google_creds.json",
              r"C:\Users\patri\optimus\google_creds.json",
              os.path.join(os.path.expanduser("~"), "Desktop", "google_creds.json")]:
        if os.path.exists(p):
            creds_file = p
            break
    if not creds_file:
        print("google_creds.json not found; will run as dry (no writes).")
        return None
    client = gspread.authorize(Credentials.from_service_account_file(creds_file, scopes=SCOPES))
    sh = client.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(OUT_TAB)
    except Exception:
        ws = sh.add_worksheet(title=OUT_TAB, rows="5000", cols="8")
    if not ws.get_all_values():
        ws.append_row(["Address", "Status", "Subscriber BAN", "Eligible",
                       "Captured At", "ZIP/Area", "Dot Status"])
    return ws


def already_seen(ws):
    """Resume: read existing addresses so a re-run skips them (survives crashes)."""
    if not ws:
        return set()
    try:
        rows = ws.get_all_values()
    except Exception:
        return set()
    return set(r[0].strip().upper() for r in rows[1:] if r and r[0].strip())


# ----------------------------------------------------------------------------
# screenshot + dot detection (canonical detector + HiDPI scaling)
# ----------------------------------------------------------------------------
DOT_COLOR_WINDOWS = [
    ("GREEN", GREEN_MIN, GREEN_MAX),   # fiber eligible / non-customer -> click
    ("GOLD", GOLD_MIN, GOLD_MAX),      # fiber eligible / copper customer -> click
    ("GRAY", GRAY_MIN, GRAY_MAX),      # existing fiber customer -> skip, count
]


def find_map_dots(page):
    """ONE screenshot, every dot color. Returns ([(x, y, color)], gray_count)
    where (x, y) are CLICK coordinates inside the map region and color is
    GREEN or GOLD (clickable). GRAY dots are only counted -- the legend says
    they're existing fiber customers, never a knock/call target."""
    raw = page.screenshot(type="png")
    vp = page.viewport_size or VIEWPORT
    out, gray = [], 0
    img_w = img_h = 0
    for color, cmin, cmax in DOT_COLOR_WINDOWS:
        dots, (img_w, img_h) = find_dots_in_png_bytes(raw, cmin, cmax)
        if not img_w or not img_h:
            continue
        sx = vp["width"] / img_w
        sy = vp["height"] / img_h
        top = vp["height"] * MAP_TOP_FRAC
        bottom = vp["height"] * MAP_BOTTOM_FRAC
        left = vp["width"] * MAP_LEFT_FRAC
        right = vp["width"] * MAP_RIGHT_FRAC
        for (px, py, _sz) in dots:
            cx, cy = px * sx, py * sy
            if left <= cx <= right and top <= cy <= bottom:
                if color == "GRAY":
                    gray += 1
                else:
                    out.append((int(cx), int(cy), color))
    out.sort(key=lambda p: (p[1] // 40, p[0]))  # reading order across colors
    return out, gray


# ----------------------------------------------------------------------------
# popup reading (scoped; falls back to body)
# ----------------------------------------------------------------------------
def _popup_text(page):
    for sel in POPUP_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el:
                t = el.inner_text()
                if t and POPUP_KEYS["eligible"].search(t):
                    return t
        except Exception:
            continue
    try:
        return page.inner_text("body")
    except Exception:
        return ""


def read_popup(page):
    txt = _popup_text(page)
    if not txt or not POPUP_KEYS["eligible"].search(txt):
        return None
    out = {"eligible": True, "address": None, "status": None, "ban": None}
    m = POPUP_KEYS["address"].search(txt)
    if m:
        out["address"] = " ".join(m.group(1).split())[:160]
    m = POPUP_KEYS["status"].search(txt)
    if m:
        out["status"] = " ".join(m.group(1).split())[:80]
    m = POPUP_KEYS["ban"].search(txt)
    if m:
        out["ban"] = m.group(1).strip()
    return out if out["address"] else None


def wait_for_popup(page, timeout=POPUP_POLL_TIMEOUT):
    """Poll until the dot popup is actually open (READY hints visible) and
    parseable, instead of sleeping a fixed interval. Returns info or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = read_popup(page)
        if info:
            return info
        time.sleep(POPUP_POLL_INTERVAL)
    return None


def click_dot(page, x, y):
    """Click a tiny map dot with a retry spiral. The markers are ~6-10 px;
    a centroid click can land just outside the hit-zone, so on a miss we
    nudge ±3 px and try again, verifying the popup opened each time."""
    for (dx, dy) in CLICK_OFFSETS:
        try:
            page.mouse.click(x + dx, y + dy)
        except Exception:
            continue
        info = wait_for_popup(page)
        if info:
            return info
    return None


def append_jsonl(record):
    try:
        with open(JSONL_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print("   jsonl write error: %s" % e)


def empty_map_point(page):
    """A spot in the map region with no dot -- top-left corner of the map area."""
    vp = page.viewport_size or VIEWPORT
    x = int(vp["width"] * (MAP_LEFT_FRAC + 0.01))
    y = int(vp["height"] * (MAP_TOP_FRAC + 0.02))
    return x, y


def close_popup(page):
    # 1) try an explicit close control
    for sel in ["[aria-label='Close']", "button:has-text('×')", "text=×",
                ".gm-ui-hover-effect"]:
        try:
            el = page.query_selector(sel)
            if el:
                el.click(timeout=800)
                time.sleep(0.2)
                return
        except Exception:
            pass
    # 2) fallback: click an EMPTY map spot (never a dot) to dismiss
    try:
        x, y = empty_map_point(page)
        page.mouse.click(x, y)
        time.sleep(0.2)
    except Exception:
        pass
    # 3) last resort
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass


# ----------------------------------------------------------------------------
# map controls
# ----------------------------------------------------------------------------
def focus_map(page):
    """Focus the map WITHOUT hitting a dot: click an empty corner of the map."""
    x, y = empty_map_point(page)
    page.mouse.click(x, y)
    time.sleep(0.3)


def _zoom_once(page, direction):
    """Try on-screen button, then keyboard, then wheel. direction = 'in'|'out'."""
    btn_selectors = (["[aria-label='Zoom in']", "button[title='Zoom in']", "text=+"]
                     if direction == "in"
                     else ["[aria-label='Zoom out']", "button[title='Zoom out']", "text=-"])
    for sel in btn_selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.click(timeout=800)
                return
        except Exception:
            pass
    try:
        page.keyboard.press("Equal" if direction == "in" else "Minus")
        return
    except Exception:
        pass
    vp = page.viewport_size or VIEWPORT
    page.mouse.move(vp["width"] // 2, int(vp["height"] * 0.55))
    page.mouse.wheel(0, -300 if direction == "in" else 300)


def zoom(page, presses, direction):
    for _ in range(max(0, presses)):
        _zoom_once(page, direction)
        time.sleep(0.3)
    if presses > 0:
        time.sleep(WAIT_AFTER_ZOOM)


def search_this_area(page):
    """After a pan/zoom the new view's dots only load when this is clicked."""
    try:
        btn = page.get_by_text(SEARCH_THIS_AREA, exact=False)
        if btn.count() > 0:
            btn.first.click()
            time.sleep(3.0)
            return True
    except Exception:
        pass
    return False


def pan(page, direction):
    focus_map(page)   # make sure arrow keys land on the map
    key = {"left": "ArrowLeft", "right": "ArrowRight",
           "up": "ArrowUp", "down": "ArrowDown"}[direction]
    for _ in range(PAN_PRESSES):
        page.keyboard.press(key)
        time.sleep(0.12)
    time.sleep(WAIT_AFTER_PAN)
    search_this_area(page)   # load the new view's dots


def search_zip(page, zip_code):
    for sel in ["input[type='search']", "input[placeholder*='ddress']",
                "input[placeholder*='earch']", "input"]:
        try:
            box = page.query_selector(sel)
            if box:
                box.click()
                box.fill(str(zip_code))
                time.sleep(0.4)
                page.keyboard.press("Enter")
                time.sleep(3.0)
                return True
        except Exception:
            continue
    return False


# ----------------------------------------------------------------------------
# scan: drain each viewport fully, THEN pan; snake across grid
# ----------------------------------------------------------------------------
def record_capture(ws, seen, area_label, dry, address, popup_status, ban,
                   dot_status, via):
    """Common writer for both the Mapbox fast path and the click path.
    Returns True when a NEW address was recorded."""
    addr_key = address.strip().upper()
    if addr_key in seen:
        return False
    seen.add(addr_key)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    row = [address, popup_status or "", ban or "", "FIBER ELIGIBLE",
           ts, area_label, dot_status]
    if dry or not ws:
        print("   + [%s/%s] %s | %s | BAN %s" %
              (dot_status, via, address, popup_status or "-", ban or "-"))
    else:
        try:
            ws.append_row(row)
        except Exception as e:
            print("   write error: %s" % e)
    if not dry:
        append_jsonl({"address": address, "dot_status": dot_status,
                      "popup_status": popup_status, "ban": ban,
                      "area": area_label, "ts": ts, "via": via})
    return True


def drain_viewport_mapbox(page, ws, seen, area_label, dry):
    """FAST PATH: read the dots straight out of the Mapbox map object.
    Features that carry an address in their properties are recorded with no
    clicking at all; the rest are clicked at their exact projected pixel.
    Returns captured count, or None when the hook isn't live (caller falls
    back to pixel detection)."""
    feats = query_map_features(page)
    if feats is None:
        return None
    print("  viewport (mapbox): %d dot features" % len(feats))
    captured = 0
    for f in feats:
        props = f.get("props") or {}
        addr = feature_address(props)
        status_txt = feature_status_text(props)
        dot_status = classify_status(text=status_txt or str(props))
        if addr:
            if record_capture(ws, seen, area_label, dry, addr, status_txt,
                              None, dot_status, via="mapbox"):
                captured += 1
            continue
        # no address in the feature -> click at the EXACT projected pixel
        info = click_dot(page, int(f["x"]), int(f["y"]))
        if info and info.get("address"):
            dot_status = classify_status(text=info.get("status") or status_txt,
                                         ban=info.get("ban"))
            if record_capture(ws, seen, area_label, dry, info["address"],
                              info.get("status"), info.get("ban"),
                              dot_status, via="mapbox-click"):
                captured += 1
        close_popup(page)
        time.sleep(0.2)
    return captured


def drain_viewport(page, ws, seen, area_label, dry):
    """Capture every dot in the current viewport. Tries the Mapbox feature
    fast path first; falls back to pixel detection + retry clicks."""
    n = drain_viewport_mapbox(page, ws, seen, area_label, dry)
    if n is not None:
        return n
    captured = 0
    clicked_pixels = set()
    dots, gray_count = find_map_dots(page)
    greens = sum(1 for d in dots if d[2] == "GREEN")
    golds = len(dots) - greens
    print("  viewport (pixels): %d green + %d gold dots (%d gray customers skipped)"
          % (greens, golds, gray_count))
    misses = 0
    for (x, y, color) in dots:
        keyxy = (x // 12, y // 12)   # coarse de-dupe within this viewport
        if keyxy in clicked_pixels:
            continue
        clicked_pixels.add(keyxy)
        info = click_dot(page, x, y)
        if info and info.get("address"):
            dot_status = classify_status(text=info.get("status"),
                                         ban=info.get("ban"), color=color)
            if record_capture(ws, seen, area_label, dry, info["address"],
                              info.get("status"), info.get("ban"),
                              dot_status, via="pixel-click"):
                captured += 1
        else:
            misses += 1
        close_popup(page)
        time.sleep(0.2)
    if misses:
        print("  (%d dots never opened a popup after retries)" % misses)
    return captured


def scan(page, ws, area_label, cols, rows, dry):
    seen = already_seen(ws)
    print("Resume: %d addresses already captured -> will skip them." % len(seen))
    total = 0
    for r in range(rows):
        for c in range(cols):
            print("[cell r%d c%d]" % (r, c))
            total += drain_viewport(page, ws, seen, area_label, dry)  # ALL dots first
            if c < cols - 1:
                pan(page, "right" if r % 2 == 0 else "left")          # THEN pan
        if r < rows - 1:
            pan(page, "down")   # next row, reverse dir
    return total


# ----------------------------------------------------------------------------
# entry
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="open browser to log in once, then quit")
    ap.add_argument("--zip", default=None, help="ZIP/area to search before scanning")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--zoom-in", type=int, default=0, help="press zoom-IN this many times after load")
    ap.add_argument("--zoom-out", type=int, default=0, help="press zoom-OUT this many times after load")
    ap.add_argument("--dry", action="store_true", help="don't write to the sheet, just print")
    args = ap.parse_args()

    os.makedirs(PROFILE_DIR, exist_ok=True)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False,
            viewport=VIEWPORT,
            device_scale_factor=1,   # screenshot px == click px (HiDPI fix)
            args=["--start-maximized"],
        )
        ctx.add_init_script(MAPBOX_HOOK_JS)   # hook the map before it loads
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(MAP_URL, wait_until="domcontentloaded", timeout=60000)

        if args.login:
            print("\nLOG IN in the browser, open the Fiber Map, then come back here.")
            input("Press Enter when you're logged in and the map is showing... ")
            print("Session saved to %s. You can now run without --login." % PROFILE_DIR)
            ctx.close()
            return

        ws = None if args.dry else open_sheet()
        focus_map(page)

        if args.zip:
            print("Searching area: %s" % args.zip)
            if not search_zip(page, args.zip):
                print("Couldn't find the search box -- pan/zoom to your area by hand.")
                input("Press Enter when the map shows your area... ")
            focus_map(page)

        if args.zoom_in:
            print("Zooming IN x%d" % args.zoom_in)
            zoom(page, args.zoom_in, "in")
        if args.zoom_out:
            print("Zooming OUT x%d" % args.zoom_out)
            zoom(page, args.zoom_out, "out")
        search_this_area(page)   # make sure the starting view's dots are loaded

        print("Scanning %d x %d viewports...\n" % (args.cols, args.rows))
        n = scan(page, ws, args.zip or "manual", args.cols, args.rows, args.dry)
        print("\nDONE. Captured %d new fiber-eligible addresses." % n)
        print(("They're in the '%s' tab." % OUT_TAB) if ws else "(dry run, nothing written)")
        input("Press Enter to close the browser... ")
        ctx.close()


if __name__ == "__main__":
    main()
