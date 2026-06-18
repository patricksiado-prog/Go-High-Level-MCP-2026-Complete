#!/usr/bin/env python3
"""
DIALER LOADER v1.0 -- the combined fiber business leads -> GoHighLevel power dialer.
=============================================================================
This is the last link in the chain. The precise hunter already wrote the
matched businesses to two Google Sheet tabs:
  - "Fiber Green Biz"  = green dot (fiber-eligible non-customer) + business
  - "Upgrade Orange Biz" = gold/orange dot (copper upgrade) + business
This script reads those tabs, scores each business (business_score), and loads
them into GHL Command's AT&T Commercial pipeline as call-ready opportunities,
then enrolls each into the "Optimus Fiber Biz -- Power Dialer Queue" workflow
(ghl_loader). After it runs, you open GHL's power dialer and the queue is
waiting, highest-value business first.

IMPORTANT -- WHAT THIS DOES AND DOES NOT DO:
  It STAGES and ORDERS the work in GHL. It does NOT place calls and does NOT
  send texts. The actual dialing is GHL's power dialer with a LIVE human on
  every call -- that is the deliberate, TCPA-defensible design (auto/predictive
  dialing of skip-traced numbers is the liability the brain-doc forbids).

SAFETY: live CRM writes. Runs a DRY PREVIEW first (writes nothing), shows you
exactly what would load, and only loads for real after you confirm (or with
--commit). Dedupe across runs is handled by ghl_loader's state file, so
re-running never double-loads the same business.

AUTH: the GHL Private Integration token (pit-...). Read from GHL_PIT_TOKEN, or
~/optimus/ghl_token.txt (the launcher caches it there on first run). Never
hardcoded.
"""

import os, sys, json, argparse

# run from the optimus/ dir so these resolve (the launcher cd's there)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghl_loader
import business_score
from optimus_dot_detect import STATUS_LEAD, STATUS_COPPER_UPGRADE

SHEET_ID = "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA"
GREEN_TAB = "Fiber Green Biz"
ORANGE_TAB = "Upgrade Orange Biz"
TOKEN_FILE = os.path.join(os.path.expanduser("~"), "optimus", "ghl_token.txt")
DNC_FILE = os.path.join(os.path.expanduser("~"), "optimus", "dnc.txt")


def _find_creds():
    for p in (os.path.join(os.path.expanduser("~"), "optimus", "google_creds.json"),
              os.path.join(os.path.expanduser("~"), "maps_scraper", "google_creds.json"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "google_creds.json")):
        if os.path.exists(p):
            return p
    return None


def _open_sheet():
    creds = _find_creds()
    if not creds:
        print("  ERROR: no google_creds.json found -- can't read the lead tabs.")
        return None
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    client = gspread.authorize(Credentials.from_service_account_file(creds, scopes=scopes))
    return client.open_by_key(SHEET_ID)


def _digits(s):
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def _load_dnc():
    """Internal do-not-call list: one phone per line in ~/optimus/dnc.txt."""
    nums = set()
    try:
        with open(DNC_FILE) as f:
            for line in f:
                d = _digits(line)
                if len(d) >= 10:
                    nums.add(d[-10:])
    except Exception:
        pass
    return nums


def _read_tab(sh, title, status):
    """Read one biz tab -> list of business dicts shaped for scoring/loading.
    Columns: Business Name, Phone, Address, Website, Category."""
    try:
        ws = sh.worksheet(title)
    except Exception:
        print("  (no '%s' tab yet -- run the hunter against scraped areas first.)" % title)
        return []
    out = []
    for r in ws.get_all_values()[1:]:
        r = (list(r) + [""] * 5)[:5]
        name, phone, addr, website, category = (c.strip() for c in r)
        if not (name or addr):
            continue
        out.append({
            "name": name,
            "phone": phone,
            "address": addr,
            "website": website,
            "types": [category] if category else [],
            "status": status,
            "zone_label": "WORKING",
            "has_phone": len(_digits(phone)) >= 10,
            "phone_type": None,         # unknown from Maps; landline/wireless not classified here
            "in_ghl": False,
            "source_tab": title,
        })
    return out


def _read_precise_fiber(sh):
    """Pull matched businesses straight from the merged Precise Fiber tab
    (Address, Dot Color, Captured At, Business, Phone) -- the freshest matches the
    hunter writes inline. Only rows that have a Business + a real Phone."""
    try:
        ws = sh.worksheet("Precise Fiber")
    except Exception:
        return []
    out = []
    for r in ws.get_all_values()[1:]:
        r = (list(r) + [""] * 5)[:5]
        addr, color, ts, name, phone = (c.strip() for c in r)
        if not name or len(_digits(phone)) < 10:
            continue
        status = STATUS_COPPER_UPGRADE if color.upper() == "ORANGE" else STATUS_LEAD
        out.append({
            "name": name, "phone": phone, "address": addr, "website": "",
            "types": [], "status": status, "zone_label": "WORKING",
            "has_phone": True, "phone_type": None, "in_ghl": False,
            "source_tab": "Precise Fiber",
        })
    return out


def gather_leads(sh):
    """All match sources -> deduped, scored, DNC-scrubbed business dicts (best-first).
    Reads the green/orange biz tabs AND the merged Precise Fiber tab so it always
    pulls the most recent matches; dedupes by phone so a business is loaded once."""
    raw = (_read_tab(sh, GREEN_TAB, STATUS_LEAD)
           + _read_tab(sh, ORANGE_TAB, STATUS_COPPER_UPGRADE)
           + _read_precise_fiber(sh))
    # dedupe by phone (same business shows up across tabs + apartment units)
    seen, dedup = set(), []
    for b in raw:
        ph = _digits(b.get("phone"))[-10:]
        key = ph if len(ph) == 10 else (b.get("name", "").lower() + "|" + b.get("address", "").lower())
        if key in seen:
            continue
        seen.add(key)
        dedup.append(b)
    raw = dedup
    dnc = _load_dnc()
    if dnc:
        for b in raw:
            if _digits(b.get("phone"))[-10:] in dnc:
                b["on_dnc"] = True
    ranked = business_score.rank_businesses(raw)   # drops non-callable (no phone / DNC / customer)
    leads = []
    for r in ranked:
        b = dict(r["business"])
        b["score"] = r["score"]
        leads.append(b)
    return leads, len(raw)


def get_token():
    tok = os.environ.get("GHL_PIT_TOKEN")
    if tok:
        return tok.strip()
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except Exception:
        return None


def _find_git():
    import shutil
    g = shutil.which("git")
    if g:
        return g
    for c in (r"C:\Program Files\Git\cmd\git.exe",
              r"C:\Program Files (x86)\Git\cmd\git.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe")):
        if os.path.exists(c):
            return c
    return "git"


def self_update():
    """Pull the latest code from GitHub on launch and relaunch once, so the dialer
    is always current (runs from the cloned repo). Guard: DIALER_NO_UPDATE=1."""
    import subprocess, sys
    if os.environ.get("DIALER_NO_UPDATE") == "1":
        return
    here = os.path.abspath(__file__)
    repo = os.path.dirname(os.path.dirname(here))            # .../optimus/x -> repo
    if not os.path.isdir(os.path.join(repo, ".git")):
        return
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    git = _find_git()
    branch = "claude/optimus-map-tools-setup-6dcl6o"
    try:
        before = open(here, "rb").read()
        subprocess.run([git, "-C", repo, "fetch", "origin", branch],
                       env=env, timeout=90, capture_output=True, text=True)
        subprocess.run([git, "-C", repo, "reset", "--hard", "origin/" + branch],
                       env=env, timeout=60, capture_output=True, text=True)
        after = open(here, "rb").read()
    except Exception:
        return
    if after != before:
        print("Updated the dialer from GitHub -- relaunching...\n")
        try:
            r = subprocess.run([sys.executable] + sys.argv,
                               env=dict(os.environ, DIALER_NO_UPDATE="1"))
            sys.exit(r.returncode)
        except Exception:
            pass


def main():
    self_update()
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="load to GHL for real (default: preview, then ask)")
    ap.add_argument("--agents", default="",
                    help="comma-separated GHL user ids to round-robin assign the calls")
    args = ap.parse_args()

    print("\n  ============================================================")
    print("     OPTIMUS DIALER LOADER  --  leads -> GHL power dialer")
    print("  ============================================================\n")

    sh = _open_sheet()
    if sh is None:
        sys.exit(1)
    leads, raw_n = gather_leads(sh)
    print("  Read %d business rows from '%s' + '%s' -> %d callable after scoring/DNC.\n"
          % (raw_n, GREEN_TAB, ORANGE_TAB, len(leads)))
    if not leads:
        print("  Nothing to load. Run the hunter (with the scraper feeding 'Maps "
              "Businesses') so the green/orange business tabs fill up first.")
        return

    # DRY PREVIEW first -- always show what would load
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    print("  --- PREVIEW (top 10, nothing written yet) ---")
    ghl_loader.load_businesses(leads, agents, _week_tag(), token=None, commit=False)
    print("  ---------------------------------------------\n")

    token = get_token()
    if not token:
        print("  To load for real I need your GHL Private Integration token (pit-...).")
        try:
            token = input("  Paste it here (or press Enter to stop): ").strip()
        except EOFError:
            token = ""
        if token:
            try:
                os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
                with open(TOKEN_FILE, "w") as f:
                    f.write(token)
                print("  (saved -- you won't be asked again on this PC.)")
            except Exception:
                pass
    if not token:
        print("\n  No token -> stopping. Nothing was loaded.")
        return

    go = args.commit
    if not go:
        try:
            go = input("\n  Load these %d leads into the GHL power dialer for real? (y/N) "
                       % len(leads)).strip().lower() == "y"
        except EOFError:
            go = False
    if not go:
        print("  OK -- nothing loaded. (Preview only.)")
        return

    summary = ghl_loader.load_businesses(leads, agents, _week_tag(), token=token, commit=True)
    print("\n  LOADED %d into GHL (AT&T Commercial pipeline) and enrolled them in the "
          "Power Dialer Queue.\n  Dupes skipped (already loaded before): %d"
          % (summary["loaded"], summary["skipped_dupes"]))
    print("  Now open GHL > power dialer: the queue is waiting, best business first.")
    print("  (Calls are human-on-every-call; this only staged the work.)")


def _week_tag():
    from datetime import datetime
    return datetime.now().strftime("week-%G-W%V")


if __name__ == "__main__":
    main()
