#!/usr/bin/env python3
"""
dedupe_sheet.py  --  remove DUPLICATE rows already sitting in the sheet.

The hunter dedupes on write, so this is a ONE-TIME cleanup of dups accumulated
before that (or from multiple machines writing the same leads).

SAFE BY DESIGN
  - Keeps the FIRST occurrence of each duplicate; deletes only the later copies.
  - Deletes rows bottom-up so nothing shifts; header row (row 1) is never touched.
  - Only the pipeline TABS listed below are considered.
  - DRY RUN unless you pass --yes.

MODES
  default (exact):  a row is a dup only if it's IDENTICAL to an earlier row
                    (safest -- can't merge two different leads).
  --by-key:         a row is a dup if its KEY column matches an earlier row's
                    (stronger -- e.g. same phone/address). Keys set per tab below.

USAGE
  python dedupe_sheet.py             # dry run, exact-duplicate rows
  python dedupe_sheet.py --yes       # delete the exact-duplicate rows
  python dedupe_sheet.py --by-key    # dry run, key-based (phone/address)
  python dedupe_sheet.py --by-key --yes
"""
import sys

from precise_fiber_hunter import open_sheet

# Tabs to dedupe, with the 0-based KEY column used in --by-key mode.
# (Exact mode ignores the key and compares the whole row.)
TABS = {
    "Fiber Green Biz":    2,   # phone column (dialer dedupes by phone)
    "Upgrade Orange Biz": 2,
    "Maps Businesses":    1,   # phone
    "Hunter Leads":       0,   # address
    "Enriched Leads":     0,
}


def _dupe_row_indices(rows, key_col=None):
    """Return 1-based sheet row numbers (skipping header) that are duplicates
    (2nd+ occurrence). key_col=None -> whole-row exact match."""
    seen = set()
    dupes = []
    for i, row in enumerate(rows):
        if i == 0:
            continue  # header
        if key_col is None:
            key = tuple(c.strip() for c in row)
            if not any(key):
                continue  # skip fully blank rows
        else:
            key = (row[key_col].strip().upper() if len(row) > key_col else "")
            if not key:
                continue  # no key value -> don't dedupe it
        if key in seen:
            dupes.append(i + 1)   # sheet rows are 1-based
        else:
            seen.add(key)
    return dupes


def main():
    by_key = "--by-key" in sys.argv
    do_it = "--yes" in sys.argv
    sh = open_sheet()
    if sh is None:
        print("Could not open the sheet (check google_creds.json)."); return
    ss = getattr(sh, "spreadsheet", sh)

    print("Mode: %s%s\n" % ("KEY-based" if by_key else "exact-row",
                            "" if do_it else "   (DRY RUN)"))
    total = 0
    for title, key_col in TABS.items():
        try:
            ws = ss.worksheet(title)
        except Exception:
            print("  %-20s (not present, skipped)" % title); continue
        rows = ws.get_all_values()
        dupes = _dupe_row_indices(rows, key_col if by_key else None)
        total += len(dupes)
        print("  %-20s %5d rows -> %d duplicate rows" % (title, len(rows), len(dupes)))
        if dupes and do_it:
            for r in sorted(dupes, reverse=True):   # bottom-up so indices hold
                try:
                    ws.delete_rows(r)
                except Exception as e:
                    print("      row %d: %s" % (r, str(e)[:50]))
            print("      -> deleted %d duplicate rows from %s" % (len(dupes), title))

    print("\nTotal duplicate rows: %d" % total)
    if total and not do_it:
        print("DRY RUN -- re-run with --yes to delete them (first copy of each is kept).")
    elif not total:
        print("No duplicates found. Sheet is clean.")


if __name__ == "__main__":
    main()
