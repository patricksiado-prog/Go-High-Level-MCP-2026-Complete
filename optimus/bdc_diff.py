#!/usr/bin/env python3
"""
BDC DIFF v1.0 -- footprint-wide "where did AT&T light NEW fiber" signal loader.
=============================================================================
This is the WIDEST, cheapest tier of the signal funnel (DESIGN.md stage 1).
The FCC's Broadband Data Collection (BDC) publishes, twice a year, every
provider's fixed-broadband availability claim per location. Diff two snapshots
and the locations where AT&T reports FIBER now but did NOT last time are the
*new builds* across the whole country -- no map scraping, no guessing which
metro to point the scanners at. Roll those new locations up to ZIPs and they
become high-priority targets in the shared TargetQueue, ahead of routine
refreshes.

WHY location_id, not address: BDC keys every claim to a CostQuest "fabric"
location_id (a stable per-rooftop id). Diffing ids is exact -- a location that
flips from "no AT&T fiber" to "AT&T fiber" is unambiguously a new build. (The
public availability CSV carries block_geoid, not ZIP; pass the fabric file or a
resolver to map locations -> ZIP. Without one we still report new-build counts
per census block so the diff is never silently empty.)

PURE LOGIC (top, unit-tested, no network):
  is_att_fiber / fiber_location_ids / diff_new_locations / rollup / order
NETWORK / IO (bottom, only when run as a CLI):
  read snapshot CSVs, persist the fiber-id baseline, enqueue into TargetQueue.

COMPLIANCE: this only decides WHERE to look. No addresses, phones, or outreach
here. New ZIPs flow scan -> enrich -> score -> load -> human power-dialer,
exactly like every other signal. BDC is public government data.

TYPICAL USE (semiannual, when a new BDC snapshot drops):
    # first time: establish the baseline from the current snapshot
    python bdc_diff.py --cur bdc_2025-12_fixed.csv --save-baseline ~/Optimus/bdc_att_fiber.json

    # next snapshot: diff against the saved baseline, enqueue new-build ZIPs
    python bdc_diff.py --cur bdc_2026-06_fixed.csv \
        --baseline ~/Optimus/bdc_att_fiber.json --fabric bdc_fabric.csv \
        --enqueue --save-baseline ~/Optimus/bdc_att_fiber.json
=============================================================================
"""

import os, csv, json, argparse

from optimus_targets import TargetQueue, DEFAULT_QUEUE_PATH, PRI_NEWS_BUILDOUT

# BDC "technology" codes for fiber-to-the-premises. 50 = Optical Carrier/FTTP.
FIBER_TECH_CODES = {"50"}
# Match AT&T by brand name (robust to AT&T's many subsidiary FRNs). A
# provider_id allowlist can be passed too for an exact-id match.
ATT_BRAND_HINTS = ("at&t", "att ", "at and t", "at&t inc")
SOURCE = "bdc"


# -------------------------------------------------------------------------
# pure logic (no network / no files)
# -------------------------------------------------------------------------
def _norm(s):
    return str(s or "").strip().lower()


def is_att_fiber(row, brand_hints=ATT_BRAND_HINTS, tech_codes=FIBER_TECH_CODES,
                 provider_ids=None):
    """True if a BDC availability row is an AT&T fiber (FTTP) claim.

    row keys are matched case-insensitively, so the raw FCC CSV headers
    (brand_name, technology, provider_id, location_id) work as-is. A provider
    matches if its provider_id is in `provider_ids` (when given) OR its
    brand name contains an AT&T hint.
    """
    r = {_norm(k): v for k, v in row.items()}
    tech = str(r.get("technology", "")).strip()
    if tech not in tech_codes:
        return False
    if provider_ids and str(r.get("provider_id", "")).strip() in provider_ids:
        return True
    brand = _norm(r.get("brand_name") or r.get("holding_company") or r.get("provider_name"))
    return any(h in brand for h in brand_hints)


def fiber_location_ids(rows, **match):
    """Set of location_ids that are AT&T-fiber claims in this snapshot."""
    out = set()
    for row in rows:
        if is_att_fiber(row, **match):
            r = {_norm(k): v for k, v in row.items()}
            loc = str(r.get("location_id", "")).strip()
            if loc:
                out.add(loc)
    return out


def diff_new_locations(prev_ids, cur_rows, **match):
    """Return the AT&T-fiber rows in cur_rows whose location_id is NEW
    (present now, absent from prev_ids). One row per new location_id."""
    prev = set(str(x).strip() for x in prev_ids)
    new_rows, seen = [], set()
    for row in cur_rows:
        if not is_att_fiber(row, **match):
            continue
        r = {_norm(k): v for k, v in row.items()}
        loc = str(r.get("location_id", "")).strip()
        if not loc or loc in prev or loc in seen:
            continue
        seen.add(loc)
        new_rows.append(row)
    return new_rows


def _row_zip(row, resolver=None):
    """Best-effort ZIP for a BDC row. Order: explicit zip column on the row >
    `resolver` (a dict location_id->zip OR a callable(row)->zip)."""
    r = {_norm(k): v for k, v in row.items()}
    for k in ("zip", "zip_code", "zipcode", "postal_code"):
        z = str(r.get(k, "")).strip()
        if len(z) >= 5 and z[:5].isdigit():
            return z[:5]
    if resolver is None:
        return None
    if callable(resolver):
        z = resolver(row)
    else:  # dict keyed by location_id
        z = resolver.get(str(r.get("location_id", "")).strip())
    z = str(z or "").strip()
    return z[:5] if (len(z) >= 5 and z[:5].isdigit()) else None


def rollup_by_zip(new_rows, resolver=None):
    """Count new-build locations per ZIP. Returns
    {"zips": {zip: count}, "unmapped": n} where unmapped = new locations we
    couldn't resolve to a ZIP (still reported so the gap is visible)."""
    zips, unmapped = {}, 0
    for row in new_rows:
        z = _row_zip(row, resolver)
        if z:
            zips[z] = zips.get(z, 0) + 1
        else:
            unmapped += 1
    return {"zips": zips, "unmapped": unmapped}


def rollup_by_block(new_rows):
    """Fallback rollup when no ZIP resolver is available: new-build count per
    census block_geoid. Keeps the diff meaningful without a fabric file."""
    blocks = {}
    for row in new_rows:
        r = {_norm(k): v for k, v in row.items()}
        b = str(r.get("block_geoid") or r.get("geoid") or "").strip()
        if b:
            blocks[b] = blocks.get(b, 0) + 1
    return blocks


def order_targets(zip_counts, min_new=1):
    """ZIPs to enqueue, most new-builds first (ties: ZIP asc for stability).
    Drops ZIPs below `min_new` new locations (filters one-off noise)."""
    items = [(z, c) for z, c in zip_counts.items() if c >= min_new]
    items.sort(key=lambda zc: (-zc[1], zc[0]))
    return items


# -------------------------------------------------------------------------
# IO (only touched by the CLI)
# -------------------------------------------------------------------------
def read_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_baseline(path):
    """Prior snapshot's AT&T-fiber location-id set."""
    try:
        with open(path) as f:
            return set(json.load(f).get("location_ids", []))
    except Exception:
        return set()


def save_baseline(path, ids):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump({"count": len(ids), "location_ids": sorted(ids)}, f)


def build_fabric_resolver(path):
    """Map location_id -> ZIP from a BDC fabric CSV (the file that carries the
    per-location ZIP). Returns a dict usable as `resolver`."""
    out = {}
    for row in read_rows(path):
        r = {_norm(k): v for k, v in row.items()}
        loc = str(r.get("location_id", "")).strip()
        z = ""
        for k in ("zip", "zip_code", "zipcode", "postal_code"):
            if r.get(k):
                z = str(r[k]).strip()
                break
        if loc and len(z) >= 5 and z[:5].isdigit():
            out[loc] = z[:5]
    return out


def enqueue_targets(queue, ordered, note_prefix="BDC new fiber"):
    added = 0
    for z, count in ordered:
        if queue.add(z, priority=PRI_NEWS_BUILDOUT,
                     note="%s: %d new build(s)" % (note_prefix, count), source=SOURCE):
            added += 1
    return added


def main():
    ap = argparse.ArgumentParser(description="Diff FCC BDC snapshots -> new AT&T fiber ZIPs")
    ap.add_argument("--cur", required=True, help="current BDC fixed-availability CSV")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--prev", help="previous BDC CSV to diff against")
    g.add_argument("--baseline", help="saved fiber-id baseline JSON to diff against")
    ap.add_argument("--fabric", help="BDC fabric CSV (location_id->ZIP) for ZIP rollup")
    ap.add_argument("--provider-ids", default="",
                    help="comma-separated AT&T provider_id allowlist (optional)")
    ap.add_argument("--min-new", type=int, default=1,
                    help="only enqueue ZIPs with >= this many new builds")
    ap.add_argument("--queue", default=DEFAULT_QUEUE_PATH, help="shared TargetQueue path")
    ap.add_argument("--enqueue", action="store_true",
                    help="actually add ZIPs to the queue (default: dry report)")
    ap.add_argument("--save-baseline", help="write current fiber-id set here as the next baseline")
    args = ap.parse_args()

    match = {}
    if args.provider_ids:
        match["provider_ids"] = set(p.strip() for p in args.provider_ids.split(",") if p.strip())

    cur_rows = read_rows(args.cur)
    cur_ids = fiber_location_ids(cur_rows, **match)

    if args.prev:
        prev_ids = fiber_location_ids(read_rows(args.prev), **match)
    elif args.baseline:
        prev_ids = load_baseline(args.baseline)
    else:
        prev_ids = set()
        print("(no --prev/--baseline: treating the whole current snapshot as new)")

    new_rows = diff_new_locations(prev_ids, cur_rows, **match)
    resolver = build_fabric_resolver(args.fabric) if args.fabric else None
    roll = rollup_by_zip(new_rows, resolver)
    ordered = order_targets(roll["zips"], min_new=args.min_new)

    print("AT&T fiber locations: prev %d | current %d | NEW %d"
          % (len(prev_ids), len(cur_ids), len(new_rows)))
    print("new-build ZIPs (>= %d new): %d | unmapped new locations: %d"
          % (args.min_new, len(ordered), roll["unmapped"]))
    for z, c in ordered[:25]:
        print("  %s  %d new" % (z, c))
    if not roll["zips"] and new_rows:
        blocks = rollup_by_block(new_rows)
        print("no ZIP resolver -> %d new-build census blocks (pass --fabric to map to ZIPs)"
              % len(blocks))

    if args.enqueue and ordered:
        q = TargetQueue(args.queue)
        n = enqueue_targets(q, ordered)
        print("enqueued %d new-build ZIP target(s) into %s" % (n, q.path))
    elif ordered:
        print("(dry) pass --enqueue to add these %d ZIPs to the queue" % len(ordered))

    if args.save_baseline:
        save_baseline(args.save_baseline, cur_ids)
        print("baseline saved (%d AT&T-fiber location ids) -> %s"
              % (len(cur_ids), args.save_baseline))


if __name__ == "__main__":
    main()
