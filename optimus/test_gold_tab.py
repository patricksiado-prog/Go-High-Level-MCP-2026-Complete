"""
test_gold_tab.py -- gold dots must land in a TAB of the main sheet.

The bug: _ensure_gold_tab() opened/created a SEPARATE spreadsheet
("OPTIMUS GOLD DOTS"). The service account has zero Drive storage quota, so
client.create() always threw, write_gold_dots() swallowed it and returned 0,
and gold silently never appeared -- while green kept writing fine.

These tests pin the fix: the tab is created on the SAME spreadsheet object the
hunter already writes to, and a failure is never silent again.
"""
import sys
sys.path.insert(0, ".")

import precise_fiber_hunter as H

fails = []


def check(name, got, want):
    if got == want:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s -- got %r, wanted %r" % (name, got, want))
        fails.append(name)


class FakeWS:
    def __init__(self, title, rows=None):
        self.title = title
        self.rows = rows if rows is not None else []
    def get_all_values(self):
        return self.rows
    def append_row(self, r, **k):
        self.rows.append(r)
    def append_rows(self, rs, **k):
        self.rows.extend(rs)
    def col_values(self, n):
        return [r[n - 1] if len(r) >= n else "" for r in self.rows]


class FakeClient:
    def __init__(self):
        self.create_calls = 0
        self.open_calls = 0
    def create(self, title):
        self.create_calls += 1
        raise Exception("insufficient Drive storage quota for service account")
    def open(self, title):
        self.open_calls += 1
        raise Exception("SpreadsheetNotFound")


class FakeSheet:
    """Stands in for the MAIN ATT FIBER LEADS spreadsheet."""
    def __init__(self, tabs=None):
        self.tabs = tabs or {}
        self.client = FakeClient()
        self.added = []
    def worksheet(self, title):
        if title in self.tabs:
            return self.tabs[title]
        raise Exception("WorksheetNotFound: %s" % title)
    def add_worksheet(self, title, rows, cols):
        self.added.append(title)
        ws = FakeWS(title)
        self.tabs[title] = ws
        return ws


def reset():
    H._GOLD["ws"] = None
    H._GOLD["seen"] = None


print("\n--- the tab is created on the MAIN sheet, not a new file ---")
reset()
sh = FakeSheet()
gw = H._ensure_gold_tab(sh)
check("tab created on the main spreadsheet", sh.added, ["Gold Dots"])
check("client.create() never called", sh.client.create_calls, 0)
check("client.open() never called", sh.client.open_calls, 0)
check("header written", gw.rows[0], H._GOLD_HEADER)

print("\n--- an existing tab is reused, not duplicated ---")
reset()
existing = FakeWS("Gold Dots", [H._GOLD_HEADER, ["1 OLD ST", "t", "", "", "", ""]])
sh2 = FakeSheet({"Gold Dots": existing})
gw2 = H._ensure_gold_tab(sh2)
check("no new tab added", sh2.added, [])
check("seen-set seeded from column A", "1 OLD ST" in H._GOLD["seen"], True)

print("\n--- gold records actually get written ---")
reset()
sh3 = FakeSheet()
records = [
    {"address": "100 GOLD ST", "dot_status": "copper_upgrade", "ts": "T", "lat": 1, "lng": 2},
    {"address": "200 GREEN ST", "dot_status": "lead", "ts": "T"},
    {"address": "300 GOLD AVE", "dot_status": "copper_upgrade", "ts": "T"},
    {"address": "400 GREY LN", "dot_status": "customer", "ts": "T"},
]
n = H.write_gold_dots(sh3, records)
check("2 gold rows written", n, 2)
written = [r[0] for r in sh3.tabs["Gold Dots"].rows[1:]]
check("only the gold addresses", written, ["100 GOLD ST", "300 GOLD AVE"])
check("green not written", "200 GREEN ST" in written, False)
check("grey not written", "400 GREY LN" in written, False)

print("\n--- dedupe: the same gold dot is not written twice ---")
n2 = H.write_gold_dots(sh3, records)
check("second pass writes 0", n2, 0)
check("still only 2 rows", len(sh3.tabs["Gold Dots"].rows) - 1, 2)

print("\n--- no gold in the batch is a clean no-op ---")
reset()
sh4 = FakeSheet()
check("all-green batch writes 0",
      H.write_gold_dots(sh4, [{"address": "1 A ST", "dot_status": "lead"}]), 0)

print("\n--- a failure is REPORTED, never silent ---")
reset()


class BrokenSheet(FakeSheet):
    def add_worksheet(self, title, rows, cols):
        raise Exception("boom")


import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    n3 = H.write_gold_dots(BrokenSheet(), records)
out = buf.getvalue()
check("returns 0 on failure", n3, 0)
check("but PRINTS the reason", "GOLD TAB FAILED" in out, True)
check("reason includes the error", "boom" in out, True)

print("\n--- config sanity ---")
check("tab name", H.GOLD_TAB, "Gold Dots")
check("header is 6 cols", len(H._GOLD_HEADER), 6)

print("")
if fails:
    print("FAILED: %d" % len(fails)); sys.exit(1)
print("ALL GOLD-TAB TESTS PASSED")
