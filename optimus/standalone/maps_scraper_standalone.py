#!/usr/bin/env python3
"""
GOOGLE MAPS BUSINESS SCRAPER -- standalone (the "guts").
=============================================================================
Self-contained: asks for ZIP codes, searches Google Maps for small/in-home
businesses by category, and writes businesses.csv (Name, Address, Phone,
Website, Category). The only dependency is Playwright, which the setup file
installs. Lives in Drive so it can be updated without re-sharing the installer.

Run by SCRAPER_SETUP.bat, or directly:  python maps_scraper_standalone.py
"""

import os, csv, re, time, json, urllib.parse

VERSION = "2.1 (2026-06-18)"   # bump this when the scraper changes; printed on start

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "businesses.csv")
PROFILE_DIR = os.path.join(HERE, "maps_profile")
PROGRESS_PATH = os.path.join(HERE, "maps_progress.json")   # resume: done searches
ZIPS_DONE_PATH = os.path.join(HERE, "maps_zips_done.json")  # ZIPs fully covered
FIELDS = ["name", "address", "phone", "website", "category"]

# Google Sheet destination (option 2). Results go to this sheet's tab below.
SHEET_ID = "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA"
SHEET_TAB = "Maps Businesses"
PER_QUERY_MAX = 120
SCROLL_ROUNDS = 18
THROTTLE = 0.8
_PHONE_RE = re.compile(r"\+?\d[\d\-\.\s\(\)]{8,}\d")

# category sets -- the run asks Light / Heavy / Deep at the start.
CATEGORIES_LIGHT = [
    "plumber", "electrician", "hvac", "roofing", "general contractor",
    "painter", "handyman", "landscaping", "house cleaning", "junk removal",
    "auto repair", "dog grooming", "hair salon", "barber shop",
    "chiropractor", "photographer", "real estate agent", "insurance agent",
]
CATEGORIES_HEAVY = [
    "plumber", "electrician", "hvac", "roofing", "general contractor",
    "painter", "handyman", "landscaping", "pest control", "flooring",
    "house cleaning", "carpet cleaning", "junk removal", "moving company",
    "appliance repair", "garage door repair", "locksmith", "tree service",
    "pressure washing", "pool cleaning", "auto repair", "auto detailing",
    "mobile mechanic", "tire shop", "dog grooming", "pet sitting",
    "dog training", "hair salon", "barber shop",
    "massage therapist", "esthetician", "tattoo shop", "chiropractor",
    "physical therapy", "catering", "bakery", "coffee shop",
    "food truck", "photographer", "bookkeeper", "real estate agent",
    "insurance agent", "tutoring", "home daycare", "notary public",
]
_DEEP_EXTRA = [
    "maid service", "window cleaning", "lawn mowing service", "gutter cleaning",
    "chimney sweep", "fence company", "blind cleaning", "home organizer",
    "air conditioning repair", "remodeling contractor", "tile installer",
    "drywall", "carpenter", "concrete contractor", "paving contractor",
    "solar installer", "welding", "masonry", "septic service",
    "insulation contractor", "cabinet maker", "countertop installer",
    "irrigation", "landscape lighting", "mobile detailing", "windshield repair",
    "transmission repair", "body shop", "oil change", "car wash",
    "window tinting", "mobile dog grooming", "dog walking", "pet boarding",
    "lash extensions", "eyebrow threading", "makeup artist", "spray tan",
    "med spa", "waxing salon", "piercing studio", "hair braiding",
    "mobile hairstylist", "acupuncture", "counseling", "therapist",
    "nutritionist", "dietitian", "personal trainer", "yoga studio",
    "pilates studio", "orthodontist", "optometrist", "podiatrist",
    "dermatologist", "personal chef", "cake decorator", "meal prep",
    "juice bar", "videographer", "graphic designer", "web designer",
    "marketing agency", "accountant", "tax preparer", "virtual assistant",
    "financial advisor", "mortgage broker", "life coach", "business consultant",
    "event planner", "wedding planner", "dj service", "florist",
    "interior designer", "architect", "travel agent", "computer repair",
    "phone repair", "tv repair", "upholstery", "sewing alterations", "tailor",
    "shoe repair", "watch repair", "jewelry repair", "screen printing",
    "embroidery", "sign shop", "print shop", "music lessons", "piano lessons",
    "guitar lessons", "art classes", "swim lessons", "driving school",
    "martial arts", "dance studio", "boutique", "consignment shop",
    "thrift store", "smoke shop", "vape shop", "gift shop", "bike shop",
    "hobby shop", "candle shop", "soap maker",
]
CATEGORIES_DEEP = CATEGORIES_HEAVY + _DEEP_EXTRA


def categories_for(level):
    """Pick a set: '1'/light, '3'/deep, else heavy ('2')."""
    lv = str(level or "2").strip().lower()
    if lv.startswith("1") or lv.startswith("l"):
        return CATEGORIES_LIGHT
    if lv.startswith("3") or lv.startswith("d"):
        return CATEGORIES_DEEP
    return CATEGORIES_HEAVY


# Big-box + national chains + franchises -- SKIP these. On a chain/franchise the
# person on site can't decide on fiber (it's corporate-procured), so they're not
# a callable prospect. We only keep local, owner-operated businesses.
CHAINS = {
    # big-box / retail / grocery / pharmacy
    "walmart", "wal-mart", "target", "costco", "sam's club", "sams club",
    "home depot", "lowe's", "lowes", "best buy", "apple store", "kroger",
    "h-e-b", "heb", "central market", "whole foods", "trader joe", "cvs",
    "walgreens", "rite aid", "ikea", "macy's", "nordstrom", "dillard",
    "jcpenney", "jc penney", "kohl's", "ross", "marshalls", "tj maxx",
    "t.j. maxx", "homegoods", "home goods", "petco", "petsmart", "gamestop",
    "hobby lobby", "michaels", "barnes & noble", "dick's sporting",
    "academy sports", "office depot", "staples", "five below", "aldi",
    "publix", "safeway", "dollar general", "dollar tree", "family dollar",
    "sephora", "ulta", "bath & body", "crate & barrel", "crate and barrel",
    "pottery barn", "williams sonoma", "west elm", "anthropologie",
    "restoration hardware",
    # banks / telecom / shipping
    "bank of america", "chase bank", "wells fargo", "capital one", "citibank",
    "us bank", "fedex", "ups store", "usps", "verizon", "t-mobile", "at&t store",
    "xfinity", "spectrum",
    # fast food / chain restaurants
    "mcdonald", "starbucks", "chick-fil-a", "chickfila", "chipotle", "subway",
    "wendy's", "burger king", "taco bell", "panera", "dunkin", "panda express",
    "olive garden", "chili's", "applebee", "ihop", "denny's", "buffalo wild",
    "raising cane", "whataburger", "jack in the box", "sonic drive", "in-n-out",
    "popeyes", "kfc", "pizza hut", "domino", "little caesars", "jimmy john",
    "jersey mike", "papa john", "wingstop", "5 guys", "five guys", "dairy queen",
    # gas / convenience
    "7-eleven", "7 eleven", "shell", "exxon", "chevron", "circle k", "valero",
    "buc-ee", "quiktrip", "racetrac",
    # service-category FRANCHISES (on-site mgr can't decide on fiber)
    "jiffy lube", "valvoline", "midas", "meineke", "firestone", "discount tire",
    "ntb", "take 5", "christian brothers", "aamco", "maaco",
    "great clips", "supercuts", "sport clips", "fantastic sams", "sola salon",
    "planet fitness", "la fitness", "24 hour fitness", "anytime fitness",
    "orangetheory", "crunch fitness", "gold's gym", "ymca",
    "massage envy", "european wax", "hand and stone", "drybar",
    "servpro", "stanley steemer", "chem-dry", "molly maid", "merry maids",
    "the maids", "two maids", "terminix", "orkin", "truly nolen", "mosquito joe",
    "1-800-got-junk", "college hunks", "junk king", "two men and a truck",
    "mr. handyman", "ace handyman", "roto-rooter", "roto rooter",
    "benjamin franklin", "mr. rooter", "mr. electric", "one hour", "aire serv",
    "kumon", "mathnasium", "sylvan", "goldfish swim", "british swim",
    "the ups store", "postal annex", "fastsigns", "signarama", "minuteman press",
}


def _is_local(name):
    """True if this looks like a local, owner-operated business (skip chains)."""
    n = (name or "").lower()
    return not any(c in n for c in CHAINS)


def _dismiss_consent(page):
    for sel in ("button[aria-label*='Accept all' i]",
                "button:has-text('Accept all')",
                "form[action*='consent'] button"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(1500)
                return
        except Exception:
            pass


def _text_attr(page, selector):
    try:
        el = page.query_selector(selector)
        if el:
            return el.get_attribute("aria-label") or el.inner_text()
    except Exception:
        pass
    return None


def _collect_links(page):
    out = {}
    for c in page.query_selector_all('a[href*="/maps/place/"]'):
        try:
            href = c.get_attribute("href")
            name = c.get_attribute("aria-label")
            if href and name and href not in out:
                out[href] = name
        except Exception:
            pass
    return out


def scrape_query(page, query, category):
    target_zip = query.split(" in ")[-1].strip() if " in " in query else ""
    page.goto("https://www.google.com/maps/search/" + urllib.parse.quote(query),
              wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)
    _dismiss_consent(page)
    if "/sorry/" in page.url or "consent.google" in page.url:
        return None
    feed = page.query_selector('div[role="feed"]')
    links, last = {}, -1
    for _ in range(SCROLL_ROUNDS):
        links.update(_collect_links(page))
        if len(links) >= PER_QUERY_MAX or len(links) == last:
            break
        last = len(links)
        if feed:
            try:
                page.evaluate("(el) => el.scrollBy(0, el.scrollHeight)", feed)
            except Exception:
                pass
        page.wait_for_timeout(1400)
    rows = []
    for href, name in list(links.items())[:PER_QUERY_MAX]:
        if not _is_local(name):        # skip big-box / chains / franchises
            continue
        try:
            page.goto(href, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1100)
            addr = _text_attr(page, "button[data-item-id='address']")
            phone_lbl = _text_attr(page, "button[data-item-id^='phone']")
            website = None
            w = page.query_selector("a[data-item-id='authority']")
            if w:
                website = w.get_attribute("href")
            phone = None
            if phone_lbl:
                m = _PHONE_RE.search(phone_lbl)
                phone = m.group(0).strip() if m else None
            addr = (addr or "").replace("Address: ", "").strip()
            if target_zip and target_zip not in addr:
                continue                 # keep only businesses actually in the ZIP
            rows.append({"name": name, "address": addr,
                         "phone": phone, "website": website, "category": category})
        except Exception:
            continue
        time.sleep(THROTTLE)
    return rows


def load_progress():
    """Searches already completed in a prior run (so a stopped run resumes)."""
    try:
        with open(PROGRESS_PATH) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_progress(done):
    try:
        with open(PROGRESS_PATH, "w") as f:
            json.dump(sorted(done), f)
    except Exception:
        pass


def clear_progress():
    """Wipe progress after a clean full run, so the next run starts fresh."""
    try:
        os.remove(PROGRESS_PATH)
    except Exception:
        pass


# After the ZIPs you enter, the scraper AUTO-ADVANCES through nearby fiber ZIPs in
# the SAME metro (inner-loop first), skipping any already finished, until you close
# it. It picks the list by the region of the FIRST ZIP you enter, so a market stays
# in its own lane -- an OKC ZIP never rolls into Houston (which would mix cities in
# the 'Maps Businesses' tab and pollute the Houston dialer).
HOUSTON_ZIPS = ["77027", "77098", "77006", "77019", "77005", "77025", "77002", "77004",
                "77003", "77007", "77008", "77009", "77030", "77023", "77046", "77056",
                "77057", "77081", "77401", "77055", "77024", "77018", "77020", "77026",
                "77087", "77021", "77033", "77074", "77036", "77063", "77042", "77077",
                "77079", "77080", "77043", "77092", "77017", "77011", "77012", "77051"]
# Oklahoma City metro fiber ZIPs (inner OKC first, then Edmond/Norman/Moore/MWC).
OKC_ZIPS = ["73106", "73103", "73102", "73104", "73105", "73107", "73108", "73109",
            "73112", "73118", "73116", "73114", "73111", "73120", "73127", "73128",
            "73119", "73129", "73139", "73142", "73159", "73162", "73170", "73013",
            "73034", "73003", "73160", "73110", "73130", "73069", "73071", "73072"]
REGIONS = [("Houston", HOUSTON_ZIPS), ("Oklahoma City", OKC_ZIPS)]
# 3-digit ZIP prefixes -> region, so a ZIP we didn't hardcode still lands in the
# right lane (or no auto-advance if it's a metro we don't have a list for).
_REGION_PREFIX = {"770": "Houston", "771": "Houston", "772": "Houston",
                  "773": "Houston", "774": "Houston", "775": "Houston",
                  "730": "Oklahoma City", "731": "Oklahoma City"}
NEXT_ZIPS = HOUSTON_ZIPS   # back-compat alias


def region_for(zip_code):
    """Return (region_name, its ZIP list) for a ZIP, so the auto-advance stays in
    that metro. Unknown metro -> (None, []) = fall back to numeric-nearby ZIPs."""
    z = (zip_code or "").strip()
    for name, zips in REGIONS:
        if z in zips:
            return name, zips
    name = _REGION_PREFIX.get(z[:3])
    for rn, zips in REGIONS:
        if rn == name:
            return rn, zips
    return None, []


def nearby_zips(seeds, want=60):
    """Generate ZIPs numerically near the seed ZIP(s) -- the 'next logical place'
    once the curated metro list runs out. ZIP numbering is GEOGRAPHIC (the first 3
    digits = a Sectional Center Facility, a physical region), so same-SCF and
    adjacent-SCF ZIPs are physically nearby. Returns them ordered by distance from
    the seed, so it expands outward. Empty/rural ZIPs just scrape few businesses --
    harmless, it moves on. Keeps the scraper covering ground on its own."""
    seed_ints = sorted({int(z) for z in seeds if z.isdigit() and len(z) == 5})
    if not seed_ints:
        return []
    scfs = set()
    for z in seed_ints:
        s = z // 100                     # first 3 digits = the SCF (a real region)
        for d in (-2, -1, 0, 1, 2):
            if s + d > 0:
                scfs.add(s + d)
    cands = []
    for scf in scfs:
        for tail in range(100):
            c = scf * 100 + tail
            if 0 < c < 100000 and c not in seed_ints:
                cands.append(c)
    cands.sort(key=lambda c: min(abs(c - z) for z in seed_ints))   # closest first
    return ["%05d" % c for c in cands[:want]]


def load_zips_done():
    try:
        with open(ZIPS_DONE_PATH) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_zips_done(z):
    try:
        with open(ZIPS_DONE_PATH, "w") as f:
            json.dump(sorted(z), f)
    except Exception:
        pass


def _find_creds():
    for p in (os.path.join(os.path.expanduser("~"), "maps_scraper", "google_creds.json"),
              os.path.join(os.path.expanduser("~"), "optimus", "google_creds.json"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "google_creds.json")):
        if os.path.exists(p):
            return p
    return None


def open_sheet():
    """Open (or create) the 'Maps Businesses' tab ONCE at the start, and read the
    rows already there so we don't duplicate. Returns (worksheet, seen-keys-set)
    or (None, set()) if there's no key. Needs google_creds.json on the machine."""
    creds = _find_creds()
    if not creds:
        print("\n  (No google_creds.json found -- results go to the CSV only.)")
        return None, set()
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        client = gspread.authorize(Credentials.from_service_account_file(creds, scopes=scopes))
        sh = client.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(SHEET_TAB)
        except Exception:
            ws = sh.add_worksheet(title=SHEET_TAB, rows="20000", cols="5")
        if not ws.get_all_values():
            ws.append_row(["Name", "Address", "Phone", "Website", "Category"])
        seen = set()
        try:
            for r in ws.get_all_values()[1:]:
                if len(r) >= 2:
                    seen.add(r[0].strip().upper() + "|" + r[1].strip().upper())
        except Exception:
            pass
        print("  -> writing to the '%s' tab live, as it runs." % SHEET_TAB)
        try:                       # load captured fiber leads for the cross-match
            init_match(sh)
        except Exception:
            pass
        return ws, seen
    except Exception as e:
        print("\n  (Could not open the sheet: %s -- results go to the CSV.)" % str(e)[:80])
        return None, set()


# ---------------------------------------------------------------------------
# CROSS-MATCH (the scraper's side of the combo): as we scrape each business, if
# its address already has a captured GREEN/ORANGE fiber dot we write the match to
# the same 'Fiber Green Biz' / 'Upgrade Orange Biz' tabs the hunter uses -- so BOTH
# programs build the combined list, from their own side, in real time.
# ---------------------------------------------------------------------------
GREEN_BIZ_TAB = "Fiber Green Biz"
ORANGE_BIZ_TAB = "Upgrade Orange Biz"
BIZ_HEADER = ["Business Name", "Phone", "Address", "Website", "Category"]
_SUF = {"ST": "ST", "STREET": "ST", "AVE": "AVE", "AV": "AVE", "AVENUE": "AVE",
        "RD": "RD", "ROAD": "RD", "DR": "DR", "DRIVE": "DR", "LN": "LN", "LANE": "LN",
        "BLVD": "BLVD", "BOULEVARD": "BLVD", "CT": "CT", "COURT": "CT", "PL": "PL",
        "PLACE": "PL", "WAY": "WAY", "CIR": "CIR", "CIRCLE": "CIR", "TER": "TER",
        "TERRACE": "TER", "TRL": "TRL", "TRAIL": "TRL", "PKWY": "PKWY",
        "PARKWAY": "PKWY", "HWY": "HWY", "HIGHWAY": "HWY"}
_UNIT = re.compile(r"\b(APT|APARTMENT|UNIT|STE|SUITE|#|BLDG|BUILDING|FL|FLOOR|RM|"
                   r"ROOM|OFC|OFFICE|TRLR|LOT|SPC)\b.*$", re.I)
_MATCH = {"leads": None, "green_ws": None, "orange_ws": None,
          "green_seen": set(), "orange_seen": set()}


def _norm_addr(a):
    if not a:
        return ""
    s = a.upper().strip().split(",")[0]
    s = _UNIT.sub("", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"^(\d+)\s+(.*)$", s)
    if not m:
        return ""
    h, rest = m.group(1), m.group(2).split()
    if not rest:
        return ""
    if rest[-1] in _SUF:
        rest[-1] = _SUF[rest[-1]]
    rest = ["N" if t == "NORTH" else "S" if t == "SOUTH" else "E" if t == "EAST"
            else "W" if t == "WEST" else t for t in rest]
    return "%s|%s" % (h, " ".join(rest))


def _ensure_match_tab(sh, title):
    try:
        ws = sh.worksheet(title)
    except Exception:
        ws = sh.add_worksheet(title=title, rows="200", cols="5")
    if not ws.get_all_values():
        ws.append_row(BIZ_HEADER)
    return ws


def init_match(sh):
    """Load captured fiber leads (Precise Fiber: Address, Dot Color) so each scraped
    business can be flagged if it sits on a GREEN/ORANGE dot, and open the two match
    tabs. No-op if there's no Precise Fiber tab yet."""
    try:
        pf = sh.worksheet("Precise Fiber").get_all_values()
    except Exception:
        _MATCH["leads"] = {}
        return
    leads = {}
    for r in pf[1:]:
        r = (list(r) + [""] * 5)[:5]
        color = (r[1] or "").strip().upper()
        if color not in ("GREEN", "ORANGE"):
            continue
        k = _norm_addr(r[0])
        if k and k not in leads:
            leads[k] = color
    _MATCH["leads"] = leads
    try:
        _MATCH["green_ws"] = _ensure_match_tab(sh, GREEN_BIZ_TAB)
        _MATCH["orange_ws"] = _ensure_match_tab(sh, ORANGE_BIZ_TAB)
        for ws, key in ((_MATCH["green_ws"], "green_seen"),
                        (_MATCH["orange_ws"], "orange_seen")):
            try:
                _MATCH[key] = set(r[2].strip().upper() for r in ws.get_all_values()[1:]
                                  if len(r) > 2 and r[2].strip())
            except Exception:
                _MATCH[key] = set()
    except Exception:
        pass
    print("  COMBO MATCH ON: %d captured fiber leads loaded -> a scraped business on "
          "a green/orange dot lands in the 'Fiber Green Biz' / 'Upgrade Orange Biz' tabs."
          % len(leads))


def _match_new(new):
    """new = list of [name,address,phone,website,category]. Write any that sit on a
    captured green/orange dot to the matching tab (batched, deduped)."""
    leads = _MATCH.get("leads")
    if not leads:
        return
    g, o = [], []
    for name, addr, phone, web, cat in new:
        color = leads.get(_norm_addr(addr))
        if not color:
            continue
        au = (addr or "").strip().upper()
        row = [name, phone, addr, web, cat]
        if color == "ORANGE":
            if au in _MATCH["orange_seen"]:
                continue
            _MATCH["orange_seen"].add(au); o.append(row)
        else:
            if au in _MATCH["green_seen"]:
                continue
            _MATCH["green_seen"].add(au); g.append(row)
    try:
        if g and _MATCH.get("green_ws"):
            _MATCH["green_ws"].append_rows(g, value_input_option="RAW")
        if o and _MATCH.get("orange_ws"):
            _MATCH["orange_ws"].append_rows(o, value_input_option="RAW")
        if g or o:
            total = len(_MATCH["green_seen"]) + len(_MATCH["orange_seen"])
            print("    MATCH  +%d green (fiber lead + business), +%d orange (upgrade + business)"
                  "  [total matches: %d]" % (len(g), len(o), total))
    except Exception:
        pass


def append_sheet(ws, rows, sheet_seen):
    """Append the new (not-already-in-sheet) rows NOW. Updates sheet_seen.
    Called after each category so the sheet fills continually."""
    if ws is None or not rows:
        return 0
    new = []
    for r in rows:
        key = ((r.get("name") or "").strip().upper() + "|"
               + (r.get("address") or "").strip().upper())
        if key in sheet_seen:
            continue
        sheet_seen.add(key)
        new.append([r.get("name") or "", r.get("address") or "", r.get("phone") or "",
                    r.get("website") or "", r.get("category") or ""])
    if not new:
        return 0
    try:
        for i in range(0, len(new), 500):
            ws.append_rows(new[i:i + 500], value_input_option="RAW")
    except Exception as e:
        print("  (sheet write hiccup, will retry next batch: %s)" % str(e)[:60])
        return 0
    # cross-match these new businesses against the captured fiber dots
    try:
        _match_new(new)
    except Exception:
        pass
    return len(new)


REPO_BRANCH = "claude/optimus-map-tools-setup-6dcl6o"
SCRAPER_RAW = ("https://raw.githubusercontent.com/patricksiado-prog/"
               "Go-High-Level-MCP-2026-Complete/claude/optimus-map-tools-setup-6dcl6o/"
               "optimus/standalone/maps_scraper_standalone.py")


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
    """Always run the latest code, HOWEVER this file is launched:
      - inside the git repo  -> git fetch + hard-reset to the branch
      - standalone single file -> re-download itself from GitHub (no git needed)
    Then relaunch once with the new version. Guard: SCRAPER_NO_UPDATE=1."""
    import subprocess, sys
    if os.environ.get("SCRAPER_NO_UPDATE") == "1":
        return
    here = os.path.abspath(__file__)
    try:
        before = open(here, "rb").read()
    except Exception:
        return
    after = None
    repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    if os.path.isdir(os.path.join(repo, ".git")):
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        git = _find_git()
        try:
            subprocess.run([git, "-C", repo, "fetch", "origin", REPO_BRANCH],
                           env=env, timeout=90, capture_output=True, text=True)
            subprocess.run([git, "-C", repo, "reset", "--hard", "origin/" + REPO_BRANCH],
                           env=env, timeout=60, capture_output=True, text=True)
            after = open(here, "rb").read()
        except Exception:
            return
    else:                                   # standalone copy -> pull the file itself
        try:
            import urllib.request
            data = urllib.request.urlopen(SCRAPER_RAW, timeout=30).read()
            if b"def main" in data and data != before:    # sanity: real code, changed
                open(here, "wb").write(data)
                after = data
        except Exception:
            return
    if after is not None and after != before:
        print("Updated the scraper from GitHub -- relaunching with the new version...\n")
        try:
            r = subprocess.run([sys.executable] + sys.argv,
                               env=dict(os.environ, SCRAPER_NO_UPDATE="1"))
            sys.exit(r.returncode)
        except Exception:
            pass


def main():
    self_update()
    print("=" * 56)
    print("  GOOGLE MAPS BUSINESS SCRAPER   v%s" % VERSION)
    print("=" * 56)
    zips = input("\nEnter ZIP codes (comma-separated, e.g. 77027,77019): ").strip()
    zips = [z.strip() for z in zips.split(",") if z.strip()]
    if not zips:
        print("No ZIPs entered. Exiting.")
        return
    print("\nWhere should the results go?")
    print("  [1] CSV file  (businesses.csv)")
    print("  [2] Google Sheet  ('%s' tab)" % SHEET_TAB)
    dest = (input("Choose 1 or 2 (press Enter for 1): ").strip() or "1")
    to_sheet = dest.startswith("2")
    print("\nHow deep should it search?")
    print("  [1] Light  (~20 categories - fastest)")
    print("  [2] Heavy  (~47 categories)")
    print("  [3] Deep   (~155 categories - most thorough, slowest)")
    cats = categories_for(input("Choose 1, 2, or 3 (press Enter for 2): ").strip() or "2")
    # ZIP PLAN: the ZIPs you entered come first, then the scraper AUTO-ADVANCES
    # through nearby fiber ZIPs IN THE SAME METRO (skipping any already finished)
    # until you close the window. The metro is picked from your first ZIP, so OKC
    # stays in OKC and Houston stays in Houston -- no cross-city mixing.
    zips_done = load_zips_done()
    region, region_zips = region_for(zips[0])
    curated = [z for z in region_zips if z not in zips]
    # after the curated metro list, keep going to the NEXT LOGICAL PLACE = numeric-
    # nearby ZIPs (same/adjacent SCF), ordered outward. So it never just stops.
    near = [z for z in nearby_zips(zips + curated) if z not in zips and z not in curated]
    extra = list(dict.fromkeys(curated + near))
    zip_plan = [z for z in zips if z not in zips_done] + [z for z in extra if z not in zips_done]
    if not zip_plan:                          # everything known is covered -> start fresh
        zips_done = set(); save_zips_done(zips_done)
        zip_plan = list(dict.fromkeys(zips + extra))
    qdone = load_progress()                    # per-search resume within a ZIP
    if region:
        print("\nMetro: %s -- after your ZIP(s) it works the %s fiber ZIPs, then keeps "
              "going OUTWARD to the next nearby ZIPs (same region, never another city)."
              % (region, region))
    else:
        print("\n(ZIP not in a curated metro -- it scrapes your ZIP(s) then auto-advances "
              "to the NEAREST ZIPs numerically (same area), expanding outward.)")
    shown = ", ".join(zip_plan[:10]) + (" +%d more" % (len(zip_plan) - 10) if len(zip_plan) > 10 else "")
    print("ZIP plan (auto-advances to the next ZIP after each; close the window to stop):\n  %s\n" % shown)

    from playwright.sync_api import sync_playwright
    os.makedirs(PROFILE_DIR, exist_ok=True)
    sheet_ws, sheet_seen = (open_sheet() if to_sheet else (None, set()))
    seen, total, sheet_added, stopped = set(), 0, 0, False
    csv_mode = "a" if (os.path.exists(OUT_PATH) and (qdone or zips_done)) else "w"
    with sync_playwright() as p:
        # Run hidden (headless) by default so the browser doesn't take over the
        # screen -- it scrapes in the background and just writes to the sheet/CSV.
        # Set SCRAPER_SHOW=1 to watch the window (occasionally more block-resistant).
        show = os.environ.get("SCRAPER_SHOW", "").strip().lower() in ("1", "true", "yes", "y")
        if show:
            print("  (window VISIBLE -- SCRAPER_SHOW is set)")
        else:
            print("  Running in the background (no window). You can keep using your PC.")
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=not show, viewport={"width": 1280, "height": 900})
        # SPEED: block images / map tiles / media / fonts. We only read TEXT from the
        # DOM (name, address, phone, website), so those bytes are pure waste -- and on
        # Google Maps the map tiles (images) are the heaviest thing on every page. This
        # makes each page load (the search AND every per-place visit, the #1 time sink)
        # much faster, cuts transferred data ~90%, and LOWERS block risk (fewer
        # requests) -- unlike parallelism, which raises it. Data we read is unaffected.
        def _block_heavy(route):
            try:
                if route.request.resource_type in ("image", "media", "font"):
                    return route.abort()
            except Exception:
                pass
            try:
                return route.continue_()
            except Exception:
                pass
        try:
            ctx.route("**/*", _block_heavy)
        except Exception:
            pass
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        out_f = open(OUT_PATH, csv_mode, newline="", encoding="utf-8")
        writer = csv.DictWriter(out_f, fieldnames=FIELDS)
        if csv_mode == "w":
            writer.writeheader()
        for z in zip_plan:
            if stopped:
                break
            qs = [("%s in %s" % (c, z), c) for c in cats if ("%s in %s" % (c, z)) not in qdone]
            print("\n=== ZIP %s : %d category searches ===" % (z, len(qs)))
            for i, (q, cat) in enumerate(qs, 1):
                try:
                    rows = scrape_query(page, q, cat)
                except Exception as e:
                    print("  [%d/%d] %-30s ERROR %s" % (i, len(qs), q, str(e)[:40]))
                    continue
                if rows is None:
                    print("  Google blocked the search -- stopping. Run again to RESUME here.")
                    stopped = True
                    break
                new, q_new = 0, []
                for r in rows:
                    key = (r["name"] or "") + "|" + (r["address"] or "")
                    if key in seen:
                        continue
                    seen.add(key)
                    writer.writerow(r)
                    q_new.append(r)
                    new += 1
                out_f.flush()
                if sheet_ws is not None and q_new:      # add to the sheet as we go
                    sheet_added += append_sheet(sheet_ws, q_new, sheet_seen)
                total += new
                qdone.add(q)                             # mark this search complete
                save_progress(qdone)
                withp = sum(1 for r in rows if r.get("phone"))
                print("  [%d/%d] %-32s +%d (%d w/phone)" % (i, len(qs), q[:32], new, withp))
            if not stopped:
                zips_done.add(z)                         # whole ZIP covered
                save_zips_done(zips_done)
                print("=== ZIP %s done -> moving to the next needed ZIP ===" % z)
        out_f.close()
        ctx.close()
    print("\nDONE this session: %d businesses (CSV: %s)." % (total, OUT_PATH))
    if to_sheet:
        print("  %d added to the '%s' tab (live as it ran)." % (sheet_added, SHEET_TAB))
    if stopped:
        print("\n  Stopped early -- run again to pick up where it left off.")
    else:
        print("\n  Covered every planned ZIP. Run again anytime to refresh/extend.")
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
