#!/usr/bin/env python3
"""
zip_reader.py  --  THE DIRECT READER.  Give it ZIPs, get the fresh green+gold
list. No serpentine panning, no pixels.

HOW IT WORKS
  The AT&T dealer map answers each "Search this area" with a JSON batch of every
  address in view + its status (subscriber_ban + curr_ntwrk_bld_type_cd). So
  instead of crawling a grid pixel-by-pixel, this just: for each ZIP -> type it
  in the map's search box -> click "Search this area" -> read the JSON batch off
  the wire (NetCapture) -> classify with backend_classifier. One fetch per ZIP.

  Output (freshest first = most GREEN+GOLD, least grey):
    - console table
    - "Fresh ZIPs" sheet tab + fresh_zips.csv
    - green+gold ADDRESSES per fresh ZIP -> fresh_addresses.csv
    - pushed to optimus/_live/fresh_zips.txt (Claude-readable)

USAGE
  python zip_reader.py                      # default Houston metro-edge ZIP list
  python zip_reader.py 77493 77433 77515    # specific ZIPs
  python zip_reader.py --file zips.txt      # one ZIP per line
"""
import os
import csv
import sys
import json
import time
import socket
import argparse

from precise_fiber_hunter import (
    self_update, PROFILE_DIR, MAP_URL, VIEWPORT, SEARCH_SETTLE,
    open_map_view, on_map, search_zip, search_this_area, NetCapture, open_sheet,
)
import backend_classifier as bc

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_CODES_PATH = os.path.join(HERE, "build_codes.json")
FRESH_CSV = os.path.join(HERE, "fresh_zips.csv")
ADDR_CSV = os.path.join(HERE, "fresh_addresses.csv")
GH_REPO = "patricksiado-prog/Go-High-Level-MCP-2026-Complete"
GH_BRANCH = "claude/optimus-map-tools-setup-6dcl6o"

# Houston metro-edge / newer-suburb ZIPs (the expansion frontier, not the
# picked-over inner loop). Edit freely or pass your own.
DEFAULT_ZIPS = [
    "77493", "77494", "77449",           # Katy
    "77441",                             # Fulshear
    "77469", "77471", "77406",           # Richmond / Rosenberg
    "77433", "77429",                    # Cypress
    "77484", "77447",                    # Waller / Hockley
    "77384", "77316", "77356",           # Conroe / Montgomery
    "77386", "77389",                    # Spring
    "77515", "77531", "77566",           # Angleton / Clute / Lake Jackson
    "77578",                             # Manvel / Pearland edge
]


def load_build_codes():
    try:
        with open(BUILD_CODES_PATH) as f:
            d = json.load(f)
        bc.FIBER_BUILD_CODES = set(str(x).lower() for x in d.get("fiber", []))
        bc.COPPER_BUILD_CODES = set(str(x).lower() for x in d.get("copper", []))
    except Exception:
        pass


def _wire_records(leads):
    out = []
    for ld in leads or []:
        r = ld.get("raw")
        if isinstance(r, dict) and ("curr_ntwrk_bld_type_cd" in r
                                    or "subscriber_ban" in r):
            out.append(r)
    return out


def _gh_token():
    for p in [os.path.join(os.path.expanduser("~"), "Downloads", "github_token.txt"),
              os.path.join(os.path.expanduser("~"), "Desktop", "github_token.txt"),
              os.path.join(os.path.expanduser("~"), "github_token.txt"),
              os.path.join(os.path.expanduser("~"), "optimus", "github_token.txt"),
              os.path.join(HERE, "github_token.txt"), "github_token.txt"]:
        try:
            if os.path.exists(p) and open(p).read().strip():
                return open(p).read().strip()
        except Exception:
            pass
    return os.environ.get("GITHUB_TOKEN")


def gh_put(path, text):
    token = _gh_token()
    if not token:
        return
    import base64
    import urllib.request
    api = "https://api.github.com/repos/%s/contents/%s" % (GH_REPO, path)
    hdr = {"Authorization": "token %s" % token, "User-Agent": "optimus-zip-reader",
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
    except Exception:
        pass


def _tab(ws, title, header):
    if ws is None:
        return None
    try:
        sh = ws.spreadsheet
        try:
            t = sh.worksheet(title)
            t.clear()
            t.append_row(header)
        except Exception:
            t = sh.add_worksheet(title=title, rows="2000", cols=str(len(header)))
            t.append_row(header)
        return t
    except Exception:
        return None


def read_zip(page, cap, zipc):
    """Search one ZIP, fetch its area once, classify the batch."""
    mark = len(cap.pending)
    search_zip(page, zipc)
    if on_map(page):
        search_this_area(page)
    time.sleep(max(SEARCH_SETTLE, 1.5))
    recs = _wire_records(cap.pending[mark:])
    s = bc.summarize(recs)
    return s, recs


def main():
    self_update()
    ap = argparse.ArgumentParser(description="Direct reader: ZIPs -> fresh green+gold list.")
    ap.add_argument("zips", nargs="*", help="ZIP codes (default: Houston metro-edge list)")
    ap.add_argument("--file", help="file with one ZIP per line")
    ap.add_argument("--no-update", action="store_true")
    args = ap.parse_args()

    zips = list(args.zips)
    if args.file and os.path.exists(args.file):
        zips += [ln.strip() for ln in open(args.file) if ln.strip()]
    if not zips:
        zips = DEFAULT_ZIPS

    load_build_codes()
    host = socket.gethostname()
    results = []

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

        print("\nReading %d ZIPs (one fetch each) ...\n" % len(zips))
        print("  %-7s %6s %5s %5s %6s  %s" % ("ZIP", "GREEN", "GOLD", "GREY", "grey%", "verdict"))
        for zc in zips:
            try:
                s, recs = read_zip(page, cap, zc)
            except Exception as e:
                if any(k in str(e).lower() for k in ("closed", "crash", "target")):
                    print("\nWindow closed -- stopping."); break
                print("  %-7s  (error: %s)" % (zc, str(e)[:50])); continue
            elig = s["green"] + s["gold"]
            print("  %-7s %6d %5d %5d %5.0f%%  %s%s"
                  % (zc, s["green"], s["gold"], s["grey"], s["grey_pct"],
                     s["verdict"], "  <-- FRESH" if s["verdict"] == "FRESH" else ""))
            results.append((zc, s["green"], s["gold"], s["grey"], s["grey_pct"],
                            elig, s["verdict"], s.get("green_addresses", [])))

        try:
            ctx.close()
        except Exception:
            pass

    # rank: freshest first = most green+gold, then least grey
    results.sort(key=lambda r: (-r[5], r[4]))

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = ["OPTIMUS FRESH ZIPS  %s  host=%s" % (ts, host),
             "ranked by GREEN+GOLD (fresh first):", "",
             "%-7s %6s %5s %5s %6s %8s  %s" % ("ZIP", "GREEN", "GOLD", "GREY", "grey%", "elig", "verdict")]
    for zc, g, o, y, gp, elig, verd, _addrs in results:
        lines.append("%-7s %6d %5d %5d %5.0f%% %8d  %s" % (zc, g, o, y, gp, elig, verd))
    gh_put("optimus/_live/fresh_zips.txt", "\n".join(lines))

    try:
        with open(FRESH_CSV, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["zip", "green", "gold", "grey", "grey_pct", "eligible", "verdict"])
            for zc, g, o, y, gp, elig, verd, _ in results:
                w.writerow([zc, g, o, y, "%.0f" % gp, elig, verd])
        with open(ADDR_CSV, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["zip", "green_address"])
            for zc, g, o, y, gp, elig, verd, addrs in results:
                for a in addrs:
                    w.writerow([zc, a])
    except Exception:
        pass

    # sheet tab
    ws = open_sheet()
    t = _tab(ws, "Fresh ZIPs", ["ZIP", "Green", "Gold", "Grey", "Grey%", "Eligible", "Verdict"])
    if t is not None:
        for zc, g, o, y, gp, elig, verd, _ in results:
            try:
                t.append_row([zc, g, o, y, "%.0f%%" % gp, elig, verd])
            except Exception:
                pass

    print("\n=========== FRESH ZIPS (best first) ===========")
    fresh = [r for r in results if r[6] == "FRESH"]
    if fresh:
        for zc, g, o, y, gp, elig, verd, _ in fresh:
            print("  %-7s  GREEN %d + GOLD %d  (grey %.0f%%)  -> FRESH" % (zc, g, o, gp))
        print("\nGreen+gold addresses saved to %s" % ADDR_CSV)
    else:
        print("  No FRESH ZIPs in this batch -- all mature/empty. Try more edge ZIPs.")
    print("Full ranking in the 'Fresh ZIPs' tab + optimus/_live/fresh_zips.txt")
    print("===============================================")


if __name__ == "__main__":
    main()
