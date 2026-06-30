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

  It does NOT record individual green-dot leads (that's the hunter's job). It
  only tells you WHERE the new fiber is, so you can point the hunter + scraper
  at a fresh area instead of guessing.

OUTPUT
  - live verdict per viewport (FRESH / WORKING / MATURE / EMPTY + counts)
  - a screenshot of every FRESH/WORKING cell saved to ./fresh_zones/ so you can
    see the streets/neighborhood and navigate there
  - a row per cell appended to ./fresh_zones.csv
  - a ranked summary of the freshest spots at the end

USAGE
  python fiber_scout.py                 # position the map, press Enter, it surveys a 4x4 grid
  python fiber_scout.py --cols 6 --rows 6
  python fiber_scout.py --survey-out 3  # zoom OUT 3x first so each cell covers more ground
  python fiber_scout.py --auto          # no 'press Enter' pause (unattended)

Reuses the hunter's proven browser/map driver + the canonical colour detector,
so it pans and reads dots exactly like precise_fiber_hunter.
"""
import os
import csv
import time
import argparse

# Reuse the proven driver + detector from the hunter (importing is safe: the
# hunter guards its CLI behind `if __name__ == "__main__"`).
from precise_fiber_hunter import (
    self_update, PROFILE_DIR, MAP_URL, VIEWPORT,
    open_map_view, on_map, mouse_drag, zoom, find_map_dots,
)
from optimus_dot_detect import zone_freshness, FRESH_MIN_ELIGIBLE

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT_DIR = os.path.join(HERE, "fresh_zones")
CSV_PATH = os.path.join(HERE, "fresh_zones.csv")


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
    ap.add_argument("--cols", type=int, default=4, help="grid columns to survey (default 4)")
    ap.add_argument("--rows", type=int, default=4, help="grid rows to survey (default 4)")
    ap.add_argument("--survey-out", type=int, default=0,
                    help="zoom OUT this many times first so each viewport covers more ground")
    ap.add_argument("--auto", action="store_true", help="no 'press Enter' pause (unattended)")
    ap.add_argument("--no-update", action="store_true", help="skip the GitHub auto-pull on start")
    args = ap.parse_args()

    os.makedirs(SHOT_DIR, exist_ok=True)
    fresh = []   # collected (idx, row, col, green, gold, gray, gray_share, label, shot)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, viewport=VIEWPORT,
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
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

        idx = 0
        # serpentine grid: left-to-right on even rows, right-to-left on odd, then down.
        for r in range(args.rows):
            row_dir = "right" if r % 2 == 0 else "left"
            for c in range(args.cols):
                idx += 1
                green, gold, gray, gray_share, label = scan_cell(page)
                elig = green + gold
                tag = {"FRESH": "*** FRESH (NEW FIBER)", "WORKING": " ~ working",
                       "MATURE": "   mature (skip)", "EMPTY": "   empty"}.get(label, label)
                print("cell %2d [r%d c%d]  GREEN %3d  GOLD %3d  GREY %3d  grey%%=%.0f%%  -> %s"
                      % (idx, r, c, green, gold, gray, gray_share * 100, tag))

                if label in ("FRESH", "WORKING") and elig >= 1:
                    shot = os.path.join(
                        SHOT_DIR, "zone_%02d_%s_g%d_o%d_grey%d.png"
                        % (idx, label, green, gold, gray))
                    try:
                        page.screenshot(path=shot)
                    except Exception:
                        shot = ""
                    fresh.append((idx, r, c, green, gold, gray, gray_share, label, shot))

                if c < args.cols - 1:
                    mouse_drag(page, row_dir)
            if r < args.rows - 1:
                mouse_drag(page, "down")

        # write the CSV log
        try:
            with open(CSV_PATH, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["idx", "row", "col", "green", "gold", "grey",
                            "grey_share", "label", "screenshot"])
                for row in fresh:
                    i, rr, cc, g, o, gy, gs, lb, sh = row
                    w.writerow([i, rr, cc, g, o, gy, "%.2f" % gs, lb, os.path.basename(sh)])
        except Exception as e:
            print("could not write CSV: %s" % e)

        # ranked summary: freshest = most green+gold, least grey
        fresh.sort(key=lambda x: (-(x[3] + x[4]), x[6]))
        print("\n=========== NEW-FIBER SCOUT RESULTS ===========")
        if not fresh:
            print("No fresh/working zones found in this survey -- the whole area")
            print("read as MATURE (grey/built-out) or EMPTY. Move to a newer suburb")
            print("(La Porte 77571, Katy 77449, Cypress 77433, Spring 77386, Pearland 77584)")
            print("and run again.")
        else:
            best = [z for z in fresh if z[7] == "FRESH"]
            print("Fresh (new-fiber) cells: %d   |   working cells: %d"
                  % (len(best), len(fresh) - len(best)))
            print("Top spots to send the hunter + scraper (green+gold, low grey):")
            for z in fresh[:10]:
                i, rr, cc, g, o, gy, gs, lb, sh = z
                print("  zone %2d  GREEN %3d + GOLD %3d  (grey %d, %.0f%%)  %-7s  %s"
                      % (i, g, o, gy, gs * 100, lb, os.path.basename(sh)))
            print("\nScreenshots of each are in: %s" % SHOT_DIR)
            print("Open the top ones to see the streets, then point the hunter + scraper there.")
        print("CSV log: %s" % CSV_PATH)
        print("===============================================")

        if not args.auto:
            try:
                input("\nDone surveying. Press Enter to close the browser ... ")
            except EOFError:
                pass
        ctx.close()


if __name__ == "__main__":
    main()
