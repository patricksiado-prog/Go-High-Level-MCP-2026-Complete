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

IN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "precise_addresses.jsonl")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "enriched_leads.jsonl")
API_BASE = "https://maps.googleapis.com/maps/api/place"
NEARBY_RADIUS_M = 40          # a fiber dot sits on a rooftop; keep it tight
THROTTLE_SECS = 0.05          # be gentle on the API
PLACES_FIELDS = "name,formatted_phone_number,types,business_status,formatted_address"


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
        if lat is not None and lng is not None:
            place = self.by_latlng(lat, lng)
            if place.get("phone"):
                return place
        if rec.get("address"):
            return self.by_text(rec["address"])
        return place if (lat is not None) else {}


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
def run(in_path, out_path, api_key, dry, client=None):
    rows = load_jsonl(in_path)
    print("Read %d captured addresses from %s" % (len(rows), in_path))
    if client is None and not dry:
        client = PlacesClient(api_key)
    seen, enriched = set(), []
    got_phone = 0
    for rec in rows:
        place = client.enrich(rec) if client else {}
        lead = merge_lead(rec, place)
        k = dedupe_key(lead)
        if k in seen:
            continue
        seen.add(k)
        enriched.append(lead)
        if lead.get("phone"):
            got_phone += 1
        if dry:
            print("  %-34s | %s | %s | %s"
                  % ((lead.get("name") or "?")[:34], lead.get("phone") or "(no phone)",
                     lead.get("zone_label") or "-", lead.get("address") or "-"))
        if client:
            time.sleep(THROTTLE_SECS)
    if not dry:
        with open(out_path, "w") as f:
            for lead in enriched:
                f.write(json.dumps(lead) + "\n")
    print("\n%s | %d leads | %d with phone | %d without"
          % ("DRY RUN" if dry else "WROTE " + out_path,
             len(enriched), got_phone, len(enriched) - got_phone))
    return enriched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", default=IN_PATH)
    ap.add_argument("--out", dest="out_path", default=OUT_PATH)
    ap.add_argument("--dry", action="store_true",
                    help="don't call the API or write; just show the plan")
    args = ap.parse_args()
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not args.dry and not key:
        print("ERROR: set GOOGLE_PLACES_API_KEY (the key from Zack's GCP project).")
        sys.exit(1)
    run(args.in_path, args.out_path, key, args.dry)


if __name__ == "__main__":
    main()
