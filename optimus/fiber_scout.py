#!/usr/bin/env python3
"""
fiber_scout.py  --  NEW-FIBER FINDER (a scout, NOT a lead recorder).

WHAT IT DOES
  Scans the AT&T dealer fiber map and flags JUST-LIT areas: viewports with lots
  of GREEN (eligible non-customers) + GOLD (copper-upgrade) dots and little/NO
  GREY (existing fiber customers). Grey share is the freshness signal -- a
  brand-new fiber zone has ~no grey yet (nobody's a customer there). As a zone
  ages, grey climbs. So:
       no/low grey + plenty of green+gold  ->  FRESH  (new fiber, go here)
       some grey                            ->  WORKING
       high grey share                      ->  MATURE (worked out, skip)

  It KEEPS MOVING continuously (serpentine pan, just like the hunter) until you
  close the window -- it does not stop after a fixed grid.

  It also CAPTURES THE BACKEND (the F12 / network traffic) once it's panned a
  few times, and writes it to a "Backend Capture" tab so Claude can analyse the
  dot endpoint + fields remotely. No separate program to install.

OUTPUT (all readable on Drive -- no screenshots needed)
  - "Fiber Scout" tab : one row per cell with dots (green/gold/grey + verdict)
  - "Backend Capture" tab : the dot endpoint(s), tile fields, parsed addresses
  - local: a screenshot of each FRESH/WORKING cell in ./fresh_zones/

USAGE
  python fiber_scout.py                 # position the map, press Enter, surveys until you close it
  python fiber_scout.py --cols 6        # wider serpentine strip
  python fiber_scout.py --survey-out 3  # zoom OUT 3x first so each view covers more ground
  python fiber_scout.py --auto          # no 'press Enter' pause

Reuses the hunter's proven browser/map driver + the canonical colour detector.
"""
import os
import csv
import json
import time
import socket
import argparse

# Reuse the proven driver + detector from the hunter (importing is safe: the
# hunter guards its CLI behind `if __name__ == "__main__"`).
from precise_fiber_hunter import (
    self_update, PROFILE_DIR, MAP_URL, VIEWPORT,
    open_map_view, on_map, mouse_drag, zoom, find_map_dots, open_sheet, NetCapture,
)
from optimus_dot_detect import zone_freshness, FRESH_MIN_ELIGIBLE

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT_DIR = os.path.join(HERE, "fresh_zones")
CSV_PATH = os.path.join(HERE, "fresh_zones.csv")
SCOUT_TAB = "Fiber Scout"          # freshness results land here (Claude-readable)
BACKEND_TAB = "Backend Capture"    # the F12/network capture lands here


def _tab(ws, title, header, clear=False):
    """Get/create a tab in the leads sheet. Returns a worksheet or None."""
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
    """Best-effort append (never blocks the scan)."""
    if t is None:
        return
    try:
        t.append_row([str(c)[:480] for c in row])
    except Exception:
        pass


def write_backend(ws, cap, host):
    """Dump the captured backend traffic (endpoints, tile fields, parsed leads,
    serviceability JSON) to the 'Backend Capture' tab so Claude can analyse it."""
    t = _tab(ws, BACKEND_TAB,
             ["Time", "Kind", "URL / Field / Address", "Type", "Bytes/Count", "Sample"],
             clear=True)
    if t is None:
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    _w(t, [ts, "START", host, "", "", "F12/network capture"])
    rows = sorted(cap.seen_urls.items(), key=lambda kv: -kv[1][2])
    for base, (ct, hits, mx) in rows[:25]:
        _w(t, [ts, "ENDPOINT", base, ct, "%d B / %d hits" % (mx, hits), ""])
    if cap.tile_keys:
        _w(t, [ts, "TILE FIELDS", ", ".join(sorted(cap.tile_keys)), "",
               "%d fields" % len(cap.tile_keys), ""])
    leads = cap.pending
    _w(t, [ts, "LEADS PARSED", "", "", "%d" % len(leads), ""])
    for ld in leads[:6]:
        _w(t, [ts, "SAMPLE LEAD", str(ld.get("address")), "status=%s" % ld.get("status"),
               "lat=%s lng=%s ban=%s" % (ld.get("lat"), ld.get("lng"), ld.get("ban")), ""])
    raw = os.path.join(HERE, "serviceability_raw.json")
    if os.path.exists(raw):
        try:
            data = json.load(open(raw))
            keys = list(data.keys()) if isinstance(data, dict) else ["<list of %d>" % len(data)]
            _w(t, [ts, "JSON TOP KEYS", ", ".join(map(str, keys)), "", "", ""])
            _w(t, [ts, "JSON SAMPLE", "", "", "", json.dumps(data)[:1500]])
        except Exception:
            pass
    _w(t, [ts, "DONE", host, "", "%d endpoints" % len(rows), "read the Backend Capture tab"])
    print("  -> wrote the backend capture to the 'Backend Capture' tab.")


def scan_cell(page):
    """Count GREEN / GOLD / GREY in the current viewport and classify freshness."""
    dots, gray = find_map_dots(page)
    green = sum(1 for _x, _y, c in dots if c == "GREEN")
    gold = sum(1 for _x, _y, c in dots if c == "GOLD")
    label, gray_share = zone_freshness(green, gold, gray)
    return green, gold, gray, gray_share, label


def main():
    self_update()
    ap = argparse.ArgumentParser(description="Scout the AT&T map for NEW fiber areas (green+gold, no grey).")
    ap.add_argument("--cols", type=int, default=4, help="serpentine strip width before stepping down (default 4)")
    ap.add_argument("--survey-out", type=int, default=0,
                    help="zoom OUT this many times first so each viewport covers more ground")
    ap.add_argument("--auto", action="store_true", help="no 'press Enter' pause (unattended)")
    ap.add_argument("--no-update", action="store_true", help="skip the GitHub auto-pull on start")
    args = ap.parse_args()

    os.makedirs(SHOT_DIR, exist_ok=True)
    fresh = []   # (idx, down, col, green, gold, gray, gray_share, label, shot)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, viewport=VIEWPORT,
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        cap = NetCapture(debug=True)            # capture backend traffic in the background
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
            print("Zooming out %dx to survey wider ..." % args.survey_out)
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
        idx = 0
        col = 0
        down = 0
        direction = "right"
        backend_done = False
        while True:
            idx += 1
            try:
                green, gold, gray, gray_share, label = scan_cell(page)
            except Exception as e:
                if any(k in str(e).lower() for k in ("closed", "crash", "target")):
                    print("\nWindow closed -- stopping."); break
                print("scan error: %s" % str(e)[:80]); break

            elig = green + gold
            tag = {"FRESH": "*** FRESH (NEW FIBER)", "WORKING": " ~ working",
                   "MATURE": "   mature (skip)", "EMPTY": "   empty"}.get(label, label)
            print("cell %3d [down %d col %d]  GREEN %3d  GOLD %3d  GREY %3d  grey%%=%.0f%%  -> %s"
                  % (idx, down, col, green, gold, gray, gray_share * 100, tag))

            if (green + gold + gray) > 0:
                _w(sws, [time.strftime("%Y-%m-%d %H:%M:%S"), host, "d%dc%d" % (down, col),
                         green, gold, gray, "%.0f%%" % (gray_share * 100), label, ""])

            if label in ("FRESH", "WORKING") and elig >= 1:
                shot = os.path.join(SHOT_DIR, "zone_%03d_%s_g%d_o%d_grey%d.png"
                                    % (idx, label, green, gold, gray))
                try:
                    page.screenshot(path=shot)
                except Exception:
                    shot = ""
                fresh.append((idx, down, col, green, gold, gray, gray_share, label, shot))

            # one-time backend capture once we've panned enough to trigger the fetches
            if not backend_done and idx >= 8:
                write_backend(ws, cap, host)
                backend_done = True

            # CONTINUOUS serpentine motion: across a strip of width --cols, then
            # step down and reverse -- forever, until the window closes.
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

        # on exit: local CSV + ranked summary + DONE to the sheet
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
        for z in fresh[:10]:
            i, dn, cc, g, o, gy, gs, lb, sh = z
            _w(sws, [ts1, host, "TOP d%dc%d" % (dn, cc), g, o, gy,
                     "%.0f%%" % (gs * 100), lb, "top spot to hunt"])
        _w(sws, [ts1, host, "DONE", "", "", "", "", "%d fresh/working" % len(fresh),
                 "survey stopped"])
        if not backend_done:          # never reached 8 cells -> still dump what we got
            write_backend(ws, cap, host)

        print("\n=========== NEW-FIBER SCOUT RESULTS ===========")
        if not fresh:
            print("No fresh/working cells -- area read as MATURE/EMPTY. Try a newer suburb")
            print("(La Porte 77571, Katy 77449, Cypress 77433, Spring 77386, Pearland 77584).")
        else:
            print("Fresh/working cells found: %d  (top ones):" % len(fresh))
            for z in fresh[:10]:
                i, dn, cc, g, o, gy, gs, lb, sh = z
                print("  GREEN %3d + GOLD %3d  (grey %d, %.0f%%)  %-7s  %s"
                      % (g, o, gy, gs * 100, lb, os.path.basename(sh)))
            print("Screenshots in: %s" % SHOT_DIR)
        print("Results are also in the 'Fiber Scout' + 'Backend Capture' sheet tabs.")
        print("===============================================")

        try:
            ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
