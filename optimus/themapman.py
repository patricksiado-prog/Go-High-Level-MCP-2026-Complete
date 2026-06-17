#!/usr/bin/env python3
"""
THE MAP MAN v11.2.5 (in-repo copy) -- address -> business name + phone enrich.
=============================================================================
This is the ENRICHMENT stage of the Optimus pipeline (DESIGN.md stage 3): it
turns an exact fiber-eligible ADDRESS (from the map scanners) into a callable
BUSINESS -- tenant name + phone + type -- using Google Places (text search ->
nearby -> details), nearest operational commercial tenant within 150 m, with
national chains / non-businesses dropped (BLOCKED_NAMES). Originally run
standalone on Pydroid/HP against a Google Sheet; this in-repo copy keeps that
exact behavior AND exposes the pure resolver so `weekly_run.py` can enrich
in-process (closing the MapMan hand-off gap) instead of only via the Sheet.

CHANGES vs the standalone original (behavior-preserving):
  - The Google Maps API key is NO LONGER hardcoded. It is read from the
    GOOGLE_MAPS_API_KEY environment variable. (The old embedded key was on a
    public repo == exposed; rotate + restrict it in GCP.)
  - Package bootstrap, credential check, and the Sheet run now live under
    main()/__main__, so importing this module for resolve()/enrich_leads()
    does NOT pip-install, touch the network, or need creds. Heavy deps
    (requests, gspread) import lazily inside the functions that use them.

RUN STANDALONE (unchanged for the operator; on Pydroid/HP):
    export GOOGLE_MAPS_API_KEY=...        # was hardcoded; now from env
    python themapman.py                   # enrich IN_TAB -> OUT_TAB on the Sheet

USE FROM THE PIPELINE (in-process, no Sheet round-trip):
    from themapman import enrich_leads
    businesses = enrich_leads(scanner_leads)   # -> dicts for business_score

COMPLIANCE: enrichment only. Output (name+phone+address) feeds DNC-scrubbed,
human-in-the-loop power-dialer CALLS / door-knock -- never a cold text.
=============================================================================
"""

import os, re, math, time
from datetime import datetime, timezone

VERSION = "11.2.5"

# secret: provide via env, never commit. (The old embedded key was public -> rotate.)
API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
SHEET_ID = os.environ.get("OPTIMUS_SHEET_ID", "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA")
IN_TAB = os.environ.get("MAPMAN_IN_TAB", "Hunter Green Commercial")
OUT_TAB = os.environ.get("MAPMAN_OUT_TAB", "Fiber Commercial Leads")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
RADII = [30, 60, 100, 200, 500]
MAX_M = 150
EARTH_M = 6371000


# -------------------------------------------------------------------------
# pure helpers (no network -- unit-tested)
# -------------------------------------------------------------------------
def haversine(lat1, lng1, lat2, lng2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return EARTH_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


BLOCKED_NAMES = {
    "walmart", "target", "costco", "sam's club", "kroger", "heb", "aldi",
    "dollar general", "family dollar", "dollar tree", "big lots",
    "mcdonald's", "burger king", "wendy's", "jack in the box", "taco bell",
    "kfc", "popeyes", "chick-fil-a", "sonic", "arbys", "dairy queen",
    "subway", "jimmy john's", "jersey mike's", "firehouse subs",
    "starbucks", "dunkin", "dunkin donuts",
    "usps", "post office", "dmv", "irs", "courthouse", "city hall",
    "police", "fire station", "library", "school", "elementary", "middle school",
    "high school", "university", "college", "hospital", "clinic", "medical center",
    "bank of america", "chase", "wells fargo", "citibank", "pnc", "regions",
    "shell", "exxon", "chevron", "bp", "mobil", "valero", "circle k",
    "7-eleven", "speedway", "quiktrip", "racetrac",
    "home depot", "lowe's", "menards", "ace hardware",
    "best buy", "circuit city",
    "autozone", "o'reilly", "advance auto parts", "napa",
    "cvs", "walgreens", "rite aid", "duane reade",
    "t-mobile", "verizon", "at&t", "sprint", "cricket",
    "ihop", "denny's", "cracker barrel", "applebee's", "chili's",
    "tgi fridays", "red lobster", "olive garden", "longhorn",
    "buffalo wild wings", "hooters", "outback",
    "marriott", "hilton", "hampton", "holiday inn", "best western",
    "la quinta", "motel 6", "super 8", "comfort inn", "quality inn",
    "fedex", "ups", "usps", "amazon", "whole foods", "trader joe's",
}


def is_blocked(name):
    if not name:
        return False
    n = name.lower()
    return any(blocked in n for blocked in BLOCKED_NAMES)


COMM_TYPES = {
    "store", "restaurant", "food", "cafe", "health", "doctor", "dentist",
    "pharmacy", "gym", "spa", "beauty_salon", "hair_care", "lodging",
    "finance", "insurance_agency", "lawyer", "real_estate_agency",
    "travel_agency", "accounting", "bank", "car_repair", "car_dealer",
    "gas_station", "shopping_mall", "clothing_store", "electronics_store",
    "furniture_store", "hardware_store", "home_goods_store",
    "jewelry_store", "shoe_store", "supermarket", "grocery_or_supermarket",
    "convenience_store", "liquor_store", "bakery", "meal_delivery",
    "meal_takeaway", "night_club", "bar", "bowling_alley", "casino",
    "movie_theater", "amusement_park", "aquarium", "art_gallery", "museum",
    "zoo", "book_store", "veterinary_care", "physiotherapist",
    "plumber", "electrician", "roofing_contractor", "general_contractor",
    "painter", "locksmith", "moving_company", "storage", "laundry",
    "car_wash", "funeral_home", "office", "establishment",
    "point_of_interest", "local_government_office", "post_office",
    "library", "fire_station", "police", "hospital", "courthouse",
    "city_hall", "parking",
}


def is_commercial(types):
    return any(t in COMM_TYPES for t in (types or []))


def has_phone(phone):
    return bool(phone) and len(re.sub(r"\D", "", phone)) >= 7


# -------------------------------------------------------------------------
# Google Places calls (network -- api_key defaults to env API_KEY)
# -------------------------------------------------------------------------
def _key(api_key):
    k = api_key or API_KEY
    if not k:
        raise RuntimeError("GOOGLE_MAPS_API_KEY not set (env) and no api_key passed")
    return k


def geocode(address, api_key=None):
    import requests
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": address, "key": _key(api_key)}
    try:
        data = requests.get(url, params=params, timeout=60).json()
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return {"lat": loc["lat"], "lng": loc["lng"]}
    except Exception as e:
        print("  Geocode error: %s" % e)
    return None


def nearby(lat, lng, radius, api_key=None):
    import requests
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {"location": "%s,%s" % (lat, lng), "radius": radius, "key": _key(api_key)}
    try:
        data = requests.get(url, params=params, timeout=60).json()
        if data.get("status") == "OK":
            return [{
                "place_id": p.get("place_id"),
                "name": p.get("name"),
                "types": p.get("types", []),
                "status": p.get("business_status", "UNKNOWN"),
                "lat": p["geometry"]["location"]["lat"],
                "lng": p["geometry"]["location"]["lng"],
            } for p in data.get("results", [])]
    except Exception as e:
        print("  Nearby error: %s" % e)
    return []


def place_details(place_id, api_key=None):
    import requests
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_phone_number,formatted_address,website,types,business_status",
        "key": _key(api_key),
    }
    try:
        data = requests.get(url, params=params, timeout=60).json()
        if data.get("status") == "OK":
            rr = data.get("result", {})
            return {
                "name": rr.get("name"),
                "phone": rr.get("formatted_phone_number"),
                "address": rr.get("formatted_address"),
                "website": rr.get("website"),
                "types": rr.get("types", []),
            }
    except Exception as e:
        print("  Details error: %s" % e)
    return None


def resolve(address, fiber_lat=None, fiber_lng=None, want_state=None, api_key=None):
    """Address -> nearest operational commercial tenant (with phone) within
    MAX_M. Uses provided lat/lng if present (skips geocoding), else geocodes."""
    result = {
        "input": address, "source": None, "radius": None,
        "distance_m": None, "place_id": None, "status": None,
        "name": None, "phone": None, "address": None,
        "website": None, "types": None,
        "fiber_lat": None, "fiber_lng": None, "error": None
    }

    def _ff(x):
        try:
            return float(str(x).strip())
        except Exception:
            return None

    _flat, _flng = _ff(fiber_lat), _ff(fiber_lng)
    geo = {"lat": _flat, "lng": _flng} if (_flat is not None and _flng is not None) else geocode(address, api_key)
    if not geo:
        result["status"] = "GEOCODE_FAILED"
        result["error"] = "Could not geocode"
        return result
    result["fiber_lat"] = geo["lat"]
    result["fiber_lng"] = geo["lng"]
    for radius in RADII:
        cands = nearby(geo["lat"], geo["lng"], radius, api_key)
        filtered = [c for c in cands
                    if c.get("status") == "OPERATIONAL"
                    and c.get("place_id")
                    and is_commercial(c.get("types", []))
                    and not is_blocked(c.get("name", ""))]
        if not filtered:
            continue
        for c in filtered:
            c["distance_m"] = haversine(geo["lat"], geo["lng"], c["lat"], c["lng"])
        filtered.sort(key=lambda x: x["distance_m"])
        best = filtered[0]
        if best["distance_m"] > MAX_M:
            continue
        det = place_details(best["place_id"], api_key)
        if not det or not has_phone(det.get("phone")):
            continue
        if is_blocked(det.get("name", "")):
            continue
        result.update({
            "source": "Tenant resolver",
            "radius": radius,
            "distance_m": round(best["distance_m"], 1),
            "place_id": best["place_id"],
            "status": "RESOLVED",
            "name": det["name"],
            "phone": det["phone"],
            "address": det["address"],
            "website": det["website"],
            "types": ", ".join(det.get("types", []))
        })
        return result
    result["status"] = "NO_TENANT_FOUND"
    result["error"] = "No valid tenant with phone"
    return result


# -------------------------------------------------------------------------
# pipeline bridge: scanner leads -> enriched business dicts (for business_score)
# -------------------------------------------------------------------------
def lead_to_business(lead, resolved):
    """Shape one MapMan `resolve()` result + its source lead into the business
    dict that business_score.score_business / ghl_loader consume."""
    types = [t.strip() for t in (resolved.get("types") or "").split(",") if t.strip()]
    phone = resolved.get("phone")
    return {
        "name": resolved.get("name"),
        "phone": phone,
        "address": resolved.get("address") or lead.get("address"),
        "state": lead.get("state"),
        "zip": lead.get("zip"),
        "lat": resolved.get("fiber_lat") if resolved.get("fiber_lat") is not None else lead.get("lat"),
        "lng": resolved.get("fiber_lng") if resolved.get("fiber_lng") is not None else lead.get("lng"),
        "zone_label": lead.get("zone_label"),
        "status": lead.get("status"),
        "types": types,
        "has_phone": has_phone(phone),
        "phone_type": lead.get("phone_type"),     # MapMan doesn't classify line type
        "resolver_status": resolved.get("status"),
    }


def enrich_leads(leads, api_key=None, sleep=0.0):
    """Resolve a list of scanner leads (each {address, lat?, lng?, status?,
    zone_label?, state?}) into enriched business dicts via Google Places.
    Network/billed per address -- run on the HP with GOOGLE_MAPS_API_KEY set."""
    out = []
    for lead in leads:
        r = resolve(lead.get("address"), lead.get("lat"), lead.get("lng"),
                    lead.get("state"), api_key=api_key)
        out.append(lead_to_business(lead, r))
        if sleep:
            time.sleep(sleep)
    return out


# -------------------------------------------------------------------------
# Google-Sheet I/O + standalone run (unchanged behavior; under main())
# -------------------------------------------------------------------------
def read_input(client, sheet_id, tab):
    ws = client.open_by_key(sheet_id).worksheet(tab)
    out = []
    for row in ws.get_all_records():
        addr = (row.get("Address") or row.get("address") or
                row.get("Street Address") or row.get("Full Address") or row.get("Location"))
        if addr and str(addr).strip():
            out.append({"address": str(addr).strip(),
                        "lat": row.get("Lat") or row.get("lat"),
                        "lng": row.get("Lng") or row.get("lng"),
                        "state": (row.get("State") or row.get("state") or "")})
    return out


def get_already_done(client, sheet_id, tab):
    import gspread
    try:
        ws = client.open_by_key(sheet_id).worksheet(tab)
        rows = ws.get_all_values()
        if len(rows) <= 1:
            return set()
        return set(row[0].strip() for row in rows[1:] if row and row[0].strip())
    except gspread.WorksheetNotFound:
        return set()


def init_out(ws):
    headers = [
        "Input Address", "Source", "Resolver Radius", "Resolver Distance Meters",
        "Place ID", "Resolver Status", "Tenant Name", "Tenant Phone",
        "Tenant Address", "Tenant Website", "Tenant Types",
        "Fiber Lat", "Fiber Lng", "Processed At", "Error"
    ]
    if not ws.get_all_values():
        ws.append_row(headers)
    return headers


def write_result(ws, result, max_retries=3):
    row = [
        result.get("input", ""), result.get("source", ""),
        result.get("radius", ""), result.get("distance_m", ""),
        result.get("place_id", ""), result.get("status", ""),
        result.get("name", ""), result.get("phone", ""),
        result.get("address", ""), result.get("website", ""),
        result.get("types", ""), result.get("fiber_lat", ""),
        result.get("fiber_lng", ""),
        datetime.now(timezone.utc).isoformat(),
        result.get("error", "")
    ]
    for attempt in range(max_retries):
        try:
            ws.append_row(row)
            return True
        except Exception as e:
            print("  Write error (attempt %d/%d): %s" % (attempt + 1, max_retries, e))
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print("  FAILED to write after %d attempts" % max_retries)
                return False
    return False


def _find_creds():
    for p in ["google_creds.json", "/storage/emulated/0/Download/google_creds.json",
              "/storage/emulated/0/google_creds.json"]:
        if os.path.exists(p):
            return p
    return None


def main():
    import subprocess, sys
    print("Checking packages...")
    for pkg in ["gspread", "google-auth", "requests"]:
        try:
            __import__(pkg.replace("-", "_"))
        except Exception:
            print("  Installing %s..." % pkg)
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

    import gspread
    from google.oauth2.service_account import Credentials

    if not API_KEY:
        print("ERROR: set GOOGLE_MAPS_API_KEY in the environment (key is no longer embedded).")
        sys.exit(1)
    creds_file = _find_creds()
    if not creds_file:
        print("ERROR: google_creds.json not found. Put it in /Download or same folder.")
        sys.exit(1)

    print("\n" + "=" * 55)
    print("  THE MAP MAN v%s - API Resolver (pulls phones)" % VERSION)
    print("=" * 55)
    print("Connecting to Google Sheets...")
    client = gspread.authorize(Credentials.from_service_account_file(creds_file, scopes=SCOPES))

    already_done = get_already_done(client, SHEET_ID, OUT_TAB)
    print("Found %d already processed. Will skip them." % len(already_done))
    addresses = read_input(client, SHEET_ID, IN_TAB)
    print("Loaded %d total addresses from '%s'" % (len(addresses), IN_TAB))
    to_process = [a for a in addresses if a["address"] not in already_done]
    print("New addresses to process: %d" % len(to_process))
    if not to_process:
        print("Nothing new to process. All done!")
        return

    try:
        out_ws = client.open_by_key(SHEET_ID).worksheet(OUT_TAB)
    except gspread.WorksheetNotFound:
        out_ws = client.open_by_key(SHEET_ID).add_worksheet(title=OUT_TAB, rows="1000", cols="20")
    init_out(out_ws)

    for i, item in enumerate(to_process, 1):
        addr = item["address"]
        print("\n[%d/%d] %s" % (i, len(to_process), addr))
        result = resolve(addr, item.get("lat"), item.get("lng"), item.get("state"))
        if write_result(out_ws, result):
            print("  -> %s | Name: %s | Phone: %s | Distance: %sm" % (
                result["status"], result.get("name") or "N/A",
                result.get("phone") or "N/A", result.get("distance_m") or "N/A"))
        else:
            print("  -> WRITE FAILED for %s" % addr)
        time.sleep(0.2)

    print("\nDone! Results in '%s' tab." % OUT_TAB)


if __name__ == "__main__":
    main()
