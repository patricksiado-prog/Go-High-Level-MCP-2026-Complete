#!/usr/bin/env python3
"""
clean_sheet.py  --  the SHEET JANITOR for ATT FIBER LEADS (Patrick, 2026-08-24).

Whitelist model: everything NOT on the KEEP list goes (backed up to CSV first).
That includes the retired 'Gold Dots' tab (contaminated, BRAIN 22.14) and every
TEST-*/debug/leftover tab.

USAGE
  python clean_sheet.py           # DRY RUN -- full plan, changes nothing
  python clean_sheet.py --yes     # do it for real

WHAT --yes DOES, IN ORDER
  1. MIGRATE  every data row in any TEST-Gold-* tab into the permanent
              'Gold Confirmed' tab (created with the hunter header if missing,
              deduped on address). Nothing gold is ever lost.
  2. DEDUPE   'Gold Confirmed' by address (first copy kept, bottom-up row
              deletes) and 'Precise Fiber' by address via safe rewrite:
              backup CSV -> unique rows written to a temp tab -> original
              deleted -> temp renamed. A crash mid-way leaves the original
              untouched.
  3. DELETE   every tab not on the KEEP list -- each one backed up to a local
              CSV first; a tab that cannot be backed up is NOT deleted.

  Old 'Gold Dots' (3,328 rows of pre-rule history) is deleted in step 3, and
  its CSV backup is the archive.
"""
import sys

from precise_fiber_hunter import open_sheet

# ---- KEEP list: the pipeline. Exact titles, case-insensitive. -------------
KEEP = {
    "precise fiber",          # production: every captured dot with color
    "gold confirmed",         # THE call list: new-rule confirmed copper only
    "grey fiber customers",   # existing fiber customers (penetration data)
    "unknown customers",      # undecodable customers, human review
    "gold recheck",           # hunter's recheck queue
    "maps businesses", "fiber green biz", "upgrade orange biz",
    "backend comm", "hunter status", "_dedupe lock", "_dispatch",
}
# ...plus anything whose name CONTAINS one of these (Patrick's working tabs).
KEEP_SUBSTR = ["campaign", "dialer", "devonwood", "commercial",
               "readme", "dashboard"]

GOLD_TAB = "Gold Confirmed"
PRECISE_TAB = "Precise Fiber"
_GOLD_HEADER = ["Address", "Captured At", "Lat", "Lng", "Business", "Phone",
                "Run ID", "Operator", "City", "State", "ZIP",
                "Tier", "Build Code"]


def _keep(title):
    low = title.strip().lower()
    return low in KEEP or any(s in low for s in KEEP_SUBSTR)


def _backup(ws, bdir):
    """Save a tab to CSV. Returns True on success (or empty tab)."""
    import os, csv
    try:
        rows = ws.get_all_values()
    except Exception as e:
        print("   (could not read %s: %s -- NOT deleting it)" % (ws.title, str(e)[:50]))
        return False
    if not rows:
        return True
    try:
        os.makedirs(bdir, exist_ok=True)
        safe = "".join(c if c.isalnum() else "_" for c in ws.title)
        with open(os.path.join(bdir, safe + ".csv"), "w", newline="",
                  encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        print("   backed up %s (%d rows)" % (ws.title, len(rows)))
        return True
    except Exception as e:
        print("   (backup failed for %s: %s -- NOT deleting it)" % (ws.title, str(e)[:50]))
        return False


def _migrate_test_gold(ss, ws, do_it):
    """Fold a TEST-Gold-* tab into Gold Confirmed, deduped on address.
    Returns rows migrated (would-migrate on dry run), -1 on failure."""
    try:
        rows = ws.get_all_values()
    except Exception as e:
        print("   (could not read %s: %s)" % (ws.title, str(e)[:60]))
        return -1
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
        if not fresh or not do_it:
            return len(fresh)
        w = len(_GOLD_HEADER)
        gw.append_rows([(r + [""] * w)[:w] for r in fresh],
                       value_input_option="RAW")
        return len(fresh)
    except Exception as e:
        print("   (migration to '%s' failed: %s -- keeping %s untouched)"
              % (GOLD_TAB, str(e)[:60], ws.title))
        return -1


def _dedupe_small_by_address(ss, title, do_it):
    """Dedupe a SMALL tab by column A (address, case-insensitive). Keeps the
    first copy; deletes later rows bottom-up. Fine up to a few thousand rows."""
    try:
        ws = ss.worksheet(title)
        rows = ws.get_all_values()
    except Exception:
        return
    seen, dupes = set(), []
    for i, r in enumerate(rows):
        if i == 0:
            continue
        key = (r[0].strip().upper() if r else "")
        if not key:
            continue
        if key in seen:
            dupes.append(i + 1)     # 1-based sheet row
        else:
            seen.add(key)
    print("   %-22s %6d rows, %d duplicate(s)%s"
          % (title, len(rows), len(dupes), "" if do_it or not dupes else "  (dry run)"))
    if do_it and dupes:
        for r in sorted(dupes, reverse=True):
            try:
                ws.delete_rows(r)
            except Exception as e:
                print("      row %d: %s" % (r, str(e)[:50]))
        print("      -> removed %d duplicates from %s" % (len(dupes), title))


def _dedupe_precise_rewrite(ss, bdir, do_it):
    """Dedupe Precise Fiber by address via SAFE REWRITE (too big for row
    deletes). Backup -> unique rows to temp tab -> delete original -> rename.
    Original is untouched until the temp copy is complete."""
    try:
        ws = ss.worksheet(PRECISE_TAB)
    except Exception:
        print("   (%s not present, skipped)" % PRECISE_TAB)
        return
    rows = ws.get_all_values()
    if not rows:
        print("   (%s empty)" % PRECISE_TAB)
        return
    seen, unique = set(), []
    for r in rows:
        key = (r[0].strip().upper() if r else "")
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    dups = len(rows) - len(unique)
    print("   %-22s %6d rows, %d duplicate(s)%s"
          % (PRECISE_TAB, len(rows), dups, "" if do_it or not dups else "  (dry run)"))
    if not do_it or not dups:
        return
    if not _backup(ws, bdir):
        print("   (no backup, no rewrite -- %s untouched)" % PRECISE_TAB)
        return
    tmp_title = PRECISE_TAB + " __dedup"
    try:
        try:
            old_tmp = ss.worksheet(tmp_title)
            ss.del_worksheet(old_tmp)          # stale leftover from a crash
        except Exception:
            pass
        cols = max(len(r) for r in unique)
        tmp = ss.add_worksheet(title=tmp_title, rows=str(len(unique) + 10),
                               cols=str(cols))
        for i in range(0, len(unique), 10000):
            tmp.append_rows(unique[i:i + 10000], value_input_option="RAW")
            print("      wrote %d / %d unique rows..."
                  % (min(i + 10000, len(unique)), len(unique)))
        ss.del_worksheet(ws)
        tmp.update_title(PRECISE_TAB)
        print("      -> %s rebuilt: %d unique rows (%d duplicates removed)"
              % (PRECISE_TAB, len(unique), dups))
    except Exception as e:
        print("      REWRITE FAILED: %s" % str(e)[:80])
        print("      Original tab is intact. Delete '%s' by hand if it exists."
              % tmp_title)


# ---- PRETTY PASS: header band color per tab (matches the dot legend) ------
PRETTY = {
    "Precise Fiber":        {"bg": (0x18, 0x80, 0x38), "fg": "white"},  # green
    "Gold Confirmed":       {"bg": (0xF9, 0xAB, 0x00), "fg": "black"},  # gold
    "Grey Fiber Customers": {"bg": (0x5F, 0x63, 0x68), "fg": "white"},  # grey
    "Unknown Customers":    {"bg": (0x9A, 0xA0, 0xA6), "fg": "black"},
    "Gold Recheck":         {"bg": (0xFD, 0xD6, 0x63), "fg": "black"},
    "Maps Businesses":      {"bg": (0x1A, 0x73, 0xE8), "fg": "white"},  # blue
    "Fiber Green Biz":      {"bg": (0x34, 0xA8, 0x53), "fg": "white"},
    "Upgrade Orange Biz":   {"bg": (0xE8, 0x71, 0x0A), "fg": "white"},
}
MAIN_HEADER = ["Address", "Dot Color", "Captured At", "Business", "Phone",
               "Run ID", "Operator", "Lat", "Lng", "City", "State", "ZIP"]


def _prettify(ss, do_it):
    """Bold colored frozen header + sized columns on every pipeline tab.
    Precise Fiber gets a header row inserted if it has none (the scraper
    filters on the Dot Color column, so a header row is invisible to it)."""
    print("\n-- PRETTY PASS --")
    for title, style in PRETTY.items():
        try:
            ws = ss.worksheet(title)
        except Exception:
            continue
        if not do_it:
            print("   would format %s (colored bold frozen header, sized columns)"
                  % title)
            continue
        try:
            if title == PRECISE_TAB:
                a1 = (ws.acell("A1").value or "").strip().lower()
                if a1 != "address":
                    ws.insert_row(MAIN_HEADER, 1)
            r, g, b = [c / 255.0 for c in style["bg"]]
            fg = ({"red": 1, "green": 1, "blue": 1} if style["fg"] == "white"
                  else {"red": 0, "green": 0, "blue": 0})
            sid = ws.id
            ss.batch_update({"requests": [
                {"repeatCell": {
                    "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": r, "green": g, "blue": b},
                        "textFormat": {"bold": True, "foregroundColor": fg},
                        "horizontalAlignment": "CENTER"}},
                    "fields": ("userEnteredFormat(backgroundColor,"
                               "textFormat,horizontalAlignment)")}},
                {"updateSheetProperties": {
                    "properties": {"sheetId": sid,
                                   "gridProperties": {"frozenRowCount": 1}},
                    "fields": "gridProperties.frozenRowCount"}},
                {"updateDimensionProperties": {
                    "range": {"sheetId": sid, "dimension": "COLUMNS",
                              "startIndex": 0, "endIndex": 1},
                    "properties": {"pixelSize": 230}, "fields": "pixelSize"}},
                {"updateDimensionProperties": {
                    "range": {"sheetId": sid, "dimension": "COLUMNS",
                              "startIndex": 1, "endIndex": 13},
                    "properties": {"pixelSize": 118}, "fields": "pixelSize"}},
            ]})
            print("   formatted %s" % title)
        except Exception as e:
            print("   (format skipped for %s: %s)" % (title, str(e)[:60]))


README_TAB = "README"
DASH_TAB = "DASHBOARD"

# Written for a HUMAN and for an AI that nobody here controls. Daniel's ChatGPT
# and Nicole's Claude will open this file and read whatever is in front of them;
# if the first thing they meet is a 474,000-row archive they choke on it. This
# tab is the map that sends them somewhere small and useful instead. Cheapest
# interop there is -- it works the same for every assistant, this year and next.
README_ROWS = [
    ["OPTIMUS — ATT FIBER LEADS", "", ""],
    ["", "", ""],
    ["READ THIS FIRST — what every tab is and which one you want.", "", ""],
    ["", "", ""],
    ["TAB", "SIZE", "WHAT IT IS / WHEN TO USE IT"],
    ["DASHBOARD", "tiny",
     "Live counts for every tab below. Start here for 'how are we doing'."],
    ["Gold Confirmed", "small",
     "THE CALL LIST. Confirmed copper customers on live fiber — the $140 "
     "upgrade. Easiest sale we have: an upgrade, not a switch."],
    ["Fiber Green Biz", "small",
     "Businesses sitting on a GREEN dot — fiber live, not an AT&T customer."],
    ["Upgrade Orange Biz", "small",
     "Businesses sitting on a GOLD dot — copper customer, upgrade pitch."],
    ["Grey Fiber Customers", "medium",
     "Already AT&T fiber customers. NOT leads — this is penetration data, and "
     "the audience for wireless/bundle offers."],
    ["Unknown Customers", "small",
     "Customers whose build code we cannot decode yet. Parked for review, "
     "deliberately NOT on the call list."],
    ["Maps Businesses", "medium", "Every business scraped off Google Maps."],
    ["Precise Fiber", "HUGE — ARCHIVE",
     "Every captured dot with its color. ~474,000 rows. Nobody calls from this "
     "tab. Do NOT open it whole and do NOT feed it to an AI — ask for a "
     "specific range or ZIP instead."],
    ["", "", ""],
    ["THE DOT LEGEND", "WORTH", ""],
    ["GREEN", "$500", "Fiber live, NOT an AT&T customer. The prize."],
    ["GOLD / ORANGE", "$140", "Fiber live + AT&T customer still on copper."],
    ["GREY", "—", "Already on AT&T fiber. Skip as a lead."],
    ["", "", ""],
    ["RULES FOR EVERYONE", "", ""],
    ["View only", "",
     "The hunter software WRITES these tabs continuously. Do not sort, insert "
     "or delete rows — it breaks the pipeline for everyone. Put call notes and "
     "dispositions in GoHighLevel, not here."],
    ["If you are an AI", "",
     "Read DASHBOARD first, then the specific small tab you need. Never load "
     "Precise Fiber in full."],
]


def _ensure_readme(ss, do_it):
    """README in front position, rewritten every run so it cannot go stale."""
    if not do_it:
        print("   would write the %s tab (tab map + dot legend + rules)" % README_TAB)
        return
    try:
        try:
            ws = ss.worksheet(README_TAB)
            ws.clear()
        except Exception:
            ws = ss.add_worksheet(title=README_TAB, rows="60", cols="3")
        ws.update("A1", README_ROWS, value_input_option="RAW")
        sid = ws.id
        ss.batch_update({"requests": [
            {"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.05, "green": 0.32, "blue": 0.13},
                    "textFormat": {"bold": True, "fontSize": 13,
                                   "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
            {"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 5},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.85, "green": 0.89, "blue": 0.85},
                    "textFormat": {"bold": True}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
            {"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 200}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS",
                          "startIndex": 1, "endIndex": 2},
                "properties": {"pixelSize": 120}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS",
                          "startIndex": 2, "endIndex": 3},
                "properties": {"pixelSize": 620}, "fields": "pixelSize"}},
        ]})
        print("   wrote %s" % README_TAB)
    except Exception as e:
        print("   (README skipped: %s)" % str(e)[:70])


def _ensure_dashboard(ss, do_it):
    """Live counts. Formulas reference tabs in THIS file, so there is no
    IMPORTRANGE and nothing to authorise -- it just works, for anyone."""
    if not do_it:
        print("   would write the %s tab (live counts, no IMPORTRANGE)" % DASH_TAB)
        return
    counted = ["Gold Confirmed", "Grey Fiber Customers", "Unknown Customers",
               "Fiber Green Biz", "Upgrade Orange Biz", "Maps Businesses",
               "Precise Fiber"]
    have = set()
    try:
        have = set(w.title for w in ss.worksheets())
    except Exception:
        pass
    rows = [["OPTIMUS DASHBOARD", ""],
            ["Updated live by formula — no refresh needed.", ""],
            ["", ""],
            ["TAB", "ROWS"]]
    for t in counted:
        if t in have:
            rows.append([t, "=MAX(0,COUNTA('%s'!A:A)-1)" % t])
    rows += [["", ""], ["DOT COLOR (Precise Fiber)", "COUNT"]]
    if "Precise Fiber" in have:
        for color in ("GREEN", "ORANGE", "GREY", "UNKNOWN"):
            rows.append([color, "=COUNTIF('Precise Fiber'!B:B,\"%s\")" % color])
    try:
        try:
            ws = ss.worksheet(DASH_TAB)
            ws.clear()
        except Exception:
            ws = ss.add_worksheet(title=DASH_TAB, rows="40", cols="2")
        ws.update("A1", rows, value_input_option="USER_ENTERED")
        sid = ws.id
        ss.batch_update({"requests": [
            {"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.10, "green": 0.45, "blue": 0.82},
                    "textFormat": {"bold": True, "fontSize": 13,
                                   "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
            {"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 260}, "fields": "pixelSize"}},
        ]})
        print("   wrote %s" % DASH_TAB)
    except Exception as e:
        print("   (DASHBOARD skipped: %s)" % str(e)[:70])


def _order_tabs(ss, do_it):
    """README, DASHBOARD, then the call lists, with the 474k archive LAST.
    Whoever opens this file -- person or AI -- should land on something small."""
    front = [README_TAB, DASH_TAB, GOLD_TAB, "Fiber Green Biz",
             "Upgrade Orange Biz", "Grey Fiber Customers", "Unknown Customers",
             "Gold Recheck", "Maps Businesses"]
    if not do_it:
        print("   would put %s first and %s last" % (README_TAB, PRECISE_TAB))
        return
    try:
        by_title = {w.title: w for w in ss.worksheets()}
        ordered = [by_title[t] for t in front if t in by_title]
        rest = [w for w in ss.worksheets()
                if w.title not in front and w.title != PRECISE_TAB]
        if PRECISE_TAB in by_title:
            rest.append(by_title[PRECISE_TAB])       # archive goes last
        ss.reorder_worksheets(ordered + rest)
        print("   tab order set (%s first, %s last)" % (README_TAB, PRECISE_TAB))
    except Exception as e:
        print("   (tab order skipped: %s)" % str(e)[:70])


def main():
    do_it = "--yes" in sys.argv
    sh = open_sheet()
    if sh is None:
        print("Could not open the sheet (check google_creds.json)."); return
    ss = getattr(sh, "spreadsheet", sh)

    import os, time
    bdir = os.path.join(os.path.expanduser("~"), "optimus",
                        "sheet_backups_" + time.strftime("%Y%m%d_%H%M%S"))

    tabs = ss.worksheets()
    print("Sheet has %d tabs.\n" % len(tabs))

    keep, kill = [], []
    for ws in tabs:
        (keep if _keep(ws.title) else kill).append(ws)

    print("KEEP (%d):" % len(keep))
    for ws in sorted(keep, key=lambda w: w.title.lower()):
        print("   %s" % ws.title)
    print("\nDELETE (%d -- each backed up to CSV first):" % len(kill))
    for ws in sorted(kill, key=lambda w: w.title.lower()):
        print("   %s" % ws.title)

    # 1) migrate TEST gold before anything else
    print("\n-- GOLD MIGRATION --")
    migrated_any = False
    for ws in list(kill):
        t = ws.title.upper()
        if t.startswith("TEST-") and "GOLD" in t:
            n = _migrate_test_gold(ss, ws, do_it)
            if n > 0:
                migrated_any = True
                print("   %s %d gold row(s): %s -> '%s'"
                      % ("MIGRATED" if do_it else "WOULD MIGRATE",
                         n, ws.title, GOLD_TAB))
            elif n < 0:
                kill = [w for w in kill if w.title != ws.title]
    if not migrated_any:
        print("   (no TEST gold to migrate)")

    # 2) dedupe the two tabs Patrick called out
    print("\n-- DUPLICATE REMOVAL --")
    _dedupe_small_by_address(ss, GOLD_TAB, do_it)
    _dedupe_precise_rewrite(ss, bdir, do_it)

    # 3) delete the junk
    if not do_it:
        print("\n-- README / DASHBOARD --")
        _ensure_readme(ss, False)
        _ensure_dashboard(ss, False)
        _order_tabs(ss, False)
        _prettify(ss, False)
        print("\nDRY RUN. Re-run with --yes to migrate, dedupe, back up, "
              "delete the %d tabs above, and format the keepers." % len(kill))
        return
    print("\n-- DELETING (%d tabs) --" % len(kill))
    for ws in kill:
        if not _backup(ws, bdir):
            continue
        try:
            ss.del_worksheet(ws)
            print("   deleted: %s" % ws.title)
        except Exception as e:
            print("   could not delete %s: %s" % (ws.title, str(e)[:60]))

    # 4) the map and the numbers, then make the survivors pretty
    print("\n-- README / DASHBOARD --")
    _ensure_readme(ss, True)
    _ensure_dashboard(ss, True)
    _order_tabs(ss, True)
    _prettify(ss, True)
    print("\nDone. Backups in %s" % bdir)


if __name__ == "__main__":
    main()
