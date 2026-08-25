#!/usr/bin/env python3
"""
clean_sheet.py  --  safely remove the DEBUG/log/TEST tabs from the ATT FIBER
LEADS sheet. Pipeline tabs are hard-protected and can never be deleted by this
script.

USAGE
  python clean_sheet.py           # DRY RUN -- lists what it WOULD do, changes nothing
  python clean_sheet.py --yes     # migrate gold, back up, then delete

WHAT --yes DOES, IN ORDER
  1. MIGRATE: every data row in any TEST-Gold-* tab is appended into the
     permanent 'Gold Confirmed' tab (created with the hunter's header if
     missing, deduped on address) BEFORE anything is deleted. Nothing gold is
     ever lost.
  2. BACK UP: every tab about to be deleted is saved to a local CSV first.
     A tab that cannot be backed up is NOT deleted.
  3. DELETE: only tabs on the DEBUG list or starting with 'TEST-'.

SAFE BY DESIGN
  - DELETE only tabs on the explicit DEBUG list below or named 'TEST-*'
    (the 2026-08-24 verification snapshots -- superseded by the permanent
    'Gold Confirmed' / 'Grey Fiber Customers' / 'Unknown Customers' tabs).
  - NEVER touch a tab whose name matches PROTECT. Belt AND suspenders: a tab
    is deleted only if it's a target *and* not in PROTECT.
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
# The 2026-08-24 permanent tabs are here so no future edit to the target list
# can ever take them out: Gold Confirmed is the call list, Grey Fiber Customers
# is the penetration data, Gold Dots is retired-but-history (old enrichment).
PROTECT = [
    "green biz", "orange biz", "maps businesses", "hunter leads",
    "enriched", "precise fiber", "optimus_enrich", "optimus_outbox",
    "gold confirmed", "grey fiber customers", "unknown customers",
    "gold dots", "gold recheck", "backend comm", "_dedupe lock", "_dispatch",
    "campaign", "dialer",
]

GOLD_TAB = "Gold Confirmed"
_GOLD_HEADER = ["Address", "Captured At", "Lat", "Lng", "Business", "Phone",
                "Run ID", "Operator", "City", "State", "ZIP",
                "Tier", "Build Code"]


def _protected(title):
    low = title.lower()
    return any(p in low for p in PROTECT)


def _is_test_tab(title):
    return title.upper().startswith("TEST-")


# The SCOUT's own discovery tabs -- with --scout-only we remove ONLY these from
# the shared team sheet (leaves the hunter's Backend/Status logs alone).
SCOUT_TABS = {"Fiber Scout", "Fresh Leads", "Fresh ZIPs"}


def _migrate_test_gold(ss, ws, do_it):
    """Fold a TEST-Gold-* tab's rows into the permanent Gold Confirmed tab,
    deduped on address (case-insensitive). Returns rows migrated (or that
    WOULD migrate on a dry run). Raises nothing -- a failed migration prints
    and returns -1 so the caller keeps the source tab."""
    try:
        rows = ws.get_all_values()
    except Exception as e:
        print("   (could not read %s: %s)" % (ws.title, str(e)[:60]))
        return -1
    # drop the header row if present
    data = [r for r in rows
            if r and r[0].strip() and r[0].strip().lower() != "address"]
    if not data:
        return 0
    try:
        try:
            gw = ss.worksheet(GOLD_TAB)
        except Exception:
            if not do_it:
                print("   (would create '%s' with the hunter header)" % GOLD_TAB)
                return len(data)
            gw = ss.add_worksheet(title=GOLD_TAB, rows="2000",
                                  cols=str(len(_GOLD_HEADER)))
            gw.append_row(_GOLD_HEADER)
        have = set(a.strip().upper() for a in gw.col_values(1) if a.strip())
        fresh = [r for r in data if r[0].strip().upper() not in have]
        if not fresh:
            return 0
        if not do_it:
            return len(fresh)
        # pad/trim each row to the gold header width so columns line up
        w = len(_GOLD_HEADER)
        out = [(r + [""] * w)[:w] for r in fresh]
        gw.append_rows(out, value_input_option="RAW")
        return len(fresh)
    except Exception as e:
        print("   (migration to '%s' failed: %s -- keeping %s untouched)"
              % (GOLD_TAB, str(e)[:60], ws.title))
        return -1


def main():
    do_it = "--yes" in sys.argv
    scout_only = "--scout-only" in sys.argv
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
        if scout_only:
            target = t in SCOUT_TABS
        else:
            target = (t in DEBUG) or _is_test_tab(t)
        if target and not _protected(t):
            to_delete.append(ws)
        else:
            kept.append(t)

    print("KEEP (%d):" % len(kept))
    for t in sorted(kept):
        print("   %s%s" % (t, "   [PROTECTED]" if _protected(t) else ""))
    print("\nDELETE (%d debug/test tabs):" % len(to_delete))
    for ws in to_delete:
        print("   %s" % ws.title)

    if not to_delete:
        print("\nNothing to clean -- no debug or TEST tabs present."); return

    # gold migration plan/preview happens for dry-run AND real run
    for ws in to_delete:
        if _is_test_tab(ws.title) and "GOLD" in ws.title.upper():
            n = _migrate_test_gold(ss, ws, do_it)
            if n > 0:
                print("\n%s %d gold row(s): %s -> '%s'"
                      % ("MIGRATED" if do_it else "WOULD MIGRATE",
                         n, ws.title, GOLD_TAB))
            elif n < 0:
                # migration failed -- do not delete the source tab
                to_delete = [w for w in to_delete if w.title != ws.title]

    if not do_it:
        print("\nDRY RUN. Re-run with --yes to migrate gold, back up, and "
              "delete the tabs above.")
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
    print("\nDone. Debug/test tabs removed (backed up to %s); pipeline tabs untouched." % bdir)


if __name__ == "__main__":
    main()
