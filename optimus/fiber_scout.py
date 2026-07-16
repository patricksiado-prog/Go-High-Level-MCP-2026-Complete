#!/usr/bin/env python3
"""
fiber_scout.py  --  NEW-FIBER FINDER (a scout, NOT a lead recorder).

WHAT IT DOES
  Scans the AT&T dealer fiber map and flags JUST-LIT areas: viewports with lots
  of GREEN (eligible non-customers) + GOLD (copper-upgrade) dots and little/NO
  GREY (existing fiber customers). Grey share is the freshness signal -- a
  brand-new fiber zone has ~no grey yet. Higher grey = older/worked area.
       no/low grey + plenty of green+gold  ->  FRESH  (new fiber, go here)
       some grey                            ->  WORKING
       high grey share                      ->  MATURE (worked out, skip)

  It KEEPS MOVING continuously (serpentine pan + 'Search this area' each cell,
  exactly like the hunter) until you close the window.

  It also CAPTURES THE BACKEND (the F12 / network traffic) and writes it where
  Claude can read it -- the Google Sheet AND GitHub (so it works even when Drive
  is flaky). Nothing extra to install.

OUTPUT (all Claude-readable)
  - Sheet tab "Fiber Scout"     : per-cell freshness (green/gold/grey + verdict)
  - Sheet tab "Backend Capture" : dot endpoints, tile fields, parsed addresses
  - GitHub optimus/_live/backend_capture.txt + scout_findings.txt (if a
    github_token.txt is present -- reliable read channel)
  - local: a screenshot of each FRESH/WORKING cell in ./fresh_zones/

USAGE
  python fiber_scout.py                 # position map, press Enter, surveys until you close it
  python fiber_scout.py --cols 6        # wider serpentine strip
  python fiber_scout.py --survey-out 3  # zoom OUT first so each view covers more ground
"""
import os
import csv
import json
import time
import socket
import base64
import argparse

# --- self-heal: older launchers download fiber_scout.py but not its newer helper
# files, which crashes the import below (ModuleNotFoundError: backend_classifier).
# Fetch any missing helper from the repo raw so the scout runs no matter which
# launcher started it. Only acts when a file is actually missing.
def _self_heal_deps():
    _here = os.path.dirname(os.path.abspath(__file__))
    _raw = ("https://raw.githubusercontent.com/patricksiado-prog/"
            "Go-High-Level-MCP-2026-Complete/claude/optimus-map-tools-setup-6dcl6o/optimus")
    for _f in ("backend_classifier.py", "build_codes.json",
               "optimus_dot_detect.py", "precise_fiber_hunter.py"):
        _p = os.path.join(_here, _f)
        if not os.path.exists(_p):
            try:
                import urllib.request
                urllib.request.urlretrieve("%s/%s" % (_raw, _f), _p)
                print("  (self-heal: downloaded missing %s)" % _f)
            except Exception:
                pass


_self_heal_deps()

from precise_fiber_hunter import (
    self_update, PROFILE_DIR, MAP_URL, VIEWPORT, SEARCH_SETTLE,
    open_map_view, on_map, mouse_drag, zoom, find_map_dots, open_sheet, NetCapture,
    search_this_area, find_creds, SCOPES,
)
from optimus_dot_detect import zone_freshness, FRESH_MIN_ELIGIBLE
import backend_classifier as bc

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_CODES_PATH = os.path.join(HERE, "build_codes.json")
SHOT_DIR = os.path.join(HERE, "fresh_zones")
CSV_PATH = os.path.join(HERE, "fresh_zones.csv")
SCOUT_TAB = "Fiber Scout"
BACKEND_TAB = "Backend Capture"
GH_REPO = "patricksiado-prog/Go-High-Level-MCP-2026-Complete"
GH_BRANCH = "claude/optimus-map-tools-setup-6dcl6o"


# ---- GitHub write (reliable read channel for Claude when Drive is flaky) ----
def _gh_token():
    for p in [os.path.join(os.path.expanduser("~"), "Downloads", "github_token.txt"),
              os.path.join(os.path.expanduser("~"), "Desktop", "github_token.txt"),
              os.path.join(os.path.expanduser("~"), "github_token.txt"),
              os.path.join(os.path.expanduser("~"), "optimus", "github_token.txt"),
              os.path.join(HERE, "github_token.txt"), "github_token.txt"]:
        try:
            if os.path.exists(p):
                t = open(p).read().strip()
                if t:
                    return t
        except Exception:
            pass
    return os.environ.get("GITHUB_TOKEN")


def gh_put(path, text):
    """Best-effort: commit a small text file to the repo so Claude can read it at
    the raw URL. Needs github_token.txt (or GITHUB_TOKEN); no token -> skip."""
    token = _gh_token()
    if not token:
        return False
    import urllib.request
    api = "https://api.github.com/repos/%s/contents/%s" % (GH_REPO, path)
    hdr = {"Authorization": "token %s" % token, "User-Agent": "optimus-scout",
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
        print("  -> pushed %s to GitHub (Claude can read it)." % path)
        return True
    except Exception as e:
        print("  (GitHub push skipped: %s)" % str(e)[:70])
        return False


def push_live_tally(host, cells, green, gold, grey, fresh_cells, leads, last):
    """REAL-TIME COUNTER (Patrick 2026-07-16 "I wanna know how many leads are
    getting pulled in real time"). Push a tiny running-totals file to GitHub
    (optimus/_live/LIVE_COUNTS.txt) as the survey runs, so Claude can git-pull
    and read the current count at ANY moment -- no need to open/parse the whole
    180k-row sheet. Small file, updated every few cells; best-effort (no token
    -> silently skips, exactly like the other pushes)."""
    txt = (
        "OPTIMUS SCOUT -- LIVE COUNTS\n"
        "updated: %s   host: %s\n"
        "STATUS: surveying (this file updates every ~15 cells while it runs)\n"
        "----------------------------------------\n"
        "cells scanned:            %d\n"
        "GREEN dots (leads):       %d\n"
        "GOLD dots (upgrades):     %d\n"
        "GREY dots (existing):     %d\n"
        "ELIGIBLE (green+gold):    %d\n"
        "FRESH/WORKING cells:      %d\n"
        "CALLABLE LEADS this run:  %d\n"
        "last cell: %s\n"
        % (time.strftime("%Y-%m-%d %H:%M:%S"), host, cells, green, gold, grey,
           green + gold, fresh_cells, leads, last))
    gh_put("optimus/_live/LIVE_COUNTS.txt", txt)


# ---- sheet tabs ----
def _tab(ws, title, header, clear=False):
    if ws is None:
        return None
    try:
        sh = ws.spreadsheet
        try:
            t = sh.worksheet(title)
            if clear:
                t.clear()
                t.append_row(header)
        except Exception:
            t = sh.add_worksheet(title=title, rows="3000", cols=str(len(header)))
            t.append_row(header)
        return t
    except Exception as e:
        print("(%s tab unavailable: %s)" % (title, str(e)[:60]))
        return None


def _w(t, row):
    if t is None:
        return
    try:
        t.append_row([str(c)[:480] for c in row])
    except Exception:
        pass


_ASSET_EXT = (".png", ".gif", ".jpg", ".jpeg", ".svg", ".ico", ".css", ".js",
              ".woff", ".woff2", ".ttf")


def _feed_url(cap):
    """Best guess at AT&T's serviceability / address-data feed URL from the
    captured traffic -- so a direct backend reader can be built without a test."""
    best = ""
    best_bytes = -1
    for base, meta in getattr(cap, "seen_urls", {}).items():
        ct, hits, mx = meta
        low = base.lower()
        if "mapbox" in low or low.endswith(_ASSET_EXT):
            continue
        looks_feed = (any(k in low for k in ("serviceability", "serviceab",
                      "availab")) or (("fiber" in low or "/api/" in low
                      or "referral" in low or "graphql" in low
                      or low.endswith(".json")) and "youachieve" in low))
        if looks_feed and mx > best_bytes:
            best, best_bytes = base, mx
    return best


def push_capture_extras(cap, host):
    """Upgrade: push the EXACT feed URL, the full non-asset endpoint list, and
    the raw AT&T serviceability JSON to GitHub so the backend can be read/built
    from a normal scout run -- no separate test needed."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    feed = _feed_url(cap)

    lines = ["OPTIMUS NET ENDPOINTS  %s  host=%s" % (ts, host),
             "SERVICEABILITY FEED URL: %s" % (feed or "(not identified)"), "",
             "All non-asset endpoints (biggest first) -- the feed is in here:"]
    rows = sorted(getattr(cap, "seen_urls", {}).items(), key=lambda kv: -kv[1][2])
    for base, (ct, hits, mx) in rows:
        low = base.lower()
        if "mapbox" in low or low.endswith(_ASSET_EXT):
            continue
        lines.append("%10dB  %3dx  %-26s %s" % (mx, hits, (ct or "")[:26], base[:200]))
    gh_put("optimus/_live/net_endpoints.txt", "\n".join(lines))

    # raw AT&T serviceability response (full records, every field) -- capped so
    # the GitHub contents API accepts it.
    raw = os.path.join(HERE, "serviceability_raw.json")
    if os.path.exists(raw):
        try:
            body = open(raw).read()
            gh_put("optimus/_live/serviceability_raw.json", body[:900000])
        except Exception:
            pass
    # push the request recipe on the SAME reliable trigger as net_endpoints, so
    # backend_exchange.txt can't get lost when a run stops early.
    try:
        push_backend_exchange(cap, host)
    except Exception:
        pass
    return feed


def push_backend_exchange(cap, host):
    """Push AT&T's captured serviceability request SHAPE (method, URL, POST
    params, header names) so a direct reader can replicate the call. Auth
    secrets are already redacted in cap.req_capture; the full request stays
    local only (serviceability_request_FULL.json)."""
    ex = getattr(cap, "req_capture", None)
    if not ex:
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = ["OPTIMUS BACKEND EXCHANGE (AT&T serviceability request)  %s  host=%s" % (ts, host),
             "", "METHOD : %s" % ex.get("method"),
             "URL    : %s" % ex.get("url"),
             "RESP   : %s  %s" % (ex.get("resp_status"), ex.get("resp_content_type")),
             "", "POST BODY (the params AT&T needs -- lat/lng/radius/etc.):",
             str(ex.get("post_data") or "(none: GET request, params are in the URL above)"),
             "", "REQUEST HEADERS (auth/cookie/token values REDACTED):"]
    for k, v in (ex.get("headers_redacted") or {}).items():
        lines.append("   %s: %s" % (k, v))
    lines += ["", "Secrets are redacted here. The full request (with your session "
              "auth) is saved LOCAL ONLY as serviceability_request_FULL.json and "
              "is gitignored -- never commit it."]
    gh_put("optimus/_live/backend_exchange.txt", "\n".join(lines))
    print("  -> backend exchange (request shape, secrets redacted) pushed.")


def write_full_analysis(ws, cap, host):
    """UPGRADE #1: run the FULL backend analysis over ALL captured records (not
    the 250-sample) and push it, so the whole feed's schema + codes can be
    learned in one look -> optimus/_live/backend_analysis.txt + a sheet tab."""
    recs = _wire_records(getattr(cap, "pending", []))
    if not recs:
        return
    report = bc.deep_analyze(recs)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    gh_put("optimus/_live/backend_analysis.txt",
           "OPTIMUS FULL BACKEND ANALYSIS  %s  host=%s  records=%d\n\n%s"
           % (ts, host, len(recs), report))
    t = _tab(ws, "Backend Analysis", ["Time", "Line"], clear=True)
    for ln in report.splitlines():
        if ln.strip():
            _w(t, [ts, ln])
    print("  -> full backend analysis pushed (%d records)." % len(recs))


def write_backend(ws, cap, host):
    """Dump the captured backend traffic to the 'Backend Capture' sheet tab AND
    push it to GitHub (optimus/_live/backend_capture.txt) so Claude can analyse
    it even when Drive is down."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    t = _tab(ws, BACKEND_TAB,
             ["Time", "Kind", "URL / Field / Address", "Type", "Bytes/Count", "Sample"],
             clear=True)
    lines = ["OPTIMUS BACKEND CAPTURE  %s  host=%s" % (ts, host)]

    def row(kind, a="", b="", c="", d=""):
        _w(t, [ts, kind, a, b, c, d])
        lines.append("%-13s| %s | %s | %s | %s" % (kind, a, b, c, d))

    rows = sorted(cap.seen_urls.items(), key=lambda kv: -kv[1][2])
    lines.append("--- ENDPOINTS (biggest first) ---")
    for base, (ct, hits, mx) in rows[:25]:
        row("ENDPOINT", base, ct, "%dB/%dhits" % (mx, hits))
    if cap.tile_keys:
        lines.append("--- TILE FIELDS (dot data schema) ---")
        row("TILE FIELDS", ", ".join(sorted(cap.tile_keys)), "", "%d fields" % len(cap.tile_keys))
    leads = cap.pending
    lines.append("--- LEADS PARSED: %d ---" % len(leads))
    row("LEADS PARSED", "", "", str(len(leads)))
    for ld in leads[:6]:
        row("SAMPLE LEAD", str(ld.get("address")), "status=%s" % ld.get("status"),
            "lat=%s lng=%s ban=%s" % (ld.get("lat"), ld.get("lng"), ld.get("ban")))
    raw = os.path.join(HERE, "serviceability_raw.json")
    if os.path.exists(raw):
        try:
            data = json.load(open(raw))
            keys = list(data.keys()) if isinstance(data, dict) else ["<list of %d>" % len(data)]
            row("JSON TOP KEYS", ", ".join(map(str, keys)))
            lines.append("--- JSON SAMPLE ---")
            lines.append(json.dumps(data)[:3000])
        except Exception:
            pass
    # BACKEND INSPECT: the cross-tab (build_type x customer) that reveals which
    # curr_ntwrk_bld_type_cd codes mean GOLD (copper) vs GREY (fiber). Run the
    # scout over a GREEN area (e.g. 77004), read this block, then put the codes
    # in optimus/build_codes.json -- that completes the classifier.
    recs = _wire_records(leads)
    if not recs and os.path.exists(raw):
        try:
            recs = _wire_records(
                [{"raw": r} for r in bc.load_leads(open(raw).read())])
        except Exception:
            recs = []
    if recs:
        insp = bc.inspect(recs)
        lines.append("--- BACKEND INSPECT (fill build_codes.json from this) ---")
        lines.append(insp)
        for ln in insp.splitlines()[:15]:
            if ln.strip():
                row("INSPECT", ln.strip())
        s = bc.summarize(recs)
        row("BACKEND VERDICT", s["verdict"],
            "green=%d gold=%d grey=%d cust=%d skip=%d" % (
                s["green"], s["gold"], s["grey"],
                s["customer_undecoded"], s["skip"]),
            "grey%%=%.1f" % s["grey_pct"])
    # UPGRADE: catch the exact feed URL + full endpoint list + raw JSON and push
    # them, so the backend reader can be built from a normal run (no test.py).
    feed = push_capture_extras(cap, host)
    row("SERVICEABILITY FEED URL", feed or "(not identified -- see net_endpoints.txt)")
    lines.append("SERVICEABILITY FEED URL: %s" % (feed or "(not identified)"))

    row("DONE", host, "", "%d endpoints" % len(rows))
    gh_put("optimus/_live/backend_capture.txt", "\n".join(lines))


def load_build_codes():
    """Once a real inspect() run over a green area (e.g. Third Ward 77004)
    reveals which curr_ntwrk_bld_type_cd values mean an existing FIBER customer
    (grey) vs a COPPER customer (gold), drop them into optimus/build_codes.json
    as {"fiber": [...], "copper": [...]} -- no code edit needed. Until then
    customers score as CUSTOMER (conservative, never falsely grey)."""
    try:
        with open(BUILD_CODES_PATH) as f:
            d = json.load(f)
        bc.FIBER_BUILD_CODES = set(str(x).lower() for x in d.get("fiber", []))
        bc.COPPER_BUILD_CODES = set(str(x).lower() for x in d.get("copper", []))
        if bc.FIBER_BUILD_CODES or bc.COPPER_BUILD_CODES:
            print("Build codes loaded: fiber=%s copper=%s"
                  % (sorted(bc.FIBER_BUILD_CODES), sorted(bc.COPPER_BUILD_CODES)))
    except Exception:
        pass


def _wire_records(leads):
    """The raw AT&T records (subscriber_ban / curr_ntwrk_bld_type_cd) riding in
    the captured leads -- only those that actually carry the backend fields."""
    out = []
    for ld in leads or []:
        r = ld.get("raw")
        if isinstance(r, dict) and ("curr_ntwrk_bld_type_cd" in r
                                    or "subscriber_ban" in r):
            out.append(r)
    return out


def scan_cell(page, wire_leads=None):
    """Score one view. BACKEND-FIRST: when this cell captured real AT&T records
    off the wire, classify THOSE (the truth from the dealer-map backend JSON).
    The pixel path is only the fallback for cells where nothing crossed the
    wire -- it can misread the map legend as one gold dot every cell."""
    recs = _wire_records(wire_leads)
    if recs:
        s = bc.summarize(recs)
        # 7th value: the actual GREEN + GOLD addresses (callable leads) from the
        # backend -- so a FRESH cell yields leads to call, not just a count.
        return (s["green"], s["gold"], s["grey"], s["grey_pct"] / 100.0,
                s["verdict"], "backend %d recs (cust-undecoded %d)"
                % (len(recs), s["customer_undecoded"]),
                (s.get("green_addresses", []), s.get("gold_addresses", [])))
    dots, gray = find_map_dots(page)
    green = sum(1 for _x, _y, c in dots if c == "GREEN")
    gold = sum(1 for _x, _y, c in dots if c == "GOLD")
    label, gray_share = zone_freshness(green, gold, gray)
    # pixel path has no addresses (dots only) -- empty lists.
    return (green, gold, gray, gray_share, label,
            "pixel fallback (legend can fake 1 gold)", ([], []))


def _sturdy_pan(page, direction, tries=3):
    """STURDY MOTION ported from the hunter ('motion that can't hang'): retry the
    proven mouse_drag a few times so a transient drag hiccup doesn't stop the
    survey. Returns True if any attempt lands; False only if all fail (window
    truly stuck/closed). The hunter never restarts -- it just keeps panning."""
    for _ in range(max(1, tries)):
        try:
            if mouse_drag(page, direction):
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _sturdy_goto(page, url, tries=5):
    """STURDY STARTUP: the map load is the one spot a network blip (VPN/wifi
    hiccup, ERR_INTERNET_DISCONNECTED, a slow AT&T redirect) kills the whole
    Scout before it does any work. Retry the goto a few times with a growing
    wait instead of crashing on the first miss -- same 'motion that can't hang'
    idea as the pan retry, applied to launch. Raises only if every try fails
    (internet is genuinely down, not just hiccuping)."""
    last = None
    for i in range(max(1, tries)):
        try:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            return True
        except Exception as e:
            last = e
            wait = 3 * (i + 1)   # 3s, 6s, 9s, 12s ...
            print("  map load failed (%s) -- retry %d/%d in %ds ..."
                  % (str(e).split("\n")[0][:80], i + 1, tries, wait))
            time.sleep(wait)
    print("\nCould not reach the AT&T map after %d tries. This is a NETWORK "
          "problem on this machine, not the Scout:\n"
          "  - check wifi / that a browser can open youachieve.att.com\n"
          "  - close any leftover Chrome windows and rerun\n"
          "  - if on VPN/McAfee, pause it and rerun\n" % tries)
    raise last


# PRIVATE scout sheet (Patrick 2026-07-16 "I don't wanna show the fresh green to
# the guys yet ... scout fresh green i wanna keep those discoveries to myself").
# The scout writes its fresh finds to a SEPARATE private spreadsheet that only
# Patrick sees -- the shared team sheet (hunter/scraper feed it) is untouched.
PRIVATE_SHEET_TITLE = "OPTIMUS SCOUT FRESH (PRIVATE)"
OWNER_EMAIL = "patricksiado@gmail.com"
PRIVATE_ID_FILE = os.path.join(os.path.expanduser("~"), "optimus",
                               "scout_private_sheet_id.txt")


def open_private_sheet():
    """Open (or CREATE) a PRIVATE spreadsheet only Patrick can see, for the
    scout's fresh-green discoveries. The service account creates + owns it and
    shares it with Patrick (writer); the sheet id is cached locally so the same
    private sheet is reused every run. Returns a worksheet handle (_tab uses
    ws.spreadsheet), or None on failure -- NEVER falls back to the team sheet, so
    a failure keeps discoveries out of the team's view rather than leaking them."""
    import gspread
    from google.oauth2.service_account import Credentials
    creds_file = find_creds()
    if not creds_file:
        print("No creds -> can't open the private scout sheet; fresh leads stay "
              "in the local CSV + _live files (NOT sent to the team).")
        return None
    try:
        client = gspread.authorize(
            Credentials.from_service_account_file(creds_file, scopes=SCOPES))
    except Exception as e:
        print("  (private sheet auth failed: %s)" % str(e)[:80])
        return None
    sh = None
    try:                                        # 1) reuse the cached id
        if os.path.exists(PRIVATE_ID_FILE):
            sid = open(PRIVATE_ID_FILE).read().strip()
            if sid:
                sh = client.open_by_key(sid)
    except Exception:
        sh = None
    if sh is None:                              # 2) find it by title
        try:
            sh = client.open(PRIVATE_SHEET_TITLE)
        except Exception:
            sh = None
    if sh is None:                              # 3) create it
        try:
            sh = client.create(PRIVATE_SHEET_TITLE)
            print("  Created your NEW private scout sheet: %s" % PRIVATE_SHEET_TITLE)
        except Exception as e:
            print("  (couldn't create the private sheet: %s)" % str(e)[:80])
            return None
    try:                                        # share with Patrick (best-effort)
        sh.share(OWNER_EMAIL, perm_type="user", role="writer")
    except Exception:
        pass
    try:                                        # cache the id for next run
        os.makedirs(os.path.dirname(PRIVATE_ID_FILE), exist_ok=True)
        open(PRIVATE_ID_FILE, "w").write(sh.id)
    except Exception:
        pass
    try:
        ws = sh.sheet1
        print("  PRIVATE scout sheet ready (only YOU see it): "
              "https://docs.google.com/spreadsheets/d/%s" % sh.id)
        return ws
    except Exception as e:
        print("  (private sheet tab error: %s)" % str(e)[:80])
        return None


def main():
    # NO in-process self-update/relaunch (Patrick 2026-07-16 "stop the relaunch
    # it's not helpful cuz I gotta login and center it"). self_update() re-execs
    # the whole process when the code changed, which opens a FRESH browser --
    # losing his AT&T login and his centered map every time. The launcher
    # (RUN_SCOUT.bat) already curls the newest fiber_scout.py + helpers from
    # GitHub on every start, so we already run the latest code WITHOUT a relaunch.
    # So: never relaunch here. Close + reopen the launcher yourself to get a new
    # version, once, on your terms.
    ap = argparse.ArgumentParser(description="Scout the AT&T map for NEW fiber areas.")
    ap.add_argument("--cols", type=int, default=4, help="serpentine strip width before stepping down")
    ap.add_argument("--survey-out", type=int, default=0, help="zoom OUT this many times first")
    ap.add_argument("--auto", action="store_true", help="no 'press Enter' pause")
    ap.add_argument("--no-update", action="store_true", help="skip the GitHub auto-pull on start")
    ap.add_argument("--to-team", action="store_true",
                    help="write fresh finds to the SHARED team sheet (the guys will see them). "
                         "Default: PRIVATE sheet only you see.")
    args = ap.parse_args()

    load_build_codes()
    os.makedirs(SHOT_DIR, exist_ok=True)
    fresh = []
    fresh_leads = []   # (cell, verdict, GREEN/GOLD, address) -- callable leads from fresh cells

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, viewport=VIEWPORT,
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        cap = NetCapture(debug=True)
        page.on("response", cap.handle)

        print("Opening the AT&T fiber map ...")
        _sturdy_goto(page, MAP_URL)
        time.sleep(4)
        open_map_view(page)
        time.sleep(2)
        if not on_map(page):
            open_map_view(page)
            time.sleep(2)

        if args.survey_out:
            print("Zooming out %dx ..." % args.survey_out)
            zoom(page, args.survey_out, "out")
            time.sleep(1.5)

        if not args.auto:
            try:
                input("\nPosition/zoom the map over the area to survey, then press Enter ... ")
            except EOFError:
                pass

        # WHERE fresh finds go: PRIVATE by default (only Patrick), or the SHARED
        # team sheet with --to-team when he wants to release a run. A failed
        # private open returns None (CSV + _live only) -- it never silently
        # leaks to the team sheet.
        to_team = args.to_team or os.environ.get("SCOUT_TO_TEAM", "").strip().lower() in ("1", "true", "yes", "y")
        if to_team:
            print("Writing fresh finds to the SHARED TEAM sheet (--to-team) -- the guys WILL see these.")
            ws = open_sheet()
        else:
            print("Writing fresh finds to your PRIVATE sheet (default) -- the team does NOT see these.")
            ws = open_private_sheet()
            if ws is None:
                print("  (private sheet unavailable -- fresh leads stay in the local CSV + _live "
                      "files only, still NOT sent to the team.)")
        sws = _tab(ws, SCOUT_TAB,
                   ["Time", "Host", "Cell", "Green", "Gold", "Grey", "Grey%", "Verdict", "Note"])
        host = socket.gethostname()
        _w(sws, [time.strftime("%Y-%m-%d %H:%M:%S"), host, "START", "", "", "", "",
                 "SURVEY", "continuous (close window to stop)"])

        print("\nSurveying CONTINUOUSLY -- it keeps panning until you close the window.\n")
        idx = col = down = 0
        direction = "right"
        backend_done = False
        tot_green = tot_gold = tot_grey = fresh_cells = 0   # real-time tally
        while True:
            idx += 1
            try:
                mark = len(cap.pending)        # wire leads BEFORE this cell
                if on_map(page):
                    search_this_area(page)     # load the new view's dots first
                time.sleep(SEARCH_SETTLE)
                green, gold, gray, gray_share, label, via, cell_addrs = scan_cell(
                    page, cap.pending[mark:])
            except Exception as e:
                if any(k in str(e).lower() for k in ("closed", "crash", "target")):
                    print("\nWindow closed -- stopping."); break
                print("scan error: %s" % str(e)[:80]); break

            elig = green + gold
            tot_green += green; tot_gold += gold; tot_grey += gray
            tag = {"FRESH": "*** FRESH (NEW FIBER)", "WORKING": " ~ working",
                   "MATURE": "   mature (skip)", "EMPTY": "   empty"}.get(label, label)
            print("cell %3d [down %d col %d]  GREEN %3d  GOLD %3d  GREY %3d  grey%%=%.0f%%  -> %s  [%s]"
                  % (idx, down, col, green, gold, gray, gray_share * 100, tag, via))

            if (green + gold + gray) > 0:
                _w(sws, [time.strftime("%Y-%m-%d %H:%M:%S"), host, "d%dc%d" % (down, col),
                         green, gold, gray, "%.0f%%" % (gray_share * 100), label, via])

            if label in ("FRESH", "WORKING") and elig >= 1:
                fresh_cells += 1
                shot = os.path.join(SHOT_DIR, "zone_%03d_%s_g%d_o%d_grey%d.png"
                                    % (idx, label, green, gold, gray))
                try:
                    page.screenshot(path=shot)
                except Exception:
                    shot = ""
                fresh.append((idx, down, col, green, gold, gray, gray_share, label, shot))
                # capture the actual callable leads from this fresh cell
                g_addr, o_addr = cell_addrs
                for a in g_addr:
                    if a:
                        fresh_leads.append(("d%dc%d" % (down, col), label, "GREEN", a))
                for a in o_addr:
                    if a:
                        fresh_leads.append(("d%dc%d" % (down, col), label, "GOLD", a))

            if not backend_done and idx >= 8:
                # push EVERYTHING mid-run (not just at the end) so a run that
                # stops early ("motion stopped") still delivers the full analysis
                # + AT&T request shape for the direct reader.
                write_backend(ws, cap, host)
                write_full_analysis(ws, cap, host)
                push_backend_exchange(cap, host)
                backend_done = True
            # refresh only the analysis occasionally as more area is captured
            # (every 100 cells, not 20 -- avoids commit spam). The request recipe
            # is static once captured, so it's NOT re-pushed here.
            elif backend_done and idx % 100 == 0:
                write_full_analysis(ws, cap, host)

            # REAL-TIME COUNT: push the running tally every 15 cells so Claude
            # can read "how many so far" at any moment (tiny file; 15-cell
            # cadence keeps commit traffic sane while still feeling live).
            if idx % 15 == 0:
                last = ("d%dc%d GREEN %d GOLD %d GREY %d -> %s"
                        % (down, col, green, gold, gray, label))
                push_live_tally(host, idx, tot_green, tot_gold, tot_grey,
                                fresh_cells, len(fresh_leads), last)

            # THE HUNTER'S MOTION, verbatim (Patrick 2026-07-16 "use the price
            # hunter motion"): the hunter FIRES the drag and keeps going -- its
            # real Windows-mouse drag (_drag_real) physically pans the map and
            # can't hang, and its sweep loops IGNORE the drag's return value and
            # never stop for a bad pan. Its whole philosophy: "the cure is
            # motion that can't hang, not restarts." So the scout now pans the
            # same way -- drag, keep surveying, NO stall counter, NO giving up
            # on motion. A genuinely closed/crashed window is still caught by
            # the scan_cell try/except above ('closed'/'crash'/'target'), which
            # is the ONLY thing that stops the survey. Close the window to stop.
            if col >= args.cols - 1:
                mouse_drag(page, "down")
                down += 1
                col = 0
                direction = "left" if direction == "right" else "right"
            else:
                mouse_drag(page, direction)
                col += 1

        # exit: local CSV + ranked summary -> sheet + GitHub
        try:
            with open(CSV_PATH, "w", newline="") as f:
                wr = csv.writer(f)
                wr.writerow(["idx", "down", "col", "green", "gold", "grey",
                             "grey_share", "label", "screenshot"])
                for z in fresh:
                    i, dn, cc, g, o, gy, gs, lb, sh = z
                    wr.writerow([i, dn, cc, g, o, gy, "%.2f" % gs, lb, os.path.basename(sh)])
        except Exception:
            pass

        fresh.sort(key=lambda x: (-(x[3] + x[4]), x[6]))
        ts1 = time.strftime("%Y-%m-%d %H:%M:%S")
        flines = ["OPTIMUS SCOUT FINDINGS  %s  host=%s" % (ts1, host),
                  "fresh/working cells: %d" % len(fresh), "TOP:"]
        for z in fresh[:12]:
            i, dn, cc, g, o, gy, gs, lb, sh = z
            _w(sws, [ts1, host, "TOP d%dc%d" % (dn, cc), g, o, gy,
                     "%.0f%%" % (gs * 100), lb, "top spot to hunt"])
            flines.append("  d%dc%d  GREEN %d + GOLD %d  (grey %d, %.0f%%)  %s  %s"
                          % (dn, cc, g, o, gy, gs * 100, lb, os.path.basename(sh)))
        _w(sws, [ts1, host, "DONE", "", "", "", "", "%d fresh/working" % len(fresh), "survey stopped"])
        push_live_tally(host, idx, tot_green, tot_gold, tot_grey, len(fresh),
                        len(fresh_leads), "survey stopped (final count)")
        if not backend_done:
            write_backend(ws, cap, host)
        write_full_analysis(ws, cap, host)
        push_backend_exchange(cap, host)
        gh_put("optimus/_live/scout_findings.txt", "\n".join(flines))

        # FRESH LEADS: the actual callable green/gold addresses from fresh cells,
        # written to a "Fresh Leads" tab + fresh_leads.csv + pushed so they can be
        # read precisely and worked/called. (Green = new fiber, Gold = upgrade.)
        nga = sum(1 for r in fresh_leads if r[2] == "GREEN")
        noa = sum(1 for r in fresh_leads if r[2] == "GOLD")
        llines = ["OPTIMUS FRESH LEADS  %s  host=%s" % (ts1, host),
                  "green=%d  gold=%d  from %d fresh/working cells" % (nga, noa, len(fresh)),
                  "", "cell | type | address"]
        for cell, verd, typ, addr in fresh_leads:
            llines.append("%s | %s | %s" % (cell, typ, addr))
        gh_put("optimus/_live/fresh_leads.txt", "\n".join(llines))
        try:
            import csv as _csv
            with open(os.path.join(HERE, "fresh_leads.csv"), "w", newline="") as _f:
                _w2 = _csv.writer(_f)
                _w2.writerow(["cell", "verdict", "type", "address"])
                _w2.writerows(fresh_leads)
        except Exception:
            pass
        lt = _tab(ws, "Fresh Leads", ["Time", "Cell", "Verdict", "Type", "Address"])
        for cell, verd, typ, addr in fresh_leads:
            _w(lt, [ts1, cell, verd, typ, addr])

        print("\n=========== NEW-FIBER SCOUT RESULTS ===========")
        if not fresh:
            print("No fresh/working cells -- area read as MATURE/EMPTY. Try a newer suburb.")
        else:
            print("Fresh/working cells found: %d  (top ones):" % len(fresh))
            for z in fresh[:10]:
                i, dn, cc, g, o, gy, gs, lb, sh = z
                print("  GREEN %3d + GOLD %3d  (grey %d, %.0f%%)  %-7s  %s"
                      % (g, o, gy, gs * 100, lb, os.path.basename(sh)))
        print("Results in the 'Fiber Scout' + 'Backend Capture' tabs and on GitHub (optimus/_live/).")
        print("===============================================")

        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
