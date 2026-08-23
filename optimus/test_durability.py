"""test_durability.py -- the regression guard for the 2026-08-23 gold loss.

WHAT IT PROTECTS
    A gold dot was detected, marked `seen`, then written. When the write failed
    the rows were discarded AND stayed marked seen, so no re-sweep would ever
    retry them. Silent $140 losses with no message anywhere.

    These tests fail if that ordering ever comes back. Run them before any push
    that touches the writer:

        py test_durability.py

    No network, no sheet, no browser. Pure functions pulled out of the hunter by
    AST so importing it (which launches things) is never necessary.
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FAILED = []


def check(name, ok, detail=""):
    print("  %-52s %s" % (name, "PASS" if ok else "FAIL"))
    if not ok:
        FAILED.append("%s %s" % (name, detail))


def load(names, extra=None):
    """Pull named functions/assignments out of the hunter without importing it."""
    src = open(os.path.join(HERE, "precise_fiber_hunter.py")).read()
    ns = dict(os=os, json=json, time=time, sys=sys, re=__import__("re"),
              RUN_ID="TEST", OPERATOR=lambda: "test", _DEDUPE_REPORT=None)
    ns.update(extra or {})
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            exec(compile(ast.Module([node], []), "<h>", "exec"), ns)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    try:
                        exec(compile(ast.Module([node], []), "<h>", "exec"), ns)
                    except Exception:
                        pass
    return ns


class FakeSheet(object):
    """append_rows fails the first `fail` times, then succeeds."""

    def __init__(self, fail=0):
        self.rows, self.fail, self.calls = [], fail, 0

    def append_rows(self, batch, **kw):
        self.calls += 1
        if self.fail > 0:
            self.fail -= 1
            raise Exception("APIError 503 backend error")
        self.rows.extend(batch)


def main():
    tmp = tempfile.mkdtemp(prefix="optimus_dur_")
    ns = load({"_park_batch", "commit_rows", "replay_pending", "stage",
               "stage_report", "_STAGE", "_STAGE_ORDER", "_as_spreadsheet"})
    ns["_pending_dir"] = lambda: tmp
    try:
        print("\n1. FAILURE INJECTION -- a failed write must not lose the rows")
        ws = FakeSheet(fail=99)
        got = ns["commit_rows"](ws, "Gold Dots", [["a"], ["b"]])
        parked = os.listdir(tmp)
        check("reports 0 committed (never claims a false write)", got == 0)
        check("rows parked on disk, not discarded", len(parked) == 1)
        if parked:
            blob = json.load(open(os.path.join(tmp, parked[0])))
            check("parked rows are intact", blob["rows"] == [["a"], ["b"]])

        print("\n2. seen is a SUBSET of committed -- the original bug")
        seen, staged, written = set(), [{"k1"}, {"k2"}, {"k3"}], 1
        for k in staged[:written]:
            seen.update(k)
        check("only committed keys are marked seen", seen == {"k1"})
        check("uncommitted keys stay retryable",
              "k2" not in seen and "k3" not in seen)

        print("\n3. CRASH RECOVERY -- a killed run loses nothing")
        # The parked file from test 1 is exactly the state a crash leaves behind.
        ws2 = FakeSheet()

        class SH(object):
            def worksheet(self, t):
                return ws2

        n = ns["replay_pending"](SH(), log=lambda *a: None)
        check("next run replays the parked batch", n == 2)
        check("rows reach the sheet after restart", ws2.rows == [["a"], ["b"]])
        check("pending cleared only after the ACK", not os.listdir(tmp))

        print("\n4. TRANSIENT FAILURE -- retries rather than parking")
        ws3 = FakeSheet(fail=2)
        got = ns["commit_rows"](ws3, "Gold Dots", [["c"]])
        check("committed after retries", got == 1)
        check("nothing parked", not os.listdir(tmp))
        check("it actually retried", ws3.calls == 3)

        print("\n5. STAGE INVARIANTS -- a breach must be named, not inferred")
        out = []
        ns["_STAGE"].clear()
        ns["_STAGE"].update(dict(classified_gold=12, gold_queued=12,
                                 gold_committed=0, gold_seen=12))
        ns["stage_report"](log=out.append)
        txt = "\n".join(out)
        check("seen-without-commit is reported", "INVARIANT BROKEN" in txt)
        check("and names the consequence", "NEVER RETRY" in txt)

        out = []
        ns["_STAGE"].clear()
        ns["_STAGE"].update(dict(classified_gold=12, gold_queued=12,
                                 gold_committed=12, gold_seen=12,
                                 gold_pending=0))
        ns["stage_report"](log=out.append)
        check("a healthy run reports no breach",
              "INVARIANT BROKEN" not in "\n".join(out))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if FAILED:
        print("%d FAILED:" % len(FAILED))
        for f in FAILED:
            print("   - %s" % f)
        return 1
    print("ALL DURABILITY TESTS PASSED -- a failed write cannot lose a gold dot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
