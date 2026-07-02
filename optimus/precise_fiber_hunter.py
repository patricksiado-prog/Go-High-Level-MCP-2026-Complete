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
import hashlib

import json
import threading

from optimus_dot_detect import (GREEN_MIN, GREEN_MAX, GOLD_MIN, GOLD_MAX,
                                GRAY_MIN, GRAY_MAX, classify_status,
                                zone_freshness,
                                ADDRESS_REGEX, STATUS_REGEX, BAN_REGEX,
                                ELIGIBLE_REGEX, POPUP_READY_HINTS,
                                find_dots_in_png_bytes)

# proven schema-tolerant JSON walker from the working pipeline -- the AT&T dot
# layer is the 'serviceability' JSON endpoint; this extracts its addresses.
try:
    from optimus_api_capture import extract_features as _extract_features
except Exception:
    _extract_features = None

# Audited fixes (safe flush / drift-proof dedup / junk-address gate). A launcher
# that predates hunter_fixes.py only refreshes the 3 old core files, so on
# ImportError fetch the module once from GitHub raw -- a stale RUN_HUNTER.bat
# must never crash the new code on import.
try:
    from hunter_fixes import Deduper, SafePending, clean_address, is_junk_address
except ImportError:
    try:
        import urllib.request as _ureq
        _hf_url = ("https://raw.githubusercontent.com/patricksiado-prog/"
                   "Go-High-Level-MCP-2026-Complete/"
                   "claude/optimus-map-tools-setup-6dcl6o/optimus/hunter_fixes.py")
        _hf = _ureq.urlopen(_hf_url, timeout=30).read()
        if _hf and len(_hf) > 500:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "hunter_fixes.py"), "wb") as _f:
                _f.write(_hf)
    except Exception:
        pass
    from hunter_fixes import Deduper, SafePending, clean_address, is_junk_address

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
MAP_URL = "https://youachieve.att.com/yourefer/fiber"
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "att_profile")

SHEET_ID = "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA"  # ATT FIBER LEADS (production)
OUT_TAB = "Precise Fiber"
STATUS_TAB = "Hunter Status"   # live "what it's doing" log, on Drive in the same sheet
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# Self-update: which branch to pull on each start (matches the launcher).
REPO_BRANCH = "claude/optimus-map-tools-setup-6dcl6o"

# BUILD STAMP -- bumped on every push so you can SEE the code actually changed.
# It prints a big banner at startup. If the number here matches what your screen
# shows, you're on the newest code.
HUNTER_BUILD = "BUILD 2026-07-02  #24  SPLIT: motion process NEVER touches Google -- a separate uploader process does all sheet work"

VIEWPORT = {"width": 1366, "height": 768}

# --- map viewport region of the screen (fractions of the window) ---
MAP_TOP_FRAC = 0.18
MAP_BOTTOM_FRAC = 0.96
MAP_LEFT_FRAC = 0.02
MAP_RIGHT_FRAC = 0.98

# --- pacing (seconds) -- FAST by default now (speed is the priority); --slow
#     restores the relaxed timing if dots aren't loading in time on a slow link.
#     Module globals so main() can adjust them.
WAIT_AFTER_PAN = 0.2
WAIT_AFTER_ZOOM = 0.45
SEARCH_SETTLE = 0.3           # wait after "Search this area" for dots to load
PAN_INTERVAL = 0.3           # TIMED sweep: brisk but gives the browser room (0.05 hung weak PCs)
FLUSH_INTERVAL = 4.0         # TIMED sweep: how often the background thread writes dots
SPIRAL_MAX = 5               # TIMED sweep: how far (cells) it may drift from the start
#                              before snapping back -- stops it wandering into empty edges
STALL_SECS = 40              # WATCHDOG: browser hung this long -> restart FAST (was 150)
RESTART_CODE = 42            # exit code the launcher loop watches to relaunch fresh
_last_beat = [0.0]           # last time the sweep made progress (0 = watchdog not armed)
SEARCH_CLICK_WAIT = 1.5       # wait after CLICKING the search control for the fetch
PAN_PRESSES = 6
# fiber_hunter's proven motion is a MOUSE DRAG across the canvas (the original
# used pyautogui.dragRel). DRAG_FRAC = how far to drag, as a fraction of the
# canvas, per cell (<1 so adjacent cells overlap a little and miss nothing).
DRAG_FRAC = 0.45

# Map the internal dot status -> the on-map LEGEND COLOR, so the sheet says
# GREEN / ORANGE / GREY at a glance (green = eligible lead, orange = copper
# upgrade, grey = existing customer/skip) instead of "lead"/"customer".
DOT_COLOR = {"lead": "GREEN", "copper_upgrade": "ORANGE", "customer": "GREY"}


def dot_color(dot_status):
    """Legend color word for a classified dot status (defaults to GREEN)."""
    return DOT_COLOR.get((dot_status or "").lower(), "GREEN")
POPUP_POLL_INTERVAL = 0.12    # poll the popup instead of fixed sleeps
POPUP_POLL_TIMEOUT = 2.0      # per click attempt
CLICK_OFFSETS = [(0, 0), (3, 0), (-3, 0), (0, 3), (0, -3)]   # retry spiral

# Pixel-click fallback is OFF by default: clicking "dots" detected on a
# transitioning/portal page lands on nav buttons and flips the view. We capture
# from the Mapbox backend read instead; --allow-click re-enables the old way.
ALLOW_CLICK = False
_AUTO_PROBED = [False]   # run the frame diagnostic at most once per session
_NET_CAPTURE = [None]    # the always-on network capture (set in main)

# SPLIT MODE (Patrick, 2026-07-02: "backend memory processing separate from
# motion"): the browser process NEVER touches Google Sheets while sweeping.
# Captures append to the local JSONL (microseconds) and a separate UPLOADER
# process (this same file, --uploader) tails the file and does ALL sheet work:
# dedupe, batched writes, biz matching, status mirroring. Two processes =
# zero interference with Playwright (the in-process background-thread version
# froze Chromium -- processes don't share the greenlet loop or the GIL).
_SPLIT = [False]
RUN_STATUS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "run_status.json")
BACKEND_LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "backend_capture_local.json")
UPLOADER_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "uploader_log.txt")

JSONL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "precise_addresses.jsonl")

# ----------------------------------------------------------------------------
# Mapbox GL fast path: hook the map object at page init, then query the dots
# as GeoJSON features instead of hunting pixels.
# ----------------------------------------------------------------------------
MAPBOX_HOOK_JS = """
(() => {
  window.__optimusMaps = window.__optimusMaps || [];
  const wrap = (lib) => {
    try {
      if (lib && lib.Map && !lib.Map.__optimusHooked) {
        const Orig = lib.Map;
        const Wrapped = function(...args) {
          const m = new Orig(...args);
          window.__optimusMaps.push(m);
          return m;
        };
        Wrapped.prototype = Orig.prototype;
        Object.setPrototypeOf(Wrapped, Orig);
        Wrapped.__optimusHooked = true;
        lib.Map = Wrapped;
      }
    } catch (e) {}
  };
  const hook = () => {
    // Mapbox GL JS AND MapLibre GL JS (identical API, different global name)
    wrap(window.mapboxgl);
    wrap(window.maplibregl);
  };
  hook();
  // keep re-wrapping for a long time: the user logs in + opens the map well
  // after page load, and the map is created THEN -- a short window misses it.
  const t = setInterval(hook, 200);
  setTimeout(() => clearInterval(t), 1800000);   // 30 minutes

  // AT&T's bundle sets NO mapboxgl/maplibregl global, so the constructor wrap
  // above never fires and __optimusMaps stays empty (that's why panBy() never
  // worked and we were stuck dragging). Escape hatch: catch the WebGL canvas the
  // instant Mapbox creates it; its DOM/React-fiber chain leads to the live map
  // object, which recover_map() then walks to. (See the mapbox-extraction skill.)
  try {
    const origGC = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
      if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') {
        (window.__glCanvases = window.__glCanvases || []).push(this);
      }
      return origGC.call(this, type, ...rest);
    };
  } catch (e) {}
})();
"""

# Recover the HIDDEN Mapbox map object (AT&T sets no global): from the WebGL
# canvases we caught (or any .mapboxgl-map node), walk the React fiber tree for
# the object that has queryRenderedFeatures + getStyle + panBy, and register it
# to window.__optimusMaps so pan_map_js()/the dot reader can use it. Returns true
# if a live map was found. Safe to call repeatedly.
MAP_RECOVER_JS = """
() => {
  if ((window.__optimusMaps || []).length &&
      window.__optimusMaps[0] && window.__optimusMaps[0].panBy) return true;
  const isMap = (o) => o && typeof o.queryRenderedFeatures === 'function'
                    && typeof o.getStyle === 'function'
                    && typeof o.panBy === 'function';
  const tag = (m) => { (window.__optimusMaps = window.__optimusMaps || []).unshift(m); return true; };
  const nodes = new Set();
  for (const c of (window.__glCanvases || [])) {
    let n = c;
    for (let i = 0; i < 8 && n; i++) { nodes.add(n); n = n.parentElement; }
  }
  document.querySelectorAll('.mapboxgl-map, .maplibregl-map, canvas')
          .forEach(n => nodes.add(n));
  const q = []; const seen = new Set();
  for (const n of nodes) {
    for (const k in n) {
      if (k.startsWith('__react')) q.push(n[k]);       // React fiber roots
      try { if (isMap(n[k])) return tag(n[k]); } catch (e) {}   // map stashed on the node
    }
  }
  let steps = 0;
  while (q.length && steps++ < 8000) {
    const f = q.shift();
    if (!f || seen.has(f)) continue; seen.add(f);
    for (const key of ['memoizedProps','memoizedState','stateNode','pendingProps']) {
      let v; try { v = f[key]; } catch (e) { continue; }
      if (isMap(v)) return tag(v);
      if (v && typeof v === 'object') {
        for (const kk in v) { try { if (isMap(v[kk])) return tag(v[kk]); } catch (e) {} }
      }
    }
    for (const key of ['child','sibling','return']) { try { if (f[key]) q.push(f[key]); } catch (e) {} }
  }
  return false;
}
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

MAPBOX_PROBE_JS = """
() => {
  let maps = (window.__optimusMaps || []).slice();
  if (!maps.length) {
    try {
      for (const k in window) {
        let v; try { v = window[k]; } catch (e) { continue; }
        if (v && typeof v.queryRenderedFeatures === 'function' &&
            typeof v.project === 'function') { maps.push(v); break; }
      }
    } catch (e) {}
  }
  const out = {hookedMaps: maps.length, maps: [],
               hasMapboxgl: !!(window.mapboxgl),
               hasMaplibregl: !!(window.maplibregl),
               canvases: document.querySelectorAll('canvas').length,
               mapboxCanvases: document.querySelectorAll('.mapboxgl-canvas').length,
               maplibreCanvases: document.querySelectorAll('.maplibregl-canvas').length};
  for (const m of maps) {
    if (!m || !m.queryRenderedFeatures) { out.maps.push({error: 'no queryRenderedFeatures'}); continue; }
    let feats = [];
    try { feats = m.queryRenderedFeatures(); } catch (e) { out.maps.push({error: String(e)}); continue; }
    const layers = {};
    let points = 0;
    const samples = [];
    for (const f of feats) {
      const lid = (f.layer && f.layer.id) || '?';
      layers[lid] = (layers[lid] || 0) + 1;
      if (f.geometry && f.geometry.type === 'Point') {
        points++;
        if (samples.length < 30) samples.push({layer: lid, props: f.properties || {}});
      }
    }
    // sources: id, type, and for geojson, a feature count + a sample's props
    const sources = {};
    try {
      const sdefs = (m.getStyle && m.getStyle().sources) || {};
      for (const id in sdefs) {
        const t = (sdefs[id] && sdefs[id].type) || '?';
        let n = null, sample = null;
        try {
          const src = m.getSource(id);
          const d = src && src._data;
          if (d && typeof d === 'object') {
            const fs = d.type === 'FeatureCollection' ? (d.features || [])
                     : (d.type === 'Feature' ? [d] : []);
            n = fs.length;
            for (const f of fs) { if (f.geometry && f.geometry.type === 'Point') { sample = f.properties || {}; break; } }
          }
        } catch (e) {}
        sources[id] = {type: t, dataFeatures: n, sampleProps: sample};
      }
    } catch (e) {}
    out.maps.push({totalFeatures: feats.length, pointFeatures: points, layers, samples, sources});
  }
  return out;
}
"""

# Read the AT&T dot features straight from the map: every rendered POINT feature
# that ISN'T part of the Mapbox basemap (roads/labels/water/etc.), with its exact
# screen pixel (via map.project) + lng/lat + properties, plus the map canvas rect
# so the pixels line up with a screenshot. No clicking, no pixel-hunting the whole
# screen (which mis-detected portal buttons as dots).
MAPBOX_DOTS_JS = """
() => {
  let m = (window.__optimusMaps || [])[0];
  if (!m || !m.queryRenderedFeatures) {
    // hook missed it (map loaded as a module?) -> search globals for a map
    try {
      for (const k in window) {
        let v; try { v = window[k]; } catch (e) { continue; }
        if (v && typeof v.queryRenderedFeatures === 'function' &&
            typeof v.project === 'function' && typeof v.getContainer === 'function') {
          m = v; break;
        }
      }
    } catch (e) {}
  }
  if (!m || !m.queryRenderedFeatures) return null;
  const SKIP_SRC = ['composite', 'mapbox', 'satellite', 'terrain-', 'hillshade'];
  const SKIP_LAYER = ['road','bridge','tunnel','motorway','street','path','rail',
    'transit','ferry','label','place','poi','water','waterway','marine','land',
    'building','structure','boundary','admin','country','state','contour',
    'hillshade','terrain','park','wood','grass','sand','pitch','aeroway',
    'airport','housenum','bound','background','bg-'];
  let rect = {left: 0, top: 0, width: 0, height: 0};
  try { const r = m.getContainer().getBoundingClientRect();
        rect = {left: r.left, top: r.top, width: r.width, height: r.height}; } catch (e) {}
  const out = [];
  const seen = new Set();
  const MAX = 4000;
  const push = (f, src) => {
    if (out.length >= MAX) return;
    if (!f || !f.geometry || f.geometry.type !== 'Point') return;
    const c = f.geometry.coordinates;
    if (!c || c.length < 2) return;
    const lng = c[0], lat = c[1];
    const key = lng.toFixed(6) + ',' + lat.toFixed(6);
    if (seen.has(key)) return;
    seen.add(key);
    let x = -1, y = -1;
    try { const p = m.project([lng, lat]); x = p.x; y = p.y; } catch (e) {}
    out.push({lng, lat, x, y, props: f.properties || {}, source: src || ''});
  };
  // 1) BEST: read each non-basemap source's data directly -> ALL dots + full
  //    properties (address/status if present), not just the viewport.
  try {
    const sources = (m.getStyle && m.getStyle().sources) || {};
    for (const id in sources) {
      if (out.length >= MAX) break;
      const lid = String(id).toLowerCase();
      if (SKIP_SRC.some(s => lid.includes(s))) continue;
      const sdef = sources[id] || {};
      let src; try { src = m.getSource(id); } catch (e) { continue; }
      if (!src) continue;
      const d = src._data;
      if (sdef.type === 'geojson' && d && typeof d === 'object') {
        const feats = d.type === 'FeatureCollection' ? (d.features || [])
                    : (d.type === 'Feature' ? [d] : []);
        for (const f of feats) push(f, id);
      } else {
        try { const qf = m.querySourceFeatures(id); for (const f of qf) push(f, id); }
        catch (e) {}
      }
    }
  } catch (e) {}
  // 2) SUPPLEMENT: rendered point features not on a basemap layer
  try {
    const feats = m.queryRenderedFeatures();
    for (const f of feats) {
      if (out.length >= MAX) break;
      const lid = ((f.layer && f.layer.id) || '').toLowerCase();
      if (SKIP_LAYER.some(s => lid.includes(s))) continue;
      push(f, (f.source || ''));
    }
  } catch (e) {}
  return {rect, dots: out};
}
"""

# property keys that may carry the address / status straight in the feature
FEATURE_ADDRESS_KEYS = ["address", "addr", "addr1", "address1", "full_address",
                        "fulladdress", "formatted_address", "street_address",
                        "streetaddress", "serviceaddress", "service_address",
                        "street", "location"]
FEATURE_STATUS_KEYS = ["status", "customer_status", "customertype",
                       "customer_type", "eligibility", "eligible", "fiber_status",
                       "fiberstatus", "service_status", "servicestatus",
                       "dot_status", "category", "segment", "color", "type"]


def query_map_features(page):
    """Ask the hooked Mapbox map for its dot features. Returns a list of
    dicts {lng, lat, x, y, props} or None when the hook isn't live."""
    try:
        feats = page.evaluate(MAPBOX_QUERY_JS)
    except Exception:
        return None
    return feats or None


def eval_best_frame(page, js):
    """Run JS in the main page AND every child frame, return the result with the
    most dots. The AT&T map can live inside an iframe, so the main-page window has
    no map -- we must ask each frame. Returns (data_dict_or_None, frame_index)."""
    best, best_n, idx = None, -1, -1
    try:
        frames = list(page.frames)
    except Exception:
        try:
            return page.evaluate(js), 0
        except Exception:
            return None, -1
    for i, fr in enumerate(frames):
        try:
            d = fr.evaluate(js)
        except Exception:
            continue
        if isinstance(d, dict):
            n = len(d.get("dots") or [])
            if n > best_n:
                best, best_n, idx = d, n, i
    return best, idx


def run_frame_probe(page):
    """Probe EVERY frame for a Mapbox map: report maps found, whether mapboxgl
    exists, canvas counts, and each data source's props. Writes probe.json and
    prints a summary. Used both by --probe AND automatically by a normal run when
    the backend read can't find the map (so no separate probe command is needed)."""
    here = os.path.dirname(os.path.abspath(__file__))
    per_frame = []
    try:
        frames = list(page.frames)
    except Exception:
        frames = [page]
    for fi, fr in enumerate(frames):
        try:
            d = fr.evaluate(MAPBOX_PROBE_JS)
        except Exception as e:
            d = {"error": str(e)}
        try:
            furl = fr.url
        except Exception:
            furl = ""
        per_frame.append({"frame": fi, "url": furl, "result": d})
    try:
        with open(os.path.join(here, "probe.json"), "w") as f:
            json.dump({"frames": per_frame}, f, indent=2)
    except Exception:
        pass
    print("\n=== MAP PROBE (frames) ===")
    print("  frames on page: %d" % len(per_frame))
    for pf in per_frame:
        d = pf.get("result") or {}
        if not isinstance(d, dict):
            continue
        print("  frame %d  maps=%s  mapboxgl=%s  maplibregl=%s  canvas=%s  mbCanvas=%s  mlCanvas=%s  %s"
              % (pf["frame"], d.get("hookedMaps"), d.get("hasMapboxgl"),
                 d.get("hasMaplibregl"), d.get("canvases"), d.get("mapboxCanvases"),
                 d.get("maplibreCanvases"), (pf.get("url") or "")[:36]))
        for mp in (d.get("maps") or []):
            for sid, sv in (mp.get("sources") or {}).items():
                sp = sv.get("sampleProps")
                keys = ",".join(list(sp.keys())[:8]) if isinstance(sp, dict) else "-"
                print("      src %-20s type=%-7s feats=%s props[%s]"
                      % (str(sid)[:20], sv.get("type"), sv.get("dataFeatures"), keys))
    print("  full detail -> %s" % os.path.join(here, "probe.json"))
    # send the diagnostic to Drive so Claude can read what the map looks like
    try:
        bits = ["PROBE frames=%d" % len(per_frame)]
        for pf in per_frame:
            d = pf.get("result") or {}
            if not isinstance(d, dict):
                continue
            srcids = []
            for mp in (d.get("maps") or []):
                srcids += list((mp.get("sources") or {}).keys())
            bits.append("f%s[maps=%s mbgl=%s mlgl=%s cv=%s mbcv=%s mlcv=%s src=%s %s]"
                        % (pf.get("frame"), d.get("hookedMaps"), d.get("hasMapboxgl"),
                           d.get("hasMaplibregl"), d.get("canvases"),
                           d.get("mapboxCanvases"), d.get("maplibreCanvases"),
                           ",".join(srcids[:4]), (pf.get("url") or "")[:30]))
        drive_log(" ".join(bits))
    except Exception:
        pass
    return per_frame


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


# ============================================================================
# NETWORK CAPTURE (the fast path) -- read the dots straight from AT&T's backend
# JSON response instead of clicking. Research-confirmed: Playwright
# page.on("response") hands us the payload; one response covers the whole
# loaded area, no clicking, and it doesn't care that the basemap didn't paint.
# Pure parsing below is unit-tested; the listener wiring runs on the HP.
# ============================================================================
def _nkey(k):
    """Normalize a JSON key for fuzzy matching: lower, drop _ - and spaces."""
    return str(k).lower().replace("_", "").replace("-", "").replace(" ", "")


ADDR_KEYS = {"address", "addr", "fulladdress", "serviceaddress", "streetaddress",
             "formattedaddress", "addressline", "address1", "fulladdr"}
LAT_KEYS = {"lat", "latitude", "y"}
LNG_KEYS = {"lng", "lon", "long", "longitude", "x"}
NET_STATUS_KEYS = {"status", "eligibility", "eligible", "customerstatus",
                   "customertype", "fiberstatus", "type", "dotstatus"}
NET_BAN_KEYS = {"ban", "subscriberban"}


def _pick(low, keyset):
    for k in keyset:
        v = low.get(k)
        if v not in (None, ""):
            return v
    return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def lead_from_dict(d):
    """Extract one lead {address, lat, lng, status, ban} from a dict that may
    be a flat record OR a GeoJSON feature (geometry + properties)."""
    if not isinstance(d, dict):
        return None
    geom = d.get("geometry") if isinstance(d.get("geometry"), dict) else None
    base = d.get("properties") if isinstance(d.get("properties"), dict) else d
    low = {_nkey(k): v for k, v in base.items()}
    addr = _pick(low, ADDR_KEYS)
    if not addr or not isinstance(addr, str):
        return None
    lat, lng = _num(_pick(low, LAT_KEYS)), _num(_pick(low, LNG_KEYS))
    if geom and geom.get("type") == "Point":
        coords = geom.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lng = lng if lng is not None else _num(coords[0])
            lat = lat if lat is not None else _num(coords[1])
    status = _pick(low, NET_STATUS_KEYS)
    # "raw" = the record exactly as AT&T sent it (subscriber_ban,
    # curr_ntwrk_bld_type_cd, ...) so backend_classifier can read the truth.
    return {"address": " ".join(addr.split())[:160], "lat": lat, "lng": lng,
            "status": status if isinstance(status, str) else None,
            "ban": _pick(low, NET_BAN_KEYS), "raw": base}


def extract_leads_from_json(obj, out=None, depth=0):
    """Recursively pull every lead out of an arbitrary JSON payload
    (FeatureCollection, plain list, {data:[...]}, nested, etc.)."""
    if out is None:
        out = []
    if depth > 7:
        return out
    if isinstance(obj, dict):
        ld = lead_from_dict(obj)
        if ld:
            out.append(ld)
        else:
            for v in obj.values():
                extract_leads_from_json(v, out, depth + 1)
    elif isinstance(obj, list):
        for it in obj:
            extract_leads_from_json(it, out, depth + 1)
    return out


# --- Mapbox vector-tile (protobuf) decoding -- the AT&T dots ride in here ----
import math

_TILE_XYZ_RE = re.compile(r"/(\d{1,2})/(\d{1,7})/(\d{1,7})(?:[._/]|\?|$)")


def _tile_zxy(url):
    """Pull (z, x, y) out of a vector-tile URL like .../14/3824/6915.pbf."""
    m = _TILE_XYZ_RE.search(url.split("?")[0])
    if not m:
        # some servers pass them as query params ?z=&x=&y=
        qz = re.search(r"[?&]z=(\d+)", url)
        qx = re.search(r"[?&]x=(\d+)", url)
        qy = re.search(r"[?&]y=(\d+)", url)
        if qz and qx and qy:
            return int(qz.group(1)), int(qx.group(1)), int(qy.group(1))
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _tilepoint_to_lnglat(z, x, y, px, py, extent):
    """Convert a tile-local point (px,py in 0..extent, y down) to lng/lat."""
    n = 2.0 ** z
    lon = (x + px / extent) / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + py / extent) / n)))
    return lon, math.degrees(lat_rad)


def _is_basemap_tile(url):
    """Mapbox's own street/terrain BASEMAP tiles -- roads & place names, NOT the
    AT&T fiber dots. Decoding these yields street names that look like addresses
    (bogus leads), so skip them."""
    u = url.lower()
    return ("api.mapbox.com" in u and
            ("mapbox-streets" in u or "mapbox-terrain" in u or "/v4/mapbox." in u))


def _is_vector_tile(url, ct):
    if _is_basemap_tile(url):
        return False
    ctl = (ct or "").lower()
    if "mapbox-vector-tile" in ctl or "protobuf" in ctl or "octet-stream" in ctl:
        return True
    base = url.split("?")[0].lower()
    return base.endswith(".pbf") or base.endswith(".mvt")


def decode_vector_tile(url, body):
    """Decode a Mapbox vector tile (protobuf bytes) into leads with exact
    lng/lat (and address/status when the tile carries them). Returns ([], keys)
    on any failure so the caller can keep going; `keys` is the set of property
    names seen, which tells us the tile schema for tightening this later."""
    try:
        import mapbox_vector_tile
    except Exception:
        return [], set(), "no-mapbox_vector_tile"
    zxy = _tile_zxy(url)
    if not zxy:
        return [], set(), "no-zxy"
    z, x, y = zxy
    try:
        # newer mapbox_vector_tile wants default_options=; older wants the kwarg
        try:
            tile = mapbox_vector_tile.decode(body, default_options={"y_coord_down": True})
        except TypeError:
            tile = mapbox_vector_tile.decode(body, y_coord_down=True)
    except Exception as e:
        return [], set(), "decode-fail:%s" % str(e)[:40]
    leads, keys = [], set()
    for _layer, lobj in (tile or {}).items():
        extent = lobj.get("extent", 4096) or 4096
        for feat in lobj.get("features", []):
            props = feat.get("properties") or {}
            keys.update(props.keys())
            low = {_nkey(k): v for k, v in props.items()}
            geom = feat.get("geometry") or {}
            lng = latv = None
            if geom.get("type") == "Point":
                c = geom.get("coordinates")
                if isinstance(c, (list, tuple)) and len(c) >= 2:
                    lng, latv = _tilepoint_to_lnglat(z, x, y, c[0], c[1], extent)
            addr = _pick(low, ADDR_KEYS)
            status = _pick(low, NET_STATUS_KEYS)
            ban = _pick(low, NET_BAN_KEYS)
            # record if we got *something* useful: an address, or a located dot
            if (addr and isinstance(addr, str)) or (lng is not None):
                leads.append({
                    "address": " ".join(addr.split())[:160] if isinstance(addr, str) else None,
                    "lat": latv, "lng": lng,
                    "status": status if isinstance(status, str) else None,
                    "ban": ban,
                    "props": props,
                })
    return leads, keys, "ok:%d" % len(leads)


_SAVED_RAW = [False]   # save AT&T's raw serviceability JSON once per run


class NetCapture:
    """Collects leads seen on the wire. Attach .handle to page.on('response');
    call .flush() per viewport to write the new ones. Handles BOTH JSON
    availability responses AND Mapbox vector tiles (protobuf), which is how the
    AT&T dealer map actually ships the dots. With debug=True it ALSO logs every
    response (URL, content-type, size) so we can find the dot endpoint."""
    def __init__(self, substr=None, debug=False):
        self.substr = substr        # restrict to URLs containing this, if set
        self.debug = debug
        self.pending = []
        self.outbox = SafePending()  # rows awaiting a sheet write; a failed
                                     # write keeps them queued (no 429 loss)
        self.seen = set()
        self.endpoints = {}          # url(no query) -> lead count, for discovery
        self.seen_urls = {}          # base url -> [content_type, hits, max_bytes]
        self.tile_keys = set()       # property names seen in vector tiles (schema)
        self.tile_status = {}        # base url -> last decode note (debug aid)

    def handle(self, response):
        try:
            url = response.url
            ct = (response.headers or {}).get("content-type", "")
            if self.debug:
                base = url.split("?")[0]
                try:
                    sz = int((response.headers or {}).get("content-length") or -1)
                except Exception:
                    sz = -1
                row = self.seen_urls.setdefault(base, [ct, 0, 0])
                row[1] += 1
                row[2] = max(row[2], sz)
            if self.substr and self.substr not in url:
                return
            ctl = ct.lower()
            low = url.lower()
            # treat it as data if the content-type OR the URL looks like data --
            # AT&T's serviceability feed must be caught even if mislabeled.
            data_url = ("serviceability" in low or "serviceab" in low
                        or "/api/" in low or "graphql" in low or "availab" in low
                        or "fiber" in low or low.endswith(".json"))
            if "json" in ctl or data_url:
                try:
                    body = response.body()
                    if not body or len(body) > 8 * 1024 * 1024:
                        return
                    data = json.loads(body)
                except Exception:
                    return
                leads = extract_leads_from_json(data)
                # ALSO run the proven extractor (catches the AT&T 'serviceability'
                # endpoint shape that the working pipeline tools rely on)
                if _extract_features is not None:
                    try:
                        for f in _extract_features(data):
                            leads.append({"address": f.get("address"),
                                          "lat": f.get("lat"), "lng": f.get("lng"),
                                          "status": f.get("status"),
                                          "ban": f.get("ban"), "props": {}})
                    except Exception:
                        pass
                # save the RAW serviceability JSON once, so we can inspect exactly
                # what AT&T sent (every field) -- locally + a sample to Drive.
                if leads and not _SAVED_RAW[0]:
                    _SAVED_RAW[0] = True
                    try:
                        here = os.path.dirname(os.path.abspath(__file__))
                        with open(os.path.join(here, "serviceability_raw.json"), "w") as f:
                            json.dump(data, f)
                        print("  (saved raw AT&T response -> serviceability_raw.json)")
                    except Exception:
                        pass
                    try:
                        drive_log("RAW %s :: %s" % (url.split("?")[0][:55],
                                                    json.dumps(data)[:480]))
                    except Exception:
                        pass
            elif _is_vector_tile(url, ct):
                try:
                    body = response.body()
                except Exception:
                    return
                if not body:
                    return
                leads, keys, note = decode_vector_tile(url, body)
                if keys:
                    self.tile_keys.update(keys)
                base = url.split("?")[0]
                self.tile_status[base] = note
            else:
                return
            if leads:
                base = url.split("?")[0]
                self.endpoints[base] = self.endpoints.get(base, 0) + len(leads)
                self.pending.extend(leads)
        except Exception:
            pass

    def dump_debug(self, path=None):
        """Print + save every endpoint the map hit, biggest first -- the dot
        data is usually a large response (a tile or an availability API)."""
        if not self.seen_urls:
            print("  (net-debug: no responses captured)")
            return
        rows = sorted(self.seen_urls.items(), key=lambda kv: -kv[1][2])

        # SHORT-LIST the likely dot/address feeds: drop fonts/images/css/js and
        # the Mapbox basemap, keep AT&T app calls + custom tilesets + JSON/pbf.
        def _is_candidate(url, ct):
            u = url.lower()
            if _is_basemap_tile(url):
                return False
            if any(u.endswith(e) for e in (".ttf", ".woff", ".woff2", ".png",
                    ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".ico")):
                return False
            if "/fonts/" in u or "/dist/" in u or "sprite" in u or "/static/" in u:
                return False
            ctl = (ct or "").lower()
            looks_data = ("json" in ctl or "protobuf" in ctl or "octet" in ctl
                          or u.endswith(".pbf") or u.endswith(".mvt")
                          or u.endswith(".geojson") or "/api/" in u or "/data/" in u
                          or "graphql" in u or "availab" in u or "fiber" in u
                          or "referral" in u or "/v4/" in u or "/v1/" in u)
            return looks_data
        cands = [(b, v) for b, v in rows if _is_candidate(b, v[0])]
        print("\n=== CANDIDATE DATA ENDPOINTS (likely the dot/address feed) ===")
        if cands:
            print("  %-9s %-22s %s" % ("bytes", "content-type", "url"))
            for base, (ct, hits, mx) in cands[:20]:
                print("  %-9s %-22s %s" % (mx, ct[:22], base[:95]))
        else:
            print("  (none stood out -- the full list is below / in the log)")

        print("\n=== all endpoints the page hit (biggest first) ===")
        print("  %-9s %-30s %s" % ("bytes", "content-type", "url"))
        for base, (ct, hits, mx) in rows[:25]:
            print("  %-9s %-30s %s" % (mx, ct[:30], base[:90]))
        if self.tile_keys:
            print("\n=== vector-tile fields decoded from the dots ===")
            print("  " + ", ".join(sorted(self.tile_keys)))
        if self.tile_status:
            print("\n=== vector-tile decode results ===")
            for base, note in list(self.tile_status.items())[:15]:
                print("  %-12s %s" % (note, base[:80]))
        if path:
            try:
                with open(path, "w") as f:
                    f.write("max_bytes\tcontent_type\thits\turl\n")
                    for base, (ct, hits, mx) in rows:
                        f.write("%d\t%s\t%d\t%s\n" % (mx, ct, hits, base))
                    f.write("\n# vector-tile property fields seen:\n# %s\n"
                            % ", ".join(sorted(self.tile_keys)))
                    f.write("\n# vector-tile decode results:\n")
                    for base, note in self.tile_status.items():
                        f.write("# %s\t%s\n" % (note, base))
                print("  full list -> %s" % path)
            except Exception as e:
                print("  (couldn't write %s: %s)" % (path, e))

    def flush(self, ws, seen, area_label, dry):
        """Write the new captured addresses. BATCHED -- one append_rows call for
        all of them, not one append_row per address (which blew the Google Sheets
        'write requests per minute' quota -> 429 errors). Rows travel through the
        SafePending outbox: they are removed ONLY after the write succeeds, so a
        429/network error keeps them queued for the next flush instead of losing
        them (the old pop-before-write data-loss bug). Junk placeholder addresses
        (UNIT DUMMY/CTR/COIN) never reach the sheet, and dedup is drift-proof
        (canonical core-address key -- 'STE 1800' vs 'UNIT COIN' vs ZIP drift all
        resolve to the same building)."""
        if _SPLIT[0]:
            # split mode: EVERY flush path becomes a local disk append; the
            # uploader process owns the sheet. Motion never waits on Google.
            return self.flush_local(seen, area_label, dry)
        self.seen = seen
        new_rows, new_records = [], []
        while self.pending:
            ld = self.pending.pop()
            addr = (ld.get("address") or "").strip()
            if not addr or is_junk_address(addr):
                continue                 # junk placeholders never reach the sheet
            addr, _stripped = clean_address(addr)
            if not seen.is_new(addr):
                continue                 # same building, any drift/unit spelling
            dot_status = classify_status(text=ld.get("status"), ban=ld.get("ban"))
            if dot_color(dot_status) == "GREY":
                continue   # GREY = existing fiber customer -> leave out
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            # clean columns + the business merged inline when the address matches a
            # scraped business: Address | Dot Color | Captured At | Business | Phone.
            _bidx = _BIZ.get("index") or {}
            _b = _bidx.get(_norm_addr(addr)) if _bidx else None
            new_rows.append([addr, dot_color(dot_status), ts,
                             (_b or {}).get("name", ""), (_b or {}).get("phone", "")])
            new_records.append({"address": addr, "dot_status": dot_status,
                                "zone_label": "WORKING", "popup_status": ld.get("status"),
                                "ban": ld.get("ban"), "area": area_label, "ts": ts,
                                "via": "network", "lat": ld.get("lat"), "lng": ld.get("lng")})
        if not new_rows and not len(self.outbox):
            return 0
        for rec in new_records:        # local backup (no quota)
            append_jsonl(rec)
        if new_rows:
            try:    # sample addresses to the Drive log so Claude can verify accuracy
                drive_log("ADDRS +%d e.g.: %s" % (
                    len(new_rows), " | ".join(r[0] for r in new_rows[:4])))
            except Exception:
                pass
        if dry or ws is None:
            for r in new_rows[:20]:
                print("   + %s | %s" % (r[0], r[1]))
        else:
            for r in new_rows:
                self.outbox.add(r)

            def _write(batch):
                try:
                    ws.append_rows(batch, value_input_option="RAW")
                except Exception as e:
                    print("   batch write error (rows kept, will retry): %s"
                          % str(e)[:120])
                    raise

            self.outbox.flush(_write, batch_size=500)   # ONE call per 500 rows
            if len(self.outbox):
                print("   (write deferred: %d row(s) queued for the next flush)"
                      % len(self.outbox))
        # COMBO: match these just-captured leads against the scraped businesses and
        # write any hits to the green/gold business tabs -- live, as we sweep.
        try:
            match_leads_to_biz(new_records)
        except Exception as e:
            print("   (biz match skipped: %s)" % str(e)[:80])
        # MOTION IS SACRED: the old periodic reload_biz_index()+_backlog_match()
        # that lived HERE re-read the whole 18k-row Maps Businesses tab and
        # re-scanned every prior capture ON THE PAN PATH -- a 10-30s read between
        # two pans, i.e. exactly "the motion stopped because it was reading
        # something." REMOVED from the hot path. Live cross-matching is NOT lost:
        # the scraper matches every business it adds against Precise Fiber from
        # ITS side (unified matching), and the hunter re-matches everything at
        # the next startup (_backlog_match). Nothing heavy runs between pans.
        return len(new_rows)

    def flush_local(self, seen, area_label, dry):
        """SPLIT-MODE flush: drain captures to the local JSONL ONLY (a disk
        append, microseconds) -- the separate --uploader process ships them to
        the sheet. The motion process never touches Google. (Patrick 2026-07-02:
        'backend memory processing separate from motion'.)"""
        new_records = []
        while self.pending:
            ld = self.pending.pop()
            addr = (ld.get("address") or "").strip()
            if not addr or is_junk_address(addr):
                continue
            addr, _stripped = clean_address(addr)
            if not seen.is_new(addr):
                continue
            dot_status = classify_status(text=ld.get("status"), ban=ld.get("ban"))
            if dot_color(dot_status) == "GREY":
                continue
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            new_records.append({"address": addr, "dot_status": dot_status,
                                "zone_label": "WORKING", "popup_status": ld.get("status"),
                                "ban": ld.get("ban"), "area": area_label, "ts": ts,
                                "via": "network", "lat": ld.get("lat"), "lng": ld.get("lng")})
        if not new_records:
            return 0
        if dry:
            for r in new_records[:20]:
                print("   + %s | %s" % (r["address"], dot_color(r["dot_status"])))
            return len(new_records)
        for rec in new_records:
            append_jsonl(rec)          # the uploader tails this file
        return len(new_records)

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
_DUMPED_CONTROLS = [False]


def dump_clickables(page):
    """List the visible buttons/links on the page so we can find the real
    'search this area' control (its text/label isn't what we guessed)."""
    try:
        items = page.evaluate(
            """() => {
                const out = [];
                const els = document.querySelectorAll(
                  "button, a, [role=button], input[type=button], input[type=submit]");
                for (const e of els) {
                    let t = (e.innerText || e.value || e.getAttribute('aria-label')
                             || e.title || '').trim().replace(/\\s+/g,' ');
                    const vis = e.offsetParent !== null;
                    if (vis && t) out.push(t.slice(0, 40));
                    if (out.length > 50) break;
                }
                return out;
            }""")
        if items:
            print("  >> CONTROLS visible on the map (which is the search button?):")
            for t in items[:50]:
                print("       [%s]" % t)
    except Exception:
        pass


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
EXPECTED_CREDS_PROJECT = "fiberscanner-493900"   # the only project that works


def _creds_candidates():
    home = os.path.expanduser("~")
    return [
        "google_creds.json",                                    # cwd
        os.path.join(home, "optimus", "google_creds.json"),     # brain canonical
        os.path.join(home, "Optimus", "google_creds.json"),
        os.path.join(home, "Desktop", "google_creds.json"),
        os.path.join(home, "OneDrive", "Desktop", "google_creds.json"),
        os.path.join(home, "Downloads", "google_creds.json"),
        "/storage/emulated/0/Download/google_creds.json",       # Pydroid
    ]


def _read_valid_creds(path):
    """Return parsed creds if the file is a usable service-account key, else None."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            info = json.load(f)
    except Exception:
        return None
    if isinstance(info, dict) and info.get("client_email") and info.get("private_key"):
        return info
    return None


def find_creds():
    """Pick the RIGHT creds out of all the scattered copies. Patrick has many
    google_creds.json across devices -- some wrong-project, some corrupt -- so
    don't take the first one found: scan all candidates, skip invalid ones, and
    prefer the fiberscanner-493900 key. Returns a path or None."""
    fallback = None
    for p in _creds_candidates():
        if not os.path.exists(p):
            continue
        info = _read_valid_creds(p)
        if not info:
            print("  (skipping invalid/corrupt creds at %s)" % p)
            continue
        if info.get("project_id") == EXPECTED_CREDS_PROJECT:
            return p                      # exact match wins immediately
        if fallback is None:
            fallback = p                  # valid but maybe wrong project
    return fallback


NEW_SHEET_ID_FILE = os.path.join(os.path.expanduser("~"), "optimus", "optimus_sheet_id.txt")


def _sheet_is_full(sh):
    """Probe: can we add even a 1-cell tab? If that raises the cell-cap error, the
    workbook is full and won't take any more writes."""
    try:
        tmp = sh.add_worksheet(title="_optimus_probe", rows="1", cols="1")
        try:
            sh.del_worksheet(tmp)
        except Exception:
            pass
        return False
    except Exception as e:
        m = str(e).lower()
        return ("cells in the workbook" in m or "10000000" in m
                or "increase the number of cells" in m)


def _authorize(creds_file):
    """gspread.authorize + a HARD HTTP TIMEOUT on every Sheets call. Without this,
    requests has NO timeout, so a single hung Google API write blocks forever and
    FREEZES the pan loop (a real 'it stopped' cause). We force ~15s on every HTTP
    call across gspread 5 (client.session) and gspread 6 (client.http_client.session)."""
    import gspread
    from google.oauth2.service_account import Credentials
    client = gspread.authorize(
        Credentials.from_service_account_file(creds_file, scopes=SCOPES))
    for sess in (getattr(client, "session", None),
                 getattr(getattr(client, "http_client", None), "session", None)):
        if sess is None or getattr(sess, "_optimus_timeout", False):
            continue
        _orig = sess.request
        def _req(method, url, *a, __o=_orig, **kw):
            kw.setdefault("timeout", 15)
            return __o(method, url, *a, **kw)
        sess.request = _req
        sess._optimus_timeout = True
    return client


def open_sheet():
    """Open the production sheet and the Precise Fiber tab. We do NOT create a new
    sheet -- if it's full, AUTO-CLEAN this one (delete junk tabs, trim) so it accepts
    writes again, then keep going. Same sheet, same link everyone has."""
    creds_file = find_creds()
    if not creds_file:
        print("No valid google_creds.json found among the usual paths; running "
              "WITHOUT the sheet (captures print only). Fix with the Drive "
              "download or drop the fiberscanner key at ~/optimus/google_creds.json.")
        return None
    print("Using creds: %s" % creds_file)
    try:
        client = _authorize(creds_file)
        sh = client.open_by_key(SHEET_ID)
        if _sheet_is_full(sh):
            print("The sheet is FULL -- auto-cleaning the garbage so leads can save...")
            try:
                clean_sheet()
            except Exception as e:
                print("  (auto-clean hiccup: %s)" % str(e)[:80])
            sh = client.open_by_key(SHEET_ID)   # re-open after cleaning
        try:
            ws = sh.worksheet(OUT_TAB)
        except Exception:
            ws = sh.add_worksheet(title=OUT_TAB, rows="5000", cols="8")
        if not ws.get_all_values():
            ws.append_row(["Address", "Dot Color", "Captured At", "Business", "Phone"])
        return ws
    except Exception as e:
        print("WARNING: couldn't open the Google Sheet (%s)." % str(e)[:100])
        if "cells in the workbook" in str(e).lower() or "increase the number" in str(e).lower():
            print("         The sheet is FULL -- run:  python precise_fiber_hunter.py --clean-sheet")
        print("         Running WITHOUT the sheet -- captures print only.")
        return None


def clean_sheet():
    """Free space in the production sheet so it accepts writes again, WITHOUT making
    a new one: delete junk tabs (anything not part of the pipeline), trim the Hunter
    Status heartbeat log to the last 100 lines, and resize every kept tab down to its
    real data so empty allocated cells are released. Never deletes lead/business data.
    Run with --clean-sheet."""
    import gspread
    from google.oauth2.service_account import Credentials
    # The Optimus pipeline tabs -- everything ELSE is junk (old MapMan run, test
    # rows) and is safe to delete to reclaim cells.
    pipeline_tabs = {OUT_TAB, MAPS_TAB, GREEN_BIZ_TAB, ORANGE_BIZ_TAB,
                     "Enriched Leads", STATUS_TAB}
    creds = find_creds()
    if not creds:
        print("No google_creds.json found -- can't clean the sheet."); return
    client = _authorize(creds)
    sh = client.open_by_key(SHEET_ID)
    keep = {t.lower() for t in pipeline_tabs}
    wss = sh.worksheets()
    print("Cleaning sheet -- %d tabs. Keeping: %s\n"
          % (len(wss), ", ".join(sorted(pipeline_tabs))))
    for ws in wss:
        title = ws.title
        cells = ws.row_count * ws.col_count
        if title.lower() not in keep:
            try:
                if len(sh.worksheets()) > 1:
                    sh.del_worksheet(ws)
                    print("  DELETED junk tab '%s' (%d cells freed)" % (title, cells))
                else:
                    print("  kept '%s' (last remaining tab)" % title)
            except Exception as e:
                print("  couldn't delete '%s': %s" % (title, str(e)[:50]))
            continue
        # kept tab -> trim to fit its data
        try:
            vals = ws.get_all_values()
            if title.lower() == STATUS_TAB.lower() and len(vals) > 120:
                tail = ([vals[0]] if vals else []) + vals[-100:]
                ws.clear()
                if tail:
                    ws.append_rows(tail, value_input_option="RAW")
                vals = tail
                print("  trimmed '%s' to last 100 heartbeats" % title)
            used_rows = max(len(vals) + 5, 10)
            used_cols = max((max((len(r) for r in vals), default=1)), 1)
            if used_rows < ws.row_count or used_cols < ws.col_count:
                ws.resize(rows=used_rows, cols=used_cols)
                print("  trimmed '%s' -> %d x %d (was %d cells)"
                      % (title, used_rows, used_cols, cells))
            else:
                print("  '%s' already tight (%d x %d)" % (title, ws.row_count, ws.col_count))
        except Exception as e:
            print("  couldn't trim '%s': %s" % (title, str(e)[:50]))
    # put the kept tabs in a clear, logical order so there's no confusion about
    # which is which: leads, then the two biz matches, enriched, businesses, status.
    try:
        order = [OUT_TAB, GREEN_BIZ_TAB, ORANGE_BIZ_TAB, "Enriched Leads",
                 MAPS_TAB, STATUS_TAB]
        cur = {w.title: w for w in sh.worksheets()}
        ordered = [cur[t] for t in order if t in cur]
        ordered += [w for w in sh.worksheets() if w not in ordered]
        sh.reorder_worksheets(ordered)
        print("  ordered tabs: %s" % " | ".join(w.title for w in ordered))
    except Exception as e:
        print("  (couldn't reorder tabs: %s)" % str(e)[:50])
    # drop any cached fresh-sheet redirect so we go back to using THIS cleaned sheet
    try:
        if os.path.exists(NEW_SHEET_ID_FILE):
            os.remove(NEW_SHEET_ID_FILE)
            print("  (cleared the fresh-sheet redirect -- back to the production sheet)")
    except Exception:
        pass
    print("\nDone. The sheet should accept writes again -- run the hunter normally.")


def already_seen(ws):
    """Resume: read existing addresses so a re-run skips them (survives crashes).
    Returns a Deduper keyed on the canonical CORE address (unit/ZIP/case drift
    all resolve to the same building), seeded from the sheet's address column."""
    if not ws:
        return Deduper()
    try:
        rows = ws.get_all_values()
    except Exception:
        return Deduper()
    return Deduper(r[0] for r in rows[1:] if r and r[0].strip())


def backfill_jsonl(ws, seen):
    """Recover captures saved locally but never written to the sheet (e.g. while the
    old sheet was full) -- write any precise_addresses.jsonl address not already in
    the sheet into the Precise Fiber tab. Batched, best-effort. Returns count."""
    if ws is None or not os.path.exists(JSONL_PATH):
        return 0
    rows = []
    try:
        with open(JSONL_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                addr = (d.get("address") or "").strip()
                if not addr or is_junk_address(addr):
                    continue
                ds = d.get("dot_status")
                if dot_color(ds) == "GREY":
                    continue
                addr, _stripped = clean_address(addr)
                if not seen.is_new(addr):
                    continue
                _bidx = _BIZ.get("index") or {}
                _b = _bidx.get(_norm_addr(addr)) if _bidx else None
                rows.append([addr, dot_color(ds), d.get("ts") or "",
                             (_b or {}).get("name", ""), (_b or {}).get("phone", "")])
    except Exception as e:
        print("  (backfill read error: %s)" % str(e)[:60])
        return 0
    if not rows:
        return 0
    print("  Backfilling %d locally-saved leads into the sheet..." % len(rows))
    try:
        for i in range(0, len(rows), 500):
            ws.append_rows(rows[i:i + 500], value_input_option="RAW")
    except Exception as e:
        print("  (backfill stopped: %s)" % str(e)[:60])
    return len(rows)


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


_COLOR_WINDOWS_BY_NAME = [("GREEN", GREEN_MIN, GREEN_MAX),
                          ("GOLD", GOLD_MIN, GOLD_MAX),
                          ("GRAY", GRAY_MIN, GRAY_MAX)]


def _color_from_status(txt):
    """Map a feature's status TEXT to a dot colour ONLY when it explicitly says
    so -- otherwise return None and let the pixel sample decide (avoids writing
    an ambiguous-coded dot as a lead)."""
    if not txt or not isinstance(txt, str):
        return None
    low = txt.lower()
    if "copper" in low:
        return "GOLD"
    if ("non-customer" in low or "noncustomer" in low or "eligible" in low
            or "serviceable" in low or "available" in low):
        return "GREEN"
    if "customer" in low or "subscriber" in low or "existing" in low or "fiber-customer" in low:
        return "GRAY"
    return None


def classify_pixel(arr, x, y, rad=4):
    """Sample a small window around (x, y) in an HxWx3 RGB array and return the
    dot color there: GREEN / GOLD / GRAY / None. Used to color a dot whose EXACT
    screen position we already know from the Mapbox backend -- so we never guess
    on random screen pixels (which mis-read portal buttons)."""
    import numpy as np
    h, w = arr.shape[0], arr.shape[1]
    x, y = int(x), int(y)
    x0, x1 = max(0, x - rad), min(w, x + rad + 1)
    y0, y1 = max(0, y - rad), min(h, y + rad + 1)
    if x0 >= x1 or y0 >= y1:
        return None
    patch = arr[y0:y1, x0:x1]
    r, g, b = patch[:, :, 0], patch[:, :, 1], patch[:, :, 2]
    best_name, best_n = None, 1
    for name, cmin, cmax in _COLOR_WINDOWS_BY_NAME:
        mask = ((r >= cmin[0]) & (r <= cmax[0]) &
                (g >= cmin[1]) & (g <= cmax[1]) &
                (b >= cmin[2]) & (b <= cmax[2]))
        n = int(mask.sum())
        if n > best_n:
            best_name, best_n = name, n
    return best_name


def drain_viewport_backend(page, ws, seen, area_label, dry, zone_label="WORKING"):
    """THE backend read (no clicking). Ask the map for every non-basemap dot,
    colour each one by sampling its EXACT pixel in a single screenshot, and write
    the GREEN (eligible) + GOLD (copper-upgrade) ones to the sheet. GREY = existing
    fiber customer, skipped. Returns the count, or None if the map hook isn't live
    yet (so the caller knows the read wasn't available)."""
    import io
    import numpy as np
    from PIL import Image
    data, _frame_idx = eval_best_frame(page, MAPBOX_DOTS_JS)
    if not data or not isinstance(data, dict):
        return None
    dots = data.get("dots") or []
    rect = data.get("rect") or {"left": 0, "top": 0}
    if not dots:
        print("  viewport (backend): 0 dots in view")
        return 0
    try:
        raw = page.screenshot(type="png")
        arr = np.array(Image.open(io.BytesIO(raw)).convert("RGB"))
    except Exception:
        return None
    vp = page.viewport_size or VIEWPORT
    img_h, img_w = arr.shape[0], arr.shape[1]
    sx = img_w / vp["width"] if vp.get("width") else 1.0
    sy = img_h / vp["height"] if vp.get("height") else 1.0
    rleft, rtop = rect.get("left", 0), rect.get("top", 0)
    greens = golds = grays = other = captured = 0
    for d in dots:
        sxpix = (rleft + d.get("x", 0)) * sx
        sypix = (rtop + d.get("y", 0)) * sy
        props = d.get("props") or {}
        # prefer an explicit status property; else colour from the exact pixel
        status_txt = feature_status_text(props)
        color = _color_from_status(status_txt)   # trust only explicit status
        if color is None:
            color = classify_pixel(arr, sxpix, sypix)   # else the dot's own pixel
        if color == "GREEN":
            greens += 1
        elif color == "GOLD":
            golds += 1
        elif color == "GRAY":
            grays += 1
            continue            # existing customer -> skip
        else:
            other += 1
            continue            # not a recognizable dot -> skip
        addr = feature_address(props)
        lat, lng = d.get("lat"), d.get("lng")
        if not addr and lat is not None and lng is not None:
            addr = "(%.6f, %.6f)" % (lat, lng)   # no street text -> use the pin
        if not addr:
            continue
        dot_status = classify_status(text=status_txt or color, color=color)
        if record_capture(ws, seen, area_label, dry, addr, status_txt, None,
                          dot_status, via="backend", zone_label=zone_label,
                          lat=lat, lng=lng):
            captured += 1
    print("  viewport (backend): %d green + %d gold + %d grey (skipped) "
          "+ %d other -> captured %d" % (greens, golds, grays, other, captured))
    drive_log("VIEWPORT backend green=%d gold=%d grey=%d other=%d captured=%d"
              % (greens, golds, grays, other, captured))
    return captured


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
    # 2) Escape key FIRST (no click -> can't land on nav and flip to portal)
    try:
        page.keyboard.press("Escape")
        time.sleep(0.15)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# map controls
# ----------------------------------------------------------------------------
def focus_map(page):
    """Click an empty part of the MAP CANVAS so keyboard pan/zoom registers.
    Proven by hand (fiber_precise_pipeline): you must click the map before the
    arrow keys / +/- work. Uses the canvas bounding box so the click lands ON
    the map (never on nav), then Escape in case it grazed a dot."""
    for sel in (".mapboxgl-canvas", ".maplibregl-canvas", "canvas"):
        try:
            cv = page.locator(sel).first
            if cv.count() == 0:
                continue
            box = cv.bounding_box()
            if box and box["width"] > 100 and box["height"] > 100:
                page.mouse.click(box["x"] + box["width"] * 0.18,
                                 box["y"] + box["height"] * 0.22)
                time.sleep(0.35)
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
                time.sleep(0.2)
                return True
        except Exception:
            pass
    # fallback: old fixed-fraction point
    try:
        x, y = empty_map_point(page)
        page.mouse.click(x, y)
        time.sleep(0.3)
    except Exception:
        pass
    return False


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


SEARCH_LABELS = ["Search this area", "Search area", "Search this map",
                 "Redo search in map", "Redo search here", "Search here",
                 "Search as I move the map", "Update results", "Search nearby"]

DRY_WARN_FLUSHES = 25   # this many 0-lead writes in a row -> DRY AREA alarm
                        # (info only -- dry ground is NORMAL, the spiral keeps
                        # expanding through it; Patrick 2026-07-02: no correcting)
FLUSH_GAP_SECS = 4      # MOTION IS SACRED: sheet writes at most this often; the
                        # pans in between never touch the network


# CSS/aria candidates for the search-area control (label text isn't the only
# way it can be marked up -- and it can live inside a FRAME with the map).
SEARCH_SELECTORS = ["[aria-label*='search this area' i]",
                    "[aria-label*='search area' i]",
                    "button[class*='search-area' i]",
                    "button[class*='searcharea' i]",
                    "[class*='search-this-area' i]",
                    "[data-testid*='search-area' i]"]


def search_this_area(page):
    """After a pan the new view's dots only load when the map's 'search this
    area' control is clicked. The exact label varies AND the button can live in
    a frame with the map (a top-page text search finds only the nav menu), so:
    search the page + EVERY frame, by text AND by aria-label/CSS. If nothing
    matches, dump the visible controls ONCE so we can pin the right one. Note
    the pan itself usually triggers the fetch too -- NetCapture is always
    listening -- so a missing button slows nothing down."""
    for ctx in [page] + list(page.frames):
        for label in SEARCH_LABELS:
            try:
                btn = ctx.get_by_text(label, exact=False)
                if btn.count() > 0:
                    print("  -> pressing '%s' (fetching dots from server)..." % label)
                    try:
                        # Cap the click at 1s. It's only a CAP -- a normal view's
                        # button is clickable instantly. On a slow/stuck view it
                        # bails so the loop pans on (capture rides the pan anyway).
                        btn.first.click(timeout=1000)
                        return True
                    except Exception:
                        print("     (search didn't take -- moving on, panning next)")
                        return False
            except Exception:
                pass
        for sel in SEARCH_SELECTORS:
            try:
                el = ctx.query_selector(sel)
                if el and el.is_visible():
                    print("  -> pressing search control %s (fetching dots)..." % sel)
                    try:
                        el.click(timeout=1000)
                        return True
                    except Exception:
                        print("     (search didn't take -- moving on, panning next)")
                        return False
            except Exception:
                pass
    print("  -> (no 'search this area' control found this view)")
    if not _DUMPED_CONTROLS[0]:
        _DUMPED_CONTROLS[0] = True
        dump_clickables(page)
    return False


MAP_VIEW_TEXTS = ["Fiber Availability Map", "Availability Map", "Fiber Map"]


def on_map(page):
    """True if the Fiber Map is showing (not the portal landing). Checks the map
    canvas/controls AND the 'Search address' box (which is on the map, never the
    portal) -- so we don't mistake the map for the portal and click 'Fiber Map',
    which flips the view."""
    for sel in (".mapboxgl-canvas", ".maplibregl-canvas", ".mapboxgl-map",
                ".maplibregl-map", ".mapboxgl-ctrl-geocoder",
                ".maplibregl-ctrl-geocoder", "canvas",
                "input[placeholder*='Search address' i]",
                "input[placeholder*='address' i]"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except Exception:
            pass
    return False


def _click_map_button(page):
    """Click the 'Fiber Availability Map' button if it's on the page. Returns
    True if clicked."""
    for t in MAP_VIEW_TEXTS:
        try:
            el = page.get_by_text(t, exact=False)
            if el.count() > 0:
                el.first.click(timeout=3000)
                time.sleep(3.5)
                return True
        except Exception:
            pass
    return False


def open_map_view(page):
    """Reach the dot map from wherever login dropped us. The path Patrick walks by
    hand: the 'you Refer' HOME -> click the 'AT&T Fiber' tile -> the /yourefer/fiber
    page -> click 'Fiber Availability Map' -> the map. So: (1) if already on the map,
    do nothing (re-clicking flips map<->portal). (2) try the map button directly.
    (3) if it's not here, we're probably on the home page -> click 'AT&T Fiber' (or
    just navigate to the fiber URL), then click the map button. Confirmed layout
    live 2026-07-01 from Patrick's screenshots."""
    if on_map(page):
        return False   # already on the map -- never re-click (no flip)
    if _click_map_button(page):
        return True
    # not on the fiber page yet -> get there. First the 'AT&T Fiber' tile...
    try:
        fib = page.get_by_text("AT&T Fiber", exact=False)
        if fib.count() > 0:
            fib.first.click(timeout=3000)
            time.sleep(2.5)
            if _click_map_button(page):
                return True
    except Exception:
        pass
    # ...else just navigate straight to the fiber page URL, then click the map.
    try:
        if "/yourefer/fiber" not in (page.url or ""):
            page.goto(MAP_URL, timeout=30000)
            time.sleep(3)
    except Exception:
        pass
    return _click_map_button(page)


_MAP_OBJ = [None]     # tri-state: None=untried, True=recovered, False=gave up
_MAP_TRIES = [0]      # how many recovery attempts so far
_MAP_MAX_TRIES = 15   # after this many misses, stop walking the fiber tree every pan


def recover_map(page):
    """Try to recover the HIDDEN Mapbox map object (getContext + React-fiber walk,
    see MAP_RECOVER_JS). Populates window.__optimusMaps so pan_map_js() can use
    the guaranteed map.panBy() motion. Returns True if a live map is reachable.
    Remembers success; after a bounded number of misses it gives up (returns
    False without re-walking) so a site where the object truly isn't reachable
    falls straight through to the drag with no per-pan cost."""
    if _MAP_OBJ[0] is True:
        return True
    if _MAP_OBJ[0] is False:
        return False
    _MAP_TRIES[0] += 1
    for ctx in [page] + list(page.frames):
        try:
            if ctx.evaluate(MAP_RECOVER_JS):
                _MAP_OBJ[0] = True
                print("  [motion] recovered the map object -- panning with "
                      "map.panBy() now (guaranteed movement).")
                return True
        except Exception:
            pass
    if _MAP_TRIES[0] >= _MAP_MAX_TRIES:
        _MAP_OBJ[0] = False
        print("  [motion] map object not reachable on this site -- using the "
              "verified drag from here on.")
    return False


def pan_map_js(page, direction):
    """Pan the Mapbox map PROGRAMMATICALLY via map.panBy() -- GUARANTEED movement,
    immune to the drag being swallowed by the map (the #1 'it stopped' cause). Only
    works once recover_map() has grabbed the hidden map object. Shifts ~70% of a
    viewport so adjacent cells overlap a little. Returns True only if it panned."""
    dx = {"left": -1, "right": 1, "up": 0, "down": 0}[direction]
    dy = {"left": 0, "right": 0, "up": -1, "down": 1}[direction]
    for ctx in [page] + list(page.frames):
        try:
            ok = ctx.evaluate(
                """([dx, dy]) => {
                    const m = (window.__optimusMaps || [])[0];
                    if (!m || !m.panBy) return false;
                    const c = m.getContainer().getBoundingClientRect();
                    m.panBy([dx * c.width * 0.7, dy * c.height * 0.7], {duration: 0});
                    return true;
                }""", [dx, dy])
            if ok:
                return True
        except Exception:
            pass
    return False


def pan(page, direction):
    """Move to the next patch the PROVEN way: click the map to focus it, then
    press the arrow key (the programmatic panBy does nothing here because the map
    object is hidden -- 'it's not moving'). Then 'Search this area' to fetch the
    new view's dots."""
    print("  -> clicking map to focus, then arrow-key panning %s..." % direction)
    focus_map(page)   # click the canvas so the keyboard registers
    key = {"left": "ArrowLeft", "right": "ArrowRight",
           "up": "ArrowUp", "down": "ArrowDown"}[direction]
    for _ in range(PAN_PRESSES):
        try:
            page.keyboard.press(key)
        except Exception:
            pass
        time.sleep(0.12)
    time.sleep(WAIT_AFTER_PAN)
    search_this_area(page)   # load the new view's dots


def _map_canvas_box(page):
    """Bounding box (viewport coords) of the map canvas, searching the top page
    AND every child frame -- the AT&T map can render inside a frame, in which
    case a top-page query finds nothing (that's why it 'wasn't moving')."""
    sels = (".mapboxgl-canvas", ".maplibregl-canvas", "canvas")
    contexts = [page] + list(page.frames)
    for ctx in contexts:
        for sel in sels:
            try:
                cv = ctx.locator(sel).first
                if cv.count() == 0:
                    continue
                b = cv.bounding_box()
                if b and b["width"] > 100 and b["height"] > 100:
                    return b
            except Exception:
                pass
    return None


def _viewport_map_box(page):
    """Fallback drag region = the map area of the VIEWPORT (config fractions).
    Used when no canvas element is reachable (it's in a hidden/cross-origin
    frame). page.mouse works in viewport coords, so dragging here pans the map
    exactly like fiber_hunter's pyautogui drag from the map centre."""
    vp = page.viewport_size or VIEWPORT
    return {"x": vp["width"] * MAP_LEFT_FRAC,
            "y": vp["height"] * MAP_TOP_FRAC,
            "width": vp["width"] * (MAP_RIGHT_FRAC - MAP_LEFT_FRAC),
            "height": vp["height"] * (MAP_BOTTOM_FRAC - MAP_TOP_FRAC)}


def _view_sig(page):
    """A cheap fingerprint of the current view -- used to tell if a pan actually
    MOVED the map (different pixels = it moved). Returns a hash or None."""
    try:
        return hashlib.md5(page.screenshot(type="png")).hexdigest()
    except Exception:
        return None


def _do_drag(page, direction, frac):
    """The raw drag gesture at a given distance fraction. Returns True if the drag
    ran, False only if the browser is gone (page.mouse threw)."""
    box = _map_canvas_box(page)
    if not box:
        box = _viewport_map_box(page)   # canvas hidden in a frame -> drag screen
    cx = box["x"] + box["width"] / 2.0
    cy = box["y"] + box["height"] / 2.0
    sx, sy = {"right": (-1, 0), "left": (1, 0),
              "down": (0, -1), "up": (0, 1)}[direction]
    dx = sx * box["width"] * frac
    dy = sy * box["height"] * frac
    try:
        page.mouse.move(cx, cy)
        page.mouse.down()
        # A too-fast flick (down->move->up with no hold) can be read by Mapbox as a
        # CLICK, not a drag -> the map doesn't pan. Hold briefly after down so the
        # grab registers, move in TWO stages while held so it's an unambiguous
        # drag-pan, then settle before release so the pan commits.
        page.wait_for_timeout(60)
        page.mouse.move(cx + dx * 0.5, cy + dy * 0.5, steps=6)
        page.mouse.move(cx + dx, cy + dy, steps=6)
        page.wait_for_timeout(40)
        page.mouse.up()
    except Exception as e:
        print("     drag failed: %s" % str(e)[:70])
        return False
    return True


def _arrow_pan(page, direction):
    """Fallback motion: focus the map canvas, then arrow-key pan. Some views honor
    keys after a focus click even when a drag is being swallowed."""
    try:
        focus_map(page)
        key = {"left": "ArrowLeft", "right": "ArrowRight",
               "up": "ArrowUp", "down": "ArrowDown"}[direction]
        for _ in range(PAN_PRESSES):
            page.keyboard.press(key)
            time.sleep(0.05)
        return True
    except Exception:
        return False


def mouse_drag(page, direction, quiet=False, verify=False):
    """PAN the map. FAST by default: just the proven hardened drag, NO screenshots
    (the gesture already lands reliably, so normal sweeping stays quick). Pass
    verify=True to screenshot before/after and ESCALATE (bigger drag, then focus+
    arrow-keys) if the view didn't change -- used ONLY when the sweep suspects it's
    stuck (a run of empty cells), so we don't pay the screenshot cost every pan.
    Returns False ONLY if the browser is gone. quiet=True = fast silent pass-through.
    Drag the content the OPPOSITE way you want the viewport to move."""
    if quiet:
        return _do_drag(page, direction, DRAG_FRAC)
    src = "canvas" if _map_canvas_box(page) else "screen"
    print("  -> PAN %s: drag %s" % (direction, src))
    if not verify:
        # FAST PATH -- no before/after screenshots (the common case).
        ok = _do_drag(page, direction, DRAG_FRAC)
        if ok:
            time.sleep(WAIT_AFTER_PAN)
        return ok
    # VERIFY PATH -- only when the caller thinks it may be stuck.
    before = _view_sig(page)
    if not _do_drag(page, direction, DRAG_FRAC):
        return False                     # browser gone -> let the sweep stop
    time.sleep(WAIT_AFTER_PAN)
    if before is None or _view_sig(page) != before:
        return True                      # moved (or can't tell) -> good
    # DIDN'T MOVE -> (1) a bigger drag
    if not _do_drag(page, direction, min(0.9, DRAG_FRAC * 1.8)):
        return False
    time.sleep(WAIT_AFTER_PAN)
    if _view_sig(page) != before:
        print("     (needed a bigger drag)")
        return True
    # (2) focus the canvas + arrow keys
    _arrow_pan(page, direction)
    time.sleep(WAIT_AFTER_PAN)
    if _view_sig(page) != before:
        print("     (fell back to arrow keys)")
        return True
    print("     (view unchanged -- area may be identical or map briefly stuck; continuing)")
    return True


def pan_next(page, direction):
    """Move to the next cell, PREFERRING the guaranteed map-object pan.
      1) recover the hidden map object (once) and pan with map.panBy() -- this
         cannot be 'swallowed' the way a drag can, so the map always moves.
      2) if the object isn't reachable here, fall back to the hardened drag with
         movement-verification (bigger drag -> arrow keys) so a swallowed drag
         still escalates instead of silently doing nothing.
    Returns False ONLY when the browser is gone (so the sweep stops cleanly)."""
    if recover_map(page):
        if pan_map_js(page, direction):
            time.sleep(WAIT_AFTER_PAN)
            return True
        # object was there but panBy failed this once -> fall through to drag
    # no map object on this site -> verified drag (escalates if it didn't move)
    return mouse_drag(page, direction, verify=True)


def sweep_backend(page, ws, seen, area_label, dry, cols, rows, capture):
    """FAST auto-sweep with the proven mouse-drag motion. Per cell: nudge the
    serviceability fetch, then FLUSH the backend capture (no clicking) to the
    sheet; then DRAG to the next cell, snaking across a cols x rows grid. The
    drag itself triggers AT&T's fetch and NetCapture reads it off the wire."""
    total = 0
    for r in range(rows):
        for c in range(cols):
            if on_map(page):
                search_this_area(page)        # belt+suspenders fetch trigger
            time.sleep(SEARCH_SETTLE)
            n = capture.flush(ws, seen, area_label, dry)
            total += n
            print("  [cell r%d c%d] +%d off the server" % (r, c, n))
            if c < cols - 1:
                mouse_drag(page, "right" if r % 2 == 0 else "left")
        if r < rows - 1:
            mouse_drag(page, "down")
    total += capture.flush(ws, seen, area_label, dry)   # final drain
    return total


def sweep_grid(page, ws, seen, area_label, dry, capture):
    """Sequential GRID (lawnmower) sweep: cover an EXPANDING SQUARE centered on
    where you start, row by row -- left-to-right, drop down, right-to-left, drop
    down -- growing outward ring by ring until you close the browser. This is the
    methodical 'read it like a book' motion (vs the spiral). As the square grows
    it has to re-cross cells it already did; those are now a FAST PASS-THROUGH
    (no 'Search this area', no settle, no re-print) so it never sits on ground
    it just covered -- only NEW cells get the full capture. Returns total."""
    pos = [0, 0]                 # net cell offset from the start cell
    tally = {"total": 0, "cells": 0}
    done = set()                 # cells already captured -> don't redo them

    def capture_here():
        key = (pos[0], pos[1])
        if key in done:
            return               # already scanned -> just passing through, fast
        done.add(key)
        if on_map(page):
            search_this_area(page)
        else:
            print("  (view flipped to portal -- re-opening the map)")
            open_map_view(page)   # else the drags land on the portal and don't pan
        time.sleep(SEARCH_SETTLE)
        n = capture.flush(ws, seen, area_label, dry)
        tally["total"] += n
        tally["cells"] += 1
        print("  [cell %d @ %d,%d] +%d  (total %d)"
              % (tally["cells"], pos[0], pos[1], n, tally["total"]))
        if tally["cells"] == 4 or tally["cells"] % 15 == 0:
            report_status(ws, area_label, "watching", found=tally["total"],
                          note="grid: %d cells, %d leads" % (tally["cells"], tally["total"]))
            dump_backend(ws, capture)   # F12/network snapshot to the sheet

    def _next(direction):
        return (pos[0] + (1 if direction == "right" else -1 if direction == "left" else 0),
                pos[1] + (1 if direction == "down" else -1 if direction == "up" else 0))

    def step(direction):
        # skate fast + silent across cells we've already scanned; full pan onto new ones
        quiet = _next(direction) in done
        if not mouse_drag(page, direction, quiet=quiet):
            return False
        pos[0] += 1 if direction == "right" else -1 if direction == "left" else 0
        pos[1] += 1 if direction == "down" else -1 if direction == "up" else 0
        return True

    def go_to(tx, ty):
        # walk one cell at a time, capturing each landed cell. Drop to the row
        # (y) FIRST, then sweep across (x) -- so each row is swept at its own y
        # (proper lawnmower, full coverage even when a new ring starts).
        while pos[1] != ty:
            if not step("down" if ty > pos[1] else "up"):
                return False
            capture_here()
        while pos[0] != tx:
            if not step("right" if tx > pos[0] else "left"):
                return False
            capture_here()
        return True

    print("Sequential grid sweep -- row by row, expanding outward until you "
          "close the browser.\n")
    try:
        capture_here()                       # the starting cell
        R, rows_down = 1, True
        while True:
            ys = list(range(-R, R + 1)) if rows_down else list(range(R, -R - 1, -1))
            for i, ty in enumerate(ys):
                target_x = R if (i % 2 == 0) else -R   # serpentine: sweep to the far edge
                if not go_to(target_x, ty):
                    return tally["total"]
            R += 1
            rows_down = not rows_down          # flow into the next ring, less backtrack
    except Exception as e:
        msg = str(e).lower()
        if "closed" in msg or "target" in msg:
            print("\nBrowser closed -- stopping the grid sweep. (%d leads this run.)"
                  % tally["total"])
        else:
            print("\nGrid sweep stopped: %s" % str(e)[:100])
        return tally["total"]


class _RestartSpiral(Exception):
    """Internal: boomerang home + restart the spiral (dry ground). Never leaves
    sweep_continuous."""


def sweep_continuous(page, ws, seen, area_label, dry, capture):
    """Keep sweeping OUTWARD in a spiral, capturing each viewport off the
    backend, until the browser is closed -- no fixed grid. Set it on a spot/ZIP
    and it covers that area and keeps expanding past it until the computer (or
    you closing the window) stops it. Returns the total captured."""
    # SINGLE-THREADED on purpose. Playwright's sync API is NOT thread-safe (it runs
    # on a greenlet loop bound to this thread); the old "background flush thread" this
    # session added was destabilizing the browser and freezing the pan mid-run. So
    # everything is sequential here, like the version that ran stable: SEARCH (now and
    # then) -> capture -> PAN, spiralling outward until the browser is closed. The only
    # other thread is the watchdog, which just reads a timestamp (never touches the page).
    dirs = ["right", "down", "left", "up"]
    di, run, cell, total = 0, 1, 0, 0
    dry_flushes = 0      # consecutive flushes with 0 new leads -> DRY AREA alarm
    last_flush = 0.0     # MOTION IS SACRED: sheet writes only every FLUSH_GAP_SECS
    print("Sweep -- SEARCH -> capture -> PAN, spiralling outward. Runs until you\n"
          "  close the browser; auto-restarts itself if it ever hangs.\n"
          "  Motion never waits on the sheet: captures queue in memory and write\n"
          "  in ONE batch every %ds.\n" % FLUSH_GAP_SECS)
    try:
      while True:
        try:
            for _arm in range(2):           # spiral: 2 arms per run-length, then grow
                for _ in range(run):
                    if not on_map(page):
                        open_map_view(page)          # flipped to portal -> flip back
                    elif cell % 3 == 0:
                        search_this_area(page)       # nudge the fetch every few cells
                    # PAN PATH RULE: nothing heavy between pans. Split mode
                    # (default): flush = a local disk append (microseconds), the
                    # uploader process does ALL sheet work. Legacy mode: one
                    # batched 15s-capped write per gap.
                    now = time.time()
                    if now - last_flush >= FLUSH_GAP_SECS:
                        if _SPLIT[0]:
                            n_flush = capture.flush_local(seen, area_label, dry)
                        else:
                            n_flush = capture.flush(ws, seen, area_label, dry)
                        total += n_flush
                        last_flush = now
                        # DRY-AREA ALARM: sweeping empty ground (golf course /
                        # all-grey) looks exactly like a freeze -- say so LOUDLY.
                        # The program is fine; the GROUND is empty. Keeps sweeping
                        # (the spiral grows outward and exits the dead patch).
                        dry_flushes = 0 if n_flush else dry_flushes + 1
                        if dry_flushes and dry_flushes % DRY_WARN_FLUSHES == 0:
                            print("\n  " + "*" * 60)
                            print("  DRY AREA: %d writes in a row with 0 new leads."
                                  % dry_flushes)
                            print("  The hunter is RUNNING FINE -- this ground is empty")
                            print("  (golf course / all-grey / no dots). PAN THE MAP to a")
                            print("  denser neighborhood and it picks up instantly.")
                            print("  " + "*" * 60 + "\n")
                            report_status(ws, area_label, "dry-area", found=total,
                                          note="%d dry writes -- move the map "
                                               "to denser dots" % dry_flushes)
                    # NOTE (Patrick, 2026-07-02): drifting across blank/dead
                    # ground is NORMAL and needs no correcting -- the spiral just
                    # keeps expanding and exits the other side. A "boomerang back
                    # to start" was tried here and REMOVED (it could trap the
                    # sweep circling a dry ring forever -- same reason the old
                    # recenter was removed). Dry ground only prints the banner.
                    cell += 1
                    if cell % 12 == 0:
                        report_status(ws, area_label, "watching", found=total,
                                      note="%d cells, %d leads" % (cell, total))
                    if cell % 60 == 0:
                        if _SPLIT[0]:
                            dump_backend_local(capture)  # disk only; uploader ships it
                        else:
                            dump_backend(ws, capture)
                    _beat()                          # tell the watchdog we're alive
                    if not pan_next(page, dirs[di]):     # PAN; False = browser closed
                        if _SPLIT[0]:
                            capture.flush_local(seen, area_label, dry)
                        else:
                            capture.flush(ws, seen, area_label, dry)
                        return total
                    time.sleep(PAN_INTERVAL)
                di = (di + 1) % 4
            run += 1                            # spiral grows -> larger and larger area
        except _RestartSpiral:
            di, run = 0, 1                      # tight spiral again, from the start
    except Exception as e:
        msg = str(e).lower()
        if "closed" in msg or "target" in msg:
            print("\nBrowser closed -- stopping. (%d leads this run.)" % total)
        else:
            print("\nSweep stopped: %s" % str(e)[:100])
        try:
            if _SPLIT[0]:
                capture.flush_local(seen, area_label, dry)
            else:
                capture.flush(ws, seen, area_label, dry)
        except Exception:
            pass
        return total


def safe_goto(page, url):
    """Navigate to the AT&T map without crashing on net::ERR_ABORTED. The site
    does an immediate client-side redirect (portal/login SPA), which aborts the
    first navigation even though the page goes on to load fine. So: try a couple
    of times, fall back to wait_until='commit', and if it still aborts, just
    proceed -- the page is loading and the rest of the flow (login / open map /
    backend capture) handles whatever state it lands in."""
    last = None
    for attempt, wait in enumerate(("domcontentloaded", "commit", "commit")):
        try:
            page.goto(url, wait_until=wait, timeout=60000)
            return True
        except Exception as e:
            last = e
            msg = str(e).lower()
            if "err_aborted" in msg or "aborted" in msg or "timeout" in msg:
                # redirect/abort is expected here -- give the SPA a moment and retry
                try:
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
                continue
            break
    print("  (navigation note: %s -- continuing; the page is loading.)"
          % str(last)[:80])
    try:                       # make sure we're at least pointed at the site
        if "youachieve" not in (page.url or ""):
            page.wait_for_timeout(1500)
    except Exception:
        pass
    return False


def search_zip(page, zip_code):
    """Type the ZIP into the AT&T map's search box and submit. Tries the
    Mapbox geocoder input, visible text inputs, then the textbox role."""
    selectors = [".mapboxgl-ctrl-geocoder--input",
                 "input[placeholder*='Search' i]",
                 "input[placeholder*='address' i]",
                 "input[type='search']",
                 "input[type='text']",
                 "input"]
    for sel in selectors:
        try:
            box = page.query_selector(sel)
            if box and box.is_visible():
                box.click()
                box.fill("")
                box.type(str(zip_code), delay=40)
                time.sleep(0.6)
                page.keyboard.press("Enter")
                time.sleep(3.5)
                return True
        except Exception:
            continue
    # last resort: any visible textbox by ARIA role
    try:
        tb = page.get_by_role("textbox")
        if tb.count() > 0:
            tb.first.click()
            tb.first.fill(str(zip_code))
            page.keyboard.press("Enter")
            time.sleep(3.5)
            return True
    except Exception:
        pass
    return False


# ----------------------------------------------------------------------------
# scan: drain each viewport fully, THEN pan; snake across grid
# ----------------------------------------------------------------------------
def record_capture(ws, seen, area_label, dry, address, popup_status, ban,
                   dot_status, via, zone_label="WORKING", lat=None, lng=None):
    """Common writer for both the Mapbox fast path and the click path.
    Returns True when a NEW address was recorded. zone_label (FRESH/WORKING/
    MATURE) rides along so business_score weights just-lit zones first;
    lat/lng (when the geo path has them) feed the Places phone enricher."""
    address = address.strip()
    if is_junk_address(address):
        return False                     # UNIT DUMMY/CTR/COIN etc -> never write
    address, _stripped = clean_address(address)
    if not seen.is_new(address):
        return False                     # same building, any drift/unit spelling
    if dot_color(dot_status) == "GREY":
        return False   # GREY = existing fiber customer -> leave out
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    row = [address, popup_status or "", ban or "", "FIBER ELIGIBLE",
           ts, area_label, dot_color(dot_status), zone_label]
    if dry or not ws:
        print("   + [%s/%s/%s] %s | %s | BAN %s" %
              (zone_label, dot_status, via, address,
               popup_status or "-", ban or "-"))
    else:
        try:
            ws.append_row(row)
        except Exception as e:
            print("   write error: %s" % e)
    if not dry:
        append_jsonl({"address": address, "dot_status": dot_status,
                      "zone_label": zone_label, "popup_status": popup_status,
                      "ban": ban, "area": area_label, "ts": ts, "via": via,
                      "lat": lat, "lng": lng})
    return True


def drain_viewport_mapbox(page, ws, seen, area_label, dry, zone_label="WORKING"):
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
        lat, lng = f.get("lat"), f.get("lng")
        if addr:
            if record_capture(ws, seen, area_label, dry, addr, status_txt,
                              None, dot_status, via="mapbox", zone_label=zone_label,
                              lat=lat, lng=lng):
                captured += 1
            continue
        # no address in the feature -> click at the EXACT projected pixel
        info = click_dot(page, int(f["x"]), int(f["y"]))
        if info and info.get("address"):
            dot_status = classify_status(text=info.get("status") or status_txt,
                                         ban=info.get("ban"))
            if record_capture(ws, seen, area_label, dry, info["address"],
                              info.get("status"), info.get("ban"),
                              dot_status, via="mapbox-click", zone_label=zone_label,
                              lat=lat, lng=lng):
                captured += 1
        close_popup(page)
        time.sleep(0.2)
    return captured


def classify_viewport(page):
    """One screenshot -> (green, gold, gray, label, gray_share, dots). The dots
    list is reused by the pixel fallback so we never screenshot twice."""
    dots, gray = find_map_dots(page)
    greens = sum(1 for d in dots if d[2] == "GREEN")
    golds = len(dots) - greens
    label, share = zone_freshness(greens, golds, gray)
    return greens, golds, gray, label, share, dots


def drain_viewport(page, ws, seen, area_label, dry, fresh_only=False):
    """Operator's plan: after search/pan fetches the dots, first try to grab the
    addresses OFF THE SERVER (network capture, no clicking). Only if the address
    data didn't materialize on the wire do we fall back to clicking each
    green/gold dot for its popup address."""
    # 1) backend map-object read -- hidden on this site, returns None (skips)
    n = drain_viewport_backend(page, ws, seen, area_label, dry)
    if n:
        return n

    # 2) NETWORK grab -- the search/pan just fetched fresh dots; did the address
    #    data come over the wire? If so, capture it with NO clicking.
    cap = _NET_CAPTURE[0]
    if cap is not None:
        netn = cap.flush(ws, seen, area_label, dry)
        if netn:
            print("  viewport (network): +%d captured OFF THE SERVER (no clicks)" % netn)
            drive_log("VIEWPORT network captured=%d" % netn)
            return netn
        # didn't decode -> show the candidate data feeds once so we can pin it
        if not _AUTO_PROBED[0]:
            _AUTO_PROBED[0] = True
            print("  (addresses did NOT come over the server this pass -- here are "
                  "the candidate data feeds, then falling back to clicking:)")
            try:
                cap.dump_debug(os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "net_responses.log"))
            except Exception:
                pass

    # 3) Clicking fallback is HELD OFF for now (operator: prove the server grab
    #    first). Server-only until we confirm whether addresses come over the
    #    wire. Clicking stays opt-in via --allow-click.
    if not ALLOW_CLICK:
        return 0
    if not on_map(page):
        return 0
    greens, golds, gray, label, share, dots = classify_viewport(page)
    print("  viewport (click): %d green + %d gold + %d grey -> %s (grey %d%%)"
          % (greens, golds, gray, label, round(share * 100)))
    if fresh_only and label in ("MATURE", "EMPTY"):
        print("  skip [%s] -- not new fiber, moving on" % label)
        return 0
    captured = 0
    clicked_pixels = set()
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
                              dot_status, via="pixel-click", zone_label=label):
                captured += 1
        else:
            misses += 1
        close_popup(page)
        time.sleep(0.2)
    if misses:
        print("  (%d dots never opened a popup after retries)" % misses)
    return captured


def scan(page, ws, area_label, cols, rows, dry, fresh_only=False):
    seen = already_seen(ws)
    print("Resume: %d addresses already captured -> will skip them." % len(seen))
    total = 0
    for r in range(rows):
        for c in range(cols):
            print("[cell r%d c%d]" % (r, c))
            total += drain_viewport(page, ws, seen, area_label, dry, fresh_only)
            if c < cols - 1:
                pan(page, "right" if r % 2 == 0 else "left")          # THEN pan
        if r < rows - 1:
            pan(page, "down")   # next row, reverse dir
    return total


def scan_net(page, ws, area_label, cols, rows, dry, capture):
    """Try the FAST network capture per cell; if the backend isn't serving the
    dots as JSON (it usually isn't -- they're vector tiles), FALL BACK to the
    click/geo capture (drain_viewport) so we still get the addresses."""
    seen = already_seen(ws)
    print("Resume: %d addresses already captured -> will skip them." % len(seen))
    total = 0
    for r in range(rows):
        for c in range(cols):
            search_this_area(page)        # trigger the data load
            time.sleep(SEARCH_SETTLE)
            n = capture.flush(ws, seen, area_label, dry)
            if n == 0:
                # dots aren't JSON on this map -> click/geo the dots instead
                n = drain_viewport(page, ws, seen, area_label, dry, fresh_only=False)
                print("[cell r%d c%d] clicked: +%d" % (r, c, n))
            else:
                print("[cell r%d c%d] network: +%d" % (r, c, n))
            total += n
            if c < cols - 1:
                pan(page, "right" if r % 2 == 0 else "left")
        if r < rows - 1:
            pan(page, "down")
    total += capture.flush(ws, seen, area_label, dry)   # final net drain
    if capture.endpoints:
        print("\nData endpoints seen (URL -> leads):")
        for u, n in sorted(capture.endpoints.items(), key=lambda kv: -kv[1]):
            print("  %4d  %s" % (n, u))
    if capture.debug:
        capture.dump_debug(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "net_responses.log"))
    return total


# ----------------------------------------------------------------------------
# self-update (pull latest code from GitHub on each start)
# ----------------------------------------------------------------------------
def _find_git():
    """Return a usable git command. Plain 'git' if it's on PATH, else the
    standard Windows install locations -- so the raw `python precise_fiber_hunter.py`
    command still auto-updates even in a Command Prompt that never got git on PATH
    (the usual reason a launch keeps running stale code)."""
    import shutil
    g = shutil.which("git")
    if g:
        return g
    for cand in (r"C:\Program Files\Git\cmd\git.exe",
                 r"C:\Program Files (x86)\Git\cmd\git.exe",
                 os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe")):
        if os.path.exists(cand):
            return cand
    return "git"   # last resort -- subprocess will raise, caught upstream


_RAW_BASE = ("https://raw.githubusercontent.com/patricksiado-prog/"
             "Go-High-Level-MCP-2026-Complete/" + REPO_BRANCH + "/optimus")
# the hunter + the sibling modules it imports -- refresh all so a ZIP install
# never runs a stale mix.
_RAW_FILES = ["precise_fiber_hunter.py", "optimus_dot_detect.py",
              "optimus_api_capture.py", "hunter_fixes.py",
              "backend_classifier.py"]


def _raw_refresh(here):
    """For a NON-git (ZIP) install: re-download the code files from GitHub raw so a
    restart runs the latest. Best-effort; a cache-buster query dodges GitHub's raw
    CDN cache. Overwrites in place (Python already read this file into memory, so
    replacing it on disk is safe; self_update re-execs into the new code)."""
    import urllib.request
    d = os.path.dirname(here)
    for i, fn in enumerate(_RAW_FILES):
        try:
            url = _RAW_BASE + "/" + fn + "?_cb=" + str(len(here) + i)
            req = urllib.request.Request(url, headers={"Cache-Control": "no-cache",
                                                       "Pragma": "no-cache"})
            data = urllib.request.urlopen(req, timeout=60).read()
            if data and len(data) > 500:      # sanity: not an error page
                with open(os.path.join(d, fn), "wb") as f:
                    f.write(data)
        except Exception:
            pass


def self_update():
    """On launch, pull the newest code from GitHub so a restart always runs the
    latest version. If THIS file actually changed, relaunch once with the new
    code. Guards: OPTIMUS_NO_UPDATE=1 (set on the relaunch) stops an infinite
    re-exec loop; GIT_TERMINAL_PROMPT=0 stops a hang on a credential prompt;
    any failure (offline, no git) is non-fatal -- we just keep running."""
    import subprocess
    if os.environ.get("OPTIMUS_NO_UPDATE") == "1" or "--no-update" in sys.argv:
        return
    here = os.path.abspath(__file__)
    repo_root = os.path.dirname(os.path.dirname(here))
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    git = _find_git()           # works even when git isn't on this shell's PATH
    is_git = os.path.isdir(os.path.join(repo_root, ".git"))
    try:
        before = open(here, "rb").read()
        if git and is_git:
            # GIT INSTALL: fetch + hard reset to origin so a local edit / conflict /
            # divergence can NEVER leave us stuck on old code.
            subprocess.run([git, "-C", repo_root, "fetch", "origin", REPO_BRANCH],
                           env=env, timeout=90, capture_output=True, text=True)
            subprocess.run([git, "-C", repo_root, "reset", "--hard",
                            "origin/" + REPO_BRANCH],
                           env=env, timeout=60, capture_output=True, text=True)
        else:
            # NON-GIT INSTALL (the ZIP-download layout, e.g. %USERPROFILE%\optimus_hunter):
            # git can't update it, so RE-DOWNLOAD the code from GitHub raw. Without
            # this the ZIP install runs stale FOREVER (the bug that kept old code
            # running -- old "business match" wording, enrichment on, etc.).
            _raw_refresh(here)
        after = open(here, "rb").read()
    except Exception as e:
        print("(auto-update skipped: %s -- run START OPTIMUS.bat to force the "
              "update, or: git pull)" % str(e)[:80])
        return
    if after != before:
        print("Pulled newer code from GitHub -- relaunching once with it...\n")
        child_env = dict(os.environ, OPTIMUS_NO_UPDATE="1")
        try:
            r = subprocess.run([sys.executable] + sys.argv, env=child_env)
            sys.exit(r.returncode)
        except Exception:
            pass   # couldn't relaunch -- fall through and run the old code


# ----------------------------------------------------------------------------
# phone + business enrichment, running alongside the hunt (in-process)
# ----------------------------------------------------------------------------
def _start_enrichment(allow_paid=False):
    """Launch phone/business enrichment in a background daemon thread so leads
    get a name + phone while the scan keeps running. FREE OpenStreetMap first;
    paid Google Places only when allow_paid AND GOOGLE_PLACES_API_KEY is set. It
    tails precise_addresses.jsonl -> enriched_leads.jsonl. Best-effort; a daemon
    thread dies with the program and never blocks or breaks the hunt."""
    def _run():
        try:
            import enrich_phones
        except Exception as e:
            print("(enrichment not started: %s)" % str(e)[:80])
            return
        key = os.environ.get("GOOGLE_PLACES_API_KEY")
        # Use Google Places whenever a key is present (best source for business
        # name + phone, and it can match by ADDRESS even with no lat/lng). No
        # --paid flag needed -- the moment Zack's key is set, it kicks in.
        paid = bool(key) or allow_paid
        try:
            enrich_phones.run(enrich_phones.IN_PATH, enrich_phones.OUT_PATH,
                              dry=False, allow_paid=paid, api_key=key,
                              watch=True, watch_interval=8.0,
                              sheet_id=SHEET_ID, creds_file=find_creds(),
                              gmaps_max=200)   # FREE Maps scrape (capped; off on block)
        except Exception as e:
            print("(enrichment stopped: %s)" % str(e)[:80])
    threading.Thread(target=_run, daemon=True).start()
    mode = "free OSM -> paid Places on misses" if allow_paid else "free OSM ($0)"
    print("Enrichment running in the background (%s) -> enriched_leads.jsonl" % mode)


# ----------------------------------------------------------------------------
# live status -> Drive (a tab in the same Google Sheet) + a local file
# ----------------------------------------------------------------------------
_status_ws = [None]   # cached "Hunter Status" worksheet handle


def _status_sheet(ws):
    """Get/create the 'Hunter Status' tab next to the data tab, so Patrick can
    watch what the hunter is doing live on Drive. Returns None if no sheet."""
    if ws is None:
        return None
    if _status_ws[0] is not None:
        return _status_ws[0]
    try:
        sh = ws.spreadsheet
        try:
            sws = sh.worksheet(STATUS_TAB)
        except Exception:
            sws = sh.add_worksheet(title=STATUS_TAB, rows="2000", cols="6")
            sws.append_row(["Time", "Host", "Area", "State", "Found this pass", "Note"])
        _status_ws[0] = sws
    except Exception:
        _status_ws[0] = None
    return _status_ws[0]


# ----------------------------------------------------------------------------
# Drive telemetry: write what the hunter does to a SHARED Drive text file so
# Claude can read it (the main sheet is AI-blocked). Uses the service-account
# creds (Drive scope) the hunter already has. Best-effort; never breaks a run.
# ----------------------------------------------------------------------------
TELEMETRY_FOLDER = "1IOWTZiDakRuzXtGGYgRCxPxXHNNZkaPc"   # "OPTIMUS SETUP" folder
TELEMETRY_NAME = "OPTIMUS_HUNTER_LOG.txt"
# Patrick-OWNED log file (Claude can read it). The service account can't create
# files in a personal Drive, so we APPEND to this existing file -- which works
# once Patrick shares it (edit) with the service-account email.
TELEMETRY_LOG_ID = "1f9Zody99XIBHiY8wFtjPU18mIKE6ftye"
TELEMETRY_SHOT_ID = "1sPlZ7Zc_lIZl6FcdU5zW3TTQn6TgtCrg"   # Patrick-owned screenshot file
_drive_sess = [None]      # AuthorizedSession or False (tried+failed)
_drive_log_id = [None]


def drive_screenshot(page):
    """Overwrite the shared Drive image file with a current browser screenshot so
    Claude can SEE the screen. Best-effort; needs the file shared (edit) with the
    service account. OFF by default (same Drive-stall reason as drive_log); set
    OPTIMUS_DRIVE_LOG=1 to enable."""
    if os.environ.get("OPTIMUS_DRIVE_LOG") != "1":
        return
    sess = _drive_session()
    if not sess:
        return
    try:
        png = page.screenshot(type="png")
        if not png:
            return
        sess.patch(
            "https://www.googleapis.com/upload/drive/v3/files/%s?uploadType=media"
            % TELEMETRY_SHOT_ID,
            data=png, headers={"Content-Type": "image/png"}, timeout=30)
    except Exception:
        pass


def _drive_session():
    if _drive_sess[0] is not None:
        return _drive_sess[0] or None
    try:
        from google.oauth2.service_account import Credentials
        from google.auth.transport.requests import AuthorizedSession
        p = find_creds()
        if not p:
            _drive_sess[0] = False
            return None
        creds = Credentials.from_service_account_file(
            p, scopes=["https://www.googleapis.com/auth/drive"])
        _drive_sess[0] = AuthorizedSession(creds)
    except Exception:
        _drive_sess[0] = False
    return _drive_sess[0] or None


def _ensure_log_file(sess):
    # Write to the fixed Patrick-owned file (shared with the service account).
    return TELEMETRY_LOG_ID


def drive_log(msg):
    """Append a timestamped line to the shared Drive telemetry file. Best-effort.
    OFF by default: this does a Drive download+reupload with a 20s timeout, and the
    service account usually can't write to a personal-Gmail Drive, so the requests
    HANG to the timeout -- it was stalling the sweep ~20s on every productive cell.
    Status still lands in run_status.json + the 'Hunter Status' sheet tab. Set
    OPTIMUS_DRIVE_LOG=1 to re-enable if you've shared the Drive folder."""
    if os.environ.get("OPTIMUS_DRIVE_LOG") != "1":
        return
    sess = _drive_session()
    if not sess:
        return
    try:
        fid = _ensure_log_file(sess)
        if not fid:
            return
        cur = sess.get("https://www.googleapis.com/drive/v3/files/%s?alt=media" % fid,
                       timeout=20)
        prev = cur.text if cur.ok else ""
        if len(prev) > 200000:
            prev = prev[-150000:]
        line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + str(msg)[:400] + "\n"
        sess.patch(
            "https://www.googleapis.com/upload/drive/v3/files/%s?uploadType=media" % fid,
            data=(prev + line).encode("utf-8"),
            headers={"Content-Type": "text/plain"}, timeout=20)
    except Exception:
        pass


def report_status(ws, area, state, found="", note=""):
    """Write one heartbeat line: always to a local run_status.json, and to the
    Drive sheet's status tab when we have one. Never crashes the run."""
    import socket
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    host = socket.gethostname()
    rec = {"time": stamp, "host": host, "area": str(area),
           "state": state, "found": found, "note": note}
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "run_status.json"), "w") as f:
            json.dump(rec, f)
    except Exception:
        pass
    print("[status] %s  %s  area=%s  %s %s" % (stamp, state, area, found, note))
    drive_log("STATUS %s host=%s area=%s found=%s %s" % (state, host, area, found, note))
    if _SPLIT[0]:
        return   # split mode: the uploader process mirrors run_status.json to
                 # the sheet -- the MOTION process never touches Google.
    sws = _status_sheet(ws)
    if sws is not None:
        try:
            sws.append_row([stamp, host, str(area), state, str(found), str(note)])
        except Exception:
            pass


# ----------------------------------------------------------------------------
# BACKEND F12 MONITOR -> the sheet. So Patrick can just run the hunter and Claude
# can SEE what's happening on the wire (the F12 / DevTools Network view) without a
# screenshot: every endpoint the AT&T map hit (biggest first -- the dot/address
# feed is usually the biggest), the vector-tile field names (the dot data schema),
# and how many addresses parsed off the server + samples. Written to a "Backend
# Capture" tab, overwritten each pass with the latest state. ON by default.
# ----------------------------------------------------------------------------
BACKEND_TAB = "Backend Capture"
_backend_ws = [None]
_BACKEND_ON = [True]
_backend_busy = [False]   # a dump is in flight -> skip, so the sweep never waits


def _backend_sheet(ws):
    """Get/create the 'Backend Capture' tab. Returns the worksheet or None."""
    if ws is None:
        return None
    if _backend_ws[0] is not None:
        return _backend_ws[0]
    try:
        sh = ws.spreadsheet
        try:
            t = sh.worksheet(BACKEND_TAB)
        except Exception:
            t = sh.add_worksheet(title=BACKEND_TAB, rows="400", cols="6")
        _backend_ws[0] = t
    except Exception:
        _backend_ws[0] = None
    return _backend_ws[0]


def dump_backend(ws, cap):
    """Snapshot the network capture (F12 view) to the 'Backend Capture' tab so the
    backend is readable remotely. SYNCHRONOUS now -- NO background thread. Playwright's
    sync API is greenlet-bound and background threads doing I/O alongside it were
    destabilizing the browser; this is a brief, infrequent sheet write on the main
    thread instead. Best-effort; never breaks a run."""
    if cap is None or not _BACKEND_ON[0]:
        return
    t = _backend_sheet(ws)
    if t is None:
        return
    try:
        _dump_backend_write(t, cap)
    except Exception as e:
        print("  (backend monitor skipped: %s)" % str(e)[:60])


def dump_backend_local(cap):
    """SPLIT-MODE backend snapshot: write the F12 rows to a LOCAL json file
    (disk only); the uploader process ships them to the Backend Capture tab."""
    if cap is None or not _BACKEND_ON[0]:
        return
    try:
        with open(BACKEND_LOCAL_PATH, "w") as f:
            json.dump(_backend_rows(cap), f)
    except Exception:
        pass


def _dump_backend_write(t, cap):
    t.clear()
    t.append_rows([[str(c)[:490] for c in r] for r in _backend_rows(cap)],
                  value_input_option="RAW")
    print("  [backend] wrote %d endpoints + %d parsed leads to '%s'"
          % (len(cap.seen_urls), len(cap.pending), BACKEND_TAB))


def _backend_rows(cap):
    import socket
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    host = socket.gethostname()
    rows = [["Time", "Kind", "URL / Field / Address", "Type", "Bytes/Count", "Sample"]]
    rows.append([ts, "SNAPSHOT", host, "", "%d endpoints" % len(cap.seen_urls),
                 "F12/network view of the AT&T map"])
    # every endpoint the page hit, biggest first (the dot/address feed is big)
    for base, (ct, hits, mx) in sorted(cap.seen_urls.items(), key=lambda kv: -kv[1][2])[:25]:
        rows.append([ts, "ENDPOINT", base, ct, "%d B / %d hits" % (mx, hits), ""])
    # vector-tile property names = the dot data schema
    if cap.tile_keys:
        rows.append([ts, "TILE FIELDS", ", ".join(sorted(cap.tile_keys)), "",
                     "%d fields" % len(cap.tile_keys), ""])
    for base, note in list(cap.tile_status.items())[:8]:
        rows.append([ts, "TILE DECODE", base, str(note), "", ""])
    # addresses parsed off the wire + samples (is status/lat/lng present?)
    rows.append([ts, "LEADS PARSED", "", "", "%d total" % len(cap.pending), ""])
    for ld in cap.pending[-6:]:
        rows.append([ts, "SAMPLE LEAD", str(ld.get("address")),
                     "status=%s" % ld.get("status"),
                     "lat=%s lng=%s" % (ld.get("lat"), ld.get("lng")), ""])
    return rows


# ----------------------------------------------------------------------------
# UPLOADER PROCESS (split mode) -- ALL sheet work lives here, in a separate
# process, so the motion process never waits on Google for anything.
# ----------------------------------------------------------------------------
def _ulog(msg):
    line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
    print(line)
    try:
        with open(UPLOADER_LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def uploader_main():
    """Tail precise_addresses.jsonl from the offset the hunter handed us and do
    ALL the sheet work: dedupe vs the sheet, batched Precise Fiber writes (rows
    survive failures via SafePending), live biz matching, Hunter Status
    mirroring, Backend Capture shipping. Exits by itself once the hunter has
    been silent for a long while and everything is shipped."""
    _ulog("uploader up (pid %d) -- all sheet work happens here" % os.getpid())
    ws = None
    delay = 5
    while ws is None:
        try:
            ws = open_sheet()
        except Exception as e:
            _ulog("sheet connect failed: %s -- retrying" % str(e)[:80])
        if ws is None:
            time.sleep(delay)
            delay = min(delay * 2, 120)
    seen = already_seen(ws)
    _ulog("seeded %d known addresses from the sheet" % len(seen))
    try:
        init_bizmatch(ws)
    except Exception as e:
        _ulog("biz match init skipped: %s" % str(e)[:80])
    try:
        offset = int(os.environ.get("OPTIMUS_OUTBOX_OFFSET", "0") or 0)
    except ValueError:
        offset = 0
    outbox = SafePending()
    remainder = b""
    last_status = ""
    last_backend = 0.0
    idle_since = time.time()
    while True:
        # ---- 1. new captures from the hunter ----
        new_records = []
        try:
            size = os.path.getsize(JSONL_PATH) if os.path.exists(JSONL_PATH) else 0
            if size < offset:
                offset = 0          # file rotated/reset
            if size > offset:
                with open(JSONL_PATH, "rb") as f:
                    f.seek(offset)
                    data = f.read()
                offset += len(data)
                data = remainder + data
                lines = data.split(b"\n")
                remainder = lines.pop()          # partial trailing line, if any
                for raw in lines:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        d = json.loads(raw.decode("utf-8", "replace"))
                    except Exception:
                        continue
                    addr = (d.get("address") or "").strip()
                    if not addr or is_junk_address(addr):
                        continue
                    addr, _st = clean_address(addr)
                    if not seen.is_new(addr):
                        continue
                    ds = d.get("dot_status")
                    if dot_color(ds) == "GREY":
                        continue
                    _bidx = _BIZ.get("index") or {}
                    _b = _bidx.get(_norm_addr(addr)) if _bidx else None
                    outbox.add([addr, dot_color(ds), d.get("ts") or "",
                                (_b or {}).get("name", ""), (_b or {}).get("phone", "")])
                    d["address"] = addr
                    new_records.append(d)
        except Exception as e:
            _ulog("outbox read error: %s" % str(e)[:80])
        if new_records or len(outbox):
            idle_since = time.time()

            def _write(batch):
                ws.append_rows(batch, value_input_option="RAW")

            shipped = outbox.flush(_write, batch_size=500)
            if shipped:
                _ulog("shipped %d rows to '%s' (%d queued)"
                      % (shipped, OUT_TAB, len(outbox)))
            elif len(outbox):
                _ulog("write failed -- %d rows stay queued for retry" % len(outbox))
            if new_records:
                try:
                    match_leads_to_biz(new_records)
                except Exception as e:
                    _ulog("biz match error: %s" % str(e)[:80])
        # ---- 2. mirror the hunter's status heartbeats to the sheet ----
        try:
            if os.path.exists(RUN_STATUS_PATH):
                s = open(RUN_STATUS_PATH).read()
                if s and s != last_status:
                    last_status = s
                    rec = json.loads(s)
                    sws = _status_sheet(ws)
                    if sws is not None:
                        sws.append_row([rec.get("time", ""), rec.get("host", ""),
                                        str(rec.get("area", "")), rec.get("state", ""),
                                        str(rec.get("found", "")), str(rec.get("note", ""))])
                    idle_since = time.time()
        except Exception:
            pass
        # ---- 3. ship the backend snapshot when the hunter refreshes it ----
        try:
            if os.path.exists(BACKEND_LOCAL_PATH):
                mt = os.path.getmtime(BACKEND_LOCAL_PATH)
                if mt > last_backend:
                    last_backend = mt
                    rows = json.load(open(BACKEND_LOCAL_PATH))
                    t = _backend_sheet(ws)
                    if t is not None:
                        t.clear()
                        t.append_rows([[str(c)[:490] for c in r] for r in rows],
                                      value_input_option="RAW")
        except Exception:
            pass
        # ---- 4. quit once the hunter has clearly gone away and we're drained --
        if not len(outbox) and time.time() - idle_since > 900:
            _ulog("hunter silent 15 min and everything shipped -- uploader done")
            return
        time.sleep(2)


# ----------------------------------------------------------------------------
# entry
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# COMBO (lives in the hunter): as it captures each address, match it against the
# scraped businesses (the standalone scraper fills the 'Maps Businesses' tab) and
# write the matches -- GREEN dot business -> 'Fiber Green Biz', GOLD/ORANGE dot
# business -> 'Upgrade Orange Biz'. The businesses are already local-only (the
# scraper drops chains), so any match is a callable lead.
# ----------------------------------------------------------------------------
MAPS_TAB = "Maps Businesses"
GREEN_BIZ_TAB = "Fiber Green Biz"
ORANGE_BIZ_TAB = "Upgrade Orange Biz"
BIZ_HEADER = ["Business Name", "Phone", "Address", "Website", "Category"]
# local-CSV fallback when the Google Sheet is full (10M-cell cap) and can't take
# the two result tabs -- matches still get saved, never lost.
GREEN_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fiber_green_biz.csv")
ORANGE_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upgrade_orange_biz.csv")

_BIZ_SUFFIX = {"ST": "ST", "STREET": "ST", "AVE": "AVE", "AV": "AVE",
               "AVENUE": "AVE", "RD": "RD", "ROAD": "RD", "DR": "DR",
               "DRIVE": "DR", "LN": "LN", "LANE": "LN", "BLVD": "BLVD",
               "BOULEVARD": "BLVD", "CT": "CT", "COURT": "CT", "PL": "PL",
               "PLACE": "PL", "WAY": "WAY", "CIR": "CIR", "CIRCLE": "CIR",
               "TER": "TER", "TERRACE": "TER", "TRL": "TRL", "TRAIL": "TRL",
               "PKWY": "PKWY", "PARKWAY": "PKWY", "HWY": "HWY", "HIGHWAY": "HWY"}
_BIZ_UNIT_RE = re.compile(r"\b(APT|APARTMENT|UNIT|STE|SUITE|#|BLDG|BUILDING|FL|"
                          r"FLOOR|RM|ROOM|OFC|OFFICE|TRLR|LOT|SPC)\b.*$", re.I)

# live state: business index + the two output tabs + the Maps Businesses worksheet
_BIZ = {"index": None, "green_ws": None, "orange_ws": None, "maps_ws": None,
        "green_seen": set(), "orange_seen": set()}
_BIZ_RELOAD = [0]   # (unused since BUILD #21 -- the periodic mid-run biz reload
                    # was a huge read ON THE PAN PATH and froze the motion)


def _norm_addr(addr):
    """Address -> 'HOUSE|STREET CORE' match key (drops unit/city/zip, standardizes
    the street suffix) so the captured address lines up with the scraped one."""
    if not addr:
        return ""
    s = addr.upper().strip().split(",")[0]
    s = _BIZ_UNIT_RE.sub("", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"^(\d+)\s+(.*)$", s)
    if not m:
        return ""
    house, rest = m.group(1), m.group(2).split()
    if not rest:
        return ""
    if rest[-1] in _BIZ_SUFFIX:
        rest[-1] = _BIZ_SUFFIX[rest[-1]]
    rest = ["N" if t == "NORTH" else "S" if t == "SOUTH" else "E" if t == "EAST"
            else "W" if t == "WEST" else t for t in rest]
    return "%s|%s" % (house, " ".join(rest))


def _ensure_biz_tab(sh, title):
    """Open the result tab, or create it with a TINY footprint (100x5 = 500 cells,
    grows as rows append) so it fits even on a near-full sheet. Returns None if the
    sheet is genuinely maxed out -- the caller then falls back to a local CSV."""
    try:
        ws = sh.worksheet(title)
        if not ws.get_all_values():
            ws.append_row(BIZ_HEADER)
        return ws
    except Exception:
        pass
    try:
        ws = sh.add_worksheet(title=title, rows="100", cols="5")
        ws.append_row(BIZ_HEADER)
        return ws
    except Exception as e:
        print("  (sheet full -- '%s' matches will go to a local CSV: %s)"
              % (title, str(e)[:50]))
        return None


def _biz_key(row5):
    """The dedup identity of a match row [name, phone, addr, web, cat]: the phone's
    last 10 digits when present (same lead even if the address TEXT varies between
    the hunter's and the scraper's write), else the normalized address, else
    name|address. This is how the real UNIQUE lead count is taken (by phone), so
    keying dedup on it kills the pile-up in the match tabs."""
    row5 = (list(row5) + [""] * 5)[:5]
    digits = re.sub(r"\D", "", row5[1] or "")
    if len(digits) >= 10:
        return "P:" + digits[-10:]
    a = _norm_addr(row5[2])
    if a:
        return "A:" + a
    return "R:" + (str(row5[0]) + "|" + str(row5[2])).strip().upper()


def _biz_seen(ws):
    if ws is None:
        return set()
    try:
        return set(_biz_key(r) for r in ws.get_all_values()[1:]
                   if any((c or "").strip() for c in r[:3]))
    except Exception:
        return set()


def _csv_seen(path):
    s = set()
    try:
        import csv as _csv
        with open(path, newline="") as f:
            for row in _csv.reader(f):
                if row and any((c or "").strip() for c in row[:3]):
                    s.add(_biz_key(row))
    except Exception:
        pass
    return s


def dedupe_biz_tab(ws, title):
    """Remove duplicate rows from ONE match tab in place, keeping the first row per
    unique lead (by _biz_key) plus the header. No-op if it's already unique (so it's
    cheap to call every startup -- one read, no rewrite when clean)."""
    if ws is None:
        return
    try:
        vals = ws.get_all_values()
    except Exception:
        return
    if len(vals) <= 2:
        return
    header = vals[0] if vals[0] else BIZ_HEADER
    body = vals[1:]
    seen, kept = set(), []
    for r in body:
        r = (list(r) + [""] * 5)[:5]
        if not any((c or "").strip() for c in r):
            continue
        k = _biz_key(r)
        if k in seen:
            continue
        seen.add(k)
        kept.append(r)
    if len(kept) == len(body):
        return   # already unique -> don't rewrite (no quota burn, no slowdown)
    try:
        ws.clear()
        ws.append_row(header)
        for i in range(0, len(kept), 500):
            ws.append_rows(kept[i:i + 500], value_input_option="RAW")
        print("  deduped '%s': %d rows -> %d unique (removed %d duplicates)"
              % (title, len(body), len(kept), len(body) - len(kept)))
    except Exception as e:
        print("  (dedupe '%s' skipped: %s)" % (title, str(e)[:50]))


def dedupe_biz_tabs(ws):
    """Dedupe BOTH match tabs. Safe to call every startup -- only rewrites a tab
    that actually has duplicates."""
    if ws is None:
        return
    try:
        sh = ws.spreadsheet
        for title in (GREEN_BIZ_TAB, ORANGE_BIZ_TAB):
            try:
                dedupe_biz_tab(sh.worksheet(title), title)
            except Exception:
                pass
    except Exception:
        pass


def _append_biz_csv(path, rows):
    import csv as _csv
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        if new:
            w.writerow(BIZ_HEADER)
        w.writerows(rows)


def init_bizmatch(ws):
    """Load the scraped businesses ONCE + open the two business tabs, so each
    captured address can be matched live as the hunter sweeps. No-op if there's
    no 'Maps Businesses' tab yet (run the scraper first)."""
    if ws is None or _BIZ["index"] is not None:
        return
    try:
        sh = ws.spreadsheet
        try:
            mb = sh.worksheet(MAPS_TAB)
        except Exception:
            print("  (no '%s' tab yet -- run the scraper to enable the green/gold "
                  "business match.)" % MAPS_TAB)
            _BIZ["index"] = {}
            return
        _BIZ["maps_ws"] = mb          # kept so the index can be RELOADED live
        idx = {}
        for r in mb.get_all_values()[1:]:        # Name,Address,Phone,Website,Category
            r = (list(r) + [""] * 5)[:5]
            key = _norm_addr(r[1])
            if key and key not in idx:
                idx[key] = {"name": r[0], "phone": r[2], "website": r[3], "category": r[4]}
        _BIZ["index"] = idx
    except Exception as e:
        print("  (live business match off: %s)" % str(e)[:80])
        _BIZ["index"] = {}
        return
    # Open the result tabs SEPARATELY -- a failure here (full sheet) must NOT turn
    # matching off; we fall back to a local CSV so matches are still saved.
    _BIZ["green_ws"] = _ensure_biz_tab(sh, GREEN_BIZ_TAB)
    _BIZ["orange_ws"] = _ensure_biz_tab(sh, ORANGE_BIZ_TAB)
    dedupe_biz_tabs(ws)   # clean historical duplicate rows once (no-op if already unique)
    _BIZ["green_seen"] = _biz_seen(_BIZ["green_ws"]) | _csv_seen(GREEN_CSV)
    _BIZ["orange_seen"] = _biz_seen(_BIZ["orange_ws"]) | _csv_seen(ORANGE_CSV)
    dst = ("the '%s' / '%s' tabs" % (GREEN_BIZ_TAB, ORANGE_BIZ_TAB)
           if _BIZ["green_ws"] else "local CSV (sheet is full)")
    print("  COMBO MATCH ON: %d scraped businesses loaded -> fiber+business matches "
          "go to %s, live." % (len(idx), dst))
    # BACKLOG: match every lead captured in prior runs (local jsonl, no quota) so
    # leads grabbed before the scraper ran still get a business name+phone. The
    # seen-sets above (sheet + CSV) keep this from re-writing duplicates.
    _backlog_match()


def reload_biz_index():
    """Re-read the 'Maps Businesses' tab into the in-memory index so businesses the
    scraper adds DURING a hunt get matched live (the old code loaded once at start,
    which is why a concurrent scrape's businesses were missed). Returns True if the
    business count GREW, so the caller can retroactively match earlier leads."""
    mb = _BIZ.get("maps_ws")
    if mb is None:
        return False
    try:
        before = len(_BIZ.get("index") or {})
        idx = {}
        for r in mb.get_all_values()[1:]:
            r = (list(r) + [""] * 5)[:5]
            key = _norm_addr(r[1])
            if key and key not in idx:
                idx[key] = {"name": r[0], "phone": r[2], "website": r[3], "category": r[4]}
        if idx:
            _BIZ["index"] = idx
            return len(idx) > before
    except Exception:
        pass
    return False


def _backlog_match():
    """One-time pass: read previously captured addresses from precise_addresses.jsonl
    and match them against the loaded businesses. Cheap -- a local file read plus
    dict lookups, written with match_leads_to_biz's batched appends."""
    if not _BIZ.get("index") or not os.path.exists(JSONL_PATH):
        return
    recs = []
    try:
        with open(JSONL_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("address"):
                    recs.append({"address": d.get("address"),
                                 "dot_status": d.get("dot_status")})
    except Exception as e:
        print("  (backlog match skipped: %s)" % str(e)[:60])
        return
    if recs:
        print("  business match: scanning %d prior captures for business hits..." % len(recs))
        match_leads_to_biz(recs)


def match_leads_to_biz(new_records):
    """Called from flush with the just-captured leads ({address, dot_status}).
    Any whose address matches a scraped business is written to the green/gold
    business tab by dot color -- live, while the hunt runs."""
    idx = _BIZ["index"]
    if not idx:
        return
    g_rows, o_rows = [], []
    for ld in new_records:
        key = _norm_addr(ld.get("address"))
        b = idx.get(key) if key else None
        if not b:
            continue
        addr = ld.get("address") or ""
        row = [b.get("name") or "", b.get("phone") or "", addr,
               b.get("website") or "", b.get("category") or ""]
        k = _biz_key(row)   # dedup by phone (else address) so the tab can't pile up
        if (ld.get("dot_status") or "").lower() == "copper_upgrade":
            if k in _BIZ["orange_seen"]:
                continue
            _BIZ["orange_seen"].add(k)
            o_rows.append(row)
        else:
            if k in _BIZ["green_seen"]:
                continue
            _BIZ["green_seen"].add(k)
            g_rows.append(row)
    try:
        if g_rows:
            if _BIZ["green_ws"]:
                _BIZ["green_ws"].append_rows(g_rows, value_input_option="RAW")
            else:
                _append_biz_csv(GREEN_CSV, g_rows)
        if o_rows:
            if _BIZ["orange_ws"]:
                _BIZ["orange_ws"].append_rows(o_rows, value_input_option="RAW")
            else:
                _append_biz_csv(ORANGE_CSV, o_rows)
        if g_rows or o_rows:
            where = "sheet" if _BIZ["green_ws"] else "CSV"
            total = len(_BIZ["green_seen"]) + len(_BIZ["orange_seen"])
            print("    MATCH  +%d green (fiber lead + business), +%d orange (upgrade + business)"
                  "  [total matches: %d -> %s]"
                  % (len(g_rows), len(o_rows), total, where))
    except Exception as e:
        print("    (biz write hiccup: %s)" % str(e)[:60])


def _clear_profile_lock():
    """Remove the Chromium single-instance lock files so a relaunch after a crash
    or a watchdog restart doesn't fail with 'profile appears to be in use'. Safe --
    Chromium recreates them on launch."""
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            p = os.path.join(PROFILE_DIR, name)
            if os.path.islink(p) or os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def _beat():
    """Mark progress -- the watchdog resets its clock on each of these."""
    _last_beat[0] = time.time()


def _start_watchdog():
    """If the sweep makes NO progress for STALL_SECS (browser hang / stuck), the
    hunter is frozen -> hard-exit with RESTART_CODE so the launcher loop relaunches
    it fresh (cleared profile lock, new browser). Runs in a daemon thread, so it can
    force the exit even when the MAIN thread is blocked on a hung browser call."""
    _beat()
    def _run():
        while True:
            time.sleep(8)
            if _last_beat[0] and (time.time() - _last_beat[0]) > STALL_SECS:
                print("\n[watchdog] no progress for %ds -- looks frozen. "
                      "Restarting fresh...\n" % STALL_SECS)
                try:
                    report_status(None, "watchdog", "restart", note="stalled -> auto-restart")
                except Exception:
                    pass
                os._exit(RESTART_CODE)
    threading.Thread(target=_run, daemon=True).start()


def main():
    self_update()
    ap = argparse.ArgumentParser()
    ap.add_argument("--uploader", action="store_true",
                    help=argparse.SUPPRESS)   # internal: the sheet-work process
    ap.add_argument("--no-split", action="store_true",
                    help="run sheet writes in-process (old behavior) instead of "
                         "the separate uploader process")
    ap.add_argument("--login", action="store_true", help="open browser to log in once, then quit")
    ap.add_argument("--zip", default=None, help="ZIP/area to search before scanning")
    ap.add_argument("--cols", type=int, default=3)   # grid so it ALWAYS sweeps
    ap.add_argument("--rows", type=int, default=3)   # (drag pan), even run direct
    ap.add_argument("--zoom-in", type=int, default=0, help="press zoom-IN this many times after load")
    ap.add_argument("--zoom-out", type=int, default=0, help="press zoom-OUT this many times after load")
    ap.add_argument("--fresh", action="store_true",
                    help="NEW-FIBER MODE: only capture FRESH/WORKING zones "
                         "(lots of green+gold, little/no grey); skip MATURE fast")
    ap.add_argument("--survey-out", type=int, default=0,
                    help="with --fresh: zoom OUT this many times first so each "
                         "viewport sweeps more ground hunting just-lit clusters")
    ap.add_argument("--net", action="store_true",
                    help="FAST PATH: capture addresses from AT&T's backend JSON "
                         "response (no dot-clicking). Prints the data endpoint(s) "
                         "it found so you can pin them with --api-substring.")
    ap.add_argument("--api-substring", default=None,
                    help="with --net: only parse responses whose URL contains "
                         "this (restrict to the real dot endpoint once known)")
    ap.add_argument("--net-debug", action="store_true",
                    help="RESEARCH: log EVERY network response (url, type, size) "
                         "so we can find which endpoint carries the dot data. "
                         "Prints the biggest endpoints + writes net_responses.log.")
    ap.add_argument("--grid", action="store_true",
                    help="pan in a sequential GRID (lawnmower, row by row) instead of "
                         "the default outward SPIRAL. Spiral is best for covering a "
                         "larger and larger area; grid is for one bounded patch. Both "
                         "run until you close the browser.")
    ap.add_argument("--dry", action="store_true", help="don't write to the sheet, just print")
    ap.add_argument("--auto", action="store_true",
                    help="UNATTENDED: no 'press Enter' pauses, auto-close at the end. "
                         "For the self-restarting launcher / scheduled runs.")
    ap.add_argument("--loop", type=int, default=0, metavar="SECS",
                    help="re-scan every SECS in the SAME browser session (stays on "
                         "the map, no reload/portal flip). 0 = one pass then done.")
    ap.add_argument("--no-update", action="store_true",
                    help="skip the GitHub auto-pull on start (run exactly this code)")
    ap.add_argument("--fast", action="store_true",
                    help="(default now) tight pacing for quick scanning")
    ap.add_argument("--slow", action="store_true",
                    help="restore the relaxed wait times -- use only if leads come "
                         "back 0 because dots aren't loading in time on a slow link")
    ap.add_argument("--clean-sheet", action="store_true",
                    help="free space in the production sheet: delete junk tabs, trim "
                         "the status log, shrink tabs to their data. Keeps all leads/"
                         "businesses. Run this when the sheet is full, then exits.")
    ap.add_argument("--probe", action="store_true",
                    help="DIAGNOSTIC: after you position the map and press Enter, "
                         "dump what the Mapbox map exposes (layers + dot feature "
                         "properties) to probe.json so the backend read can be wired.")
    ap.add_argument("--allow-click", action="store_true",
                    help="re-enable the old pixel-click dot capture (off by "
                         "default because the clicks can flip the view to the portal)")
    ap.add_argument("--no-enrich", action="store_true",
                    help="(kept for compatibility; enrichment is OFF by default now)")
    ap.add_argument("--enrich", action="store_true",
                    help="run phone/business enrichment in the background during the "
                         "hunt. OFF by default now -- it writes to the sheet too, so it "
                         "competes for the write quota and can stall the sweep, and most "
                         "captures are houses with no free phone anyway (business phones "
                         "already come from the scraper match). Run it as its own pass "
                         "instead, or pass --enrich to re-enable it inline.")
    ap.add_argument("--no-match", action="store_true",
                    help="don't cross-reference captured leads to the scraped "
                         "businesses live (skip the Fiber Green Biz / Upgrade "
                         "Orange Biz tabs)")
    ap.add_argument("--paid", action="store_true",
                    help="let the background enricher use paid Google Places on "
                         "OSM misses (needs GOOGLE_PLACES_API_KEY). Default is FREE.")
    ap.add_argument("--no-backend", action="store_true",
                    help="turn off the backend F12/network monitor (the periodic "
                         "'Backend Capture' sheet snapshot of what the map hits on "
                         "the wire). It's ON by default so the backend is visible.")
    ap.add_argument("--dedupe-biz", action="store_true",
                    help="remove duplicate rows from the Fiber Green Biz / Upgrade "
                         "Orange Biz tabs (keep one row per unique lead, by phone), "
                         "then exit. The hunter also auto-dedupes these on startup.")
    args = ap.parse_args()

    if args.uploader:
        uploader_main()          # sheet-work process: no browser, no Playwright
        return

    # print the build stamp FIRST so you can see, immediately, which code is running
    print("\n" + "#" * 60)
    print("#  OPTIMUS FIBER HUNTER   %s" % HUNTER_BUILD)
    print("#" * 60 + "\n")

    _BACKEND_ON[0] = not args.no_backend

    if args.dedupe_biz:
        ws = open_sheet()
        if ws is None:
            print("No sheet available -- nothing to dedupe.")
        else:
            print("Deduping the business-match tabs...")
            dedupe_biz_tabs(ws)
            print("Done.")
        return

    if args.clean_sheet:
        clean_sheet()
        return

    if args.allow_click:
        global ALLOW_CLICK
        ALLOW_CLICK = True

    global WAIT_AFTER_PAN, WAIT_AFTER_ZOOM, SEARCH_SETTLE, SEARCH_CLICK_WAIT
    global POPUP_POLL_TIMEOUT
    if args.slow:               # relaxed pacing -- only if fast misses dots
        WAIT_AFTER_PAN = 0.9
        WAIT_AFTER_ZOOM = 0.9
        SEARCH_SETTLE = 0.8
        print("SLOW mode: relaxed pacing (more time for dots to load).")
    else:                       # FAST is the default now -- speed is the priority
        WAIT_AFTER_PAN = 0.2
        WAIT_AFTER_ZOOM = 0.45
        SEARCH_SETTLE = 0.3
        SEARCH_CLICK_WAIT = 0.5
        POPUP_POLL_TIMEOUT = 1.3
        print("FAST pacing (default). Use --slow if leads come back 0.")

    os.makedirs(PROFILE_DIR, exist_ok=True)
    _clear_profile_lock()   # so a relaunch after a freeze/crash can open the profile

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False,
            viewport=VIEWPORT,
            device_scale_factor=1,   # screenshot px == click px (HiDPI fix)
            args=["--start-maximized",
                  # kill the "Chromium didn't shut down / Restore pages" bubble that
                  # kept covering the map after a restart (it blocked the sweep).
                  "--disable-session-crashed-bubble",
                  "--hide-crash-restore-bubble",
                  "--no-first-run",
                  "--no-default-browser-check",
                  "--disable-features=InfiniteSessionRestore",
                  # stability on weak laptops (the map + long runs were hanging Chromium):
                  "--disable-dev-shm-usage",
                  "--disable-background-timer-throttling",
                  "--disable-backgrounding-occluded-windows",
                  "--disable-renderer-backgrounding",
                  "--disable-ipc-flooding-protection"],
        )
        ctx.add_init_script(MAPBOX_HOOK_JS)   # hook the map before it loads
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # ALWAYS capture network responses now -- the map object is hidden on
        # this site, so the dots have to be read off the wire. debug=True records
        # every endpoint to net_responses.log so the dot-data URL can be found.
        capture = NetCapture(substr=args.api_substring, debug=True)
        page.on("response", capture.handle)   # grab dot data off the wire
        _NET_CAPTURE[0] = capture

        safe_goto(page, MAP_URL)

        if args.login:
            print("\nLOG IN in the browser, open the Fiber Map, then come back here.")
            input("Press Enter when you're logged in and the map is showing... ")
            print("Session saved to %s. You can now run without --login." % PROFILE_DIR)
            ctx.close()
            return

        ws = None if args.dry else open_sheet()
        searched = [False]   # only search the ZIP on the first pass
        seen = already_seen(ws)            # resume set, persists across passes
        area_label = args.zip or "manual"

        # COMBO: load the scraped businesses FIRST so flush() and the backfill can
        # merge the business name+phone inline as each lead is written.
        if not args.dry and not args.no_match:
            init_bizmatch(ws)

        # Recover any locally-saved leads that never reached the sheet (e.g. the
        # old sheet was full) -- write them into the active sheet now (with biz merge).
        if not args.dry and ws is not None:
            backfill_jsonl(ws, seen)

        # SPLIT MODE (default): spawn the UPLOADER process. From here on the
        # motion process does ZERO sheet work -- captures append to disk and the
        # uploader ships them. "Backend memory processing separate from motion."
        if not args.dry and ws is not None and not args.no_split:
            try:
                import subprocess as _sp
                _env = dict(os.environ)
                _env["OPTIMUS_NO_UPDATE"] = "1"
                _here = os.path.dirname(os.path.abspath(__file__))
                _env["OPTIMUS_OUTBOX_OFFSET"] = str(
                    os.path.getsize(JSONL_PATH) if os.path.exists(JSONL_PATH) else 0)
                _flags = 0
                if os.name == "nt":
                    _flags = 0x00000008 | 0x08000000   # DETACHED | NO_WINDOW
                _logf = open(UPLOADER_LOG, "a")
                _kw = {"cwd": _here, "env": _env, "stdout": _logf,
                       "stderr": _logf, "stdin": _sp.DEVNULL}
                if os.name == "nt":
                    _kw["creationflags"] = _flags
                else:
                    _kw["start_new_session"] = True
                _sp.Popen([sys.executable, os.path.abspath(__file__),
                           "--uploader"], **_kw)
                _SPLIT[0] = True
                print("  MOTION <-> SHEET SPLIT ON: uploader process handles all "
                      "sheet work (log: uploader_log.txt).\n"
                      "  The motion process never waits on Google -- ever.")
            except Exception as e:
                print("  (uploader spawn failed: %s -- using in-process writes)"
                      % str(e)[:80])

        if args.net_debug:
            # RESEARCH short-circuit: load the map, trigger a few data loads by
            # searching/panning, then dump the endpoint log. No scanning/clicking.
            if open_map_view(page):
                print("Opened the Fiber Availability Map view.")
            focus_map(page)
            if args.zip:
                print("Searching area: %s" % args.zip)
                search_zip(page, args.zip)
                focus_map(page)
            for _ in range(4):
                search_this_area(page)
                time.sleep(1.5)
                try:
                    pan(page, "right")
                except Exception:
                    pass
            capture.dump_debug(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "net_responses.log"))
            if not args.auto:
                input("\nPress Enter to close the browser... ")
            ctx.close()
            return

        if args.probe:
            print("\n  Get the AT&T Fiber Map showing dots, then come back here.")
            try:
                input("  Press Enter to PROBE what the map exposes... ")
            except EOFError:
                pass
            run_frame_probe(page)
            if not args.auto:
                input("\nPress Enter to close the browser... ")
            ctx.close()
            return

        # Phone + business enrichment runs IN-PROCESS alongside the hunt (free
        # OSM first; paid Places only with --paid + a key). It tails
        # precise_addresses.jsonl, so every address the hunter writes gets a
        # name/phone attached while the scan keeps going. Daemon = dies with us.
        if args.enrich and not args.no_enrich and not args.dry:
            _start_enrichment(args.paid)

        def one_pass():
            # MANUAL mode: you already positioned + zoomed the map (which made
            # AT&T fetch the serviceability dots). READ what's captured off the
            # wire, then DRAG cell-to-cell (proven fiber_hunter motion) across a
            # cols x rows grid to keep going -- no clicking, no reload/flip.
            if not args.auto:
                drive_screenshot(page)   # so Claude can see the screen
                cap = _NET_CAPTURE[0]
                if cap is None:
                    n = 0
                else:                    # CONTINUOUS: grid (default) or spiral, until stopped
                    _sweep = sweep_grid if args.grid else sweep_continuous
                    n = _sweep(page, ws, seen, area_label, args.dry, cap)
                if n:
                    print("  captured %d addresses OFF THE SERVER "
                          "(backend read, no dot-clicking)" % n)
                    drive_log("MANUAL captured=%d" % n)
                else:
                    print("  no serviceability addresses decoded for this view yet.")
                    drive_log("MANUAL captured=0")
                    if cap is not None and not _AUTO_PROBED[0]:
                        _AUTO_PROBED[0] = True
                        try:
                            cap.dump_debug(os.path.join(
                                os.path.dirname(os.path.abspath(__file__)),
                                "net_responses.log"))
                        except Exception:
                            pass
                return n
            # ----- AUTO mode: navigate + scan -----
            # Only touch the map if the SPA bounced us to the PORTAL. When the
            # map is already showing we DON'T click it -- arbitrary map clicks /
            # auto-pans were landing on nav and flipping the view to the portal.
            if not on_map(page):
                if open_map_view(page):
                    print("Re-opened the map view.")
                    time.sleep(2.0)
            if args.zip and not searched[0]:
                print("Searching area: %s" % args.zip)
                if not search_zip(page, args.zip):
                    if args.auto:
                        print("Couldn't find the search box -- scanning the current view.")
                    else:
                        print("Couldn't find the search box -- pan to your area by hand.")
                if args.zoom_in:
                    zoom(page, args.zoom_in, "in")
                if args.zoom_out:
                    zoom(page, args.zoom_out, "out")
                if args.fresh and args.survey_out:
                    zoom(page, args.survey_out, "out")
                searched[0] = True
            # ----- backend read path (default; no dot-clicking) -----
            # "Search this area" is a map-scoped button (safe) that loads the
            # current view's dots; then scan() reads them from the backend and
            # pans cell-to-cell PROGRAMMATICALLY (no clicks -> no portal flip).
            if on_map(page):
                search_this_area(page)
            cap = _NET_CAPTURE[0]
            print("Continuous sweep of %s (backend read)...\n" % (args.zip or "this area"))
            if cap is None:
                return 0
            _start_watchdog()   # arm the freeze-detector now that scanning starts
            _sweep = sweep_grid if args.grid else sweep_continuous
            return _sweep(page, ws, seen, args.zip or "manual", args.dry, cap)

        # After a WATCHDOG restart we must NOT sit waiting for Enter (that would
        # defeat the auto-restart). The launcher sets OPTIMUS_AUTORESUME=1 on a
        # relaunch so the hunter resumes scanning on its own.
        _auto_resume = os.environ.get("OPTIMUS_AUTORESUME") == "1"
        if not args.auto and not _auto_resume:
            # MANUAL mode: let the user get the map where they want it, then
            # scan THAT view (don't auto-jump to a ZIP). They press Enter to go.
            searched[0] = True
            print("\n  " + "=" * 56)
            print("  Get the AT&T Fiber Map showing the area you want to scan.")
            print("  (Log in if needed; pan/zoom to your spot.)")
            print("  Then come back here and press Enter to START scanning.")
            print("  " + "=" * 56)
            try:
                input("  Press Enter to start... ")
            except EOFError:
                pass
        elif _auto_resume:
            searched[0] = True
            print("\n  (auto-resumed after a restart -- scanning the current view)\n")

        # Manual mode keeps watching by default: you pan the map by hand and it
        # collects the backend dots from each view, every few seconds, until you
        # close the browser. (auto mode honors --loop.)
        # the continuous sweep loops internally until you close the browser, so
        # the outer loop is a single pass unless you explicitly pass --loop.
        loop_secs = args.loop if (args.loop and args.loop > 0) else 0
        # build tag rides in the started row so the SHEET proves which version ran
        report_status(ws, args.zip or "manual", "started",
                      note="%s -- %s" % (HUNTER_BUILD,
                                         ("watching every %ss" % loop_secs)
                                         if loop_secs else "single pass"))
        if loop_secs and not args.auto:
            print("\n  WATCHING: pan the map by hand to new areas -- it grabs each "
                  "one off the server every %ds. Close the browser to stop.\n" % loop_secs)
        passno = 0
        while True:
            passno += 1
            try:
                n = one_pass()
            except Exception as e:
                msg = str(e)
                report_status(ws, args.zip or "manual", "error", note=msg[:120])
                closed = "closed" in msg.lower() or "target" in msg.lower()
                try:
                    closed = closed or page.is_closed()
                except Exception:
                    pass
                if closed:
                    print("\nBrowser closed -- stopping. (Run it again to restart.)")
                    break
                print("\nHit a snag: %s" % msg[:120])
                if loop_secs > 0:
                    print("  staying open, retrying next pass...\n")
                    time.sleep(loop_secs)
                    continue
                break
            if loop_secs > 0:
                report_status(ws, args.zip or "manual", "watching",
                              found=n, note="pass %d; +%d this pass" % (passno, n))
                time.sleep(loop_secs)
                continue
            # NEVER STOPS ON ITS OWN: if the browser is still open, whatever made
            # the sweep return was transient (blank view, hiccup, false 'closed')
            # -- start a NEW sweep instead of ending. Closing the browser is the
            # only off switch.
            _alive = False
            try:
                _alive = not page.is_closed()
            except Exception:
                _alive = False
            if _alive and not args.auto:
                print("\n(the browser is still open -- the sweep never ends on its"
                      " own; starting a new sweep)")
                report_status(ws, args.zip or "manual", "watching", found=n,
                              note="pass %d ended with the browser open -- "
                                   "auto-resuming" % passno)
                time.sleep(2)
                continue
            print("\nDONE. Captured %d new fiber-eligible addresses." % n)
            print(("They're in the '%s' tab." % OUT_TAB) if ws else "(dry run, nothing written)")
            report_status(ws, args.zip or "manual", "done", found=n,
                          note="pass %d; single run complete" % passno)
            break
        if not args.auto:
            try:
                input("Press Enter to close the browser... ")
            except EOFError:
                pass
        ctx.close()


if __name__ == "__main__":
    main()
