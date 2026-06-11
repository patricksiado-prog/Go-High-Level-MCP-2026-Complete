#!/usr/bin/env python3
"""
OPTIMUS API CAPTURE v1.0 -- read the map's own backend JSON instead of pixels.
=============================================================================
The youachieve fiber map loads its dots from a backend JSON API. Capturing
that response gives the EXACT address + lat/lng + Subscriber BAN for every
dot in the view, with none of the failure modes of the click path:
  - no HiDPI screenshot-px vs click-px drift
  - no overlapping dots opening a NEIGHBOR's popup (the main inaccuracy)
  - no color-threshold tuning at all

Two pieces:

1) ResponseSniffer -- attach to a Playwright page. In PROBE mode it inspects
   every JSON response and reports which URLs contain address/coord/BAN-ish
   data, so you can pick the `address_api_url_substring` once. In CAPTURE
   mode (substring set) it keeps every matching response's parsed features.

2) extract_features(obj) -- schema-tolerant walk of any JSON payload that
   pulls out {address, lat, lng, ban} records. Handles plain dicts, nested
   lists, and GeoJSON ({geometry:{coordinates:[lng,lat]}, properties:{...}}).

This module does NOT log in, does NOT automate any gate, and only listens to
responses the page already loads in Patrick's own session.
"""

import json
import re

# key names seen across map backends; lowercase, punctuation stripped
ADDRESS_KEYS = ("address", "formattedaddress", "fulladdress", "addressline1",
                "streetaddress", "siteaddress", "serviceaddress", "addr")
LAT_KEYS = ("lat", "latitude")
LNG_KEYS = ("lng", "lon", "long", "longitude")
BAN_KEYS = ("ban", "subscriberban", "billingaccountnumber", "billingaccount",
            "accountnumber")
# URLs that are never the dot layer; skipped to keep probe output readable
BORING_URL_BITS = (".js", ".css", ".png", ".jpg", ".svg", ".woff", "google-analytics",
                   "googletagmanager", "doubleclick", "hotjar", "telemetry")

_ADDRESS_SHAPE = re.compile(r"\d+\s+\S+")  # "13911 E CYPRESS ..." -- starts with a house number


def _norm_key(k):
    return re.sub(r"[^a-z]", "", str(k).lower())


def _get_first(d, names):
    for k, v in d.items():
        if _norm_key(k) in names and v not in (None, ""):
            return v
    return None


def _as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _looks_like_address(v):
    return isinstance(v, str) and bool(_ADDRESS_SHAPE.search(v))


def extract_features(obj, out=None):
    """Walk any JSON structure; return a list of
    {"address": str, "lat": float|None, "lng": float|None, "ban": str|None}."""
    if out is None:
        out = []
    if isinstance(obj, list):
        for item in obj:
            extract_features(item, out)
        return out
    if not isinstance(obj, dict):
        return out

    addr = _get_first(obj, ADDRESS_KEYS)
    lat = _as_float(_get_first(obj, LAT_KEYS))
    lng = _as_float(_get_first(obj, LNG_KEYS))
    ban = _get_first(obj, BAN_KEYS)

    # GeoJSON: coordinates are [lng, lat]; attributes live in "properties"
    props = obj.get("properties")
    if isinstance(props, dict):
        addr = addr or _get_first(props, ADDRESS_KEYS)
        ban = ban or _get_first(props, BAN_KEYS)
        if lat is None or lng is None:
            plat = _as_float(_get_first(props, LAT_KEYS))
            plng = _as_float(_get_first(props, LNG_KEYS))
            lat = lat if lat is not None else plat
            lng = lng if lng is not None else plng
    geom = obj.get("geometry")
    if (lat is None or lng is None) and isinstance(geom, dict):
        coords = geom.get("coordinates")
        if (isinstance(coords, list) and len(coords) >= 2
                and _as_float(coords[0]) is not None and _as_float(coords[1]) is not None):
            lng, lat = float(coords[0]), float(coords[1])

    # sanity: lat/lng must be on Earth, and an address must look like one
    if lat is not None and not (-90 <= lat <= 90):
        lat = None
    if lng is not None and not (-180 <= lng <= 180):
        lng = None
    if _looks_like_address(addr):
        out.append({
            "address": re.sub(r"\s+", " ", addr).strip(),
            "lat": lat, "lng": lng,
            "ban": str(ban).strip() if ban not in (None, "") else None,
        })
    else:
        # keep walking nested containers for the real feature objects
        for v in obj.values():
            if isinstance(v, (dict, list)):
                extract_features(v, out)
    return out


class ResponseSniffer:
    """Attach with page.on('response', sniffer.on_response).

    capture_substring=None  -> PROBE mode: record candidate endpoints only.
    capture_substring="..." -> CAPTURE mode: parse + keep matching features.
    """

    MAX_BODY = 8 * 1024 * 1024  # don't json-parse bodies bigger than 8 MB

    def __init__(self, capture_substring=None, verbose=False):
        self.capture_substring = (capture_substring or "").lower() or None
        self.verbose = verbose
        self.features = []          # CAPTURE mode results (deduped by address)
        self._seen_addrs = set()
        self.candidates = {}        # PROBE mode: url -> stats

    def on_response(self, resp):
        try:
            url = resp.url
            low = url.lower()
            if any(b in low for b in BORING_URL_BITS):
                return
            ctype = (resp.headers or {}).get("content-type", "")
            if "json" not in ctype and not low.endswith(".json"):
                return
            body = resp.body()
            if not body or len(body) > self.MAX_BODY:
                return
            data = json.loads(body)
        except Exception:
            return

        if self.capture_substring:
            if self.capture_substring in low:
                self._capture(data, url)
        else:
            self._probe(data, url)

    def _capture(self, data, url):
        feats = extract_features(data)
        new = 0
        for f in feats:
            key = f["address"].upper()
            if key not in self._seen_addrs:
                self._seen_addrs.add(key)
                self.features.append(f)
                new += 1
        if self.verbose and feats:
            print("  [capture] %d features (%d new) from %s" % (len(feats), new, url[:110]))

    def _probe(self, data, url):
        feats = extract_features(data)
        base = url.split("?")[0]
        st = self.candidates.setdefault(base, {"hits": 0, "features": 0,
                                               "with_coords": 0, "with_ban": 0,
                                               "example": url})
        st["hits"] += 1
        st["features"] += len(feats)
        st["with_coords"] += sum(1 for f in feats if f["lat"] is not None and f["lng"] is not None)
        st["with_ban"] += sum(1 for f in feats if f["ban"])
        if feats and self.verbose:
            print("  [probe] %3d addr-features <- %s" % (len(feats), url[:110]))

    def probe_report(self):
        """Print ranked candidate endpoints; returns the best base URL or None."""
        ranked = sorted(self.candidates.items(),
                        key=lambda kv: (kv[1]["features"], kv[1]["with_coords"]),
                        reverse=True)
        print("\n" + "=" * 64)
        print(" PROBE RESULTS -- candidate dot-layer endpoints")
        print("=" * 64)
        hits = [kv for kv in ranked if kv[1]["features"] > 0]
        if not hits:
            print(" No JSON responses contained address-shaped data.")
            print(" Pan/zoom the map and click 'Search this area' while probing,")
            print(" then check again. (The dot layer only loads on that click.)")
            return None
        for base, st in hits[:10]:
            print("  %4d features (%d w/coords, %d w/BAN, %d responses)\n    %s"
                  % (st["features"], st["with_coords"], st["with_ban"], st["hits"], base))
        best = hits[0][0]
        # suggest the last meaningful path segment as the substring
        seg = [s for s in best.split("/") if s][-1]
        print("\n SUGGESTED address_api_url_substring: %r" % seg.lower())
        print(" (any unique lowercase piece of the winning URL works)")
        return best
