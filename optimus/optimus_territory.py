"""optimus_territory.py -- who is working which area, so two reps never collide.

THE PROBLEM (Patrick, 2026-08-22)
---------------------------------
"If I scanned a bunch of gold in Beaumont that's mine. I don't want Zack to go
there. I want the zip suggestion to tell him where to go."

So the suggestion is not a report. It is a DISPATCH: an area, claimed by a named
operator, at a time. Once Patrick holds Beaumont, Beaumont stops being offered
to anybody else and Zack is handed the next unclaimed area instead.

KEPT DELIBERATELY SEPARATE FROM CAPTURED DATA
---------------------------------------------
Where our gold already is and where somebody should go next are different
questions, and mixing them is what made the old banner useless. Captured counts
are context on a claim -- "Patrick, Beaumont, 412 gold" -- never the thing that
generates the suggestion. Suggestions come from nationwide AT&T announcements.

THE LEDGER
----------
One tab, `Territory Claims`, on the master sheet:

    Claimed At | Operator | Machine | Area | State | ZIP | Source | Status | Released At

Append-only in practice: releasing writes Status=RELEASED rather than deleting
the row, so the history of who worked what survives. A claim also EXPIRES on its
own after HOLD_DAYS, because an operator who claimed a market and never went
must not lock it forever.
"""

import time

TAB = "Territory Claims"
HEADER = ["Claimed At", "Operator", "Machine", "Area", "State", "ZIP",
          "Source", "Status", "Released At"]
HOLD_DAYS = 21          # a claim nobody acts on frees itself
ACTIVE = ("CLAIMED", "SCANNING")


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _age_days(stamp):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return (time.time() - time.mktime(time.strptime(stamp, fmt))) / 86400.0
        except Exception:
            continue
    return 0.0          # unparseable -> treat as fresh, never free somebody's area by accident


def key(area, state=""):
    """Normalise an area so 'Beaumont, TX', 'beaumont tx' and 'Beaumont' match."""
    a = " ".join(str(area or "").replace(",", " ").split()).upper()
    st = str(state or "").strip().upper()
    if st and a.endswith(" " + st):
        a = a[: -(len(st) + 1)].strip()
    elif not st:
        # "Beaumont TX" typed as one string must match ("Beaumont", "TX") passed
        # as two, or the same market gets claimed twice under two spellings.
        parts = a.split()
        if len(parts) > 1 and len(parts[-1]) == 2 and parts[-1].isalpha():
            st, a = parts[-1], " ".join(parts[:-1])
    return (a + "|" + st).strip("|")


def ensure_tab(sh):
    """Return the ledger worksheet, creating it if absent. (None, reason) on
    failure -- the service account has no Drive quota so it can only
    add_worksheet to an existing spreadsheet, never create a file.)"""
    try:
        return sh.worksheet(TAB), None
    except Exception:
        pass
    try:
        ws = sh.add_worksheet(title=TAB, rows="2000", cols=str(len(HEADER)))
        ws.append_row(HEADER)
        return ws, None
    except Exception as e:
        return None, "could not create '%s' (%s)" % (TAB, str(e)[:50])


def load(sh):
    """All claims. Returns (list, reason). Never raises."""
    ws, why = ensure_tab(sh)
    if ws is None:
        return [], why
    try:
        rows = ws.get_all_values()
    except Exception as e:
        return [], "could not read '%s' (%s)" % (TAB, str(e)[:50])
    out = []
    for r in rows[1:]:
        r = (list(r) + [""] * len(HEADER))[: len(HEADER)]
        rec = dict(zip(HEADER, [str(x).strip() for x in r]))
        if not rec["Area"] and not rec["ZIP"]:
            continue
        rec["_key"] = key(rec["Area"], rec["State"])
        rec["_age_days"] = _age_days(rec["Claimed At"])
        rec["_active"] = (rec["Status"].upper() in ACTIVE
                          and rec["_age_days"] <= HOLD_DAYS)
        out.append(rec)
    return out, None


def held_by(claims):
    """{area_key: claim} for claims still holding. Latest claim on an area wins."""
    out = {}
    for c in sorted(claims, key=lambda c: c["Claimed At"]):
        if c["_active"]:
            out[c["_key"]] = c
        else:
            out.pop(c["_key"], None)      # released or expired frees the area
    return out


def claim(sh, area, state="", zipc="", operator="", machine="", source=""):
    """Take an area. Returns (True, msg) or (False, why). Refuses to take an
    area somebody else is holding -- that refusal IS the feature."""
    ws, why = ensure_tab(sh)
    if ws is None:
        return False, why
    claims, why = load(sh)
    if why:
        return False, why
    k = key(area, state)
    if not k:
        return False, "no area given"
    holder = held_by(claims).get(k)
    if holder and holder["Operator"].upper() != str(operator).upper():
        return False, ("%s is held by %s since %s"
                       % (area, holder["Operator"], holder["Claimed At"]))
    if holder:
        return True, "%s is already yours (since %s)" % (area, holder["Claimed At"])
    try:
        ws.append_row([_now(), operator, machine, area, state, zipc, source,
                       "CLAIMED", ""])
    except Exception as e:
        return False, "could not write the claim (%s)" % str(e)[:50]
    return True, "%s claimed by %s" % (area, operator)


def release(sh, area, state="", operator=""):
    """Give an area back. Marks the row RELEASED rather than deleting it, so who
    worked what survives."""
    ws, why = ensure_tab(sh)
    if ws is None:
        return False, why
    claims, why = load(sh)
    if why:
        return False, why
    k = key(area, state)
    holder = held_by(claims).get(k)
    if not holder:
        return False, "%s is not currently claimed" % area
    if operator and holder["Operator"].upper() != str(operator).upper():
        return False, ("%s is %s's claim, not yours" % (area, holder["Operator"]))
    try:
        row = claims.index(holder) + 2            # +1 header, +1 to 1-based
        ws.update_cell(row, HEADER.index("Status") + 1, "RELEASED")
        ws.update_cell(row, HEADER.index("Released At") + 1, _now())
    except Exception as e:
        return False, "could not update the claim (%s)" % str(e)[:50]
    return True, "%s released" % area


def dispatch(candidates, claims, me, limit=6):
    """THE POINT OF THIS MODULE.

    Split web-announced areas into what THIS operator should go and take, versus
    what somebody else is already holding. `candidates` are dicts carrying at
    least `where`; `me` is the operator name.

    Returns (go, taken, mine):
      go    -- unclaimed, in announcement order. Where this operator should go.
      taken -- held by somebody else, with who and since when. Shown so nobody
               wonders why a market they saw in the news vanished.
      mine  -- areas this operator already holds.
    """
    holders = held_by(claims)
    mine_keys = {k for k, c in holders.items()
                 if c["Operator"].upper() == str(me).upper()}
    go, taken, seen = [], [], set()
    for c in candidates:
        k = key(c.get("where") or c.get("city"), c.get("state"))
        if not k or k in seen:
            continue
        seen.add(k)
        h = holders.get(k)
        if h is None:
            go.append(c)
        elif k in mine_keys:
            continue                      # already mine; listed under `mine`
        else:
            d = dict(c)
            d["holder"] = h["Operator"]
            d["since"] = h["Claimed At"]
            taken.append(d)
    mine = [holders[k] for k in sorted(mine_keys)]
    return go[:limit], taken[:limit], mine
