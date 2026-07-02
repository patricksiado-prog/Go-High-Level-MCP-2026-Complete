"""
backend_classifier.py  —  Fiber Scout: read dots from the AT&T dealer-map
                          BACKEND JSON instead of sampling pixels.

WHY THIS EXISTS
---------------
The AT&T dealer map (youachieve.att.com) answers every "Search this area"
click with a JSON payload:

    { "success": true,
      "error":   {...},
      "content": [ {lead}, {lead}, ... ] }     # up to ~3000 leads

Each lead carries the ADDRESS + lat/lng + status directly, e.g.:

    {"zip":"77598","address":"558 TRESVANT DR","city":"WEBSTER","state":"TX",
     "latitude":"29.562304","longitude":"-95.144801",
     "subscriber_ban":"", "subscriber_ban_masked":"",
     "curr_ntwrk_bld_type_cd":"unavailable", "speed":"",
     "miles_from_claim":"0.10137", "missing_supl":0}

So the Scout does NOT need to count green/gold/grey pixels (the source of the
GREEN_MIN/GREEN_MAX calibration bug). It can read the truth from this JSON.

THE COLOR KEY (from the dealer-map legend, confirmed on the Third Ward view)
    GREEN  = Fiber eligible / NON-customer   -> THE PRIZE (lit, nobody signed up)
    GOLD   = Fiber eligible / COPPER customer -> upgrade target (on DSL now)
    GREY   = Fiber customer                    -> already sold, skip

TWO SIGNALS WE UNDERSTAND TODAY
    subscriber_ban  ""/empty  = NON-customer     |  present ("BmrSnr!...") = customer
    curr_ntwrk_bld_type_cd    = "unavailable"    = fiber NOT available here (dead)
                              = anything else    = treated as eligible/available

WHAT WE DON'T KNOW YET (the next capture answers it)
    The exact build-type code(s) that separate GOLD (copper customer) from
    GREY (fiber customer). Run inspect() over a GREEN-heavy area (e.g. the
    Arbor/Blodgett Third Ward view) and the cross-tab prints the answer.
    Then drop those codes into FIBER_BUILD_CODES / COPPER_BUILD_CODES below.
"""

import json


# ── CONFIG: fill these in from an inspect() run over a green area ───────────
# Build-type codes (curr_ntwrk_bld_type_cd, lowercased) that mean "not lit".
UNAVAILABLE_CODES = {"", "unavailable", "not_eligible", "none", "n/a"}

# Once a green-area capture reveals them, list the codes that mean an
# existing FIBER subscriber (=> GREY) vs a COPPER/DSL account (=> GOLD).
# Until then they stay empty and customers are reported as "CUSTOMER".
FIBER_BUILD_CODES  = set()   # e.g. {"fiber", "ftth", "available_fiber"}
COPPER_BUILD_CODES = set()   # e.g. {"copper", "ipbb", "dsl"}


# ── CORE CLASSIFIER ────────────────────────────────────────────────────────
def _norm(v):
    return (str(v) if v is not None else "").strip()


def classify_lead(rec):
    """Return one of: GREEN, GOLD, GREY, CUSTOMER, SKIP.

    GREEN     eligible + non-customer          (the prize)
    GOLD      eligible + copper customer        (upgrade)
    GREY      eligible + fiber customer         (sold)
    CUSTOMER  eligible customer, gold/grey not
              yet decodable (codes unknown)     (refine via inspect())
    SKIP      fiber unavailable here            (dead ground)
    """
    bld = _norm(rec.get("curr_ntwrk_bld_type_cd")).lower()
    ban = _norm(rec.get("subscriber_ban"))

    if bld in UNAVAILABLE_CODES:
        return "SKIP"

    if not ban:
        return "GREEN"                      # eligible, no account = PRIZE

    # eligible customer -> gold (copper) or grey (fiber), if we know the codes
    if bld in FIBER_BUILD_CODES:
        return "GREY"
    if bld in COPPER_BUILD_CODES:
        return "GOLD"
    return "CUSTOMER"                        # decode pending an inspect() run


# ── VIEW SUMMARY + FRESH VERDICT ───────────────────────────────────────────
# A "fresh / just-lit" area = lots of green, a few gold, almost no grey.
FRESH_MIN_GREEN   = 8       # need at least this many green dots in the view
FRESH_MAX_GREY_PCT = 15.0   # ...and grey must be under this % of all dots


def summarize(records):
    """Classify a view's leads and return counts + a FRESH/MATURE verdict."""
    counts = {"GREEN": 0, "GOLD": 0, "GREY": 0, "CUSTOMER": 0, "SKIP": 0}
    greens = []
    for rec in records:
        cls = classify_lead(rec)
        counts[cls] += 1
        if cls == "GREEN":
            greens.append(_norm(rec.get("address")))

    green = counts["GREEN"]
    # Until gold/grey are decodable, CUSTOMER counts as "customer" (not grey),
    # so grey% stays conservative (won't falsely fail a fresh view).
    plotted = green + counts["GOLD"] + counts["GREY"] + counts["CUSTOMER"]
    grey_pct = (100.0 * counts["GREY"] / plotted) if plotted else 0.0

    fresh = (green >= FRESH_MIN_GREEN and grey_pct < FRESH_MAX_GREY_PCT)

    return {
        "counts": counts,
        "green": green,
        "gold": counts["GOLD"],
        "grey": counts["GREY"],
        "customer_undecoded": counts["CUSTOMER"],
        "skip": counts["SKIP"],
        "plotted": plotted,
        "grey_pct": round(grey_pct, 1),
        "verdict": "FRESH" if fresh else "MATURE",
        "green_addresses": greens,
    }


# ── DISCOVERY INSPECTOR (run this over a GREEN area) ────────────────────────
def inspect(records):
    """Cross-tab (build_type x ban-present) so we can SEE how the colors
    encode. Returns a printable string; also fine to log to a sheet cell."""
    from collections import Counter

    by_build = Counter()
    by_ban = Counter()
    cross = Counter()
    samples = {}

    for rec in records:
        bld = _norm(rec.get("curr_ntwrk_bld_type_cd")).lower() or "(empty)"
        ban_present = "customer" if _norm(rec.get("subscriber_ban")) else "non-cust"
        by_build[bld] += 1
        by_ban[ban_present] += 1
        key = (bld, ban_present)
        cross[key] += 1
        samples.setdefault(key, _norm(rec.get("address")))

    out = []
    out.append("=== BACKEND INSPECT ===  total leads: %d" % len(records))
    out.append("")
    out.append("curr_ntwrk_bld_type_cd values:")
    for bld, n in by_build.most_common():
        out.append("   %-24s %d" % (bld, n))
    out.append("")
    out.append("subscriber_ban:")
    for k, n in by_ban.most_common():
        out.append("   %-24s %d" % (k, n))
    out.append("")
    out.append("CROSS-TAB  (build_type x ban)  -> sample address:")
    for (bld, ban_present), n in cross.most_common():
        out.append("   %-22s %-9s %5d   e.g. %s"
                    % (bld, ban_present, n, samples[(bld, ban_present)]))
    out.append("")
    out.append("READ IT LIKE THIS:")
    out.append("   non-cust rows on an available build  = GREEN (prize)")
    out.append("   customer rows split into GOLD(copper)/GREY(fiber) by build code")
    out.append("   -> copy the customer build codes into COPPER/FIBER_BUILD_CODES")
    return "\n".join(out)


# ── PAYLOAD HELPERS ────────────────────────────────────────────────────────
def load_leads(payload):
    """Accept the raw JSON envelope, a already-parsed dict, or a bare list;
    return the list of lead records."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("content", []) or []
    return []


# ── CLI: python backend_classifier.py leads.json ───────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python backend_classifier.py <leads.json>")
        raise SystemExit(1)

    with open(sys.argv[1]) as fh:
        records = load_leads(fh.read())

    print(inspect(records))
    print()
    s = summarize(records)
    print("=== VIEW VERDICT ===")
    print("  green=%d gold=%d grey=%d customer(undecoded)=%d skip=%d"
          % (s["green"], s["gold"], s["grey"], s["customer_undecoded"], s["skip"]))
    print("  grey%% of plotted=%.1f  ->  %s" % (s["grey_pct"], s["verdict"]))
    if s["green_addresses"]:
        print("  first green addresses to hunt:")
        for a in s["green_addresses"][:15]:
            print("     " + a)
