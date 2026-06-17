#!/usr/bin/env python3
"""
ENRICH PHONES v1.0 -- the missing map->phone bridge.
=============================================================================
The fiber map gives EXACT ADDRESSES but no phone numbers, so a captured lead
can't be called or fed to the dialer. This reads the hunter's output
(precise_addresses.jsonl: address + lat/lng + zone + status) and uses the
GOOGLE PLACES API to attach the BUSINESS NAME and PHONE for each address, then
writes enriched records that business_score.py / ghl_loader.py consume.

WHY GOOGLE PLACES (this is what Zack's Google Cloud billing is for):
 - Places billing runs through a Google Cloud project (enable the
   "Places API", set up a Cloud Billing account, use an API key) -- exactly
   the account Zack is opening.
 - For a known lat/lng we Nearby-Search the closest establishment; for an
   address-only row we Find-Place-From-Text. Place Details then returns the
   business name + formatted phone + types + business_status.

COMPLIANCE (unchanged): enriched leads feed DOOR-KNOCK + DNC-scrubbed MANUAL
CALL routes only. Business phones are NOT cold-texted. Places gives a phone,
not consent.

KEY: set GOOGLE_PLACES_API_KEY in the environment (never hardcode it).

RUN:
    export GOOGLE_PLACES_API_KEY=...        # the key from Zack's GCP project
    python enrich_phones.py --dry           # show what it would attach
    python enrich_phones.py                 # write enriched_leads.jsonl
"""

import os, sys, json, time, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
IN_PATH = os.path.join(HERE, "precise_addresses.jsonl")
OUT_PATH = os.path.join(HERE, "enriched_leads.jsonl")
CACHE_PATH = os.path.join(HERE, "enrich_cache.json")   # never pay twice
API_BASE = "https://maps.googleapis.com/maps/api/place"
NEARBY_RADIUS_M = 40          # a fiber dot sits on a rooftop; keep it tight
THROTTLE_SECS = 0.05          # be gentle on the paid API
PLACES_FIELDS = "name,formatted_phone_number,types,business_status,formatted_address"

# FREE source: OpenStreetMap Overpass (no cost, no key). Coverage is partial
# (US business phones are spotty in OSM) so it's the FIRST pass; paid Places
# only fills the misses, and only when --paid is set.
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_RADIUS_M = 35
OVERPASS_THROTTLE_SECS = 1.1  # public Overpass etiquette: ~1 req/s

# Optional: write enriched leads (name + phone) back into the same Google Sheet
# the hunter writes to, in an "Enriched Leads" tab, so the numbers show up next
# to the captured addresses. Off unless run() gets a sheet_id + creds_file.
ENRICHED_TAB = "Enriched Leads"
ENRICHED_HEADER = ["Address", "Business Name", "Phone", "Phone Source",
                   "Dot Color", "Zone", "Lat", "Lng", "Enriched At"]
_DOT_COLOR = {"lead": "GREEN", "copper_upgrade": "ORANGE", "customer": "GREY"}


def _open_enriched_ws(sheet_id, creds_file):
    """Open (or create) the 'Enriched Leads' tab. Returns a gspread worksheet or
    None. Best-effort: a failure just means we keep writing the jsonl only."""
    if not sheet_id or not creds_file:
        return None
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        client = gspread.authorize(
            Credentials.from_service_account_file(creds_file, scopes=scopes))
        sh = client.open_by_key(sheet_id)
        try:
            ws = sh.worksheet(ENRICHED_TAB)
        except Exception:
            ws = sh.add_worksheet(title=ENRICHED_TAB, rows="5000",
                                  cols=str(len(ENRICHED_HEADER)))
        if not ws.get_all_values():
            ws.append_row(ENRICHED_HEADER)
        print("  enriched leads -> '%s' tab in the sheet" % ENRICHED_TAB)
        return ws
    except Exception as e:
        print("  (enriched-sheet off: %s)" % str(e)[:80])
        return None


# Leads we should NOT cold-call: government/civic/institutional places, and
# national big-box chains (corporate-procured -- not a local AT&T dealer sale).
# Excluded from the callable 'Enriched Leads' tab. Tune freely; matching is
# case-insensitive substring on the business name + place types.
EXCLUDE_TYPES = {
    "local_government_office", "city_hall", "courthouse", "police",
    "fire_station", "post_office", "library", "school", "primary_school",
    "secondary_school", "university", "college", "kindergarten",
    "place_of_worship", "church", "mosque", "synagogue", "hindu_temple",
    "embassy", "hospital", "parking", "atm", "bank", "gas_station", "fuel",
    "department_store", "supermarket", "shopping_mall", "stadium", "airport",
    "transit_station", "train_station", "bus_station", "townhall",
    "public_building", "prison", "government",
}
EXCLUDE_NAME_WORDS = (
    "city of ", " county", "police dep", "fire dep", "fire station",
    "post office", "court house", "courthouse", "city hall", "municipal",
    " dmv", "public library", "school district", "elementary", "middle school",
    "high school", " isd", " university", " college", "department of",
    "us postal", "embassy", "district court", "sheriff", "city council",
    "church", "ministries", "chapel", "mosque", "synagogue",
)
CHAIN_NAMES = {
    "walmart", "wal-mart", "target", "costco", "sam's club", "sams club",
    "home depot", "lowe's", "lowes", "best buy", "apple store", "kroger",
    "h-e-b", "heb", "central market", "whole foods", "trader joe", "cvs",
    "walgreens", "rite aid", "starbucks", "mcdonald", "chick-fil-a", "chickfila",
    "chipotle", "subway", "wendy's", "burger king", "taco bell", "panera",
    "dunkin", "ikea", "macy's", "nordstrom", "dillard", "jcpenney", "jc penney",
    "kohl's", "ross dress", "marshalls", "tj maxx", "t.j. maxx", "homegoods",
    "home goods", "petco", "petsmart", "gamestop", "bank of america",
    "chase bank", "wells fargo", "capital one", "citibank", "us bank", "fedex",
    "ups store", "usps", "autozone", "o'reilly", "advance auto", "dollar general",
    "dollar tree", "family dollar", "7-eleven", "7 eleven", "shell", "exxon",
    "chevron", "circle k", "crate & barrel", "crate and barrel", "j.crew",
    "j crew", "anthropologie", "restoration hardware", "pottery barn",
    "williams sonoma", "west elm", "sephora", "ulta", "bath & body", "verizon",
    "t-mobile", "office depot", "staples", "five below", "aldi", "publix",
    "safeway", "panda express", "olive garden", "chili's", "applebee", "ihop",
    "denny's", "buffalo wild", "raising cane", "whataburger", "jack in the box",
    "sonic drive", "in-n-out", "popeyes", "kfc", "pizza hut", "domino",
    "little caesars", "jimmy john", "jersey mike", "planet fitness", "la fitness",
    "24 hour fitness", "anytime fitness", "great clips", "supercuts",
    "massage envy", "european wax", "hobby lobby", "michaels", "barnes & noble",
    "dick's sporting", "academy sports", "at&t store", "xfinity", "spectrum",
}


def _is_callable_prospect(lead):
    """True if this is a local business we'd actually cold-call for fiber.
    Excludes government/civic/institutional places and national big-box chains."""
    name = (lead.get("name") or "").lower()
    types = [str(t).lower() for t in (lead.get("types") or [])]
    if any(t in EXCLUDE_TYPES for t in types):
        return False
    if any(w in name for w in EXCLUDE_NAME_WORDS):
        return False
    if any(c in name for c in CHAIN_NAMES):
        return False
    return True


def _enriched_row(lead, source):
    """A sheet row for one enriched lead (only the callable fields)."""
    ds = (lead.get("dot_status") or lead.get("status") or "").lower()
    return [lead.get("address") or "", lead.get("name") or "",
            lead.get("phone") or "", source,
            _DOT_COLOR.get(ds, ""), lead.get("zone_label") or "",
            lead.get("lat"), lead.get("lng"),
            time.strftime("%Y-%m-%d %H:%M:%S")]


# ---------------------------------------------------------------------------
# pure helpers (unit-tested; no network)
# ---------------------------------------------------------------------------
def normalize_phone(raw):
    """Digits -> +1XXXXXXXXXX (US). Returns None if not a usable 10/11-digit #."""
    if not raw:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return "+1" + digits


def parse_place_details(result):
    """Pull the fields we care about out of a Places Details 'result' dict."""
    if not result:
        return {}
    return {
        "name": result.get("name"),
        "phone": normalize_phone(result.get("formatted_phone_number")),
        "types": result.get("types") or [],
        "business_status": result.get("business_status"),
    }


def merge_lead(rec, place):
    """Combine a hunter record with Places enrichment into the dict shape
    business_score / ghl_loader expect. Address from the MAP is authoritative
    (it has the unit number); Places supplies name + phone + types."""
    out = dict(rec)
    out["name"] = place.get("name") or rec.get("name")
    out["phone"] = place.get("phone")
    out["has_phone"] = bool(place.get("phone"))
    out["types"] = place.get("types") or []
    out["business_status"] = place.get("business_status")
    # business lines are landlines far more often than not; Places can't tell
    # line type, so mark unknown-but-business rather than guess wireless.
    out["phone_type"] = "business" if place.get("phone") else None
    # map the hunter's dot_status onto the scorer's status vocabulary
    out["status"] = rec.get("dot_status") or rec.get("status")
    return out


def dedupe_key(rec):
    ph = "".join(ch for ch in str(rec.get("phone") or "") if ch.isdigit())
    if len(ph) >= 10:
        return "ph:" + ph[-10:]
    return "ad:" + (rec.get("address") or "").strip().upper()


def cache_key(rec):
    """Stable key for the lookup cache -- coordinates if we have them (a dot is
    a rooftop), else the map address. Lets re-runs cost $0."""
    lat, lng = rec.get("lat"), rec.get("lng")
    if lat is not None and lng is not None:
        return "ll:%.5f,%.5f" % (float(lat), float(lng))
    return "ad:" + (rec.get("address") or "").strip().upper()


def parse_overpass(elements):
    """Pick the best-named element from an Overpass response and pull
    name + phone + types from its OSM tags (free; no key)."""
    best = None
    for el in elements or []:
        tags = el.get("tags") or {}
        if tags.get("name"):
            best = tags
            if tags.get("phone") or tags.get("contact:phone"):
                break   # prefer one that actually has a phone
    if not best:
        return {}
    raw_phone = best.get("phone") or best.get("contact:phone")
    types = []
    for k in ("amenity", "shop", "office", "craft", "healthcare"):
        if best.get(k):
            types.append(best[k])
    return {"name": best.get("name"), "phone": normalize_phone(raw_phone),
            "types": types, "business_status": None}


def load_cache(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(path, cache):
    try:
        with open(path, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        print("   cache write error: %s" % e)


def load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


# ---------------------------------------------------------------------------
# Google Places client (only touched on a real run)
# ---------------------------------------------------------------------------
class PlacesClient:
    def __init__(self, api_key):
        import requests
        self._r = requests
        self.key = api_key

    def _details(self, place_id):
        r = self._r.get("%s/details/json" % API_BASE,
                        params={"place_id": place_id, "fields": PLACES_FIELDS,
                                "key": self.key}, timeout=20)
        r.raise_for_status()
        return parse_place_details(r.json().get("result"))

    def by_latlng(self, lat, lng):
        r = self._r.get("%s/nearbysearch/json" % API_BASE,
                        params={"location": "%s,%s" % (lat, lng),
                                "radius": NEARBY_RADIUS_M, "key": self.key},
                        timeout=20)
        r.raise_for_status()
        results = r.json().get("results") or []
        if not results:
            return {}
        return self._details(results[0]["place_id"])

    def by_text(self, address):
        r = self._r.get("%s/findplacefromtext/json" % API_BASE,
                        params={"input": address, "inputtype": "textquery",
                                "fields": "place_id", "key": self.key},
                        timeout=20)
        r.raise_for_status()
        cands = r.json().get("candidates") or []
        if not cands:
            return {}
        return self._details(cands[0]["place_id"])

    def enrich(self, rec):
        lat, lng = rec.get("lat"), rec.get("lng")
        place = {}
        if lat is not None and lng is not None:
            place = self.by_latlng(lat, lng)
            if place.get("phone"):
                return place
        if rec.get("address"):
            return self.by_text(rec["address"])
        return place


class OverpassClient:
    """FREE business lookup via OpenStreetMap Overpass (no key, no cost).
    Partial coverage, so it's the first pass before paid Places."""
    def __init__(self):
        import requests
        self._r = requests

    def by_latlng(self, lat, lng):
        if lat is None or lng is None:
            return {}
        q = ('[out:json][timeout:20];'
             '(node(around:%d,%s,%s)[name];'
             ' way(around:%d,%s,%s)[name];);'
             'out tags center 8;'
             % (OVERPASS_RADIUS_M, lat, lng, OVERPASS_RADIUS_M, lat, lng))
        try:
            r = self._r.post(OVERPASS_URL, data={"data": q}, timeout=30)
            r.raise_for_status()
            return parse_overpass(r.json().get("elements"))
        except Exception:
            return {}

    def enrich(self, rec):
        return self.by_latlng(rec.get("lat"), rec.get("lng"))


def enrich_one(rec, cache, overpass, places, allow_paid):
    """FREE-FIRST chain for one record, with cache so nothing is paid twice.
    Order: cache -> OSM (free) -> Places (only if --paid and key present).
    Returns (place_dict, source)."""
    ck = cache_key(rec)
    if ck in cache:
        return cache[ck], "cache"
    place, source = {}, "none"
    if overpass is not None:
        place = overpass.enrich(rec) or {}
        if place.get("phone"):
            source = "osm"
    if not place.get("phone") and allow_paid and places is not None:
        paid = places.enrich(rec) or {}
        if paid.get("name") or paid.get("phone"):
            place, source = paid, "places"
    elif place.get("name") and source == "none":
        source = "osm"   # OSM gave a name but no phone
    cache[ck] = place
    return place, source


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
def _process(rows, cache, overpass, places, allow_paid, seen, out_f, dry,
             enriched_ws=None):
    """Enrich a batch of rows free-first; append new leads to out_f. Returns
    (new_count, phone_count, paid_calls)."""
    new = phones = paid = 0
    sheet_rows = []
    for rec in rows:
        place, source = enrich_one(rec, cache, overpass, places, allow_paid)
        if source == "places":
            paid += 1
        lead = merge_lead(rec, place)
        k = dedupe_key(lead)
        if k in seen:
            continue
        seen.add(k)
        new += 1
        if lead.get("phone"):
            phones += 1
        print("  [%s] %-30s | %s | %s | %s"
              % (source, (lead.get("name") or "?")[:30],
                 lead.get("phone") or "(no phone)", lead.get("zone_label") or "-",
                 lead.get("address") or "-"))
        if out_f and not dry:
            out_f.write(json.dumps(lead) + "\n")
            out_f.flush()
        # to the sheet: identified leads (name or phone) we can actually call --
        # skip government/civic + big-box chains.
        if (enriched_ws is not None and not dry
                and (lead.get("phone") or lead.get("name"))
                and _is_callable_prospect(lead)):
            sheet_rows.append(_enriched_row(lead, source))
        if source == "osm":
            time.sleep(OVERPASS_THROTTLE_SECS)   # public Overpass etiquette
        elif source == "places":
            time.sleep(THROTTLE_SECS)
    if enriched_ws is not None and sheet_rows:
        try:    # ONE batched append (don't blow the per-minute write quota)
            for i in range(0, len(sheet_rows), 500):
                enriched_ws.append_rows(sheet_rows[i:i + 500],
                                        value_input_option="RAW")
        except Exception as e:
            print("  (enriched-sheet write error: %s)" % str(e)[:80])
    return new, phones, paid


def run(in_path, out_path, dry, allow_paid=False, api_key=None,
        overpass=None, places=None, watch=False, watch_interval=10.0,
        sheet_id=None, creds_file=None):
    """Free-first enrichment. Default costs $0 (OSM only); paid Places is used
    only when allow_paid is set AND a key is present. --watch tails the input
    so it can run in the background while the hunter is still capturing. When
    sheet_id + creds_file are given, identified leads (name/phone) are also
    written to an 'Enriched Leads' tab in that sheet."""
    cache = load_cache(CACHE_PATH)
    if overpass is None:
        overpass = OverpassClient()
    if places is None and allow_paid and api_key:
        places = PlacesClient(api_key)
    enriched_ws = _open_enriched_ws(sheet_id, creds_file) if not dry else None
    seen = set()
    for lead in load_jsonl(out_path):    # resume: don't re-emit existing leads
        seen.add(dedupe_key(lead))

    mode = "PAID (OSM free-first -> Places on misses)" if allow_paid else "FREE (OSM only, $0)"
    print("Enrichment mode: %s%s" % (mode, " | WATCH" if watch else ""))

    out_f = None if dry else open(out_path, "a")
    total_new = total_phone = total_paid = 0
    offset = 0
    try:
        while True:
            rows = load_jsonl(in_path)
            batch = rows[offset:]
            offset = len(rows)
            if batch:
                n, p, paid = _process(batch, cache, overpass, places,
                                      allow_paid, seen, out_f, dry, enriched_ws)
                total_new += n; total_phone += p; total_paid += paid
                if not dry:
                    save_cache(CACHE_PATH, cache)
            if not watch:
                break
            time.sleep(watch_interval)
    except KeyboardInterrupt:
        print("\n(stopped)")
    finally:
        if out_f:
            out_f.close()

    print("\n%s | %d new leads | %d with phone | %d paid Places calls (~$%.2f)"
          % ("DRY RUN" if dry else "appended -> " + out_path,
             total_new, total_phone, total_paid, total_paid * 0.017))
    return total_new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", default=IN_PATH)
    ap.add_argument("--out", dest="out_path", default=OUT_PATH)
    ap.add_argument("--paid", action="store_true",
                    help="allow paid Google Places on OSM misses (needs "
                         "GOOGLE_PLACES_API_KEY). Default is FREE (OSM only, $0).")
    ap.add_argument("--watch", action="store_true",
                    help="keep running and enrich new addresses as the hunter "
                         "appends them (run in a 2nd terminal; never blocks the scan)")
    ap.add_argument("--watch-interval", type=float, default=10.0)
    ap.add_argument("--dry", action="store_true",
                    help="show the plan; don't write or spend")
    args = ap.parse_args()
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if args.paid and not key:
        print("NOTE: --paid set but no GOOGLE_PLACES_API_KEY -- staying FREE (OSM only).")
        args.paid = False
    run(args.in_path, args.out_path, args.dry, allow_paid=args.paid,
        api_key=key, watch=args.watch, watch_interval=args.watch_interval)


if __name__ == "__main__":
    main()
