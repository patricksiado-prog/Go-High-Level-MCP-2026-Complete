"""
test_backend_classifier.py — prove the backend logic on real + synthetic data.

Run:  python test_backend_classifier.py

WEBSTER sample = the actual records the Scout captured (build "unavailable")
                 -> should score MATURE (0 green, dead ground).
GREEN sample   = a synthetic Third-Ward-style view (eligible + non-customers)
                 -> should score FRESH and list the green addresses.
"""

import backend_classifier as bc


# Real records the Scout captured (Backend Capture tab, Webster 77598).
WEBSTER = [
    {"zip": "77598", "address": "558 TRESVANT DR", "city": "WEBSTER", "state": "TX",
     "latitude": "29.562304", "longitude": "-95.144801",
     "subscriber_ban": "", "curr_ntwrk_bld_type_cd": "unavailable", "speed": ""},
    {"zip": "77598", "address": "554 TRESVANT DR", "city": "WEBSTER", "state": "TX",
     "latitude": "29.5622", "longitude": "-95.144968",
     "subscriber_ban": "BmrSnr!7D80C09CBA9D8412EAD9DE39FC5999FF",
     "curr_ntwrk_bld_type_cd": "unavailable", "speed": ""},
    {"zip": "77598", "address": "15339 SILVERMAN ST", "city": "WEBSTER", "state": "TX",
     "latitude": "29.562603", "longitude": "-95.145159",
     "subscriber_ban": "BmrSnr!502350536BB823C17A0D021B0F19F9FB",
     "curr_ntwrk_bld_type_cd": "unavailable", "speed": ""},
    {"zip": "77598", "address": "15335 SILVERMAN ST", "city": "WEBSTER", "state": "TX",
     "latitude": "29.562727", "longitude": "-95.145309",
     "subscriber_ban": "", "curr_ntwrk_bld_type_cd": "unavailable", "speed": ""},
]

# Synthetic "fresh" view in the shape we expect over Third Ward (77004).
# NOTE: build code here is a GUESS ("fiber"/"copper") purely to exercise the
# code paths — the real codes come from your first inspect() run over green.
GREEN_VIEW = (
    [{"zip": "77004", "address": "%d ARBOR ST" % n, "city": "HOUSTON", "state": "TX",
      "subscriber_ban": "", "curr_ntwrk_bld_type_cd": "fiber"} for n in range(2700, 2712)]
    + [{"zip": "77004", "address": "%d BLODGETT ST" % n, "city": "HOUSTON", "state": "TX",
        "subscriber_ban": "BmrSnr!AAA%d" % n, "curr_ntwrk_bld_type_cd": "copper"}
       for n in range(2800, 2803)]
    + [{"zip": "77004", "address": "%d ENNIS ST" % n, "city": "HOUSTON", "state": "TX",
        "subscriber_ban": "BmrSnr!BBB%d" % n, "curr_ntwrk_bld_type_cd": "fiber"}
       for n in range(2900, 2901)]
)


def show(name, records):
    print("\n" + "#" * 66)
    print("# " + name)
    print("#" * 66)
    print(bc.inspect(records))
    s = bc.summarize(records)
    print("\nVERDICT: %s  (green=%d gold=%d grey=%d undecoded-cust=%d skip=%d, grey%%=%.1f)"
          % (s["verdict"], s["green"], s["gold"], s["grey"],
             s["customer_undecoded"], s["skip"], s["grey_pct"]))
    if s["green_addresses"]:
        print("GREEN ADDRESSES:", ", ".join(s["green_addresses"][:10]))


if __name__ == "__main__":
    # Webster with codes unknown -> everything SKIP (unavailable) -> MATURE.
    show("WEBSTER 77598  (real capture, unavailable = dead)", WEBSTER)

    # Green view with codes still empty -> customers show as 'undecoded'.
    show("THIRD WARD 77004  (codes NOT yet configured)", GREEN_VIEW)

    # Now pretend an inspect() run taught us the codes, and re-score:
    bc.FIBER_BUILD_CODES = {"fiber"}
    bc.COPPER_BUILD_CODES = {"copper"}
    show("THIRD WARD 77004  (after codes configured -> gold/grey split)", GREEN_VIEW)
