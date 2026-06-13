#!/usr/bin/env python3
"""
WEEKLY RUN v1.0 -- the Optimus orchestrator (DESIGN.md stage 7 / cron).
=============================================================================
One command that walks the whole factory for the week, in order, and is safe
to re-run: it records which stages finished in a small state file and picks up
where it left off. That matters because the pipeline has ONE unavoidable human
/ other-device gap -- MapMan (themapman.py) runs on Pydroid and enriches the
scanned dots into business name + phone on a Google Sheet. So a single process
can't go dot -> dial in one shot. weekly_run models that honestly: it runs the
code-able stages, and when it reaches enrichment it CHECKPOINTS -- if MapMan
hasn't produced its output yet it stops cleanly and tells you to re-run after
MapMan finishes. No stage is ever done twice.

STAGES (in order):
  signals  feed news/outage/BDC signals into the shared TargetQueue
  scan     (browser, multi-instance) report queue depth; optionally drain once
  enrich   CHECKPOINT: wait for MapMan's enriched-businesses file
  score    rank enriched businesses (business_score) best-first
  load     stage ranked businesses into GHL + write the power-dialer queue
           (DRY by default; --commit + GHL_PIT_TOKEN to actually load)

Heavy/optional deps (playwright, numpy, requests) are imported lazily inside
the stage that needs them, so the orchestrator and its pure planning logic
import and test cleanly anywhere.

COMPLIANCE: orchestration only. The load stage stages call-ready work for a
human-in-the-loop power dialer; nothing here dials or texts. Found businesses
route to DNC-scrubbed calls, consent, then the consented drip -- never a cold
text or predictive blast.
=============================================================================
"""

import os, sys, json, argparse
from datetime import datetime

import optimus_targets as targets

STAGES = ["signals", "scan", "enrich", "score", "load"]
DEFAULT_STATE = os.path.join(os.path.expanduser("~"), "Optimus", "weekly_state.json")
DEFAULT_ENRICHED = os.path.join(os.path.expanduser("~"), "Optimus", "enriched_businesses.json")
DEFAULT_RANKED = os.path.join(os.path.expanduser("~"), "Optimus", "ranked_businesses.json")


def week_tag(now=None):
    return (now or datetime.now()).strftime("week-%G-W%V")


# -------------------------------------------------------------------------
# pure planning / resume logic (unit-tested, no IO)
# -------------------------------------------------------------------------
def plan_stages(done, only=None, skip=None, force=False, all_stages=STAGES):
    """Decide which stages to run this invocation.

    done   : iterable of already-completed stage names (from the state file)
    only   : if set, run exactly these stages (still in canonical order)
    skip   : stage names to skip
    force  : ignore `done` and run everything not skipped (a clean re-run)
    Returns the ordered list of stages to execute.
    """
    done = set() if force else set(done or [])
    only = set(only) if only else None
    skip = set(skip or [])
    out = []
    for s in all_stages:
        if only is not None and s not in only:
            continue
        if s in skip or s in done:
            continue
        out.append(s)
    return out


# -------------------------------------------------------------------------
# run-state (resume across invocations; same shape as the other state files)
# -------------------------------------------------------------------------
def load_state(path):
    try:
        with open(path) as f:
            st = json.load(f)
    except Exception:
        st = {}
    st.setdefault("week", None)
    st.setdefault("done", [])
    return st


def save_state(path, st):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    st["updated"] = datetime.now().strftime("%m/%d/%Y %I:%M %p")
    with open(path, "w") as f:
        json.dump(st, f, indent=2)


def _mark_done(state_path, st, stage):
    if stage not in st["done"]:
        st["done"].append(stage)
    save_state(state_path, st)


# -------------------------------------------------------------------------
# stage implementations (each returns True on success / "advance the stage")
# -------------------------------------------------------------------------
def stage_signals(args, q):
    """Drain configured signal sources into the TargetQueue."""
    added = 0
    if args.outage:
        added += int(targets.ingest_outage_signal(q, args.outage))
    if args.news and os.path.exists(args.news):
        with open(args.news) as f:
            items = json.load(f)
        added += targets.enqueue_news(q, items)
    if args.bdc_cur:
        import bdc_diff
        match = {}
        cur_rows = bdc_diff.read_rows(args.bdc_cur)
        prev = bdc_diff.load_baseline(args.bdc_baseline) if args.bdc_baseline else set()
        new_rows = bdc_diff.diff_new_locations(prev, cur_rows, **match)
        resolver = bdc_diff.build_fabric_resolver(args.bdc_fabric) if args.bdc_fabric else None
        ordered = bdc_diff.order_targets(bdc_diff.rollup_by_zip(new_rows, resolver)["zips"])
        added += bdc_diff.enqueue_targets(q, ordered)
        if args.bdc_baseline:
            bdc_diff.save_baseline(args.bdc_baseline,
                                   bdc_diff.fiber_location_ids(cur_rows, **match))
    print("[signals] enqueued %d target(s); queue now %d pending"
          % (added, len(q.pending())))
    return True


def stage_scan(args, q):
    """Discovery is the long-running, multi-instance browser job. The
    orchestrator does NOT own those browsers by default -- run
    fiber_zone_scanner --instance N separately against the same --queue. Here
    we just report depth, unless --scan-once is given to drain one ZIP inline."""
    pending = q.pending()
    print("[scan] %d ZIP(s) pending in %s" % (len(pending), q.path))
    if not args.scan_once:
        if pending:
            print("       run: python fiber_zone_scanner.py --instance 1 "
                  "--queue %s --api-substring <substring>" % q.path)
        return True
    if not args.api_substring:
        print("       --scan-once needs --api-substring (from fiber_precise_pipeline --probe)")
        return False
    import fiber_zone_scanner as fzs
    import fiber_precise_pipeline as fp
    fp.POPUP_CONFIG["address_api_url_substring"] = args.api_substring.strip().lower()
    row = q.claim("weekly")
    if not row:
        print("       queue empty -- nothing to scan")
        return True
    client = fp.connect_sheets()
    try:
        fzs.scan_zip(row["zip"], True, None, client, "weekly")
        q.complete(row["zip"], "weekly", requeue_refresh_after=fzs.REFRESH_AFTER_SECS)
    except Exception as e:
        q.release(row["zip"])
        print("       scan error on %s: %s" % (row["zip"], str(e)[:120]))
        return False
    return True


def stage_enrich(args):
    """CHECKPOINT on MapMan. MapMan (Pydroid) reads the scanner's exact
    addresses and writes back business name + phone + type. We just confirm its
    output exists and is non-empty; if not, stop cleanly so a later re-run
    resumes here once MapMan has finished."""
    path = args.enriched
    if not os.path.exists(path):
        print("[enrich] waiting on MapMan: %s not found." % path)
        print("         Run themapman.py (Pydroid) on the Precise tab, export the")
        print("         enriched businesses to that path, then re-run weekly_run.")
        return False
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        print("[enrich] %s is not valid JSON yet (%s) -- waiting." % (path, str(e)[:80]))
        return False
    if not data:
        print("[enrich] %s is empty -- MapMan hasn't written businesses yet." % path)
        return False
    print("[enrich] MapMan output ready: %d enriched business(es)." % len(data))
    return True


def stage_score(args):
    """Rank the enriched businesses best-first (pure scoring)."""
    import business_score
    with open(args.enriched) as f:
        businesses = json.load(f)
    ranked = business_score.rank_businesses(businesses)
    with open(args.ranked, "w") as f:
        json.dump([{**r["business"], "score": r["score"]} for r in ranked], f, indent=2)
    print("[score] ranked %d callable business(es) (of %d) -> %s"
          % (len(ranked), len(businesses), args.ranked))
    if ranked:
        top = ranked[0]
        print("        top: %s (score %d)"
              % (top["business"].get("name") or top["business"].get("address"), top["score"]))
    return bool(ranked)


def stage_load(args):
    """Stage ranked businesses into GHL + write the dialer queue (DRY default)."""
    import ghl_loader
    with open(args.ranked) as f:
        ranked = json.load(f)
    agents = [a.strip() for a in (args.agents or "").split(",") if a.strip()]
    token = os.environ.get("GHL_PIT_TOKEN")
    if args.commit and not token:
        print("[load] --commit needs GHL_PIT_TOKEN in the environment; staying DRY.")
        return False
    summary = ghl_loader.load_businesses(ranked, agents, args.week,
                                         token=token, commit=args.commit)
    print("[load] %s | input %d | new %d | loaded %d | dupes %d | dial queue -> %s"
          % ("COMMITTED" if args.commit else "DRY", summary["input"], summary["new"],
             summary["loaded"], summary["skipped_dupes"], summary["dial_queue"]))
    return True


# -------------------------------------------------------------------------
# driver
# -------------------------------------------------------------------------
def run(args):
    st = load_state(args.state)
    wk = args.week
    # a new week (or a --force) starts the stage ledger fresh
    if args.force or st.get("week") != wk:
        st["week"] = wk
        st["done"] = [] if (args.force or st.get("week") != wk) else st["done"]
    plan = plan_stages(st["done"], only=args.only, skip=args.skip, force=args.force)
    if not plan:
        print("Nothing to do for %s (done: %s). Use --force to re-run." % (wk, st["done"] or "none"))
        return 0

    print("== Optimus weekly run %s == plan: %s\n" % (wk, " -> ".join(plan)))
    q = targets.TargetQueue(args.queue)
    for stage in plan:
        if stage == "signals":
            ok = stage_signals(args, q)
        elif stage == "scan":
            ok = stage_scan(args, q)
        elif stage == "enrich":
            ok = stage_enrich(args)
        elif stage == "score":
            ok = stage_score(args)
        elif stage == "load":
            ok = stage_load(args)
        else:
            ok = False
        if not ok:
            print("\nStopped at '%s' (checkpoint or error). Re-run to resume here." % stage)
            save_state(args.state, st)
            return 1
        _mark_done(args.state, st, stage)

    print("\nAll stages complete for %s. Dial queue is staged for the power dialer." % wk)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Optimus weekly orchestrator (resumable)")
    ap.add_argument("--week", default=week_tag(), help="week tag (default: this ISO week)")
    ap.add_argument("--state", default=DEFAULT_STATE, help="resume state file")
    ap.add_argument("--queue", default=targets.DEFAULT_QUEUE_PATH, help="shared TargetQueue path")
    ap.add_argument("--only", nargs="*", help="run ONLY these stages")
    ap.add_argument("--skip", nargs="*", help="skip these stages")
    ap.add_argument("--force", action="store_true", help="ignore prior state; re-run all")
    # signal inputs
    ap.add_argument("--outage", help="COMMAND-sheet outage value, e.g. '77002|Comcast outage'")
    ap.add_argument("--news", help="JSON file of news items to scan for AT&T fiber ZIPs")
    ap.add_argument("--bdc-cur", help="current FCC BDC CSV (new-build diff signal)")
    ap.add_argument("--bdc-baseline", help="saved BDC fiber-id baseline JSON")
    ap.add_argument("--bdc-fabric", help="BDC fabric CSV (location_id->ZIP)")
    # scan
    ap.add_argument("--scan-once", action="store_true", help="drain ONE ZIP inline (else just report)")
    ap.add_argument("--api-substring", help="dot-layer JSON substring (for --scan-once)")
    # enrich / score / load
    ap.add_argument("--enriched", default=DEFAULT_ENRICHED, help="MapMan output (enriched businesses JSON)")
    ap.add_argument("--ranked", default=DEFAULT_RANKED, help="where to write the ranked list")
    ap.add_argument("--agents", default="", help="comma-separated GHL user ids to round-robin")
    ap.add_argument("--commit", action="store_true", help="load stage writes to GHL for real")
    args = ap.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
