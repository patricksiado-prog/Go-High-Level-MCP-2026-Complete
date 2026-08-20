"""
verify_gold_capture.py -- audit gold/grey classification against a REAL AT&T
serviceability response, and show what the pre-2026-08-20 code got wrong.

WHY
    The unit tests prove the logic on records we wrote ourselves. This proves it
    on records AT&T actually sent. The hunter already saves one response per run
    as serviceability_raw.json, so the data is sitting next to this script.

RUN
    python verify_gold_capture.py                     # uses serviceability_raw.json
    python verify_gold_capture.py <path-to-json>      # or point it at any capture

WHAT IT TELLS YOU
    * the GREEN / GOLD / GREY split the fixed classifier produces
    * how many dots the OLD code called GOLD that are really GREY
      (existing fiber customers -- worthless to call, and the bug Patrick
      caught by clicking a "gold" dot on the map)
    * every build code AT&T sent that we cannot decode, with counts. Any code
      appearing in volume is worth confirming: if it turns out to be copper it
      is real gold we are currently discarding as grey. Add confirmed codes to
      build_codes.json.
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from backend_classifier import (classify_lead, FIBER_BUILD_CODES,
                                COPPER_BUILD_CODES)


def old_classify(rec):
    """The pre-fix rule, reproduced exactly, so the delta is measurable.

    Old order: the word "copper" anywhere in the status text won BEFORE AT&T's
    own curr_ntwrk_bld_type_cd was consulted -- and an undecodable customer fell
    through into that same word-match instead of defaulting to grey.
    """
    ban = str(rec.get("subscriber_ban") or "").strip()
    bld = str(rec.get("curr_ntwrk_bld_type_cd") or "").strip().lower()
    txt = str(rec.get("status") or "").lower()
    if "copper" in txt:
        return "GOLD"
    if ban and bld:
        if bld in COPPER_BUILD_CODES:
            return "GOLD"
        if bld in FIBER_BUILD_CODES:
            return "GREY"
    if "non-customer" in txt or "noncustomer" in txt or "eligible" in txt:
        return "GREEN"
    if "customer" in txt or "subscriber" in txt:
        return "GREY"
    return "GREY" if ban else "GREEN"


def walk(obj, out):
    """Pull every record carrying an address out of an arbitrary payload."""
    if isinstance(obj, list):
        for x in obj:
            walk(x, out)
    elif isinstance(obj, dict):
        if obj.get("address"):
            out.append(obj)
        else:
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    walk(v, out)
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        HERE, "serviceability_raw.json")
    if not os.path.exists(path):
        print("No capture found at %s" % path)
        print("Run the hunter once -- it writes serviceability_raw.json beside itself.")
        return 1

    with open(path) as f:
        recs = walk(json.load(f), [])
    if not recs:
        print("No address-bearing records in %s" % path)
        return 1

    now, was, unknown, flipped = Counter(), Counter(), Counter(), []
    for r in recs:
        n = classify_lead(r)
        n = "GREY" if n == "CUSTOMER" else n
        o = old_classify(r)
        now[n] += 1
        was[o] += 1
        if o == "GOLD" and n != "GOLD":
            flipped.append(r)
        if classify_lead(r) == "CUSTOMER":
            unknown[str(r.get("curr_ntwrk_bld_type_cd") or "(blank)").lower()] += 1

    print("\nAT&T capture: %s" % os.path.basename(path))
    print("records with an address: %d\n" % len(recs))
    print("%-8s %10s %10s" % ("COLOR", "BEFORE", "AFTER"))
    print("-" * 30)
    for c in ("GREEN", "GOLD", "GREY"):
        print("%-8s %10d %10d" % (c, was[c], now[c]))

    print("\nFALSE GOLD (called gold before, actually grey): %d" % len(flipped))
    if flipped:
        pct = 100.0 * len(flipped) / max(1, was["GOLD"])
        print("  -> %.1f%% of the old gold list was existing fiber customers" % pct)
        for r in flipped[:10]:
            print("     %-34s ban=%-9s build=%-12s %s" % (
                str(r.get("address"))[:34],
                "yes" if r.get("subscriber_ban") else "no",
                str(r.get("curr_ntwrk_bld_type_cd"))[:12],
                str(r.get("status") or "")[:34]))
        if len(flipped) > 10:
            print("     ... and %d more" % (len(flipped) - 10))

    if unknown:
        print("\nUNDECODABLE build codes (currently defaulting to GREY):")
        for code, n in unknown.most_common():
            print("     %-16s %5d dots" % (code, n))
        print("  If any of these is really copper, that is gold we are throwing")
        print("  away. Confirm on the map, then add it to build_codes.json.")
    else:
        print("\nEvery build code in this capture decoded cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
