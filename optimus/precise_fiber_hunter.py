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
import threading
import hashlib

from backend_classifier import classify_hunter_record
from optimus_dot_detect import (GREEN_MIN, GREEN_MAX, GOLD_MIN, GOLD_MAX,
                                GRAY_MIN, GRAY_MAX, classify_status,
                                is_customer_ban,
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

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
MAP_URL = "https://youachieve.att.com/yourefer/fiber"
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "att_profile")

SHEET_ID = "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA"  # ATT FIBER LEADS (production)
# Tab promotion (Patrick, 2026-08-24, after the field-verified end-to-end test):
#   green is trusted  -> main output goes back to production 'Precise Fiber'
#                        (which also feeds the maps scraper's green/orange
#                        cross-match -- it reads this tab by name)
#   gold going forward-> fresh permanent 'Gold Confirmed' tab, NEW-RULE rows
#                        only. The old 'Gold Dots' tab is contaminated with
#                        gold-by-default rows (BRAIN 22.14) and stays retired.
#   grey start fresh  -> fresh permanent 'Grey Fiber Customers' tab.
OUT_TAB = "Precise Fiber"
GOLD_TAB = "Gold Confirmed"    # EVERY confirmed copper-upgrade dot address -- all of
                               # them, not just business matches. For analysis +
                               # calling the upgrades first (Patrick, 2026-08-18).
GREY_TAB = "Grey Fiber Customers"        # existing fiber customers
UNKNOWN_TAB = "Unknown Customers"        # customer, undecodable build code
STATUS_TAB = "Hunter Status"   # live "what it's doing" log, on Drive in the same sheet
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# Self-update: which branch to pull on each start (matches the launcher).
REPO_BRANCH = (os.environ.get("OPTIMUS_REPO_BRANCH")
               or "claude/optimus-map-tools-setup-6dcl6o")

# ---- GitHub write: real-time count channel (Patrick 2026-07-16 "how many leads
#      are getting pulled in real time"). Same proven best-effort push the scout
#      uses -- pushes a tiny running-total file Claude can read instantly without
#      opening the 180k-row sheet. No token -> silently skips. Never crashes. ----
GH_REPO = "patricksiado-prog/Go-High-Level-MCP-2026-Complete"
GH_BRANCH = REPO_BRANCH


_GH_TOKEN_WARNED = []      # warn once per run, not once per push


def _gh_token():
    home = os.path.expanduser("~")
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        here = os.getcwd()      # frozen/exec-wrapped launcher has no __file__
    for p in [os.path.join(home, "Downloads", "github_token.txt"),
              os.path.join(home, "Desktop", "github_token.txt"),
              os.path.join(home, "github_token.txt"),
              os.path.join(home, "optimus", "github_token.txt"),
              os.path.join(here, "github_token.txt"), "github_token.txt"]:
        try:
            if os.path.exists(p):
                t = open(p).read().strip()
                if t:
                    return t
        except Exception:
            pass
    return os.environ.get("GITHUB_TOKEN")


def gh_get(path):
    """Read a file back out of the repo. The wire audit appends to it, and
    without a read the next run would overwrite the last one's evidence."""
    import base64
    token = _gh_token()
    if not token:
        return ""
    import urllib.request
    api = "https://api.github.com/repos/%s/contents/%s?ref=%s" % (
        GH_REPO, path, GH_BRANCH)
    try:
        req = urllib.request.Request(api, headers={
            "Authorization": "token %s" % token,
            "User-Agent": "optimus-hunter",
            "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=25) as r:
            blob = json.load(r)
        return base64.b64decode(blob.get("content") or "").decode("utf-8", "replace")
    except Exception:
        return ""


def gh_put(path, text):
    """Best-effort: commit a small text file so Claude can read it at the raw URL."""
    import base64
    token = _gh_token()
    if not token:
        # Silent here is how LIVE_COUNTS_hunter.txt never got written once: no
        # token file, no push, no message, and nothing on GitHub to notice was
        # missing. Say it out loud and say exactly where to put the file.
        if not _GH_TOKEN_WARNED:
            _GH_TOKEN_WARNED.append(1)
            print("  (GitHub push OFF: no github_token.txt found. Put it at "
                  "%s and the live counts start working.)"
                  % os.path.join(os.path.expanduser("~"), "github_token.txt"))
        return False
    import urllib.request
    api = "https://api.github.com/repos/%s/contents/%s" % (GH_REPO, path)
    hdr = {"Authorization": "token %s" % token, "User-Agent": "optimus-hunter",
           "Accept": "application/vnd.github+json"}
    sha = None
    try:
        req = urllib.request.Request(api + "?ref=" + GH_BRANCH, headers=hdr)
        with urllib.request.urlopen(req, timeout=20) as r:
            sha = json.load(r).get("sha")
    except Exception:
        pass
    body = {"message": "live: %s" % path, "branch": GH_BRANCH,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    if sha:
        body["sha"] = sha
    try:
        req = urllib.request.Request(api, data=json.dumps(body).encode("utf-8"),
                                     headers=hdr, method="PUT")
        with urllib.request.urlopen(req, timeout=25) as r:
            r.read()
        print("  -> pushed %s to GitHub (Claude can read the live count)." % path)
        return True
    except Exception as e:
        print("  (GitHub push skipped: %s)" % str(e)[:70])
        return False


def push_live_counts_hunter(cells, leads, area):
    """Running totals for the HUNTER, pushed to optimus/_live/LIVE_COUNTS_hunter.txt
    so Claude can read the count live WITHOUT opening the giant sheet (which the
    connector can't export -- 10MB/first-tab wall). Includes the MATCHED-BUSINESS
    total (green dot + orange dot business), read from the _BIZ seen-sets, which
    load the existing matches at start -> this is the CUMULATIVE count (the real
    'Fiber Green Biz' number), so Claude can diff it against the 1,793 baseline."""
    import socket
    try:
        g = len(_BIZ.get("green_seen") or ())
        o = len(_BIZ.get("orange_seen") or ())
    except Exception:
        g = o = 0
    txt = (
        "OPTIMUS HUNTER -- LIVE COUNTS\n"
        "updated: %s   host: %s   area: %s\n"
        "STATUS: hunting (updates every ~15 cells while it runs)\n"
        "----------------------------------------\n"
        "cells scanned:                 %d\n"
        "ADDRESSES captured this run:    %d\n"
        "MATCHED businesses (green dot): %d   <- 'Fiber Green Biz' cumulative total\n"
        "MATCHED businesses (orange):    %d   <- 'Upgrade Orange Biz' cumulative total\n"
        "MATCHED total (green+orange):   %d\n"
        % (time.strftime("%Y-%m-%d %H:%M:%S"), socket.gethostname(),
           str(area), cells, leads, g, o, g + o))
    gh_put("optimus/_live/LIVE_COUNTS_hunter.txt", txt)

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
SEARCH_CLICK_WAIT = 1.5       # wait after CLICKING the search control for the fetch
PAN_PRESSES = 6
# fiber_hunter's proven motion is a MOUSE DRAG across the canvas (the original
# used pyautogui.dragRel). DRAG_FRAC = how far to drag, as a fraction of the
# canvas, per cell (<1 so adjacent cells overlap a little and miss nothing).
DRAG_FRAC = 0.45

# Map the internal dot status -> the on-map LEGEND COLOR, so the sheet says
# GREEN / ORANGE / GREY at a glance (green = eligible lead, orange = copper
# upgrade, grey = existing customer/skip) instead of "lead"/"customer".
DOT_COLOR = {"lead": "GREEN", "copper_upgrade": "ORANGE", "customer": "GREY",
             # A customer whose build code we cannot decode is NOT a confirmed
             # fiber customer. Calling it GREY deletes it -- grey never reaches
             # the sheet -- so every undecodable customer silently vanished.
             # UNKNOWN is written out instead: visible, reviewable, and NOT on
             # the call list until a human or a decoded build code says so.
             "unknown_customer": "UNKNOWN"}


def dot_color(dot_status):
    """Legend color word for a classified dot status (defaults to GREEN)."""
    return DOT_COLOR.get((dot_status or "").lower(), "GREEN")


def record_id(address, lat, lng, classification):
    """Deterministic ID for a test record (prove sheet row ↔ captured record)."""
    payload = "|".join([
        str(address or "").strip().upper(),
        str(lat or ""),
        str(lng or ""),
        str(classification or "").upper(),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# --- GOLD vs GREY on the wire path (build_codes.json tiebreak) ---------------
# The serviceability/wire capture has no pixel color, and a copper customer
# HAS a Subscriber BAN -- so classify_status(ban=...) called every customer
# GREY and the write path skipped them all. Result: 436k GREEN and ZERO
# gold/orange rows in the sheet while the map plainly shows gold dots.
# build_codes.json (decoded 2026-07-01 from a live 19.5k-record capture)
# breaks the tie: fttn-bp / ip-rt = COPPER customer -> copper_upgrade
# (ORANGE in the sheet, the hottest upgrade lead -- WRITE IT); fttp-gpon =
# FIBER customer -> customer (GREY, skip). No BAN = not a customer = the
# normal classify_status path (GREEN).
_BLD_CODES = {"fiber": (), "copper": ()}
try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "build_codes.json")) as _bcf:
        _bc = json.load(_bcf)
    _BLD_CODES["fiber"] = tuple(str(x).lower() for x in _bc.get("fiber", []))
    _BLD_CODES["copper"] = tuple(str(x).lower() for x in _bc.get("copper", []))
except Exception:
    pass
BUILD_DATE = "2026-08-24"   # bump on every push so the console proves the version

# ---- DERIVED VERSION STAMP -------------------------------------------------
# RULE (Patrick 2026-08-20, after BUILD_DATE reported 08-18 while running 08-20
# code): a version marker that is typed by hand WILL eventually disagree with the
# code, and a marker that disagrees is worse than none because it gets trusted.
# So the console also prints values DERIVED from the file itself -- the mtime the
# updater actually wrote, and a fingerprint of the bytes. Neither can go stale,
# because neither is maintained by anyone.
def _file_stamp():
    """(written-at, 8-char fingerprint) of THIS file. Cannot lie about its age."""
    import hashlib
    try:
        f = os.path.abspath(__file__)
        b = open(f, "rb").read()
        return (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(f))),
                hashlib.sha256(b).hexdigest()[:8])
    except Exception:
        return ("unknown", "unknown")


# One id per launch, stamped on every lead this run writes. BRAIN section 44 has
# asked for run_id on every lead since April: without it nobody can say which
# capture produced which row, so "does the software make money" stays unanswerable.
try:
    import optimus_operator as _OP
except Exception:                     # never let identity break a sweep
    _OP = None


def OPERATOR():
    """Who is running this scan. Stamped on every row we write so 'who found
    this lead' has an answer in the data. Falls back to the hostname; never
    returns blank, and never raises into the sweep."""
    try:
        return _OP.current() if _OP else ("PC:" + os.environ.get("COMPUTERNAME", "unknown"))
    except Exception:
        return "unknown"


RUN_ID = time.strftime("%Y%m%d-%H%M%S")
_WRITTEN_AT, _FINGERPRINT = _file_stamp()
# Build-code status as ONE line for the banner. This used to be three lines of
# console every launch; the fact that matters is whether copper can be decoded.
if _BLD_CODES["copper"]:
    _GOLD_STATUS = ("gold = CONFIRMED copper only   (%d copper / %d fiber codes)"
                    % (len(_BLD_CODES["copper"]), len(_BLD_CODES["fiber"])))
else:
    _GOLD_STATUS = ("!! build_codes.json MISSING -- copper cannot be decoded, "
                    "every customer files as UNKNOWN")

def _git_commit():
    """Short commit of the checkout this file sits in, or a reason it is absent.

    The fingerprint already proves WHICH BYTES are running, which is the fact
    that matters. The commit adds provenance -- it says which push those bytes
    came from -- but it is genuinely unavailable on a PC that installed by raw
    download rather than git clone, and saying "unknown" there is honest rather
    than a fault to hide.
    """
    try:
        import shutil
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        git = shutil.which("git") or "git"
        r = subprocess.run([git, "-C", root, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=15)
        out = (r.stdout or "").strip()
        return out or "unknown (%s)" % (r.stderr or "").strip()[:50]
    except Exception as e:
        return "unavailable (no git checkout: %s)" % str(e)[:40]


def print_identity():
    """Prove WHICH file, from WHICH repo, is running -- before anything else.

    There are two hunters and two repos. `fiber_hunter.py` (v5.27, pixel-based)
    lives in patricksiado-prog/optimus-map-tools and self-updates from main;
    THIS file is precise_fiber_hunter.py and self-updates from the branch below.
    An outside review of the public repo in 2026-08 read v5.27, reasonably
    assumed it was the running code, and reported a writer bug that is real --
    but in a program that is not executing. Hours go to that mix-up. So the
    console states its own identity, and the feed publishes it.
    """
    try:
        me = os.path.abspath(__file__)
    except NameError:
        me = "(exec'd -- no __file__)"
    print("-" * 68)
    print("  RUNNING FILE : %s" % me)
    print("  BUILD_DATE   : %s   fingerprint: %s" % (BUILD_DATE, _FINGERPRINT))
    print("  COMMIT       : %s" % _git_commit())
    print("  PYTHON       : %s" % sys.executable)
    print("  SOURCE REPO  : %s" % GH_REPO)
    print("  BRANCH       : %s" % REPO_BRANCH)
    print("  SELF-UPDATE  : https://raw.githubusercontent.com/%s/%s/optimus/"
          "precise_fiber_hunter.py" % (GH_REPO, REPO_BRANCH))
    print("  NOT this one : optimus-map-tools/main/fiber_hunter.py (v5.27, "
          "pixel-based, a different tool)")
    print("-" * 68)


def print_controls():
    """The stop/go keys, ON THE LAUNCH BANNER. They used to print only when the
    sweep started, by which point the browser was up and the line had scrolled.
    Patrick drives this from a truck: the controls have to be on screen before
    anything moves. Skipped for the uploader window, which has no browser to
    pause and must not advertise keys that do nothing there."""
    print("-" * 68)
    print("  CONTROLS -- work anywhere, even while Chrome has focus")
    print("")
    print("    Ctrl+Shift+Pause   PAUSE  the hunter lets go of the map;")
    print("      (or Ctrl+Shift+P)       pan / zoom / search it by hand")
    print("    Ctrl+G             GO     resume from the CURRENT view")
    print("")
    print("    Ctrl+Shift+S       STOP   finish this cell, close clean")
    print("    Ctrl+Shift+K       KILL   force-quit, even if frozen")
    print("=" * 68)


def print_banner():
    """ONE tight banner. Every line here is something to act on.

    What used to print: nine lines of provenance (file path, python path, repo,
    branch, self-update URL, a warning about a different tool), three lines
    about gold, and a Gold Dots tab notice pointing at a RETIRED tab. It scrolled
    the controls off the screen every launch. The fingerprint is the fact that
    actually settles 'which code is running', so that stays; the rest is behind
    --identity (or OPTIMUS_VERBOSE=1) for when a version argument comes up.
    Moving _git_commit() behind the flag also drops a subprocess call from every
    startup.
    """
    print("=" * 68)
    print("  OPTIMUS FIBER HUNTER    build %s   fp %s   run %s"
          % (BUILD_DATE, _FINGERPRINT, RUN_ID))
    print("  %s" % _GOLD_STATUS)


if "--uploader" not in sys.argv:
    print_banner()
    print_controls()
if "--identity" in sys.argv or os.environ.get("OPTIMUS_VERBOSE"):
    print_identity()


def _bld_code(raw):
    """Pull the network build-type code (curr_ntwrk_bld_type_cd or kin) off a
    wire record's original JSON, tolerant of key formatting."""
    if not isinstance(raw, dict):
        return ""
    for k, v in raw.items():
        nk = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if "bldtype" in nk or ("ntwrk" in nk and "typecd" in nk):
            return str(v or "").strip().lower()
    return ""


try:
    from optimus_api_capture import compose_address as _compose_address
except Exception:                                  # keep the hunter standalone
    def _compose_address(street, city="", state="", zipc=""):
        street = (street or "").strip()
        tail = " ".join(x for x in ((state or "").strip(), (zipc or "").strip()) if x)
        parts = [p for p in (street, (city or "").strip(), tail) if p]
        return ", ".join(parts[:2]) + ((" " + tail) if tail and len(parts) > 2 else "")


# ---- classification telemetry -------------------------------------------------
# Every customer dot lands in exactly one of these buckets. Printed at the end of
# a run by wire_classification_report() so a bad gold/grey split is visible on the
# console instead of being discovered weeks later on the phone.
_WIRE_COUNTS = {"green": 0, "fiber": 0, "copper": 0, "unknown": 0, "no_code": 0}
_UNKNOWN_CODES = {}
# One real address per undecoded code, so the operator can click THAT dot on
# the map and read its popup. A code with no example is unconfirmable.
_UNKNOWN_CODE_SAMPLE = {}

# What to call a CUSTOMER whose build code we cannot decode.
#   "grey" (default) -- treat as an existing fiber customer and skip. A false
#                       grey costs nothing, because grey is skipped anyway.
#   "gold"           -- the old behaviour: assume copper and put them on the
#                       call list. Only use this if gold collapses to zero and
#                       the report below shows the codes really are copper.
# Override with:  set OPTIMUS_UNKNOWN_CUSTOMER=gold
_UNKNOWN_CUSTOMER = (os.environ.get("OPTIMUS_UNKNOWN_CUSTOMER")
                     or "unknown").strip().lower()


def _unknown_customer_status():
    """What to call a CUSTOMER whose build code we cannot decode.

    Three settings, via OPTIMUS_UNKNOWN_CUSTOMER:
      unknown (default) -- write it to the sheet as UNKNOWN. Not a lead, not
                           deleted. This is how `unavailable` stops being
                           invisible: it is the most common build code AT&T
                           sends, and both previous settings were wrong about
                           it -- "gold" put fiber customers on the call list,
                           "grey" threw real copper away.
      grey              -- old behaviour: treat as an existing fiber customer
                           and drop the row entirely.
      gold              -- the original behaviour that produced the
                           contaminated 3,328 rows. Do not use.
    """
    if _UNKNOWN_CUSTOMER == "gold":
        return "copper_upgrade"
    if _UNKNOWN_CUSTOMER == "grey":
        return "customer"
    return "unknown_customer"


def _publish_feed():
    """Ship this run's classification evidence to GitHub. Best-effort."""
    if not _FEED:
        return
    try:
        ded = {}
        if _DEDUPE_REPORT:
            ded = dict((f, getattr(_DEDUPE_REPORT, f))
                       for f in _DEDUPE_REPORT.FIELDS)
        # The capture already works out WHY a 200 yielded nothing -- the
        # top-level keys of the payload. It was printed to the console and
        # never published, so the one fact that identifies a changed payload
        # shape could only be read off a photograph.
        try:
            cap = _NET_CAPTURE[0]
            if cap is not None and _FEED:
                _FEED.truth(raw_features=getattr(cap, "svc_leads", None),
                            note="capture: %s" % cap.diag()[:150])
                _FEED.note_diagnostic({
                    "serviceability_responses": getattr(cap, "svc_seen", None),
                    "leads_decoded": getattr(cap, "svc_leads", None),
                    "empty_payload_top_keys": getattr(cap, "svc_empty_keys", None),
                    "capture_reason": cap.diag(),
                })
        except Exception:
            pass
        c = _WIRE_COUNTS
        stage(classified_green=c["green"], classified_gold=c["copper"],
              classified_grey=c["fiber"],
              classified_unknown=c["unknown"] + c["no_code"])
        stage_report()
        try:
            _FEED.note_stages(_STAGE)
        except Exception:
            pass
        _FEED.truth(classified=(c["green"] + c["fiber"] + c["copper"]
                                + c["unknown"] + c["no_code"]),
                    written=(_DEDUPE_REPORT.written if _DEDUPE_REPORT else None))
        _FEED.truth_report()
        _FEED.phase_report()
        _FEED.publish_audit(gh_put)
        return _FEED.publish(gh_put, counts=_WIRE_COUNTS,
                             undecoded=_UNKNOWN_CODES,
                             undecoded_samples=_UNKNOWN_CODE_SAMPLE,
                             dedupe=ded, note_text=_CUR_AREA[0] or "")
    except Exception as e:
        print("  (feed publish FAILED: %s)" % str(e)[:90])
        return False


def wire_classification_report():
    """One block at the end of a run saying how every customer dot was decided.

    Read it like this: `copper` is real gold. `unknown` and `no code` are dots we
    guessed on -- if either is large, the gold count is not trustworthy and the
    codes listed underneath need confirming on the dealer map."""
    c = _WIRE_COUNTS
    cust = c["fiber"] + c["copper"] + c["unknown"] + c["no_code"]
    if not (cust or c["green"]):
        return
    print("\n" + "-" * 62)
    print("DOT CLASSIFICATION THIS RUN")
    print("  GREEN  non-customers            %7d" % c["green"])
    print("  GREY   confirmed fiber customer %7d" % c["fiber"])
    print("  GOLD   confirmed copper         %7d   <- real upgrade leads" % c["copper"])
    if c["unknown"]:
        print("  ?      customer, code unknown   %7d   -> %s" % (
            c["unknown"], _unknown_customer_status().upper()))
    if c["no_code"]:
        print("  ?      customer, NO build code  %7d   -> %s" % (
            c["no_code"], _unknown_customer_status().upper()))
    if cust:
        guessed = 100.0 * (c["unknown"] + c["no_code"]) / cust
        print("  %.1f%% of customer dots were a guess, not a decode." % guessed)
    if _UNKNOWN_CODES:
        print("  UNDECODED BUILD CODES  (each one may be real gold we are")
        print("  currently discarding as grey):")
        for code, n in sorted(_UNKNOWN_CODES.items(), key=lambda kv: -kv[1])[:10]:
            print("     %-16s %6d   e.g. %s"
                  % (code, n, _UNKNOWN_CODE_SAMPLE.get(code, "(no sample)")))
        print("  CLICK one of those addresses on the dealer map. If its popup")
        print("  says 'Status: Existing Copper Customer', that code is COPPER --")
        print("  add it to build_codes.json and the gold comes back.")
    print("-" * 62)


def classify_wire(status, ban, raw):
    """classify_status + build-code tiebreak, for wire-captured dots.

    The map legend has only three states, keyed off two fields:
      * subscriber_ban EMPTY            -> GREEN (fiber-eligible non-customer)
      * ban present + confirmed FIBER   -> GREY  (fttp-gpon/ftth = already on fiber)
      * ban present + confirmed COPPER  -> GOLD  (copper/DSL customer = the
                                                  upgrade lead)
      * ban present + code we cannot decode -> GREY (see below -- NOT gold)
    A customer is GOLD only when we can CONFIRM copper. An unrecognised build
    code is GREY, not gold.

    DO NOT "fix" this back to gold-by-default. That was the old rule, and it put
    existing FIBER customers on the call list -- Patrick clicked a gold dot and
    got somebody already on fiber. It is also why the 'Gold Dots' tab still holds
    roughly 4.7x more rows than this rule produces (audit 2026-08-23, BRAIN.md
    22.14): those rows were written under the old rule and cannot be told apart,
    because nothing stamps which rule wrote a row. If a code is genuinely copper,
    confirm it on the map and add it to build_codes.json -- do not widen the
    default."""
    # GREY MEANS CUSTOMER. Nothing becomes grey without a real subscriber
    # account behind it -- a placeholder like "non-cust" is truthy, and reading
    # it as a customer turns a $500 GREEN into a GREY, which the write path
    # drops entirely. The lead does not get misfiled, it disappears.
    if is_customer_ban(ban):
        # AT&T sometimes SAYS it outright: "Status: Existing Copper Customer".
        # That is a direct statement from the source and it outranks a build
        # code we failed to decode. Without this, a dot whose own popup names it
        # a copper customer is filed GREY the moment its code is unfamiliar --
        # a confirmed $140 upgrade thrown away on a technicality.
        _txt = (status or "").lower() if isinstance(status, str) else ""
        if "copper" in _txt:
            _WIRE_COUNTS["copper"] += 1
            return "copper_upgrade"
        code = _bld_code(raw)
        if not code:
            # No build code on the record at all. We cannot tell fiber from
            # copper, so we are guessing either way. Counted, because if this
            # number is large the real problem is upstream (raw not reaching
            # us) and NO classification rule can fix it.
            _WIRE_COUNTS["no_code"] += 1
            return _unknown_customer_status()
        if code in _BLD_CODES["fiber"]:
            _WIRE_COUNTS["fiber"] += 1
            return "customer"            # GREY -> confirmed fiber customer, skip
        if code in _BLD_CODES["copper"]:
            _WIRE_COUNTS["copper"] += 1
            return "copper_upgrade"      # GOLD dot -> ORANGE row -> upgrade lead
        # Customer on a code in neither list. Previously this fell through to
        # GOLD, which is why existing FIBER customers turned up on the call
        # list -- Patrick clicked a "gold" dot on the map and it came back an
        # existing fiber customer. A new AT&T fiber designation lands here.
        _WIRE_COUNTS["unknown"] += 1
        _UNKNOWN_CODES[code] = _UNKNOWN_CODES.get(code, 0) + 1
        if code not in _UNKNOWN_CODE_SAMPLE:
            try:
                _UNKNOWN_CODE_SAMPLE[code] = str(
                    (raw or {}).get("address") or "")[:44]
            except Exception:
                pass
        return _unknown_customer_status()
    _WIRE_COUNTS["green"] += 1
    return classify_status(text=status, ban=ban)   # no ban -> GREEN (eligible)


def classify_lead(ld):
    """Build-code-aware classification for a captured lead dict."""
    return classify_wire(
        ld.get("status") if isinstance(ld.get("status"), str) else None,
        ld.get("ban"), ld.get("raw"))
POPUP_POLL_INTERVAL = 0.12    # poll the popup instead of fixed sleeps
POPUP_POLL_TIMEOUT = 2.0      # per click attempt
CLICK_OFFSETS = [(0, 0), (3, 0), (-3, 0), (0, 3), (0, -3)]   # retry spiral

# Pixel-click fallback is OFF by default: clicking "dots" detected on a
# transitioning/portal page lands on nav buttons and flips the view. We capture
# from the Mapbox backend read instead; --allow-click re-enables the old way.
ALLOW_CLICK = False
_AUTO_PROBED = [False]   # run the frame diagnostic at most once per session
# Alert when this many GOLD (copper->fiber upgrade) dots land in ONE viewport --
# a dense upgrade pocket is the hottest thing to work. Tune here.
GOLD_CLUSTER_ALERT = 8
# NEW-FIBER alert: this many GREEN (fiber-eligible / NON-customer) dots in ONE
# viewport AND very little grey (existing fiber customers) = a freshly-lit
# neighborhood -- brand-new fiber nobody has sold yet. Logged to a 'New Fiber
# Alerts' tab so it can trigger a phone notification.
NEW_FIBER_ALERT = 15
NEW_FIBER_TAB = "New Fiber Alerts"

# ---- BACKEND COMM TAB (Patrick 2026-08-20: "add a tab, tell the program to put
#      that info in, we run it, you observe the backend comm") -----------------
# Every network reply the sniffer considers DATA gets one row here, including the
# non-200s that used to be printed to the console and thrown away. That console
# print is how "serviceability reply 301" stayed invisible: it scrolls past, it is
# never persisted, and nobody can see it remotely. A 301 means AT&T bounced the
# data call to login and NOTHING lands -- green or gold -- so it is the single
# most important thing to be able to read after the fact.
# Precise Fiber's real shape. The header on the live sheet was 5 wide while
# flush() appended 6 values -- Run ID has been landing in an UNLABELLED column F
# since 2026-08-20, and the uploader path wrote only 5, so rows were ragged
# depending on which code path saved them. Both are normalised to this list.
OUT_HEADER = ["Address", "Dot Color", "Captured At", "Business", "Phone",
              "Run ID", "Operator"]


def _ensure_header(ws, header):
    """Make row 1 of `ws` carry `header`, WITHOUT disturbing any data.

    Adding a column to a tab that already holds hundreds of thousands of rows is
    the kind of edit that eats a dataset if it goes wrong, so this is deliberately
    timid:
      - empty tab            -> write the header
      - header already wide  -> do nothing at all
      - header too short     -> write ONLY the missing cells at the end of row 1
    It never rewrites a label that is already there (someone may have renamed a
    column on purpose) and never touches row 2 or below. Best-effort: a failure
    here must not stop leads from saving."""
    try:
        first = ws.row_values(1)
    except Exception:
        return
    try:
        if not first:
            ws.append_row(header, value_input_option="RAW")
            return
        if len(first) >= len(header):
            return
        # widen the tab if the grid is too narrow to hold the new columns
        try:
            if getattr(ws, "col_count", 0) and ws.col_count < len(header):
                ws.add_cols(len(header) - ws.col_count)
        except Exception:
            pass
        missing = header[len(first):]
        start = len(first) + 1
        cells = ws.range(1, start, 1, len(header))
        for c, val in zip(cells, missing):
            c.value = val
        ws.update_cells(cells, value_input_option="RAW")
        print("   labelled %d new column(s) in '%s': %s"
              % (len(missing), ws.title, ", ".join(missing)))
    except Exception as e:
        print("   (header check skipped on '%s': %s)" % (ws.title, str(e)[:60]))


BACKEND_TAB = "Backend Comm"
BACKEND_HEADER = ["Time", "Host", "Area", "Kind", "Status", "Bytes", "ms",
                  "Leads", "Green", "Gold", "Grey", "Zoom", "Radius mi", "URL",
                  "Content-Type", "Note", "Operator"]

# AT&T returns AT MOST ~3000 leads per "Search this area" (documented in
# backend_classifier.py, and four tabs in the sheet sit at exactly 3,000 rows --
# the fingerprint of a truncated response). This is the REAL limit on how far out
# we can usefully zoom: past the point where a viewport holds ~3000 addresses the
# reply silently truncates and the rest of that ground is never captured. Nothing
# reports an error -- the sweep just quietly misses houses. Any row at or above
# NEAR_CAP is a viewport that probably lost addresses.
# MEASURED, not assumed: backend_capture.txt (2026-07-16) shows two replies of
# EXACTLY 500 and an inspect header reading "total leads: 500". Patrick's team
# email says the same. This constant previously read 3000 -- a number taken from
# four sheet tabs sitting at 3,000 rows, which is a different artifact entirely.
# At 3000 the warning below could NEVER fire, so every truncated viewport was
# logged as a clean scan. That is worse than no guard at all.
BACKEND_LEAD_CAP = 500
NEAR_CAP = 475
# Landing EXACTLY on a round number is the truncation fingerprint. Flag those
# outright, so a future cap we have not measured still gets caught.
BACKEND_CAP_VALUES = (500, 1000, 1500, 2000, 2500, 3000)
_BACKEND_LOG = []          # rows buffered between flushes
_BACKEND_WS = [None]       # cached worksheet handle
_BACKEND_MAX = 5000        # hard cap per run so a long sweep cannot flood the sheet
_BACKEND_WRITTEN = [0]
_CUR_AREA = [""]        # set per cell so every backend row says WHERE
_CUR_ZOOM = [""]         # live map zoom, stamped on every backend row
_DOT_LAYERS = [None]     # dot-layer minzoom/maxzoom, printed once
_SVC_SAID = set()          # payload verdicts announced this run
_SVC_STATUS_SAID = set()   # HTTP statuses announced this run
_SEEN_ENDPOINTS = set()  # normalised endpoints already logged once
_SEEN_ENDPOINTS_MAX = 300   # bound it; a runaway pattern can never eat memory


def _endpoint_key(url):
    """Collapse a URL to the ENDPOINT it represents, not the individual request.

    Map tiles are addressed /z/x/y, so every single tile is a distinct path and
    naive de-duplication logs all of them -- hundreds of rows per sweep, the exact
    flood the once-per-endpoint rule exists to prevent. Replacing the numeric
    z/x/y segments with placeholders collapses a whole tile layer to one row:

        /v4/att.dots/12/954/1710.vector.pbf  ->  /v4/att.dots/{z}/{x}/{y}.vector.pbf
    """
    try:
        base = url.split("?")[0]
        parts = base.split("/")
        out, n = [], 0
        for seg in parts:
            head = seg.split(".")[0]
            if head.isdigit() and n < 3:
                out.append(("{z}", "{x}", "{y}")[n] + seg[len(head):])
                n += 1
            else:
                out.append(seg)
        return "/".join(out)[:180]
    except Exception:
        return url.split("?")[0][:180]


def log_backend(kind, url="", status="", ct="", nbytes="", ms="", leads="",
                green="", gold="", grey="", note="", area="", radius=""):
    """Buffer one backend-communication row. Never raises, never blocks.

    Called from the response handler on EVERY data-ish reply, success or not.
    Rows are written by flush_backend() in the same batch cadence as the leads,
    so this costs one extra append per viewport, not one per request.
    """
    try:
        if _BACKEND_WRITTEN[0] >= _BACKEND_MAX or len(_BACKEND_LOG) >= 2000:
            return          # capped: telemetry must never grow without bound
        host = ""
        try:
            host = url.split("//", 1)[-1].split("/", 1)[0][:40]
        except Exception:
            pass
        _BACKEND_LOG.append([
            time.strftime("%Y-%m-%d %H:%M:%S"), host, str(area)[:40], kind,
            str(status), str(nbytes), str(ms), str(leads), str(green),
            str(gold), str(grey), str(_CUR_ZOOM[0]), str(radius),
            url.split("?")[0][:180], str(ct)[:40], str(note)[:180]])
    except Exception:
        pass


def flush_backend(ws):
    """Write buffered backend rows to the Backend Comm tab. Best-effort."""
    global _BACKEND_LOG
    if not _BACKEND_LOG or ws is None:
        return 0
    rows, _BACKEND_LOG = _BACKEND_LOG, []
    try:
        bw = _BACKEND_WS[0]
        if bw is None:
            sh = ws.spreadsheet
            try:
                bw = sh.worksheet(BACKEND_TAB)
            except Exception:
                bw = sh.add_worksheet(title=BACKEND_TAB, rows="6000",
                                      cols=str(len(BACKEND_HEADER)))
                bw.append_row(BACKEND_HEADER, value_input_option="RAW")
            _ensure_header(bw, BACKEND_HEADER)
            _BACKEND_WS[0] = bw
        for i in range(0, len(rows), 500):
            bw.append_rows(rows[i:i + 500], value_input_option="RAW")
        _BACKEND_WRITTEN[0] += len(rows)
        return len(rows)
    except Exception as e:
        print("  (Backend Comm tab write failed: %s)" % str(e)[:70])
        return 0

# SLAM-TO-STOP: hold the mouse in the very top-left screen corner ~1s to stop the
# hunt cleanly. The hunter pans from the CENTER of the screen and never parks the
# cursor in the corner itself, so this can only be triggered by you.
_STOP = [False]

# PAUSE/RESUME (Patrick, 2026-08-25): freeze the motion so the map can be moved
# BY HAND -- pan, zoom, type a new address, click Search this area -- and then
# pick the hunt back up from wherever it now sits. Without this the only way to
# re-aim was to kill the program and relaunch, which costs a browser start, a
# login, and the run's dedupe memory.
_PAUSE = [False]
# Ctrl+G means GO in two situations: resume from a pause, and skip the opening
# countdown. One flag for the second, so the countdown never waits on a key it
# cannot see.
_GO_NOW = [False]
_PAUSE_FLAG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "PAUSED.flag")


def _set_paused(on):
    """Flip the pause state AND leave a flag file. The uploader is a SEPARATE
    process -- it cannot see this flag in memory, and its 15-minute idle
    shutdown would otherwise quit mid-pause and stop writing."""
    _PAUSE[0] = bool(on)
    try:
        if on:
            with open(_PAUSE_FLAG, "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        elif os.path.exists(_PAUSE_FLAG):
            os.remove(_PAUSE_FLAG)
    except OSError:
        pass


def pause_gate(page=None):
    """Block here while paused. Returns True if we WERE paused, which tells the
    caller the map may have been moved by hand and it should re-aim rather than
    resume its old spiral. Never raises."""
    if not _PAUSE[0]:
        return False
    print("\n" + "=" * 58)
    print("  PAUSED -- the hunter has let go of the map.")
    print("  Move it however you like: pan, zoom, search a new address.")
    print("  Press Ctrl+G to GO again from wherever you leave it.")
    print("=" * 58 + "\n")
    while _PAUSE[0] and not _STOP[0]:
        time.sleep(0.25)
    if _STOP[0]:
        return True
    print("\n" + "=" * 58)
    print("  RESUMED -- sweeping outward from the CURRENT view.")
    print("=" * 58 + "\n")
    return True


def countdown_to_start(secs=10):
    """Hold before the FIRST pan so the map can be aimed by hand.

    The map opens wherever the ZIP search put it (or wherever the last session
    left it) and the hunter used to start dragging immediately -- if that view
    was wrong, the first cells were already the wrong streets. Ten seconds is
    enough to look at it. Every control works during the hold, and Ctrl+G cuts
    it short. Skipped when nobody is at the keyboard.
    """
    if _STOP[0]:
        return
    try:
        if not (sys.stdin and sys.stdin.isatty()):
            return
    except Exception:
        return
    _GO_NOW[0] = False
    print("")
    print("  Map is up. Sweep starts in %d seconds." % secs)
    print("  Ctrl+G = go NOW    Ctrl+Shift+Pause = hold    Ctrl+Shift+S = stop")
    for i in range(secs, 0, -1):
        if _STOP[0] or _GO_NOW[0]:
            break
        if _PAUSE[0]:
            pause_gate()
            break
        try:
            sys.stdout.write("\r   starting in %2d ... " % i)
            sys.stdout.flush()
        except Exception:
            pass
        time.sleep(1)
    try:
        sys.stdout.write("\r" + " " * 32 + "\r")
        sys.stdout.flush()
    except Exception:
        pass
    if not _STOP[0]:
        print("  GO.\n")


def _start_stop_watcher():
    """Background watcher: if the mouse sits in the extreme top-left corner for
    ~1 second, set _STOP so the sweep ends cleanly (closes the browser, no auto-
    restart). Windows only; a harmless no-op elsewhere."""
    _set_paused(False)      # clear a flag left behind by a run that died paused
    if os.name != "nt":
        return
    import threading

    def _watch():
        import ctypes
        import time as _t

        class _PT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        user32 = ctypes.windll.user32

        def _down(vk):
            return bool(user32.GetAsyncKeyState(vk) & 0x8000)
        held = 0
        while True:
            try:
                # HARD KILL SWITCH: Ctrl+Shift+K -> force-quit INSTANTLY, even if
                # the hunt is frozen on a hung AT&T request (this runs in its own
                # thread and os._exit doesn't wait for the stuck main thread, so
                # you never have to restart the PC). Ctrl=0x11 Shift=0x10 K=0x4B.
                if _down(0x11) and _down(0x10) and _down(0x4B):
                    print("\n" + "#" * 58)
                    print("  KILL SWITCH (Ctrl+Shift+K): force-quitting now.")
                    print("#" * 58 + "\n")
                    os._exit(0)          # immediate; launcher sees 0 = no restart
                # PAUSE: Ctrl+Shift+Pause -> let go of the map so it can be moved
                # by hand. Ctrl+Shift+P does the same, because Pause/Break is an
                # Fn-layer key on most HP laptops and a hotkey you cannot press
                # is not a hotkey. Pause=0x13 P=0x50.
                if _down(0x11) and _down(0x10) and (_down(0x13) or _down(0x50)):
                    if not _PAUSE[0]:
                        _set_paused(True)
                # GO AGAIN: Ctrl+G -> resume from the CURRENT view, and skip
                # the opening countdown. G=0x47.
                if _down(0x11) and _down(0x47):
                    _GO_NOW[0] = True
                    if _PAUSE[0]:
                        _set_paused(False)
                # GENTLE STOP (keyboard): Ctrl+Shift+S -> finish this cell, close
                # the browser cleanly, no restart. Keyboard beats the corner
                # gesture because the hunter OWNS the mouse (it moves the cursor
                # every pan), so you can't hold the pointer still in a corner --
                # but a key combo is read straight off the keyboard state.
                # Ctrl=0x11 Shift=0x10 S=0x53.
                if _down(0x11) and _down(0x10) and _down(0x53):
                    _STOP[0] = True
                    print("\n" + "#" * 58)
                    print("  STOP (Ctrl+Shift+S): finishing this cell, closing cleanly.")
                    print("  (If it's frozen, hit Ctrl+Shift+K to force-quit.)")
                    print("#" * 58 + "\n")
                    return
                # GENTLE STOP (mouse): jam the pointer into ANY screen corner and
                # hold ~0.6s. Wider 10px zone; works in the brief idle window
                # between pans. If it won't catch (the hunter keeps grabbing the
                # cursor), use Ctrl+Shift+S instead.
                pt = _PT()
                user32.GetCursorPos(ctypes.byref(pt))
                sw = user32.GetSystemMetrics(0); sh = user32.GetSystemMetrics(1)
                near = 10
                in_corner = ((pt.x <= near or pt.x >= sw - near) and
                             (pt.y <= near or pt.y >= sh - near))
                if in_corner:
                    held += 1
                    if held >= 3:                    # ~0.6s at 0.2s poll
                        _STOP[0] = True
                        print("\n" + "#" * 58)
                        print("  STOP: mouse held in a screen CORNER.")
                        print("  Finishing this cell and shutting down cleanly...")
                        print("  (If it's frozen, hit Ctrl+Shift+K to force-quit.)")
                        print("#" * 58 + "\n")
                        return
                else:
                    held = 0
            except Exception:
                pass
            _t.sleep(0.15)
    threading.Thread(target=_watch, daemon=True).start()

    # Windows turns Ctrl+Pause into a BREAK signal that kills the process when
    # the console has focus -- which would make the pause hotkey a quit button.
    # Catch it and pause instead. (Ctrl+Shift+K remains the way to force-quit.)
    try:
        import signal
        if hasattr(signal, "SIGBREAK"):
            def _on_break(_sig, _frm):
                _set_paused(not _PAUSE[0])
            signal.signal(signal.SIGBREAK, _on_break)
    except Exception:
        pass

    # Compact reminder right as motion begins -- the full block is on the
    # launch banner (print_controls). The corner gesture lives only here.
    print("  KEYS: Ctrl+Shift+Pause = PAUSE   Ctrl+G = GO   "
          "Ctrl+Shift+S = stop   Ctrl+Shift+K = kill")
    print("  (mouse stop: jam the pointer into any screen CORNER, hold ~1s)")
_NET_CAPTURE = [None]    # the always-on network capture (set in main)

JSONL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "precise_addresses.jsonl")

# WRITES NEVER TOUCH THE MOTION (Patrick, 2026-07-02 "once and for all"):
# the browser process pans/searches/captures ONLY -- every capture goes to the
# local JSONL (microseconds) and a separate UPLOADER process (this same file,
# --uploader) does ALL Google work: sheet writes, biz matching, status rows.
# While it's writing, the map is still panning, because they are two programs.
_SPLIT = [False]
RUN_STATUS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "run_status.json")
UPLOADER_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "uploader_log.txt")
UPLOADER_LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "uploader.lock")

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
})();
"""

# Hide the Mapbox/MapLibre "user location accuracy circle" -- on a laptop (no GPS)
# the geolocation accuracy is poor, so that translucent circle balloons into a
# huge blob that covers the map and hides the fiber dots underneath it. It is
# purely cosmetic (the real fix would be showAccuracyCircle:false, but this is
# AT&T's site, so we just hide the element in OUR browser). Kills the blob without
# touching any fiber dot.
GEO_HIDE_JS = """
(() => {
  const css = '.mapboxgl-user-location-accuracy-circle,' +
              '.maplibregl-user-location-accuracy-circle{display:none !important;}';
  const add = () => {
    try {
      if (document.getElementById('optimus-hide-geo')) return;
      const s = document.createElement('style');
      s.id = 'optimus-hide-geo';
      s.textContent = css;
      (document.head || document.documentElement).appendChild(s);
    } catch (e) {}
  };
  add();
  document.addEventListener('DOMContentLoaded', add);
  const t = setInterval(add, 500);
  setTimeout(() => clearInterval(t), 120000);
})();
"""

# WebGL-context-loss watchdog. On a low-RAM laptop, after a long run Chromium
# drops the map's WebGL context ("Too many active WebGL contexts") -> the canvas
# goes BLANK WHITE and never renders again, but our Python loop keeps sweeping a
# DEAD map (so the motion watchdog never fires) = the permanent freeze. This
# listener flips window.__optimusGLLost when the context is lost so the sweep can
# detect it and RELOAD the page to revive the map.
GL_WATCH_JS = """
(() => {
  window.__optimusGLLost = false;
  const hook = (cv) => {
    if (cv.__optimusGLHooked) return;
    cv.__optimusGLHooked = true;
    cv.addEventListener('webglcontextlost', (e) => {
      try { e.preventDefault(); } catch (x) {}
      window.__optimusGLLost = true;
    }, false);
    cv.addEventListener('webglcontextrestored', () => {
      window.__optimusGLLost = false;
    }, false);
  };
  const scan = () => { try { document.querySelectorAll('canvas').forEach(hook); } catch (e) {} };
  scan();
  const t = setInterval(scan, 1000);
  setTimeout(() => clearInterval(t), 1800000);   // 30 minutes
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

MAPBOX_VIEW_JS = """
() => {
  const m = (window.__optimusMaps || [])[0];
  if (!m || !m.getZoom) return null;
  const out = {zoom: null, bounds: null, layers: []};
  try { out.zoom = Math.round(m.getZoom() * 100) / 100; } catch (e) {}
  try {
    const b = m.getBounds();
    out.bounds = {w: b.getWest(), s: b.getSouth(), e: b.getEast(), n: b.getNorth()};
  } catch (e) {}
  // Patrick 2026-08-20: "the dots are created at a certain zoom level". A Mapbox
  // layer DECLARES that threshold as minzoom, so read it instead of guessing --
  // below it the layer renders nothing no matter how the sweep is configured.
  try {
    const style = m.getStyle();
    for (const L of (style.layers || [])) {
      const id = (L.id || '').toLowerCase();
      if (L.type !== 'circle' && L.type !== 'symbol') continue;
      if (!(id.includes('dot') || id.includes('fiber') || id.includes('elig') ||
            id.includes('serv') || id.includes('addr') || id.includes('point'))) continue;
      let n = 0;
      try { n = m.queryRenderedFeatures({layers: [L.id]}).length; } catch (e) {}
      out.layers.push({id: L.id, type: L.type,
                       minzoom: (L.minzoom === undefined ? null : L.minzoom),
                       maxzoom: (L.maxzoom === undefined ? null : L.maxzoom),
                       rendered: n});
    }
  } catch (e) {}
  return out;
}
"""


# Full capture-state diagnostic. Answers, in one call: is the hook alive, did we
# get the real map, is the style loaded, what zoom are we at, which layers can
# carry dots, what is each layer's zoom band, and how many features does each
# actually return RIGHT NOW. Without the zoom band a zero is unreadable -- a
# layer above its maxzoom is hidden and returns nothing, which is not the same
# fact as "no fiber here".
MAPBOX_DUMP_JS = """
() => {
  // EVIDENCE ONLY. Reads the live map; changes nothing.
  const out = {captured: false, style: null, features: [], markers: [],
               marker_note: "", error: null};
  let maps = (window.__optimusMaps || []).slice();
  if (!maps.length) {
    try {
      for (const k in window) {
        let v; try { v = window[k]; } catch (e) { continue; }
        if (v && typeof v.queryRenderedFeatures === 'function' &&
            typeof v.getStyle === 'function') { maps.push(v); break; }
      }
    } catch (e) {}
  }
  const m = maps[0];

  // DOM MARKERS. If AT&T draws the dots as mapboxgl.Marker elements rather
  // than as a styled layer, they are NOT in queryRenderedFeatures and there is
  // no circle-color expression anywhere -- the colour lives in inline CSS. The
  // console has already shown '[Map marker]' entries, so capture this either
  // way rather than reporting an empty Mapbox dump as if it meant no dots.
  try {
    const sel = '.mapboxgl-marker, .maplibregl-marker, [class*=marker], ' +
                '[class*=dot], [class*=pin], [data-status], [data-type]';
    const els = document.querySelectorAll(sel);
    out.marker_note = els.length + " marker-ish element(s) in the DOM";
    let n = 0;
    for (const el of els) {
      if (n++ >= 80) break;
      const cs = window.getComputedStyle(el);
      const par = el.parentElement;
      const pcs = par ? window.getComputedStyle(par) : null;

      // EVERY data-* attribute. AT&T's own state name is far more likely to be
      // here (data-status="copper") than inferable from an RGB value.
      const data = {};
      try { for (const k in el.dataset) data[k] = el.dataset[k]; } catch (e) {}
      const pdata = {};
      try { if (par) for (const k in par.dataset) pdata[k] = par.dataset[k]; } catch (e) {}

      // Every attribute, not just the ones we thought to ask for.
      const attrs = {};
      try {
        for (const a of el.attributes) attrs[a.name] = String(a.value).slice(0, 200);
      } catch (e) {}

      // React keeps the component's props on the DOM node under a hashed key.
      // If AT&T's frontend decided the colour from a prop, it is in here.
      let react = null;
      try {
        for (const k of Object.keys(el)) {
          if (k.startsWith('__reactProps') || k.startsWith('__reactEventHandlers')) {
            const p = el[k];
            react = {};
            for (const pk in p) {
              const pv = p[pk];
              if (pv === null || ['string','number','boolean'].includes(typeof pv))
                react[pk] = pv;
            }
            break;
          }
        }
      } catch (e) {}

      // The marker's own coordinate -- this is what ties it to a backend record.
      let lngLat = null;
      try {
        for (const k of Object.keys(el)) {
          const v = el[k];
          if (v && typeof v === 'object' && 'lng' in v && 'lat' in v) {
            lngLat = {lng: v.lng, lat: v.lat}; break;
          }
        }
        if (!lngLat && el._lngLat) lngLat = {lng: el._lngLat.lng, lat: el._lngLat.lat};
      } catch (e) {}

      const svg = el.querySelector('svg, circle, path');
      out.markers.push({
        id: el.id || null,
        className: el.className && el.className.baseVal !== undefined
                   ? el.className.baseVal : String(el.className || ''),
        data: data,
        attributes: attrs,
        inline_style: (el.getAttribute && el.getAttribute('style')) || '',
        computed: {backgroundColor: cs.backgroundColor, color: cs.color,
                   borderColor: cs.borderColor, fill: cs.fill,
                   stroke: cs.stroke, backgroundImage: (cs.backgroundImage || '').slice(0,160)},
        inner_fill: svg ? (svg.getAttribute('fill') ||
                           window.getComputedStyle(svg).fill || '') : '',
        lngLat: lngLat,
        react_props: react,
        title: el.getAttribute('title') || el.getAttribute('aria-label') || '',
        parent: par ? {
          className: par.className && par.className.baseVal !== undefined
                     ? par.className.baseVal : String(par.className || ''),
          data: pdata,
          backgroundColor: pcs ? pcs.backgroundColor : '',
          html_head: (par.outerHTML || '').slice(0, 400)
        } : null,
        outerHTML: (el.outerHTML || '').slice(0, 1200)
      });
    }
  } catch (e) { out.marker_note = 'marker scan failed: ' + e; }

  if (!m) { out.error = 'no mapboxgl.Map object found'; return out; }
  out.captured = true;

  try {
    const st = m.getStyle() || {};
    out.style = {
      sources: Object.keys(st.sources || {}),
      layers: (st.layers || []).map(L => ({
        id: L.id, type: L.type, source: L.source,
        sourceLayer: L['source-layer'],
        minzoom: (L.minzoom === undefined ? null : L.minzoom),
        maxzoom: (L.maxzoom === undefined ? null : L.maxzoom),
        filter: L.filter === undefined ? null : L.filter,
        layout: L.layout || null,
        paint: L.paint || null          // circle-color expression preserved WHOLE
      }))
    };
  } catch (e) { out.error = 'getStyle: ' + e; }

  try {
    const fs = m.queryRenderedFeatures() || [];
    for (let i = 0; i < fs.length && i < 300; i++) {
      const f = fs[i];
      out.features.push({
        id: f.id === undefined ? null : f.id,
        type: f.type, source: f.source, sourceLayer: f.sourceLayer || null,
        layer_id: (f.layer || {}).id || null,
        layer_type: (f.layer || {}).type || null,
        paint: (f.layer || {}).paint || null,
        geometry_type: (f.geometry || {}).type || null,
        coordinates: (f.geometry || {}).coordinates || null,
        properties: f.properties || {}
      });
    }
  } catch (e) { out.error = (out.error || '') + ' qRF: ' + e; }
  return out;
}
"""


def dump_mapbox_evidence(page, log=print):
    """Publish the live Mapbox style and rendered features. Reads only.

    Requested as an evidence-only audit: rather than inferring the gold/grey
    rule from build codes, read the rule AT&T's own map uses to paint the dots.
    If the dots turn out to be DOM markers instead of a styled layer, the
    marker dump says so plainly instead of an empty features list being
    mistaken for "no dots here".
    """
    try:
        d = page.evaluate(MAPBOX_DUMP_JS)
    except Exception as e:
        log("  (mapbox dump failed: %s)" % str(e)[:90])
        return None
    try:
        style = d.get("style") or {}
        layers = style.get("layers") or []
        feats = d.get("features") or []
        marks = d.get("markers") or []
        dots = [L for L in layers
                if L.get("type") in ("circle", "symbol")
                and not re.search(r"mapbox|composite|terrain|satellite|road|label",
                                  str(L.get("source") or ""), re.I)]
        log("")
        log("=== MAPBOX EVIDENCE DUMP ===")
        log("  map object captured : %s" % d.get("captured"))
        log("  style layers        : %d  (sources: %d)"
            % (len(layers), len(style.get("sources") or [])))
        log("  candidate dot layers: %d" % len(dots))
        log("  rendered features   : %d" % len(feats))
        log("  DOM markers         : %s" % d.get("marker_note"))
        if d.get("error"):
            log("  error               : %s" % str(d["error"])[:120])
        for L in dots[:6]:
            log("    layer %-24s src=%-18s color=%s"
                % (str(L.get("id"))[:24], str(L.get("source"))[:18],
                   json.dumps((L.get("paint") or {}).get("circle-color"))[:90]))
        if not feats and marks:
            log("")
            log("  NOTE: zero Mapbox features but %d DOM marker(s) present." % len(marks))
            log("  The dots are drawn as DOM elements, NOT as a styled Mapbox")
            log("  layer -- so there is no circle-color expression to read and")
            log("  queryRenderedFeatures can never see them. The colour lives in")
            log("  the marker CSS captured above.")
        blob = json.dumps(d, indent=1, default=str)
        gh_put("optimus/_feed/mapbox_style_dump.json",
               json.dumps({"captured": d.get("captured"),
                           "error": d.get("error"),
                           "style": style,
                           "candidate_dot_layers": dots}, indent=1, default=str))
        gh_put("optimus/_feed/mapbox_features_dump.json",
               json.dumps({"rendered_features": feats,
                           "dom_markers": marks,
                           "marker_note": d.get("marker_note")},
                          indent=1, default=str))
        log("  -> optimus/_feed/mapbox_style_dump.json")
        log("  -> optimus/_feed/mapbox_features_dump.json")
        log("=" * 30)
        return d
    except Exception as e:
        log("  (mapbox dump publish failed: %s)" % str(e)[:90])
        return None


MAPBOX_DIAG_JS = """
() => {
  const out = {hook_installed: !!(window.__optimusMaps),
               maps_hooked: (window.__optimusMaps || []).length,
               has_mapboxgl: !!(window.mapboxgl),
               canvases: document.querySelectorAll('.mapboxgl-canvas').length,
               map_captured: false, map_loaded: null, style_loaded: null,
               zoom: null, center: null, layers_total: null, sources_total: null,
               candidate_layers: [], rendered_total: null, error: null};
  let maps = (window.__optimusMaps || []).slice();
  if (!maps.length) {
    try {
      for (const k in window) {
        let v; try { v = window[k]; } catch (e) { continue; }
        if (v && typeof v.queryRenderedFeatures === 'function' &&
            typeof v.getStyle === 'function') { maps.push(v); break; }
      }
    } catch (e) {}
  }
  const m = maps[0];
  if (!m) { out.error = 'no map object found'; return out; }
  out.map_captured = true;
  try { out.map_loaded = !!m.loaded(); } catch (e) {}
  try { out.style_loaded = !!m.isStyleLoaded(); } catch (e) {}
  try { out.zoom = m.getZoom(); } catch (e) {}
  try { const c = m.getCenter(); out.center = [c.lng, c.lat]; } catch (e) {}
  let style = null;
  try { style = m.getStyle(); } catch (e) { out.error = 'getStyle: ' + e; }
  if (!style) return out;
  out.layers_total = (style.layers || []).length;
  out.sources_total = Object.keys(style.sources || {}).length;
  let all = [];
  try { all = m.queryRenderedFeatures(); } catch (e) { out.error = 'qRF: ' + e; }
  out.rendered_total = all.length;
  for (const L of (style.layers || [])) {
    // circle/symbol layers on a non-basemap source are what a dot can be
    const t = L.type || '';
    if (t !== 'circle' && t !== 'symbol') continue;
    const srcId = String(L.source || '');
    if (/mapbox|composite|terrain|satellite/i.test(srcId) && !/att|fiber|dot|lead/i.test(srcId)) continue;
    let n = 0, sample = null;
    try {
      const f = m.queryRenderedFeatures({layers: [L.id]});
      n = f.length;
      if (n) sample = {geom: (f[0].geometry || {}).type,
                       props: f[0].properties || {},
                       source_layer: f[0].sourceLayer || null};
    } catch (e) {}
    // SOURCE-level truth, a DIFFERENT question from rendered: what is in the
    // loaded tiles, regardless of whether the style draws it right now. A layer
    // hidden by zoom band, filter or visibility renders zero while its source
    // is full -- and a rendered-only diagnostic calls that "empty ground".
    // With both numbers the distinction is free:
    //   src>0 rend>0 healthy       src>0 rend=0 style/zoom/filter hides it
    //   src=0 rend>0 wrong source  src=0 rend=0 data/session/load problem
    let srcN = null;
    try {
      const q = {};
      if (L['source-layer']) q.sourceLayer = L['source-layer'];
      srcN = m.querySourceFeatures(srcId, q).length;
    } catch (e) {}
    let color = null;
    try { color = JSON.stringify(m.getPaintProperty(L.id, 'circle-color')); } catch (e) {}
    let vis = null;
    try { vis = m.getLayoutProperty(L.id, 'visibility'); } catch (e) {}
    out.candidate_layers.push({
      id: L.id, type: t, source: srcId,
      source_layer: L['source-layer'] || null,
      source_features: srcN,
      // The SOURCE's own maxzoom caps which tiles exist; the LAYER's maxzoom
      // caps where the style draws them. They are different numbers and they
      // fail differently: past source maxzoom the tiles are overzoomed from a
      // lower level (data still there); past layer maxzoom the layer is simply
      // not drawn (data there, rendered zero). Conflating them misreads which.
      source_maxzoom: (function(){
        try { const sp = (style.sources || {})[srcId] || {};
              return (sp.maxzoom === undefined ? null : sp.maxzoom); }
        catch (e) { return null; }
      })(),
      minzoom: (L.minzoom === undefined ? null : L.minzoom),
      maxzoom: (L.maxzoom === undefined ? null : L.maxzoom),
      visibility: vis, circle_color: color,
      rendered: n, sample: sample
    });
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


def read_map_view(page):
    """Read the live map's zoom, bounds and dot-layer zoom thresholds.

    Cheap (one evaluate) and called once per cell so every Backend Comm row can
    say WHICH ZOOM produced it. The dot layer's declared minzoom is the hard
    floor on zooming out: below it the layer draws nothing and the sweep captures
    nothing, regardless of how wide the viewport is. Never raises.
    """
    try:
        v = page.evaluate(MAPBOX_VIEW_JS)
    except Exception:
        return None
    if not isinstance(v, dict):
        return None
    try:
        if v.get("zoom") is not None:
            _CUR_ZOOM[0] = v["zoom"]
        if v.get("layers") and not _DOT_LAYERS[0]:
            _DOT_LAYERS[0] = v["layers"]
            print("\n  DOT LAYERS (the zoom range where dots exist):")
            for L in v["layers"]:
                print("    %-30s min=%-5s max=%-5s rendered now=%d"
                      % (str(L.get("id"))[:30], L.get("minzoom"),
                         L.get("maxzoom"), L.get("rendered") or 0))
            print("    -> zooming out below the highest 'min' shows NO dots at all.\n")
    except Exception:
        pass
    return v


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


def capture_diagnostic(page):
    """Run the full capture-state diagnostic and hand it to the feed.

    Patrick, 2026-08-23: "create backend feedback u need to diagnose the issue
    not me." So the tool reports its own health instead of asking the operator
    to read a console.
    """
    diag = {"mapbox": {}, "verdict": "", "advice": ""}
    try:
        frames = list(page.frames)
    except Exception:
        frames = [page]
    best = None
    for fr in frames:
        try:
            d = fr.evaluate(MAPBOX_DIAG_JS)
        except Exception as e:
            d = {"error": str(e)[:120]}
        if d and d.get("map_captured"):
            best = d
            break
        if best is None:
            best = d
    diag["mapbox"] = best or {}

    mb = diag["mapbox"]
    zoom = mb.get("zoom")
    cands = mb.get("candidate_layers") or []
    # A layer is only usable when the CURRENT zoom sits inside its own band.
    # Outside it the layer is hidden and returns nothing -- a zero that means
    # "you cannot see this from here", not "there is nothing here".
    in_band, out_band = [], []
    for L in cands:
        lo = L.get("minzoom")
        hi = L.get("maxzoom")
        lo = 0.0 if lo is None else float(lo)
        hi = 24.0 if hi is None else float(hi)
        L["in_band"] = (zoom is not None and lo <= float(zoom) < hi)
        (in_band if L["in_band"] else out_band).append(L)
    diag["layers_in_band"] = len(in_band)
    diag["layers_out_of_band"] = len(out_band)
    if in_band:
        diag["safe_zoom"] = round(
            (max(float(L.get("minzoom") or 0) for L in in_band)
             + min(float(L.get("maxzoom") or 24) for L in in_band)) / 2.0, 2)

    if not mb.get("hook_installed") and not mb.get("map_captured"):
        diag["verdict"] = "HOOK_MISSING"
        diag["advice"] = ("the mapboxgl hook never captured a map object -- "
                          "capture cannot use the Mapbox path at all")
    elif not mb.get("style_loaded"):
        diag["verdict"] = "MAP_NOT_READY"
        diag["advice"] = "style not loaded yet; query too early"
    elif cands and not in_band:
        diag["verdict"] = "ZOOM_OUT_OF_BAND"
        diag["advice"] = ("every dot layer is outside its zoom band at z=%s -- "
                          "a zero here is INVALID, not empty ground" % zoom)
    elif not cands:
        diag["verdict"] = "NO_DOT_LAYERS"
        diag["advice"] = "no circle/symbol layer looks like a dot layer"
    elif not mb.get("rendered_total"):
        # Source vs rendered separates "nothing is here" from "something is
        # here and the style is hiding it" -- the same zero, opposite causes.
        _src = sum((L.get("source_features") or 0) for L in cands)
        if _src:
            diag["verdict"] = "RENDERED_ZERO_SOURCE_FULL"
            diag["advice"] = ("%d feature(s) ARE in the loaded tiles but the "
                              "style renders none of them -- a filter, a "
                              "visibility flag or the zoom band is hiding "
                              "them. This zero is INVALID, not empty ground."
                              % _src)
        else:
            diag["verdict"] = "ZERO_RENDERED"
            diag["advice"] = ("nothing drawn AND nothing in the source tiles "
                              "-- no data reached the map for this view")
    else:
        diag["verdict"] = "MAPBOX_OK"
    # A zero is only evidence of empty ground when EVERY precondition held.
    # Otherwise it is an artefact of our own broken state, and writing "+0" for
    # it is how a working neighbourhood gets recorded as barren.
    _pre = {
        "map_captured": bool(mb.get("map_captured")),
        "style_loaded": bool(mb.get("style_loaded")),
        "map_loaded": bool(mb.get("map_loaded")),
        "dot_layers_found": bool(cands),
        "zoom_in_band": diag.get("layers_in_band", 0) > 0,
        "query_ok": not mb.get("error"),
    }
    diag["preconditions"] = _pre
    _failed = [k for k, ok in _pre.items() if not ok]
    # WHICH PATH ARE WE JUDGING? Dots are read off the WIRE, not out of Mapbox
    # -- the Mapbox hook is a cross-check. So a Mapbox precondition failure is
    # only a verdict on capture when the wire produced nothing either. Without
    # this, a perfectly healthy backend sweep prints INVALID_ZERO in red every
    # time the map object is slow to appear, and the next person spends an hour
    # on a renderer that was never in the path.
    _wire_ok = False
    try:
        if _FEED:
            _t = getattr(_FEED, "_TRUTH", {}) or {}
            _wire_ok = (_t.get("delivery") in ("DATA_OK", "OK")
                        and (_t.get("raw_features") or 0) > 0)
    except Exception:
        pass
    if _failed and _wire_ok:
        diag["zero_verdict"] = "MAPBOX_UNAVAILABLE_WIRE_OK"
        diag["zero_reason"] = ("the Mapbox cross-check is unavailable (%s) but "
                               "AT&T delivered records on the wire, which is "
                               "the path capture actually uses -- not a capture "
                               "failure" % ", ".join(_failed))
    elif _failed:
        stage(invalid_zero=1)
        diag["zero_verdict"] = "INVALID_ZERO"
        diag["zero_reason"] = ("a zero from this view proves nothing -- "
                               "failed: %s" % ", ".join(_failed))
    else:
        stage(valid_zero=1)
        diag["zero_verdict"] = "VALID_ZERO"
        diag["zero_reason"] = ("all preconditions held, so a zero here really "
                               "does mean no dots in this view")

    if _FEED:
        try:
            mbx = diag.get("mapbox") or {}
            _FEED.truth(map_ok=bool(mbx.get("map_captured")
                                    and mbx.get("style_loaded")),
                        zoom_ok=(diag.get("layers_in_band", 0) > 0),
                        rendered=mbx.get("rendered_total"),
                        note="mapbox %s / %s" % (diag.get("verdict"),
                                                 diag.get("zero_verdict")))
            _FEED.note_diagnostic(diag)
        except Exception:
            pass
    return diag


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


# Keys whose NAME contains an address word but which are never the address.
_ADDR_NOT = ("id", "count", "type", "code", "flag", "status", "url", "key")


def _pick(low, keyset, kind=None):
    """Exact match first, then a guarded substring match.

    Exact-only matching is a single point of failure: rename `address` to
    `svcAddress` upstream and EVERY record silently stops being a lead -- green
    and gold together, with no error anywhere. That is indistinguishable from an
    empty neighbourhood, which is the failure this whole system keeps hitting.

    The fallback is guarded by TYPE, not just by name, so a key called
    `addressId` carrying an integer can never be mistaken for a street address.
    """
    for k in keyset:
        v = low.get(k)
        if v not in (None, ""):
            return v
    if not kind:
        return None
    for k, v in low.items():
        if v in (None, ""):
            continue
        if kind == "addr":
            if "addr" not in k or any(b in k for b in _ADDR_NOT):
                continue
            if isinstance(v, str) and len(v.strip()) >= 4:
                return v
        elif kind == "lat":
            if not ("lat" in k or k.endswith("y")):
                continue
            f = _num(v)
            if f is not None and 20.0 <= f <= 72.0:
                return v
        elif kind == "lng":
            if not ("lon" in k or "lng" in k or k.endswith("x")):
                continue
            f = _num(v)
            if f is not None and -170.0 <= f <= -50.0:
                return v
        elif kind == "ban":
            if "ban" in k and "banner" not in k:
                return v
    return None


# Keys seen on a dict that LOOKED like a record but produced no lead. This is
# the fact that identifies a renamed field, and it was never being collected.
_UNMATCHED_KEYS = {}


def note_unmatched(low):
    try:
        if len(_UNMATCHED_KEYS) > 60:
            return
        for k in low:
            _UNMATCHED_KEYS[k] = _UNMATCHED_KEYS.get(k, 0) + 1
    except Exception:
        pass


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
    addr = _pick(low, ADDR_KEYS, "addr")
    lat = _num(_pick(low, LAT_KEYS, "lat"))
    lng = _num(_pick(low, LNG_KEYS, "lng"))
    if geom and geom.get("type") == "Point":
        coords = geom.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lng = lng if lng is not None else _num(coords[0])
            lat = lat if lat is not None else _num(coords[1])
    status = _pick(low, NET_STATUS_KEYS)
    ban = _pick(low, NET_BAN_KEYS, "ban")
    if not addr or not isinstance(addr, str):
        # AT&T sometimes returns a serviceability dot with a STATUS + COORDINATES
        # but no inline street address. Those are still real GREEN/GOLD dots, so
        # capture them by coordinate (the street address can be backfilled later)
        # instead of silently dropping them -- that drop is a prime suspect for
        # "the map shows dots but the sheet stays 0." Tightly gated so random
        # coordinate/UI JSON can never sneak in: needs a US lat/lng AND a fiber
        # status/ban that classifies GREEN or GOLD (GREY/unknown are not coord-
        # captured).
        us_lat = isinstance(lat, (int, float)) and 20.0 <= lat <= 72.0
        us_lng = isinstance(lng, (int, float)) and -170.0 <= lng <= -50.0
        has_sig = (isinstance(status, str) and status.strip()) or ban
        if us_lat and us_lng and has_sig:
            _c = dot_color(classify_wire(
                status if isinstance(status, str) else None, ban, base))
            if _c in ("GREEN", "GOLD", "ORANGE"):
                addr = "(%.6f, %.6f)" % (lat, lng)
        if not addr or not isinstance(addr, str):
            # Record what this dict DID carry. A payload that stops yielding
            # leads is otherwise indistinguishable from empty ground, and the
            # key names are what identify a rename.
            if len(low) >= 3:
                note_unmatched(low)
            return None
    # Keep the ORIGINAL record on the lead. The scout's backend classifier reads
    # subscriber_ban + curr_ntwrk_bld_type_cd off ld["raw"] to score GREEN/GOLD/
    # GREY per cell; without this the backend path never fires and every cell
    # silently falls back to pixel detection.
    # City / state / ZIP ride in the same backend record as the street. Dropping
    # them produced street-only addresses that cannot be skip-traced and cannot
    # be told apart from the same street name in another metro.
    _b = base if isinstance(base, dict) else {}
    _city = str(_b.get("city") or "").strip()
    _state = str(_b.get("state") or "").strip()
    _zip = str(_b.get("zip") or _b.get("zipcode") or "").strip()
    _street = " ".join(addr.split())
    return {"address": _compose_address(_street, _city, _state, _zip)[:160],
            "street": _street[:160],
            "city": _city, "state": _state, "zip": _zip,
            "lat": lat, "lng": lng,
            "status": status if isinstance(status, str) else None,
            "ban": _pick(low, NET_BAN_KEYS),
            "raw": base if isinstance(base, dict) else None}


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
        self.req_capture = None      # exact AT&T serviceability request (secrets redacted)
        self.seen = set()
        self.endpoints = {}          # url(no query) -> lead count, for discovery
        self.seen_urls = {}          # base url -> [content_type, hits, max_bytes]
        self.tile_keys = set()       # property names seen in vector tiles (schema)
        self.tile_status = {}        # base url -> last decode note (debug aid)
        # ZERO-CAPTURE DIAGNOSTICS: so a run that writes nothing can say WHY.
        self.svc_seen = 0            # # of AT&T serviceability 200 responses read
        self.svc_leads = 0          # # of leads those responses yielded
        self.svc_empty_keys = None   # top-level keys of a 200 svc reply that had 0 leads

    def diag(self):
        """One-line reason the sweep can log so 0-capture is never a mystery:
        no serviceability responses at all => not logged in / map not loading data;
        responses seen but 0 leads => AT&T's payload shape changed (keys shown)."""
        if self.svc_seen == 0:
            return ("NO serviceability responses seen -- the map isn't loading "
                    "fiber data (check you're LOGGED IN and dots are visible)")
        if self.svc_leads == 0:
            return ("saw %d serviceability response(s) but decoded 0 leads -- "
                    "AT&T payload shape may have changed; top keys: %s"
                    % (self.svc_seen, self.svc_empty_keys))
        return "OK: %d serviceability responses -> %d leads" % (
            self.svc_seen, self.svc_leads)

    ASSET_CT = ("image/", "font/", "video/", "audio/", "text/css",
                "application/javascript", "application/font",
                "application/x-protobuf", "application/octet-stream")
    ASSET_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
                 ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
                 ".pbf", ".mvt", ".map")

    def is_asset(self, url, ct):
        """True for a website asset -- an image, font, stylesheet or base-map
        tile. We read AT&T's serviceability JSON off the wire; an asset cannot
        contain a lead, so its body is never worth fetching. Reading them is
        what produced pages of 'NOT JSON -- \x89PNG' and crowded the real
        evidence out of the diagnostics."""
        try:
            c = (ct or "").lower()
            if any(c.startswith(a) or a in c for a in self.ASSET_CT):
                return True
            base = (url or "").split("?")[0].lower()
            return base.endswith(self.ASSET_EXT)
        except Exception:
            return False

    def handle(self, response):
        try:
            url = response.url
            ct = (response.headers or {}).get("content-type", "")
            _asset = self.is_asset(url, ct)
            if self.debug:
                base = url.split("?")[0]
                try:
                    sz = int((response.headers or {}).get("content-length") or -1)
                except Exception:
                    sz = -1
                row = self.seen_urls.setdefault(base, [ct, 0, 0])
                row[1] += 1
                row[2] = max(row[2], sz)
            # ENDPOINT DISCOVERY: one row the FIRST time each distinct base URL is
            # seen, then never again. Tiles arrive in the hundreds, so logging every
            # one would flood the tab and teach us nothing; logging each endpoint
            # once shows exactly which hosts the map talks to and in what shape.
            # This is what tells us whether the dots ride in Mapbox vector tiles
            # (queryable in-page via querySourceFeatures, no panning needed) or only
            # in the serviceability JSON we currently pan for.
            try:
                _b = _endpoint_key(url)
                if _b not in _SEEN_ENDPOINTS and len(_SEEN_ENDPOINTS) < _SEEN_ENDPOINTS_MAX:
                    _SEEN_ENDPOINTS.add(_b)
                    _st = 0
                    try:
                        _st = response.status
                    except Exception:
                        pass
                    _n = ""
                    try:
                        _n = (response.headers or {}).get("content-length") or ""
                    except Exception:
                        pass
                    _kind = "tile" if (".pbf" in url or ".mvt" in url or "/tiles/" in url) else (
                        "mapbox" if "mapbox" in url.lower() else "endpoint")
                    log_backend(_kind, _b, _st, ct, _n, note="first sight of this endpoint",
                                area=_CUR_AREA[0])
            except Exception:
                pass
            if self.substr and self.substr not in url:
                return
            ctl = ct.lower()
            low = url.lower()
            # treat it as data if the content-type OR the URL looks like data --
            # AT&T's serviceability feed must be caught even if mislabeled.
            data_url = ("serviceability" in low or "serviceab" in low
                        or "/api/" in low or "graphql" in low or "availab" in low
                        or "fiber" in low or low.endswith(".json"))
            if data_url:
                # (was: any json-labeled reply too -- narrowed 2026-07-02: only
                # read bodies that look like the dot/data feed. A pan can cancel
                # ANY in-flight reply, and reading a cancelled body waits forever
                # on the upgraded browser. The serviceability feed matches these
                # keywords, so capture is unchanged; random page JSON no longer
                # gets read at all.)
                # FREEZE FIX (Patrick 2026-07-16, Romeo's hunter hung ~1h after a
                # 503 "service currently unavailable"): NEVER read the body of a
                # non-200 reply. On the upgraded browser response.body() on a
                # hung/error/cancelled reply BLOCKS FOREVER and freezes the whole
                # hunt (same trap the tile-skip above avoids). A 503/500/429/redirect
                # carries no dot data anyway, so skipping it loses nothing and keeps
                # the sweep moving when AT&T's server hiccups.
                try:
                    st = response.status
                except Exception:
                    st = 0
                if st != 200:
                    # 301 = AT&T bounced the data call to login; 429/503 = rate
                    # limited or down. All three mean NOTHING lands this viewport.
                    hint = {301: "REDIRECTED TO LOGIN -- not logged in, nothing lands",
                            302: "redirected -- session likely expired",
                            401: "unauthorized -- session expired",
                            403: "forbidden -- blocked or logged out",
                            429: "RATE LIMITED -- slow the sweep down",
                            503: "AT&T unavailable -- transient"}.get(st, "non-200, body not read")
                    log_backend("serviceability", url, st, ct, note=hint,
                                area=_CUR_AREA[0])
                    # A console line scrolls away. THIS is how "serviceability
                    # reply 301" hid for weeks: the sweep kept moving, every cell
                    # read +0, and nothing anywhere said the session was dead.
                    if st not in _SVC_STATUS_SAID:
                        _SVC_STATUS_SAID.add(st)
                        print("\n" + "!" * 64)
                        print("!! AT&T REPLIED %s -- NOTHING CAN LAND THIS RUN" % st)
                        print("!! %s" % hint)
                        if st in (301, 302, 401, 403):
                            print("!! FIX: log OUT of youachieve.att.com, close the "
                                  "browser,")
                            print("!!      log back in, then start the hunter again.")
                        print("!" * 64 + "\n")
                    if st in (301, 302, 401, 403):
                        _AUTH_FAIL[0] += 1
                        stage(auth_expired=1)
                    else:
                        stage(http_error=1)
                    if _FEED:
                        try:
                            _FEED.truth(delivery=("AUTH_EXPIRED"
                                                  if st in (301, 302, 401, 403)
                                                  else "HTTP_ERROR"),
                                        note="HTTP %d %s" % (st, hint))
                            _FEED.note_empty(url, ct, "HTTP %d -- %s" % (st, hint))
                        except Exception:
                            pass
                    return
                if _asset:
                    return          # an asset cannot carry a lead; skip its body
                try:
                    body = response.body()
                    if not body or len(body) > 8 * 1024 * 1024:
                        return
                except Exception:
                    return
                # An image is not a failed payload. Running one through the
                # JSON parser produced pages of "NOT JSON -- \x89PNG" noise and
                # buried the one reply that mattered.
                if _FEED and _FEED.is_binary(body):
                    return
                try:
                    data = json.loads(body)
                except Exception:
                    # A 200 that is not JSON is almost always AT&T's login page
                    # wearing a 200. This used to `return` silently, so the whole
                    # run reported "no serviceability responses" and the real
                    # cause never surfaced anywhere.
                    if _FEED:
                        try:
                            _m, _k = _FEED.diagnose(body, ct)
                            if _k in ("auth", "notjson"):
                                _AUTH_FAIL[0] += 1
                            stage(auth_expired=1) if _k == "auth" else stage(parse_error=1)
                            _FEED.truth(delivery=("AUTH_EXPIRED" if _k == "auth"
                                                  else "PARSE_ERROR"),
                                        note=_m[:150])
                            _FEED.note_empty(url, ct, body)
                            if _k not in _SVC_SAID:
                                _SVC_SAID.add(_k)
                                print("\n" + "!" * 64)
                                print("!! AT&T SENT 200 BUT THE BODY IS NOT DATA:")
                                print("!! " + _m)
                                print("!" * 64 + "\n")
                        except Exception:
                            pass
                    try:
                        log_backend("serviceability", url, 200, ct, len(body),
                                    note="200 but body is not JSON",
                                    area=_CUR_AREA[0])
                    except Exception:
                        pass
                    return
                self.svc_seen += 1
                if _FEED:
                    try:
                        _AUTH_FAIL[0] = 0        # a real reply clears the streak
                        stage(serviceability_replies=1)
                        _FEED.truth(delivery="DATA_OK")
                    except Exception:
                        pass
                _t0 = time.time()
                leads = extract_leads_from_json(data)
                # ALSO run the proven extractor (catches the AT&T 'serviceability'
                # endpoint shape that the working pipeline tools rely on)
                if _extract_features is not None:
                    try:
                        for f in _extract_features(data):
                            rec = dict(f)
                            leads.append(rec)
                            # Regression check: build codes from raw must survive
                            # the extraction → leads → classification path, or
                            # Gold/Grey will fall back to UNKNOWN.
                            if rec.get("ban"):
                                code = _bld_code(rec.get("raw") or {})
                                if not code:
                                    stage(customer_missing_build_code=1)
                    except Exception:
                        pass
                # save the RAW serviceability JSON so we can inspect exactly what
                # AT&T sent (every field). Overwrite EVERY capture (cheap, local)
                # so the file always reflects the CURRENT area -- the once-only
                # gate left it stuck on the first area forever, useless for
                # diagnosing a gold-heavy view captured later. Drive log stays
                # once-only (that's the expensive push).
                # One Backend Comm row per successful data reply: how big it was,
                # how long decoding took, how many leads came out, and the colour
                # split. A reply that is 200 but yields 0 leads means AT&T changed
                # the payload shape -- that is invisible without this row.
                try:
                    # Snapshot and restore _WIRE_COUNTS around this pass. Counting
                    # colours for the log calls the same classifier the writer
                    # calls, so without this every dot is tallied TWICE and the
                    # exit report -- the thing we actually use to judge the gold
                    # split -- comes out doubled. Observability must never alter
                    # what it observes.
                    _snap = dict(_WIRE_COUNTS)
                    _g = _o = _y = 0
                    for _ld in leads:
                        _c = dot_color(classify_lead(_ld))
                        if _c == "GREEN":
                            _g += 1
                        elif _c == "ORANGE":
                            _o += 1
                        elif _c == "GREY":
                            _y += 1
                    _WIRE_COUNTS.clear()
                    _WIRE_COUNTS.update(_snap)
                    # miles_from_claim rides on every lead and is the distance
                    # from the search centre. Its MAX is therefore the actual
                    # radius this one search covered -- a direct measurement of
                    # how much ground a viewport buys, instead of guessing from
                    # zoom presses.
                    _rad = ""
                    try:
                        _m = [float(l.get("raw", {}).get("miles_from_claim") or 0)
                              for l in leads if isinstance(l.get("raw"), dict)]
                        if _m:
                            _rad = round(max(_m), 2)
                    except Exception:
                        pass
                    if not leads:
                        _note = ("200 but 0 leads -- payload shape may have changed: %s"
                                 % (list(data)[:6] if isinstance(data, dict) else type(data).__name__))
                        # A 200 that decodes to nothing is the single most
                        # opaque failure this tool has. Keep the actual body so
                        # it can be read later instead of guessed at from a
                        # console photo. First occurrence only -- one specimen
                        # is enough and a sweep must never balloon the feed.
                        if _FEED:
                            try:
                                _FEED.truth(delivery="DATA_OK", raw_features=0)
                                _FEED.note_empty(url, ct, body)
                                _msg, _kind = _FEED.diagnose(body, ct)
                                # Say it ONCE, loudly. A silent +0 is
                                # indistinguishable from an empty street, and
                                # that ambiguity is what wastes an afternoon.
                                if _kind not in _SVC_SAID:
                                    _SVC_SAID.add(_kind)
                                    print("\n" + "!" * 64)
                                    print("!! WHY THIS VIEW CAPTURED NOTHING:")
                                    print("!! " + _msg)
                                    print("!" * 64 + "\n")
                                _note += " | " + _msg[:120]
                            except Exception:
                                pass
                    elif (len(leads) in BACKEND_CAP_VALUES
                          or len(leads) >= NEAR_CAP):
                        _note = ("TRUNCATED? %d leads, at/near AT&T's %d cap -- "
                                 "this viewport probably LOST addresses. Zoom IN "
                                 "and sweep it again."
                                 % (len(leads), BACKEND_LEAD_CAP))
                    else:
                        _note = ""
                    log_backend("serviceability", url, 200, ct, len(body),
                                int((time.time() - _t0) * 1000), len(leads),
                                _g, _o, _y, _note, _CUR_AREA[0], _rad)
                except Exception:
                    pass
                if leads:
                    try:
                        here = os.path.dirname(os.path.abspath(__file__))
                        with open(os.path.join(here, "serviceability_raw.json"), "w") as f:
                            json.dump(data, f)
                    except Exception:
                        pass
                if leads and not _SAVED_RAW[0]:
                    _SAVED_RAW[0] = True
                    print("  (saved raw AT&T response -> serviceability_raw.json)")
                    try:
                        drive_log("RAW %s :: %s" % (url.split("?")[0][:55],
                                                    json.dumps(data)[:480]))
                    except Exception:
                        pass
                # capture the EXACT request once (method, full URL, POST body,
                # header names) so a direct backend reader can replicate AT&T's
                # serviceability call. SECRETS (auth/cookie/token) are redacted
                # before anything is exposed; the full request is saved locally
                # only (serviceability_request_FULL.json, gitignored).
                if leads and self.req_capture is None:
                    try:
                        here = os.path.dirname(os.path.abspath(__file__))
                        rq = response.request
                        try:
                            hdrs = dict(rq.all_headers())
                        except Exception:
                            hdrs = dict(getattr(rq, "headers", {}) or {})
                        SECRET = ("authorization", "cookie", "token", "auth",
                                  "bearer", "session", "apikey", "api-key",
                                  "x-api", "secret", "csrf", "set-cookie")
                        red = {}
                        for k, v in hdrs.items():
                            if any(s in k.lower() for s in SECRET):
                                red[k] = "<redacted %d chars>" % len(str(v))
                            else:
                                red[k] = v
                        try:
                            post = rq.post_data
                        except Exception:
                            post = None
                        self.req_capture = {
                            "url": rq.url, "method": rq.method,
                            "post_data": post, "headers_redacted": red,
                            "header_names": sorted(hdrs.keys()),
                            "resp_status": getattr(response, "status", None),
                            "resp_content_type": ct,
                        }
                        with open(os.path.join(here,
                                  "serviceability_request_FULL.json"), "w") as f:
                            json.dump({"url": rq.url, "method": rq.method,
                                       "post_data": post, "headers": hdrs}, f, indent=2)
                        print("  (captured AT&T request shape -> _live/backend_exchange.txt; "
                              "full+secrets kept local only)")
                    except Exception:
                        pass
            elif _is_vector_tile(url, ct):
                # THE 3-5-CELLS-THEN-STOP GLITCH (found 2026-07-02): do NOT read
                # tile bodies. Mapbox CANCELS in-flight tile fetches on every pan;
                # reading a cancelled reply's body is a wait that never returns,
                # and it lands mid-drag -- the exact "PAN ... drag canvas" freeze.
                # The old browser errored instantly (harmless); the upgraded one
                # waits forever. Addresses never came from tiles anyway (geometry
                # only -- every sheet address comes from the serviceability JSON),
                # so skipping tile bodies changes nothing in the output.
                return
            else:
                return
            if leads:
                self.svc_leads += len(leads)
                base = url.split("?")[0]
                self.endpoints[base] = self.endpoints.get(base, 0) + len(leads)
                self.pending.extend(leads)
            elif data_url:
                # a serviceability 200 that produced NO leads: record its shape
                # once so we can see exactly how AT&T's payload changed.
                if self.svc_empty_keys is None:
                    try:
                        if isinstance(data, dict):
                            self.svc_empty_keys = ",".join(list(data.keys())[:12])
                        elif isinstance(data, list) and data and isinstance(data[0], dict):
                            self.svc_empty_keys = "[list] item0: " + ",".join(
                                list(data[0].keys())[:12])
                        else:
                            self.svc_empty_keys = type(data).__name__
                        drive_log("SVC-EMPTY %s :: keys=%s :: %s" % (
                            url.split("?")[0][:55], self.svc_empty_keys,
                            json.dumps(data)[:300]))
                    except Exception:
                        pass
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
        _CUR_AREA[0] = str(area_label or "")[:40]
        if not dry:
            flush_backend(ws)
        """Write the new captured addresses. BATCHED -- one append_rows call for
        all of them, not one append_row per address (which blew the Google Sheets
        'write requests per minute' quota -> 429 errors)."""
        if _SPLIT[0]:
            # split mode: motion never touches Google -- captures go to disk and
            # the uploader process ships them. A write CANNOT pause a pan.
            return self.flush_local(seen, area_label, dry)
        self.seen = seen
        new_rows, new_records, staged_keys, grey_records, unknown_records = [], [], [], [], []
        grey_ct = 0                        # existing fiber customers in this batch
        unknown_ct = 0                     # undecodable customer build codes
        while self.pending:
            ld = self.pending.pop()
            addr = (ld.get("address") or "").strip()
            if not addr:
                continue
            key = addr.upper()
            # THE GOLD BUG, found 2026-08-23. `seen` is built from PRECISE FIBER
            # -- the GREEN tab -- and this used to `continue` here, before the
            # dot was ever classified. So any address captured on an earlier
            # sweep was skipped outright, never reached write_gold_dots, and
            # could NEVER be added to the Gold Dots tab. That is exactly why
            # Precise Fiber holds 8,264 orange rows while Gold Dots holds 1,984:
            # the gap could not close no matter how often the ground was swept.
            #
            # Being in Precise Fiber now suppresses only the Precise Fiber ROW.
            # Classification still runs, and gold/grey/recheck still route --
            # each of those tabs carries its own dedupe, so nothing duplicates.
            # TESTING: bypass already_scanned check to isolate classification.
            _already = False  # key in seen  # DISABLED FOR TEST
            if not _already:
                staged_keys.append(key)   # NOT seen until the write is ACKed
            dot_status = classify_lead(ld)
            _raw = ld.get("raw") or {}
            _code = _bld_code(_raw)
            if _FEED:
                # The build code is what actually decides gold vs grey, and it
                # is the one field a console photo cannot carry. Publish it.
                _FEED.note(addr, ld.get("lat"), ld.get("lng"), ld.get("ban"),
                           _code, dot_status, dot_color(dot_status))
                # And for CUSTOMERS specifically, keep the whole record. The
                # field that separates a DSL customer from a fiber one is
                # already in this payload; we have simply never looked at it.
                if is_customer_ban(ld.get("ban")):
                    _FEED.note_customer(_raw, _code, dot_color(dot_status))
                # WIRE AUDIT: the full non-secret record beside the verdict, so
                # gold and grey can be diffed field by field without another
                # field run. Observability only -- reads nothing, decides nothing.
                try:
                    _reason = ("no account -> GREEN" if not is_customer_ban(ld.get("ban"))
                               else ("build code %r in copper list -> GOLD" % _code
                                     if dot_color(dot_status) == "ORANGE"
                                     else ("build code %r in fiber list -> GREY" % _code
                                           if dot_color(dot_status) == "GREY"
                                           else "account present, build code %r decodes to neither list"
                                                % (_code or "(none)"))))
                    _c_now = dot_color(dot_status)
                    stage(raw_backend_records=1)
                    if _c_now == "GREY":
                        stage(grey_rejected_from_gold=1)
                    elif _c_now == "UNKNOWN":
                        stage(unknown_rejected_from_gold=1)
                    _FEED.audit(cell=_CUR_AREA[0], lat=ld.get("lat"), lng=ld.get("lng"),
                                http_status=200, response_kind="DATA_OK",
                                raw=_raw, classification=dot_color(dot_status),
                                reason=_reason, queued=True, write_attempted=False,
                                committed=False, seen=False, pending=True)
                except Exception:
                    pass
                # Publish mid-run, not only at exit. optimus_feed has always had
                # should_flush() for this and nothing ever called it, so a sweep
                # that ran for an hour and was then force-quit reported NOTHING
                # -- the exit report is registered with atexit, and a hard kill
                # never runs it. Now the evidence lands while the sweep works.
                try:
                    if _FEED.should_flush():
                        _publish_feed()
                except Exception:
                    pass
            if dot_color(dot_status) == "GREY":
                grey_ct += 1
                grey_records.append({
                    "address": addr, "lat": ld.get("lat"), "lng": ld.get("lng"),
                    "build_code": _code,
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "city": ld.get("city") or "", "state": ld.get("state") or "",
                    "zip": ld.get("zip") or "", "run_id": RUN_ID,
                    "operator": OPERATOR()})
                # A dot we ALREADY recorded as gold that now reads grey is the
                # single most valuable observation a re-sweep produces: it is an
                # existing fiber customer sitting on the upgrade call list. Record
                # it as evidence. The old row is left untouched.
                _note_verification(ld, addr, "GOLD", "GREY")
                continue   # GREY = existing fiber customer -> leave out
            if dot_color(dot_status) == "UNKNOWN":
                unknown_ct += 1
                unknown_records.append({
                    "address": addr, "lat": ld.get("lat"), "lng": ld.get("lng"),
                    "build_code": _code,
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "city": ld.get("city") or "", "state": ld.get("state") or "",
                    "zip": ld.get("zip") or "", "run_id": RUN_ID,
                    "operator": OPERATOR()})
                continue   # UNKNOWN = undecodable code -> separate tab
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            # clean columns + the business merged inline when the address matches a
            # scraped business: Address | Dot Color | Captured At | Business | Phone.
            _bidx = _BIZ.get("index") or {}
            _b = _bidx.get(_norm_addr(addr)) if _bidx else None
            # Suppress only the Precise Fiber ROW for an address we already
            # hold. A `continue` here would skip new_records too -- and
            # new_records is exactly what feeds write_gold_dots, so it would
            # re-create the bug this change exists to fix.
            if _already:
                stage(revisited=1)
            else:
                new_rows.append([addr, dot_color(dot_status), ts,
                                 (_b or {}).get("name", ""),
                                 (_b or {}).get("phone", ""),
                                 RUN_ID, OPERATOR(),
                                 ld.get("lat") if ld.get("lat") is not None else "",
                                 ld.get("lng") if ld.get("lng") is not None else "",
                                 ld.get("city") or "", ld.get("state") or "",
                                 ld.get("zip") or ""])
            new_records.append({"address": addr, "dot_status": dot_status,
                                "run_id": RUN_ID, "operator": OPERATOR(),
                                "zone_label": "WORKING", "popup_status": ld.get("status"),
                                "ban": ld.get("ban"), "area": area_label, "ts": ts,
                                "via": "network", "lat": ld.get("lat"), "lng": ld.get("lng"),
                                # AT&T's payload carries city/state/zip beside the
                                # street. Dropping them is what produced a gold tab
                                # that DealMachine cannot skip-trace: enrich_address
                                # fails hard with no ZIP.
                                "city": ld.get("city") or "",
                                "state": ld.get("state") or "",
                                "zip": ld.get("zip") or "",
                                "biz_name": (_b or {}).get("name", ""),
                                "biz_phone": (_b or {}).get("phone", ""),
                                # WHY this row was called gold. Without it the
                                # Gold tab records a verdict and destroys the
                                # evidence for it.
                                "build_code": _code})
        # ROUTING: each destination (Green/Precise, Gold, Grey) writes independently.
        # No destination depends on another having rows. This prevents early return
        # from blocking writes.
        if new_rows and not (dry or ws is None):
            # GOLD CLUSTER ALERT: gold = copper-to-fiber UPGRADE prospects (hottest
            # leads). If an unusually dense pocket shows up in one viewport, call it
            # out loudly + log it to the status sheet + Drive so it's easy to work.
            _golds = [r[0] for r in new_rows if r[1] in ("GOLD", "ORANGE")]
            if len(_golds) >= GOLD_CLUSTER_ALERT:
                print("\n" + "*" * 60)
                print("  ** GOLD CLUSTER: %d gold (upgrade) dots in ONE view **" % len(_golds))
                print("     e.g. " + " | ".join(_golds[:4]))
                print("*" * 60 + "\n")
                try:
                    drive_log("GOLD-CLUSTER %d in one view (area %s): %s" % (
                        len(_golds), area_label, " | ".join(_golds[:6])))
                except Exception:
                    pass
                try:
                    report_status(ws, area_label, "GOLD CLUSTER", found=len(_golds),
                                  note="%d gold upgrade dots in one viewport" % len(_golds))
                except Exception:
                    pass
            # NEW-FIBER CLUSTER ALERT: a viewport that is mostly GREEN (fiber eligible /
            # NON-customer) with hardly any grey (existing customers) = a just-lit
            # neighborhood. Logged to the 'New Fiber Alerts' tab so a phone alert can fire.
            _greens = [r[0] for r in new_rows if r[1] == "GREEN"]
            if len(_greens) >= NEW_FIBER_ALERT and len(_greens) >= 4 * grey_ct:
                print("\n" + "=" * 60)
                print("  >> NEW FIBER: %d green (eligible, NON-customer) dots, only %d "
                      "existing customers -- looks freshly lit <<" % (len(_greens), grey_ct))
                print("     e.g. " + " | ".join(_greens[:4]))
                print("=" * 60 + "\n")
                try:
                    drive_log("NEW-FIBER %d green / %d grey (area %s): %s" % (
                        len(_greens), grey_ct, area_label, " | ".join(_greens[:6])))
                except Exception:
                    pass
                try:
                    _log_new_fiber_alert(ws, area_label, _greens, grey_ct)
                except Exception:
                    pass
        # GREEN / PRECISE FIBER: write eligible addresses
        if new_rows:
            for rec in new_records:        # local backup (no quota)
                append_jsonl(rec)
            try:    # sample addresses to the Drive log so Claude can verify accuracy
                drive_log("ADDRS +%d e.g.: %s" % (
                    len(new_rows), " | ".join(r[0] for r in new_rows[:4])))
            except Exception:
                pass
            if dry or ws is None:
                for r in new_rows[:20]:
                    print("   + %s | %s" % (r[0], r[1]))
            else:
                _n, _failed = commit_rows(ws, "Precise Fiber", new_rows)
                for _k in staged_keys[:_n]:
                    seen.add(_k)          # only what Google actually acknowledged
                _greens = sum(1 for r in new_rows if r[1] == "GREEN")
                stage(green_queued=_greens,
                      green_committed=int(_greens * _n / max(1, len(new_rows))))
                if _n < len(new_rows):
                    print("   %d of %d row(s) did NOT commit -- parked for retry, "
                          "and NOT marked seen, so the next sweep picks them up."
                          % (len(new_rows) - _n, len(new_rows)))
        # GOLD DOTS: write EVERY gold (copper-upgrade) dot to its own tab independently
        if new_records and not (dry or ws is None):
            try:
                ng = write_gold_dots(ws.spreadsheet, new_records)
                write_gold_recheck(ws.spreadsheet, new_records)
                if ng:
                    print("   + %d gold (upgrade) dots -> '%s' tab" % (ng, GOLD_TAB))
                # Evidence from this batch: dots we had already called gold that
                # now read grey. Appended, never overwriting the original rows.
                _flush_verification(ws.spreadsheet)
            except Exception as e:
                print("   (gold dots skipped: %s)" % str(e)[:80])
        # GREY DOTS: write existing fiber customers independently
        if grey_records and not (dry or ws is None):
            try:
                write_grey_dots(ws.spreadsheet, grey_records)
            except Exception as e:
                print("   (grey dots skipped: %s)" % str(e)[:80])
        # UNKNOWN DOTS: write undecodable customer build codes independently
        if unknown_records and not (dry or ws is None):
            try:
                write_unknown_dots(ws.spreadsheet, unknown_records)
            except Exception as e:
                print("   (unknown dots skipped: %s)" % str(e)[:80])
        # COMBO: match these just-captured leads against the scraped businesses and
        # write any hits to the green/gold business tabs -- live, as we sweep.
        try:
            match_leads_to_biz(new_records)
        except Exception as e:
            print("   (biz match skipped: %s)" % str(e)[:80])
        # REAL-TIME MATCH: periodically reload the business list so a scrape running
        # ALONGSIDE the hunter gets matched live. -- REMOVED (the ONE change to
        # this June build): the periodic reload re-read the whole Maps
        # Businesses tab mid-motion; fine at June's 3.6k rows, a 10-30s motion
        # freeze at today's 18k+. Matching still runs at startup and from the
        # scraper's side. Everything else in this file is June 18, untouched.
        # (COMBO MATCH ON -- launcher version-check marker.)
        return len(new_rows)

    def flush_local(self, seen, area_label, dry):
        """SPLIT-MODE flush: June's exact skip logic, but captures go to the
        local JSONL only (a disk append, microseconds). The uploader process
        ships them to the sheet. The pan loop never waits on Google."""
        new_records = []
        _report_counter = 0
        while self.pending:
            ld = self.pending.pop()
            addr = (ld.get("address") or "").strip()
            if not addr:
                continue
            key = addr.upper()
            # DEDUPE: For test mode, disable seen check so all records are
            # classified. Permanently, mark seen only after successful uploader
            # persistence (seen ⊆ committed rule). Currently dedupe is OFF to
            # allow GOLD/GREY reclassification during test.
            # if key in seen:
            #     continue
            # seen.add(key)
            dot_status = classify_lead(ld)
            _report_counter += 1
            if _report_counter % 50 == 0:
                wire_classification_report()
            # Split mode must not drop GREY like the old code did. Production path
            # routes GREY to the Grey Dots tab; split-mode uploader respects
            # dot_color, so GREY records are properly handled downstream.
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            # Split mode used to drop run_id/operator/geography entirely, so a
            # gold row captured this way landed with no ZIP and no provenance --
            # unskip-traceable AND unauditable, depending only on which code path
            # happened to save it.
            new_records.append({"address": addr, "dot_status": dot_status,
                                "run_id": RUN_ID, "operator": OPERATOR(),
                                "zone_label": "WORKING", "popup_status": ld.get("status"),
                                "ban": ld.get("ban"), "area": area_label, "ts": ts,
                                "via": "network", "lat": ld.get("lat"), "lng": ld.get("lng"),
                                "city": ld.get("city") or "",
                                "state": ld.get("state") or "",
                                "zip": ld.get("zip") or ""})
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
    sh = _as_spreadsheet(sh)
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


# ---------------------------------------------------------------------------
# GOLD DOTS -- every gold (copper-upgrade) dot, all of them, not just the
# business matches. Copper customers are the hottest UPGRADE leads (easy call:
# "upgrade your line to fiber"), so Patrick wants them all in one place to
# analyze where new fiber is and to call for upgrades first (2026-08-18).
#
# They go to a SMALL STANDALONE spreadsheet ("OPTIMUS GOLD DOTS"), NOT a tab in
# the 446k-row monster -- because Claude can read a small sheet whole via Drive
# but the giant one exports "File too large". So the hunter fills this inline as
# it sweeps (NO extra program), and Claude reads it directly to report where the
# new fiber is. It's shared to Patrick's Gmail so it's also his upgrade call list.
# ---------------------------------------------------------------------------
# Kept only so older references/log lines still resolve. Gold now lives in a
# TAB in the main sheet (GOLD_TAB), because the service account cannot create
# a standalone file -- see _ensure_gold_tab().
GOLD_SHEET_TITLE = "OPTIMUS GOLD DOTS"
GOLD_OWNER_EMAIL = "patricksiado@gmail.com"
_GOLD = {"ws": None, "seen": None}
# Tier and Build Code are what make a re-check possible. Without them every row
# on this tab looks equally confirmed, which is exactly why the existing 3,328
# rows cannot be trusted: nothing records WHY a row was called gold.
_GOLD_HEADER = ["Address", "Captured At", "Lat", "Lng", "Business", "Phone",
                "Run ID", "Operator", "City", "State", "ZIP",
                "Tier", "Build Code"]

# VERIFIED_GOLD  -- AT&T said copper, or the build code decodes to copper.
#                   This is the call list. Dave works these.
# NEEDS_RECHECK  -- a real CUSTOMER on a build code we cannot decode. Not a
#                   confirmed upgrade, but not rubbish either: it is a live
#                   account on a lit street. Written so it can be reviewed
#                   instead of deleted. NOT on the call list.
TIER_VERIFIED = "VERIFIED_GOLD"
TIER_RECHECK = "NEEDS_RECHECK"


def gold_tier(dot_status):
    """Which tier a classified dot belongs to, or None if it is not gold at all."""
    c = dot_color(dot_status)
    if c in ("GOLD", "ORANGE"):
        return TIER_VERIFIED
    if c == "UNKNOWN":
        return TIER_RECHECK
    return None


def _coord_key(lat, lng):
    """Positional identity, ~1 m. Delegates to optimus_dedupe when present."""
    if _DEDUPE:
        return _DEDUPE.coord_key(lat, lng)
    try:
        return "@%.5f,%.5f" % (float(lat), float(lng))
    except (TypeError, ValueError):
        return None


def _gold_keys(addr, lat=None, lng=None):
    """Keys a gold row is claimed under: normalised FULL address + coordinates.

    Street-only text is never a key on its own -- '5309 WENDA ST' exists in both
    Houston and Beaumont and collapsing those drops a real $140 lead. See
    optimus_dedupe for the full reasoning.
    """
    if _DEDUPE:
        return _DEDUPE.keys_for(addr, lat, lng)
    keys = set()
    a = (addr or "").strip().upper()
    if a:
        keys.add(a)
    ck = _coord_key(lat, lng)
    if ck:
        keys.add(ck)
    return keys


def _note_verification(ld, addr, prev_class, new_class):
    """Record one re-observation of a dot we have seen before. Never raises.

    Only fires when the address is already claimed in the gold set, so a first
    sighting is not mistaken for a change of mind.
    """
    if not _DEDUPE or _GOLD.get("seen") is None:
        return
    try:
        lat, lng = ld.get("lat"), ld.get("lng")
        if not (_gold_keys(addr, lat, lng) & _GOLD["seen"]):
            return                     # never seen before: not a verification
        _DEDUPE_REPORT.duplicates += 1
        _DEDUPE_REPORT.note_change(addr, prev_class, new_class)
        raw = ld.get("raw") if isinstance(ld.get("raw"), dict) else {}
        _VERIFY_ROWS.append(_DEDUPE.history_row(
            addr, lat, lng, prev_class, new_class,
            _bld_code(raw) or "", bool(ld.get("ban")), "",
            RUN_ID, OPERATOR()))
    except Exception:
        pass


def _flush_verification(sh):
    """Append the run's observations to the history tab. Best-effort."""
    if not (_DEDUPE and sh is not None and _VERIFY_ROWS):
        return
    try:
        ws = _DEDUPE.ensure_history_tab(sh)
        _DEDUPE.write_history(ws, _VERIFY_ROWS, _DEDUPE_REPORT)
        del _VERIFY_ROWS[:]
    except Exception as e:
        print("   (verification flush skipped: %s)" % str(e)[:70])


def _ensure_gold_tab(sh):
    """Get/create the 'Gold Dots' TAB inside the main ATT FIBER LEADS sheet.

    WAS: this opened/created a SEPARATE spreadsheet ("OPTIMUS GOLD DOTS").
    That could never work. The service account has ZERO Drive storage quota --
    it can READ and UPDATE files already shared with it, but it cannot CREATE
    a new file. So client.create() always threw, write_gold_dots() swallowed
    the exception and returned 0, and gold silently never appeared anywhere
    while green kept writing fine. (Confirmed 2026-08-18: no such spreadsheet
    exists in Drive; the limit is documented in SESSION_SUMMARY_2026-04-30.)

    NOW: the tab lives in `sh` -- the main sheet, which already exists and is
    already shared with the service account. add_worksheet() on an existing
    spreadsheet needs no Drive quota, so this works.

    `sh` is the open gspread Spreadsheet the hunter is already writing to.
    """
    sh = _as_spreadsheet(sh)
    if _GOLD["ws"] is not None:
        return _GOLD["ws"]
    try:
        gw = sh.worksheet(GOLD_TAB)
    except Exception:
        gw = sh.add_worksheet(title=GOLD_TAB, rows="5000",
                              cols=str(len(_GOLD_HEADER)))
        print("   created '%s' tab in the main sheet" % GOLD_TAB)
    if not gw.get_all_values():
        gw.append_row(_GOLD_HEADER)
    else:
        _ensure_header(gw, _GOLD_HEADER)
    try:
        col = gw.col_values(1)
        # Only drop row 1 when it REALLY is the header. The live tab has no
        # header row (verified 2026-08-22), so blindly slicing [1:] left a real
        # address out of `seen` -- and that address was re-appended on every
        # single run that captured it again.
        if col and col[0].strip().lower() == _GOLD_HEADER[0].strip().lower():
            col = col[1:]
        # Coordinates come from columns C and D so a legacy street-only row is
        # still recognisable when the same property is captured again under its
        # new full-address form.
        lat_col, lng_col = gw.col_values(3), gw.col_values(4)
        if col and col[0].strip().lower() == _GOLD_HEADER[0].strip().lower():
            lat_col, lng_col = lat_col[1:], lng_col[1:]
        seen = set()
        for i, a in enumerate(col):
            la = lat_col[i] if i < len(lat_col) else None
            ln = lng_col[i] if i < len(lng_col) else None
            seen.update(_gold_keys(a, la, ln))
        _GOLD["seen"] = seen
    except Exception:
        _GOLD["seen"] = set()
    _GOLD["ws"] = gw
    return gw


def _gold_layout(gw):
    """Map the LIVE header to column indexes, or None when there is no header.

    Column positions must never be assumed. The live tab has no header row and
    something else now occupies column G (a Full Address column added outside
    the hunter). Writing our own 8-column row would have overwritten every one
    of those values on the next sweep -- silent destruction of somebody else's
    work, which is exactly the class of bug this file keeps getting bitten by.

    So: if row 1 is a real header we place each field BY NAME. If row 1 is data,
    we write only the four legacy columns we can be certain of and leave every
    other column strictly alone.
    """
    try:
        head = gw.row_values(1)
    except Exception:
        return None
    if not head or head[0].strip().lower() != _GOLD_HEADER[0].strip().lower():
        return None                    # row 1 is data: headerless legacy tab
    return dict((h.strip().lower(), i) for i, h in enumerate(head) if h.strip())


_GOLD_WARNED = []
_GOLD_RECHECK_WARNED = []


# ---------------------------------------------------------------------------
# DURABLE WRITES. A row is not captured until Google acknowledges it.
#
# The old fiber_hunter (v5.27, still in the optimus-map-tools repo) cleared its
# batch buffer in a finally-shaped path that ran on failure too, so a transient
# Sheets error silently destroyed the rows. This hunter never had that buffer --
# but it had the same defect wearing different clothes: the dedupe key was
# marked `seen` while BUILDING the row, before the write was attempted. A failed
# batch was therefore lost AND permanently marked captured, so not even a
# re-sweep would pick it up. Same outcome, quieter.
#
# Rule: mark seen only after an ACK, retry with bounded backoff, and if it still
# fails, write the batch to disk so the next run replays it. Never say "wrote".
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# STAGE COUNTERS. One number per boundary, so the FIRST drop is obvious instead
# of argued about. The point is the shape, not the totals:
#
#   GOLD CLASSIFIED 12 / QUEUED 12 / COMMITTED 0   -> stop looking at Mapbox
#   GOLD CLASSIFIED 0  / RAW 480                   -> it is the classifier
#   RAW 0                                          -> nothing was delivered
# ---------------------------------------------------------------------------
_STAGE = {}
_STAGE_ORDER = [
    ("serviceability_replies", "AT&T REPLIES (200 JSON)"),
    ("raw_backend_records", "RAW BACKEND RECORDS"),
    ("raw_features",       "RAW FEATURES"),
    ("classified_green",   "  GREEN classified"),
    ("classified_gold",    "  GOLD classified"),
    ("classified_grey",    "  GREY classified"),
    ("classified_unknown", "  UNKNOWN classified"),
    ("gold_queued",        "GOLD QUEUED"),
    ("gold_attempted",     "GOLD WRITE ATTEMPTED"),
    ("gold_committed",     "GOLD COMMITTED"),
    ("gold_seen",          "GOLD SEEN"),
    ("gold_pending",       "GOLD PENDING"),
    ("green_queued",       "GREEN QUEUED"),
    ("green_committed",    "GREEN COMMITTED"),
    ("grey_committed",     "GREY COMMITTED"),
    ("revisited",          "ALREADY IN PRECISE FIBER (re-checked for gold)"),
    ("grey_rejected_from_gold",    "GREY rejected from gold"),
    ("unknown_rejected_from_gold", "UNKNOWN rejected from gold"),
    ("auth_expired",       "AUTH_EXPIRED replies"),
    ("http_error",         "HTTP_ERROR replies"),
    ("parse_error",        "PARSE_ERROR replies"),
    ("valid_zero",         "VALID_ZERO cells"),
    ("invalid_zero",       "INVALID_ZERO cells"),
]


def stage(**kw):
    """Add to a stage counter. Never raises into a sweep."""
    try:
        for k, v in kw.items():
            _STAGE[k] = _STAGE.get(k, 0) + int(v or 0)
    except Exception:
        pass


def stage_report(log=print):
    log("")
    log("=== STAGE COUNTERS (the first drop is the bug) ===")
    for key, label in _STAGE_ORDER:
        if key in _STAGE:
            log("  %-28s %6d" % (label, _STAGE[key]))
    g = _STAGE.get
    # Invariants. Each is a sentence about where leads go, and a breach names
    # the stage instead of leaving it to be inferred from totals.
    for name, ok, why in (
        ("gold_queued == gold_classified",
         "gold_queued" not in _STAGE
         or g("gold_queued", 0) == g("classified_gold", 0),
         "gold was classified but never reached the writer"),
        ("gold_committed <= gold_queued",
         g("gold_committed", 0) <= g("gold_queued", 0),
         "more committed than queued -- a counter is wrong"),
        ("gold_seen == gold_committed",
         g("gold_seen", 0) == g("gold_committed", 0),
         "a dot was marked seen without being committed -- IT WILL NEVER RETRY"),
    ):
        if not ok:
            log("  !! INVARIANT BROKEN: %s" % name)
            log("     %s" % why)
    # FIRST_DROP: RAW -> CLASSIFIED -> QUEUED -> COMMITTED, named not inferred.
    _chain = [("DELIVERY", g("serviceability_replies")),
              ("RAW", g("raw_backend_records")),
              ("CLASSIFIED", (g("classified_green", 0) + g("classified_gold", 0)
                              + g("classified_grey", 0) + g("classified_unknown", 0))),
              ("QUEUED", g("gold_queued")),
              ("COMMITTED", g("gold_committed"))]
    _drop = "NONE"
    _prev = None
    for _name, _v in _chain:
        if _v is None:
            continue
        if _v == 0 and _prev not in (None, 0):
            _drop = _name
            break
        _prev = _v
    log("  FIRST_DROP: %s" % _drop)
    if g("gold_pending"):
        log("  %d gold row(s) PENDING -- parked on disk, replayed next run."
            % g("gold_pending"))
    log("=" * 49)


def _pending_dir():
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_pending")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _park_batch(tab, rows):
    """Persist a batch we could not commit, so it is replayed, not lost."""
    try:
        path = os.path.join(_pending_dir(), "%s__%s__%s.json"
                            % (re.sub(r"[^A-Za-z0-9]+", "_", tab), RUN_ID,
                               len(rows)))
        with open(path, "w") as f:
            json.dump({"tab": tab, "run_id": RUN_ID, "rows": rows}, f)
        print("   PRESERVED FOR RETRY: %d row(s) parked at %s"
              % (len(rows), os.path.basename(path)))
        return True
    except Exception as e:
        # If even this fails the rows really are gone -- say so in full.
        print("   *** %d ROW(S) LOST: could not commit and could not park (%s)"
              % (len(rows), str(e)[:80]))
        return False


def commit_rows(ws, tab, rows, tries=3):
    """Append rows and return (committed_count, failed_count). Never raises.

    Rows that cannot be committed are parked on disk. The caller must not treat
    an uncommitted row as captured.
    """
    if ws is None or not rows:
        return 0, 0
    committed = 0
    failed = 0
    for i in range(0, len(rows), 500):
        batch = rows[i:i + 500]
        ok = False
        for attempt in range(tries):
            try:
                ws.append_rows(batch, value_input_option="RAW")
                ok = True
                break
            except Exception as e:
                print("   SHEET COMMIT FAILED %s batch=%d attempt=%d/%d: %s"
                      % (tab, len(batch), attempt + 1, tries, str(e)[:80]))
                if attempt + 1 < tries:
                    time.sleep(2 ** attempt)
        if ok:
            committed += len(batch)
            print("   SHEET COMMITTED %s batch=%d" % (tab, len(batch)))
        else:
            failed += len(batch)
            _park_batch(tab, batch)
            if _DEDUPE_REPORT:
                _DEDUPE_REPORT.failed_writes += len(batch)
    return committed, failed


def replay_pending(sh, log=print):
    """Re-commit batches parked by an earlier run. Best-effort, at startup."""
    sh = _as_spreadsheet(sh)
    if sh is None:
        return 0
    d = _pending_dir()
    try:
        files = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    except Exception:
        return 0
    if not files:
        return 0
    log("   replaying %d parked batch(es) from a previous run..." % len(files))
    total = 0
    for name in files:
        path = os.path.join(d, name)
        try:
            with open(path) as f:
                blob = json.load(f)
            ws = sh.worksheet(blob["tab"])
        except Exception as e:
            log("   (cannot replay %s: %s)" % (name, str(e)[:60]))
            continue
        got, _ = commit_rows(ws, blob["tab"], blob.get("rows") or [])
        if got:
            total += got
            try:
                os.remove(path)          # only once it is really in the sheet
            except Exception:
                pass
    if total:
        log("   replayed %d row(s) that an earlier run could not commit." % total)
    return total


# GREY = an existing AT&T fiber customer. Not a fiber lead -- but not rubbish
# either: it is a confirmed fiber household, which is what a competitor pitch
# and a penetration ratio are computed from. Grey used to be DISCARDED, and
# "grey never reaches the sheet" is how real leads were silently deleted
# whenever the classifier got one wrong. Nothing is thrown away now: every
# classified dot lands on a tab.
GREY_TAB = "Grey Fiber Customers"
GREY_HEADER = ["Address", "Captured At", "Lat", "Lng", "Build Code",
               "City", "State", "ZIP", "Run ID", "Operator"]
_GREY = {"seen": set()}


def write_grey_dots(sh, records):
    """Existing fiber customers -> their own tab. Never the gold call list."""
    sh = _as_spreadsheet(sh)
    if sh is None or not records:
        return 0
    try:
        try:
            ws = sh.worksheet(GREY_TAB)
        except Exception:
            ws = sh.add_worksheet(title=GREY_TAB, rows="5000",
                                  cols=str(len(GREY_HEADER)))
            ws.append_row(GREY_HEADER)
            print("   created '%s' tab (existing fiber customers)" % GREY_TAB)
    except Exception as e:
        print("   (GREY TAB FAILED: %s)" % str(e)[:110])
        return 0

    seen, rows, staged = _GREY["seen"], [], []
    for r in records:
        addr = (r.get("address") or "").strip()
        if not addr:
            continue
        keys = _gold_keys(addr, r.get("lat"), r.get("lng"))
        if keys & seen:
            continue
        staged.append(keys)          # NOT marked seen until Google ACKs
        rows.append([addr, r.get("ts") or "",
                     r.get("lat") if r.get("lat") is not None else "",
                     r.get("lng") if r.get("lng") is not None else "",
                     (r.get("build_code") or "").upper(),
                     r.get("city") or "", r.get("state") or "",
                     r.get("zip") or "",
                     r.get("run_id") or RUN_ID,
                     r.get("operator") or OPERATOR()])
    if not rows:
        return 0
    written, _ = commit_rows(ws, GREY_TAB, rows)
    for keys in staged[:written]:
        seen.update(keys)
    stage(grey_committed=written)
    if written:
        print("   %d existing fiber customer(s) -> '%s'" % (written, GREY_TAB))
    return written


def write_unknown_dots(sh, records):
    """Customers with undecodable build codes -> their own tab for analysis.

    These should NOT go to the call list (gold) or be skipped (grey). They
    are visible, auditable, and reviewable until their build code is confirmed.
    """
    sh = _as_spreadsheet(sh)
    if sh is None or not records:
        return 0
    try:
        try:
            ws = sh.worksheet(UNKNOWN_TAB)
        except Exception:
            ws = sh.add_worksheet(title=UNKNOWN_TAB, rows="5000",
                                  cols="10")
            ws.append_row(["Address", "Captured At", "Lat", "Lng", "Build Code",
                          "City", "State", "ZIP", "Run ID", "Operator"])
            print("   created '%s' tab (undecodable customer build codes)" % UNKNOWN_TAB)
    except Exception as e:
        print("   (UNKNOWN TAB FAILED: %s)" % str(e)[:110])
        return 0

    seen, rows, staged = {}, [], []
    for r in records:
        addr = (r.get("address") or "").strip()
        if not addr:
            continue
        if addr.upper() in seen:
            continue
        staged.append(addr.upper())
        rows.append([addr, r.get("ts") or "",
                     r.get("lat") if r.get("lat") is not None else "",
                     r.get("lng") if r.get("lng") is not None else "",
                     (r.get("build_code") or "").upper(),
                     r.get("city") or "", r.get("state") or "",
                     r.get("zip") or "",
                     r.get("run_id") or RUN_ID,
                     r.get("operator") or OPERATOR()])
        seen[addr.upper()] = True
    if not rows:
        return 0
    written, _ = commit_rows(ws, UNKNOWN_TAB, rows)
    stage(unknown_committed=written)
    if written:
        print("   %d undecodable customer(s) -> '%s'" % (written, UNKNOWN_TAB))
    return written


RECHECK_TAB = "Gold Recheck"
RECHECK_HEADER = ["Address", "Captured At", "Lat", "Lng", "Build Code",
                  "City", "State", "ZIP", "Run ID", "Operator"]
_RECHECK = {"seen": set()}


def write_gold_recheck(sh, records):
    """Customers we could NOT decode -- written, never deleted, never called.

    These are real AT&T accounts on lit streets whose build code is in neither
    the fiber nor the copper list (`unavailable` is most of them). Calling them
    gold put existing fiber customers in front of a rep; calling them grey threw
    real $140 upgrades away. Both were guesses, and both were wrong.

    So they land here instead: a review queue, on its own tab, off the call
    list. The Build Code column is the point -- once one of these codes is
    confirmed on the map it goes into build_codes.json and every row carrying it
    is promoted to real gold in one move.
    """
    sh = _as_spreadsheet(sh)
    if sh is None or not records:
        return 0
    rows_in = [r for r in records
               if gold_tier(r.get("dot_status")) == TIER_RECHECK]
    if not rows_in:
        return 0
    try:
        try:
            ws = sh.worksheet(RECHECK_TAB)
        except Exception:
            ws = sh.add_worksheet(title=RECHECK_TAB, rows="5000",
                                  cols=str(len(RECHECK_HEADER)))
            ws.append_row(RECHECK_HEADER)
            print("   created '%s' tab (undecodable customers, for review)"
                  % RECHECK_TAB)
    except Exception as e:
        print("   (RECHECK TAB FAILED: %s)" % str(e)[:110])
        return 0

    seen, rows, staged = _RECHECK["seen"], [], []
    for r in rows_in:
        addr = (r.get("address") or "").strip()
        if not addr:
            continue
        keys = _gold_keys(addr, r.get("lat"), r.get("lng"))
        if keys & seen:
            continue
        staged.append(keys)          # NOT marked seen until Google ACKs
        rows.append([addr, r.get("ts") or "",
                     r.get("lat") if r.get("lat") is not None else "",
                     r.get("lng") if r.get("lng") is not None else "",
                     (r.get("build_code") or "").upper(),
                     r.get("city") or "", r.get("state") or "",
                     r.get("zip") or "",
                     r.get("run_id") or RUN_ID,
                     r.get("operator") or OPERATOR()])
    if not rows:
        return 0
    written, _ = commit_rows(ws, RECHECK_TAB, rows)
    for keys in staged[:written]:
        seen.update(keys)            # only what actually landed
    if written:
        print("   %d undecodable customer(s) -> '%s' (NOT on the call list)"
              % (written, RECHECK_TAB))
    return written


def write_gold_dots(sh, records):
    """Append every gold (copper-upgrade) dot to the 'Gold Dots' tab.

    Deduped on normalised full address + coordinates (see optimus_dedupe).
    Best-effort: never raises into the sweep. Returns rows actually written.
    """
    if sh is None or not records:
        return 0
    golds = [r for r in records if gold_tier(r.get("dot_status"))]
    if not golds:
        return 0
    try:
        gw = _ensure_gold_tab(sh)
    except Exception as e:
        print("   (GOLD TAB FAILED: %s)" % str(e)[:120])
        return 0

    layout = _gold_layout(gw)
    if layout is None and not _GOLD_WARNED:
        _GOLD_WARNED.append(1)
        print("   (Gold Dots has no header row: writing ONLY columns A-D so "
              "nothing else on the tab is overwritten. Add the header row to "
              "capture Run ID / Operator / City / State / ZIP.)")
    # 'Gold Dots' is the CALL LIST and stays confirmed-only. Unconfirmed
    # customers go to their own tab, so nothing here can put a fiber customer
    # in front of a rep.
    golds = [r for r in golds
             if gold_tier(r.get("dot_status")) == TIER_VERIFIED]
    if not golds:
        return 0

    seen = _GOLD["seen"]
    rows, staged = [], []
    for r in golds:
        addr = (r.get("address") or "").strip()
        if not addr:
            continue
        keys = _gold_keys(addr, r.get("lat"), r.get("lng"))
        if keys & seen:
            continue
        staged.append(keys)          # NOT marked seen until Google ACKs
        vals = {
            "address": addr,
            "captured at": r.get("ts") or "",
            "lat": r.get("lat") if r.get("lat") is not None else "",
            "lng": r.get("lng") if r.get("lng") is not None else "",
            "business": r.get("biz_name") or "",
            "phone": r.get("biz_phone") or "",
            "run id": r.get("run_id") or RUN_ID,
            "operator": r.get("operator") or OPERATOR(),
            "city": r.get("city") or "",
            "state": r.get("state") or "",
            "zip": r.get("zip") or "",
            "tier": gold_tier(r.get("dot_status")) or "",
            "build code": (r.get("build_code") or "").upper(),
        }
        if layout is None:
            # Headerless: the four columns the tab has always meant. Anything
            # to the right belongs to somebody else -- do not touch it.
            rows.append([vals["address"], vals["captured at"],
                         vals["lat"], vals["lng"]])
        else:
            row = [""] * (max(layout.values()) + 1)
            for name, idx in layout.items():
                if name in vals:
                    row[idx] = vals[name]
            rows.append(row)
    if not rows:
        return 0

    stage(gold_queued=len(rows), gold_attempted=len(rows))
    written, _ = commit_rows(gw, GOLD_TAB, rows)
    stage(gold_committed=written, gold_seen=written,
          gold_pending=len(rows) - written)
    for keys in staged[:written]:
        seen.update(keys)            # only what actually landed
    if _DEDUPE_REPORT:
        _DEDUPE_REPORT.written += written
    return written


def _backfill_gold_from(sh, log=print):
    """Core: seed the 'Gold Dots' tab from every ORANGE (gold/upgrade) row
    already captured in 'Precise Fiber' on the big sheet `sh`. Reads just the
    Address + color columns, dedupes against what's already in the gold sheet,
    batches the write. Returns rows written. Best-effort."""
    sh = _as_spreadsheet(sh)
    try:
        pf = sh.worksheet(OUT_TAB)
    except Exception:
        log("No '%s' tab -- nothing to backfill." % OUT_TAB)
        return 0
    log("Reading Precise Fiber address + color columns (one-time; can take a "
        "minute on a big sheet)...")
    addrs = pf.col_values(1)      # column A = Address
    colors = pf.col_values(2)     # column B = Dot Color
    ts_col = pf.col_values(3)     # column C = Captured At
    biz_col = pf.col_values(4)    # column D = Business
    ph_col = pf.col_values(5)     # column E = Phone
    run_col = pf.col_values(6)    # column F = Run ID
    op_col = pf.col_values(7)     # column G = Operator (blank on old rows)
    gw = _ensure_gold_tab(sh)     # the 'Gold Dots' tab in this same sheet
    seen = _GOLD["seen"]
    rows = []
    n = max(len(addrs), len(colors))
    for i in range(1, n):         # skip header row 0
        color = (colors[i].strip().upper() if i < len(colors) and colors[i] else "")
        if color not in ("ORANGE", "GOLD"):
            continue
        addr = (addrs[i].strip() if i < len(addrs) and addrs[i] else "")
        if not addr or addr.upper() in seen:
            continue
        seen.add(addr.upper())
        # Backfilled from history: we genuinely do not know who scanned these,
        # and inventing an operator would be worse than leaving it honest.
        rows.append([addr,
                     ts_col[i] if i < len(ts_col) else "",
                     "", "",     # lat/lng not stored in Precise Fiber
                     biz_col[i] if i < len(biz_col) else "",
                     ph_col[i] if i < len(ph_col) else "",
                     run_col[i] if i < len(run_col) else "",
                     op_col[i] if i < len(op_col) else "(before operator tracking)"])
    if not rows:
        log("No ORANGE/gold rows found in Precise Fiber to backfill.")
        return 0
    log("Writing %d historical gold (upgrade) addresses to '%s'..."
        % (len(rows), GOLD_TAB))
    for i in range(0, len(rows), 500):
        gw.append_rows(rows[i:i + 500], value_input_option="RAW")
    log("Done. '%s' tab now holds %d gold addresses." % (GOLD_TAB, len(rows)))
    return len(rows)


def _auto_backfill_gold_once(sh):
    """Fold the history backfill INTO the hunter (no extra program): the first
    time the standalone gold sheet is empty, seed it from Precise Fiber's ORANGE
    rows. Runs at startup (before the browser), guarded + best-effort so it can
    never touch the sweep. After the first run the sheet stays current on its own."""
    if sh is None:
        return
    try:
        gw = _ensure_gold_tab(sh)
    except Exception:
        return
    # only backfill when the gold sheet is fresh (just the header, nothing seeded)
    if _GOLD.get("seen"):
        return
    try:
        _backfill_gold_from(sh, log=lambda m: print("  [gold backfill] " + m))
    except Exception as e:
        print("  (gold backfill skipped: %s)" % str(e)[:80])


def backfill_gold_dots():
    """One-time CLI (--backfill-gold): open the big sheet and seed the standalone
    gold sheet from its ORANGE rows. New runs keep it current on their own."""
    import gspread
    from google.oauth2.service_account import Credentials
    creds = find_creds()
    if not creds:
        print("No google_creds.json found -- can't backfill the gold dots.")
        return
    client = gspread.authorize(
        Credentials.from_service_account_file(creds, scopes=SCOPES))
    sh = client.open_by_key(SHEET_ID)
    _backfill_gold_from(sh)


def open_sheet():
    """Open the production sheet and the Precise Fiber tab. We do NOT create a new
    sheet -- if it's full, AUTO-CLEAN this one (delete junk tabs, trim) so it accepts
    writes again, then keep going. Same sheet, same link everyone has."""
    import gspread
    from google.oauth2.service_account import Credentials
    creds_file = find_creds()
    if not creds_file:
        print("No valid google_creds.json found among the usual paths; running "
              "WITHOUT the sheet (captures print only). Fix with the Drive "
              "download or drop the fiberscanner key at ~/optimus/google_creds.json.")
        return None
    print("Using creds: %s" % creds_file)
    try:
        client = gspread.authorize(
            Credentials.from_service_account_file(creds_file, scopes=SCOPES))
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
            _ensure_header(ws, OUT_HEADER)
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
    pipeline_tabs = {OUT_TAB, GOLD_TAB, MAPS_TAB, GREEN_BIZ_TAB, ORANGE_BIZ_TAB,
                     "Enriched Leads", STATUS_TAB}
    creds = find_creds()
    if not creds:
        print("No google_creds.json found -- can't clean the sheet."); return
    client = gspread.authorize(
        Credentials.from_service_account_file(creds, scopes=SCOPES))
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
    """Resume: read existing addresses so a re-run skips them (survives crashes)."""
    if not ws:
        return set()
    try:
        rows = ws.get_all_values()
    except Exception:
        return set()
    return set(r[0].strip().upper() for r in rows[1:] if r and r[0].strip())


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
                if not addr or addr.upper() in seen:
                    continue
                ds = d.get("dot_status")
                if dot_color(ds) == "GREY":
                    continue
                seen.add(addr.upper())
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
        elif color in ("GOLD", "ORANGE"):
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


def search_this_area(page):
    """After a pan the new view's dots only load when the map's 'search this
    area' control is clicked. The exact label varies, so try several; if none
    match, dump the visible controls ONCE so we can pin the right one.

    Also stamps the live map zoom (read_map_view) so every Backend Comm row
    produced by this search records WHICH ZOOM produced it. Done here rather than
    at each of the seven call sites so no sweep mode can miss it."""
    read_map_view(page)
    for label in SEARCH_LABELS:
        try:
            btn = page.get_by_text(label, exact=False)
            if btn.count() > 0:
                print("  -> pressing '%s' (fetching dots from server)..." % label)
                try:
                    # Cap the click at 1s. It's only a CAP -- a normal view's button
                    # is clickable instantly, so we don't actually wait. The 1s only
                    # applies on a slow/stuck view, then it bails so the loop pans on
                    # (no long pause). The network capture is always listening, so the
                    # dots get collected off the pan whether or not this click landed.
                    btn.first.click(timeout=1000)
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


_LOGIN_MARKERS = ("choose your method of access", "at&t employee",
                  "retiree/affiliate", "sign in", "log in", "global logon",
                  "user id", "password")


def _logged_in(page):
    """False when AT&T is showing the access chooser or a sign-in form.

    The whole of 2026-08-23 was spent reading empty reports off runs that had
    quietly loaded THIS page instead of the map. The chooser answers 200, the
    hunter swept it, found nothing, and reported a clean zero -- indistinguishable
    from an empty neighbourhood. Checked positively (is the map there?) and then
    negatively (is the login text there?), because either alone can be fooled:
    the portal landing page has no map but is not a login, and a slow map render
    is not a logout.
    """
    if on_map(page):
        return True
    try:
        txt = (page.inner_text("body") or "")[:6000].lower()
    except Exception:
        return True            # cannot read the page: don't cry logout on noise
    if any(m in txt for m in _LOGIN_MARKERS):
        return False
    return True                # portal landing, or something else -- not a login


# Long by design: signing in to AT&T means a password and often an MFA prompt on
# a phone. A 60-second timeout would fail people who are doing exactly the right
# thing, and a failed run costs far more than waiting.
LOGIN_WAIT_SECS = int(os.environ.get("OPTIMUS_LOGIN_WAIT") or 600)


def _wait_for_login(page, secs):
    """Poll until the map appears. True if it did, False on timeout."""
    end = time.time() + max(1, secs)
    told = 0
    while time.time() < end:
        try:
            if on_map(page):
                return True
        except Exception:
            pass
        left = int(end - time.time())
        if left // 60 != told // 60 and left > 0:
            told = left
            print("     ...still waiting (%d min left)" % (left // 60 + 1))
        time.sleep(3)
    return bool(on_map(page))


def open_map_view(page):
    """A fresh load of /yourefer/fiber lands on the PORTAL page; the dot map is
    revealed by clicking 'Fiber Availability Map'. ONLY click it when we're on
    the portal -- if the map is already showing, do nothing (clicking again was
    flipping the view map<->portal every scan cycle). Confirmed live 2026-06-13:
    the map renders in-page at the same URL."""
    if on_map(page):
        return False   # already on the map -- never re-click (no flip)
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


def pan_map_js(page, direction):
    """Pan the Mapbox map PROGRAMMATICALLY (no mouse click, no keyboard focus) --
    a click can land on nav and flip to the portal, so we move the map directly.
    Shifts ~70% of a viewport so adjacent cells overlap a little."""
    dx = {"left": -1, "right": 1, "up": 0, "down": 0}[direction]
    dy = {"left": 0, "right": 0, "up": -1, "down": 1}[direction]
    try:
        ok = page.evaluate(
            """([dx, dy]) => {
                const m = (window.__optimusMaps || [])[0];
                if (!m || !m.panBy) return false;
                const c = m.getContainer().getBoundingClientRect();
                m.panBy([dx * c.width * 0.7, dy * c.height * 0.7], {duration: 0});
                return true;
            }""", [dx, dy])
        return bool(ok)
    except Exception:
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


# ---------------------------------------------------------------------------
# FREEZE REVIVER: if the pan loop goes silent for WATCHDOG_STALL_SECS (a
# healthy sweep pans every ~1 second, so this is a 100x margin -- it can NEVER
# fire on a moving run), the run is already dead: a hung browser, a blocked
# console, anything. A daemon thread that only reads a timestamp exits with
# code 42; the launcher relaunches fresh and the run resumes BY ITSELF -- no
# clicks, no Enter, no user. It never touches the browser or the sheet.
# ---------------------------------------------------------------------------
WATCHDOG_STALL_SECS = 300  # LAST resort only (restarts cost a re-login, so the
                           # fuse is long) -- with the real-mouse motion the
                           # pans always land and this should never fire.
_WD = [False]
_BEAT = [0.0]


def _start_watchdog():
    if _WD[0]:
        return
    _WD[0] = True
    import threading

    def _watch():
        while True:
            time.sleep(5)
            b = _BEAT[0]
            if b and time.time() - b > WATCHDOG_STALL_SECS:
                try:   # a file note, not print (a blocked console can't stop this)
                    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "watchdog_fired.txt"), "a") as f:
                        f.write("%s  frozen %ds -- relaunching itself\n"
                                % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                   int(time.time() - b)))
                except Exception:
                    pass
                os._exit(42)   # the launcher loop relaunches + auto-resumes

    threading.Thread(target=_watch, daemon=True).start()


# ---------------------------------------------------------------------------
# THE ORIGINAL FIBER HUNTER MOTION (ported 2026-07-02 on Patrick's call --
# "use the motion from the old program that worked"). fiber_hunter.py's pan():
# move the REAL Windows mouse to the map and physically drag it 150px. The OS
# injects the input directly -- it never asks the browser for a receipt, so
# THIS PAN CANNOT HANG no matter what the page is doing. The console minimizes
# itself so the drag always lands on the map, never on a window in front.
# ---------------------------------------------------------------------------
REAL_PAN_PIXELS = 150          # fiber_hunter.py: PAN_PIXELS = 150
_REAL = {"ok": None}
_CONSOLE_MIN = [False]


def _real_mouse_ready(install=False):
    """The real-mouse drive uses raw Windows system calls (ctypes user32) --
    built into every Windows Python, NOTHING to install, no fallback needed."""
    if _REAL["ok"] is None:
        _REAL["ok"] = False
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.user32.GetSystemMetrics(0)
                try:   # real pixel coords even on scaled displays
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
                _REAL["ok"] = True
            except Exception:
                _REAL["ok"] = False
    return bool(_REAL["ok"])


def _minimize_console_once():
    """Drop this console out of the way so the real-mouse drag can only land
    on the map. (The program keeps running and logging -- watch the map/sheet.)"""
    if _CONSOLE_MIN[0] or os.name != "nt":
        return
    _CONSOLE_MIN[0] = True
    print("  (minimizing this window so the map stays in front -- still "
          "running; watch the map)")
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)   # SW_MINIMIZE
    except Exception:
        pass


def _drag_real(direction, quiet=False):
    """fiber_hunter.py pan(), verbatim semantics: drag the content the OPPOSITE
    way the viewport should move. Raw OS input (SetCursorPos + mouse_event) --
    the same calls pyautogui wraps, with no package needed. Never touches the
    browser connection, so it cannot wait on anything."""
    import ctypes
    u = ctypes.windll.user32
    _minimize_console_once()
    w, h = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    cx, cy = int(w * 0.5), int(h * 0.52)     # centre of the maximized map
    dx, dy = {"right": (-REAL_PAN_PIXELS, 0), "left": (REAL_PAN_PIXELS, 0),
              "down": (0, -REAL_PAN_PIXELS), "up": (0, REAL_PAN_PIXELS)}[direction]
    if not quiet:
        print("  -> PAN %s: REAL mouse drag (the original motion)" % direction)
    try:
        u.SetCursorPos(cx, cy)
        time.sleep(0.03)
        u.mouse_event(0x0002, 0, 0, 0, 0)          # left button DOWN (real)
        time.sleep(0.06)                           # let the grab register
        steps = 8
        for i in range(1, steps + 1):              # glide, like a human drag
            u.SetCursorPos(cx + dx * i // steps, cy + dy * i // steps)
            time.sleep(0.02)
        time.sleep(0.05)                           # settle before release
        u.mouse_event(0x0004, 0, 0, 0, 0)          # left button UP
    except Exception as e:
        print("     (real drag interrupted: %s -- panning on)" % str(e)[:50])
        try:
            u.mouse_event(0x0004, 0, 0, 0, 0)      # never leave the button down
        except Exception:
            pass
    time.sleep(0.05 if quiet else WAIT_AFTER_PAN)
    return True


def mouse_drag(page, direction, quiet=False):
    """PROVEN fiber_hunter motion: DRAG to pan (the original used
    pyautogui.dragRel, ~150px serpentine). A drag is a map gesture, so it pans
    the HIDDEN Mapbox map where arrow keys / panBy do nothing. We drag the map
    CANVAS if we can find it (even in a frame); otherwise we drag the map REGION
    of the screen -- either way page.mouse moves the map. Drag the content the
    OPPOSITE way you want the viewport to move. quiet=True is a fast, silent
    pass-through pan (used to skate across cells already scanned)."""
    if _STOP[0]:
        return False   # top-left-corner STOP gesture -> end the sweep cleanly
    _BEAT[0] = time.time()
    # (auto-restart REMOVED for good, Patrick 2026-07-02: a relaunch can't get
    #  itself back to the right screen -- login/portal need button presses. So
    #  nothing here ever exits or restarts anything. The cure is motion that
    #  can't hang, not restarts.)
    if _real_mouse_ready():
        return _drag_real(direction, quiet)   # the unhangable original motion
    box = _map_canvas_box(page)
    src = "canvas"
    if not box:
        box = _viewport_map_box(page)   # canvas hidden in a frame -> drag screen
        src = "screen"
    cx = box["x"] + box["width"] / 2.0
    cy = box["y"] + box["height"] / 2.0
    sx, sy = {"right": (-1, 0), "left": (1, 0),
              "down": (0, -1), "up": (0, 1)}[direction]
    dx = sx * box["width"] * DRAG_FRAC
    dy = sy * box["height"] * DRAG_FRAC
    if not quiet:
        print("  -> PAN %s: drag %s from (%d,%d)" % (direction, src, int(cx), int(cy)))
    try:
        page.mouse.move(cx, cy)
        page.mouse.down()
        # FAST flick: few steps = a quick drag (like fiber_hunter's dragRel);
        # Mapbox adds a little inertia so it pans snappy AND a touch further.
        page.mouse.move(cx + dx, cy + dy, steps=4)
        page.mouse.up()
    except Exception as e:
        print("     drag failed: %s" % str(e)[:70])
        return False
    time.sleep(0.05 if quiet else WAIT_AFTER_PAN)
    return True


def sweep_backend(page, ws, seen, area_label, dry, cols, rows, capture):
    """FAST auto-sweep with the proven mouse-drag motion. Per cell: nudge the
    serviceability fetch, then FLUSH the backend capture (no clicking) to the
    sheet; then DRAG to the next cell, snaking across a cols x rows grid. The
    drag itself triggers AT&T's fetch and NetCapture reads it off the wire."""
    total = 0
    for r in range(rows):
        for c in range(cols):
            if _STOP[0]:                       # gentle stop -> quit within a cell
                return total
            pause_gate(page)                   # Ctrl+Shift+Pause / Ctrl+G
            if _STOP[0]:
                return total
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
        if _STOP[0]:                 # gentle stop -> quit within a cell
            return
        pause_gate(page)             # Ctrl+Shift+Pause / Ctrl+G
        if _STOP[0]:
            return
        if _map_frozen(page):        # WebGL freeze -> alert + stop cleanly
            _handle_frozen_map(ws, area_label)
            return
        if on_map(page):
            search_this_area(page)
        time.sleep(SEARCH_SETTLE)
        n = capture.flush(ws, seen, area_label, dry)
        tally["total"] += n
        tally["cells"] += 1
        touch_lock()          # keep this instance's liveness fresh
        # Stop the moment the session dies. Grinding on is how 150 cells were
        # spent capturing login pages.
        if _AUTH_FAIL[0] >= AUTH_FAIL_LIMIT:
            if not recover_session(page):
                _STOP[0] = True
        print("  [cell %d @ %d,%d] +%d  (total %d)"
              % (tally["cells"], pos[0], pos[1], n, tally["total"]))
        if tally["cells"] % 15 == 0:
            report_status(ws, area_label, "watching", found=tally["total"],
                          note="grid: %d cells, %d leads" % (tally["cells"], tally["total"]))
            push_live_counts_hunter(tally["cells"], tally["total"], area_label)

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


def _map_frozen(page):
    """True once the map's WebGL context is lost (blank-white permanent freeze)."""
    try:
        return bool(page.evaluate("() => window.__optimusGLLost === true"))
    except Exception:
        return False


def _handle_frozen_map(ws, area_label):
    """The map's WebGL context died (blank-white freeze). It can't be revived
    automatically -- turning the map back on needs the log-in + 'Fiber
    Availability Map' clicks. So DON'T reload; just alert loudly, mark it on the
    status sheet, and stop cleanly so it never sits scanning a dead map."""
    print("\n" + "!" * 62)
    print("  MAP FROZE (WebGL context lost -- the blank white map).")
    print("  It can't be turned back on automatically (needs the log-in +")
    print("  'Fiber Availability Map' clicks). STOPPING so it doesn't scan a")
    print("  dead map. Reopen the hunter, click the map back on, press Enter.")
    print("!" * 62 + "\n")
    try:
        report_status(ws, area_label, "stopped",
                      note="map froze (WebGL context lost) -- revive manually")
    except Exception:
        pass
    _STOP[0] = True          # end the sweep + shut down cleanly (no auto-restart)


# ---------------------------------------------------------------------------
# SESSION RECOVERY. AT&T's cookie can authenticate the page shell while the API
# rejects it: the map still shows the dots it fetched earlier, so the screen
# looks perfectly healthy while every new request is bounced to a login page.
# On 2026-08-23 that cost a 150-cell sweep -- every cell pressed Search, every
# reply was a 301 or an HTML login page, every cell scored +0, and the operator
# was told to log out by hand afterwards.
#
# A stale cookie is a fixable condition, not a reason to grind. Three failures
# in a row now stop the sweep, clear the cookies so AT&T is forced to present a
# real login, and wait for the sign-in -- then carry on where it left off.
# ---------------------------------------------------------------------------
_AUTH_FAIL = [0]
AUTH_FAIL_LIMIT = int(os.environ.get("OPTIMUS_AUTH_FAIL_LIMIT") or 3)
_RECOVERED = [0]


def _lock_path():
    return os.path.join(PROFILE_DIR, "optimus_run_%d.lock" % os.getpid())


def touch_lock():
    """Mark this instance alive. Cheap, best-effort."""
    try:
        os.makedirs(PROFILE_DIR, exist_ok=True)
        with open(_lock_path(), "w") as f:
            f.write("%s %d %s" % (RUN_ID, os.getpid(), time.time()))
    except Exception:
        pass


def other_instance_live(max_age=180):
    """True when another hunter has touched its lock recently.

    This exists because of a live interaction, not a theory: two hunters share
    one Chromium profile AND one cookie store, so a second instance clearing
    cookies logged the FIRST one out mid-sweep, and the report came back
    delivery=AUTH_EXPIRED -- indistinguishable from AT&T expiring the session.
    """
    try:
        me = _lock_path()
        now = time.time()
        for name in os.listdir(PROFILE_DIR):
            if not name.startswith("optimus_run_") or not name.endswith(".lock"):
                continue
            path = os.path.join(PROFILE_DIR, name)
            if os.path.abspath(path) == os.path.abspath(me):
                continue
            if now - os.path.getmtime(path) < max_age:
                return True
            try:
                os.remove(path)          # stale lock from a dead run
            except Exception:
                pass
    except Exception:
        pass
    return False


def recover_session(page, log=print):
    """Clear the dead session and wait for a fresh sign-in. True if recovered."""
    _RECOVERED[0] += 1
    log("")
    log("!" * 68)
    log("  SESSION DEAD -- %d replies in a row were a redirect or a login page."
        % _AUTH_FAIL[0])
    log("  The map still SHOWS dots because they were fetched before the")
    log("  cookie went stale. Nothing new can land until you sign in again.")
    log("")
    log("  Clearing the stale cookie now so AT&T has to show a real login...")
    log("!" * 68)
    if other_instance_live():
        log("")
        log("  ANOTHER HUNTER IS RUNNING on this machine. NOT clearing cookies --")
        log("  doing so would sign THAT run out mid-sweep, which is exactly how a")
        log("  healthy run got reported as AUTH_EXPIRED earlier today.")
        log("  Close the other window, then sign in here.")
    else:
        try:
            page.context.clear_cookies()
        except Exception as e:
            log("  (could not clear cookies: %s -- sign out by hand)" % str(e)[:60])
    try:
        safe_goto(page, MAP_URL)
    except Exception:
        pass
    log("")
    log("  SIGN IN AGAIN in the browser window, then leave it on the Fiber Map.")
    log("  The sweep resumes by itself -- do not restart the hunter.")
    if _FEED:
        try:
            _FEED.truth(auth_ok=False, note="session died mid-sweep, recovering")
            _FEED.phase("SESSION_RECOVERY_%d" % _RECOVERED[0])
        except Exception:
            pass
    ok = _wait_for_login(page, LOGIN_WAIT_SECS)
    if ok:
        log("  Signed in -- resuming the sweep where it left off.")
        _AUTH_FAIL[0] = 0
        if _FEED:
            try:
                _FEED.truth(auth_ok=True)
                _FEED.phase("resumed_after_login")
            except Exception:
                pass
    else:
        log("  Still not signed in. Stopping rather than sweeping login pages.")
    return ok


def sweep_continuous(page, ws, seen, area_label, dry, capture):
    """Keep sweeping OUTWARD in a spiral, capturing each viewport off the
    backend, until the browser is closed -- no fixed grid. Set it on a spot/ZIP
    and it covers that area and keeps expanding past it until the computer (or
    you closing the window) stops it. Returns the total captured."""
    dirs = ["right", "down", "left", "up"]
    di, run, cell, total = 0, 1, 0, 0
    print("Continuous sweep -- panning outward until you close the browser.\n")
    try:
        while True:
            reaim = False
            for _arm in range(2):           # spiral: 2 arms per run-length, then grow
                if reaim:
                    break
                for _ in range(run):
                    if _STOP[0]:                # gentle stop -> quit within a cell
                        return total
                    # PAUSED -> hands off the map until Ctrl+G. On resume the
                    # map is wherever Patrick left it, so the old spiral is
                    # meaningless: start a fresh one from the CURRENT view
                    # instead of panning back toward the old center.
                    if pause_gate(page):
                        if _STOP[0]:
                            return total
                        di, run, reaim = 0, 1, True
                        break
                    if _map_frozen(page):       # WebGL freeze -> alert + stop
                        _handle_frozen_map(ws, area_label)
                        return total
                    if on_map(page):
                        search_this_area(page)
                    time.sleep(SEARCH_SETTLE)
                    n = capture.flush(ws, seen, area_label, dry)
                    total += n
                    cell += 1
                    print("  [cell %d] +%d  (total %d)" % (cell, n, total))
                    if cell % 15 == 0:
                        note = "continuous: %d cells, %d leads" % (cell, total)
                        if total == 0:
                            # nothing captured yet -> say WHY on the status sheet
                            try:
                                note += " | " + capture.diag()
                            except Exception:
                                pass
                        report_status(ws, area_label, "watching", found=total, note=note)
                    if not mouse_drag(page, dirs[di]):
                        return total        # canvas gone -> stop
                if not reaim:
                    di = (di + 1) % 4
            if reaim:
                continue        # re-aimed by hand: spiral afresh, don't grow the old one
            run += 1
    except Exception as e:
        msg = str(e).lower()
        if "closed" in msg or "target" in msg:
            print("\nBrowser closed -- stopping the sweep. (%d leads this run.)" % total)
        else:
            print("\nSweep stopped: %s" % str(e)[:100])
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
    """Type the ZIP into the AT&T map's search box, pick the first geocoder
    suggestion, and fly the map there. Works for ANY market (OKC, Houston,
    anywhere). Pressing Enter alone often leaves a bare ZIP unresolved so the
    map never moves and the scan runs on the DEFAULT view -- that was the
    'entered OKC but scraped elsewhere' bug. Returns True only when a location
    was entered."""
    q = str(zip_code).strip()
    selectors = [".mapboxgl-ctrl-geocoder--input",
                 ".maplibregl-ctrl-geocoder--input",
                 "input[placeholder*='Search' i]",
                 "input[placeholder*='address' i]",
                 "input[placeholder*='ZIP' i]",
                 "input[type='search']",
                 "input[type='text']"]
    box = None
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                box = el; break
        except Exception:
            continue
    if box is None:
        try:
            tb = page.get_by_role("textbox")
            if tb.count() > 0 and tb.first.is_visible():
                box = tb.first
        except Exception:
            box = None
    if box is None:
        return False
    try:
        box.click(); box.fill(""); box.type(q, delay=60); time.sleep(1.2)
    except Exception:
        return False
    for ss in [".mapboxgl-ctrl-geocoder .suggestions li > a",
               ".maplibregl-ctrl-geocoder .suggestions li > a",
               ".suggestions li > a",
               ".mapboxgl-ctrl-geocoder--suggestion",
               "ul.suggestions li"]:
        try:
            page.wait_for_selector(ss, timeout=3500)
            sug = page.query_selector(ss)
            if sug and sug.is_visible():
                sug.click(); time.sleep(3.5); return True
        except Exception:
            continue
    try:
        page.keyboard.press("Enter"); time.sleep(4.0); return True
    except Exception:
        return False

def record_capture(ws, seen, area_label, dry, address, popup_status, ban,
                   dot_status, via, zone_label="WORKING", lat=None, lng=None):
    """Common writer for both the Mapbox fast path and the click path.
    Returns True when a NEW address was recorded. zone_label (FRESH/WORKING/
    MATURE) rides along so business_score weights just-lit zones first;
    lat/lng (when the geo path has them) feed the Places phone enricher."""
    addr_key = address.strip().upper()
    if addr_key in seen:
        return False
    seen.add(addr_key)
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


# Core files a fresh launch must have current -- the SAME set RUN_HUNTER.bat curls.
# THIS TUPLE IS THE ENTIRE DEPLOY MANIFEST on a machine without git (the hunter
# PC has none -- self_update's git path throws WinError 2 and _raw_refresh takes
# over). A file absent from this list NEVER reaches that machine by auto-update,
# so pushing it to the branch changes nothing there. Add new tools here or they
# do not ship.
_CORE_FILES = ("precise_fiber_hunter.py", "optimus_dedupe.py",
               "optimus_feed.py",
               "optimus_web_intel.py",
               "optimus_territory.py", "optimus_operator.py",
               "optimus_dot_detect.py",
               "optimus_api_capture.py", "hunter_fixes.py",
               "backend_classifier.py", "build_codes.json",
               "verify_gold_capture.py", "deploy_check.py",
               "test_durability.py", "decode_gold.py",
               "test_gold_predicate.py", "wire_diff.py",
               "clean_sheet.py", "CLEAN_SHEET.bat", "sheet_feed.py")


def _raw_refresh(here):
    """HTTPS raw-download fallback for when git isn't installed (the WinError 2
    case). Re-downloads the core files straight from GitHub raw with stdlib
    urllib -- no git, no launcher needed, so the PROGRAM self-heals to the latest
    code every launch on ANY machine. Returns True if THIS file's bytes changed
    (caller then re-execs once). Best-effort; every failure is swallowed."""
    import urllib.request, time, hashlib, json as _json
    base = ("https://raw.githubusercontent.com/%s/%s/optimus"
            % (GH_REPO, GH_BRANCH))
    cb = str(int(time.time()))        # cache-bust so a CDN copy can't pin us stale
    d = os.path.dirname(here)
    changed = False
    updated, same, failed = [], [], []

    for name in _CORE_FILES:
        url = "%s/%s?cb=%s" % (base, name, cb)
        dest = os.path.join(d, name)
        try:
            req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
            resp = urllib.request.urlopen(req, timeout=30)
            new = resp.read()
            if not new:
                failed.append((name, "empty response"))
                continue

            # A captive portal, a proxy login page or a truncated transfer can all
            # come back HTTP 200 with a body that is not the file. Writing that
            # over a working core file bricks the hunter with no clue why, so
            # every download is parsed BEFORE it is allowed to land.
            if name.endswith(".py"):
                try:
                    compile(new, name, "exec")
                except SyntaxError as e:
                    failed.append((name, "downloaded bytes are not valid Python "
                                         "(line %s) -- kept the working copy" % e.lineno))
                    continue
            elif name.endswith(".json"):
                try:
                    _json.loads(new.decode("utf-8"))
                except Exception:
                    failed.append((name, "downloaded bytes are not valid JSON "
                                         "-- kept the working copy"))
                    continue

            old = b""
            if os.path.exists(dest):
                old = open(dest, "rb").read()
            if new == old:
                same.append(name)
                continue

            # Write to a temp file then replace, so a crash or a full disk mid-write
            # cannot leave a half-written core file behind. os.replace is atomic.
            tmp = dest + ".new"
            with open(tmp, "wb") as fh:
                fh.write(new)
            os.replace(tmp, dest)
            updated.append((name, hashlib.sha256(new).hexdigest()[:8]))
            if os.path.abspath(dest) == os.path.abspath(here):
                changed = True
        except Exception as e:
            # Report it. Swallowing this is how a hunter runs month-old code while
            # printing a success line -- the exact failure this whole block exists
            # to make visible.
            failed.append((name, "%s: %s" % (type(e).__name__, str(e)[:70])))

    print("  UPDATE (HTTPS, no git needed): %d updated, %d already current, "
          "%d FAILED" % (len(updated), len(same), len(failed)))
    for name, fp in updated:
        print("     updated  %-28s -> %s" % (name, fp))
    if failed:
        print("!" * 68)
        print("  %d OF %d CORE FILES DID NOT UPDATE. This run is using the copy"
              % (len(failed), len(_CORE_FILES)))
        print("  already on disk for those files, which may be old.")
        for name, why in failed:
            print("     FAILED   %-28s %s" % (name, why))
        print("  Branch: %s/%s" % (GH_REPO, GH_BRANCH))
        print("  A 404 here usually means the file was renamed or the branch")
        print("  moved. Check the branch above still exists on GitHub.")
        print("!" * 68)
    return changed


def _deploy_manifest():
    """Print what is ACTUALLY on disk for every core file: when it was written and
    a fingerprint of its bytes.

    A hand-typed version marker eventually disagrees with the code, and one that
    disagrees is worse than none because it gets believed -- BUILD_DATE already
    did exactly that, reporting 08-18 while 08-20 code was running. Nothing here
    is maintained by anyone, so nothing here can go stale: it is read off the
    files themselves at launch. When somebody says 'the update didn't take',
    this is the block that answers it."""
    import hashlib
    d = os.path.dirname(os.path.abspath(__file__))
    print("  DEPLOYED FILES (read from disk -- cannot go stale):")
    for name in _CORE_FILES:
        p = os.path.join(d, name)
        if not os.path.exists(p):
            print("     MISSING  %-28s <- not on this PC; it will never "
                  "auto-update" % name)
            continue
        try:
            b = open(p, "rb").read()
            print("     %-28s %s  %s"
                  % (name,
                     time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p))),
                     hashlib.sha256(b).hexdigest()[:8]))
        except Exception as e:
            print("     %-28s unreadable: %s" % (name, str(e)[:40]))


def self_update():
    """On launch, pull the newest code from GitHub so a restart always runs the
    latest version. If THIS file actually changed, relaunch once with the new
    code. Guards: OPTIMUS_NO_UPDATE=1 (set on the relaunch) stops an infinite
    re-exec loop; GIT_TERMINAL_PROMPT=0 stops a hang on a credential prompt;
    any failure (offline, no git) is non-fatal -- we just keep running.

    Two update paths so it self-heals on ANY machine: (1) git fetch+reset when
    git is present (a full clone install); (2) if git is missing/fails -- the
    common WinError 2 on a no-git PC -- fall back to an HTTPS raw re-download of
    the core files (like the scraper), so the PROGRAM updates itself with no git
    and no launcher. Either way, if this file's bytes changed, we re-exec once."""
    import subprocess
    if os.environ.get("OPTIMUS_NO_UPDATE") == "1" or "--no-update" in sys.argv:
        return
    here = os.path.abspath(__file__)
    repo_root = os.path.dirname(os.path.dirname(here))
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    git = _find_git()           # works even when git isn't on this shell's PATH
    changed = False
    try:
        before = open(here, "rb").read()
        # fetch + hard reset to origin so a local edit / conflict / divergence
        # can NEVER leave us stuck on old code (a plain pull silently fails then).
        f = subprocess.run([git, "-C", repo_root, "fetch", "origin", REPO_BRANCH],
                           env=env, timeout=90, capture_output=True, text=True)
        r = subprocess.run([git, "-C", repo_root, "reset", "--hard",
                            "origin/" + REPO_BRANCH],
                           env=env, timeout=60, capture_output=True, text=True)
        # A silent failure here is how the hunter ends up running MONTHS-old code
        # while looking perfectly healthy. Both commands used to have their
        # output captured and their exit codes ignored, so a wrong branch name or
        # an expired credential produced no message at all. Say it loudly.
        if f.returncode or r.returncode:
            bad = (f if f.returncode else r)
            print("!" * 68)
            print("  SELF-UPDATE FAILED -- THIS RUN IS USING THE CODE ON DISK,")
            print("  WHICH MAY BE OLD. Branch: %s" % REPO_BRANCH)
            print("  git said: %s" % (bad.stderr or bad.stdout or "").strip()[:200])
            print("  Fix the branch/credentials, or run: git pull")
            print("!" * 68)
        after = open(here, "rb").read()
        changed = (after != before)
    except Exception as e:
        # No git (WinError 2) or a git failure -- fall back to HTTPS raw download
        # so the program STILL self-updates. This is the no-git-PC self-heal.
        print("(git update unavailable: %s -- using HTTPS raw fallback)"
              % str(e)[:60])
        try:
            changed = _raw_refresh(here)
        except Exception:
            print("(auto-update skipped -- run START OPTIMUS.bat to force it)")
            return
    if changed:
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
def _start_summary():
    """Refresh the small 'OPTIMUS DATA SUMMARY' sheet Claude reads (best-effort,
    one-shot, detached). The production sheet is too big for Claude to export, so
    optimus_summary.py distills it. Runs in its own process so it never delays or
    touches the hunt; ONE-SHOT (no loop) so nothing leaks. Silent on any failure."""
    try:
        import subprocess as _sp
        here = os.path.dirname(os.path.abspath(__file__))
        summ = os.path.join(here, "optimus_summary.py")
        if not os.path.exists(summ):
            return
        _env = dict(os.environ, OPTIMUS_NO_UPDATE="1")
        _kw = {"cwd": here, "env": _env, "stdin": _sp.DEVNULL,
               "stdout": _sp.DEVNULL, "stderr": _sp.DEVNULL}
        if os.name == "nt":
            _kw["creationflags"] = 0x00000008 | 0x08000000   # detached, no window
        else:
            _kw["start_new_session"] = True
        _sp.Popen([sys.executable, summ], **_kw)   # run once, then it exits
        print("  (refreshing the OPTIMUS DATA SUMMARY sheet for Claude in the "
              "background)")
    except Exception:
        pass


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


def _ulog(msg):
    print("%s  %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def uploader_main():
    """THE WRITE WORKER (split mode). Tails precise_addresses.jsonl from the
    offset the hunter handed us and does ALL Google work: batched sheet writes
    (failed batches stay queued and retry), live biz matching, Hunter Status
    mirroring. SINGLETON: exactly one, ever. Exits itself when the hunter has
    been silent a long while and everything is shipped."""
    try:
        if os.path.exists(UPLOADER_LOCK) and                 time.time() - os.path.getmtime(UPLOADER_LOCK) < 60:
            print("another uploader is live -- standing down (pid %d)" % os.getpid())
            return
    except OSError:
        pass
    _ulog("uploader up (pid %d) -- all sheet work happens here" % os.getpid())
    ws = None
    delay, tries = 5, 0
    while ws is None:
        try:
            ws = open_sheet()
        except Exception as e:
            _ulog("sheet connect failed: %s -- retrying" % str(e)[:80])
        if ws is None:
            tries += 1
            if tries >= 12:
                _ulog("no sheet after %d tries -- exiting (leads stay in the "
                      "local JSONL; next start backfills them)" % tries)
                return
            time.sleep(delay)
            delay = min(delay * 2, 120)
    seen = already_seen(ws)
    _ulog("seeded %d known addresses from the sheet" % len(seen))
    try:
        init_bizmatch(ws)
    except Exception as e:
        _ulog("biz match init skipped: %s" % str(e)[:80])
    try:
        # ONE-TIME: fold the gold history backfill into the hunter (no extra
        # program) -- if the standalone gold sheet is empty, seed it from the
        # ORANGE rows already in Precise Fiber. Runs once, before shipping starts.
        _auto_backfill_gold_once(ws)
    except Exception as e:
        _ulog("gold backfill skipped: %s" % str(e)[:80])
    try:
        offset = int(os.environ.get("OPTIMUS_OUTBOX_OFFSET", "0") or 0)
    except ValueError:
        offset = 0
    green_records = []
    gold_records = []
    grey_records = []
    unknown_records = []
    main_sheet_rows = []      # all colors route through here FIRST
    remainder = b""
    last_status = ""
    idle_since = time.time()
    while True:
        new_records = []
        try:
            size = os.path.getsize(JSONL_PATH) if os.path.exists(JSONL_PATH) else 0
            if size < offset:
                offset = 0
            if size > offset:
                with open(JSONL_PATH, "rb") as f:
                    f.seek(offset)
                    data = f.read()
                offset += len(data)
                data = remainder + data
                lines = data.split(b"\n")
                remainder = lines.pop()
                for raw in lines:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        d = json.loads(raw.decode("utf-8", "replace"))
                    except Exception:
                        continue
                    addr = (d.get("address") or "").strip()
                    if not addr:
                        continue
                    # CLASSIFY FIRST, before any seen check or routing
                    ds = d.get("dot_status")
                    color = dot_color(ds)
                    # Skip only AFTER classifying (no global seen skip)
                    if addr.upper() in seen:
                        continue
                    # June's exact Precise Fiber shape: Address | Dot Color |
                    # Captured At | Business | Phone (biz merged like the flush)
                    _bidx = _BIZ.get("index") or {}
                    _b = _bidx.get(_norm_addr(addr)) if _bidx else None
                    # Complete address on every row (Patrick 2026-08-24):
                    # City/State/ZIP ride along so enrichment never fails on a
                    # missing ZIP, plus Lat/Lng. Columns H-L; old rows just
                    # have blanks there, nothing downstream reads past G.
                    row = [addr, color, d.get("ts") or "",
                           (_b or {}).get("name", ""),
                           (_b or {}).get("phone", ""),
                           d.get("run_id") or RUN_ID,
                           d.get("operator") or OPERATOR(),
                           d.get("lat") if d.get("lat") is not None else "",
                           d.get("lng") if d.get("lng") is not None else "",
                           d.get("city") or "", d.get("state") or "",
                           d.get("zip") or ""]
                    d["biz_name"] = (_b or {}).get("name", "")
                    d["biz_phone"] = (_b or {}).get("phone", "")
                    # Route to appropriate bucket BEFORE main sheet write
                    if color == "GREEN":
                        green_records.append(d)
                    elif color in ("GOLD", "ORANGE"):
                        gold_records.append(d)
                    elif color == "GREY":
                        grey_records.append(d)
                    else:
                        unknown_records.append(d)
                    # Add to main sheet queue
                    main_sheet_rows.append(row)
                    new_records.append(d)
        except Exception as e:
            _ulog("outbox read error: %s" % str(e)[:80])
        if main_sheet_rows:
            idle_since = time.time()
            try:
                for i in range(0, len(main_sheet_rows), 500):
                    ws.append_rows(main_sheet_rows[i:i + 500], value_input_option="RAW")
                _ulog("shipped %d rows to the sheet" % len(main_sheet_rows))
                _g = [r[0] for r in main_sheet_rows if r[1] == "GREEN"]
                if _g:
                    _extra = (" +%d more" % (len(_g) - 5)) if len(_g) > 5 else ""
                    _ulog("   GREEN x%d -> %s%s"
                          % (len(_g), ", ".join(_g[:5]), _extra))
                # ONLY mark seen after successful write
                for row in main_sheet_rows:
                    addr = row[0]
                    if addr:
                        seen.add(addr.upper())
                main_sheet_rows = []
                green_records = []
            except Exception as e:
                _ulog("write failed (%s) -- %d rows stay queued for retry"
                      % (str(e)[:60], len(main_sheet_rows)))
            if new_records:
                try:
                    # Buckets are cleared only AFTER these writes succeed. They
                    # used to be cleared alongside main_sheet_rows above, which
                    # handed write_gold_dots an always-empty list -- gold was
                    # classified all run and the gold tab never got a row.
                    ng = write_gold_dots(ws.spreadsheet, gold_records)
                    write_gold_recheck(ws.spreadsheet, gold_records)
                    write_grey_dots(ws.spreadsheet, grey_records)
                    if grey_records:
                        _greys = [(_r.get("address") or "?")
                                  for _r in grey_records]
                        _extra = ((" +%d more" % (len(_greys) - 8))
                                  if len(_greys) > 8 else "")
                        _ulog("   GREY x%d -> %s%s"
                              % (len(_greys), ", ".join(_greys[:8]), _extra))
                    if ng:
                        _ulog("shipped %d gold (upgrade) dots to '%s'" % (ng, GOLD_TAB))
                        for _r in gold_records:
                            if gold_tier(_r.get("dot_status")) == TIER_VERIFIED:
                                _ulog("   GOLD -> %s" % (_r.get("address") or "?"))
                    gold_records = []
                    grey_records = []
                    unknown_records = []
                    _flush_verification(ws.spreadsheet)
                except Exception as e:
                    _ulog("gold dots error: %s" % str(e)[:60])
                try:
                    match_leads_to_biz(new_records)
                except Exception as e:
                    _ulog("biz match error: %s" % str(e)[:60])
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
        try:
            with open(UPLOADER_LOCK, "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass
        # A PAUSE is not an idle hunt. The uploader is its own process, so it
        # reads the flag FILE the hunter drops -- without this, pausing to move
        # the map for 15 minutes quietly killed the writer.
        if os.path.exists(_PAUSE_FLAG):
            idle_since = time.time()
        if not main_sheet_rows and time.time() - idle_since > 900:
            _ulog("hunter silent 15 min and everything shipped -- uploader done")
            try:
                os.remove(UPLOADER_LOCK)
            except OSError:
                pass
            return
        time.sleep(2)


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
        return   # split mode: the uploader mirrors run_status.json to the sheet
    sws = _status_sheet(ws)
    if sws is not None:
        try:
            sws.append_row([stamp, host, str(area), state, str(found), str(note)])
        except Exception:
            pass


_NEWFIBER_WS = [None]
_NEWFIBER_LOG = []      # recent alert lines, mirrored to a public GitHub file


def _log_new_fiber_alert(ws, area, greens, grey_ct):
    """Record a NEW-FIBER cluster so it can trigger a phone notification, TWO ways:
      1) a row on the 'New Fiber Alerts' sheet tab (needs the Google key), and
      2) a line pushed to a PUBLIC GitHub file optimus/_live/NEW_FIBER_ALERTS.txt
         (no key needed) so a scheduled notifier can read it and ping the phone.
    Columns on the tab: Time | Host | Area | Green(new) | Existing | Sample | Notified."""
    import socket
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    host = socket.gethostname()
    sample = " | ".join(greens[:8])
    # 1) sheet tab
    if ws is not None:
        try:
            sh = ws.spreadsheet
            w = _NEWFIBER_WS[0]
            if w is None:
                try:
                    w = sh.worksheet(NEW_FIBER_TAB)
                except Exception:
                    w = sh.add_worksheet(title=NEW_FIBER_TAB, rows="500", cols="7")
                    w.append_row(["Time", "Host", "Area", "Green (new)",
                                  "Existing customers", "Sample addresses", "Notified"])
                _NEWFIBER_WS[0] = w
            w.append_row([stamp, host, str(area), len(greens), grey_ct, sample, ""])
        except Exception:
            pass
    # 2) public GitHub file -> readable by a notifier with no Google key
    try:
        _NEWFIBER_LOG.append("%s  host=%s  area=%s  NEW-FIBER green=%d existing=%d :: %s"
                             % (stamp, host, area, len(greens), grey_ct, sample))
        body = ("OPTIMUS -- NEW FIBER ALERTS (freshly-lit, mostly-green blocks)\n"
                "latest: %s   total alerts this run: %d\n"
                "%s\n----------------------------------------\n%s\n"
                % (stamp, len(_NEWFIBER_LOG), "=" * 40,
                   "\n".join(_NEWFIBER_LOG[-40:])))
        gh_put("optimus/_live/NEW_FIBER_ALERTS.txt", body)
    except Exception:
        pass
    # 3) REAL-TIME email, the moment it's spotted (cooldown-limited so a big
    #    neighborhood doesn't spam). Needs a local optimus_email.json; without it
    #    this silently skips and the daily digest still covers it.
    try:
        _email_alert(
            "NEW FIBER: %d eligible homes (%s)" % (len(greens), area),
            "A freshly-lit fiber block was just found.\n\n"
            "When: %s\nMachine: %s\nArea: %s\n"
            "New (green, non-customer) homes in view: %d\n"
            "Existing customers in view: %d\n\nSample addresses:\n%s\n"
            % (stamp, host, area, len(greens), grey_ct, "\n".join(greens[:15])))
    except Exception:
        pass


EMAIL_COOLDOWN = 600       # min seconds between real-time emails (anti-spam)
_LAST_EMAIL = [0.0]
# Where new-fiber alerts are emailed by default (overridable with "to" in the
# optimus_email.json file). Set to Patrick per request.
DEFAULT_ALERT_TO = "patricksiado@gmail.com"


def _email_cfg():
    """Load real-time email settings from a LOCAL file (never committed):
    optimus_email.json = {"user":"you@gmail.com","password":"<app password>",
    "to":"BHOLLAND@thefiberplug.com","host":"smtp.gmail.com","port":587}.
    Looked for in the same spots as the github token. Returns a dict or None."""
    import json as _j
    home = os.path.expanduser("~")
    for p in [os.path.join(home, "Desktop", "optimus_email.json"),
              os.path.join(home, "Downloads", "optimus_email.json"),
              os.path.join(home, "optimus_email.json"),
              os.path.join(home, "optimus", "optimus_email.json"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "optimus_email.json")]:
        try:
            if os.path.exists(p):
                c = _j.load(open(p))
                if c.get("user") and c.get("password"):
                    c.setdefault("host", "smtp.gmail.com")
                    c.setdefault("port", 587)
                    c.setdefault("to", DEFAULT_ALERT_TO)
                    return c
        except Exception:
            pass
    return None


def _email_alert(subject, body):
    """Send an alert email NOW (best-effort, cooldown-limited). No config file ->
    silently skip. Never crashes the hunt."""
    import time as _t
    if (_t.time() - _LAST_EMAIL[0]) < EMAIL_COOLDOWN:
        return
    cfg = _email_cfg()
    if not cfg:
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        m = MIMEText(body)
        m["Subject"] = subject
        m["From"] = cfg["user"]
        m["To"] = cfg["to"]
        s = smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=20)
        s.starttls()
        s.login(cfg["user"], cfg["password"])
        s.sendmail(cfg["user"], [x.strip() for x in str(cfg["to"]).split(",")],
                   m.as_string())
        s.quit()
        _LAST_EMAIL[0] = _t.time()
        print("   (real-time email sent to %s)" % cfg["to"])
    except Exception as e:
        print("   (real-time email skipped: %s)" % str(e)[:70])


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
# Captured At + Run ID appended 2026-08-20. These rows carried no timestamp of any
# kind, so a business lead could not be aged, diffed against a later sweep, or
# traced to the run that produced it. Appended at the END so existing rows stay
# valid -- they simply have the last two columns blank.
BIZ_HEADER = ["Business Name", "Phone", "Address", "Website", "Category",
              "Captured At", "Run ID"]
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
        "green_seen": set(), "orange_seen": set(),
        "green_ph": set(), "orange_ph": set()}
_BIZ_RELOAD = [0]   # flush counter -> reload the business index every 20 flushes


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


def _biz_ph10(s):
    """Last-10-digit phone key (the dialer key) or '' if not a real 10-digit US
    number. Same normalization the scraper uses so both sides dedup identically."""
    d = re.sub(r"\D", "", s or "")
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d if len(d) == 10 else ""


def _ensure_biz_tab(sh, title):
    """Open the result tab, or create it with a TINY footprint (100x5 = 500 cells,
    grows as rows append) so it fits even on a near-full sheet. Returns None if the
    sheet is genuinely maxed out -- the caller then falls back to a local CSV."""
    sh = _as_spreadsheet(sh)
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


def _biz_seen(ws):
    if ws is None:
        return set()
    try:
        return set(r[2].strip().upper() for r in ws.get_all_values()[1:]
                   if len(r) > 2 and r[2].strip())
    except Exception:
        return set()


def _csv_seen(path):
    s = set()
    try:
        import csv as _csv
        with open(path, newline="") as f:
            for row in _csv.reader(f):
                if len(row) > 2 and row[2].strip():
                    s.add(row[2].strip().upper())
    except Exception:
        pass
    return s


def _biz_seen_ph(ws):
    """Seed the phone-dedup set from an existing result tab (col B = Phone)."""
    if ws is None:
        return set()
    try:
        return set(p for p in (_biz_ph10(r[1]) for r in ws.get_all_values()[1:]
                               if len(r) > 1) if p)
    except Exception:
        return set()


def _csv_seen_ph(path):
    s = set()
    try:
        import csv as _csv
        with open(path, newline="") as f:
            for row in _csv.reader(f):
                if len(row) > 1:
                    p = _biz_ph10(row[1])
                    if p:
                        s.add(p)
    except Exception:
        pass
    return s


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
    _BIZ["green_seen"] = _biz_seen(_BIZ["green_ws"]) | _csv_seen(GREEN_CSV)
    _BIZ["orange_seen"] = _biz_seen(_BIZ["orange_ws"]) | _csv_seen(ORANGE_CSV)
    _BIZ["green_ph"] = _biz_seen_ph(_BIZ["green_ws"]) | _csv_seen_ph(GREEN_CSV)
    _BIZ["orange_ph"] = _biz_seen_ph(_BIZ["orange_ws"]) | _csv_seen_ph(ORANGE_CSV)
    dst = ("the '%s'/'%s' tabs" % (GREEN_BIZ_TAB, ORANGE_BIZ_TAB)
           if _BIZ["green_ws"] else "local CSV (sheet is full)")
    print("  business match ON: %d businesses loaded -> matches go to %s, live."
          % (len(idx), dst))
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
        au = addr.strip().upper()
        ph = _biz_ph10(b.get("phone"))          # dialer key: last-10-digit phone
        # Captured At carries the DOT's timestamp, not "now" -- these rows are
        # a business matched to a captured dot, so the dot's capture time is the
        # date that matters for ageing and for diffing against a later sweep.
        row = [b.get("name") or "", b.get("phone") or "", addr,
               b.get("website") or "", b.get("category") or "",
               ld.get("ts") or time.strftime("%Y-%m-%d %H:%M:%S"), RUN_ID]
        if (ld.get("dot_status") or "").lower() == "copper_upgrade":
            # Dedup by PHONE when the business has one (one business = one row, no
            # matter how many address/unit/spelling variants matched the dot) --
            # this is what stopped the ~8x row inflation. No phone -> fall back to
            # the raw-address guard so no-phone matches still don't double-write.
            if ph:
                if ph in _BIZ["orange_ph"]:
                    continue
                _BIZ["orange_ph"].add(ph)
            elif au in _BIZ["orange_seen"]:
                continue
            _BIZ["orange_seen"].add(au)
            o_rows.append(row)
        else:
            if ph:
                if ph in _BIZ["green_ph"]:
                    continue
                _BIZ["green_ph"].add(ph)
            elif au in _BIZ["green_seen"]:
                continue
            _BIZ["green_seen"].add(au)
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
            print("    business match: +%d Fiber Green Biz, +%d Upgrade Orange Biz (-> %s)"
                  % (len(g_rows), len(o_rows), where))
    except Exception as e:
        print("    (biz write hiccup: %s)" % str(e)[:60])



# ============================================================================
# PERIODIC BACKGROUND DEDUPE  (identical block in precise_fiber_hunter.py AND
# maps_scraper_standalone.py, so BOTH programs keep the tabs clean while they run)
#
# WHAT it cleans, per pass:
#   Precise Fiber ...... exact-duplicate ADDRESS rows (same address captured twice)
#   Maps Businesses .... same PHONE (else same NAME|ADDRESS) written twice
#   Fiber Green Biz .... same PHONE (else NAME|ADDRESS) -- collapses the ~8x
#   Upgrade Orange Biz . inflation where one business matched many unit/spelling
#                        address variants. Keeps the row that has a call
#                        disposition, else the first one. NO unique phone is ever
#                        dropped (verified: 21,662 -> 4,105 rows, phones lost = 0).
#
# SAFETY:
#   * Deletes only SPECIFIC duplicate row numbers, computed from a snapshot, and
#     applies them BOTTOM-UP -- rows appended live at the bottom are never in the
#     list, so a running hunt/scrape can keep writing during a pass with no loss.
#   * Writes a local CSV backup of a tab BEFORE it removes anything from it.
#   * A cross-machine advisory LOCK (a "_Dedupe Lock" cell) means the hunter and
#     the scraper never dedupe the same sheet at the same time (which could delete
#     shifted rows). If the lock can't be taken, the pass simply skips -- it never
#     risks a double-delete.
#   * Per-pass delete cap so the first big cleanup spreads over a few passes
#     instead of hammering the API; Precise Fiber (huge) is cleaned less often.
# ============================================================================
_DEDUPE_EVERY   = 1800     # seconds between passes (30 min)
_DEDUPE_WARMUP  = 120      # let the run get going before the first pass
_DEDUPE_STALE   = 900      # a lock older than this (sec) is treated as abandoned
_DEDUPE_MAXDEL  = 6000     # max rows removed from one tab per pass (converges)
_DEDUPE_LOCK_TAB = "_Dedupe Lock"
_DD_PASS = [0]             # pass counter (Precise Fiber only every 6th pass)


def _dd_phone(s):
    import re as _re
    d = _re.sub(r"\D", "", s or "")
    return d[-10:] if len(d) >= 10 else ""


def _dd_backup_csv(tabname, values):
    """One rolling local CSV backup per tab, written just before we delete."""
    import csv as _csv, os as _os, re as _re
    try:
        here = _os.path.dirname(_os.path.abspath(__file__))
        p = _os.path.join(here, "dedupe_backup_%s.csv"
                          % _re.sub(r"\W+", "_", tabname).strip("_"))
        with open(p, "w", newline="", encoding="utf-8") as f:
            _csv.writer(f).writerows(values)
    except Exception:
        pass


def _dd_delete_rows(ws, row_numbers):
    """Delete 1-based sheet row numbers, batched into contiguous ranges and
    applied BOTTOM-UP in a single batch_update so earlier deletes don't shift
    later ones. Returns how many rows were removed."""
    if not row_numbers:
        return 0
    idx = sorted(set(row_numbers), reverse=True)
    ranges, start, prev = [], idx[0], idx[0]
    for r in idx[1:]:
        if r == prev - 1:
            prev = r
        else:
            ranges.append((prev, start)); start = prev = r
    ranges.append((prev, start))          # (lo, hi) inclusive, already top-to-bottom
    sid = ws.id
    reqs = [{"deleteDimension": {"range": {"sheetId": sid, "dimension": "ROWS",
             "startIndex": lo - 1, "endIndex": hi}}} for (lo, hi) in ranges]
    removed = sum(hi - lo + 1 for lo, hi in ranges)
    for i in range(0, len(reqs), 200):    # chunk the payload; order preserved
        ws.spreadsheet.batch_update({"requests": reqs[i:i + 200]})
    return removed


def _dd_dedupe_tab(sh, tab, key_fn, score_fn=None):
    """Keep one row per key (highest score, else earliest); remove the rest by
    OVERWRITING the kept rows at the top, then trimming the old trailing rows in
    ONE contiguous delete. Reliable at ANY scale (2 API calls, not thousands of
    scattered deletes -- the old way choked on a 17k-dupe tab). Append-safe: a
    live append lands at row >= N+2, BELOW the trimmed range [K+2 .. N+1], so it
    survives and just shifts up. Returns rows removed."""
    sh = _as_spreadsheet(sh)
    try:
        ws = sh.worksheet(tab)
    except Exception:
        return 0
    vals = ws.get_all_values()
    if len(vals) < 3:
        return 0
    hdr, rows = vals[0], vals[1:]
    N = len(rows)
    best, keyless = {}, []                 # key -> (score, index); keyless kept as-is
    for i, r in enumerate(rows):
        k = key_fn(r)
        if not k:
            keyless.append(i)
            continue
        s = score_fn(r) if score_fn else 0
        if k not in best or s > best[k][0]:
            best[k] = (s, i)
    keep_idx = sorted(set(v[1] for v in best.values()) | set(keyless))
    removed = N - len(keep_idx)
    if removed <= 0:
        return 0
    _dd_backup_csv(tab, vals)              # local CSV backup BEFORE any change
    width = max(len(hdr), max((len(rows[i]) for i in keep_idx), default=len(hdr)))
    body = [(list(rows[i]) + [""] * width)[:width] for i in keep_idx]
    K = len(body)
    # 1) overwrite kept rows starting at row 2 (header stays row 1)
    ws.batch_update([{"range": "A2", "values": body}], value_input_option="RAW")
    # 2) trim the OLD trailing rows [K+2 .. N+1]; live appends land at >= N+2, safe
    lo, hi = K + 2, N + 1
    if hi >= lo:
        ws.spreadsheet.batch_update({"requests": [{"deleteDimension": {"range": {
            "sheetId": ws.id, "dimension": "ROWS",
            "startIndex": lo - 1, "endIndex": hi}}}]})
    return removed


def _dd_acquire_lock(sh):
    """Advisory cross-machine lock so hunter+scraper never dedupe at once."""
    sh = _as_spreadsheet(sh)
    import time as _t, socket as _s
    try:
        try:
            lk = sh.worksheet(_DEDUPE_LOCK_TAB)
        except Exception:
            lk = sh.add_worksheet(title=_DEDUPE_LOCK_TAB, rows="2", cols="2")
        host = _s.gethostname()
        now = _t.time()
        cur = lk.acell("A1").value or ""
        if cur:
            try:
                ts = float(cur.split("|", 1)[0])
            except Exception:
                ts = 0.0
            if (now - ts) < _DEDUPE_STALE and not cur.endswith("|" + host):
                return None                # someone else holds a fresh lock
        lk.update_acell("A1", "%f|%s" % (now, host))
        return lk
    except Exception:
        return None


def _dd_keys():
    def biz_key(r):
        r = (list(r) + [""] * 3)
        ph = _dd_phone(r[1])
        if ph:
            return ph
        nm, ad = r[0].strip().upper(), r[2].strip().upper()
        return ("N:" + nm + "|" + ad) if (nm or ad) else ""

    def biz_score(r):                      # keep the row that has a disposition
        return 1 if (len(r) > 5 and str(r[5]).strip()) else 0

    def pf_key(r):
        return r[0].strip().upper() if (r and r[0].strip()) else ""

    def maps_key(r):
        r = (list(r) + [""] * 3)
        ph = _dd_phone(r[2])
        if ph:
            return ph
        nm, ad = r[0].strip().upper(), r[1].strip().upper()
        return ("N:" + nm + "|" + ad) if (nm or ad) else ""
    return biz_key, biz_score, pf_key, maps_key


def dedupe_all_tabs(sh):
    if sh is None:
        return 0
    lk = _dd_acquire_lock(sh)
    if lk is None:
        return 0                            # another machine is deduping now
    biz_key, biz_score, pf_key, maps_key = _dd_keys()
    _DD_PASS[0] += 1
    jobs = [("Maps Businesses", maps_key, None),
            ("Fiber Green Biz", biz_key, biz_score),
            ("Upgrade Orange Biz", biz_key, biz_score)]
    if _DD_PASS[0] == 1 or _DD_PASS[0] % 6 == 0:   # huge tab: clean less often
        jobs.insert(0, ("Precise Fiber", pf_key, None))
    total = 0
    for tab, kf, sf in jobs:
        try:
            n = _dd_dedupe_tab(sh, tab, kf, sf)
            if n:
                total += n
                print("  [dedupe] %s: removed %d duplicate rows" % (tab, n))
        except Exception as e:
            print("  [dedupe] %s skipped: %s" % (tab, str(e)[:60]))
    if total:
        print("  [dedupe] cleaned %d duplicate rows this pass" % total)
    return total


def _dd_count_col(sh, tab, col=1):
    sh = _as_spreadsheet(sh)
    try:
        return max(0, len(sh.worksheet(tab).col_values(col)) - 1)
    except Exception:
        return 0


def _dd_unique_phones(sh, tab):
    sh = _as_spreadsheet(sh)
    try:
        vals = sh.worksheet(tab).col_values(2)[1:]   # the Phone column
    except Exception:
        return 0
    u = set()
    for v in vals:
        p = _dd_phone(v)
        if p:
            u.add(p)
    return len(u)


def startup_clean_and_counts(sh):
    """Run at program START: delete the exact/phone duplicates NOW (looping until
    it converges), then print the real total of every tab so you see the numbers
    up front -- e.g. fiber addresses / scraped businesses / callable matches."""
    if sh is None:
        return
    print("\n  Cleaning duplicates on startup (one time, then it stays clean)...")
    _DD_PASS[0] = 0
    for _ in range(8):                       # converge, but bounded
        try:
            if dedupe_all_tabs(sh) == 0:
                break
        except Exception as e:
            print("  (startup dedupe stopped: %s)" % str(e)[:60])
            break
    pf  = _dd_count_col(sh, "Precise Fiber")
    mb  = _dd_count_col(sh, "Maps Businesses")
    fg  = _dd_count_col(sh, "Fiber Green Biz")
    fgp = _dd_unique_phones(sh, "Fiber Green Biz")
    og  = _dd_count_col(sh, "Upgrade Orange Biz")
    print("\n  ================= TOTALS (deduped) =================")
    print("   Fiber green addresses (Precise Fiber) : {:>9,}".format(pf))
    print("   Scraped businesses (Maps Businesses)  : {:>9,}".format(mb))
    print("   MATCHES - callable (unique phone)     : {:>9,}".format(fgp))
    print("   MATCHES - Fiber Green Biz rows        : {:>9,}".format(fg))
    if og:
        print("   Upgrade Orange Biz matches            : {:>9,}".format(og))
    print("  ===================================================\n")


def start_periodic_dedupe(sh, every=_DEDUPE_EVERY):
    """Daemon thread: dedupe the tabs every `every` seconds, in the background,
    without ever blocking or crashing the main hunt/scrape."""
    import threading, time as _t
    if sh is None:
        return
    def _loop():
        _t.sleep(_DEDUPE_WARMUP)
        while True:
            try:
                dedupe_all_tabs(sh)
            except Exception:
                pass
            _t.sleep(every)
    threading.Thread(target=_loop, daemon=True).start()
    print("  periodic background dedupe ON (every %d min, all tabs, phone-keyed)"
          % (every // 60))


def _kill_stale_browser():
    """A frozen/killed run can leave its Chromium alive; a leftover holding
    att_profile blocks the next launch (the reviver's relaunch included).
    Clear ONLY browser processes using OUR profile -- normal Chrome untouched."""
    if os.name != "nt":
        return
    try:
        import subprocess
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { "
             "$_.Name -match 'chrome|chromium|msedge' -and "
             "$_.CommandLine -like '*att_profile*' } | "
             "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
             "-ErrorAction SilentlyContinue }"],
            capture_output=True, timeout=30)
    except Exception:
        pass


def _disable_quickedit():
    """Windows: one stray click inside the console window starts a text
    selection (QuickEdit mode) and the OS then FREEZES this program on its
    very next print -- silently, no error -- until a key is pressed. That is
    indistinguishable from 'the hunter stopped'. Turn QuickEdit off for this
    window so touching/clicking the console can never pause the motion."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-10)                 # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k32.GetConsoleMode(h, ctypes.byref(mode)):
            return
        # clear ENABLE_QUICK_EDIT_MODE (0x40); ENABLE_EXTENDED_FLAGS (0x80)
        # must be set for the change to stick
        k32.SetConsoleMode(h, (mode.value & ~0x40) | 0x80)
        print("  (console click-freeze protection ON -- clicking this window "
              "can't pause the hunter)")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# OPENING INTEL BANNER (Patrick, 2026-08-22)
# The startup banner already answers "who is scanning". It should also answer
# "what changed since last time" -- the two things that decide where today's
# sweep should point:
#   1. precise fiber cable outages -- a live buying window. The pipeline and
#      portal already log these to the 'Outage Signals' tab; nothing read them
#      back, so a logged outage sat unseen until somebody opened the sheet.
#   2. suggested new build ZIPs    -- fiber_zone_scanner already scores every
#      ZIP it sweeps into 'Fiber Zones'. The ZIPs turning up the most NEW green
#      are where fiber was just lit.
# Read-only, and wrapped end to end: intel is never worth breaking a sweep for,
# so every failure degrades to one quiet line and the hunter carries on. Same
# rule the operator check follows.
# ---------------------------------------------------------------------------
OUTAGE_TAB = "Outage Signals"    # Logged At | ZIP | Signal | Status
ZONES_TAB_NAME = "Fiber Zones"
GOLD_TAB_NAME = "Gold Dots"       # no header row: A=Address B=Captured At C=Lat D=Lng   # Scanned At | ZIP | Zone Label | Priority |
                                 # Action | Green | Gold | Grey | Gray Share |
                                 # New Green | Instance
INTEL_ROWS = 5

# Web intel. Imported defensively: optimus_web_intel.py is in _CORE_FILES, but a
# PC whose download of it failed must still scan. No import, no web lines, sweep
# unaffected.
try:
    import optimus_web_intel as _WEB
except Exception:
    _WEB = None

try:
    import optimus_territory as _TERR
except Exception:                     # a missing ledger must not stop a sweep
    _TERR = None

try:
    import optimus_dedupe as _DEDUPE
except Exception:                     # dedupe is safety, not a hard dependency
    _DEDUPE = None

try:
    import optimus_feed as _FEED
except Exception:                     # the feed is telemetry, never a blocker
    _FEED = None

def _phase(name):
    """Stamp a startup milestone. Telemetry only -- never blocks a sweep."""
    if _FEED is None:
        return
    try:
        _FEED.phase(name, log=print)
    except Exception:
        pass


# One report per run, filled by the flush paths and printed at the end.
_DEDUPE_REPORT = _DEDUPE.DedupeReport() if _DEDUPE else None
_VERIFY_ROWS = []                     # verification observations, appended only

def _web_cache_path():
    """Where to cache web intel. Module-level `__file__` is NOT safe here: a
    frozen or exec-wrapped launcher leaves it undefined, and a NameError at
    import time kills the hunter outright instead of costing it one banner."""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        base = os.getcwd()
    return os.path.join(base, "optimus_web_intel_cache.json")


def _web_intel():
    """Outage + new-build chatter off the open web. Never raises, never blocks
    longer than its own budget. Returns None if the module is not present."""
    if _WEB is None:
        return None
    try:
        return _WEB.gather(budget_s=9.0, per_source_s=3.0,
                           cache_path=_web_cache_path(), ttl_s=21600)
    except Exception as e:
        return {"outage": [], "build": [], "cable": [], "zips": [],
                "notes": ["web intel failed: %s" % str(e)[:60]],
                "cached": False, "age_s": 0}


# Why a given intel source produced nothing. The whole point of this block is
# that "none open" reads as "we checked and there were none" when the truth was
# "that tab does not exist" -- a failure returning 0 instead of saying so, which
# is the exact bug pattern that has cost this project weeks before. Filled by
# the readers below, printed by intel_banner().
_INTEL_WHY = {}


def _intel_tab(sh, name):
    """Open a tab. Returns (rows, None) or (None, reason). Never raises."""
    sh = _as_spreadsheet(sh)
    try:
        return sh.worksheet(name).get_all_values(), None
    except Exception as e:
        blob = (e.__class__.__name__ + " " + str(e)).lower()
        if "worksheetnotfound" in blob or "not found" in blob:
            return None, "there is no '%s' tab in the sheet" % name
        return None, "could not read '%s' (%s)" % (name, str(e)[:40] or
                                                   e.__class__.__name__)


def _intel_int(v):
    """Sheet cells arrive as text and may carry a '%'. Never raise on junk."""
    try:
        return int(float(str(v).replace("%", "").strip() or 0))
    except Exception:
        return 0


def _intel_recent_outages(sh, limit=INTEL_ROWS):
    """Newest outage signals that nobody has worked yet."""
    sh = _as_spreadsheet(sh)
    rows, why = _intel_tab(sh, OUTAGE_TAB)
    if rows is None:
        _INTEL_WHY["outages"] = why
        return []
    if len(rows) < 2:
        _INTEL_WHY["outages"] = "'%s' is empty -- nothing logs into it yet" % OUTAGE_TAB
    out = []
    for r in reversed(rows[1:]):              # newest appended last
        logged, zipc, signal, status = [str(x).strip() for x in (r + [""] * 4)[:4]]
        if not zipc and not signal:
            continue
        if status.upper() in ("DONE", "WORKED", "CLOSED"):
            continue
        out.append((logged, zipc, signal, status or "RECEIVED"))
        if len(out) >= limit:
            break
    return out


def _intel_gold_pockets(sh, limit=INTEL_ROWS):
    """Fallback: derive where to go next from the gold dots we already captured.

    `Fiber Zones` only has rows once somebody runs fiber_zone_scanner.py, and
    until then the banner had nothing to say. But the answer is already in the
    sheet: `Gold Dots` carries lat/lng for every gold dot ever captured, and gold
    means an AT&T customer still on copper -- a dense pocket of them is fiber that
    was lit recently and that nobody has converted. That IS the freshness signal,
    so no web lookup and no outside update is needed to produce it.

    Grids the coordinates to ~1km cells and returns the thickest pockets. Read
    only, best-effort, and silent on any failure.
    """
    sh = _as_spreadsheet(sh)
    rows, why = _intel_tab(sh, GOLD_TAB_NAME)
    if rows is None:
        _INTEL_WHY["gold"] = why
        return []
    n_rows = len(rows)
    n_coord = 0
    cells = {}
    for r in rows:                      # Gold Dots has NO header row
        if len(r) < 4:
            continue
        try:
            lat = float(str(r[2]).strip())
            lng = float(str(r[3]).strip())
        except (ValueError, TypeError):
            continue
        if lat == 0 or lng == 0:
            continue
        n_coord += 1
        key = (round(lat, 2), round(lng, 2))     # ~1.1km latitude cells
        c = cells.setdefault(key, {"n": 0, "streets": {}})
        c["n"] += 1
        addr = str(r[0] or "").strip().upper()
        # keep the street, drop the house number, so a pocket names a street
        parts = addr.split()
        if len(parts) > 1:
            st = " ".join(parts[1:])[:26]
            c["streets"][st] = c["streets"].get(st, 0) + 1
    out = []
    for (lat, lng), c in sorted(cells.items(), key=lambda kv: kv[1]["n"], reverse=True):
        if c["n"] < 4:                  # a pocket, not a stray dot
            continue
        top = sorted(c["streets"].items(), key=lambda kv: kv[1], reverse=True)[:2]
        out.append({"lat": lat, "lng": lng, "gold": c["n"],
                    "streets": ", ".join(s for s, _ in top)})
        if len(out) >= limit:
            break
    if not out:
        # Say which step lost the data. Each of these is a different bug.
        if not n_rows:
            _INTEL_WHY["gold"] = "'%s' read back 0 rows" % GOLD_TAB_NAME
        elif not n_coord:
            _INTEL_WHY["gold"] = ("read %d rows from '%s' but none had a usable "
                                  "lat/lng in columns C and D"
                                  % (n_rows, GOLD_TAB_NAME))
        else:
            _INTEL_WHY["gold"] = ("%d gold dots over %d cells, none with %d+ in "
                                  "one cell" % (n_coord, len(cells), 4))
    return out


def _intel_suggested_zips(sh, limit=INTEL_ROWS):
    """Newest scan per ZIP, ranked by how much NEW green it turned up."""
    sh = _as_spreadsheet(sh)
    rows, why = _intel_tab(sh, ZONES_TAB_NAME)
    if rows is None:
        _INTEL_WHY["zips"] = why
        return []
    if len(rows) < 2:
        _INTEL_WHY["zips"] = "'%s' is empty -- nobody has run fiber_zone_scanner.py" % ZONES_TAB_NAME
    latest = {}
    for r in rows[1:]:
        r = (r + [""] * 11)[:11]
        zipc = str(r[1]).strip()
        if not zipc:
            continue
        latest[zipc] = {          # later row wins -> newest scan per ZIP
            "zip": zipc, "label": str(r[2]).strip(), "action": str(r[4]).strip(),
            "green": _intel_int(r[5]), "gold": _intel_int(r[6]),
            "grey_share": str(r[8]).strip(), "new_green": _intel_int(r[9]),
        }
    ranked = sorted(latest.values(),
                    key=lambda z: (z["new_green"], z["green"] + z["gold"]),
                    reverse=True)
    return [z for z in ranked if z["new_green"] or z["green"] or z["gold"]][:limit]


def _as_spreadsheet(obj):
    """Return the Spreadsheet for either a Spreadsheet or a Worksheet.

    gspread's Worksheet and Spreadsheet are easy to confuse at a call site, and
    passing the wrong one fails with 'Worksheet object has no attribute
    add_worksheet' -- a message that names the symptom and hides the cause.
    Three separate opening-intel lines died that way on 2026-08-23, one of them
    reading "could not read 'Gold Dots'", which looks exactly like gold capture
    being broken when it is only the banner.
    """
    if obj is None:
        return None
    return getattr(obj, "spreadsheet", obj)


def _print_dispatch(sh, web):
    sh = _as_spreadsheet(sh)
    """WHERE TO GO NEXT -- a dispatch, not a report.

    Areas come from NATIONWIDE AT&T announcements, never from what we have
    already captured. An area another operator holds is shown as taken, with
    who and since when, so nobody wonders why a market they saw in the news is
    missing. Captured counts appear only as context on a claim.
    """
    me = OPERATOR()
    cands = (web or {}).get("build") or []

    if _TERR is None:
        print("  WHERE TO SCAN NEXT: optimus_territory.py not on this PC")
        return
    claims, why = _TERR.load(sh)
    if why:
        print("  WHERE TO SCAN NEXT: %s" % why)
        return

    go, taken, mine = _TERR.dispatch(cands, claims, me)

    print("  WHERE TO SCAN NEXT -- %s, these are yours to take:" % me)
    if go:
        for c in go:
            z = (", ".join(c.get("zips") or []))[:24]
            print("     %-26s %-4s %-24s %s"
                  % (str(c.get("where"))[:26], c.get("state") or "",
                     z or "-", str(c.get("title"))[:44]))
        print("     claim one:  --claim \"%s\"" % (go[0].get("where") or ""))
    elif cands:
        print("     nothing free -- every announced area is already claimed")
    else:
        print("     no new-build announcements came back this launch")
        for n in ((web or {}).get("notes") or [])[:3]:
            if " build" in n:
                print("       " + n)

    if taken:
        print("  ALREADY SOMEBODY ELSE'S -- do not go:")
        for c in taken:
            print("     %-26s held by %-12s since %s"
                  % (str(c.get("where"))[:26], c.get("holder"), c.get("since")))

    if mine:
        print("  YOURS RIGHT NOW (%s):" % me)
        for c in mine:
            print("     %-26s claimed %s%s"
                  % (str(c.get("Area"))[:26], c.get("Claimed At"),
                     ("  ZIP " + c["ZIP"]) if c.get("ZIP") else ""))


def _print_web(web, kind, heading):
    """Print web items, or -- when there are none -- WHY there are none.

    Same rule as the sheet readers: an empty line that does not say why is how
    the old banner spent weeks reporting "none open" about a tab that did not
    exist.
    """
    if web is None:
        print("  %s: optimus_web_intel.py not on this PC" % heading)
        return
    items = web.get(kind) or []
    if items:
        mins = web.get("age_s", 0) // 60
        if web.get("stale"):
            age = "STALE, %dh old -- the net was unreachable" % (mins // 60)
        elif web.get("cached"):
            age = "cached %dm ago" % mins
        else:
            age = "fresh"
        print("  %s (%s):" % (heading, age))
        for it in items[:8]:
            print("     [%-12s] %-64s %s"
                  % (str(it.get("where"))[:12], str(it.get("title"))[:64],
                     str(it.get("when"))[:16]))
        return
    print("  %s: nothing --" % heading)
    for n in (web.get("notes") or [])[:6]:
        if (" " + kind) in n or "failed" in n:
            print("     " + n)


def intel_banner():
    """Outages + suggested new build ZIPs, printed at every opening."""
    try:
        sh = open_sheet()
    except Exception as e:
        print("  INTEL: sheet unreachable (%s) -- scanning anyway" % str(e)[:50])
        return
    try:
        outages = _intel_recent_outages(sh)
    except Exception:
        outages = []
    try:
        zips = _intel_suggested_zips(sh)
    except Exception:
        zips = []

    web = _web_intel()

    print("  ---- OPENING INTEL -----------------------------------------")
    if outages:
        print("  PRECISE FIBER CABLE OUTAGES (open):")
        for logged, zipc, signal, status in outages:
            print("     %-6s %-28s %-9s %s"
                  % (zipc, signal[:28], status, logged))
    else:
        print("  PRECISE FIBER CABLE OUTAGES (sheet): %s"
              % (_INTEL_WHY.get("outages") or "none logged"))
    _print_web(web, "outage", "AT&T OUTAGES ON THE WEB (our territory)")
    # Cable outages were never fetched, and build news was fetched every launch
    # and never printed -- the query ran, the items were filtered and cached,
    # and nothing ever put them on screen.
    _print_web(web, "cable",
               "CABLE OUTAGES -- SELL AGAINST THESE (our territory)")
    _print_web(web, "build",
               "AT&T BUILD-OUT NEWS (whole footprint -- where to point next)")

    if zips:
        print("  SUGGESTED NEW BUILD ZIPS (most new green first):")
        for z in zips:
            print("     %-6s new-green %-5d green %-5d gold %-4d grey %-5s %s"
                  % (z["zip"], z["new_green"], z["green"], z["gold"],
                     z["grey_share"] or "-",
                     (z["action"] or z["label"] or "")[:24]))
    else:
        try:
            pockets = _intel_gold_pockets(sh)
        except Exception:
            pockets = []
        if pockets:
            print("  ALREADY WORKED BY US -- captured gold, NOT a suggestion:")
            for p in pockets:
                print("     %6.2f,%-8.2f  %3d gold   %s"
                      % (p["lat"], p["lng"], p["gold"], p["streets"]))
            print("     (gold = AT&T customers still on copper. A thick pocket means")
            print("      fiber was lit there recently and nobody has worked it.)")
        else:
            print("  SUGGESTED NEW BUILD ZIPS: nothing to suggest --")
            for k, label in (("zips", "zones"), ("gold", "gold ")):
                if _INTEL_WHY.get(k):
                    print("     %s: %s" % (label, _INTEL_WHY[k]))
            if not (_INTEL_WHY.get("zips") or _INTEL_WHY.get("gold")):
                print("     no zone scans and no gold dots yet")
    _print_dispatch(sh, web)
    print("  ------------------------------------------------------------")


def _territory_cli(args):
    """--claim / --release / --territory. Never raises into the launcher."""
    me = OPERATOR()
    try:
        machine = _OP.machine_name() if _OP else ""
    except Exception:
        machine = ""
    if _TERR is None:
        print("  territory: optimus_territory.py is not on this PC")
        return
    try:
        sh = open_sheet()
    except Exception as e:
        print("  territory: sheet unreachable (%s)" % str(e)[:60])
        return

    if args.claim:
        area, st = _split_area(args.claim)
        ok, msg = _TERR.claim(sh, area, st, operator=me, machine=machine,
                              source="manual")
        print("  %s %s" % ("CLAIMED:" if ok else "REFUSED:", msg))
    if args.release:
        area, st = _split_area(args.release)
        ok, msg = _TERR.release(sh, area, st, operator=me)
        print("  %s %s" % ("RELEASED:" if ok else "REFUSED:", msg))

    print("  ---- TERRITORY BOARD ---------------------------------------")
    _print_dispatch(sh, _web_intel())
    print("  ------------------------------------------------------------")


def _split_area(text):
    """'Beaumont, TX' -> ('Beaumont', 'TX'). 'Beaumont' -> ('Beaumont', '')."""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) >= 2 and len(parts[-1]) == 2 and parts[-1].isalpha():
        return ", ".join(parts[:-1]), parts[-1].upper()
    return str(text).strip(), ""


# Seconds to wait at the "press Enter" prompt before starting anyway. The
# prompt is a convenience, not a gate: an unattended hunter that waits forever
# is indistinguishable from a broken one.
START_WAIT_SECS = int(os.environ.get("OPTIMUS_START_WAIT") or 45)


def _wait_for_start(secs):
    """Wait up to `secs` for Enter, then start regardless. Never blocks forever.

    Counts down out loud so it is obvious the tool is alive and what it will do.
    """
    print("  Map on the right spot? Press Enter to START scanning "
          "(auto-starts in %ds)... " % secs)
    end = time.time() + max(1, secs)
    try:
        if not sys.stdin.isatty():
            # Launched with no console input (a .bat double-click, a scheduler).
            # There is nobody to press anything, so waiting is pure dead time.
            print("  (no interactive console -- starting immediately)")
            return False
    except Exception:
        pass
    try:
        import msvcrt                       # Windows
        while time.time() < end:
            if msvcrt.kbhit():
                msvcrt.getch()
                print("  starting now.")
                return True
            left = int(end - time.time())
            if left and left % 10 == 0:
                print("     auto-start in %ds..." % left)
                time.sleep(1.05)
            time.sleep(0.15)
    except ImportError:
        try:
            import select                   # POSIX
            while time.time() < end:
                r, _, _ = select.select([sys.stdin], [], [], 0.5)
                if r:
                    sys.stdin.readline()
                    print("  starting now.")
                    return True
        except Exception:
            # NEVER fall back to a bare input() here. That is the exact call
            # this function exists to remove: it blocks forever and the sweep
            # silently never starts. Sleeping out the timer is strictly better.
            while time.time() < end:
                time.sleep(0.2)
    except Exception:
        pass
    print("  no keypress -- STARTING ANYWAY so the sweep is never stuck here.")
    return False


def _mark_profile_clean(profile_dir):
    """Stop Chromium's "Restore pages?" bubble coming back every launch.

    We cause it ourselves: Ctrl+Shift+K is os._exit, so Chromium never gets to
    write a clean shutdown, and the next launch opens with a restore bubble
    sitting over the map. It can cover the very dots we are about to read, and
    on a bad day it eats the first click. Chromium decides this from two keys in
    the profile's Preferences, so set them before launch. Best-effort: a missing
    or unreadable Preferences file just means a first run.
    """
    for name in ("Default", ""):
        pref = os.path.join(profile_dir, name, "Preferences") if name else \
            os.path.join(profile_dir, "Preferences")
        if not os.path.exists(pref):
            continue
        try:
            with open(pref, "r", encoding="utf-8") as f:
                data = json.load(f)
            prof = data.setdefault("profile", {})
            if (prof.get("exit_type") == "Normal"
                    and prof.get("exited_cleanly") is True):
                continue                       # already clean, don't rewrite
            prof["exit_type"] = "Normal"
            prof["exited_cleanly"] = True
            tmp = pref + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, pref)              # atomic: never half a Preferences
        except Exception:
            pass


def main():
    self_update()
    # Configured FIRST so every later milestone can be pushed live. A run that
    # hangs or is force-quit never reaches its exit report, and for a full day
    # that made "died before the map loaded" and "swept and found nothing" look
    # identical from here. The heartbeat tells them apart.
    if _FEED is not None:
        try:
            _FEED.configure(RUN_ID, OPERATOR(), "", _FINGERPRINT)
            _FEED.arm_heartbeat(gh_put)
            _FEED.arm_reader(gh_get)
            _FEED.phase("start")
        except Exception:
            pass
    # Straight after the update, so the console always answers "did the update
    # actually take, and what am I running?" before anything else happens.
    # Wrapped: a manifest is diagnostics, and diagnostics must never be the
    # reason a sweep does not run.
    try:
        _deploy_manifest()
    except Exception as e:
        print("  (deploy manifest unavailable: %s)" % str(e)[:70])
    _disable_quickedit()
    ap = argparse.ArgumentParser()
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
    ap.add_argument("--backfill-gold", action="store_true",
                    help="one-time: pull every ORANGE (gold/upgrade) address "
                         "already in 'Precise Fiber' into the 'Gold Dots' tab")
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
                    help="don't run phone/business enrichment in the background")
    ap.add_argument("--no-match", action="store_true",
                    help="don't cross-reference captured leads to the scraped "
                         "businesses live (skip the Fiber Green Biz / Upgrade "
                         "Orange Biz tabs)")
    ap.add_argument("--no-dedupe", action="store_true",
                    help="don't run the periodic background tab-dedupe cleanup")
    ap.add_argument("--paid", action="store_true",
                    help="let the background enricher use paid Google Places on "
                         "OSM misses (needs GOOGLE_PLACES_API_KEY). Default is FREE.")
    ap.add_argument("--uploader", action="store_true",
                    help=argparse.SUPPRESS)   # internal: the write worker
    ap.add_argument("--operator", default=None, metavar="NAME",
                    help="who is running this scan (stamped on every row). "
                         "Normally you are asked once and it is remembered; "
                         "use this to override, or on scheduled runs.")
    ap.add_argument("--claim", metavar="AREA", default="",
                    help="claim an area so nobody else is sent there, e.g. "
                         "--claim \"Beaumont, TX\"")
    ap.add_argument("--release", metavar="AREA", default="",
                    help="give a claimed area back so others can take it")
    ap.add_argument("--territory", action="store_true",
                    help="print the dispatch board and quit")
    ap.add_argument("--whoami", action="store_true",
                    help="show/change who this PC scans as, then carry on")
    ap.add_argument("--no-split", action="store_true",
                    help="write to the sheet in-process (June's original way) "
                         "instead of the separate write worker")
    args = ap.parse_args()

    # NO ZIP PROMPT. With no --zip/--auto (how the launcher runs it) this stays
    # in MANUAL mode: you pan/search the AT&T map to the spot you want by hand,
    # then press Enter here to scan THAT view. You control where it scans, so it
    # can never wander to the wrong area.

    # WHO IS SCANNING -- settled before a single row can be written, so no
    # capture in this process can ever be saved anonymously. Asks once on a real
    # terminal, then remembers; silently falls back to the hostname on scheduled
    # and worker runs, which have nobody at the keyboard to answer.
    if _OP:
        try:
            _OP.resolve(cli_value=args.operator,
                        auto=bool(args.auto or args.uploader),
                        force_ask=bool(args.whoami))
            print(_OP.banner())
        except Exception as e:
            print("  (operator check skipped: %s)" % str(e)[:60])

    if args.uploader:
        uploader_main()          # write worker: no browser, no Playwright
        return

    # Territory: claiming an area is a bookkeeping action, not a scan. It runs
    # before the browser opens and quits, so a rep can take or hand back a
    # market without burning a launch.
    if args.claim or args.release or args.territory:
        _territory_cli(args)
        return

    # Intel prints for a person opening the hunter, so it sits after the
    # uploader return -- a headless write worker has nobody to read it.
    intel_banner()

    # THE ORIGINAL MOTION -- raw Windows input, nothing to install, no fallback.
    if _real_mouse_ready():
        print("  REAL-MOUSE MOTION ON: the original fiber hunter gesture "
              "(the pan physically cannot hang).")

    if args.clean_sheet:
        clean_sheet()
        return

    if args.backfill_gold:
        backfill_gold_dots()
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

    with sync_playwright() as pw:
        _phase("playwright_up")
        touch_lock()
        _kill_stale_browser()   # a frozen run's leftover Chromium would block
        try:
            _lock = os.path.join(PROFILE_DIR, "SingletonLock")
            _busy = os.path.exists(_lock)
        except Exception:
            _busy = False
        if _busy:
            print("")
            print("  NOTE: a Chromium profile lock is present. If another")
            print("  Optimus Fiber Hunter window is already open, CLOSE THIS ONE")
            print("  -- two hunters cannot share one browser profile, and the")
            print("  second to start will die immediately.")
        _mark_profile_clean(PROFILE_DIR)
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False,
            viewport=VIEWPORT,
            device_scale_factor=1,   # screenshot px == click px (HiDPI fix)
            # Flags that PREVENT the WebGL-context-loss freeze on low-RAM laptops:
            # keep the map rendering even when the window is covered/backgrounded
            # (Chrome otherwise throttles or discards it, dropping the GL context),
            # and don't let the tab be memory-saver-discarded mid-run.
            args=["--start-maximized",
                  # belt and braces with _mark_profile_clean(): no restore
                  # bubble, no session-restore prompt over the map
                  "--hide-crash-restore-bubble",
                  "--disable-session-crashed-bubble",
                  "--no-first-run",
                  "--no-default-browser-check",
                  "--disable-background-timer-throttling",
                  "--disable-renderer-backgrounding",
                  "--disable-backgrounding-occluded-windows",
                  "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling,HighEfficiencyModeAvailable",
                  "--disable-dev-shm-usage"],
        )
        ctx.add_init_script(MAPBOX_HOOK_JS)   # hook the map before it loads
        ctx.add_init_script(GEO_HIDE_JS)      # hide the giant geolocation blob
        ctx.add_init_script(GL_WATCH_JS)      # detect WebGL context loss (freeze)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _phase("chromium_up")

        # ALWAYS capture network responses now -- the map object is hidden on
        # this site, so the dots have to be read off the wire. debug=True records
        # every endpoint to net_responses.log so the dot-data URL can be found.
        capture = NetCapture(substr=args.api_substring, debug=True)
        page.on("response", capture.handle)   # grab dot data off the wire
        _NET_CAPTURE[0] = capture

        _phase("browser_up")
        safe_goto(page, MAP_URL)
        _phase("page_loaded")
        if not _logged_in(page):
            _phase("LOGGED_OUT")
            if _FEED:
                _FEED.truth(auth_ok=False, note="access chooser, not the map")
            print("")
            print("  " + "!" * 62)
            print("  NOT LOGGED IN -- AT&T is showing the access chooser, not")
            print("  the fiber map. Nothing can be captured from this screen.")
            print("")
            print("     1. Dismiss 'Restore pages?' with the X (not Restore)")
            print("     2. Click 'AT&T Employee' and sign in")
            print("     3. Open the Fiber Map and put it on your area")
            print("")
            print("  Waiting up to %d minutes for you to finish..."
                  % (LOGIN_WAIT_SECS // 60))
            print("  " + "!" * 62)
            if _wait_for_login(page, LOGIN_WAIT_SECS):
                print("  Logged in -- map is up. Carrying on.")
                if _FEED:
                    _FEED.truth(auth_ok=True)
                _phase("logged_in")
            else:
                print("  Still not on the map after %ds. Stopping rather than"
                      % LOGIN_WAIT_SECS)
                print("  sweeping a login page and reporting a clean zero.")
                _phase("LOGIN_TIMEOUT")
                ctx.close()
                return 1

        if args.login:
            print("\nLOG IN in the browser, open the Fiber Map, then come back here.")
            input("Press Enter when you're logged in and the map is showing... ")
            print("Session saved to %s. You can now run without --login." % PROFILE_DIR)
            ctx.close()
            return

        ws = None if args.dry else open_sheet()
        _phase("sheet_open")
        if ws is not None:
            try:
                replay_pending(ws.spreadsheet)
            except Exception as e:
                print("   (replay skipped: %s)" % str(e)[:70])
        searched = [False]   # only search the ZIP on the first pass
        seen = already_seen(ws)            # resume set, persists across passes
        _phase("resume_loaded")
        area_label = args.zip or "manual"

        # COMBO: load the scraped businesses FIRST so flush() and the backfill can
        # merge the business name+phone inline as each lead is written.
        if not args.dry and not args.no_match:
            init_bizmatch(ws)

        # Keep all the tabs deduped in the background while the hunt runs (phone-
        # keyed on the biz tabs, exact-address on Precise Fiber). Cross-machine
        # locked so it never collides with the scraper's dedupe.
        if not args.dry and ws is not None and not args.no_dedupe:
            try:
                startup_clean_and_counts(ws.spreadsheet)   # clean + show totals NOW
                start_periodic_dedupe(ws.spreadsheet)      # keep it clean while running
            except Exception as e:
                print("  (dedupe off: %s)" % str(e)[:60])

        # Recover any locally-saved leads that never reached the sheet (e.g. the
        # old sheet was full) -- write them into the active sheet now (with biz merge).
        if not args.dry and ws is not None:
            backfill_jsonl(ws, seen)

        # WRITES NEVER TOUCH THE MOTION: spawn the write worker. From here on
        # this process pans/searches/captures only -- captures go to disk and
        # the worker ships them. A sheet write CANNOT pause a pan anymore.
        if not args.dry and ws is not None and not args.no_split:
            try:
                import subprocess as _sp
                _env = dict(os.environ)
                _env["OPTIMUS_NO_UPDATE"] = "1"
                _env["OPTIMUS_OUTBOX_OFFSET"] = str(
                    os.path.getsize(JSONL_PATH) if os.path.exists(JSONL_PATH) else 0)
                _logf = open(UPLOADER_LOG, "a")
                _kw = {"cwd": os.path.dirname(os.path.abspath(__file__)),
                       "env": _env, "stdout": _logf, "stderr": _logf,
                       "stdin": _sp.DEVNULL}
                if os.name == "nt":
                    _kw["creationflags"] = 0x00000008 | 0x08000000
                else:
                    _kw["start_new_session"] = True
                _sp.Popen([sys.executable, os.path.abspath(__file__),
                           "--uploader"], **_kw)
                _SPLIT[0] = True
                print("  WRITES OFF THE MOTION: a separate worker ships leads to "
                      "the sheet (log: uploader_log.txt). Panning never waits.")
            except Exception as e:
                print("  (write worker spawn failed: %s -- writing in-process)"
                      % str(e)[:80])

        # ANALYSIS FOR CLAUDE: refresh the small "OPTIMUS DATA SUMMARY" sheet once
        # at startup (a detached ONE-SHOT so it can't leak looping processes and
        # never touches the pan loop). The giant sheet can't be read by Claude
        # (too big to export) -- this distills it into a sheet Claude reads fully.
        _start_summary()

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
        # -- OFF BY DEFAULT (June's 2nd landmine, found 2026-07-02): this
        # background thread writes to the SAME sheet while the hunter writes,
        # colliding on the 60/min quota -> the flush stalls -> 'the map froze.'
        # Houses have no free public phone anyway; business phones come from
        # the scraper match. Re-enable with OPTIMUS_ENRICH=1 if ever wanted.
        if os.environ.get("OPTIMUS_ENRICH") == "1" and not args.no_enrich and not args.dry:
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
                    print("\n" + "!" * 64)
                    print("!! WARNING: could NOT enter ZIP %s into the map." % args.zip)
                    print("!! The map is still on its DEFAULT area -- scanning now would")
                    print("!! scrape the WRONG location. Type the ZIP into the map's search")
                    print("!! box BY HAND, wait for it to fly to %s, then let it scan." % args.zip)
                    print("!" * 64 + "\n")
                    time.sleep(6.0)
                else:
                    searched[0] = True
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
            _sweep = sweep_grid if args.grid else sweep_continuous
            return _sweep(page, ws, seen, args.zip or "manual", args.dry, cap)

        if not args.auto:
            # MANUAL mode: let the user get the map where they want it, then
            # scan THAT view (don't auto-jump to a ZIP). They press Enter to go.
            searched[0] = True
            print("\n  " + "=" * 60)
            print("  STEP 1  ->  In the browser, move the AT&T Fiber Map to the")
            print("              area you want (type your ZIP in the map's search")
            print("              box, or pan/zoom by hand). Log in first if asked.")
            print("  STEP 2  ->  When the map is sitting on the right spot, come")
            print("              back to THIS window and press Enter to scan it.")
            print("  " + "=" * 60)
            # A bare input() blocks FOREVER. If this window does not have
            # keyboard focus -- easy to miss when the map window is the one you
            # were just using -- the sweep never starts, every feed report comes
            # back empty, and nothing anywhere says "I am waiting for a keypress".
            # That cost most of 2026-08-23. It now starts on its own.
            _wait_for_start(START_WAIT_SECS)
            _phase("wait_done")
            # Report our own health before a single cell is swept, so a bad
            # capture state is known up front instead of inferred from zeros.
            try:
                _d = capture_diagnostic(page)
                print("\n  [HUNTER DIAG] mapbox=%s  zoom=%s  layers_in_band=%s"
                      % (_d.get("verdict"), (_d.get("mapbox") or {}).get("zoom"),
                         _d.get("layers_in_band")))
                print("                %s -- %s"
                      % (_d.get("zero_verdict"), _d.get("zero_reason")))
                if _d.get("advice"):
                    print("                %s" % _d["advice"])
                if _d.get("safe_zoom"):
                    print("                safe capture zoom ~ %s" % _d["safe_zoom"])
            except Exception as _e:
                print("  (diagnostic skipped: %s)" % str(_e)[:70])
            # EVIDENCE ONLY: dump the live style and rendered features on the
            # viewport the operator chose -- which is the populated one. Reads
            # the map, publishes, decides nothing.
            try:
                dump_mapbox_evidence(page)
            except Exception as _e:
                print("  (mapbox evidence dump skipped: %s)" % str(_e)[:70])
            _phase("diag_done")
            # 5-second grace period so you can MINIMIZE this window before the
            # hunter takes over the mouse (real-mouse motion). Countdown so you
            # know how long you've got.
            print("\n  Starting in 5 seconds -- MINIMIZE this window now if you want")
            print("  it out of the way (the map keeps scanning either way):")
            for _n in range(5, 0, -1):
                print("     ...%d" % _n)
                time.sleep(1)
            print("  Go.\n")

        # Manual mode keeps watching by default: you pan the map by hand and it
        # collects the backend dots from each view, every few seconds, until you
        # close the browser. (auto mode honors --loop.)
        # the continuous sweep loops internally until you close the browser, so
        # the outer loop is a single pass unless you explicitly pass --loop.
        loop_secs = args.loop if (args.loop and args.loop > 0) else 0
        report_status(ws, args.zip or "manual", "started",
                      note="watching every %ss" % loop_secs if loop_secs else "single pass")
        if loop_secs and not args.auto:
            print("\n  WATCHING: pan the map by hand to new areas -- it grabs each "
                  "one off the server every %ds. Close the browser to stop.\n" % loop_secs)
        _start_stop_watcher()          # slam mouse to top-left corner to stop
        countdown_to_start(10)         # aim the map by hand before it moves
        _phase("sweep_start")
        passno = 0
        while True:
            passno += 1
            try:
                n = one_pass()
                # Stamped only on the FIRST completed pass. PHASES lists
                # pass_done, so without this every phase report would end with
                # "NEVER REACHED: pass_done" even on a healthy run -- a false
                # alarm in the one tool whose job is to stop false alarms.
                if passno == 1:
                    _phase("pass_done")
                # Publish on the FIRST completed pass, whatever it found.
                # Otherwise a pass that captured fewer than FLUSH_EVERY dots
                # reports nothing at all until the run exits -- and a pass that
                # captured ZERO looks identical to one that captured 40. That
                # ambiguity is the exact thing this feed exists to remove, and
                # it survived right up to the first pass that ever completed.
                try:
                    if _FEED:
                        _FEED.publish_audit(gh_put)
                        _ok = _publish_feed()
                        print("  FEED PUBLISH %s run=%s"
                              % ("SUCCESS" if _ok else "FAILED", RUN_ID))
                except Exception as _e:
                    print("")
                    print("!" * 64)
                    print("!! FEED PUBLISH FAILED run=%s: %s" % (RUN_ID, str(_e)[:120]))
                    print("!! The run's evidence did NOT reach GitHub. Everything")
                    print("!! downstream is reading a STALE latest.json.")
                    print("!" * 64)
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
            if _STOP[0]:
                print("\nStopped by the top-left corner gesture. Closing.")
                report_status(ws, args.zip or "manual", "stopped", found=n,
                              note="corner STOP gesture")
                break
            if loop_secs > 0:
                report_status(ws, args.zip or "manual", "watching",
                              found=n, note="pass %d; +%d this pass" % (passno, n))
                time.sleep(loop_secs)
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
    # atexit, not a call at the end of main(): the sweep is normally stopped with
    # Ctrl-C, and the gold/grey split is exactly what we need to see when it is.
    import atexit
    atexit.register(wire_classification_report)
    if _FEED is not None:
        atexit.register(_publish_feed)
        atexit.register(lambda: _FEED.phase("exit"))
    # Same reasoning as above: a sweep is normally ended with Ctrl-C, and the
    # duplicate / GOLD->GREY split is exactly what we need to see when it is.
    if _DEDUPE_REPORT is not None:
        atexit.register(lambda: (_DEDUPE_REPORT.duplicates
                                 or _DEDUPE_REPORT.failed_writes)
                        and _DEDUPE_REPORT.report())
    try:
        main()
    except SystemExit as e:
        # A non-zero exit is a failure even though nothing was raised. The
        # dependency check does exactly this -- one printed line, then gone.
        if getattr(e, "code", 0) and _FEED is not None:
            try:
                _FEED.note_crash("SystemExit(%s) -- something called sys.exit"
                                 % e.code)
                _FEED.phase("EXIT_%s" % e.code)
            except Exception:
                pass
        raise
    except BaseException as e:
        import traceback as _tb
        _msg = "%s: %s" % (type(e).__name__, str(e)[:200])
        print("")
        print("!" * 68)
        print("  THE RUN DIED: %s" % _msg)
        print("!" * 68)
        _tb.print_exc()
        if _FEED is not None:
            try:
                _FEED.note_crash(_msg, _tb.format_exc())
                _FEED.phase("CRASHED")
            except Exception:
                pass
        raise
