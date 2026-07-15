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

from precise_fiber_hunter import (
    self_update, PROFILE_DIR, MAP_URL, VIEWPORT, SEARCH_SETTLE,
    open_map_view, on_map, mouse_drag, zoom, find_map_dots, open_sheet, NetCapture,
    search_this_area,
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
    return feed


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
        return (s["green"], s["gold"], s["grey"], s["grey_pct"] / 100.0,
                s["verdict"], "backend %d recs (cust-undecoded %d)"
                % (len(recs), s["customer_undecoded"]))
    dots, gray = find_map_dots(page)
    green = sum(1 for _x, _y, c in dots if c == "GREEN")
    gold = sum(1 for _x, _y, c in dots if c == "GOLD")
    label, gray_share = zone_freshness(green, gold, gray)
    return green, gold, gray, gray_share, label, "pixel fallback (legend can fake 1 gold)"


def main():
    self_update()
    ap = argparse.ArgumentParser(description="Scout the AT&T map for NEW fiber areas.")
    ap.add_argument("--cols", type=int, default=4, help="serpentine strip width before stepping down")
    ap.add_argument("--survey-out", type=int, default=0, help="zoom OUT this many times first")
    ap.add_argument("--auto", action="store_true", help="no 'press Enter' pause")
    ap.add_argument("--no-update", action="store_true", help="skip the GitHub auto-pull on start")
    args = ap.parse_args()

    load_build_codes()
    os.makedirs(SHOT_DIR, exist_ok=True)
    fresh = []

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, viewport=VIEWPORT,
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        cap = NetCapture(debug=True)
        page.on("response", cap.handle)

        print("Opening the AT&T fiber map ...")
        page.goto(MAP_URL, timeout=60000)
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

        ws = open_sheet()
        sws = _tab(ws, SCOUT_TAB,
                   ["Time", "Host", "Cell", "Green", "Gold", "Grey", "Grey%", "Verdict", "Note"])
        host = socket.gethostname()
        _w(sws, [time.strftime("%Y-%m-%d %H:%M:%S"), host, "START", "", "", "", "",
                 "SURVEY", "continuous (close window to stop)"])

        print("\nSurveying CONTINUOUSLY -- it keeps panning until you close the window.\n")
        idx = col = down = 0
        direction = "right"
        backend_done = False
        while True:
            idx += 1
            try:
                mark = len(cap.pending)        # wire leads BEFORE this cell
                if on_map(page):
                    search_this_area(page)     # load the new view's dots first
                time.sleep(SEARCH_SETTLE)
                green, gold, gray, gray_share, label, via = scan_cell(
                    page, cap.pending[mark:])
            except Exception as e:
                if any(k in str(e).lower() for k in ("closed", "crash", "target")):
                    print("\nWindow closed -- stopping."); break
                print("scan error: %s" % str(e)[:80]); break

            elig = green + gold
            tag = {"FRESH": "*** FRESH (NEW FIBER)", "WORKING": " ~ working",
                   "MATURE": "   mature (skip)", "EMPTY": "   empty"}.get(label, label)
            print("cell %3d [down %d col %d]  GREEN %3d  GOLD %3d  GREY %3d  grey%%=%.0f%%  -> %s  [%s]"
                  % (idx, down, col, green, gold, gray, gray_share * 100, tag, via))

            if (green + gold + gray) > 0:
                _w(sws, [time.strftime("%Y-%m-%d %H:%M:%S"), host, "d%dc%d" % (down, col),
                         green, gold, gray, "%.0f%%" % (gray_share * 100), label, via])

            if label in ("FRESH", "WORKING") and elig >= 1:
                shot = os.path.join(SHOT_DIR, "zone_%03d_%s_g%d_o%d_grey%d.png"
                                    % (idx, label, green, gold, gray))
                try:
                    page.screenshot(path=shot)
                except Exception:
                    shot = ""
                fresh.append((idx, down, col, green, gold, gray, gray_share, label, shot))

            if not backend_done and idx >= 8:
                write_backend(ws, cap, host)
                backend_done = True

            if col >= args.cols - 1:
                ok = mouse_drag(page, "down")
                down += 1
                col = 0
                direction = "left" if direction == "right" else "right"
            else:
                ok = mouse_drag(page, direction)
                col += 1
            if not ok:
                print("\nMotion stopped (window closed?). Stopping."); break

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
        if not backend_done:
            write_backend(ws, cap, host)
        write_full_analysis(ws, cap, host)
        gh_put("optimus/_live/scout_findings.txt", "\n".join(flines))

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
