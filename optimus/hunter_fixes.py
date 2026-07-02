"""
hunter_fixes.py  —  Precise Hunter: drop-in fixes for the bugs recorded in the
                    BRAIN (Discovery Log 2026-06-29, precise_fiber_hunter.py).

WHY THIS EXISTS
---------------
precise_fiber_hunter.py (2,889 lines) lives in repo
Go-High-Level-MCP-2026-Complete, branch claude/optimus-map-tools-setup-6dcl6o
— not reachable from this session, same as when backend_classifier.py was
built. So, per the same pattern, the fixes are built and TESTED here as a
standalone module the hunter imports with one line:

    from hunter_fixes import Deduper, SafePending, clean_address, normalize_phone

THE FOUR BUGS THIS FIXES (from the BRAIN)
-----------------------------------------
1. DATA LOSS in flush(): the hunter pops rows from self.pending BEFORE the
   sheet write succeeds, so a 429/network error permanently loses those
   captures (they only survive in the JSONL).
   -> SafePending: rows are removed ONLY after write_fn returns without
      raising. A failed flush keeps everything for the next retry.

2. DEDUP DRIFT: dedup is exact-string and in-memory, so address drift between
   passes (pin vs street, ZIP/no-ZIP, "UNIT 5" vs "STE 5") re-adds the same
   place hours later.
   -> Deduper keyed on the CANONICAL core address (the same normalization the
      BRAIN's "HOW TO COUNT FIBER LEADS" method uses), optionally seeded from
      the sheet's existing rows at startup.

3. JUNK ADDRESSES: AT&T feed values like "UNIT DUMMY", "UNIT CTR", "UNIT COIN"
   pass straight through to the sheet with no validation.
   -> clean_address() strips junk unit designators and is_junk_address()
      rejects rows with no real street address at all.

4. APARTMENT EXPLOSION: one complex = 200+ rows (one per unit), useless for a
   call list.
   -> rollup_buildings() collapses captures to one row per building with a
      unit count, for building the callable list.

CANONICAL NORMALIZATION (must stay in sync with the BRAIN)
----------------------------------------------------------
Phone:   strip to digits; drop leading 1 if 11 digits; valid = exactly 10.
Address: UPPERCASE, text before first comma, then cut everything from the
         first UNIT/APT/STE/SUITE/#/BLDG/FL/RM token onward.
         "24 Greenway Plz Ste 1800, Houston, TX 77046" -> "24 GREENWAY PLZ"
         "24 GREENWAY PLZ UNIT COIN"                   -> "24 GREENWAY PLZ"
"""

import json
import re


# ── PHONE ──────────────────────────────────────────────────────────────────
def normalize_phone(raw):
    """Canonical 10-digit phone, or "" if not a valid US number."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


# ── ADDRESS ────────────────────────────────────────────────────────────────
# Unit designators that start the "unit tail" of an address line.
_UNIT_RE = re.compile(
    r"\s+(?:(?:UNIT|APT|APARTMENT|STE|SUITE|BLDG|BUILDING|FL|FLOOR|RM|ROOM|LOT|TRLR)\b|#).*$"
)

# AT&T feed placeholder unit values that mark a junk/meter/office record,
# not a sellable living/working unit. Extend as new ones show up.
JUNK_UNIT_VALUES = {"DUMMY", "CTR", "COIN", "OFC", "OFFICE", "METER", "POOL",
                    "CLUB", "CLBHS", "LNDRY", "MAINT"}


def core_address(addr):
    """The BRAIN's canonical building key: UPPER, pre-comma, unit tail cut."""
    a = str(addr or "").upper().strip()
    a = a.split(",", 1)[0]
    a = _UNIT_RE.sub("", a)
    return re.sub(r"\s+", " ", a).strip()


def _unit_tail(addr):
    """The unit part that core_address() cuts, e.g. 'UNIT COIN' -> 'COIN'."""
    a = str(addr or "").upper().split(",", 1)[0]
    m = _UNIT_RE.search(a)
    if not m:
        return ""
    tail = m.group(0).strip()
    return re.sub(r"^(?:UNIT|APT|APARTMENT|STE|SUITE|BLDG|BUILDING|FL|FLOOR|RM|ROOM|LOT|TRLR|#)\s*",
                  "", tail).strip()


def is_junk_address(addr):
    """True when the row should NOT be written to the sheet at all."""
    core = core_address(addr)
    if not core or len(core) < 5:
        return True
    if not re.match(r"^\d+\s+\S", core):        # no house number = not an address
        return True
    if any(tok in JUNK_UNIT_VALUES for tok in core.split()):
        return True                              # junk leaked into the core
    return False


def clean_address(addr):
    """(clean_address, was_modified). Junk unit values are stripped so
    '24 GREENWAY PLZ UNIT COIN' stores as '24 GREENWAY PLZ'; real units
    ('STE 1800') are kept as captured."""
    a = re.sub(r"\s+", " ", str(addr or "").strip())
    unit = _unit_tail(a)
    if unit and unit.upper() in JUNK_UNIT_VALUES:
        pre_comma, _, rest = a.partition(",")
        cleaned = _UNIT_RE.sub("", pre_comma.upper()).strip()
        if rest:
            cleaned = cleaned + "," + rest
        return re.sub(r"\s+", " ", cleaned).strip(), True
    return a, False


# ── DEDUP (fix #2) ─────────────────────────────────────────────────────────
class Deduper:
    """Dedup on the canonical core address, immune to string drift.

    Seed it once at startup from the sheet's existing address column, then
    call is_new() before queuing a capture.
    """

    def __init__(self, seen=None):
        self._seen = set()
        for a in (seen or []):
            self._seen.add(core_address(a))

    def key(self, addr):
        return core_address(addr)

    def is_new(self, addr):
        """True (and remembered) the first time a building is seen."""
        k = self.key(addr)
        if not k or k in self._seen:
            return False
        self._seen.add(k)
        return True

    def __len__(self):
        return len(self._seen)


# ── SAFE FLUSH (fix #1) ────────────────────────────────────────────────────
class SafePending:
    """Pending-row buffer whose flush NEVER loses rows on a failed write.

    Old hunter behavior:  rows = self.pending; self.pending = []  # <-- pop
                          sheet.append_rows(rows)                 # <-- boom, rows gone
    This class:           write first, remove only on success.
    """

    def __init__(self, jsonl_path=None):
        self.rows = []
        self.jsonl_path = jsonl_path        # optional write-ahead log

    def add(self, row):
        self.rows.append(row)
        if self.jsonl_path:
            try:
                with open(self.jsonl_path, "a") as f:
                    f.write(json.dumps(row) + "\n")
            except OSError:
                pass                        # WAL is best-effort; row is in memory

    def flush(self, write_fn, batch_size=None):
        """write_fn(list_of_rows) -> raises on failure.
        Returns the number of rows actually written and removed.
        On ANY exception the un-written rows stay queued for the next flush."""
        written = 0
        while self.rows:
            batch = self.rows[:batch_size] if batch_size else list(self.rows)
            try:
                write_fn(batch)
            except Exception:
                break                       # keep everything still in self.rows
            del self.rows[:len(batch)]
            written += len(batch)
        return written

    def __len__(self):
        return len(self.rows)


# ── BUILDING ROLL-UP (fix #4) ──────────────────────────────────────────────
def rollup_buildings(rows, addr_key="address"):
    """Collapse per-unit captures to one row per building.

    rows: list of dicts. Returns list of dicts = first row seen per building
    plus 'unit_count' and 'core_address'. Order of first appearance kept.
    """
    out, index = [], {}
    for r in rows:
        k = core_address(r.get(addr_key))
        if not k:
            continue
        if k in index:
            index[k]["unit_count"] += 1
        else:
            rep = dict(r)
            rep["core_address"] = k
            rep["unit_count"] = 1
            index[k] = rep
            out.append(rep)
    return out
