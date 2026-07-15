#!/usr/bin/env python3
"""
COMMERCIAL SPLIT v1.0 -- separate the captured fiber leads into COMMERCIAL
(a business is at the address -> callable, with name + phone) vs RESIDENTIAL
(a home -> door-knock, no phone), the scalable MapMan way.
=============================================================================
WHY: looking up 20,000 addresses one-by-one on Google Maps gets blocked fast.
The proven approach is BULK: scrape every business in the ZIP by category (one
search returns ~120), then CROSS-REFERENCE that business list against the fiber
addresses. A match = COMMERCIAL (attach the business name + phone); no match =
RESIDENTIAL. That both classifies the leads AND phones the commercial ones, and
because it's a few hundred bulk searches (not 20k lookups) it doesn't trip
Google's bot blocking -- which is exactly why the old MapMan worked.

THE SCRAPER (free, open source, does the bulk pull + anti-blocking for us):
  gosom/google-maps-scraper  -- MIT, no API key, prebuilt Windows binary.
  https://github.com/gosom/google-maps-scraper/releases
  Run:  google-maps-scraper -input queries.txt -results businesses.csv -depth 1

WORKFLOW:
  1) python commercial_split.py make-queries --zips 77027,77019 -> queries.txt
  2) google-maps-scraper -input queries.txt -results businesses.csv -depth 1
  3) python commercial_split.py split --businesses businesses.csv
       -> writes 'Commercial Leads' (name+phone) and 'Residential Leads' tabs.

COMPLIANCE (unchanged): commercial phones feed DNC-scrubbed MANUAL CALL / power
dialer; residential is a door-knock list. No cold texting.
"""

import os, sys, csv, json, re, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
FIBER_JSONL = os.path.join(HERE, "precise_addresses.jsonl")
SHEET_ID = "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA"
COMMERCIAL_TAB = "Commercial Leads"
RESIDENTIAL_TAB = "Residential Leads"
COMMERCIAL_HEADER = ["Category", "Email", "Business Name", "Address", "Phone"]
RESIDENTIAL_HEADER = ["Address", "Dot Color", "Zone", "Lat", "Lng"]

# bizmatch: cross-reference captured fiber leads (Precise Fiber tab) with scraped
# businesses (Maps Businesses tab) and split the business ones by dot color.
PRECISE_TAB = "Precise Fiber"
MAPS_TAB = "Maps Businesses"
FIBER_GREEN_TAB = "Fiber Green Biz"        # green dot = sell NEW fiber
UPGRADE_ORANGE_TAB = "Upgrade Orange Biz"  # orange dot = upgrade copper -> fiber
BIZ_HEADER = ["Business Name", "Phone", "Address", "Website", "Category"]

# Three category sets you pick from at the start of a run (MAPMAN asks). All are
# small-business + in-home focused (owner-operated / mobile / home-based -- many
# sit at RESIDENTIAL addresses, so searching them catches the home-based ones a
# plain "is it a house?" test would miss). Edit freely.

# QUICK (~20): the highest-value common small businesses; fastest scrape.
CATEGORIES_CORE = [
    "plumber", "electrician", "hvac", "roofing", "general contractor",
    "painter", "handyman", "landscaping", "house cleaning", "junk removal",
    "auto repair", "dog grooming", "hair salon", "barber shop", "nail salon",
    "chiropractor", "dentist", "photographer", "real estate agent",
    "insurance agent",
]

# NORMAL (~47): the default -- a solid, balanced set.
CATEGORIES = [
    # trades / contractors
    "plumber", "electrician", "hvac", "roofing", "general contractor",
    "painter", "handyman", "landscaping", "pest control", "flooring",
    # home services
    "house cleaning", "carpet cleaning", "junk removal", "moving company",
    "appliance repair", "garage door repair", "locksmith", "tree service",
    "pressure washing", "pool cleaning",
    # auto
    "auto repair", "auto detailing", "mobile mechanic", "tire shop",
    # pets
    "dog grooming", "pet sitting", "dog training",
    # beauty / personal
    "hair salon", "barber shop", "nail salon", "massage therapist",
    "esthetician", "tattoo shop",
    # health
    "chiropractor", "dentist", "physical therapy",
    # food
    "catering", "bakery", "coffee shop", "food truck",
    # professional / home-based
    "photographer", "bookkeeper", "real estate agent", "insurance agent",
    "tutoring", "home daycare", "notary public",
]

# DEEP (~160): thorough, slow -- normal plus a long tail of niche home/mobile biz.
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
CATEGORIES_DEEP = CATEGORIES + _DEEP_EXTRA


def categories_for(level):
    """Pick a category set: 'core'/'1', 'deep'/'3', else normal/'2'."""
    lv = str(level or "normal").lower()
    if lv.startswith("c") or lv == "1":
        return CATEGORIES_CORE
    if lv.startswith("d") or lv == "3":
        return CATEGORIES_DEEP
    return CATEGORIES

# reuse the don't-call filter (government/civic + national chains)
try:
    from enrich_phones import _is_callable_prospect
except Exception:                       # standalone fallback: keep everything
    def _is_callable_prospect(lead):
        return True

_DOT_COLOR = {"lead": "GREEN", "copper_upgrade": "ORANGE", "customer": "GREY"}

# street-suffix canonicalization so "Westheimer Rd" == "WESTHEIMER ROAD"
_SUFFIX = {
    "ST": "ST", "STREET": "ST", "AVE": "AVE", "AV": "AVE", "AVENUE": "AVE",
    "RD": "RD", "ROAD": "RD", "DR": "DR", "DRIVE": "DR", "LN": "LN",
    "LANE": "LN", "BLVD": "BLVD", "BOULEVARD": "BLVD", "CT": "CT",
    "COURT": "CT", "PL": "PL", "PLACE": "PL", "WAY": "WAY", "CIR": "CIR",
    "CIRCLE": "CIR", "TER": "TER", "TERRACE": "TER", "TRL": "TRL",
    "TRAIL": "TRL", "PKWY": "PKWY", "PARKWAY": "PKWY", "HWY": "HWY",
    "HIGHWAY": "HWY", "SQ": "SQ", "SQUARE": "SQ", "LOOP": "LOOP",
}
# unit markers to strip (everything from here on is a unit, not the street)
_UNIT_RE = re.compile(r"\b(APT|APARTMENT|UNIT|STE|SUITE|#|BLDG|BUILDING|FL|"
                      r"FLOOR|RM|ROOM|OFC|OFFICE|TRLR|LOT|SPC)\b.*$", re.I)
_DIRS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW",
         "NORTH", "SOUTH", "EAST", "WEST"}


# -------------------------------------------------------------------------
# pure address normalization + matching (unit-tested; no IO)
# -------------------------------------------------------------------------
def normalize_address(addr):
    """Reduce an address to a match key 'HOUSE|STREET CORE' so the fiber list
    and the scraped business list line up. Drops unit/apt, city/state/zip, and
    standardizes the street suffix. Returns '' if it isn't a street address."""
    if not addr:
        return ""
    s = addr.upper().strip()
    s = s.split(",")[0]                     # drop ', Houston, TX 77027, USA'
    s = _UNIT_RE.sub("", s)                 # drop unit/apt/suite tail
    s = re.sub(r"[^A-Z0-9 ]", " ", s)       # punctuation -> space
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"^(\d+)\s+(.*)$", s)      # must start with a house number
    if not m:
        return ""
    house, rest = m.group(1), m.group(2).split()
    if not rest:
        return ""
    # canonical suffix if the last token is a known street type
    if rest[-1] in _SUFFIX:
        rest[-1] = _SUFFIX[rest[-1]]
    # drop a leading directional (N/S/E/W) so "3266 LOCKE" == "3266 N LOCKE"? no
    # -- keep directionals, they distinguish streets. Just normalize spelled-out
    rest = ["N" if t == "NORTH" else "S" if t == "SOUTH" else "E" if t == "EAST"
            else "W" if t == "WEST" else t for t in rest]
    return "%s|%s" % (house, " ".join(rest))


def build_business_index(businesses):
    """Map normalized-address -> business dict (first wins). businesses: list of
    dicts with at least 'address'; ideally name/phone/website/category."""
    idx = {}
    for b in businesses:
        key = normalize_address(b.get("address"))
        if key and key not in idx:
            idx[key] = b
    return idx


def split_leads(fiber, biz_index):
    """Classify each fiber lead. Returns (commercial, residential) lists.
    commercial leads get the matched business name/phone merged in."""
    commercial, residential = [], []
    for f in fiber:
        key = normalize_address(f.get("address"))
        b = biz_index.get(key) if key else None
        if b and (b.get("phone") or b.get("name")):
            merged = dict(f)
            merged["name"] = b.get("name")
            merged["phone"] = b.get("phone")
            merged["email"] = b.get("email")
            merged["website"] = b.get("website")
            merged["category"] = b.get("category")
            merged["types"] = [b.get("category")] if b.get("category") else []
            if _is_callable_prospect(merged):
                commercial.append(merged)
            else:
                residential.append(f)   # chain/govt -> not a callable lead
        else:
            residential.append(f)
    return commercial, residential


# -------------------------------------------------------------------------
# IO: queries, businesses CSV, fiber jsonl, sheet
# -------------------------------------------------------------------------
def build_queries(zips, categories=None):
    """'restaurants in 77027' style queries -- one per category per ZIP."""
    cats = categories or CATEGORIES
    return ["%s in %s" % (c, z) for z in zips for c in cats]


def load_businesses_csv(path):
    """Read the gosom/google-maps-scraper CSV. Column names vary a little across
    versions, so match them case-insensitively."""
    rows = []
    with open(path, newline="", encoding="utf-8", errors="ignore") as f:
        for r in csv.DictReader(f):
            low = {(k or "").strip().lower(): (v or "").strip()
                   for k, v in r.items()}
            rows.append({
                "name": low.get("name") or low.get("title") or low.get("business_name"),
                "address": low.get("address") or low.get("full_address")
                           or low.get("formatted_address"),
                "phone": low.get("phone") or low.get("phone_number")
                         or low.get("formatted_phone_number"),
                "email": low.get("email") or low.get("emails") or low.get("email_1"),
                "website": low.get("website") or low.get("site"),
                "category": low.get("category") or low.get("type")
                            or low.get("main_category") or low.get("query"),
            })
    return rows


def load_fiber_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def _dot_color(rec):
    return _DOT_COLOR.get((rec.get("dot_status") or rec.get("status") or "").lower(), "")


def _open_ws(title, header):
    """Open/create a tab in the sheet. Needs google_creds.json on the box."""
    import gspread
    from google.oauth2.service_account import Credentials
    creds = _find_creds()
    if not creds:
        print("No google_creds.json found -> printing only (no sheet write).")
        return None
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    client = gspread.authorize(Credentials.from_service_account_file(creds, scopes=scopes))
    sh = client.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(title)
    except Exception:
        ws = sh.add_worksheet(title=title, rows="20000", cols=str(len(header)))
    if not ws.get_all_values():
        ws.append_row(header)
    return ws


def _find_creds():
    for p in (os.path.join(os.path.expanduser("~"), "optimus", "google_creds.json"),
              os.path.join(os.path.expanduser("~"), "Optimus", "google_creds.json"),
              os.path.join(HERE, "google_creds.json")):
        if os.path.exists(p):
            return p
    return None


def _existing_keys(ws, addr_col=0):
    """Addresses already in a tab (read from column addr_col), so re-runs don't
    duplicate -- the address column isn't always column A."""
    if not ws:
        return set()
    try:
        return set(r[addr_col].strip().upper() for r in ws.get_all_values()[1:]
                   if len(r) > addr_col and r[addr_col].strip())
    except Exception:
        return set()


def write_split(commercial, residential):
    cw = _open_ws(COMMERCIAL_TAB, COMMERCIAL_HEADER)
    rw = _open_ws(RESIDENTIAL_TAB, RESIDENTIAL_HEADER)
    c_seen = _existing_keys(cw, addr_col=3)   # Address is the 4th column now
    r_seen = _existing_keys(rw, addr_col=0)
    # Commercial tab order: Category, Email, Business Name, Address, Phone
    c_rows = [[c.get("category") or "", c.get("email") or "", c.get("name") or "",
               c.get("address"), c.get("phone") or ""]
              for c in commercial
              if (c.get("address") or "").strip().upper() not in c_seen]
    r_rows = [[r.get("address"), _dot_color(r), r.get("zone_label") or "",
               r.get("lat"), r.get("lng")]
              for r in residential
              if (r.get("address") or "").strip().upper() not in r_seen]
    _append(cw, c_rows)
    _append(rw, r_rows)
    return len(c_rows), len(r_rows)


def _append(ws, rows):
    if not rows:
        return
    if ws is None:
        for r in rows[:20]:
            print("   " + " | ".join(str(x) for x in r))
        return
    for i in range(0, len(rows), 500):
        ws.append_rows(rows[i:i + 500], value_input_option="RAW")


# -------------------------------------------------------------------------
# bizmatch: fiber leads x businesses -> green-biz + orange-biz tabs
# -------------------------------------------------------------------------
_SS = [None]


def _spreadsheet():
    """The Google Sheet (cached). Needs google_creds.json on the box."""
    if _SS[0] is not None:
        return _SS[0]
    creds = _find_creds()
    if not creds:
        print("No google_creds.json found -- can't read/write the sheet.")
        return None
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        client = gspread.authorize(Credentials.from_service_account_file(creds, scopes=scopes))
        _SS[0] = client.open_by_key(SHEET_ID)
        return _SS[0]
    except Exception as e:
        print("Could not open the sheet: %s" % str(e)[:90])
        return None


def load_businesses_from_sheet():
    """Scraped businesses from the 'Maps Businesses' tab."""
    sh = _spreadsheet()
    if not sh:
        return []
    try:
        ws = sh.worksheet(MAPS_TAB)
    except Exception:
        print("No '%s' tab -- run the scraper first." % MAPS_TAB)
        return []
    out = []
    for r in ws.get_all_values()[1:]:        # header: Name,Address,Phone,Website,Category
        r = (list(r) + [""] * 5)[:5]
        out.append({"name": r[0], "address": r[1], "phone": r[2],
                    "website": r[3], "category": r[4]})
    return out


def load_fiber_from_sheet():
    """Captured fiber leads from the 'Precise Fiber' tab. Dot Color (col 7) ->
    green = lead, orange = copper_upgrade."""
    sh = _spreadsheet()
    if not sh:
        return []
    try:
        ws = sh.worksheet(PRECISE_TAB)
    except Exception:
        print("No '%s' tab -- run the precise hunter first." % PRECISE_TAB)
        return []
    out = []
    for r in ws.get_all_values()[1:]:        # Address,Status,BAN,Eligible,At,ZIP,DotColor,Zone
        if not r or not r[0].strip():
            continue
        color = (r[6] if len(r) > 6 else "").strip().upper()
        ds = "copper_upgrade" if color == "ORANGE" else "lead"
        out.append({"address": r[0], "dot_status": ds})
    return out


def split_fiber_biz(fiber, biz_index):
    """Fiber leads that match a (callable) business, split by dot color.
    Returns (green_biz, orange_biz)."""
    green_biz, orange_biz = [], []
    for f in fiber:
        key = normalize_address(f.get("address"))
        b = biz_index.get(key) if key else None
        if not (b and (b.get("phone") or b.get("name"))):
            continue
        merged = dict(f)
        merged["name"] = b.get("name")
        merged["phone"] = b.get("phone")
        merged["website"] = b.get("website")
        merged["category"] = b.get("category")
        merged["types"] = [b.get("category")] if b.get("category") else []
        if not _is_callable_prospect(merged):
            continue
        if (f.get("dot_status") or "").lower() == "copper_upgrade":
            orange_biz.append(merged)
        else:
            green_biz.append(merged)
    return green_biz, orange_biz


def _biz_rows(leads):
    return [[c.get("name") or "", c.get("phone") or "", c.get("address") or "",
             c.get("website") or "", c.get("category") or ""] for c in leads]


def _existing_addr_phone(ws, addr_col=2, phone_col=1):
    """One read of a biz tab -> (addresses set, phones set). BIZ_HEADER is
    [Business Name, Phone(1), Address(2), Website, Category]."""
    addrs, phones = set(), set()
    if not ws:
        return addrs, phones
    try:
        for r in ws.get_all_values()[1:]:
            if len(r) > addr_col and r[addr_col].strip():
                addrs.add(r[addr_col].strip().upper())
            if len(r) > phone_col and r[phone_col].strip():
                phones.add(r[phone_col].strip().upper())
    except Exception:
        pass
    return addrs, phones


def _dedup_biz_rows(rows, addr_seen, phone_seen):
    """Skip a biz row if its ADDRESS or its PHONE is already present (in the tab
    or emitted earlier this run) -> one row per phone = dialer-ready. Rows with
    no phone still dedupe by address. Keeps the first of each."""
    out = []
    for row in rows:
        addr = row[2].strip().upper() if len(row) > 2 else ""
        phone = row[1].strip().upper() if len(row) > 1 else ""
        if addr and addr in addr_seen:
            continue
        if phone and phone in phone_seen:
            continue
        out.append(row)
        if addr:
            addr_seen.add(addr)
        if phone:
            phone_seen.add(phone)
    return out


def write_fiber_biz(green_biz, orange_biz):
    gw = _open_ws(FIBER_GREEN_TAB, BIZ_HEADER)
    ow = _open_ws(UPGRADE_ORANGE_TAB, BIZ_HEADER)
    # dedup by ADDRESS and PHONE (was address-only, which let same-phone/
    # different-address-string businesses pile up as duplicates).
    g_addr, g_ph = _existing_addr_phone(gw)
    o_addr, o_ph = _existing_addr_phone(ow)
    g_rows = _dedup_biz_rows(_biz_rows(green_biz), g_addr, g_ph)
    o_rows = _dedup_biz_rows(_biz_rows(orange_biz), o_addr, o_ph)
    _append(gw, g_rows)
    _append(ow, o_rows)
    return len(g_rows), len(o_rows)


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd")

    q = sub.add_parser("make-queries", help="write queries.txt for the scraper")
    q.add_argument("--zips", required=True, help="comma-separated ZIPs, e.g. 77027,77019")
    q.add_argument("--level", default="normal",
                   help="category set: core/1 (~20, quick), normal/2 (~47), deep/3 (~160)")
    q.add_argument("--out", default=os.path.join(HERE, "queries.txt"))

    s = sub.add_parser("split", help="cross-reference businesses vs fiber addresses")
    s.add_argument("--businesses", required=True, help="businesses.csv from the scraper")
    s.add_argument("--fiber", default=FIBER_JSONL, help="captured fiber addresses (jsonl)")

    sub.add_parser("bizmatch", help="match captured fiber leads (Precise Fiber tab) to "
                   "scraped businesses (Maps Businesses tab) -> Fiber Green Biz + "
                   "Upgrade Orange Biz tabs. Reads + writes the sheet.")

    args = ap.parse_args()
    if args.cmd == "make-queries":
        zips = [z.strip() for z in args.zips.split(",") if z.strip()]
        cats = categories_for(args.level)
        qs = build_queries(zips, cats)
        with open(args.out, "w") as f:
            f.write("\n".join(qs) + "\n")
        print("Wrote %d queries (%d categories x %d ZIPs) -> %s"
              % (len(qs), len(cats), len(zips), args.out))
        print("Next: google-maps-scraper -input %s -results businesses.csv -depth 1"
              % args.out)
    elif args.cmd == "split":
        businesses = load_businesses_csv(args.businesses)
        fiber = load_fiber_jsonl(args.fiber)
        idx = build_business_index(businesses)
        commercial, residential = split_leads(fiber, idx)
        print("businesses scraped: %d | fiber addresses: %d" % (len(businesses), len(fiber)))
        print("  -> COMMERCIAL (callable): %d | RESIDENTIAL (door-knock): %d"
              % (len(commercial), len(residential)))
        nc, nr = write_split(commercial, residential)
        print("  wrote +%d commercial, +%d residential (new rows)" % (nc, nr))
    elif args.cmd == "bizmatch":
        businesses = load_businesses_from_sheet()
        fiber = load_fiber_from_sheet()
        idx = build_business_index(businesses)
        green_biz, orange_biz = split_fiber_biz(fiber, idx)
        print("fiber leads: %d | businesses: %d" % (len(fiber), len(businesses)))
        print("  -> GREEN fiber biz: %d | ORANGE upgrade biz: %d"
              % (len(green_biz), len(orange_biz)))
        ng, no = write_fiber_biz(green_biz, orange_biz)
        print("  wrote +%d to '%s', +%d to '%s'"
              % (ng, FIBER_GREEN_TAB, no, UPGRADE_ORANGE_TAB))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
