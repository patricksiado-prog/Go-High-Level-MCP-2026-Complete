#!/usr/bin/env python3
"""
FIBER ZONE SCANNER v1.0 -- fast, headless, multi-instance fiber DISCOVERY.
=============================================================================
This is the new front end of the hunt: find WHERE new fiber is, fast, before
anyone works it. It replaces the slow path in the old fiber_hunter.py (which
screenshotted every cell and reverse-geocoded EVERY dot at ~1.2s each). Here
we pull every dot for a ZIP in ONE backend-JSON read (optimus_api_capture),
classify by the legend color, score the zone, and diff against last scan to
surface NEW fiber. Exact addresses come straight from the JSON, so green/gold
leads can be written immediately with lat/lng -- no per-dot geocoding at all.

Because it's headless, you run MANY instances in parallel. Each one claims a
different ZIP from the shared TargetQueue (optimus_targets), so i1/i2/i3...
never collide. The queue is fed by news / outage signals.

ZONE FRESHNESS (operator rule, confirmed on the map 2026-06):
  "more grey + less gold = the area is getting older."
  grey = existing fiber customers = penetration. So:
    low grey share + lots of green  -> FRESH  (greenfield, knock TODAY)
    high grey share                 -> MATURE (already worked, deprioritize)
    in between                      -> WORKING
  A street that just lit up (new green vs last scan) always jumps priority.

PIPELINE PLACE:
  signals -> TargetQueue -> [this scanner x N] -> Fiber Zones tab (scored)
          -> exact green/gold leads -> Precise / Copper Upgrade tabs (lat/lng)
          -> MapMan enriches phones -> door-knock + DNC-scrubbed call routes.

COMPLIANCE: discovery only. No outreach here. Found addresses route door /
DNC-scrubbed call -> consent -> consented drip, never auto-text.

SETUP / RUN (HP, after fiber_precise_pipeline --login + --probe once):
    # one instance:
    python fiber_zone_scanner.py --instance 1 --api-substring serviceability
    # parallel instances (separate terminals or machines, shared queue path):
    python fiber_zone_scanner.py --instance 2 --api-substring serviceability
    # one-off single ZIP without the queue:
    python fiber_zone_scanner.py --zip 77004 --api-substring serviceability
=============================================================================
"""

import os, sys, json, time, argparse

from optimus_dot_detect import (classify_status, STATUS_LEAD, STATUS_CUSTOMER,
                                STATUS_COPPER_UPGRADE)
from optimus_api_capture import ResponseSniffer
from optimus_targets import TargetQueue, DEFAULT_QUEUE_PATH, PRI_REFRESH
import fiber_precise_pipeline as fp   # reuse browser helpers + sheet writers

FINGERPRINT_DIR = os.path.join(os.path.expanduser("~"), "Optimus", "zone_fingerprints")
ZONES_TAB = "Fiber Zones"
REFRESH_AFTER_SECS = 7 * 24 * 3600   # re-scan a worked ZIP a week later

# zone freshness thresholds (shares of total eligible+customer dots)
FRESH_MAX_GRAY_SHARE = 0.12
MATURE_MIN_GRAY_SHARE = 0.35
GREENFIELD_MIN_GREEN = 15


# -------------------------------------------------------------------------
# pure scoring + diff (unit-tested, no browser/sheet needed)
# -------------------------------------------------------------------------
def score_zone(green, gold, gray, new_green=0):
    """Score a zone from its dot counts. Returns a dict with label + priority
    (1 = knock today ... 3 = aging). Encodes the operator's freshness rule."""
    total = green + gold + gray
    if total == 0:
        return {"label": "EMPTY", "priority": 0, "green": 0, "gold": 0,
                "gray": 0, "gray_share": 0.0, "green_share": 0.0,
                "new_green": 0, "action": "skip"}
    gray_share = gray / total
    green_share = green / total
    if gray_share <= FRESH_MAX_GRAY_SHARE and green >= GREENFIELD_MIN_GREEN:
        label, pri, action = "FRESH", 1, "KNOCK TODAY (greenfield)"
    elif gray_share >= MATURE_MIN_GRAY_SHARE:
        label, pri, action = "MATURE", 3, "aging/penetrated - deprioritize"
    else:
        label, pri, action = "WORKING", 2, "work normally"
    if new_green > 0:                       # freshly lit since last scan
        pri = min(pri, 1)
        action = "NEW FIBER - %d new green; %s" % (new_green, action)
    return {"label": label, "priority": pri, "green": green, "gold": gold,
            "gray": gray, "gray_share": round(gray_share, 3),
            "green_share": round(green_share, 3), "new_green": new_green,
            "action": action}


def diff_new_addresses(prev_addrs, cur_addrs):
    """Addresses present now but not in the previous scan (newly lit)."""
    prev = set(a.upper() for a in prev_addrs)
    return [a for a in cur_addrs if a.upper() not in prev]


# -------------------------------------------------------------------------
# per-ZIP fingerprint (for the new-fiber diff across scans)
# -------------------------------------------------------------------------
def _fp_path(zipc):
    return os.path.join(FINGERPRINT_DIR, "%s.json" % zipc)


def load_fingerprint(zipc):
    try:
        with open(_fp_path(zipc)) as f:
            return json.load(f).get("green_addrs", [])
    except Exception:
        return []


def save_fingerprint(zipc, green_addrs):
    os.makedirs(FINGERPRINT_DIR, exist_ok=True)
    with open(_fp_path(zipc), "w") as f:
        json.dump({"scanned": time.time(), "green_addrs": green_addrs}, f)


# -------------------------------------------------------------------------
# capture all dots for one ZIP via the backend JSON (headless)
# -------------------------------------------------------------------------
def capture_zip(zipc, headless, profile_dir):
    """Open the map on a ZIP, capture the dot-layer JSON, return its features.
    Returns [] if the API substring isn't set or nothing was captured."""
    from playwright.sync_api import sync_playwright
    sub = fp.POPUP_CONFIG.get("address_api_url_substring")
    if not sub:
        print("  !! no --api-substring set; run fiber_precise_pipeline --probe first")
        return []
    feats = []
    with sync_playwright() as p:
        ctx = fp.open_context(p, headless=headless, profile_dir=profile_dir)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        sniffer = ResponseSniffer(capture_substring=sub, verbose=False)
        page.on("response", sniffer.on_response)
        page.goto(fp.FIBER_URL, wait_until="domcontentloaded", timeout=45000)
        time.sleep(fp.MAP_SETTLE)
        if fp.at_gate(page):
            print("  !! access gate -- run fiber_precise_pipeline --login first")
            ctx.close()
            return []
        if not fp.reach_map(page):
            print("  !! could not reach the map")
            ctx.close()
            return []
        fp.search_zip(page, zipc)
        fp.focus_map(page)
        fp.zoom_in(page)
        fp.search_this_area(page)
        time.sleep(fp.CAPTURE_SETTLE)
        feats = list(sniffer.features)
        ctx.close()
    return feats


# -------------------------------------------------------------------------
# scan one ZIP: classify, score, diff, write zone + exact leads
# -------------------------------------------------------------------------
def scan_zip(zipc, headless, profile_dir, client, instance_id):
    print("\n[i%s] ZIP %s -- capturing dot layer..." % (instance_id, zipc))
    feats = capture_zip(zipc, headless, profile_dir)
    if not feats:
        print("  no features captured for %s" % zipc)
        return None

    on_lead, on_customer, on_copper, precise_ws = fp.make_writers(client, zipc)
    seen = fp.already_seen(precise_ws)

    green = gold = gray = 0
    cur_green_addrs = []
    for f in feats:
        st = classify_status(text=f.get("status"), ban=f.get("ban"))
        addr = f["address"]
        if st == STATUS_CUSTOMER:
            gray += 1
            on_customer(addr, f.get("ban"), f.get("lat"), f.get("lng"))
        elif st == STATUS_COPPER_UPGRADE:
            gold += 1
            if addr.upper() not in seen:
                seen.add(addr.upper())
                on_copper(addr, f.get("ban"), f.get("lat"), f.get("lng"))
        else:
            green += 1
            cur_green_addrs.append(addr)
            if addr.upper() not in seen:
                seen.add(addr.upper())
                on_lead(addr, "API", f.get("lat"), f.get("lng"))

    prev_green = load_fingerprint(zipc)
    new_green_list = diff_new_addresses(prev_green, cur_green_addrs)
    save_fingerprint(zipc, cur_green_addrs)

    score = score_zone(green, gold, gray, new_green=len(new_green_list))
    _write_zone_row(client, zipc, score, instance_id)
    print("  %s | green %d gold %d grey %d | gray_share %.0f%% | NEW green %d | P%d -> %s"
          % (score["label"], green, gold, gray, score["gray_share"] * 100,
             score["new_green"], score["priority"], score["action"]))
    return score


def _write_zone_row(client, zipc, score, instance_id):
    ss = client.open_by_key(fp.SHEET_ID)
    ws = fp.ensure_tab(ss, ZONES_TAB,
                       ["Scanned At", "ZIP", "Zone Label", "Priority", "Action",
                        "Green", "Gold", "Grey", "Gray Share", "New Green",
                        "Instance"])
    ws.append_row([fp.now_str(), zipc, score["label"], score["priority"],
                   score["action"], score["green"], score["gold"], score["gray"],
                   "%.0f%%" % (score["gray_share"] * 100), score["new_green"],
                   "i%s" % instance_id])


# -------------------------------------------------------------------------
# worker loop: drain the shared queue (this is the multi-instance engine)
# -------------------------------------------------------------------------
def worker(instance_id, queue, headless, profile_dir, idle_sleep=20):
    client = fp.connect_sheets()
    print("[i%s] worker up; draining queue %s" % (instance_id, queue.path))
    while True:
        row = queue.claim(instance_id)
        if not row:
            time.sleep(idle_sleep)
            continue
        zipc = row["zip"]
        print("[i%s] claimed %s (%s, pri %s)"
              % (instance_id, zipc, row.get("source"), row.get("priority")))
        try:
            scan_zip(zipc, headless, profile_dir, client, instance_id)
            queue.complete(zipc, instance_id, requeue_refresh_after=REFRESH_AFTER_SECS)
        except Exception as e:
            print("[i%s] scan error on %s: %s -- releasing" % (instance_id, zipc, str(e)[:120]))
            queue.release(zipc)
            time.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default="1", help="instance id (i1/i2/... ; unique per process)")
    ap.add_argument("--zip", help="scan ONE ZIP and exit (no queue)")
    ap.add_argument("--queue", default=DEFAULT_QUEUE_PATH, help="shared target-queue path")
    ap.add_argument("--api-substring", required=False,
                    help="dot-layer JSON URL substring (from fiber_precise_pipeline --probe)")
    ap.add_argument("--headless", action="store_true", default=True)
    ap.add_argument("--headed", dest="headless", action="store_false")
    ap.add_argument("--profile", default=None,
                    help="login profile dir (default: per-instance under ~/Optimus)")
    args = ap.parse_args()

    if args.api_substring:
        fp.POPUP_CONFIG["address_api_url_substring"] = args.api_substring.strip().lower()

    # each instance gets its own browser profile so parallel logins don't clash
    profile = args.profile or os.path.join(os.path.expanduser("~"), "Optimus",
                                            "att_profile_i%s" % args.instance)

    if args.zip:
        client = fp.connect_sheets()
        scan_zip(args.zip, args.headless, profile, client, args.instance)
        return

    q = TargetQueue(args.queue)
    worker(args.instance, q, args.headless, profile)


if __name__ == "__main__":
    main()
