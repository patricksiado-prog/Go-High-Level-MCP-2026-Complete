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

# SMB categories worth a fiber call (one Maps search each, per ZIP). Bandwidth-
# hungry local businesses that actually buy business fiber.
CATEGORIES = [
    "restaurants", "cafes", "coffee shops", "bars", "bakeries",
    "hair salons", "barber shops", "nail salons", "spas", "beauty salons",
    "dentists", "doctors", "medical clinics", "chiropractors", "veterinarians",
    "law firms", "accountants", "insurance agencies", "real estate agencies",
    "auto repair", "car dealerships", "tire shops", "gyms", "fitness studios",
    "retail stores", "boutiques", "furniture stores", "hardware stores",
    "florists", "pet stores", "dry cleaners", "print shops", "tattoo shops",
    "daycares", "physical therapy", "dental labs", "marketing agencies",
    "contractors", "plumbers", "electricians", "hvac", "roofing companies",
]

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
# CLI
# -------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd")

    q = sub.add_parser("make-queries", help="write queries.txt for the scraper")
    q.add_argument("--zips", required=True, help="comma-separated ZIPs, e.g. 77027,77019")
    q.add_argument("--out", default=os.path.join(HERE, "queries.txt"))

    s = sub.add_parser("split", help="cross-reference businesses vs fiber addresses")
    s.add_argument("--businesses", required=True, help="businesses.csv from the scraper")
    s.add_argument("--fiber", default=FIBER_JSONL, help="captured fiber addresses (jsonl)")

    args = ap.parse_args()
    if args.cmd == "make-queries":
        zips = [z.strip() for z in args.zips.split(",") if z.strip()]
        qs = build_queries(zips)
        with open(args.out, "w") as f:
            f.write("\n".join(qs) + "\n")
        print("Wrote %d queries (%d categories x %d ZIPs) -> %s"
              % (len(qs), len(CATEGORIES), len(zips), args.out))
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
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
