"""gold_audit.py -- READ-ONLY audit of the canonical gold tab.

WHY THIS EXISTS
    Autosheet ran out of credits and was the only path anyone had to the master
    sheet, which blocked the Gold Dots audit for a full day. The hunter never
    needed Autosheet -- it talks to the sheet directly with the fiberscanner
    service account. So does this.

RUN IT (one line, nothing to save first):

    py -c "import urllib.request as u;exec(u.urlopen('https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/claude/optimus-map-tools-setup-6dcl6o/optimus/gold_audit.py').read())"

    ...or, with the file sitting next to the hunter:  py gold_audit.py

THIS CHANGES NOTHING. It only reads and prints. Cleaning up the duplicates is a
separate, deliberate step -- writing a delete against 3,000+ live lead rows
before anyone has seen the numbers is how data gets lost.

BOUNDED BY DESIGN
    CLAUDE.md: never pull a whole tab. Precise Fiber is ~474k rows and pulling
    it is what killed Autosheet twice. This reads a handful of columns from ONE
    tab. get_all_values() is deliberately never called.
"""
import os
import sys

SHEET_ID = "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA"
# 'Gold Dots' is RETIRED: it is contaminated with gold-by-default rows
# (BRAIN 22.14), so auditing it graded bad gold as good. The canonical tab is
# 'Gold Confirmed' -- new-rule confirmed copper only. Import it from the hunter
# when we can, so a future rename moves this too.
try:
    from precise_fiber_hunter import GOLD_TAB
except Exception:
    GOLD_TAB = "Gold Confirmed"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly",
          "https://www.googleapis.com/auth/drive.readonly"]
# Row 1 counts as a header ONLY if it really matches. The retired 'Gold Dots'
# tab had none and assuming one is what made the hunter re-append row 1 every
# run; 'Gold Confirmed' DOES have one. Detecting it rather than assuming either
# way is what lets this audit point at both.
GOLD_HEADER0 = "address"


def find_creds():
    """Look where the installer actually puts google_creds.json."""
    here = os.getcwd()
    try:
        here = os.path.dirname(os.path.abspath(__file__)) or here
    except NameError:
        pass                      # exec()'d from the one-liner: no __file__
    home = os.path.expanduser("~")
    for p in (os.path.join(here, "google_creds.json"),
              os.path.join(home, "optimus_hunter", "google_creds.json"),
              os.path.join(home, "maps_scraper", "google_creds.json"),
              os.path.join(home, "optimus", "google_creds.json"),
              os.path.join(home, "google_creds.json"),
              "google_creds.json"):
        if os.path.exists(p) and os.path.getsize(p) > 200:
            return p
    return None


def main():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("Missing packages. Run:  py -m pip install gspread google-auth")
        return 1

    path = find_creds()
    if not path:
        print("No google_creds.json found. Open a command prompt inside your")
        print("optimus_hunter folder and run it there -- the installer puts")
        print("the key in that folder.")
        return 1
    print("credential: %s" % path)

    sh = gspread.authorize(
        Credentials.from_service_account_file(path, scopes=SCOPES)
    ).open_by_key(SHEET_ID)
    print("sheet     : %s\n" % sh.title)

    try:
        ws = sh.worksheet(GOLD_TAB)
    except Exception:
        print("There is no '%s' tab. Tabs present:" % GOLD_TAB)
        for w in sh.worksheets():
            print("   %-28s %8d rows" % (w.title, w.row_count))
        return 1

    # ---- bounded column reads, nothing else ------------------------------
    addrs = ws.col_values(1)
    when = ws.col_values(2)
    lat = ws.col_values(3)
    lng = ws.col_values(4)

    has_header = bool(addrs) and addrs[0].strip().lower() == GOLD_HEADER0
    start = 1 if has_header else 0

    rows = [a.strip() for a in addrs[start:] if a and a.strip()]
    seen, dupes = set(), {}
    for a in rows:
        k = a.upper()
        if k in seen:
            dupes[k] = dupes.get(k, 1) + 1
        else:
            seen.add(k)

    both = 0
    for i in range(start, max(len(lat), len(lng))):
        has_lat = i < len(lat) and str(lat[i]).strip()
        has_lng = i < len(lng) and str(lng[i]).strip()
        if has_lat and has_lng:
            both += 1
    stamps = sorted(v.strip() for v in when[start:] if v and v.strip())

    print("=" * 60)
    print("GOLD DOTS AUDIT   (read-only -- nothing was changed)")
    print("=" * 60)
    print("row 1 is            : %s" % ("a HEADER" if has_header else
                                        "A REAL ADDRESS (no header row)"))
    print("   A1 | B1 | C1 | D1: %s | %s | %s | %s" % (
        (addrs[0] if addrs else "")[:26], (when[0] if when else "")[:20],
        (lat[0] if lat else "")[:11], (lng[0] if lng else "")[:11]))
    print("total address rows  : %d" % len(rows))
    print("unique addresses    : %d" % len(seen))
    print("DUPLICATE rows      : %d  (across %d repeated addresses)"
          % (len(rows) - len(seen), len(dupes)))
    print("rows with lat AND lng: %d" % both)
    print("rows missing either : %d" % (len(rows) - both))
    if stamps:
        print("captured range      : %s  ->  %s" % (stamps[0], stamps[-1]))
    else:
        print("captured range      : (column B is empty)")

    # The writer emits 8 columns; the live tab reportedly holds 4. If E-H are
    # empty then no row carries a Run ID or an Operator -- i.e. there is no
    # provenance on any historical row and they cannot be audited in place.
    wide = []
    for idx, name in ((5, "E Business"), (6, "F Phone"),
                      (7, "G Run ID"), (8, "H Operator")):
        try:
            if any(v.strip() for v in ws.col_values(idx)[start:] if v):
                wide.append(name)
        except Exception:
            pass
    print("columns E-H in use  : %s" % (", ".join(wide) if wide else
                                        "NONE -- no provenance on any row"))

    if dupes:
        print("\nmost-repeated addresses:")
        for k, n in sorted(dupes.items(), key=lambda kv: -kv[1])[:10]:
            print("   %5dx  %s" % (n, k[:50]))

    print("\nSend this whole output back to Claude.")
    return 0


raise SystemExit(main())
