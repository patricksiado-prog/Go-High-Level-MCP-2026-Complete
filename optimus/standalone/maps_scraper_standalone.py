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
    if _SHEET_FULL["hit"]:
        status = ("STATUS: *** SHEET FULL -- NOTHING IS REACHING THE SHEET ***\n"
                  "        %d row(s) parked on this PC; they go in when there is room"
                  % _PARKED_ROWS[0])
    else:
        status = "STATUS: scraping (updates as it runs)"
    txt = (
        "OPTIMUS SCRAPER -- LIVE COUNTS\n"
        "updated: %s   host: %s   ZIP now: %s\n"
        "%s\n"
        "----------------------------------------\n"
        "BUSINESSES pulled this run:   %d\n"
        "added to sheet (Maps Biz):    %d\n"
        % (time.strftime("%Y-%m-%d %H:%M:%S"), socket.gethostname(),
           str(zip_now), status, total, sheet_added))
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


PF_REDIRECT_FILE = os.path.join(os.path.expanduser("~"), "optimus",
                                "optimus_sheet_id.txt")
# MUST equal PF_SPLIT_SHEET_ID in precise_fiber_hunter.py. The hunter writes
# green dots there; this program cross-matches against it. Different values =
# the match silently finds nothing. Empty string = no split.
PF_SPLIT_SHEET_ID = "1DXu-nuQvVKrqQVk8LDNwLztG31ddi6sAyo8vXDFKcmQ"


def _pf_spreadsheet(sh):
    """The workbook that holds 'Precise Fiber'.

    Reads the SAME redirect file the hunter reads, so when green dots are split
    into their own spreadsheet both programs follow. Without that, the hunter
    would write dots to the new file while the scraper kept cross-matching
    against the old one and quietly found nothing.

    No redirect file -> returns `sh` unchanged, so behaviour is identical to
    before until somebody deliberately splits.
    """
    # Same default the hunter carries (PF_SPLIT_SHEET_ID there). If the two
    # ever differ, the hunter writes green dots to one workbook and this match
    # reads another -- and finds nothing, silently. Keep them identical.
    raw = ""
    try:
        if os.path.exists(PF_REDIRECT_FILE):
            raw = open(PF_REDIRECT_FILE, encoding="utf-8").read().strip()
    except Exception:
        raw = ""
    if not raw:
        raw = PF_SPLIT_SHEET_ID
    if not raw:
        return sh
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})", raw)
    sid = m.group(1) if m else raw.split()[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,}", sid or ""):
        return sh
    try:
        return sh.client.open_by_key(sid)
    except Exception as e:
        print("  (Precise Fiber redirect %s would not open: %s -- falling back to "
              "the main workbook. Check it is shared with the service account.)"
              % (sid, str(e)[:50]))
        return sh


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
        pf = _pf_spreadsheet(sh).worksheet("Precise Fiber").get_all_values()
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
    # 'Precise Fiber' has been GREEN ONLY since 2026-08-26 -- every gold dot goes
    # to 'Gold Confirmed' now, and this function never read that tab. So the
    # ORANGE side of the match was scanning a tab with zero orange rows, and
    # 'Upgrade Orange Biz' froze at 62 rows (measured 2026-09-03) while 38,481
    # scraped businesses sat unmatched. Gold is loaded from its own tab and
    # OVERRIDES green: a business on a gold dot is an upgrade sale, not a
    # switch pitch, and it is the highest-value row this program can write.
    n_gold = 0
    try:
        for r in sh.worksheet(GOLD_TAB).get_all_values()[1:]:
            k = _norm_addr(r[0] if r else "")
            if k:
                if leads.get(k) != "ORANGE":
                    n_gold += 1
                leads[k] = "ORANGE"
    except Exception as e:
        print("  (gold dots NOT loaded for the match -- 'Upgrade Orange Biz' will not"
              " grow this run: %s)" % str(e)[:50])
    _MATCH["leads"] = leads
    _MATCH["n_gold"] = n_gold
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
    print("  COMBO MATCH ON: %d captured fiber leads loaded (%d gold from '%s') -> a "
          "scraped business on a green/orange dot lands in the 'Fiber Green Biz' / "
          "'Upgrade Orange Biz' tabs."
          % (len(leads), n_gold, GOLD_TAB))


def _match_new(new):
    """new = list of [name,address,phone,website,category]. Write any that sit on a
    captured green/orange dot to the matching tab (batched, deduped)."""
    leads = _MATCH.get("leads")
    if not leads:
        return
    g, o = [], []
    for _row in new:
        # _safe_append builds 7-wide rows (…, resi_hint, cell_hint). Unpacking a
        # fixed 5 raised ValueError on the FIRST row, so every cross-match batch
        # aborted and the business-to-dot match never wrote anything. Slice, so
        # adding a column can never silently kill the match again.
        name, addr, phone, web, cat = _row[:5]
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

    def pf_score(r):
        # Keep the FULLEST copy of an address, not the earliest. Keeping the
        # earliest meant a skinny 3-column row from June beat its own fresh
        # 13-column re-capture -- the full address was deleted and the
        # incomplete one won forever (found 2026-08-27 while building "full
        # address everywhere").
        return sum(1 for c in r if str(c).strip())

    def maps_key(r):
        r = (list(r) + [""] * 3)
        ph = _dd_phone(r[2])
        if ph:
            return ph
        nm, ad = r[0].strip().upper(), r[1].strip().upper()
        return ("N:" + nm + "|" + ad) if (nm or ad) else ""
    return biz_key, biz_score, pf_key, pf_score, maps_key


def dedupe_all_tabs(sh):
    if sh is None:
        return 0
    lk = _dd_acquire_lock(sh)
    if lk is None:
        return 0                            # another machine is deduping now
    biz_key, biz_score, pf_key, pf_score, maps_key = _dd_keys()
    _DD_PASS[0] += 1
    jobs = [("Maps Businesses", maps_key, None),
            ("Fiber Green Biz", biz_key, biz_score),
            ("Upgrade Orange Biz", biz_key, biz_score)]
    if _DD_PASS[0] == 1 or _DD_PASS[0] % 6 == 0:   # huge tab: clean less often
        jobs.insert(0, ("Precise Fiber", pf_key, pf_score))
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


# ---------------------------------------------------------------------------
# ADDRESS BACKFILL (Patrick, 2026-08-27: "full address everywhere w time
# stamp"). Rows captured before the 13-column format hold a street line and
# nothing else -- no city, state or ZIP -- so an exported row cannot be mailed,
# skip-traced, or handed to a rep as-is. Any such row that still carries
# coordinates can be repaired for free: the US Census Bureau's public geocoder
# reverse-resolves lat/lng to city + state + ZIP with no key and no cost. A
# bounded batch runs each launch inside the scraper, so the tab heals itself
# over a few days with nobody running anything.
#
# HONESTY RULES:
#   * A row with no coordinates CANNOT be filled and is left exactly as it is.
#     Never invent a city from a street name.
#   * A failed or slow lookup leaves that row untouched, to retry next launch.
#   * "Backfilled At" is stamped in its own column, so a repaired row says when
#     it was completed. The capture timestamp in "Captured At" is NEVER
#     overwritten -- that is when the DOT was seen, and it stays true.
# ---------------------------------------------------------------------------
PF_TAB = "Precise Fiber"
BACKFILL_PER_LAUNCH = 400        # rows repaired per launch; bounded on purpose
NO_MATCH = "NO MATCH"            # stamp for coordinates that resolve to nothing
_CENSUS_URL = ("https://geocoding.geo.census.gov/geocoder/geographies/"
               "coordinates?x=%s&y=%s&benchmark=Public_AR_Current"
               "&vintage=Current_Current&format=json")


def _a1(idx):
    """0-based column index -> A1 letters (27 -> AB)."""
    out, i = "", idx + 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def _census_place(lat, lng):
    """(city, state, zip) for a coordinate, or None. Free, keyless, and it
    fails quietly -- a repair that cannot be verified is not made."""
    import urllib.request
    try:
        url = _CENSUS_URL % (str(lng).strip(), str(lat).strip())
        with urllib.request.urlopen(url, timeout=12) as r:
            geo = (json.load(r).get("result") or {}).get("geographies") or {}
    except Exception:
        return None
    blocks = geo.get("2020 Census Blocks") or geo.get("Census Blocks") or []
    places = (geo.get("Incorporated Places") or geo.get("Census Designated Places")
              or geo.get("County Subdivisions") or [])
    zips = (geo.get("2010 Census ZIP Code Tabulation Areas")
            or geo.get("Zip Code Tabulation Areas") or [])
    city = (places[0].get("NAME") or "").strip() if places else ""
    state = (blocks[0].get("STUSAB") or "").strip() if blocks else ""
    zc = ""
    for z in zips:
        zc = (z.get("ZCTA5") or z.get("GEOID") or "").strip()
        if zc:
            break
    if not (city or state or zc):
        return None
    return city, state, zc


# The canonical Precise Fiber layout. MUST stay identical to OUT_HEADER in
# precise_fiber_hunter.py -- the hunter appends rows in exactly this order, so
# these labels describe columns that already hold data.
PF_HEADER = ["Address", "Dot Color", "Captured At", "Business", "Phone",
             "Run ID", "Operator", "Lat", "Lng", "City", "State", "ZIP",
             "Status"]


def _repair_pf_header(ws, first):
    """Put the missing labels back on row 1 of Precise Fiber.

    Row 1 lost everything past 'Captured At' at some point. backfill_addresses
    finds Lat/Lng/City/State/ZIP BY NAME, so it bailed on every single launch
    and the address repair has never run once -- which is why captured rows
    still have no city, state or ZIP and cannot be mailed or skip-traced. The
    columns were never junk; only their labels were gone.

    Timid on purpose, same contract as the hunter's _ensure_header:
      * fills ONLY row-1 cells that are blank
      * never overwrites a label already there (someone may have renamed one)
      * never touches row 2 or below, so no data can move
    Returns the repaired header list, or None if it could not help.
    """
    cur = list(first) + [""] * max(0, len(PF_HEADER) - len(first))
    fixed, added = list(cur), []
    for i, want in enumerate(PF_HEADER):
        if str(cur[i]).strip():
            continue                      # already labelled -- leave it alone
        fixed[i] = want
        added.append(want)
    if not added:
        return None
    print("  Precise Fiber row 1 is missing %d column label(s): %s"
          % (len(added), ", ".join(added)))
    try:
        _sheet_throttle()
        ws.batch_update([{"range": "A1:%s1" % _a1(len(fixed) - 1),
                          "values": [fixed]}], value_input_option="RAW")
    except Exception as e:
        print("  (could not repair the header: %s -- nothing else touched)"
              % str(e)[:60])
        return None
    print("  header repaired -- the address backfill can find its columns now.")
    return fixed


def backfill_addresses(sh, limit=BACKFILL_PER_LAUNCH):
    """Fill City/State/ZIP on located rows that lack them, and stamp when.
    Bounded, resumable, and it never touches a row it cannot verify."""
    try:
        ws = _pf_spreadsheet(sh).worksheet(PF_TAB)
        vals = ws.get_all_values()
    except Exception as e:
        print("  (address backfill skipped -- cannot read %s: %s)"
              % (PF_TAB, str(e)[:50]))
        return 0
    if len(vals) < 2:
        return 0
    hdr = [h.strip().lower() for h in vals[0]]
    col = lambda name: hdr.index(name) if name in hdr else -1
    i_lat, i_lng = col("lat"), col("lng")
    i_city, i_state, i_zip = col("city"), col("state"), col("zip")
    if min(i_lat, i_lng, i_city, i_state, i_zip) < 0:
        repaired = _repair_pf_header(ws, vals[0])
        if repaired:
            vals[0] = repaired
            hdr = [h.strip().lower() for h in repaired]
            i_lat, i_lng = col("lat"), col("lng")
            i_city, i_state, i_zip = col("city"), col("state"), col("zip")
    if min(i_lat, i_lng, i_city, i_state, i_zip) < 0:
        # Loud, not a one-line skip. This quietly switched the entire address
        # repair off for weeks and nobody could tell from the console.
        print("")
        print("  " + "!" * 66)
        print("  ADDRESS BACKFILL IS OFF. '%s' row 1 does not name" % PF_TAB)
        print("  Lat / Lng / City / State / ZIP, so nothing can be repaired and")
        print("  captured rows stay un-mailable and un-skip-traceable.")
        print("  Row 1 currently reads: %s" % (", ".join(vals[0]) or "(empty)"))
        print("  " + "!" * 66)
        print("")
        return 0
    width = max(len(vals[0]), i_zip + 1)
    i_when = col("backfilled at")
    if i_when < 0:                       # add the stamp column once
        i_when = width
        width += 1
        try:
            _sheet_throttle()
            ws.update_cell(1, i_when + 1, "Backfilled At")
        except Exception as e:
            print("  (could not add the Backfilled At header: %s)" % str(e)[:40])
            return 0

    cell = lambda r, i: (r[i] if i < len(r) else "").strip()
    todo, no_coords, dead = [], 0, 0
    for n, r in enumerate(vals[1:], start=2):        # n = real sheet row number
        if cell(r, i_city) and cell(r, i_state) and cell(r, i_zip):
            continue                                 # already complete
        if not (cell(r, i_lat) and cell(r, i_lng)):
            no_coords += 1
            continue                                 # cannot fill honestly
        if cell(r, i_when).upper().startswith(NO_MATCH):
            dead += 1
            continue    # its coordinates resolve to nothing; asked once, never
                        # again -- otherwise a handful of junk points would
                        # refill the batch every launch and starve real rows
        todo.append((n, cell(r, i_lat), cell(r, i_lng)))
        if len(todo) >= limit:
            break
    if dead:
        print("  address backfill: %d row(s) have coordinates that resolve to "
              "nothing -- marked, not retried." % dead)
    if no_coords:
        print("  address backfill: %d row(s) have no coordinates -- left exactly "
              "as they are (a city is never guessed from a street name)." % no_coords)
    if not todo:
        print("  address backfill: every located row already has a full address.")
        return 0

    print("  address backfill: repairing %d located row(s) from their "
          "coordinates (free Census geocoder)..." % len(todo))
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    updates, misses, filled = [], [], 0
    for n, lat, lng in todo:
        place = _census_place(lat, lng)
        if place is None:
            time.sleep(1.0)                          # one quick re-ask
            place = _census_place(lat, lng)
        if not place:
            # HOLD the miss -- do not write the marker yet. A marker is
            # permanent (the row is never looked up again), so it may only be
            # written once something ELSE in this same run proves the geocoder
            # was actually answering. A one-second re-ask does NOT survive an
            # outage: with the service down, every row here would miss, and
            # marking them would retire real addresses for good over a network
            # blip. Proof of life first, markers second.
            misses.append(n)
            continue
        city, state, zc = place
        row = [""] * width
        row[i_city], row[i_state], row[i_zip] = city, state, zc
        row[i_when] = stamp
        updates.append({"range": "%s%d:%s%d" % (_a1(i_city), n, _a1(i_when), n),
                        "values": [row[i_city:i_when + 1]]})
        filled += 1
        time.sleep(0.4)                              # polite to a free service
    if misses and filled:
        # The service answered for other rows, so these coordinates really do
        # resolve to nothing. Retire them so a handful of junk points cannot
        # refill the batch every launch and starve real rows.
        for n in misses:
            updates.append({"range": "%s%d:%s%d"
                                     % (_a1(i_when), n, _a1(i_when), n),
                            "values": [["%s %s" % (NO_MATCH, stamp)]]})
    elif misses:
        print("  address backfill: the geocoder answered nothing this run "
              "(%d row(s)) -- looks like an outage, so NOTHING was marked; "
              "they are retried next launch." % len(misses))
    if not updates:
        return 0
    try:
        for i in range(0, len(updates), 100):
            _sheet_throttle()
            ws.batch_update(updates[i:i + 100], value_input_option="RAW")
        print("  address backfill: %d row(s) now carry a full address, stamped %s."
              % (filled, stamp))
        return filled
    except Exception as e:
        print("  (address backfill write failed: %s -- rows unchanged, retried "
              "next launch)" % str(e)[:60])
        return 0


# ---------------------------------------------------------------------------
# ONE-SHOT GOLD PURGE (Patrick, 2026-08-27: "delete every gold dot before gold
# dot capture worked!!"). Gold-by-default -- the rule that called a customer
# gold whenever it could not decode the build code -- died on 2026-08-23
# (BRAIN 22.17); confirmed-copper-only capture was verified 2026-08-24
# (TEST-Gold-2026-08-24). So every 'Gold Confirmed' row captured BEFORE
# 2026-08-24 is that old contamination: not confirmed copper, not a $140
# upgrade, just a decode failure wearing a gold label.
#
# Safety, in order: the WHOLE tab is saved to a local CSV first; the removed
# rows are ALSO saved to their own JSON (NOT the replay dir -- replay would
# write them straight back); a missing/unrecognizable 'Captured At' header
# aborts the purge and touches nothing; the rewrite is the same 2-call
# overwrite+trim the dedupe uses (append-safe); and a marker file makes it
# run once per PC, ever.
# ---------------------------------------------------------------------------
GOLD_TAB = "Gold Confirmed"
GOLD_CUTOFF = "2026-08-24"          # keep rows captured ON or AFTER this day
# v2 ON PURPOSE. The build before 2026-09-03 wrote the old 'gold_purge_done.flag'
# even when the tab read as EMPTY -- i.e. on a FAILED read -- which disabled the
# purge on that PC permanently and silently. Any flag that build left behind is
# untrustworthy, so the marker name changes once and every PC gets exactly one
# honest retry. Do not rename it back.
_GOLD_PURGE_MARKER = os.path.join(HERE, "gold_purge_done_v2.flag")
_GOLD_PURGE_MARKER_OLD = os.path.join(HERE, "gold_purge_done.flag")


def _clean_open():
    """Open the workbook for the startup clean WITHOUT going near 'Maps
    Businesses'. open_sheet() creates that tab when it is missing, and a
    20000x7 add_worksheet is 140,000 cells -- an instant 400 on a workbook at
    the 10,000,000-cell ceiling. Its bare except then returned None, and the
    whole cleanup block was gated on that, so the sheet being too full stopped
    the very routine that frees the space. Measured 2026-09-03. This opens the
    spreadsheet and nothing else.

    Returns (spreadsheet_or_None, reason). RETRIES: measured on Patrick's PC
    2026-09-03, this got 'APIError: [503]' on the first attempt while
    open_sheet() opened the same workbook fine seconds later. A 5xx is Google
    being briefly unavailable, not a real failure, and giving up on it left the
    junk in place for the whole run."""
    creds = _find_creds()
    if not creds:
        return None, "no google_creds.json on this PC"
    last = "unknown"
    for attempt in range(4):
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            scopes = ["https://www.googleapis.com/auth/spreadsheets",
                      "https://www.googleapis.com/auth/drive"]
            client = gspread.authorize(
                Credentials.from_service_account_file(creds, scopes=scopes))
            return client.open_by_key(SHEET_ID), ""
        except Exception as e:
            last = str(e)[:70]
            if attempt < 3:
                print("     (workbook open failed: %s -- retrying)" % last)
                time.sleep(3 * (attempt + 1))
    return None, last


def _run_startup_clean(sh):
    """The three clean steps, in order. Split out so it can be retried against
    the handle open_sheet() gets when the standalone open lost a coin-flip 503."""
    for _label, _step in (("GOLD PURGE", purge_prefix_gold),
                          ("TEST-GOLD MIGRATION", migrate_test_gold),
                          ("JUNK TAB CLEAN", purge_junk_tabs),
                          ("TAB COUNTS", publish_tab_counts)):
        try:
            _step(sh)
        except Exception as e:
            # NO SILENT RUNNING (2026-08-28): name the step that failed. This
            # used to collapse into "(dedupe off: ...)", which reads as a minor
            # unrelated notice rather than "the gold tab was not cleaned".
            print("  *** %s DID NOT RUN: %s" % (_label, str(e)[:70]))


# ---------------------------------------------------------------------------
# JUNK TABS -- frozen snapshots and scratch tabs, removed once per PC.
#
# Named junk ONLY. A tab that is not on this list SURVIVES. That default is
# deliberate and it is the opposite of clean_sheet.py, which is a whitelist:
# run against the 29 live tabs on 2026-09-03 that whitelist would have deleted
# 14 tabs / 22,457 rows, and 7 of them were hand-built working tabs -- including
# 'Warm Backlog -- Replied YES' (40 people who had already said yes), the
# Angleton call list and the Beaumont work list. Reps and one-off scripts make
# tabs constantly; a whitelist deletes the ones nobody thought to list.
#
# 'Gold Dots' goes because it is RETIRED and contaminated (BRAIN 22.14) and
# 'GOLD - CLEAN' is its cleaned copy -- that one stays.
# ---------------------------------------------------------------------------
JUNK_TABS = {
    "gold dots",
    "tmp sweep census",
    "zz_tmp_grid",
    "_temp_ash_lookup",
    "_optimus_probe",               # write-access probe, transient by design
    "at&t test",
}
JUNK_TAB_PREFIX = ("test-", "debug", "_tmp", "tmp_", "zz_", "copy of ")
_JUNK_TABS_MARKER = os.path.join(HERE, "junk_tabs_done.flag")


def _is_junk_tab(title):
    low = title.strip().lower()
    # TEST-Gold-* holds real confirmed gold. It is never deleted here -- only
    # migrate_test_gold() may remove it, and only after its rows are safely in
    # 'Gold Confirmed'.
    if low.startswith("test-gold"):
        return False
    return low in JUNK_TABS or low.startswith(JUNK_TAB_PREFIX)


def migrate_test_gold(sh):
    """Fold the TEST-Gold-* verification snapshots into 'Gold Confirmed', then
    drop the tab. If the append fails for any reason the tab is LEFT ALONE --
    losing confirmed gold to a tidy-up would be far worse than a stale tab."""
    if sh is None:
        return
    try:
        tabs = [w for w in sh.worksheets()
                if w.title.strip().lower().startswith("test-gold")]
    except Exception as e:
        print("  (TEST-Gold migration skipped -- cannot list tabs: %s)" % str(e)[:60])
        return
    if not tabs:
        return
    try:
        gold = sh.worksheet(GOLD_TAB)
        have = set()
        for r in gold.get_all_values()[1:]:
            if r and r[0].strip():
                have.add(r[0].strip().upper())
    except Exception as e:
        print("  (TEST-Gold migration skipped -- cannot read '%s': %s)"
              % (GOLD_TAB, str(e)[:50]))
        return
    for w in tabs:
        try:
            _sheet_throttle()
            vals = w.get_all_values()
        except Exception as e:
            print("  (TEST-Gold migration skipped for '%s': %s)" % (w.title, str(e)[:50]))
            continue
        body = [r for r in vals[1:]
                if r and r[0].strip() and r[0].strip().upper() not in have]
        try:
            if body:
                _sheet_throttle()
                gold.append_rows(body, value_input_option="RAW")
                for r in body:
                    have.add(r[0].strip().upper())
            _sheet_throttle()
            sh.del_worksheet(w)
            print("  migrated '%s': %d new gold row(s) into '%s', tab removed."
                  % (w.title, len(body), GOLD_TAB))
        except Exception as e:
            print("  ! '%s' KEPT -- migration failed, nothing lost: %s"
                  % (w.title, str(e)[:60]))


def purge_junk_tabs(sh):
    """Delete the frozen snapshots and scratch tabs, backing every one up to a
    local CSV FIRST. A tab that cannot be backed up is not deleted."""
    if sh is None:
        return
    if os.path.exists(_JUNK_TABS_MARKER):
        print("  junk tabs: already done on this PC. (delete %s to run it again)"
              % _JUNK_TABS_MARKER)
        return
    try:
        doomed = [w for w in sh.worksheets() if _is_junk_tab(w.title)]
    except Exception as e:
        print("  (junk-tab clean SKIPPED -- cannot list tabs: %s)" % str(e)[:60])
        return
    if not doomed:
        print("  junk tabs: none present -- nothing to remove.")
        open(_JUNK_TABS_MARKER, "w").write("clean already %s" % time.ctime())
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(HERE, "tab_backup_%s" % stamp)
    try:
        os.makedirs(bdir)
    except Exception:
        pass
    print("\n  JUNK TABS: removing %d. Every one is saved to %s first."
          % (len(doomed), bdir))
    gone, held = 0, []
    for w in doomed:
        try:
            _sheet_throttle()
            vals = w.get_all_values()
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", w.title).strip("_") or "tab"
            with io.open(os.path.join(bdir, safe + ".csv"), "w",
                         newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(vals)
        except Exception as e:
            # No backup, no delete. A tab we could not read is a tab we keep.
            print("    ! KEPT '%s' -- could not back it up (%s)"
                  % (w.title, str(e)[:40]))
            held.append(w.title)
            continue
        try:
            _sheet_throttle()
            sh.del_worksheet(w)
            gone += 1
            print("    - %-32s %7d rows  (backed up)"
                  % (w.title[:32], max(len(vals) - 1, 0)))
        except Exception as e:
            print("    ! could not delete '%s': %s" % (w.title, str(e)[:40]))
            held.append(w.title)
    if gone and not held:
        open(_JUNK_TABS_MARKER, "w").write("removed %d %s" % (gone, time.ctime()))
    print("  JUNK TABS DONE: removed %d, backups in %s\n" % (gone, bdir))


# ---------------------------------------------------------------------------
# THE SHEET AS THE FOLLOW-UP BOARD -- enrichment, GHL status and sales, landed
# at every launch.
#
# Patrick, 2026-09-03: "when we enrich leads add that to the sheet" -> "so u
# don't enrich 2x, dnd, u can check if we called and if dead" -> "use the sheet
# to log sales etc" -> "color for sales status red no / green cb maybe / blue
# paid" -> "I want ghl data and whether or not we already enriched something to
# be obvious ... and if it's sold or needs to be called back cuz we're doing an
# atrocious job of following up" -> "the same columns grey green gold biz fiber
# green biz, and if it's enriched it has name cell number, color coded for
# sales cb or ni".
#
# So 'Enriched Leads' is ONE ROW PER PERSON, laid out like the hunter's own
# tabs: the 13 hunter columns first (Address .. Status, copied from whichever
# tab the address sits on: Gold Confirmed, Grey Fiber Customers, Precise Fiber,
# or a business tab), then WHICH TAB it came from, then Name and Cell, then the
# enrichment record, then the GHL follow-up block. The whole row is coloured by
# Disposition: green = call back, red = no / not interested / dead, blue = paid.
# A white row is a person nobody has touched -- the follow-up being lost.
#
# HOW IT GETS HERE. Claude cannot write the workbook (its Drive connector is
# file-level only), and names and cell numbers cannot go through GitHub (both
# repos are PUBLIC). So Claude drops a small Google Sheet titled
# "OPTIMUS FEED <kind>" into the Drive folder FEED_FOLDER_ID, which is shared
# with the service account this program already runs as. At launch this step
# lists that folder, lands every file it has not seen, and renames the file
# "LANDED ..." so it is never read twice. Then it stamps a receipt on GitHub
# (optimus/_feed/_landed.json, no PII) so Claude can confirm delivery without
# Google auth: CHECK THE DESTINATION, not the return value.
#
# "So that doesn't cause a prob": every row carries a key (GHL contact id,
# else ADDRESS|ENRICHED AT; a sale keys on the opportunity id), so a launch
# repeats safely; the tabs live in the SPLIT workbook because production is at
# the 10,000,000-cell ceiling; a FULL workbook is said out loud and never
# retried; rows a person typed by hand on 'Sales Log' are never touched; and
# no dollar figure is ever written -- the sheet is shared with the team.
# ---------------------------------------------------------------------------
FEED_FOLDER_ID = "1XOqADybKvneC5gwsxjpsGkVC6RLQ-1an"      # 'OPTIMUS FEED (Claude -> sheet)'
FEED_TITLE = "OPTIMUS FEED"                               # + " enriched" | " status" | " sales"
FEED_ROOT = "optimus/_feed"                               # the receipt lives here on GitHub
ENRICHED_TAB = "Enriched Leads"
HUNTER_COLS = ["Address", "Dot Color", "Captured At", "Business", "Phone",
               "Run ID", "Operator", "Lat", "Lng", "City", "State", "ZIP", "Status"]
ENRICHED_HEADER = HUNTER_COLS + [
    "Tab",                                                 # which hunter tab the dot is on
    "Name", "Cell", "Phone Type",                          # the person (DealMachine / GHL)
    "Enriched At", "Source", "Pool", "GHL Contact ID", "Likely Gold", "DNC",
    "Dialed", "Last Call", "Disposition", "DND", "Dead", "Status At"]   # GHL follow-up
STATUS_COLS = ("dialed", "last_call", "disposition", "dnd", "dead", "status_at")
STATUS_FIRST_COL = ENRICHED_HEADER.index("Dialed") + 1          # 1-based
_E = {name: i for i, name in enumerate(ENRICHED_HEADER)}        # column index by name
SALES_TAB = "Sales Log"
SALES_HEADER = ["Sold At", "Address", "City", "State", "ZIP", "Name", "Cell", "Product",
                "Rep #", "Pool", "Source", "GHL Contact ID", "Opportunity ID", "Stage",
                "Status", "Logged At"]
# The whole row takes the colour of its Disposition / Status cell. Free text:
# CB, CALL BACK, MAYBE -> green; NO, NI, NOT INTERESTED, DEAD -> red; PAID,
# SOLD, INSTALLED -> blue.
STATUS_COLOURS = (
    ("PAID|SOLD|INSTALLED",              {"red": 0.74, "green": 0.84, "blue": 0.98}),  # blue
    ("^NO$|^NI$|NOT INTERESTED|DEAD|DNC", {"red": 0.96, "green": 0.72, "blue": 0.72}),  # red
    ("^CB|CALL ?BACK|MAYBE",             {"red": 0.72, "green": 0.90, "blue": 0.72}),  # green
)
GREY_TAB = "Grey Fiber Customers"
MAPS_BIZ_TAB = "Maps Businesses"
_STATUS_WORDS = {"GREEN": "Non-AT&T Customer - Can Get Fiber",
                 "ORANGE": "Upgrade Customer - On Copper, Fiber Available",
                 "GOLD": "Upgrade Customer - On Copper, Fiber Available",
                 "GREY": "Existing AT&T Customer"}


def _feed_sheets(client, kind):
    """[(spreadsheet id, title)] of unlanded feed files for one kind, oldest
    first. A landed file is renamed 'LANDED ...' and no longer matches."""
    want = ("%s %s" % (FEED_TITLE, kind)).lower()
    out = []
    for f in client.list_spreadsheet_files(folder_id=FEED_FOLDER_ID):
        name = (f.get("name") or "").strip()
        if name.lower().startswith(want):
            out.append((f.get("id"), name))
    return sorted(out, key=lambda x: x[1])


def _feed_rows(client, sid):
    """First tab of a feed sheet -> list of dicts keyed by its header row."""
    vals = client.open_by_key(sid).sheet1.get_all_values()
    if not vals:
        return []
    head = [h.strip().lower().replace(" ", "_") for h in vals[0]]
    rows = []
    for r in vals[1:]:
        if not any(c.strip() for c in r):
            continue
        rows.append({h: r[i].strip() for i, h in enumerate(head) if h and i < len(r)})
    return rows


def _mark_landed(client, sid, name):
    try:
        client.open_by_key(sid).update_title("LANDED " + name)
    except Exception as e:
        print("  (SHEET LOG: could not rename feed '%s' -- it is re-read next launch,"
              " harmlessly: %s)" % (name, str(e)[:40]))


def _hunter_lookup(book_main):
    """Normalised address -> (tab, the 13 hunter columns). Gold and grey from
    their own tabs (small); the three business tabs give Business + Phone;
    green from the biz-match set, which init_match() already loaded from the
    ~700k-row Precise Fiber tab. Read ONLY when there is something to land."""
    known = {}

    def take(tab, header, rows):
        idx = {h: i for i, h in enumerate(header)}
        for r in rows:
            k = _norm_addr(r[0] if r else "")
            if not k or k in known:
                continue
            row = [""] * len(HUNTER_COLS)
            for j, col in enumerate(HUNTER_COLS):
                i = idx.get(col)
                if i is not None and i < len(r):
                    row[j] = r[i]
            if not row[1]:
                row[1] = "ORANGE" if tab == GOLD_TAB else "GREY"
            if not row[12]:
                row[12] = _STATUS_WORDS.get(row[1].upper(), "")
            known[k] = (tab, row)

    for tab in (GOLD_TAB, GREY_TAB):
        try:
            _sheet_throttle()
            vals = book_main.worksheet(tab).get_all_values()
            if vals:
                take(tab, vals[0], vals[1:])
        except Exception as e:
            print("  (SHEET LOG: '%s' not read for the lookup: %s)" % (tab, str(e)[:40]))
    for tab in (GREEN_BIZ_TAB, ORANGE_BIZ_TAB, MAPS_BIZ_TAB):
        try:
            _sheet_throttle()
            vals = book_main.worksheet(tab).get_all_values()
        except Exception:
            continue
        for r in vals[1:]:                       # BIZ_HEADER: Business Name, Phone, Address, ...
            k = _norm_addr(r[2] if len(r) > 2 else "")
            if not k:
                continue
            if k in known:
                row = known[k][1]
                if not row[3]:
                    row[3], row[4] = r[0], (r[1] if len(r) > 1 else "")
                continue
            row = [""] * len(HUNTER_COLS)
            row[0], row[3], row[4] = r[2], r[0], (r[1] if len(r) > 1 else "")
            row[1] = "GREEN" if tab == GREEN_BIZ_TAB else "ORANGE" if tab == ORANGE_BIZ_TAB else ""
            row[12] = _STATUS_WORDS.get(row[1], "")
            known[k] = (tab, row)
    for k, colour in (_MATCH.get("leads") or {}).items():
        if k not in known:
            row = [""] * len(HUNTER_COLS)
            row[1], row[12] = colour, _STATUS_WORDS.get(colour, "")
            known[k] = ("Precise Fiber" if colour == "GREEN" else GOLD_TAB, row)
    return known


def _s(v):
    if v is True:
        return "YES"
    if v is False or v is None:
        return ""
    return str(v).strip()


def _yes(v):
    return "YES" if _s(v).upper() in ("YES", "TRUE", "1", "Y") else ""


def _enriched_row(r, known, stamp):
    """One 'enriched' feed row -> (key, sheet row). Pure -- tested without
    Google. Hunter columns come from the lookup when the address is on the
    map; the feed's own city/state/zip/lat/lng fill any blank. Key = GHL id,
    else ADDRESS|ENRICHED AT."""
    addr = _s(r.get("address"))
    if not addr:
        return None
    when = _s(r.get("enriched_at"))
    gid = _s(r.get("ghl_contact_id"))
    key = gid or ("%s|%s" % (addr.upper(), when))
    tab, hrow = known.get(_norm_addr(addr), ("", [""] * len(HUNTER_COLS)))
    row = list(hrow)
    row[0] = row[0] or addr
    for col, fld in (("City", "city"), ("State", "state"), ("ZIP", "zip"),
                     ("Lat", "lat"), ("Lng", "lng"), ("Business", "business")):
        if not row[_E[col]]:
            row[_E[col]] = _s(r.get(fld))
    if not row[1]:
        row[1] = (_s(r.get("colour")) or "UNVERIFIED").upper()
    if not row[12]:
        row[12] = _STATUS_WORDS.get(row[1], "Not on the hunter map yet - colour unverified")
    row += [tab, _s(r.get("name")), _s(r.get("cell")), _s(r.get("phone_type")), when,
            _s(r.get("source")), _s(r.get("pool")), gid,
            _yes(r.get("likely_gold")), _yes(r.get("dnc"))]
    row += [_s(r.get(c)) for c in STATUS_COLS]
    if not row[-1] and any(row[-6:-1]):
        row[-1] = stamp
    return key, row


def _sales_row(r, stamp):
    """One 'sales' feed row -> (key, sheet row). Key = opportunity id, else
    GHL id|sold at. No dollar figures: the sheet is shared with the team."""
    sold = _s(r.get("sold_at"))
    gid, oid, addr = _s(r.get("ghl_contact_id")), _s(r.get("opportunity_id")), _s(r.get("address"))
    if not (gid or oid or addr):
        return None
    key = oid or ("%s|%s" % (gid or addr.upper(), sold))
    return key, [sold, addr, _s(r.get("city")), _s(r.get("state")), _s(r.get("zip")),
                 _s(r.get("name")), _s(r.get("cell")), _s(r.get("product")), _s(r.get("rep")),
                 _s(r.get("pool")), _s(r.get("source")), gid, oid, _s(r.get("stage")),
                 _s(r.get("status")) or "PAID", stamp]


def _colour_status_rows(book, ws, header, col_name):
    """Conditional formatting: colour the whole row by the text in `col_name`.
    Added once, when the tab is created. Formatting can never stop rows from
    landing -- any failure is one printed line."""
    try:
        c = header.index(col_name)
        col = _col_letter(c + 1)
        reqs = []
        for i, (pattern, rgb) in enumerate(STATUS_COLOURS):
            reqs.append({"addConditionalFormatRule": {"index": i, "rule": {
                "ranges": [{"sheetId": ws.id, "startRowIndex": 1,
                            "startColumnIndex": 0, "endColumnIndex": len(header)}],
                "booleanRule": {
                    "condition": {"type": "CUSTOM_FORMULA", "values": [
                        {"userEnteredValue": '=REGEXMATCH(UPPER($%s2),"%s")' % (col, pattern)}]},
                    "format": {"backgroundColor": rgb}}}}})
        _sheet_throttle()
        book.batch_update({"requests": reqs})
        print("  SHEET LOG: '%s' rows colour by %s (green CB / red NI / blue PAID)."
              % (ws.title, col_name))
    except Exception as e:
        print("  (SHEET LOG: colour rules not added on '%s': %s)" % (ws.title, str(e)[:50]))


def _status_row(r, stamp):
    """One 'status' feed row -> (ghl id, [Dialed, Last Call, Disposition, DND, Dead, Status At])."""
    gid = _s(r.get("ghl_contact_id"))
    if not gid:
        return None
    vals = [_s(r.get(c)) for c in STATUS_COLS]
    if not vals[-1]:
        vals[-1] = stamp
    return gid, vals


def _tab_keys(values, id_col, key_cols):
    """Keys already on a tab: the id column when filled, else key_cols joined."""
    have = set()
    for row in values[1:]:
        if not row:
            continue
        gid = row[id_col].strip() if len(row) > id_col else ""
        if gid:
            have.add(gid)
            continue
        parts = [(row[c].strip().upper() if c == key_cols[0] else row[c].strip())
                 if len(row) > c else "" for c in key_cols]
        if parts[0]:
            have.add("|".join(parts))
    return have


def _col_letter(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _open_log_tab(book, title, header, where):
    """The tab, created with its header if missing, header widened if an
    older build made it narrower. None (already explained) on failure."""
    try:
        ws = book.worksheet(title)
    except Exception:
        try:
            _sheet_throttle()
            ws = book.add_worksheet(title=title, rows="1000", cols=str(len(header)))
            _sheet_throttle()
            ws.append_row(header, value_input_option="RAW")
            print("  SHEET LOG: created tab '%s' in the %s." % (title, where))
            _colour_status_rows(book, ws, header,
                                "Status" if title == SALES_TAB else "Disposition")
            return ws
        except Exception as e:
            if _err_kind(e) == "FULL":
                print("  *** SHEET LOG NOT LANDED: the %s is at the 10,000,000-cell"
                      " ceiling, so '%s' cannot be created there. Share the split"
                      " workbook with the service account and relaunch." % (where, title))
            else:
                print("  *** SHEET LOG NOT LANDED: could not make '%s': %s"
                      % (title, str(e)[:60]))
            return None
    try:
        _sheet_throttle()
        head = ws.row_values(1)
        if head and head != header[:len(head)]:
            print("  *** SHEET LOG: '%s' has a different header than this build expects"
                  " -- leaving it alone. Rename that tab to keep it, then relaunch." % title)
            return None
        if len(head) < len(header):
            if ws.col_count < len(header):
                _sheet_throttle()
                ws.resize(cols=len(header))
            _sheet_throttle()
            ws.update("A1:%s1" % _col_letter(len(header)), [header],
                      value_input_option="RAW")
            print("  SHEET LOG: '%s' header widened to %d columns." % (title, len(header)))
    except Exception as e:
        print("  (SHEET LOG: could not check the '%s' header: %s)" % (title, str(e)[:50]))
    return ws


def _append_rows(ws, rows, kind):
    """Append in 500-row batches under the write throttle. (landed, all ok)."""
    landed = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        try:
            _sheet_throttle()
            ws.append_rows(chunk, value_input_option="RAW")
            landed += len(chunk)
        except Exception as e:
            print("  *** SHEET LOG: %d of %d '%s' row(s) NOT landed -- %s%s"
                  % (len(rows) - landed, len(rows), kind,
                     "workbook FULL (cell ceiling), " if _err_kind(e) == "FULL" else "",
                     str(e)[:50]))
            print("  *** The feed file stays unlanded and is retried next launch.")
            return landed, False
    return landed, True


def _read_feed_files(client, files, to_row, stamp, have=None, collect=None):
    """Every row of every feed file -> to_row(); rows whose key is already on
    the tab are skipped. Returns the files that were fully read."""
    ok = []
    for sid, name in files:
        try:
            rows = _feed_rows(client, sid)
        except Exception as e:
            print("  (SHEET LOG: feed '%s' unreadable: %s)" % (name, str(e)[:40]))
            continue
        for r in rows:
            kr = to_row(r, stamp)
            if kr and (have is None or kr[0] not in have):
                if have is not None:
                    have.add(kr[0])
                collect(kr)
        ok.append((sid, name))
    return ok


def sync_sheet_log(sh):
    """Runs after open_sheet()/init_match(), so the green set is loaded."""
    if sh is None:
        return
    client = sh.client
    book = _pf_spreadsheet(sh)
    where = "split workbook" if book is not sh else "MAIN workbook (split did not open)"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    report = {"generated_at": stamp, "source": "maps_scraper startup", "workbook": where}
    try:
        feeds = {k: _feed_sheets(client, k) for k in ("enriched", "status", "sales")}
    except Exception as e:
        print("  SHEET LOG: feed folder not readable (%s) -- share Drive folder %s with"
              " the service account. Retries next launch." % (str(e)[:40], FEED_FOLDER_ID))
        return
    if not any(feeds.values()):
        print("  SHEET LOG: nothing new in the feed folder.")
        gh_put(FEED_ROOT + "/_landed.json",
               json.dumps(dict(report, nothing_new=True), separators=(",", ":")))
        return
    values = None
    ws = _open_log_tab(book, ENRICHED_TAB, ENRICHED_HEADER, where) \
        if (feeds["enriched"] or feeds["status"]) else None
    if ws is not None:
        try:
            _sheet_throttle()
            values = ws.get_all_values()
        except Exception as e:
            print("  *** SHEET LOG: cannot read '%s': %s" % (ENRICHED_TAB, str(e)[:60]))
    if ws is not None and values is not None:
        # 1. enriched: new people, laid out like the hunter's tabs
        if feeds["enriched"]:
            known = _hunter_lookup(sh)
            have = _tab_keys(values, _E["GHL Contact ID"], (0, _E["Enriched At"]))
            new = []
            files = _read_feed_files(client, feeds["enriched"],
                                     lambda r, st: _enriched_row(r, known, st),
                                     stamp, have, lambda kr: new.append(kr[1]))
            landed, ok = _append_rows(ws, new, "enriched")
            done = new[:landed]
            on_map = sum(1 for r in done if r[_E["Tab"]])
            print("  SHEET LOG: enriched -> '%s': %d file(s), %d new row(s), %d on the hunter"
                  " map (%d gold/orange, %d grey, %d green)"
                  % (ENRICHED_TAB, len(files), landed, on_map,
                     sum(1 for r in done if r[1] in ("ORANGE", "GOLD")),
                     sum(1 for r in done if r[1] == "GREY"),
                     sum(1 for r in done if r[1] == "GREEN")))
            if ok:
                for sid, name in files:
                    _mark_landed(client, sid, name)
            report["enriched"] = {"files": len(files), "landed": landed, "on_map": on_map}
            if landed:
                try:
                    _sheet_throttle()
                    values = ws.get_all_values()
                except Exception:
                    values = None
        # 2. status: the GHL follow-up columns on those rows, newest file wins
        if feeds["status"] and values is not None:
            latest = {}
            files = _read_feed_files(client, feeds["status"], _status_row, stamp,
                                     None, lambda kv: latest.__setitem__(kv[0], kv[1]))
            idx = {}
            gcol = _E["GHL Contact ID"]
            for n, row in enumerate(values[1:], start=2):
                g = row[gcol].strip() if len(row) > gcol else ""
                if g:
                    idx.setdefault(g, n)
            c0 = _col_letter(STATUS_FIRST_COL)
            c1 = _col_letter(STATUS_FIRST_COL + len(STATUS_COLS) - 1)
            updates, missing = [], 0
            for gid, vals in latest.items():
                n = idx.get(gid)
                if n is None:
                    missing += 1
                    continue
                cur = values[n - 1][STATUS_FIRST_COL - 1:STATUS_FIRST_COL - 1 + len(STATUS_COLS)]
                if len(cur) == len(vals) and [c.strip() for c in cur] == vals:
                    continue
                updates.append({"range": "%s%d:%s%d" % (c0, n, c1, n), "values": [vals]})
            done, ok = 0, True
            for i in range(0, len(updates), 500):
                try:
                    _sheet_throttle()
                    ws.batch_update(updates[i:i + 500], value_input_option="RAW")
                    done += len(updates[i:i + 500])
                except Exception as e:
                    print("  *** SHEET LOG: %d status row(s) NOT updated -- %s"
                          % (len(updates) - done, str(e)[:60]))
                    ok = False
                    break
            print("  SHEET LOG: status -> '%s': %d file(s), %d row(s) updated, %d unchanged%s"
                  % (ENRICHED_TAB, len(files), done, len(latest) - len(updates) - missing,
                     ", %d id(s) not on the tab (enrich them first)" % missing if missing else ""))
            if ok:
                for sid, name in files:
                    _mark_landed(client, sid, name)
            report["status"] = {"files": len(files), "updated": done, "not_on_tab": missing}
        try:
            report["enriched_rows_on_tab"] = max(len(ws.col_values(1)) - 1, 0)
        except Exception:
            pass
    # 3. sales on 'Sales Log' -- hand-typed rows have no id and are left alone
    if feeds["sales"]:
        ws2 = _open_log_tab(book, SALES_TAB, SALES_HEADER, where)
        if ws2 is not None:
            try:
                _sheet_throttle()
                vals = ws2.get_all_values()
                oi, gi = SALES_HEADER.index("Opportunity ID"), SALES_HEADER.index("GHL Contact ID")
                have = _tab_keys(vals, oi, (1, 0))
                for row in vals[1:]:
                    if len(row) > gi and row[gi].strip():
                        have.add("%s|%s" % (row[gi].strip(), row[0].strip()))
                new = []
                files = _read_feed_files(client, feeds["sales"], _sales_row, stamp,
                                         have, lambda kr: new.append(kr[1]))
                landed, ok = _append_rows(ws2, new, "sales")
                print("  SHEET LOG: sales -> '%s': %d file(s), %d new row(s)"
                      % (SALES_TAB, len(files), landed))
                if ok:
                    for sid, name in files:
                        _mark_landed(client, sid, name)
                report["sales"] = {"files": len(files), "landed": landed,
                                   "rows_on_tab": len(vals) - 1 + landed}
            except Exception as e:
                print("  *** SHEET LOG: cannot read '%s': %s" % (SALES_TAB, str(e)[:60]))
    # Tell Claude what landed WITHOUT Google auth: CHECK THE DESTINATION, not
    # the return value. A launch that lands nothing still stamps this, so a
    # stale stamp means "no scraper launch since", not "nothing to land".
    gh_put(FEED_ROOT + "/_landed.json", json.dumps(report, separators=(",", ":")))


def publish_tab_counts(sh):
    """Every tab and its data-row count -> optimus/_feed/sheet/tabs.json on
    GitHub, WITH a timestamp, at every launch. Replaces COUNT_TABS.bat.

    Patrick, 2026-09-03: "I don't like extra program, can u connect it to the
    launch of something." Before this the feed refreshed only when someone
    remembered to run the .bat; it sat at 08-27 numbers for a week and the
    brain quoted 'Gold Confirmed = 11,490' as live while the tab held 1,884.
    Runs AFTER the clean so the feed shows the cleaned state. Every launch, not
    once per PC -- counts change, flags do not apply."""
    if sh is None:
        return
    out = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "source": "maps_scraper startup", "tabs": []}
    try:
        tabs = sh.worksheets()
    except Exception as e:
        print("  (tab counts NOT published -- cannot list tabs: %s)" % str(e)[:50])
        return
    for ws in tabs:
        try:
            _sheet_throttle()
            n = max(len(ws.col_values(1)) - 1, 0)          # data rows, minus header
        except Exception as e:
            n = -1                                            # -1 = could not read
        out["tabs"].append({"tab": ws.title, "rows": n})
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    ok = gh_put("optimus/_feed/sheet/tabs.json", text)
    print("  TAB COUNTS: %d tabs -> %s" % (
        len(out["tabs"]),
        "published (tabs.json, stamped %s)" % out["generated_at"] if ok
        else "NOT published -- no github_token.txt, counts stay stale on GitHub"))


def purge_prefix_gold(sh):
    if sh is None:
        return
    if os.path.exists(_GOLD_PURGE_MARKER):
        # NO SILENT RUNNING: say WHY nothing happened. This used to be a bare
        # `return` and an operator had no way to tell "already clean" from
        # "quietly disabled".
        try:
            _was = io.open(_GOLD_PURGE_MARKER, encoding="utf-8").read().strip()[:60]
        except Exception:
            _was = "?"
        print("  gold purge: already done on this PC (%s)." % _was)
        print("  (delete %s to run it again)" % _GOLD_PURGE_MARKER)
        return
    if os.path.exists(_GOLD_PURGE_MARKER_OLD):
        print("  gold purge: ignoring the OLD done-flag -- the build that wrote it"
              " could write it on a FAILED read. Running the purge once more.")
    try:
        ws = sh.worksheet(GOLD_TAB)
        vals = ws.get_all_values()
    except Exception as e:
        print("  (gold purge skipped -- cannot read '%s': %s)" % (GOLD_TAB, str(e)[:50]))
        return
    if len(vals) < 2:
        # NOT marking done. An empty read is a FAILED read, not a clean tab --
        # one quota blip used to write the marker and disable the purge on this
        # PC forever (measured 2026-09-03).
        print("  (gold purge: '%s' read as %d rows -- retrying next launch)"
              % (GOLD_TAB, len(vals)))
        return
    hdr = vals[0]
    cap_i = None
    for i, h in enumerate(hdr):
        if h.strip().lower() == "captured at":
            cap_i = i
            break
    if cap_i is None:
        print("  (gold purge ABORTED -- no 'Captured At' column in '%s'; nothing touched)"
              % GOLD_TAB)
        return
    rows = vals[1:]

    def _kept(r):
        # Must LOOK like a date before it may compare as one: "not a date"
        # sorts above "2026-08-24" as a string and would survive the purge.
        d = (r[cap_i] if cap_i < len(r) else "").strip()
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}", d)) and d[:10] >= GOLD_CUTOFF

    keep = [r for r in rows if _kept(r)]
    remove = [r for r in rows if not _kept(r)]
    if not remove:
        open(_GOLD_PURGE_MARKER, "w").write("clean already %s" % time.ctime())
        print("  gold purge: nothing to remove -- all %d rows are post-fix." % len(rows))
        return

    stamp = time.strftime("%Y%m%d-%H%M%S")
    try:                                       # backup EVERYTHING before any change
        import csv as _csv
        bpath = os.path.join(HERE, "gold_confirmed_backup_%s.csv" % stamp)
        with open(bpath, "w", newline="", encoding="utf-8") as f:
            _csv.writer(f).writerows(vals)
        with io.open(os.path.join(HERE, "gold_purged_%s.json" % stamp),
                     "w", encoding="utf-8") as f:
            json.dump({"tab": GOLD_TAB, "cutoff": GOLD_CUTOFF, "rows": remove}, f)
    except Exception as e:
        print("  (gold purge ABORTED -- could not write the backup: %s)" % str(e)[:50])
        return

    print("  GOLD PURGE: '%s' has %d rows; %d captured before %s (the era when"
          % (GOLD_TAB, len(rows), len(remove), GOLD_CUTOFF))
    print("  gold-by-default mislabeled decode failures) -- removing them now.")
    print("  Full backup: %s" % bpath)
    try:
        width = max(len(hdr), max((len(r) for r in keep), default=len(hdr)))
        body = [(list(r) + [""] * width)[:width] for r in keep]
        _sheet_throttle()
        if body:
            ws.batch_update([{"range": "A2", "values": body}],
                            value_input_option="RAW")
        lo, hi = len(body) + 2, len(rows) + 1
        if hi >= lo:
            _sheet_throttle()
            ws.spreadsheet.batch_update({"requests": [{"deleteDimension": {"range": {
                "sheetId": ws.id, "dimension": "ROWS",
                "startIndex": lo - 1, "endIndex": hi}}}]})
        open(_GOLD_PURGE_MARKER, "w").write(
            "purged %d kept %d %s" % (len(remove), len(keep), time.ctime()))
        print("  GOLD PURGE DONE: kept %d confirmed gold, removed %d pre-fix rows."
              % (len(keep), len(remove)))
    except Exception as e:
        print("  (gold purge FAILED mid-write: %s -- backup is safe at %s;"
              " it will retry next launch)" % (str(e)[:60], bpath))


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
_PARKED_ROWS = [0]        # rows parked to disk this run -- shown in every status line
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
        _PARKED_ROWS[0] += len(rows)
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
    # ---- THE STARTUP CLEAN -------------------------------------------------
    # Patrick, 2026-09-03: "attach that software to the map scraper start up /
    # for the 5th time i don't want 5 programs, 2 is enough." So the clean is
    # HERE, not in a .bat nobody remembers to run.
    #
    # It runs BEFORE open_sheet() on purpose. open_sheet() can need to create a
    # 20000x7 tab = 140,000 cells, which is an instant 400 on a workbook at the
    # 10M ceiling; its bare except returned None and the old cleanup block was
    # gated on that. So the sheet being full stopped the cleanup that frees the
    # space -- the purge was the cure for the condition blocking the purge, and
    # it had never run once in five builds. Clean first, then open.
    _want_clean = to_sheet and os.environ.get(
        "SCRAPER_NO_CLEAN", "").strip().lower() not in ("1", "true", "yes")
    _clean_done = False
    if _want_clean:
        print("\n  Startup clean (once per PC: junk gold rows, then junk tabs)...")
        _clean_sh, _why = None, "unknown"
        try:
            _clean_sh, _why = _clean_open()
        except Exception as e:
            _why = str(e)[:70]
        if _clean_sh is not None:
            _run_startup_clean(_clean_sh)
            _clean_done = True
        else:
            print("  *** Could not open the workbook for the clean: %s" % _why)
            print("  *** Trying again on the connection the scraper opens next.")

    sheet_ws, sheet_seen = (open_sheet() if to_sheet else (None, set()))

    # SECOND CHANCE. On 2026-09-03 the standalone open got a 503 and open_sheet()
    # opened the SAME workbook seconds later -- so a transient blip used to cost
    # the whole clean. If the first attempt lost, reuse the handle that worked.
    if _want_clean and not _clean_done and sheet_ws is not None:
        print("\n  Startup clean, second attempt (on the live connection)...")
        try:
            _run_startup_clean(sheet_ws.spreadsheet)
            _clean_done = True
        except Exception as e:
            print("  *** STARTUP CLEAN DID NOT RUN: %s" % str(e)[:70])
    if _want_clean and not _clean_done:
        print("\n  *** THE JUNK GOLD ROWS AND JUNK TABS ARE STILL THERE.")
        print("  *** Nothing was deleted. It retries on the next launch.\n")
    # Rows an earlier run could not write (sheet full, quota) go in first, so a
    # backlog drains instead of growing. Bounded per launch -- see replay_parked.
    try:
        replay_parked(sheet_ws, sheet_seen)
    except Exception as e:
        print("  (replay skipped: %s)" % str(e)[:60])

    # THE FOLLOW-UP BOARD (Patrick 2026-09-03): land what Claude enriched, the
    # GHL status and sales on the split workbook. After open_sheet() on purpose:
    # init_match() has read Precise Fiber by now, so green dots resolve free.
    if _want_clean and sheet_ws is not None:
        try:
            sync_sheet_log(sheet_ws.spreadsheet)
        except Exception as e:
            print("  *** SHEET LOG DID NOT RUN: %s" % str(e)[:70])
    # Keep the tabs deduped in the background while the scraper runs (phone-keyed
    # on the biz tabs). Cross-machine locked so it never collides with the hunter.
    if sheet_ws is not None and os.environ.get("SCRAPER_NO_DEDUPE", "").strip() not in ("1", "true", "yes"):
        try:
            backfill_addresses(sheet_ws.spreadsheet)         # bounded, resumable
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
                # When the sheet is full the run keeps capturing (the rows are
                # parked and replay later) -- but the operator must never be
                # able to mistake that for delivery. A banner printed once
                # scrolls away in minutes; this is on every single line.
                flag = ("   <-- NOT ON THE SHEET, parked (%d held)" % _PARKED_ROWS[0]
                        if _SHEET_FULL["hit"] else "")
                print("  [%d/%d] %-32s +%d (%d w/phone)%s"
                      % (i, len(qs), q[:32], new, withp, flag))
                # REAL-TIME COUNT: push the running tally every 5 searches so
                # Claude can read "how many pulled so far" at any moment.
                if i % 5 == 0:
                    push_live_counts_scraper(total, sheet_added, z)
            if not stopped:
                zips_done.add(z)                         # whole ZIP covered
                save_zips_done(zips_done)
                push_live_counts_scraper(total, sheet_added, z)   # ZIP-complete snapshot
                if _SHEET_FULL["hit"]:
                    print("=== ZIP %s done -- BUT NOTHING WENT TO THE SHEET (%d rows "
                          "parked on this PC; the workbook is full) ===" % (z, _PARKED_ROWS[0]))
                else:
                    print("=== ZIP %s done -> moving to the next needed ZIP ===" % z)
        out_f.close()
        ctx.close()
    push_live_counts_scraper(total, sheet_added, "DONE (final count)")
    print("\nDONE this session: %d businesses (CSV: %s)." % (total, OUT_PATH))
    if to_sheet and _SHEET_FULL["hit"]:
        print("")
        print("  " + "!" * 66)
        print("  NOTHING REACHED THE SHEET THIS RUN. The workbook is FULL.")
        print("  %d row(s) are parked on this PC and go in automatically once" % _PARKED_ROWS[0])
        print("  there is room. Scraping more right now adds nothing you can use.")
        print("  Tell Patrick the sheet is full.")
        print("  " + "!" * 66)
    elif to_sheet:
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
