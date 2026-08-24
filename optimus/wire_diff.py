"""wire_diff.py -- answer "what does AT&T send differently for GOLD vs GREY?"

Reads optimus/_feed/wire_audit.jsonl (one line per captured backend record,
written by the hunter) and prints a field-by-field comparison:

    FIELD                     GREEN          GOLD           GREY
    subscriber_ban            empty          present        present
    curr_ntwrk_bld_type_cd    unavailable    fttn-bp        fttp-gpon
    speed                     (empty)        768K           1G

The last column that DIFFERS between GOLD and GREY is the rule. Everything else
is noise. This exists because that question has been argued from theory all day
while the answer sits in the payload nobody had captured.

RUN:
    py wire_diff.py                      # reads ./_feed/wire_audit.jsonl or ~/optimus_hunter
    py wire_diff.py path/to/audit.jsonl
"""
import json
import os
import sys

# Colour vocabularies differ across the codebase; normalise once.
CANON = {"GREEN": "GREEN", "LEAD": "GREEN",
         "ORANGE": "GOLD", "GOLD": "GOLD", "COPPER_UPGRADE": "GOLD",
         "GREY": "GREY", "GRAY": "GREY", "CUSTOMER": "GREY",
         "UNKNOWN": "UNKNOWN", "UNKNOWN_CUSTOMER": "UNKNOWN"}
ORDER = ["GREEN", "GOLD", "GREY", "UNKNOWN"]


def find_audit():
    home = os.path.expanduser("~")
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        here = os.getcwd()
    for d in (here, os.path.join(here, "_feed"),
              os.path.join(home, "optimus_hunter"),
              os.path.join(home, "optimus_hunter", "_feed"), os.getcwd()):
        p = os.path.join(d, "wire_audit.jsonl")
        if os.path.exists(p):
            return p
    return None


def summarise(values):
    """One cell of the table: what this colour tends to carry for this field."""
    vals = ["(empty)" if v in (None, "", False) else
            ("present" if v is True else str(v)) for v in values]
    uniq = {}
    for v in vals:
        uniq[v] = uniq.get(v, 0) + 1
    if len(uniq) == 1:
        return list(uniq)[0][:22]
    top = sorted(uniq.items(), key=lambda kv: -kv[1])
    return "%s(%d) +%d more" % (top[0][0][:14], top[0][1], len(top) - 1)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else find_audit()
    if not path or not os.path.exists(path):
        print("No wire_audit.jsonl found.")
        print("Run the hunter once on a view with GREEN, GOLD and GREY dots --")
        print("it writes one line per record, then this reads them.")
        return 1

    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    if not rows:
        print("%s is empty." % path)
        return 1

    by = {}
    for r in rows:
        c = CANON.get(str(r.get("classifier_result") or "").upper(), "UNKNOWN")
        by.setdefault(c, []).append(r)

    print("=" * 78)
    print("WIRE DIFF -- what AT&T sends differently per colour")
    print("=" * 78)
    print("source : %s" % path)
    print("records: %s" % "  ".join("%s=%d" % (c, len(by.get(c, [])))
                                    for c in ORDER))
    missing = [c for c in ("GREEN", "GOLD", "GREY") if not by.get(c)]
    if missing:
        print("")
        print("!! NO %s RECORDS CAPTURED." % " or ".join(missing))
        print("!! The gold-vs-grey rule cannot be settled without all three.")
        print("!! Re-run the hunter over a view that visibly has them.")
    print("")

    fields = []
    for r in rows:
        for k in (r.get("backend_fields") or {}):
            if k not in fields:
                fields.append(k)

    cols = [c for c in ORDER if by.get(c)]
    print("%-28s %s" % ("FIELD", "".join("%-18s" % c for c in cols)))
    print("-" * 78)
    decisive = []
    for fld in fields:
        cells = {}
        for c in cols:
            cells[c] = summarise([(r.get("backend_fields") or {}).get(fld)
                                  for r in by[c]])
        print("%-28s %s" % (fld[:28], "".join("%-18s" % cells[c][:17]
                                              for c in cols)))
        if ("GOLD" in cells and "GREY" in cells
                and cells["GOLD"] != cells["GREY"]):
            decisive.append((fld, cells["GOLD"], cells["GREY"]))

    print("-" * 78)
    if "GOLD" in cols and "GREY" in cols:
        if decisive:
            print("")
            print("FIELDS THAT SEPARATE GOLD FROM GREY:")
            for fld, g, y in decisive:
                print("   %-26s GOLD=%-18s GREY=%s" % (fld, g[:18], y[:18]))
            print("")
            print("Any field above is a candidate rule. A field that is")
            print("consistent WITHIN each colour and differs BETWEEN them is")
            print("the rule -- put its values into build_codes.json.")
        else:
            print("")
            print("NOTHING separates GOLD from GREY in this sample.")
            print("Either the sample is too small, or the distinction is not in")
            print("the payload at all -- which would itself be the answer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
