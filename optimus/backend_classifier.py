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

THE SIGNAL THAT ACTUALLY WORKS  (corrected 2026-07-01 from a live 77027 capture)
    subscriber_ban  ""/empty  = NON-customer (GREEN lead)  |  present = customer
    curr_ntwrk_bld_type_cd    = the address's CURRENT AT&T network, NOT
                                availability. "unavailable" just means the
                                address has no AT&T service today -- which is
                                what a GREEN eligible non-customer looks like.
    >>> DO NOT treat "unavailable" as dead. A live capture over ZIP 77027 (a
        known green corridor) returned every green address as ban="" +
        curr_ntwrk_bld_type_cd="unavailable". Skipping "unavailable" threw away
        100% of the greens (the GREEN-0 bug). The map only plots eligible /
        customer dots anyway, so every record here is a real dot.

WHAT WE DON'T KNOW YET (a CUSTOMER-area capture answers it)
    Among CUSTOMERS (ban present), which curr_ntwrk_bld_type_cd values mean an
    existing FIBER subscriber (GREY) vs a COPPER customer (GOLD). Run inspect()
    over an area with customers, then drop those codes into
    FIBER_BUILD_CODES / COPPER_BUILD_CODES below. Greens don't need this.
"""

import json


# ── CONFIG: fill these in from a CUSTOMER-area inspect() run ────────────────
# Once a customer-area capture reveals them, list the codes that mean an
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
    CUSTOMER  customer, gold/grey not yet
              decodable (codes unknown)         (refine via inspect())
    SKIP      empty / unusable record           (no address at all)

    Signal: subscriber_ban drives it. Empty ban = non-customer = GREEN.
    curr_ntwrk_bld_type_cd is the address's CURRENT network, NOT availability --
    "unavailable" (no service today) is normal for a green lead, so it is NOT a
    skip. The map only returns eligible/customer dots, so every real record is
    one of GREEN / GOLD / GREY.
    """
    ban = _norm(rec.get("subscriber_ban"))
    bld = _norm(rec.get("curr_ntwrk_bld_type_cd")).lower()

    # Only skip records that carry no address at all (garbage / non-dot rows).
    if not _norm(rec.get("address")):
        return "SKIP"

    if not ban:
        return "GREEN"                      # no account = eligible non-customer = PRIZE

    # customer -> gold (copper) or grey (fiber), once the codes are known
    if bld in FIBER_BUILD_CODES:
        return "GREY"
    if bld in COPPER_BUILD_CODES:
        return "GOLD"
    return "CUSTOMER"                        # has account; copper/fiber decode pending


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


# ── FULL BACKEND ANALYSIS (learn the WHOLE feed, not a sample) ──────────────
def deep_analyze(records, top=15):
    """Comprehensive report over ALL captured records: field fill-rates, the
    distinct values of every status-bearing field, build_type x ban and
    build_type x speed cross-tabs, the full-set classification, and any
    CUSTOMER build codes not yet mapped (so we know what to learn next)."""
    from collections import Counter

    n = len(records)
    out = ["=== FULL BACKEND ANALYSIS ===  records: %d" % n, ""]
    if not n:
        return "\n".join(out + ["(no records captured)"])

    fields = Counter()
    for r in records:
        if isinstance(r, dict):
            for k in r.keys():
                fields[k] += 1
    out.append("FIELDS present (fill rate):")
    for k, c in fields.most_common():
        out.append("   %-28s %d/%d" % (k, c, n))
    out.append("")

    for key in ("curr_ntwrk_bld_type_cd", "subscriber_ban", "speed",
                "missing_supl", "state", "city", "zip"):
        vals = Counter()
        for r in records:
            v = _norm(r.get(key))
            if key == "subscriber_ban":
                v = "customer" if v else "non-cust"
            vals[v or "(empty)"] += 1
        out.append("%s -- distinct values:" % key)
        for v, c in vals.most_common(top):
            out.append("   %-28s %d" % (v[:28], c))
        out.append("")

    cross = Counter(); samp = {}
    for r in records:
        bld = _norm(r.get("curr_ntwrk_bld_type_cd")).lower() or "(empty)"
        ban = "customer" if _norm(r.get("subscriber_ban")) else "non-cust"
        cross[(bld, ban)] += 1
        samp.setdefault((bld, ban), _norm(r.get("address")))
    out.append("CROSS-TAB  build_type x ban  -> sample address:")
    for (bld, ban), c in cross.most_common():
        out.append("   %-22s %-9s %6d   e.g. %s" % (bld, ban, c, samp[(bld, ban)]))
    out.append("")

    sp = Counter()
    for r in records:
        bld = _norm(r.get("curr_ntwrk_bld_type_cd")).lower() or "(empty)"
        speed = _norm(r.get("speed")) or "(none)"
        sp[(bld, speed)] += 1
    out.append("CROSS-TAB  build_type x speed:")
    for (bld, speed), c in sp.most_common(top):
        out.append("   %-22s %-14s %6d" % (bld, speed, c))
    out.append("")

    s = summarize(records)
    out.append("CLASSIFICATION (full set): green=%d gold=%d grey=%d "
               "cust-undecoded=%d skip=%d  grey%%=%.1f  -> %s"
               % (s["green"], s["gold"], s["grey"], s["customer_undecoded"],
                  s["skip"], s["grey_pct"], s["verdict"]))

    unmapped = Counter()
    for r in records:
        if _norm(r.get("subscriber_ban")):
            bld = _norm(r.get("curr_ntwrk_bld_type_cd")).lower()
            if bld and bld not in FIBER_BUILD_CODES and bld not in COPPER_BUILD_CODES:
                unmapped[bld] += 1
    if unmapped:
        out.append("")
        out.append("UNMAPPED CUSTOMER build codes (decide fiber vs copper, add "
                   "to build_codes.json):")
        for bld, c in unmapped.most_common():
            out.append("   %-28s %d customers" % (bld, c))
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
