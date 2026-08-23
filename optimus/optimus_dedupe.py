"""optimus_dedupe.py -- safe identity + verification history for captured dots.

WHY
    Two separate failures made the gold data untrustworthy, and both were
    identity problems rather than classification problems:

    1. The hunter used to write a STREET-ONLY address and now writes the full
       "STREET, CITY STATE ZIP" that AT&T's payload carries. Compared as raw
       text those never match, so every legacy row would be written a SECOND
       time the next time that property was captured.

    2. Matching on street alone collapses '5309 WENDA ST' in Houston and the
       same number in Beaumont into one row. That is a silently dropped $140
       lead, and it is the same defect as the cross-state business match that
       put an Oklahoma phone number on a Texas address.

    So: normalized FULL address plus coordinates is the key. Street-only text
    is never a key. Units are preserved -- APT 2 is a different customer from
    the front house, with a different account and a different sale.

VERIFICATION HISTORY
    A re-sweep over ground already captured is evidence, not noise. When a
    record comes back that we have seen before, the old row is left exactly as
    it is and a new observation is APPENDED to the history tab: what it was,
    what it is now, the build code, whether a subscriber BAN was present, and
    when each was seen. Nothing is ever overwritten, so a wrong call can always
    be traced back rather than silently replaced.
"""
import re
import time

HISTORY_TAB = "Gold Verification"
HISTORY_HEADER = ["Checked At", "Address", "Lat", "Lng",
                  "Previous Class", "New Class", "Verdict",
                  "Build Code", "BAN Present", "Previously Captured",
                  "Run ID", "Operator"]

# Coordinate rounding for identity. 5 dp is ~1 m -- tight enough that two
# neighbouring houses never collide, loose enough that AT&T returning the same
# address with a hair of float drift still matches.
_COORD_DP = 5

# Directionals and street types are the only things normalised. Unit markers are
# deliberately NOT in here: dropping "APT 2" merges distinct customers.
_ABBREV = {
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR",
    "ROAD": "RD", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR",
    "PLACE": "PL", "PARKWAY": "PKWY", "HIGHWAY": "HWY", "TERRACE": "TER",
    "TRAIL": "TRL", "SQUARE": "SQ",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW",
    "SOUTHEAST": "SE", "SOUTHWEST": "SW",
}


def norm_address(addr):
    """Normalise for comparison WITHOUT discarding identity.

    Case, punctuation and street-type spelling are levelled. City, state, ZIP
    and unit designators are all kept -- they are what makes the address unique.
    """
    a = (addr or "").strip().upper()
    if not a:
        return ""
    a = a.replace(".", " ").replace("#", " ")
    a = re.sub(r"[^A-Z0-9,\- ]+", " ", a)
    out = []
    for tok in a.split():
        out.append(_ABBREV.get(tok, tok))
    a = " ".join(out)
    a = re.sub(r"\s*,\s*", ", ", a)
    return re.sub(r"\s+", " ", a).strip(" ,")


def coord_key(lat, lng):
    """Positional identity, ~1 m. None when coordinates are unusable."""
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= la <= 90.0 and -180.0 <= ln <= 180.0):
        return None
    if la == 0.0 and ln == 0.0:
        return None
    return "@%.*f,%.*f" % (_COORD_DP, la, _COORD_DP, ln)


_UNIT_RE = re.compile(
    r"\b(?:APT|APARTMENT|UNIT|STE|SUITE|RM|ROOM|BLDG|BUILDING|FL|FLOOR|LOT|TRLR)"
    r"\s*([A-Z0-9\-]+)\b")


def unit_token(addr):
    """The unit designator, or '' -- e.g. 'APT 2' -> '2'.

    This exists because of a real collision in the live data: 4231 BARBERRY DR
    APT 2, APT 3 and the base address all carry the SAME lat/lng, so a purely
    positional key merges an entire apartment building into one row. Each unit
    is a separate AT&T account and a separate sale.
    """
    m = _UNIT_RE.search((addr or "").upper())
    return m.group(1) if m else ""


_HOUSE_RE = re.compile(r"^\s*([0-9]+[A-Z]?)\b")


def house_number(addr):
    """The leading street number, or ''. e.g. '8231 DEVONWOOD LN' -> '8231'."""
    m = _HOUSE_RE.match((addr or "").upper())
    return m.group(1) if m else ""


def keys_for(addr, lat=None, lng=None):
    """Every key this record may be claimed under.

    The normalised FULL address and the coordinate key. A street-only string
    (no comma, so no city) still yields an address key, but that key can only
    ever match another identical street-only string -- it will never absorb a
    full address from a different city, because those normalise differently.
    """
    keys = set()
    na = norm_address(addr)
    if na:
        keys.add(na)
    ck = coord_key(lat, lng)
    if ck:
        # AT&T geocodes more than one address to a single point -- every unit of
        # an apartment building, and neighbouring townhouses to a shared parcel.
        # A bare positional key therefore MERGES DISTINCT CUSTOMERS: 8231 and
        # 8233 Devonwood arrive on the same lat/lng and one of the two $140
        # leads disappears with no trace. Caught in test 2026-08-23.
        #
        # So the coordinate key carries the street number and the unit. Two
        # different doors at one point stay two rows; the SAME door written two
        # ways -- '5309 WENDA ST' and '5309 WENDA ST, HOUSTON TX 77016', which
        # is exactly the legacy-vs-current format split this key exists for --
        # still collapses to one, because the street number is identical.
        qual = "-".join(x for x in (house_number(addr), unit_token(addr)) if x)
        keys.add(ck + ("#" + qual if qual else ""))
    return keys


def has_geography(addr):
    """True when the address carries more than a street -- i.e. it is complete
    enough to skip-trace. Used to prefer a full row over a legacy stub."""
    return "," in (addr or "")


class DedupeReport(object):
    """Counters for one run. Printed by report() and safe to call anywhere."""

    FIELDS = ("seen", "written", "duplicates", "unchanged",
              "gold_to_grey", "grey_to_gold", "unknown", "failed_writes",
              "history_rows", "history_failed")

    def __init__(self):
        for f in self.FIELDS:
            setattr(self, f, 0)
        self.changes = []          # (address, prev, new) -- for the console

    def note_change(self, addr, prev, new):
        p, n = (prev or "").upper(), (new or "").upper()
        if not p or p == "?" or not n:
            self.unknown += 1
        elif p == n:
            self.unchanged += 1
        elif p == "GOLD" and n == "GREY":
            self.gold_to_grey += 1
            self.changes.append((addr, p, n))
        elif p == "GREY" and n == "GOLD":
            self.grey_to_gold += 1
            self.changes.append((addr, p, n))
        else:
            self.unknown += 1
            self.changes.append((addr, p, n))

    def report(self, log=print):
        log("")
        log("-" * 62)
        log("DEDUPE + VERIFICATION")
        log("-" * 62)
        log("  records seen            : %d" % self.seen)
        log("  new rows written        : %d" % self.written)
        log("  duplicates found        : %d" % self.duplicates)
        log("    unchanged             : %d" % self.unchanged)
        log("    GOLD -> GREY          : %d" % self.gold_to_grey)
        log("    GREY -> GOLD          : %d" % self.grey_to_gold)
        log("    unknown / other       : %d" % self.unknown)
        log("  history rows appended   : %d" % self.history_rows)
        log("  FAILED writes           : %d" % self.failed_writes)
        if self.history_failed:
            log("  FAILED history writes   : %d" % self.history_failed)
        if self.gold_to_grey:
            log("")
            log("  %d dot(s) previously called GOLD are existing FIBER"
                % self.gold_to_grey)
            log("  customers. They are NOT upgrade leads. The old rows are")
            log("  untouched -- see the '%s' tab for the evidence."
                % HISTORY_TAB)
        for addr, p, n in self.changes[:10]:
            log("     %-44s %s -> %s" % (addr[:44], p, n))
        if len(self.changes) > 10:
            log("     ... and %d more" % (len(self.changes) - 10))
        log("-" * 62)


def ensure_history_tab(sh):
    """Get/create the append-only verification tab. Returns None on failure."""
    try:
        ws = sh.worksheet(HISTORY_TAB)
    except Exception:
        try:
            ws = sh.add_worksheet(title=HISTORY_TAB, rows="5000",
                                  cols=str(len(HISTORY_HEADER)))
            ws.append_row(HISTORY_HEADER)
        except Exception:
            return None
    try:
        if not ws.row_values(1):
            ws.append_row(HISTORY_HEADER)
    except Exception:
        pass
    return ws


def history_row(addr, lat, lng, prev_class, new_class, build_code,
                ban_present, prev_seen, run_id, operator):
    """One observation. APPEND ONLY -- this never replaces an existing row."""
    p, n = (prev_class or "").upper(), (new_class or "").upper()
    if not p or p == "?":
        verdict = "NO PRIOR CLASS"
    elif p == n:
        verdict = "UNCHANGED"
    else:
        verdict = "CHANGED %s -> %s" % (p, n)
    return [time.strftime("%Y-%m-%d %H:%M:%S"), addr,
            "" if lat is None else lat, "" if lng is None else lng,
            p or "?", n or "?", verdict,
            (build_code or "").upper(), "YES" if ban_present else "NO",
            prev_seen or "", run_id or "", operator or ""]


def write_history(ws, rows, rep=None, chunk=500):
    """Append observations in batches. Never raises into a sweep."""
    if ws is None or not rows:
        return 0
    done = 0
    for i in range(0, len(rows), chunk):
        batch = rows[i:i + chunk]
        try:
            ws.append_rows(batch, value_input_option="RAW")
            done += len(batch)
        except Exception as e:
            print("   (verification history write failed: %s)" % str(e)[:80])
            if rep is not None:
                rep.history_failed += len(batch)
    if rep is not None:
        rep.history_rows += done
    return done
