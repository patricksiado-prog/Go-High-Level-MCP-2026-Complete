"""
test_hunter_fixes.py — prove every fix on the real failure cases from the
BRAIN's 2026-06-29 audit of precise_fiber_hunter.py.

Run:  python test_hunter_fixes.py
"""

import os
import tempfile

import hunter_fixes as hf


FAILED = []


def check(name, got, want):
    ok = got == want
    print(("  OK   " if ok else "  FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAILED.append(name)


print("PHONE — canonical 10-digit rule")
check("plain", hf.normalize_phone("(346) 401-1250"), "3464011250")
check("leading paren dropped by old scraper regex", hf.normalize_phone("346) 401-1250"), "3464011250")
check("11-digit with 1", hf.normalize_phone("1-713-555-0142"), "7135550142")
check("too short", hf.normalize_phone("555-0142"), "")

print("ADDRESS CORE — collapses drift that broke the exact-string dedup")
check("suite", hf.core_address("24 Greenway Plz Ste 1800, Houston, TX 77046"), "24 GREENWAY PLZ")
check("junk unit", hf.core_address("24 GREENWAY PLZ UNIT COIN"), "24 GREENWAY PLZ")
check("apt", hf.core_address("2400 Blodgett St Apt 214"), "2400 BLODGETT ST")
check("hash unit", hf.core_address("2400 BLODGETT ST # 12"), "2400 BLODGETT ST")
check("zip drift", hf.core_address("558 TRESVANT DR, WEBSTER, TX 77598"),
      hf.core_address("558 Tresvant Dr"))

print("JUNK FILTER — AT&T feed placeholders must not reach the sheet")
check("unit dummy is junk", hf.is_junk_address("UNIT DUMMY"), True)
check("bare word is junk", hf.is_junk_address("CTR"), True)
check("no house number is junk", hf.is_junk_address("GREENWAY PLZ"), True)
check("real address is kept", hf.is_junk_address("558 TRESVANT DR"), False)
check("real suite is kept", hf.is_junk_address("24 GREENWAY PLZ STE 1800"), False)

print("CLEAN ADDRESS — junk unit stripped, real unit kept")
check("coin stripped", hf.clean_address("24 GREENWAY PLZ UNIT COIN"), ("24 GREENWAY PLZ", True))
check("real suite kept", hf.clean_address("24 GREENWAY PLZ STE 1800"), ("24 GREENWAY PLZ STE 1800", False))

print("DEDUPER — drift-proof, seedable from the sheet")
d = hf.Deduper(seen=["24 Greenway Plz Ste 1800, Houston, TX 77046"])
check("seeded building not re-added", d.is_new("24 GREENWAY PLZ UNIT COIN"), False)
check("new building added", d.is_new("558 TRESVANT DR"), True)
check("second pass same place blocked", d.is_new("558 Tresvant Dr, Webster, TX 77598"), False)

print("SAFE PENDING — a failed sheet write LOSES NOTHING (the flush() bug)")
wal = os.path.join(tempfile.gettempdir(), "hunter_fixes_test.jsonl")
if os.path.exists(wal):
    os.remove(wal)
p = hf.SafePending(jsonl_path=wal)
p.add({"address": "558 TRESVANT DR"})
p.add({"address": "554 TRESVANT DR"})


def broken_write(rows):
    raise RuntimeError("429 quota exceeded")


check("failed flush writes 0", p.flush(broken_write), 0)
check("rows retained after failure", len(p), 2)

sheet = []
check("retry flush writes 2", p.flush(sheet.append), 2)
check("buffer empty after success", len(p), 0)
check("sheet got one batch of 2", sheet, [[{"address": "558 TRESVANT DR"},
                                           {"address": "554 TRESVANT DR"}]])
check("WAL kept both rows", sum(1 for _ in open(wal)), 2)
os.remove(wal)

print("ROLL-UP — apartment explosion collapses to one row per building")
rows = [{"address": "2400 BLODGETT ST APT %d" % i} for i in range(1, 201)]
rows.append({"address": "558 TRESVANT DR"})
rolled = hf.rollup_buildings(rows)
check("2 buildings", len(rolled), 2)
check("unit count 200", rolled[0]["unit_count"], 200)
check("core address set", rolled[0]["core_address"], "2400 BLODGETT ST")

print()
if FAILED:
    raise SystemExit("FAILED: " + ", ".join(FAILED))
print("ALL TESTS PASSED")
