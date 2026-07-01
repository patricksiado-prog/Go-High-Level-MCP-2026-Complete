#!/usr/bin/env python3
"""
att_test.py  --  is it US or AT&T? A one-shot HEALTH CHECK of the AT&T fiber map
that runs the SAME steps the hunter runs and prints a clear PASS/FAIL report you
can screenshot. It tells us whether the hunter "stopping / not panning" is our
code or AT&T changing their site.

It reuses the hunter's own helpers (open_map_view, on_map, _map_canvas_box,
find_map_dots, mouse_drag, search_this_area, NetCapture) so a PASS here means the
hunter's building blocks still work; a FAIL pins the exact step that broke.

CHECKS (each prints PASS / FAIL / WARN):
  1. PAGE LOADS          - the AT&T page opens at all
  2. LOGGED IN           - we're not bounced to a login/sign-in screen
  3. MAP OPENS           - the "Fiber Availability Map" reveals the dot map
  4. MAP CANVAS          - the Mapbox canvas element is present (page or frame)
  5. DOTS RENDER         - green/gold/grey dots are actually drawn
  6. PAN MOVES           - a mouse-drag actually shifts the view (the #1 symptom)
  7. SEARCH CONTROL      - the "Search this area" button is found
  8. SERVICEABILITY FEED - AT&T's dot/address data is seen on the wire

Writes the same summary to an "AT&T Test" tab in the sheet + att_test_report.txt
locally, and dumps every endpoint the page hit to net_responses.log (so if AT&T
renamed the dot feed, we can see the new URL).

USAGE
  python att_test.py            # opens map, position over dots, press Enter, it tests
  python att_test.py --auto     # no pause (tests whatever view loads)

Run this ALONE -- close the hunter first (it shares the att_profile login and two
programs can't hold that profile at once).
"""
import os
import sys
import time
import socket
import argparse
import hashlib

from precise_fiber_hunter import (
    self_update, PROFILE_DIR, MAP_URL, VIEWPORT, SEARCH_SETTLE,
    open_map_view, on_map, _map_canvas_box, find_map_dots, mouse_drag,
    search_this_area, dump_clickables, open_sheet, NetCapture,
)

HERE = os.path.dirname(os.path.abspath(__file__))
TAB = "AT&T Test"
REPORT = os.path.join(HERE, "att_test_report.txt")

RESULTS = []   # (step, verdict, detail)


def record(step, verdict, detail=""):
    """Log one check line to console + the results list. verdict in
    PASS/FAIL/WARN."""
    mark = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]"}.get(verdict, "[??]")
    line = "%s  %-20s %s" % (mark, step, detail)
    print(line)
    RESULTS.append((step, verdict, detail))


def _shot_hash(page):
    """A cheap fingerprint of what's on screen -- used to tell if a pan actually
    moved the map (different pixels = it moved)."""
    try:
        raw = page.screenshot(type="png")
        return hashlib.md5(raw).hexdigest()
    except Exception:
        return None


def _looks_logged_out(page):
    """True if the page is showing a login / sign-in wall instead of the portal
    or map."""
    try:
        low = (page.content() or "").lower()
    except Exception:
        return False
    # strong sign-in signals; the real portal has none of these front-and-center
    signals = ["sign in to your account", "forgot your password", "att access id",
               "user id", "log in to continue", "please sign in"]
    hits = sum(1 for s in signals if s in low)
    # a password field visible on load is the clearest tell
    try:
        pw = page.query_selector("input[type=password]")
        if pw and pw.is_visible():
            hits += 2
    except Exception:
        pass
    return hits >= 2


def main():
    self_update()
    ap = argparse.ArgumentParser(description="Health-check the AT&T fiber map (us vs them).")
    ap.add_argument("--auto", action="store_true", help="no 'press Enter' pause")
    ap.add_argument("--no-update", action="store_true", help="skip the GitHub auto-pull")
    args = ap.parse_args()

    print("\n" + "=" * 64)
    print("  AT&T FIBER MAP  --  HEALTH CHECK  (us or them?)")
    print("=" * 64 + "\n")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            ctx = pw.chromium.launch_persistent_context(
                PROFILE_DIR, headless=False, viewport=VIEWPORT,
                args=["--disable-blink-features=AutomationControlled"])
        except Exception as e:
            record("BROWSER LAUNCH", "FAIL",
                   "profile busy? close the hunter first (%s)" % str(e)[:50])
            _finish(None)
            return
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        cap = NetCapture(debug=True)      # sniff every response to find the dot feed
        page.on("response", cap.handle)

        # 1) PAGE LOADS ------------------------------------------------------
        try:
            page.goto(MAP_URL, timeout=60000)
            time.sleep(4)
            title = (page.title() or "").strip()
            record("PAGE LOADS", "PASS", "title: %s" % (title[:40] or "(blank)"))
        except Exception as e:
            record("PAGE LOADS", "FAIL", "goto failed: %s" % str(e)[:50])
            _finish(cap)
            ctx.close()
            return

        # 2) LOGGED IN -------------------------------------------------------
        if _looks_logged_out(page):
            record("LOGGED IN", "FAIL",
                   "hit a sign-in wall -- re-run the hunter with --login")
        else:
            record("LOGGED IN", "PASS", "no sign-in wall")

        # 3) MAP OPENS -------------------------------------------------------
        open_map_view(page)
        time.sleep(2)
        if not on_map(page):
            open_map_view(page)
            time.sleep(2)
        if on_map(page):
            record("MAP OPENS", "PASS", "Fiber map is showing")
        else:
            record("MAP OPENS", "FAIL",
                   "'Fiber Availability Map' didn't reveal the map (AT&T layout change?)")

        if not args.auto:
            try:
                input("\nPosition the map over a DOTTED area, then press Enter to test ... ")
            except EOFError:
                pass

        # 4) MAP CANVAS ------------------------------------------------------
        box = _map_canvas_box(page)
        if box:
            record("MAP CANVAS", "PASS",
                   "canvas %dx%d found" % (int(box["width"]), int(box["height"])))
        else:
            record("MAP CANVAS", "WARN",
                   "no canvas element (hidden in a frame -- pan uses the screen region)")

        # 5) DOTS RENDER -----------------------------------------------------
        try:
            dots, gray = find_map_dots(page)
            n = len(dots)
            if n or gray:
                record("DOTS RENDER", "PASS",
                       "%d green/gold + %d grey visible" % (n, gray))
            else:
                record("DOTS RENDER", "WARN",
                       "0 dots in view (empty area, or dots not drawn -- try another spot)")
        except Exception as e:
            record("DOTS RENDER", "FAIL", "dot scan errored: %s" % str(e)[:50])

        # 6) PAN MOVES (the big one) ----------------------------------------
        before = _shot_hash(page)
        moved = mouse_drag(page, "right")
        time.sleep(SEARCH_SETTLE)
        after = _shot_hash(page)
        if before and after and before != after:
            record("PAN MOVES", "PASS", "drag shifted the view")
        elif not moved:
            record("PAN MOVES", "FAIL", "mouse_drag couldn't run (no canvas/region)")
        else:
            record("PAN MOVES", "FAIL",
                   "view identical after drag -- map isn't panning (AT&T gesture change?)")

        # 7) SEARCH CONTROL --------------------------------------------------
        found_search = search_this_area(page)
        if found_search:
            record("SEARCH CONTROL", "PASS", "'Search this area' clicked")
        else:
            record("SEARCH CONTROL", "WARN",
                   "no 'Search this area' control this view (renamed? see controls dump above)")

        # give the fetch a moment, then pan once more to be sure it fires
        time.sleep(SEARCH_SETTLE)
        mouse_drag(page, "down")
        time.sleep(SEARCH_SETTLE)
        search_this_area(page)
        time.sleep(1.5)

        # 8) SERVICEABILITY FEED --------------------------------------------
        # did AT&T's dot/address data show up on the wire?
        feed_hits = 0
        feed_url = ""
        for base, (ct, hits, mx) in cap.seen_urls.items():
            low = base.lower()
            if any(k in low for k in ("serviceability", "serviceab", "availab", "fiber")):
                if not _is_noise(low):
                    feed_hits += hits
                    if not feed_url or mx > 0:
                        feed_url = base
        parsed = len(cap.pending)
        if parsed > 0:
            record("SERVICEABILITY FEED", "PASS",
                   "%d addresses parsed off the wire" % parsed)
        elif feed_hits > 0:
            record("SERVICEABILITY FEED", "WARN",
                   "feed hit (%s) but 0 parsed -- schema may have changed" % feed_url[:50])
        else:
            record("SERVICEABILITY FEED", "FAIL",
                   "no serviceability/availability call seen -- fetch not firing")

        # endpoint dump so a renamed feed is visible
        try:
            cap.dump_debug(os.path.join(HERE, "net_responses.log"))
        except Exception:
            pass

        _finish(cap)

        if not args.auto:
            try:
                input("\nPress Enter to close ... ")
            except EOFError:
                pass
        ctx.close()


def _is_noise(low):
    """Skip basemap/font/asset URLs that merely contain 'fiber' etc."""
    return any(low.endswith(e) for e in
               (".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js",
                ".woff", ".woff2", ".ttf", ".ico"))


def _verdict():
    """Overall read: which side changed."""
    steps = {s: v for s, v, _ in RESULTS}
    fails = [s for s, v, _ in RESULTS if v == "FAIL"]
    if not fails:
        return "ALL CLEAR -- the map + hunter building blocks all work. If the " \
               "hunter still stalls, it's parked in a built-out (all-grey) area " \
               "or running alongside another program on the same login."
    # map failing steps to a likely cause
    if "PAGE LOADS" in fails or "LOGGED IN" in fails:
        return "THEM/LOGIN -- couldn't even load or stay logged in. Re-login " \
               "(hunter --login) and check attX is up. Not a code bug."
    if "MAP OPENS" in fails or "DOTS RENDER" in fails:
        return "LIKELY THEM -- the page loads + you're logged in, but the MAP/DOTS " \
               "changed (AT&T reworked the map UI). Our motion code is fine; the " \
               "open-map / dot-render step needs updating to their new layout."
    if "PAN MOVES" in fails:
        return "PAN BROKE -- the map isn't moving on a drag. Either AT&T changed " \
               "the map gesture/canvas, or the canvas moved into a frame we don't " \
               "reach. This is the 'not panning' symptom -- see MAP CANVAS above."
    if "SERVICEABILITY FEED" in fails:
        return "FEED CHANGED -- panning works but AT&T's dot/address call didn't " \
               "fire or was renamed. Check net_responses.log for the new endpoint " \
               "and point the capture at it."
    return "MIXED -- see the failed steps above."


def _finish(cap):
    """Print the verdict + write the report to the sheet and a local file."""
    print("\n" + "=" * 64)
    print("  VERDICT")
    print("=" * 64)
    verdict = _verdict()
    print("  " + verdict + "\n")

    host = socket.gethostname()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")

    # local report (always works, even with no sheet/Drive)
    try:
        with open(REPORT, "w") as f:
            f.write("AT&T FIBER MAP HEALTH CHECK  %s  (%s)\n" % (ts, host))
            f.write("=" * 60 + "\n")
            for step, v, detail in RESULTS:
                f.write("%-6s %-20s %s\n" % (v, step, detail))
            f.write("\nVERDICT: %s\n" % verdict)
        print("  (report saved -> %s)" % REPORT)
    except Exception:
        pass

    # best-effort to the sheet so it's readable remotely
    try:
        ws = open_sheet()
        if ws is not None:
            sh = ws.spreadsheet
            try:
                t = sh.worksheet(TAB)
                t.clear()
            except Exception:
                t = sh.add_worksheet(title=TAB, rows="200", cols="4")
            rows = [["Time", "Result", "Step", "Detail"]]
            for step, v, detail in RESULTS:
                rows.append([ts, v, step, str(detail)[:480]])
            rows.append([ts, "VERDICT", "", verdict])
            t.append_rows(rows, value_input_option="RAW")
            print("  (also wrote the 'AT&T Test' tab in your sheet)")
    except Exception as e:
        print("  (sheet write skipped: %s)" % str(e)[:60])


if __name__ == "__main__":
    main()
