#!/usr/bin/env python3
"""
dedupe_sheet.py  --  remove DUPLICATE rows already sitting in the sheet.

The hunter dedupes on write, so this is a ONE-TIME cleanup of dups accumulated
before that (or from multiple machines writing the same leads).

SAFE BY DESIGN
  - Keeps the FIRST occurrence of each duplicate; deletes only the later copies.
  - Deletes rows bottom-up so nothing shifts; header row (row 1) is never touched.
  - Only the pipeline TABS listed below are considered.
  - The dedup KEY column is found BY HEADER NAME (not a hardcoded position), so
    it can't dedup on the wrong field if a tab's columns are in a different order.
  - DRY RUN unless you pass --yes.

MODES
  default (exact):  a row is a dup only if it's IDENTICAL to an earlier row.
  --by-phone:       dup if the "Phone" column matches an earlier row (best for the
                    biz tabs -- same business matched many times).
  --by-address:     dup if the "Address" column matches an earlier row.
  (If a tab has no matching column for the chosen mode, that tab is skipped.)

USAGE
  python dedupe_sheet.py                # dry run, exact-duplicate rows
  python dedupe_sheet.py --by-phone     # dry run, dedup by phone
  python dedupe_sheet.py --by-phone --yes
"""
import sys

from precise_fiber_hunter import open_sheet

TABS = ["Fiber Green Biz", "Upgrade Orange Biz", "Maps Businesses",
        "Hunter Leads", "Enriched Leads"]


def _find_col(header, want):
    """Index of the first column whose header contains `want` (case-insensitive)."""
    for i, h in enumerate(header):
        if want in (h or "").strip().lower():
            return i
    return None


def _dupe_row_indices(rows, key_col=None):
    """1-based sheet row numbers (skipping header) that are duplicates (2nd+).
    key_col=None -> whole-row exact match."""
    seen = set()
    dupes = []
    for i, row in enumerate(rows):
        if i == 0:
            continue  # header
        if key_col is None:
            key = tuple(c.strip() for c in row)
            if not any(key):
                continue
        else:
            key = (row[key_col].strip().upper() if len(row) > key_col else "")
            if not key:
                continue  # blank key -> never dedupe it away
        if key in seen:
            dupes.append(i + 1)
        else:
            seen.add(key)
    return dupes


def main():
    do_it = "--yes" in sys.argv
    mode = "exact"
    if "--by-phone" in sys.argv:
        mode = "phone"
    elif "--by-address" in sys.argv:
        mode = "address"

    sh = open_sheet()
    if sh is None:
        print("Could not open the sheet (check google_creds.json)."); return
    ss = getattr(sh, "spreadsheet", sh)

    print("Mode: %s%s\n" % (mode, "" if do_it else "   (DRY RUN -- nothing deleted)"))
    total = 0
    for title in TABS:
        try:
            ws = ss.worksheet(title)
        except Exception:
            print("  %-20s (not present, skipped)" % title); continue
        rows = ws.get_all_values()
        if not rows:
            print("  %-20s (empty)" % title); continue

        if mode == "exact":
            key_col = None
        else:
            key_col = _find_col(rows[0], mode)
            if key_col is None:
                print("  %-20s (no '%s' column, skipped)" % (title, mode)); continue

        dupes = _dupe_row_indices(rows, key_col)
        total += len(dupes)
        keeps = len(rows) - 1 - len(dupes)
        print("  %-20s %7d rows -> %7d duplicates  (%d unique kept)"
              % (title, len(rows), len(dupes), keeps))
        if dupes and do_it:
            for r in sorted(dupes, reverse=True):
                try:
                    ws.delete_rows(r)
                except Exception as e:
                    print("      row %d: %s" % (r, str(e)[:50]))
            print("      -> deleted %d duplicate rows from %s" % (len(dupes), title))

    print("\nTotal duplicate rows: %d" % total)
    if total and not do_it:
        print("DRY RUN -- re-run with --yes to delete them (first copy of each is kept).")
    elif not total:
        print("No duplicates found.")


if __name__ == "__main__":
    main()
