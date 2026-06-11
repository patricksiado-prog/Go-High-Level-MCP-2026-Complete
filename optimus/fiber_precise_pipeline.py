#!/usr/bin/env python3
"""
FIBER PRECISE PIPELINE v0.4 (signal -> ZIP -> capture the map's OWN data ->
EXACT address + lat/lng + BAN -> hand to MapMan for a precise phone)
=========================================================================
WHAT CHANGED FROM v0.3:
 1. BACKEND API CAPTURE IS NOW THE PRIMARY PATH. The map loads its dots from
    a backend JSON API. With --api-substring set (or POPUP_CONFIG
    "address_api_url_substring"), the script captures that response and reads
    EXACT address + lat/lng + Subscriber BAN for EVERY dot in the view --
    no clicking, no pixel detection, no OCR. This removes:
      - HiDPI drift (screenshot px != click px)
      - overlap misattribution (click opens a NEIGHBOR's popup -> the real
        address gets pinned to the wrong house) -- the main inaccuracy
      - color-threshold tuning entirely
    The click/popup path is kept as FALLBACK when no substring is set or a
    capture returns nothing.
 2. NEW --probe MODE to find the substring ONCE: opens the map, you pan/zoom
    and click "Search this area" by hand, it watches every JSON response and
    prints which endpoint carries address/coords/BAN data + the suggested
    substring. Run it once per map version, paste the substring, done.
 3. LAT/LNG IN THE OUTPUT. Leads now carry the map's own coordinates into
    the Precise tab's Lat/Lng columns. MapMan v11.2.5 already reads Lat/Lng
    from its input tab and SKIPS geocoding when present -> routes/door-knock
    lists land on the exact rooftop, not a geocoder's guess.
 4. THRESHOLDS UNIFIED. Dot detection (fallback path only) now imports from
    optimus_dot_detect.py -- the one canonical threshold set shared with
    precise_fiber_hunter. (The old "same thresholds as fiber_hunter" claim
    was wrong; see optimus_dot_detect.py for the analysis.)
 5. RESUME: addresses already in the Precise tab are skipped on re-run.

UNCHANGED ON PURPOSE:
 - PERSISTENT SESSION: you log in ONCE by hand (--login). No passwords are
   typed or stored by this script, no gate automation, no parallel logins.
   This is YOUR single session, reused -- same as clicking the map by hand.
 - Polite pacing between actions; one ZIP per signal.
 - BAN present = existing customer -> Customers tab, NOT a lead.

COMPLIANCE (do not edit around this):
 Output feeds DOOR-KNOCK + DNC-SCRUBBED MANUAL CALL routes only. Map or
 skip-traced numbers are NEVER cold-texted (TCPA $500-$1,500 per text).
 Consent first (verbal yes OK in TX) -> only then the consented GHL drip.

ONE-TIME SETUP (HP):
    pip install playwright gspread google-auth numpy pillow scipy
    python -m playwright install chromium

STEP 1 -- log in once (opens a real window; you pass the gate by hand):
    python fiber_precise_pipeline.py --login

STEP 2 -- find the dot-layer endpoint ONCE (pan/zoom + "Search this area"):
    python fiber_precise_pipeline.py --probe --zip 77070

STEP 3 -- scan a ZIP with the substring from step 2:
    python fiber_precise_pipeline.py --zip 77002 --signal "Comcast outage" \
        --api-substring serviceability

    # or watch the command sheet for OUTAGE signals Claude/portal write:
    python fiber_precise_pipeline.py --watch --api-substring serviceability
=========================================================================
"""

import os, sys, time, re, argparse
from datetime import datetime

from optimus_dot_detect import (GREEN_MIN, GREEN_MAX, GOLD_MIN, GOLD_MAX,
                                ADDRESS_REGEX, BAN_REGEX, POPUP_READY_HINTS,
                                find_dots_in_png_bytes, classify_status,
                                STATUS_LEAD, STATUS_CUSTOMER, STATUS_COPPER_UPGRADE)
from optimus_api_capture import ResponseSniffer

# ---- shared config (matches the rest of Optimus) ------------------------
SHEET_ID = "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA"   # production (leads)
COMMAND_ID = "12PIIplhqUuZWAfEUdJMP3J04nAyrsFsFB07bDDDV2Ag"  # command channel only
PRECISE_TAB = "Precise"               # green: eligible non-customer leads
COPPER_TAB = "Copper Upgrade"         # gold: eligible existing copper customers
SIGNAL_LOG_TAB = "Outage Signals"
CUSTOMERS_TAB = "Customers (has BAN)"  # gray: existing fiber customers (skip)
FIBER_URL = "https://youachieve.att.com/yourefer/fiber"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# persistent login profile (you log in here ONCE; session is reused).
DEFAULT_PROFILE = os.path.join(os.path.expanduser("~"), "Optimus", "att_profile")

# timing / behaviour
MAP_SETTLE = 12        # sec for the map to render after navigation
POPUP_TIMEOUT = 6      # sec to wait for a clicked popup to fill in
BETWEEN_CLICKS = 0.5   # sec between dot clicks (be polite, avoid rate flags)
ZOOM_CLICKS = 4        # keyboard '=' presses to zoom in
CAPTURE_SETTLE = 4     # sec to let the dot-layer API responses land
VIEWPORT = {"width": 1400, "height": 900}

# -------------------------------------------------------------------------
# SELECTORS -- map/search/popup. Tune here if the first run reports misses.
# -------------------------------------------------------------------------
SELECTORS = {
    "map_ready": ".mapboxgl-canvas",
    "geocoder": ".mapboxgl-ctrl-geocoder--input",
    "geocoder_fallback": "input[placeholder*='Search' i], input[type='search'], input[type='text']",
    "popup": ".mapboxgl-popup-content, .mapboxgl-popup, [class*='popup']",
    # text on the access gate -> means we are NOT logged in
    "gate_hints": ["choose your method of access", "method of access"],
    # buttons that open the dot map from the you Refer home
    "map_buttons": ["Fiber Availability Map", "Fiber Map", "Availability Map"],
    # after pan/zoom the map only loads dots for the new view when this is
    # clicked (confirmed live, 77070, 2026-05-31).
    "search_this_area": "Search this area",
}

# -------------------------------------------------------------------------
# POPUP_CONFIG -- fallback click path. address_api_url_substring is the
# BEST path: run --probe once to find it, then pass --api-substring (or
# hardcode it here).
# -------------------------------------------------------------------------
POPUP_CONFIG = {
    "popup_ready_hints": POPUP_READY_HINTS,
    "address_regex": ADDRESS_REGEX,
    "ban_regex": BAN_REGEX,
    "address_api_url_substring": None,   # e.g. "serviceability"
}


def now_str():
    return datetime.now().strftime("%m/%d/%Y %I:%M %p")


# -------------------------------------------------------------------------
# Google Sheets
# -------------------------------------------------------------------------
def find_creds():
    for p in ["google_creds.json",
              os.path.join(os.path.expanduser("~"), "Optimus", "google_creds.json"),
              os.path.join(os.path.expanduser("~"), "Desktop", "google_creds.json"),
              "/storage/emulated/0/Download/google_creds.json"]:
        if os.path.exists(p):
            return p
    return None


def connect_sheets():
    import gspread
    from google.oauth2.service_account import Credentials
    cf = find_creds()
    if not cf:
        print("ERROR: google_creds.json not found.")
        sys.exit(1)
    return gspread.authorize(Credentials.from_service_account_file(cf, scopes=SCOPES))


def ensure_tab(ss, title, headers):
    existing = [w.title for w in ss.worksheets()]
    if title in existing:
        return ss.worksheet(title)
    ws = ss.add_worksheet(title=title, rows=1000, cols=max(20, len(headers)))
    ws.append_row(headers)
    return ws


def log_signal(client, zipc, note):
    ss = client.open_by_key(SHEET_ID)
    ws = ensure_tab(ss, SIGNAL_LOG_TAB, ["Logged At", "ZIP", "Signal", "Status"])
    ws.append_row([now_str(), zipc, note, "RECEIVED"])
    print("  signal logged: %s / %s" % (zipc, note))


def already_seen(ws):
    """Resume: addresses already in the Precise tab get skipped on re-run."""
    try:
        rows = ws.get_all_values()
    except Exception:
        return set()
    return set(r[0].strip().upper() for r in rows[1:] if r and r[0].strip())


# -------------------------------------------------------------------------
# popup parsing (fallback click path)
# -------------------------------------------------------------------------
def parse_popup_text(txt):
    addr = ban = None
    m = re.search(POPUP_CONFIG["address_regex"], txt, re.IGNORECASE | re.DOTALL)
    if m:
        addr = re.sub(r"\s+", " ", m.group(1)).strip()
    m = re.search(POPUP_CONFIG["ban_regex"], txt, re.IGNORECASE)
    if m:
        ban = m.group(1).strip()
    return addr, ban


def read_popup_text(page):
    for sel in SELECTORS["popup"].split(","):
        loc = page.locator(sel.strip())
        try:
            if loc.count() > 0:
                t = loc.first.inner_text(timeout=1500)
                if t and t.strip():
                    return t
        except Exception:
            pass
    try:
        return page.locator("body").inner_text()
    except Exception:
        return ""


def wait_popup(page, deadline):
    start = time.time()
    while time.time() - start < deadline:
        txt = read_popup_text(page)
        low = txt.lower()
        for hint in POPUP_CONFIG["popup_ready_hints"]:
            if hint.lower() in low:
                return txt
        time.sleep(0.15)
    return None


# -------------------------------------------------------------------------
# browser session helpers (persistent profile -> your own reused login)
# -------------------------------------------------------------------------
def open_context(p, headless, profile_dir):
    return p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=headless,
        viewport=VIEWPORT,
        device_scale_factor=1,   # screenshot px == click px (no HiDPI scaling)
        args=["--disable-blink-features=AutomationControlled"],
    )


def at_gate(page):
    try:
        body = page.locator("body").inner_text(timeout=4000).lower()
    except Exception:
        body = ""
    return any(h in body for h in SELECTORS["gate_hints"])


def reach_map(page):
    """Get from wherever we land to the dot map. Returns True if map is up."""
    if page.locator(SELECTORS["map_ready"]).count() > 0:
        return True
    for label in SELECTORS["map_buttons"]:
        try:
            btn = page.get_by_text(label, exact=False)
            if btn.count() > 0:
                btn.first.click()
                time.sleep(MAP_SETTLE)
                if page.locator(SELECTORS["map_ready"]).count() > 0:
                    return True
        except Exception:
            pass
    return page.locator(SELECTORS["map_ready"]).count() > 0


def search_zip(page, zipc):
    geo = page.locator(SELECTORS["geocoder"])
    if geo.count() == 0:
        geo = page.locator(SELECTORS["geocoder_fallback"])
    if geo.count() == 0:
        print("  (no search box found -- scanning the current view)")
        return False
    try:
        geo.first.click()
        geo.first.fill("")
        geo.first.type(zipc, delay=60)
        time.sleep(1.5)
        geo.first.press("Enter")  # Enter centers the map on the ZIP (proven by hand)
        time.sleep(4.0)
        return True
    except Exception as e:
        print("  (search box error: %s)" % str(e)[:80])
        return False


def focus_map(page):
    """Click an empty part of the map so the keyboard +/- zoom registers.
    Proven by hand: you must click the map before pressing + or it won't zoom."""
    try:
        cv = page.locator(SELECTORS["map_ready"]).first
        box = cv.bounding_box()
        if box:
            x = box["x"] + box["width"] * 0.18
            y = box["y"] + box["height"] * 0.22
            page.mouse.click(x, y)
            time.sleep(0.4)
            page.keyboard.press("Escape")  # in case the click grazed a dot
            time.sleep(0.3)
    except Exception:
        pass


def zoom_in(page):
    for _ in range(ZOOM_CLICKS):
        try:
            page.keyboard.press("=")  # same physical key as '+', no shift needed
        except Exception:
            pass
        time.sleep(0.6)
    time.sleep(2)


def search_this_area(page):
    """After pan/zoom the dots for the new view only load when this button is
    clicked. Click it (if present) and wait for the dot layer to refresh."""
    try:
        btn = page.get_by_text(SELECTORS["search_this_area"], exact=False)
        if btn.count() > 0:
            btn.first.click()
            time.sleep(3.5)
            return True
    except Exception:
        pass
    return False


# -------------------------------------------------------------------------
# --login: open a real window so you pass the gate by hand, ONCE.
# -------------------------------------------------------------------------
def login_session(profile_dir):
    from playwright.sync_api import sync_playwright
    print("=" * 64)
    print(" ONE-TIME LOGIN. A Chromium window will open.")
    print(" Log in through AT&T's access gate yourself, get to the Fiber Map,")
    print(" then come back here and press ENTER. Your session is saved to:")
    print("   %s" % profile_dir)
    print(" No password is read or stored by this script.")
    print("=" * 64)
    os.makedirs(profile_dir, exist_ok=True)
    with sync_playwright() as p:
        ctx = open_context(p, headless=False, profile_dir=profile_dir)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(FIBER_URL, wait_until="domcontentloaded", timeout=60000)
        try:
            input("\n >> press ENTER here once you're logged in and on the map... ")
        except EOFError:
            time.sleep(60)
        ok = page.locator(SELECTORS["map_ready"]).count() > 0
        print("  map detected: %s" % ("YES -- session saved, you're set" if ok
                                      else "not detected (login may be incomplete)"))
        ctx.close()


# -------------------------------------------------------------------------
# --probe: find the dot-layer endpoint ONCE (you drive, it listens)
# -------------------------------------------------------------------------
def probe_session(profile_dir, zipc=None):
    from playwright.sync_api import sync_playwright
    sniffer = ResponseSniffer(capture_substring=None, verbose=True)
    print("=" * 64)
    print(" PROBE MODE. A Chromium window will open on the Fiber Map.")
    print(" 1. Pan/zoom to a ZIP with green dots.")
    print(" 2. Click 'Search this area' so the dot layer loads.")
    print(" 3. Click one green dot too (catches per-dot detail endpoints).")
    print(" 4. Come back here and press ENTER for the report.")
    print("=" * 64)
    with sync_playwright() as p:
        ctx = open_context(p, headless=False, profile_dir=profile_dir)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("response", sniffer.on_response)
        page.goto(FIBER_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(MAP_SETTLE)
        if at_gate(page):
            print(" !! Hit AT&T's access gate -- run --login first.")
            ctx.close()
            return
        reach_map(page)
        if zipc:
            search_zip(page, zipc)
            focus_map(page)
            zoom_in(page)
            search_this_area(page)
        try:
            input("\n >> press ENTER here when you've loaded dots on the map... ")
        except EOFError:
            time.sleep(90)
        ctx.close()
    sniffer.probe_report()


# -------------------------------------------------------------------------
# the precise scan: API capture first, click/popup fallback
# -------------------------------------------------------------------------
def precise_scan(zipc, headless, profile_dir, want_gold, on_lead, on_customer,
                 on_copper, seen):
    from playwright.sync_api import sync_playwright

    sub = POPUP_CONFIG.get("address_api_url_substring")
    sniffer = ResponseSniffer(capture_substring=sub, verbose=True) if sub else None

    with sync_playwright() as p:
        ctx = open_context(p, headless=headless, profile_dir=profile_dir)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if sniffer:
            page.on("response", sniffer.on_response)

        page.goto(FIBER_URL, wait_until="domcontentloaded", timeout=45000)
        time.sleep(MAP_SETTLE)

        if at_gate(page):
            print(" !! Hit AT&T's access gate -- this session isn't logged in.")
            print(" !! Run once: python %s --login" % os.path.basename(__file__))
            ctx.close()
            return 0, 0

        if not reach_map(page):
            print(" !! Could not reach the Fiber Map (no map canvas found).")
            ctx.close()
            return 0, 0

        search_zip(page, zipc)
        focus_map(page)   # click the map first so keyboard zoom works
        zoom_in(page)
        if search_this_area(page):
            print("  clicked 'Search this area' -- dots refreshed for this view")
        if sniffer:
            time.sleep(CAPTURE_SETTLE)   # let the dot-layer responses land

        # ---------------- PRIMARY: backend API capture --------------------
        if sniffer and sniffer.features:
            print("  API capture: %d features for this view -- no clicking needed"
                  % len(sniffer.features))
            leads = custs = coppers = 0
            for f in sniffer.features:
                key = f["address"].upper()
                if key in seen:
                    continue
                seen.add(key)
                st = classify_status(text=f.get("status"), ban=f.get("ban"))
                if st == STATUS_CUSTOMER:
                    custs += 1
                    on_customer(f["address"], f["ban"], f["lat"], f["lng"])
                elif st == STATUS_COPPER_UPGRADE:
                    coppers += 1
                    on_copper(f["address"], f["ban"], f["lat"], f["lng"])
                else:
                    leads += 1
                    on_lead(f["address"], "API", f["lat"], f["lng"])
            ctx.close()
            print("  -> %d leads, %d copper-upgrades, %d fiber customers (skipped)"
                  " [exact coords from API]" % (leads, coppers, custs))
            return leads, custs

        if sniffer:
            print("  API capture matched nothing for %r -- falling back to clicks."
                  % sub)
            print("  (Re-run --probe if AT&T changed the map's endpoints.)")

        # ---------------- FALLBACK: click each dot, read the popup --------
        raw = page.screenshot(type="png")
        green, dims = find_dots_in_png_bytes(raw, GREEN_MIN, GREEN_MAX)
        # gold = copper-upgrade customers; a real lead bucket, so always detect.
        gold, _ = find_dots_in_png_bytes(raw, GOLD_MIN, GOLD_MAX)
        img_w, img_h = dims
        sx = VIEWPORT["width"] / img_w if img_w else 1.0
        sy = VIEWPORT["height"] / img_h if img_h else 1.0
        dots = [("GREEN", d) for d in green] + [("GOLD", d) for d in gold]
        print("  detected %d clickable dots (%d green, %d gold)"
              % (len(dots), len(green), len(gold)))

        # gray dots are existing fiber customers -- we never detect/click them.
        leads = custs = coppers = blanks = 0
        for color, (px, py, sz) in dots:
            cx, cy = int(px * sx), int(py * sy)
            try:
                page.mouse.click(cx, cy)
            except Exception:
                continue
            txt = wait_popup(page, POPUP_TIMEOUT)
            if txt is None:
                blanks += 1
                continue
            addr, ban = parse_popup_text(txt)
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(BETWEEN_CLICKS)
            if not addr:
                blanks += 1
                continue
            key = addr.upper()
            if key in seen:
                continue
            seen.add(key)
            st = classify_status(ban=ban, color=color)   # dot color is the legend
            if st == STATUS_CUSTOMER:
                custs += 1
                on_customer(addr, ban, None, None)
            elif st == STATUS_COPPER_UPGRADE:
                coppers += 1
                on_copper(addr, ban, None, None)
            else:
                leads += 1
                on_lead(addr, color, None, None)

        ctx.close()
        print("  -> %d leads, %d copper-upgrades, %d customers, %d blank/closed"
              " [click fallback]" % (leads, coppers, custs, blanks))
        return leads, custs


# -------------------------------------------------------------------------
# write precise leads where MapMan will pick them up
# -------------------------------------------------------------------------
def make_writers(client, zipc):
    ss = client.open_by_key(SHEET_ID)
    # column layout matches Hunter Green Commercial so MapMan can read it.
    # MapMan v11.2.5 reads Address/Lat/Lng/State by header name and SKIPS
    # geocoding when Lat/Lng are present -- so always fill them when known.
    precise_headers = ["Address", "Business Name", "City", "State", "Zip",
                       "Zone", "Instance", "Scan #", "Date", "Phone",
                       "Lat", "Lng", "Business Address", "Phone Source", "Checked At"]
    precise_ws = ensure_tab(ss, PRECISE_TAB, precise_headers)
    copper_ws = ensure_tab(ss, COPPER_TAB, precise_headers)  # same layout for MapMan
    cust_ws = ensure_tab(ss, CUSTOMERS_TAB,
                         ["Logged At", "Address", "Subscriber BAN", "ZIP", "Lat", "Lng"])

    def _lead_row(addr, lat, lng, source):
        return [addr, "", "", "", zipc,
                "Precise_%s" % zipc, "Precise", "1", now_str(), "",
                lat if lat is not None else "", lng if lng is not None else "",
                "", "Precise %s" % source.lower(), ""]

    def on_lead(addr, source, lat, lng):
        precise_ws.append_row(_lead_row(addr, lat, lng, source))
        print("  PRECISE LEAD -> %s%s" % (
            addr, " (%.6f, %.6f)" % (lat, lng) if lat is not None and lng is not None else ""))

    def on_copper(addr, ban, lat, lng):
        # eligible existing copper customer -> fiber UPGRADE pitch, own tab
        copper_ws.append_row(_lead_row(addr, lat, lng, "copper-upgrade"))
        print("  COPPER UPGRADE -> %s%s" % (
            addr, " (BAN %s)" % ban if ban else ""))

    def on_customer(addr, ban, lat, lng):
        cust_ws.append_row([now_str(), addr, ban, zipc,
                            lat if lat is not None else "",
                            lng if lng is not None else ""])
        print("  fiber customer -- %s skipped" % addr)

    return on_lead, on_customer, on_copper, precise_ws


# -------------------------------------------------------------------------
# trigger MapMan to enrich the new precise leads with phones
# -------------------------------------------------------------------------
def trigger_mapman(client):
    try:
        cmd = client.open_by_key(COMMAND_ID).worksheet("COMMAND")
        cmd.update(values=[["RUN_MAPMAN"]], range_name="A1")
        print("  MapMan triggered (RUN_MAPMAN written to command sheet).")
    except Exception as e:
        print("  (could not auto-trigger MapMan: %s) -- run it manually." % str(e)[:80])


# -------------------------------------------------------------------------
# one full run for one outage signal
# -------------------------------------------------------------------------
def run_signal(zipc, note, headless, profile_dir, want_gold, enrich=False):
    print("\n" + "=" * 60)
    print(" PRECISE PIPELINE | ZIP %s | %s" % (zipc, note))
    print("=" * 60)
    client = connect_sheets()
    log_signal(client, zipc, note)
    on_lead, on_customer, on_copper, precise_ws = make_writers(client, zipc)
    seen = already_seen(precise_ws)
    if seen:
        print("  resume: %d addresses already captured -> will skip them" % len(seen))
    leads, custs = precise_scan(zipc, headless, profile_dir, want_gold,
                                on_lead, on_customer, on_copper, seen)
    if leads > 0 and enrich:
        trigger_mapman(client)
    print("\nDONE: %d precise leads written to the '%s' tab, %d customers skipped."
          % (leads, PRECISE_TAB, custs))


# -------------------------------------------------------------------------
# --watch: poll the command sheet for OUTAGE signals
#          A1 = "OUTAGE"   B1 = "77002|Comcast outage"
# -------------------------------------------------------------------------
def watch_loop(headless, profile_dir, want_gold, enrich=False, poll=30):
    print("WATCH MODE: polling command sheet for OUTAGE signals every %ds" % poll)
    client = connect_sheets()
    cmd = client.open_by_key(COMMAND_ID).worksheet("COMMAND")
    last = None
    while True:
        try:
            a1 = (cmd.acell("A1").value or "").strip()
            b1 = (cmd.acell("B1").value or "").strip()
            sig = (a1.upper(), b1)
            if a1.upper() == "OUTAGE" and sig != last:
                last = sig
                parts = b1.split("|", 1)
                zipc = parts[0].strip()
                note = parts[1].strip() if len(parts) > 1 else "outage signal"
                if re.fullmatch(r"\d{5}", zipc):
                    run_signal(zipc, note, headless, profile_dir, want_gold, enrich)
                    cmd.update(values=[["DONE"]], range_name="A1")
                else:
                    print("  bad ZIP in B1: %r" % b1)
        except Exception as e:
            print("  watch error: %s" % str(e)[:100])
        time.sleep(poll)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true",
                    help="one-time: open a window to log in; saves the session")
    ap.add_argument("--probe", action="store_true",
                    help="one-time: find the dot-layer API endpoint (prints the substring)")
    ap.add_argument("--zip", help="5-digit ZIP to scan precisely")
    ap.add_argument("--signal", default="manual outage signal",
                    help="description of the signal/outage")
    ap.add_argument("--watch", action="store_true",
                    help="poll command sheet for OUTAGE signals")
    ap.add_argument("--api-substring", default=None,
                    help="URL substring of the dot-layer JSON API (from --probe); "
                         "enables exact capture, no clicking")
    ap.add_argument("--headless", action="store_true",
                    help="run with no visible window (default: headed)")
    ap.add_argument("--gold", action="store_true",
                    help="also click gold (copper-upgrade) dots [fallback path]")
    ap.add_argument("--enrich", action="store_true",
                    help="trigger MapMan after (point MapMan at the Precise tab)")
    ap.add_argument("--profile", default=DEFAULT_PROFILE,
                    help="persistent login profile folder")
    args = ap.parse_args()

    try:
        import playwright  # noqa
    except ImportError:
        print("ERROR: playwright not installed. Run:")
        print("  pip install playwright")
        print("  python -m playwright install chromium")
        sys.exit(1)

    if args.api_substring:
        POPUP_CONFIG["address_api_url_substring"] = args.api_substring.strip().lower()

    if args.login:
        login_session(args.profile)
    elif args.probe:
        probe_session(args.profile, args.zip)
    elif args.watch:
        watch_loop(args.headless, args.profile, args.gold, args.enrich)
    elif args.zip and re.fullmatch(r"\d{5}", args.zip):
        run_signal(args.zip, args.signal, args.headless, args.profile,
                   args.gold, args.enrich)
    else:
        print("Usage:")
        print("  python fiber_precise_pipeline.py --login                      # once")
        print("  python fiber_precise_pipeline.py --probe --zip 77070          # once")
        print("  python fiber_precise_pipeline.py --zip 77070 --api-substring serviceability")
        print("  python fiber_precise_pipeline.py --watch --api-substring serviceability")


if __name__ == "__main__":
    main()
