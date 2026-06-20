#!/usr/bin/env python3
"""
BUSINESS SCORE v1.0 -- rank fiber-eligible businesses so callers work the
"perfect business" first.
=============================================================================
Pure scoring (no network) so it's testable and fast. Input is one enriched
business dict (address already resolved to a business name + phone + type by
MapMan, classified by the legend color, tagged with its zone freshness).
Output is an integer score (higher = call sooner) plus the factor breakdown.

Factors (see DESIGN.md "Perfect business"):
  zone freshness   FRESH > WORKING > MATURE      (just-lit, unworked wins)
  customer status  GREEN > GOLD ; GREY excluded  (non-customer best)
  business type    bandwidth-hungry SMB > marginal
  reachability     landline > wireless > none ; internal-DNC = drop
  freshness to us  not already in GHL / not contacted before
"""

from optimus_dot_detect import STATUS_LEAD, STATUS_COPPER_UPGRADE, STATUS_CUSTOMER

# zone label -> points
ZONE_POINTS = {"FRESH": 40, "WORKING": 20, "MATURE": 5, "EMPTY": 0}

# customer status -> points (GREY/customer is excluded upstream, 0 here)
STATUS_POINTS = {STATUS_LEAD: 30, STATUS_COPPER_UPGRADE: 18, STATUS_CUSTOMER: 0}

# business-type buckets (matched against MapMan's Google "types" + name).
# bandwidth-hungry SMBs that buy business fiber readily score highest.
HIGH_VALUE_TYPES = {
    "doctor", "dentist", "clinic", "medical", "veterinary_care", "physiotherapist",
    "lawyer", "accounting", "insurance_agency", "real_estate_agency", "office",
    "restaurant", "cafe", "bar", "bakery", "meal_takeaway", "store", "retail",
    "beauty_salon", "hair_care", "spa", "gym", "car_repair", "car_dealer",
    "electronics_store", "furniture_store", "hardware_store", "general_contractor",
    "plumber", "electrician", "lodging", "hotel", "pharmacy",
}
LOW_VALUE_TYPES = {
    "atm", "parking", "storage", "laundry", "car_wash", "funeral_home",
    "local_government_office", "post_office", "library", "fire_station",
    "police", "courthouse", "city_hall", "school", "church", "place_of_worship",
}
TYPE_HIGH, TYPE_MID, TYPE_LOW = 20, 10, 2

PHONE_LANDLINE, PHONE_WIRELESS, PHONE_NONE = 10, 5, 0
NEW_TO_US_BONUS = 15


def _type_points(biz_types, name=""):
    toks = set()
    for t in (biz_types or []):
        toks.add(str(t).lower())
    blob = " ".join(toks) + " " + (name or "").lower()
    if any(t in HIGH_VALUE_TYPES for t in toks) or any(w in blob for w in HIGH_VALUE_TYPES):
        return TYPE_HIGH
    if any(t in LOW_VALUE_TYPES for t in toks):
        return TYPE_LOW
    return TYPE_MID


def score_business(biz):
    """biz keys (all optional except as noted):
      zone_label   "FRESH"|"WORKING"|"MATURE"
      status       STATUS_LEAD|STATUS_COPPER_UPGRADE|STATUS_CUSTOMER
      types        list[str]  (Google place types from MapMan)
      name         str
      phone_type   "landline"|"wireless"|None
      on_dnc       bool   (internal DNC -> caller_drop)
      in_ghl       bool   (already a contact/contacted -> no NEW bonus)
      has_phone    bool   (required to be callable)
    Returns dict: {score, callable, drop_reason, factors{...}}.
    """
    # hard drops first
    if biz.get("status") == STATUS_CUSTOMER:
        return {"score": 0, "callable": False, "drop_reason": "already fiber customer", "factors": {}}
    if biz.get("on_dnc"):
        return {"score": 0, "callable": False, "drop_reason": "internal DNC", "factors": {}}
    if not biz.get("has_phone"):
        return {"score": 0, "callable": False, "drop_reason": "no phone", "factors": {}}

    f = {}
    f["zone"] = ZONE_POINTS.get((biz.get("zone_label") or "").upper(), 10)
    f["status"] = STATUS_POINTS.get(biz.get("status"), 10)
    f["type"] = _type_points(biz.get("types"), biz.get("name", ""))
    pt = (biz.get("phone_type") or "").lower()
    f["phone"] = (PHONE_LANDLINE if pt == "landline"
                  else PHONE_WIRELESS if pt == "wireless"
                  else PHONE_NONE)
    f["new"] = 0 if biz.get("in_ghl") else NEW_TO_US_BONUS
    return {"score": sum(f.values()), "callable": True, "drop_reason": None, "factors": f}


def rank_businesses(businesses):
    """Score a list; return callable ones sorted best-first (stable on ties)."""
    scored = []
    for i, b in enumerate(businesses):
        r = score_business(b)
        if r["callable"]:
            scored.append((r["score"], i, b, r))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [{"business": b, **r} for (_s, _i, b, r) in scored]
