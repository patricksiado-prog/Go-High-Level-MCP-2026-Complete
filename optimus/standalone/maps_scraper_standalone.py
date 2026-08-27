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

import os, io, csv, re, time, json, urllib.parse

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

# ---- GitHub write: real-time count channel (Patrick 2026-07-16 "how many leads
#      are getting pulled in real time"). Same best-effort push the scout/hunter
#      use -- pushes a tiny running-total file Claude can read instantly. No token
#      -> silently skips; never crashes the scrape. ----
GH_REPO = "patricksiado-prog/Go-High-Level-MCP-2026-Complete"
GH_BRANCH = "claude/optimus-map-tools-setup-6dcl6o"


def _gh_token():
    home = os.path.expanduser("~")
    for p in [os.path.join(home, "Downloads", "github_token.txt"),
              os.path.join(home, "Desktop", "github_token.txt"),
              os.path.join(home, "github_token.txt"),
              os.path.join(home, "optimus", "github_token.txt"),
              os.path.join(HERE, "github_token.txt"), "github_token.txt"]:
        try:
            if os.path.exists(p):
                t = open(p).read().strip()
                if t:
                    return t
        except Exception:
            pass
    return os.environ.get("GITHUB_TOKEN")


_GH_TOKEN_WARNED = []      # warn once per run, not once per push


def gh_put(path, text):
    """Best-effort: commit a small text file so Claude can read it at the raw URL."""
    import base64, urllib.request
    token = _gh_token()
    if not token:
        # Silent here means the scraper runs for hours while its live count sits
        # frozen on GitHub and nobody can tell it is still working. Say it once.
        if not _GH_TOKEN_WARNED:
            _GH_TOKEN_WARNED.append(1)
            print("  (GitHub push OFF: no github_token.txt found. Put it at "
                  "%s and the live counts start working.)"
                  % os.path.join(os.path.expanduser("~"), "github_token.txt"))
        return False
    api = "https://api.github.com/repos/%s/contents/%s" % (GH_REPO, path)
    hdr = {"Authorization": "token %s" % token, "User-Agent": "optimus-scraper",
           "Accept": "application/vnd.github+json"}
    sha = None
    try:
        req = urllib.request.Request(api + "?ref=" + GH_BRANCH, headers=hdr)
        with urllib.request.urlopen(req, timeout=20) as r:
            sha = json.load(r).get("sha")
    except Exception:
        pass
    body = {"message": "live: %s" % path, "branch": GH_BRANCH,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    if sha:
        body["sha"] = sha
    try:
        req = urllib.request.Request(api, data=json.dumps(body).encode("utf-8"),
                                     headers=hdr, method="PUT")
        with urllib.request.urlopen(req, timeout=25) as r:
            r.read()
        return True
    except Exception:
        return False


def push_live_counts_scraper(total, sheet_added, zip_now, matches=None):
    """Running total for the SCRAPER (businesses pulled), pushed to
    optimus/_live/LIVE_COUNTS_scraper.txt so Claude can read it live."""
    import socket
    txt = (
        "OPTIMUS SCRAPER -- LIVE COUNTS\n"
        "updated: %s   host: %s   ZIP now: %s\n"
        "STATUS: scraping (updates as it runs)\n"
        "----------------------------------------\n"
        "BUSINESSES pulled this run:   %d\n"
        "added to sheet (Maps Biz):    %d\n"
        % (time.strftime("%Y-%m-%d %H:%M:%S"), socket.gethostname(),
           str(zip_now), total, sheet_added))
    if matches is not None:
        txt += "COMBO matches (green+orange): %d\n" % matches
    gh_put("optimus/_live/LIVE_COUNTS_scraper.txt", txt)

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
            ws = sh.add_worksheet(title=SHEET_TAB, rows="20000", cols="7")
        # ONE read of the tab, not two. Reads have their own ~300/min quota,
        # and pulling the whole tab twice for data already in hand is how a
        # launch spends its budget before writing anything.
        try:
            vals = ws.get_all_values()
        except Exception:
            vals = []
        if not vals:
            ws.append_row(["Name", "Address", "Phone", "Website", "Category",
                           "Resi?", "Cell?"])
        seen = set()
        for r in vals[1:]:
            if len(r) >= 2:
                seen.add(r[0].strip().upper() + "|" + r[1].strip().upper())
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
BIZ_HEADER = ["Business Name", "Phone", "Address", "Website", "Category",
              "Resi?", "Cell?"]
_SUF = {"ST": "ST", "STREET": "ST", "AVE": "AVE", "AV": "AVE", "AVENUE": "AVE",
        "RD": "RD", "ROAD": "RD", "DR": "DR", "DRIVE": "DR", "LN": "LN", "LANE": "LN",
        "BLVD": "BLVD", "BOULEVARD": "BLVD", "CT": "CT", "COURT": "CT", "PL": "PL",
        "PLACE": "PL", "WAY": "WAY", "CIR": "CIR", "CIRCLE": "CIR", "TER": "TER",
        "TERRACE": "TER", "TRL": "TRL", "TRAIL": "TRL", "PKWY": "PKWY",
        "PARKWAY": "PKWY", "HWY": "HWY", "HIGHWAY": "HWY"}
_UNIT = re.compile(r"\b(APT|APARTMENT|UNIT|STE|SUITE|#|BLDG|BUILDING|FL|FLOOR|RM|"
                   r"ROOM|OFC|OFFICE|TRLR|LOT|SPC)\b.*$", re.I)
_MATCH = {"leads": None, "green_ws": None, "orange_ws": None,
          "green_seen": set(), "orange_seen": set(),
          "green_ph": set(), "orange_ph": set()}


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


# ---- RESI / CELL INDICATORS (Patrick, 2026-08-25) -------------------------
# A scraped "business" run out of a house is BOTH a business lead and a resi
# fiber lead, and the two get pitched differently. Street type carries that
# signal reliably; suite/floor markers carry the opposite one.
_RESI_ST = ("LN", "LANE", "CT", "COURT", "CIR", "CIRCLE", "PL", "PLACE",
            "DR", "DRIVE", "WAY", "TRL", "TRAIL", "CV", "COVE", "TER",
            "TERRACE", "LOOP", "BND", "BEND", "RUN", "HOLLOW", "MEADOW")
_BIZ_ST = ("HWY", "HIGHWAY", "FWY", "FREEWAY", "BLVD", "BOULEVARD", "PKWY",
           "PARKWAY", "PLZ", "PLAZA", "EXPY", "EXPRESSWAY")
_UNIT_BIZ = ("STE", "SUITE", "FL ", "FLOOR", "BLDG", "BUILDING", "RM ", "ROOM")


def resi_hint(address):
    """RESI / BIZ / "?" from the shape of the address. A hint, not a verdict --
    it is here so a rep can see at a glance which rows are houses."""
    a = " " + (address or "").upper().replace(",", " ") + " "
    if any(m in a for m in _UNIT_BIZ):
        return "BIZ"
    if " APT " in a or "#" in a:
        return "RESI"
    toks = a.split()
    for t in reversed(toks):
        t = t.strip(".")
        if t in _BIZ_ST:
            return "BIZ"
        if t in _RESI_ST:
            return "RESI"
    return "?"


_TOLL_FREE = ("800", "888", "877", "866", "855", "844", "833", "822")


def cell_hint(phone):
    """Can we TEXT this number?

    Honest by design. Toll-free is a definite no. Everything else needs a real
    carrier lookup (DealMachine) -- about 12% of these come back landline-only,
    and texting a landline is Twilio 30006 against our own sending number. So
    unknown says LOOKUP, never a guess dressed up as an answer.
    """
    d = re.sub(r"[^0-9]", "", str(phone or ""))
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if len(d) != 10:
        return ""
    if d[:3] in _TOLL_FREE:
        return "NO toll-free"
    return "LOOKUP"


def _ensure_match_tab(sh, title):
    try:
        ws = sh.worksheet(title)
    except Exception:
        ws = sh.add_worksheet(title=title, rows="200", cols="7")
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
        for ws, akey, pkey in ((_MATCH["green_ws"], "green_seen", "green_ph"),
                               (_MATCH["orange_ws"], "orange_seen", "orange_ph")):
            try:
                vals = ws.get_all_values()[1:]
                # BIZ_HEADER: [Business Name, Phone(1), Address(2), Website, Category]
                _MATCH[akey] = set(r[2].strip().upper() for r in vals
                                   if len(r) > 2 and r[2].strip())
                _MATCH[pkey] = set(r[1].strip().upper() for r in vals
                                   if len(r) > 1 and r[1].strip())
            except Exception:
                _MATCH[akey] = set(); _MATCH[pkey] = set()
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
        pu = (phone or "").strip().upper()   # dedupe by PHONE too (dialer-ready)
        row = [name, phone, addr, web, cat, resi_hint(addr), cell_hint(phone)]
        if color == "ORANGE":
            if (au and au in _MATCH["orange_seen"]) or (pu and pu in _MATCH["orange_ph"]):
                continue
            if au:
                _MATCH["orange_seen"].add(au)
            if pu:
                _MATCH["orange_ph"].add(pu)
            o.append(row)
        else:
            if (au and au in _MATCH["green_seen"]) or (pu and pu in _MATCH["green_ph"]):
                continue
            if au:
                _MATCH["green_seen"].add(au)
            if pu:
                _MATCH["green_ph"].add(pu)
            g.append(row)
    # These are the money rows -- a business sitting on a green or orange dot.
    # They used to go out as a bare append_rows wrapped in `except: pass`, so a
    # full sheet threw them away without printing anything at all. Now they go
    # through the same write path as everything else: paced, classified, and
    # parked to disk rather than dropped.
    gw, ow = 0, 0
    if g and _MATCH.get("green_ws"):
        gw = _safe_append(_MATCH["green_ws"], g, GREEN_BIZ_TAB)
    if o and _MATCH.get("orange_ws"):
        ow = _safe_append(_MATCH["orange_ws"], o, ORANGE_BIZ_TAB)
    if g or o:
        total = len(_MATCH["green_seen"]) + len(_MATCH["orange_seen"])
        held = (len(g) - gw) + (len(o) - ow)
        print("    MATCH  +%d green (fiber lead + business), +%d orange (upgrade + business)"
              "  [total matches: %d]%s"
              % (len(g), len(o), total,
                 ("  (%d held on disk until the sheet has room)" % held) if held else ""))



# ============================================================================
# PERIODIC BACKGROUND DEDUPE  (identical block in precise_fiber_hunter.py AND
# maps_scraper_standalone.py, so BOTH programs keep the tabs clean while they run)
#
# WHAT it cleans, per pass:
#   Precise Fiber ...... exact-duplicate ADDRESS rows (same address captured twice)
#   Maps Businesses .... same PHONE (else same NAME|ADDRESS) written twice
#   Fiber Green Biz .... same PHONE (else NAME|ADDRESS) -- collapses the ~8x
#   Upgrade Orange Biz . inflation where one business matched many unit/spelling
#                        address variants. Keeps the row that has a call
#                        disposition, else the first one. NO unique phone is ever
#                        dropped (verified: 21,662 -> 4,105 rows, phones lost = 0).
#
# SAFETY:
#   * Deletes only SPECIFIC duplicate row numbers, computed from a snapshot, and
#     applies them BOTTOM-UP -- rows appended live at the bottom are never in the
#     list, so a running hunt/scrape can keep writing during a pass with no loss.
#   * Writes a local CSV backup of a tab BEFORE it removes anything from it.
#   * A cross-machine advisory LOCK (a "_Dedupe Lock" cell) means the hunter and
#     the scraper never dedupe the same sheet at the same time (which could delete
#     shifted rows). If the lock can't be taken, the pass simply skips -- it never
#     risks a double-delete.
#   * Per-pass delete cap so the first big cleanup spreads over a few passes
#     instead of hammering the API; Precise Fiber (huge) is cleaned less often.
# ============================================================================
_DEDUPE_EVERY   = 1800     # seconds between passes (30 min)
_DEDUPE_WARMUP  = 120      # let the run get going before the first pass
_DEDUPE_STALE   = 900      # a lock older than this (sec) is treated as abandoned
_DEDUPE_MAXDEL  = 6000     # max rows removed from one tab per pass (converges)
_DEDUPE_LOCK_TAB = "_Dedupe Lock"
_DD_PASS = [0]             # pass counter (Precise Fiber only every 6th pass)


def _dd_phone(s):
    import re as _re
    d = _re.sub(r"\D", "", s or "")
    return d[-10:] if len(d) >= 10 else ""


def _dd_backup_csv(tabname, values):
    """One rolling local CSV backup per tab, written just before we delete."""
    import csv as _csv, os as _os, re as _re
    try:
        here = _os.path.dirname(_os.path.abspath(__file__))
        p = _os.path.join(here, "dedupe_backup_%s.csv"
                          % _re.sub(r"\W+", "_", tabname).strip("_"))
        with open(p, "w", newline="", encoding="utf-8") as f:
            _csv.writer(f).writerows(values)
    except Exception:
        pass


def _dd_delete_rows(ws, row_numbers):
    """Delete 1-based sheet row numbers, batched into contiguous ranges and
    applied BOTTOM-UP in a single batch_update so earlier deletes don't shift
    later ones. Returns how many rows were removed."""
    if not row_numbers:
        return 0
    idx = sorted(set(row_numbers), reverse=True)
    ranges, start, prev = [], idx[0], idx[0]
    for r in idx[1:]:
        if r == prev - 1:
            prev = r
        else:
            ranges.append((prev, start)); start = prev = r
    ranges.append((prev, start))          # (lo, hi) inclusive, already top-to-bottom
    sid = ws.id
    reqs = [{"deleteDimension": {"range": {"sheetId": sid, "dimension": "ROWS",
             "startIndex": lo - 1, "endIndex": hi}}} for (lo, hi) in ranges]
    removed = sum(hi - lo + 1 for lo, hi in ranges)
    for i in range(0, len(reqs), 200):    # chunk the payload; order preserved
        ws.spreadsheet.batch_update({"requests": reqs[i:i + 200]})
    return removed


def _dd_dedupe_tab(sh, tab, key_fn, score_fn=None):
    """Keep one row per key (highest score, else earliest); remove the rest by
    OVERWRITING the kept rows at the top, then trimming the old trailing rows in
    ONE contiguous delete. Reliable at ANY scale (2 API calls, not thousands of
    scattered deletes -- the old way choked on a 17k-dupe tab). Append-safe: a
    live append lands at row >= N+2, BELOW the trimmed range [K+2 .. N+1], so it
    survives and just shifts up. Returns rows removed."""
    try:
        ws = sh.worksheet(tab)
    except Exception:
        return 0
    vals = ws.get_all_values()
    if len(vals) < 3:
        return 0
    hdr, rows = vals[0], vals[1:]
    N = len(rows)
    best, keyless = {}, []                 # key -> (score, index); keyless kept as-is
    for i, r in enumerate(rows):
        k = key_fn(r)
        if not k:
            keyless.append(i)
            continue
        s = score_fn(r) if score_fn else 0
        if k not in best or s > best[k][0]:
            best[k] = (s, i)
    keep_idx = sorted(set(v[1] for v in best.values()) | set(keyless))
    removed = N - len(keep_idx)
    if removed <= 0:
        return 0
    _dd_backup_csv(tab, vals)              # local CSV backup BEFORE any change
    width = max(len(hdr), max((len(rows[i]) for i in keep_idx), default=len(hdr)))
    body = [(list(rows[i]) + [""] * width)[:width] for i in keep_idx]
    K = len(body)
    # 1) overwrite kept rows starting at row 2 (header stays row 1)
    ws.batch_update([{"range": "A2", "values": body}], value_input_option="RAW")
    # 2) trim the OLD trailing rows [K+2 .. N+1]; live appends land at >= N+2, safe
    lo, hi = K + 2, N + 1
    if hi >= lo:
        ws.spreadsheet.batch_update({"requests": [{"deleteDimension": {"range": {
            "sheetId": ws.id, "dimension": "ROWS",
            "startIndex": lo - 1, "endIndex": hi}}}]})
    return removed


def _dd_acquire_lock(sh):
    """Advisory cross-machine lock so hunter+scraper never dedupe at once."""
    import time as _t, socket as _s
    try:
        try:
            lk = sh.worksheet(_DEDUPE_LOCK_TAB)
        except Exception:
            lk = sh.add_worksheet(title=_DEDUPE_LOCK_TAB, rows="2", cols="2")
        host = _s.gethostname()
        now = _t.time()
        cur = lk.acell("A1").value or ""
        if cur:
            try:
                ts = float(cur.split("|", 1)[0])
            except Exception:
                ts = 0.0
            if (now - ts) < _DEDUPE_STALE and not cur.endswith("|" + host):
                return None                # someone else holds a fresh lock
        lk.update_acell("A1", "%f|%s" % (now, host))
        return lk
    except Exception:
        return None


def _dd_keys():
    def biz_key(r):
        r = (list(r) + [""] * 3)
        ph = _dd_phone(r[1])
        if ph:
            return ph
        nm, ad = r[0].strip().upper(), r[2].strip().upper()
        return ("N:" + nm + "|" + ad) if (nm or ad) else ""

    def biz_score(r):                      # keep the row that has a disposition
        return 1 if (len(r) > 5 and str(r[5]).strip()) else 0

    def pf_key(r):
        return r[0].strip().upper() if (r and r[0].strip()) else ""

    def maps_key(r):
        r = (list(r) + [""] * 3)
        ph = _dd_phone(r[2])
        if ph:
            return ph
        nm, ad = r[0].strip().upper(), r[1].strip().upper()
        return ("N:" + nm + "|" + ad) if (nm or ad) else ""
    return biz_key, biz_score, pf_key, maps_key


def dedupe_all_tabs(sh):
    if sh is None:
        return 0
    lk = _dd_acquire_lock(sh)
    if lk is None:
        return 0                            # another machine is deduping now
    biz_key, biz_score, pf_key, maps_key = _dd_keys()
    _DD_PASS[0] += 1
    jobs = [("Maps Businesses", maps_key, None),
            ("Fiber Green Biz", biz_key, biz_score),
            ("Upgrade Orange Biz", biz_key, biz_score)]
    if _DD_PASS[0] == 1 or _DD_PASS[0] % 6 == 0:   # huge tab: clean less often
        jobs.insert(0, ("Precise Fiber", pf_key, None))
    total = 0
    for tab, kf, sf in jobs:
        try:
            n = _dd_dedupe_tab(sh, tab, kf, sf)
            if n:
                total += n
                print("  [dedupe] %s: removed %d duplicate rows" % (tab, n))
        except Exception as e:
            print("  [dedupe] %s skipped: %s" % (tab, str(e)[:60]))
    if total:
        print("  [dedupe] cleaned %d duplicate rows this pass" % total)
    return total


def _dd_count_col(sh, tab, col=1):
    try:
        return max(0, len(sh.worksheet(tab).col_values(col)) - 1)
    except Exception:
        return 0


def _dd_unique_phones(sh, tab):
    try:
        vals = sh.worksheet(tab).col_values(2)[1:]   # the Phone column
    except Exception:
        return 0
    u = set()
    for v in vals:
        p = _dd_phone(v)
        if p:
            u.add(p)
    return len(u)


def startup_clean_and_counts(sh):
    """Run at program START: delete the exact/phone duplicates NOW (looping until
    it converges), then print the real total of every tab so you see the numbers
    up front -- e.g. fiber addresses / scraped businesses / callable matches."""
    if sh is None:
        return
    print("\n  Cleaning duplicates on startup (one time, then it stays clean)...")
    _DD_PASS[0] = 0
    for _ in range(8):                       # converge, but bounded
        try:
            if dedupe_all_tabs(sh) == 0:
                break
        except Exception as e:
            print("  (startup dedupe stopped: %s)" % str(e)[:60])
            break
    pf  = _dd_count_col(sh, "Precise Fiber")
    mb  = _dd_count_col(sh, "Maps Businesses")
    fg  = _dd_count_col(sh, "Fiber Green Biz")
    fgp = _dd_unique_phones(sh, "Fiber Green Biz")
    og  = _dd_count_col(sh, "Upgrade Orange Biz")
    print("\n  ================= TOTALS (deduped) =================")
    print("   Fiber green addresses (Precise Fiber) : {:>9,}".format(pf))
    print("   Scraped businesses (Maps Businesses)  : {:>9,}".format(mb))
    print("   MATCHES - callable (unique phone)     : {:>9,}".format(fgp))
    print("   MATCHES - Fiber Green Biz rows        : {:>9,}".format(fg))
    if og:
        print("   Upgrade Orange Biz matches            : {:>9,}".format(og))
    print("  ===================================================\n")


def start_periodic_dedupe(sh, every=_DEDUPE_EVERY):
    """Daemon thread: dedupe the tabs every `every` seconds, in the background,
    without ever blocking or crashing the main hunt/scrape."""
    import threading, time as _t
    if sh is None:
        return
    def _loop():
        _t.sleep(_DEDUPE_WARMUP)
        while True:
            try:
                dedupe_all_tabs(sh)
            except Exception:
                pass
            _t.sleep(every)
    threading.Thread(target=_loop, daemon=True).start()
    print("  periodic background dedupe ON (every %d min, all tabs, phone-keyed)"
          % (every // 60))


# ---------------------------------------------------------------------------
# SHEET WRITES -- quota, permanent errors, and never losing a row.
#
# All three of these were real failures on 2026-08-27, all in one loop:
#   1. The 400 "would increase the number of cells above the limit" error was
#      retried batch after batch. It can NEVER succeed -- the workbook is out
#      of cells. Retrying it just fills the screen and burns quota.
#   2. `sheet_seen.add(key)` ran BEFORE the write, so a failed batch marked its
#      rows as already-in-the-sheet. "will retry next batch" was never true:
#      those rows were gone for good, even after space was freed.
#   3. Nothing paced the writes against Google's ~60-per-minute ceiling.
# ---------------------------------------------------------------------------

# How many PCs are scraping into this sheet right now. Google counts its write
# quota PER SERVICE ACCOUNT, not per machine, and every PC runs the same
# google_creds.json -- so two laptops each pacing at 50/min send 100 against a
# ~60/min ceiling and BOTH crawl. Set OPTIMUS_MACHINES=2 before launching.
_MACHINES = [1]
try:
    _MACHINES[0] = max(1, int(os.environ.get("OPTIMUS_MACHINES", "1")))
except Exception:
    pass

_SHEET_FULL = {"hit": False, "said": False}
_WRITE_STAMPS = []
_PARK_SEQ = [0]
_RUN_STAMP = time.strftime("%Y%m%d-%H%M%S")


_AUTOSHRINK = {"tried": False}


def _auto_free_space(ws):
    """The cell-limit 400 means the WORKBOOK is out of cells -- but a tab is
    billed for its whole GRID, not its rows, so a 5000x26 tab holding ten rows
    bills 130,000 cells. When FULL hits, shrink every over-allocated grid to
    its used size automatically. Deletes nothing, asks nobody: Patrick's
    standing rule (2026-08-27) is no separate programs anyone has to run.

    Rows never go below used + slack; columns never below the tab's own header
    width, and never below 13 (the hunter's OUT_HEADER is 13 wide).
    Runs at most ONCE per process, through the write throttle."""
    if _AUTOSHRINK["tried"] or ws is None:
        return 0
    _AUTOSHRINK["tried"] = True
    try:
        tabs = ws.spreadsheet.worksheets()
    except Exception as e:
        print("  (auto free-space could not list tabs: %s)" % str(e)[:50])
        return 0
    print("  sheet FULL -- shrinking over-allocated grids (deletes nothing)...")
    freed = 0
    for t in tabs:
        try:
            gr, gc = t.row_count, t.col_count
            if gr * gc < 50000:
                continue                      # not worth a read+write
            used_r = len(t.col_values(1))
            head_c = len(t.row_values(1))
            want_r = min(gr, max(used_r + 2000, 100))
            want_c = min(gc, max(head_c, 13))
            if want_r * want_c >= gr * gc:
                continue
            _sheet_throttle()
            t.resize(rows=want_r, cols=want_c)
            freed += gr * gc - want_r * want_c
            print("  shrunk %-28s %dx%d -> %dx%d"
                  % (t.title[:28], gr, gc, want_r, want_c))
        except Exception:
            continue
    if freed:
        print("  freed {:,} cells -- writes can resume.".format(freed))
    else:
        print("  nothing left to shrink -- the workbook truly needs archiving.")
    return freed


def _err_kind(e):
    """QUOTA = wait and retry. FULL = the workbook is out of cells, never
    retry. OTHER = transient, worth a couple of goes."""
    t = str(e)
    if ("above the limit of" in t or "increase the number of cells" in t
            or "exceeds the maximum" in t):
        return "FULL"
    if ("[429]" in t or "Quota exceeded" in t or "RATE_LIMIT" in t
            or "rateLimitExceeded" in t or "userRateLimit" in t):
        return "QUOTA"
    return "OTHER"


def _sheet_throttle(max_per_min=50):
    """Stay under the write quota instead of discovering it with a 429.
    Google's window is rolling and per minute, so hold the next write until the
    oldest ages out. The budget is divided by the number of PCs sharing the
    sheet -- the quota belongs to the service account, and every PC uses the
    same google_creds.json."""
    max_per_min = max(6, int(max_per_min / max(1, _MACHINES[0])))
    now = time.time()
    _WRITE_STAMPS[:] = [t for t in _WRITE_STAMPS if now - t < 60]
    if len(_WRITE_STAMPS) >= max_per_min:
        wait = max(1, int(60 - (now - _WRITE_STAMPS[0]) + 1))
        print("   (write quota reached -- holding %ds so nothing is lost)" % wait)
        time.sleep(wait)
        now = time.time()
        _WRITE_STAMPS[:] = [t for t in _WRITE_STAMPS if now - t < 60]
    _WRITE_STAMPS.append(time.time())


def _pending_dir():
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_pending_maps")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _park_rows(rows, tab=None):
    """Save rows Google would not take, so a later run can write them.

    The file records WHICH TAB the rows belong to -- business rows and matched
    fiber-lead rows go to different tabs, and a replay that put them all in one
    place would be worse than losing them.

    Named by run + sequence, never by row COUNT alone: two failed batches of
    the same size in one run would overwrite each other, and the one function
    whose whole job is 'do not lose rows' would be losing them."""
    if not rows:
        return True
    tab = tab or SHEET_TAB
    _PARK_SEQ[0] += 1
    path = os.path.join(_pending_dir(), "maps__%s__%s__%04d__%d.json"
                        % (re.sub(r"[^A-Za-z0-9]+", "_", tab),
                           _RUN_STAMP, _PARK_SEQ[0], len(rows)))
    try:
        with io.open(path, "w", encoding="utf-8") as f:
            json.dump({"tab": tab, "rows": rows}, f)
        return True
    except Exception as e:
        print("  (could not park %d rows: %s)" % (len(rows), str(e)[:50]))
        return False


def _read_park(path):
    """Load a park file. Tolerates the old bare-list format."""
    with io.open(path, encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, list):
        return SHEET_TAB, d
    return d.get("tab") or SHEET_TAB, d.get("rows") or []


def _safe_append(ws, rows, tab):
    """Write rows to `ws` in 500-row chunks, parking anything Google refuses.
    Returns how many rows Google actually acknowledged."""
    if ws is None or not rows:
        return 0
    if _SHEET_FULL["hit"]:
        _park_rows(rows, tab)
        return 0
    written = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        if _write_chunk(ws, chunk):
            written += len(chunk)
        else:
            _park_rows(chunk, tab)
    return written


def _say_full():
    """Say the sheet is full ONCE, with the fix, instead of once per batch."""
    if _SHEET_FULL["said"]:
        return
    _SHEET_FULL["said"] = True
    print("")
    print("  " + "=" * 66)
    print("  THE SHEET IS FULL. Google will not accept another row.")
    print("  (10,000,000-cell limit on the workbook -- not a network problem,")
    print("   and no number of retries can ever succeed.)")
    print("")
    print("  NOTHING IS LOST. Every business is still going into the CSV, and")
    print("  the sheet rows are being saved on this PC -- they write themselves")
    print("  into the sheet automatically the next time there is room.")
    print("")
    print("  Grids were already auto-shrunk. The workbook now genuinely needs")
    print("  archiving (the plan is parked in the brain, BRAIN.md 22.35).")
    print("  " + "=" * 66)
    print("")


def _write_chunk(ws, chunk):
    """Write one chunk. Returns True if Google acknowledged it.
    Raises nothing: classifies the failure and parks on anything permanent."""
    waits = [15, 35, 65, 65]
    for attempt in range(len(waits) + 1):
        if _SHEET_FULL["hit"]:
            return False
        try:
            _sheet_throttle()
            ws.append_rows(chunk, value_input_option="RAW")
            return True
        except Exception as e:
            kind = _err_kind(e)
            if kind == "FULL":
                # Make room automatically, then retry this same chunk once.
                if not _AUTOSHRINK["tried"] and _auto_free_space(ws) > 0:
                    continue
                _SHEET_FULL["hit"] = True
                _say_full()
                return False
            if attempt >= len(waits):
                print("  (sheet write failed after %d tries, parking %d rows: %s)"
                      % (attempt + 1, len(chunk), str(e)[:50]))
                return False
            if kind == "QUOTA":
                # Google's window is per MINUTE. A 1s or 2s backoff cannot
                # outlive it, so short waits just collect more 429s.
                print("   (rate limited -- waiting %ds)" % waits[attempt])
                time.sleep(waits[attempt])
            else:
                time.sleep(min(5, waits[attempt]))
    return False


def append_sheet(ws, rows, sheet_seen):
    """Append the new (not-already-in-sheet) rows NOW.

    A key enters `sheet_seen` only once the row is safely accounted for --
    written to the sheet, or parked to disk for a later run. A row that is
    neither is left unseen so the next pass picks it up again.
    """
    if ws is None or not rows:
        return 0
    new, keys = [], []
    for r in rows:
        key = ((r.get("name") or "").strip().upper() + "|"
               + (r.get("address") or "").strip().upper())
        if key in sheet_seen or key in keys:
            continue
        _a, _p = r.get("address") or "", r.get("phone") or ""
        new.append([r.get("name") or "", _a, _p,
                    r.get("website") or "", r.get("category") or "",
                    resi_hint(_a), cell_hint(_p)])
        keys.append(key)
    if not new:
        return 0

    written = 0
    # Already known to be full: park straight away, don't ask Google again.
    if _SHEET_FULL["hit"]:
        if _park_rows(new, SHEET_TAB):
            sheet_seen.update(keys)
    else:
        for i in range(0, len(new), 500):
            chunk, ckeys = new[i:i + 500], keys[i:i + 500]
            if _write_chunk(ws, chunk):
                sheet_seen.update(ckeys)
                written += len(chunk)
            elif _park_rows(chunk, SHEET_TAB):
                sheet_seen.update(ckeys)      # parked = safe, will be replayed

    # Cross-match EVERY new business against the captured dots, not just the
    # ones this tab accepted. The matches go to different tabs and park
    # themselves; gating them on this write would lose leads for no reason.
    try:
        _match_new(new)
    except Exception as e:
        print("  (cross-match skipped: %s)" % str(e)[:50])
    return written


def replay_parked(ws, sheet_seen, max_files=60, max_rows=15000):
    """Write rows parked by earlier runs, back into the tab each one came from.

    Bounded per launch. An unbounded replay is how the hunter's backlog turned
    into a doom loop: one worksheet lookup and one append per parked FILE blew
    the read quota before a single row was written, and left more parked than
    it found. So: at most `max_files` files and `max_rows` rows, grouped by tab
    so each tab is resolved ONCE, and merged into 500-row writes.
    """
    if ws is None:
        return 0
    d = _pending_dir()
    try:
        files = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    except Exception:
        return 0
    if not files:
        return 0
    print("  %d parked batch(es) from earlier runs -- replaying up to %d."
          % (len(files), min(len(files), max_files)))

    # group first: rows for the same tab are written together, not file by file
    by_tab, rows_read = {}, 0
    for name in files[:max_files]:
        if rows_read >= max_rows:
            break
        path = os.path.join(d, name)
        try:
            tab, rows = _read_park(path)
        except Exception:
            continue
        if not rows:
            try:
                os.remove(path)
            except Exception:
                pass
            continue
        slot = by_tab.setdefault(tab, {"rows": [], "files": []})
        slot["rows"].extend(rows)
        slot["files"].append(path)
        rows_read += len(rows)

    done, wrote = 0, 0
    for tab, slot in by_tab.items():
        if _SHEET_FULL["hit"]:
            break
        target = _resolve_tab(ws, tab)
        if target is None:
            continue                       # tab not open this run: leave parked
        ok = True
        rows = slot["rows"]
        for i in range(0, len(rows), 500):
            if not _write_chunk(target, rows[i:i + 500]):
                ok = False
                break
            wrote += len(rows[i:i + 500])
        if ok:                             # delete ONLY what Google acknowledged
            for path in slot["files"]:
                try:
                    os.remove(path)
                    done += 1
                except Exception:
                    pass

    if done:
        print("  replayed %d parked batch(es) (%d rows) into the sheet." % (done, wrote))
        try:
            for r in ws.get_all_values()[1:]:
                if len(r) >= 2:
                    sheet_seen.add(r[0].strip().upper() + "|" + r[1].strip().upper())
        except Exception:
            pass
    elif _SHEET_FULL["hit"]:
        print("  (still full -- parked rows kept on disk, nothing deleted.)")
    left = len(files) - done
    if left > 0:
        print("  %d batch(es) still parked -- they go in on a later run." % left)
    return done


def _resolve_tab(ws, tab):
    """The worksheet for a parked tab name. Resolved from what is already open,
    so a replay costs no extra reads."""
    if tab == SHEET_TAB:
        return ws
    if tab == GREEN_BIZ_TAB:
        return _MATCH.get("green_ws")
    if tab == ORANGE_BIZ_TAB:
        return _MATCH.get("orange_ws")
    return None


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


def _start_summary():
    """Refresh the 'OPTIMUS DATA SUMMARY' sheet Claude reads (best-effort, one-shot,
    detached). Uses the hunter's optimus_summary.py if the hunter is installed on
    this PC (usual case -- the installer sets up both). Silent if not found."""
    try:
        import subprocess as _sp, sys
        cands = [os.path.join(os.path.expanduser("~"), "optimus_hunter"),
                 os.path.join(os.path.expanduser("~"), "optimus", "repo", "optimus")]
        for d in cands:
            summ = os.path.join(d, "optimus_summary.py")
            if os.path.exists(summ):
                _env = dict(os.environ, OPTIMUS_NO_UPDATE="1", SCRAPER_NO_UPDATE="1")
                _kw = {"cwd": d, "env": _env, "stdin": _sp.DEVNULL,
                       "stdout": _sp.DEVNULL, "stderr": _sp.DEVNULL}
                if os.name == "nt":
                    _kw["creationflags"] = 0x00000008 | 0x08000000
                else:
                    _kw["start_new_session"] = True
                _sp.Popen([sys.executable, summ], **_kw)
                print("  (refreshing the OPTIMUS DATA SUMMARY sheet for Claude...)")
                return
    except Exception:
        pass


def main():
    self_update()
    _start_summary()
    print("=" * 56)
    print("  GOOGLE MAPS BUSINESS SCRAPER   v%s" % VERSION)
    print("=" * 56)
    zips = input("\nEnter ZIP codes (comma-separated, e.g. 77027,77019): ").strip()
    zips = [z.strip() for z in zips.split(",") if z.strip()]
    if not zips:
        print("No ZIPs entered. Exiting.")
        return
    # Results ALWAYS go to the Google Sheet. The old prompt offered a CSV and
    # defaulted to it, so anyone who just pressed Enter scraped into a local
    # file on their own PC and nothing ever reached the sheet. businesses.csv
    # is still written quietly as a local backup, so a run is never lost if the
    # sheet is unreachable -- but it is no longer something you can pick.
    to_sheet = True
    print("\nResults go to the Google Sheet: '%s' tab." % SHEET_TAB)
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
    # Rows an earlier run could not write (sheet full, quota) go in first, so a
    # backlog drains instead of growing. Bounded per launch -- see replay_parked.
    try:
        replay_parked(sheet_ws, sheet_seen)
    except Exception as e:
        print("  (replay skipped: %s)" % str(e)[:60])
    # Keep the tabs deduped in the background while the scraper runs (phone-keyed
    # on the biz tabs). Cross-machine locked so it never collides with the hunter.
    if sheet_ws is not None and os.environ.get("SCRAPER_NO_DEDUPE", "").strip() not in ("1", "true", "yes"):
        try:
            startup_clean_and_counts(sheet_ws.spreadsheet)   # clean + show totals NOW
            start_periodic_dedupe(sheet_ws.spreadsheet)      # keep it clean while running
        except Exception as e:
            print("  (dedupe off: %s)" % str(e)[:60])
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
                # REAL-TIME COUNT: push the running tally every 5 searches so
                # Claude can read "how many pulled so far" at any moment.
                if i % 5 == 0:
                    push_live_counts_scraper(total, sheet_added, z)
            if not stopped:
                zips_done.add(z)                         # whole ZIP covered
                save_zips_done(zips_done)
                push_live_counts_scraper(total, sheet_added, z)   # ZIP-complete snapshot
                print("=== ZIP %s done -> moving to the next needed ZIP ===" % z)
        out_f.close()
        ctx.close()
    push_live_counts_scraper(total, sheet_added, "DONE (final count)")
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
