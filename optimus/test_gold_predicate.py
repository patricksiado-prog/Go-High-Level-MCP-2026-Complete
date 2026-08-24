"""test_gold_predicate.py -- lock the GOLD vs GREY rule, and keep the two
implementations of it agreeing.

WHY THIS EXISTS
    Gold and grey are identical on the wire except curr_ntwrk_bld_type_cd. That
    one predicate decides whether a $140 upgrade reaches the call list or a
    fiber customer wastes a rep's morning, and it is implemented TWICE:

        precise_fiber_hunter.classify_wire()   <- the live sweep
        backend_classifier.classify_lead()     <- fiber_scout, zip_reader,
                                                  verify_gold_capture

    Two copies of one rule is how they drift apart without anyone noticing.
    CLAUDE.md already warns about exactly this. Until they are merged, this test
    holds them to the same answers.

    It also pins the decisions that have been got WRONG in production before, so
    a future "improvement" cannot quietly reintroduce them:
      - an undecodable customer must NOT be called gold (that put existing fiber
        customers in front of a rep)
      - an undecodable customer must NOT be called grey (grey never reaches the
        sheet, so real $140 leads were deleted)
      - a placeholder BAN like "non-cust" is NOT a customer (reading it as one
        turned a $500 green into a dropped row)

RUN:  py test_gold_predicate.py
"""
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FAILED = []


def check(name, ok, detail=""):
    print("  %-56s %s" % (name, "PASS" if ok else "FAIL"))
    if not ok:
        FAILED.append("%s %s" % (name, detail))


def load_hunter_classifier():
    """Lift classify_wire out of the hunter WITHOUT importing it (importing
    launches things). Every module-level assignment it depends on is executed,
    including the build-code load -- running only the empty default is how an
    earlier version of this test invented two bugs that did not exist."""
    import optimus_dot_detect as DD
    src = open(os.path.join(HERE, "precise_fiber_hunter.py")).read()
    ns = {"os": os, "json": json, "re": __import__("re"),
          # the loader resolves build_codes.json relative to __file__; without
          # it the open() throws, the except swallows it, and the code tables
          # stay EMPTY -- which looks exactly like a classifier that cannot
          # decode anything. That false alarm cost two rounds here already.
          "__file__": os.path.join(HERE, "precise_fiber_hunter.py"),
          "is_customer_ban": DD.is_customer_ban,
          "classify_status": getattr(DD, "classify_status",
                                     lambda *a, **k: "lead"),
          "_WIRE_COUNTS": {"green": 0, "fiber": 0, "copper": 0,
                           "unknown": 0, "no_code": 0},
          "_UNKNOWN_CODES": {}, "_UNKNOWN_CODE_SAMPLE": {},
          "_UNKNOWN_CUSTOMER": "unknown"}
    want_fn = {"classify_wire", "_bld_code", "_unknown_customer_status"}
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name in want_fn:
            exec(compile(ast.Module([node], []), "<h>", "exec"), ns)
        elif isinstance(node, (ast.Assign, ast.Try, ast.If)):
            # the build-code load lives in a try/except at module level
            txt = ast.get_source_segment(src, node) or ""
            if "_BLD_CODES" in txt or "_CODES_PATH" in txt:
                try:
                    exec(compile(ast.Module([node], []), "<h>", "exec"), ns)
                except Exception:
                    pass
    return ns


NORM = {"lead": "GREEN", "copper_upgrade": "GOLD",
        "customer": "GREY", "unknown_customer": "UNKNOWN"}


def main():
    import backend_classifier as BC
    ns = load_hunter_classifier()
    cw = ns["classify_wire"]
    codes = ns.get("_BLD_CODES", {})

    print("\n0. THE RULE IS ACTUALLY LOADED (an empty table decides nothing)")
    check("hunter knows the copper codes", bool(codes.get("copper")),
          "_BLD_CODES['copper'] is empty -> gold can never be emitted")
    check("hunter knows the fiber codes", bool(codes.get("fiber")))
    check("backend_classifier knows the copper codes",
          bool(BC.COPPER_BUILD_CODES))
    check("both read the SAME build_codes.json",
          set(BC.COPPER_BUILD_CODES) == set(codes.get("copper", ())),
          "the two implementations disagree on what copper means")

    # address is required by backend_classifier -- a record without one is not
    # a dot at all, and omitting it is how this test once invented a bug.
    def rec(ban, bld):
        return {"address": "8211 COOLSHIRE LN", "subscriber_ban": ban,
                "curr_ntwrk_bld_type_cd": bld}

    CASES = [
        ("no account -> GREEN ($500)",        rec("", "unavailable"),      "GREEN"),
        ("fiber code + account -> GREY",      rec("123", "fttp-gpon"),     "GREY"),
        ("copper code + account -> GOLD",     rec("123", "fttn-bp"),       "GOLD"),
        ("ip-rt + account -> GOLD",           rec("123", "ip-rt"),         "GOLD"),
        ("ftth + account -> GREY",            rec("123", "ftth"),          "GREY"),
    ]
    print("\n1. THE DECIDED CASES -- both implementations must agree")
    for name, r, want in CASES:
        a = NORM.get(cw(None, r["subscriber_ban"], r), "?")
        b = str(BC.classify_lead(r)).upper()
        check("%-34s hunter=%-7s backend=%s" % (name, a, b),
              a == want and b == want, "expected %s" % want)

    print("\n2. THE UNDECIDED CASE -- 'unavailable' on a real account")
    r = rec("123", "unavailable")
    a = NORM.get(cw(None, r["subscriber_ban"], r), "?")
    b = str(BC.classify_lead(r)).upper()
    print("     hunter=%s   backend=%s" % (a, b))
    check("hunter does NOT call it gold", a != "GOLD",
          "calling it gold put fiber customers on the call list")
    check("hunter does NOT call it grey", a != "GREY",
          "calling it grey deleted real $140 leads")
    check("backend does NOT call it gold", b != "GOLD")

    print("\n3. THE REGRESSIONS THAT COST MONEY BEFORE")
    r = rec("non-cust", "unavailable")
    check("placeholder BAN is NOT a customer -> stays GREEN",
          NORM.get(cw(None, r["subscriber_ban"], r), "?") == "GREEN",
          "reading a placeholder as a customer drops a $500 green")
    r = rec("123", "")
    check("account with NO build code is not guessed",
          NORM.get(cw(None, r["subscriber_ban"], r), "?") == "UNKNOWN")
    r = {"address": "", "subscriber_ban": "", "curr_ntwrk_bld_type_cd": ""}
    check("a record with no address is skipped",
          str(BC.classify_lead(r)).upper() == "SKIP")

    print("")
    if FAILED:
        print("%d FAILED:" % len(FAILED))
        for f in FAILED:
            print("   - %s" % f)
        return 1
    print("GOLD PREDICATE LOCKED -- both implementations agree on every")
    print("decided case, and neither guesses on the undecided one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
