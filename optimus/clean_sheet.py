#!/usr/bin/env python3
"""
clean_sheet.py  --  safely remove the DEBUG/log tabs from the ATT FIBER LEADS
sheet. Pipeline tabs are hard-protected and can never be deleted by this script.

USAGE
  python clean_sheet.py           # DRY RUN -- lists what it WOULD delete, deletes nothing
  python clean_sheet.py --yes     # actually delete the debug tabs

SAFE BY DESIGN
  - DELETE only tabs on the explicit DEBUG list below.
  - NEVER touch a tab whose name matches PROTECT (green/orange biz, maps, hunter
    leads, enriched, precise, and the OPTIMUS_ state tabs). Belt AND suspenders:
    a tab is deleted only if it's in DEBUG *and* not in PROTECT.
  - Dry-run unless you pass --yes.
"""
import sys

from precise_fiber_hunter import open_sheet

# Debug / log / capture tabs -- regenerated on the next run, safe to remove.
# "Fresh Leads" + "Fiber Scout" are the SCOUT's discovery tabs -- removing them
# from the shared team sheet keeps fresh green private (Patrick 2026-07-16). Any
# tab with data is BACKED UP to a local CSV before deletion so nothing is lost.
DEBUG = {
    "Backend Capture", "Backend Analysis", "Fiber Scout", "Fresh ZIPs",
    "Fresh Leads",
    "Hunter Status", "OPTIMUS_DRIVE_LOG", "_optimus_probe", "Precise Fiber_DEBUG",
}

# Anything matching these (case-insensitive substring) is NEVER deleted.
PROTECT = [
    "green biz", "orange biz", "maps businesses", "hunter leads",
    "enriched", "precise fiber", "optimus_enrich", "optimus_outbox",
]


def _protected(title):
    low = title.lower()
    return any(p in low for p in PROTECT)


# The SCOUT's own discovery tabs -- with --scout-only we remove ONLY these from
# the shared team sheet (leaves the hunter's Backend/Status logs alone).
SCOUT_TABS = {"Fiber Scout", "Fresh Leads", "Fresh ZIPs"}


def main():
    do_it = "--yes" in sys.argv
    scout_only = "--scout-only" in sys.argv
    targets = SCOUT_TABS if scout_only else DEBUG
    if scout_only:
        print("SCOUT-ONLY: removing just the scout's discovery tabs "
              "(Fiber Scout, Fresh Leads, Fresh ZIPs) from the team sheet.\n")
    sh = open_sheet()
    if sh is None:
        print("Could not open the sheet (check google_creds.json)."); return
    # open_sheet() may return a worksheet or the spreadsheet -- normalize.
    ss = getattr(sh, "spreadsheet", sh)

    tabs = ss.worksheets()
    print("Sheet has %d tabs.\n" % len(tabs))

    to_delete, kept = [], []
    for ws in tabs:
        t = ws.title
        if t in targets and not _protected(t):
            to_delete.append(ws)
        else:
            kept.append(t)

    print("KEEP (%d):" % len(kept))
    for t in sorted(kept):
        print("   %s%s" % (t, "   [PROTECTED]" if _protected(t) else ""))
    print("\nDELETE (%d debug tabs):" % len(to_delete))
    for ws in to_delete:
        print("   %s" % ws.title)

    if not to_delete:
        print("\nNothing to clean -- no debug tabs present."); return

    if not do_it:
        print("\nDRY RUN. Re-run with --yes to actually delete the %d debug tabs above."
              % len(to_delete))
        return

    import os, csv, time
    bdir = os.path.join(os.path.expanduser("~"), "optimus",
                        "sheet_backups_" + time.strftime("%Y%m%d_%H%M%S"))
    for ws in to_delete:
        # BACK UP the tab's data to a local CSV before deleting, so nothing
        # valuable (e.g. Fresh Leads' callable green/gold addresses) is lost.
        try:
            rows = ws.get_all_values()
        except Exception:
            rows = []
        if rows:
            try:
                os.makedirs(bdir, exist_ok=True)
                safe = "".join(c if c.isalnum() else "_" for c in ws.title)
                with open(os.path.join(bdir, safe + ".csv"), "w", newline="",
                          encoding="utf-8") as f:
                    csv.writer(f).writerows(rows)
                print("   backed up %s (%d rows) -> %s" % (ws.title, len(rows), bdir))
            except Exception as e:
                print("   (backup hiccup for %s: %s -- NOT deleting it to be safe)"
                      % (ws.title, str(e)[:50]))
                continue   # never delete a tab we couldn't back up
        try:
            ss.del_worksheet(ws)
            print("   deleted: %s" % ws.title)
        except Exception as e:
            print("   could not delete %s: %s" % (ws.title, str(e)[:60]))
    print("\nDone. Debug/scout tabs removed (backed up to %s); pipeline tabs untouched." % bdir)


if __name__ == "__main__":
    main()
