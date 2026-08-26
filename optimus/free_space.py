#!/usr/bin/env python3
"""
free_space.py -- the ATT FIBER LEADS workbook hit Google's 10,000,000 cell
limit and writes started failing with:

    APIError: [400]: This action would increase the number of cells in the
    workbook above the limit of 10000000 cells.

No retry fixes that. Room has to be made. This makes it, safest-first.

WHY THERE IS USUALLY FREE ROOM
A tab's cell cost is its GRID (rows x cols), not the cells you filled. A tab
added as rows="5000", cols="26" bills 130,000 cells even holding ten rows. The
hunter creates tabs that way, so most workbooks carry millions of paid-for,
empty cells. Shrinking a grid to its used range deletes NOTHING and is the
cheapest space there is.

USAGE
  python free_space.py
      DRY RUN. Prints every tab: rows used, grid size, cells billed, and the
      cells a resize would return. Changes nothing.

  python free_space.py --yes
      Shrink every over-allocated grid to its used range (plus a little slack
      so the hunter can keep appending). Deletes no data.

  python free_space.py --drop-test --yes
      Also delete the frozen TEST-*-2026-08-24 verification tabs. CLAUDE.md
      marks these safe to delete once Patrick is done with them.
"""
import sys
import time

from precise_fiber_hunter import open_sheet

CELL_LIMIT = 10_000_000
SLACK_ROWS = 2000          # headroom left on a tab so appends keep working
MIN_COLS = 12              # every pipeline tab is <= 12 wide
PROTECTED = ("Precise Fiber", "Gold Confirmed", "Grey Fiber Customers",
             "Unknown Customers", "Maps Businesses", "Fiber Green Biz",
             "Upgrade Orange Biz", "DASHBOARD", "README")


def _used_rows(ws):
    try:
        return len(ws.col_values(1))
    except Exception:
        return None


def main():
    go = "--yes" in sys.argv
    drop_test = "--drop-test" in sys.argv

    sh = open_sheet()
    if sh is None:
        print("Could not open the sheet (check google_creds.json).")
        return
    ss = getattr(sh, "spreadsheet", sh)

    print("=" * 74)
    print("  WORKBOOK SPACE  --  %s" % ("APPLYING CHANGES" if go else "DRY RUN"))
    print("=" * 74)
    print("  %-30s %9s %13s %11s %10s"
          % ("TAB", "ROWS USED", "GRID", "CELLS", "RECLAIM"))

    total = 0
    plans = []
    for ws in ss.worksheets():
        grid_r, grid_c = ws.row_count, ws.col_count
        cells = grid_r * grid_c
        total += cells
        used = _used_rows(ws)
        want_r = grid_r if used is None else max(used + SLACK_ROWS, 100)
        want_c = max(MIN_COLS, min(grid_c, 12))
        gain = cells - (want_r * want_c) if want_r < grid_r or want_c < grid_c else 0
        gain = max(0, gain)
        print("  %-30s %9s %13s %11s %10s"
              % (ws.title[:30], "?" if used is None else used,
                 "%dx%d" % (grid_r, grid_c), "{:,}".format(cells),
                 "{:,}".format(gain) if gain else "-"))
        # No point resizing a tab that --drop-test is about to delete: it
        # spends two write calls out of a quota we are already short on.
        if gain and not (drop_test and ws.title.startswith("TEST-")):
            plans.append((ws, want_r, want_c, gain))

    print("-" * 74)
    print("  TOTAL BILLED: {:,} of {:,} cells  ({:.1f}% full)"
          .format(total, CELL_LIMIT, 100.0 * total / CELL_LIMIT))
    reclaim = sum(p[3] for p in plans)
    print("  RECLAIMABLE BY RESIZE (no data deleted): {:,} cells".format(reclaim))
    if total >= CELL_LIMIT:
        print("  *** THE WORKBOOK IS FULL. Writes are failing right now. ***")

    test_tabs = [w for w in ss.worksheets() if w.title.startswith("TEST-")]
    if test_tabs:
        t_cells = sum(w.row_count * w.col_count for w in test_tabs)
        print("  TEST-* tabs: {}, holding {:,} cells{}".format(
            len(test_tabs), t_cells,
            "" if drop_test else "  (--drop-test to remove)"))

    if not go:
        print("\n  Dry run. Re-run with --yes to apply.")
        return

    print("\n  Resizing %d over-allocated tab(s)..." % len(plans))
    freed = 0
    for ws, r, c, gain in plans:
        try:
            ws.resize(rows=r, cols=c)
            freed += gain
            print("   {:<30} -> {}x{}  (+{:,} cells)".format(
                ws.title[:30], r, c, gain))
            time.sleep(1.2)          # stay under the write quota
        except Exception as e:
            print("   %-30s resize failed: %s" % (ws.title[:30], str(e)[:60]))

    if drop_test:
        for ws in test_tabs:
            if ws.title in PROTECTED:
                continue
            try:
                cells = ws.row_count * ws.col_count
                ss.del_worksheet(ws)
                freed += cells
                print("   deleted {:<24} (+{:,} cells)".format(ws.title[:24], cells))
                time.sleep(1.2)
            except Exception as e:
                print("   could not delete %s: %s" % (ws.title[:24], str(e)[:60]))

    print("\n  FREED {:,} cells. Workbook now ~{:,} of {:,}."
          .format(freed, max(0, total - freed), CELL_LIMIT))
    print("  Parked rows replay automatically on the next hunter launch.")


if __name__ == "__main__":
    main()
