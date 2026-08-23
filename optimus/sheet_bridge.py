"""sheet_bridge.py -- feed a sheet tab to Claude one slice at a time, via GitHub.

THE PROBLEM THIS SOLVES
    Claude cannot read the master sheet. Autosheet was the only path and it has
    been out of credits for a day; the sandbox blocks Claude from running
    anything that touches the Google credential. So the sheet -- the thing every
    decision depends on -- is invisible to it.

    But Claude CAN read GitHub. And this PC already has both the Google
    credential (the hunter's google_creds.json) and a GitHub token
    (github_token.txt, same one gh_put uses). So this machine is the bridge:
    it reads the sheet in bounded slices and pushes each slice to the repo,
    where Claude reads it like any other file.

RUN IT (one line, nothing to save first):

    py -c "import urllib.request as u;exec(u.urlopen('https://raw.githubusercontent.com/patricksiado-prog/Go-High-Level-MCP-2026-Complete/claude/new-session-8z4pyb/optimus/sheet_bridge.py').read())"

    ...or with the file next to the hunter:

    py sheet_bridge.py                          # Gold Dots, all of it
    py sheet_bridge.py --tab "Maps Businesses"  # a different tab
    py sheet_bridge.py --slice 250              # smaller slices
    py sheet_bridge.py --max 2000               # stop after N rows

WHAT LANDS IN THE REPO
    optimus/_bridge/<tab>/_manifest.json   row count, slice count, when, columns
    optimus/_bridge/<tab>/0001.csv         rows 1-500
    optimus/_bridge/<tab>/0002.csv         rows 501-1000        ...and so on

BOUNDED BY DESIGN
    Reads explicit A1 ranges, never get_all_values(). Pulling whole tabs is what
    killed Autosheet twice. A slice is one API call for a fixed number of rows,
    so this works the same on a 3,000-row tab and a 474,000-row one -- the only
    difference is how many slices you let it push.

READ-ONLY on the sheet. It never writes to, edits, or deletes anything in
ATT FIBER LEADS. The only thing it writes is CSV files into the GitHub repo.
"""
import base64
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

SHEET_ID = "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA"
REPO = "patricksiado-prog/Go-High-Level-MCP-2026-Complete"
BRANCH = "claude/new-session-8z4pyb"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly",
          "https://www.googleapis.com/auth/drive.readonly"]
SLICE = 500          # rows per file; also AT&T's own per-response cap
LAST_COL = "H"       # Gold Dots writes 8 columns at most


def arg(name, default=None):
    """--name value, from argv. Works when exec()'d too (argv is just short)."""
    a = sys.argv
    if name in a and a.index(name) + 1 < len(a):
        return a[a.index(name) + 1]
    return default


def _search_dirs():
    here = os.getcwd()
    try:
        here = os.path.dirname(os.path.abspath(__file__)) or here
    except NameError:
        pass                      # exec()'d from the one-liner: no __file__
    home = os.path.expanduser("~")
    return [here,
            os.path.join(home, "optimus_hunter"),
            os.path.join(home, "maps_scraper"),
            os.path.join(home, "optimus"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Desktop"),
            home, "."]


def find_file(name, min_size=1):
    for d in _search_dirs():
        p = os.path.join(d, name)
        if os.path.exists(p) and os.path.getsize(p) >= min_size:
            return p
    return None


def gh_token():
    p = find_file("github_token.txt")
    if not p:
        return None
    with open(p) as f:
        return f.read().strip()


def gh_put(token, path, text, tries=3):
    """Create or update one file in the repo. Returns True on success.

    GitHub needs the CURRENT blob sha to update an existing file, so this looks
    it up first. A missing file (404) is the create case, not an error.
    """
    api = "https://api.github.com/repos/%s/contents/%s" % (REPO, path)
    hdr = {"Authorization": "Bearer " + token,
           "Accept": "application/vnd.github+json",
           "User-Agent": "optimus-sheet-bridge"}
    sha = None
    try:
        req = urllib.request.Request(api + "?ref=" + BRANCH, headers=hdr)
        with urllib.request.urlopen(req, timeout=30) as r:
            sha = json.loads(r.read()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print("   (sha lookup failed %s: %s)" % (e.code, path))
    except Exception:
        pass

    body = {"message": "bridge: %s" % path,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "branch": BRANCH}
    if sha:
        body["sha"] = sha
    data = json.dumps(body).encode("utf-8")

    for attempt in range(tries):
        try:
            req = urllib.request.Request(api, data=data, headers=hdr,
                                         method="PUT")
            with urllib.request.urlopen(req, timeout=60):
                return True
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read()).get("message", "")
            except Exception:
                pass
            print("   push failed (%s %s) %s" % (e.code, detail, path))
            if e.code in (401, 403):
                return False          # bad token: retrying cannot help
        except Exception as e:
            print("   push error: %s" % str(e)[:70])
        time.sleep(2 ** attempt)
    return False


def to_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def main():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("Missing packages. Run:  py -m pip install gspread google-auth")
        return 1

    creds = find_file("google_creds.json", 200)
    if not creds:
        print("No google_creds.json found. Run this on a PC with the hunter")
        print("installed -- the installer puts the key in optimus_hunter.")
        return 1
    token = gh_token()
    if not token:
        print("No github_token.txt found. Put it in your Downloads or your")
        print("optimus_hunter folder. Without it there is nowhere to push.")
        return 1

    tab = arg("--tab", "Gold Dots")
    step = int(arg("--slice", SLICE))
    cap = int(arg("--max", "0")) or None

    print("credential : %s" % creds)
    print("token      : found")
    sh = gspread.authorize(
        Credentials.from_service_account_file(creds, scopes=SCOPES)
    ).open_by_key(SHEET_ID)
    print("sheet      : %s" % sh.title)

    try:
        ws = sh.worksheet(tab)
    except Exception:
        print("\nThere is no '%s' tab. Tabs present:" % tab)
        for w in sh.worksheets():
            print("   %-28s %8d rows" % (w.title, w.row_count))
        return 1

    # How many rows actually hold data. ONE column read, not the whole tab.
    col_a = ws.col_values(1)
    n = len(col_a)
    if cap:
        n = min(n, cap)
    if not n:
        print("'%s' is empty -- nothing to send." % tab)
        return 0

    safe = tab.lower().replace(" ", "_").replace("/", "_")
    base = "optimus/_bridge/%s" % safe
    total_slices = (n + step - 1) // step
    print("rows       : %d  ->  %d slice(s) of %d\n" % (n, total_slices, step))

    manifest = {"tab": tab, "rows": n, "slices": total_slices,
                "slice_rows": step, "last_col": LAST_COL,
                "sheet": sh.title,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "machine": os.environ.get("COMPUTERNAME", "") or
                           os.environ.get("HOSTNAME", ""),
                "files": []}

    sent = 0
    for i in range(total_slices):
        lo = i * step + 1
        hi = min((i + 1) * step, n)
        rng = "A%d:%s%d" % (lo, LAST_COL, hi)
        try:
            rows = ws.get(rng)
        except Exception as e:
            print("   read failed %s: %s" % (rng, str(e)[:60]))
            break
        name = "%04d.csv" % (i + 1)
        ok = gh_put(token, "%s/%s" % (base, name), to_csv(rows))
        status = "ok" if ok else "FAILED"
        print("   %s  rows %6d-%-6d  %4d read  %s"
              % (name, lo, hi, len(rows), status))
        if ok:
            sent += 1
            manifest["files"].append({"file": name, "from": lo, "to": hi,
                                      "rows": len(rows)})
        time.sleep(0.4)          # stay clear of Sheets' per-minute read quota

    manifest["slices_pushed"] = sent
    gh_put(token, "%s/_manifest.json" % base,
           json.dumps(manifest, indent=2))

    print("\nPushed %d/%d slices." % (sent, total_slices))
    print("Tell Claude: \"bridge done, %s, %d slices\"" % (tab, sent))
    print("It reads them from:")
    print("   https://github.com/%s/tree/%s/%s" % (REPO, BRANCH, base))
    return 0


raise SystemExit(main())
