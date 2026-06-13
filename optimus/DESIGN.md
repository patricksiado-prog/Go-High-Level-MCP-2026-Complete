# Optimus — End Goal & Architecture (the business-lead factory)

> Operator: Patrick Siado, AT&T Fiber Authorized Sales Agent #247444.
> Rewritten 2026-06 around the real end goal (below). Supersedes the
> "find dots → door routes" framing in earlier notes.

## End goal (one line)

**Every week, automatically surface all the newly fiber-eligible _businesses_
across AT&T's footprint, rank them, load them into GHL (Command) as call-ready
opportunities assigned to callers, and feed a dialer so the team works the
best businesses first — hands-free right up to the conversation.**

Target volume: ~18,000 new fiber businesses/week. That's the goal to *scale
to*; actual weekly yield = however many genuinely-new fiber businesses the
footprint produces and we can capture + enrich. The system is built so it
never re-serves a business it already served (weekly dedupe), so the number is
"new this week," not "all of them again."

## The funnel (7 stages)

```
1. WIDE SIGNAL TIER  — where to point the scanners (national, cheap)
     FCC BDC diff (semiannual)      -> new AT&T fiber location_ids -> ZIPs
     AT&T newsroom / PR / attconnects (daily) -> target metros -> ZIPs
     BEAD award lists               -> funded future builds -> areas
     Reddit / local & trade press   -> metros with fiber chatter spikes
     competitor outage hook (COMMAND sheet)  -> opportunistic ZIPs
        => optimus_targets.TargetQueue  (priority-ordered, deduped)

2. DISCOVERY — find every eligible dot (live, exact, parallel)
     fiber_zone_scanner x N  drains the queue, captures the map's backend
     JSON: exact address + lat/lng + legend status, deduped vs LAST WEEK.
     The week-over-week green diff IS the "new fiber this week" engine.

3. BUSINESS ISOLATION + ENRICH — turn a dot into a callable business
     MapMan (themapman) resolves address -> business name + phone + type.
     Classify commercial vs residential; DROP national chains / blocked
     brands (BLOCKED_NAMES) and non-businesses. This is where "18k
     BUSINESSES" gets separated from "all eligible locations."

4. SCRUB + SCORE — find the PERFECT business
     - dedupe against GHL (already a contact?) and prior weeks
     - scrub internal DNC + known-litigator lists
     - flag wireless vs landline (compliance + answer-rate)
     - score each business (see "Perfect business score" below)

5. LOAD INTO GHL (Command  xZj500PjsflIQg2j9f9D) — the new core piece
     upsert contact + create opportunity in the "AT&T Commercial" pipeline
     (trc5dwodtc1LBYHikmiK), tag {week, zone, freshness, score, source},
     set custom fields {fiber status, address, lat/lng, business type,
     phone-type}, assign round-robin to a caller. Highest score = top of
     the pipeline.

6. DIAL — callers work it, hands-free up to the call
     GHL power/preview dialer pulls the pipeline in score order; the agent
     is connected to a live business, pitches fiber, dispositions the call,
     opp stage advances. Verbal consent (TX ok) -> THEN the consented drip
     may text. Bad/wrong/DNC -> scrub + stop.

7. LOOP + MEASURE — weekly orchestrator (cron)
     new-biz count, contacted, connected, booked, closed; feed outcomes
     back into the score (which zones/types actually convert).
```

## "Perfect business" score (stage 4)

Rank so callers spend minutes on the businesses most likely to buy:

| Factor | Best (high score) |
|---|---|
| Zone freshness | FRESH greenfield (just lit, unworked) > WORKING > MATURE |
| Customer status | GREEN (eligible non-customer) > GOLD (copper upgrade); skip GREY (already fiber) |
| Business type | bandwidth-hungry SMB (clinic, office, retail, restaurant, salon, contractor) > marginal |
| Reachability | valid landline > wireless > none; not on internal DNC |
| Freshness to us | not already in GHL / not contacted before |
| Geography | priority metros / signal-confirmed areas first |

`fiber_zone_scanner.score_zone()` already produces the zone half; MapMan
already classifies type + filters chains. The score module combines them.

## Calling mechanism — DECIDED: power dialer, human on every call

Operator left the call. Decision: **power/preview dialer with a live agent on
every call** (built). The loader stages and ranks the work and assigns it;
GHL's power dialer pulls the AT&T Commercial pipeline in score order and
connects a human to each business. No predictive/auto-blast and no recordings
to map/skip-traced (mostly-wireless) numbers — that's the TCPA line we don't
cross. "Automatic" for the team, defensible for the agent ID.

## Calling mechanism — detail (stage 6)

"Call automatically" has two very different meanings, and they sit on opposite
sides of the compliance line:

- **Power / preview dialer, human in the loop (recommended).** GHL queues and
  dials for the agent; a person is connected to each business and talks. This
  is "automatic" for your callers (no manual dialing, list auto-fed in score
  order) and is the defensible B2B motion.
- **Predictive / fully-autonomous autodialer or prerecorded blast.** Fires
  ahead of agents / drops recordings. This is where TCPA exposure spikes,
  especially on the wireless numbers that skip-tracing pulls. Not recommended.

### Why business calling is the RIGHT lane (and where the edges are)
- B2B calls to **business landlines** are broadly open — the **National DNC
  Registry is for residential subscribers**, not B2B. Calling fiber-eligible
  businesses about fiber is a normal, legal outbound-sales motion.
- BUT TCPA's autodialer + consent rules still apply to **wireless** numbers
  regardless of B2B — and many small businesses use cell numbers. So: keep a
  **human in the loop** (power/preview, not predictive-blast), and treat
  wireless-flagged rows with extra care.
- Still: scrub **internal DNC**, honor opt-outs, **8am–9pm local**, watch
  reassigned numbers, log everything. Matches the brain-doc rule
  "cold + DNC lists = door/call routes" and "calls: scrub DNC, 8a–9p."
- **No cold texting** map/skip-traced numbers — ever. Text only AFTER verbal
  consent on the call, via the consented drip, one registered number.

## What exists vs what's new

Built (this branch):
- `optimus_dot_detect` — legend colors + classify_status + dot detection
- `optimus_api_capture` — backend-JSON capture (exact addr + lat/lng + status)
- `fiber_precise_pipeline` — signal→ZIP scan (API capture primary)
- `precise_fiber_hunter` — wide-area grid scan (HiDPI fixed)
- `optimus_targets` — shared lease-based ZIP queue + news/outage ingestion
- `fiber_zone_scanner` — headless multi-instance discovery + freshness score
- `themapman` (MapMan) — address → business name + phone + type, chain filter

Built (this branch, continued):
- `business_score` — perfect-business rank (zone + status + type +
  reachability + new-to-us); hard-drops customers/DNC/no-phone. Tested.
- `ghl_loader` — scored businesses → Command: upsert contact + AT&T Commercial
  opportunity at Lead stage, tag/assign round-robin/custom-fields, dedupe
  across weeks (by phone), and export a score-ordered DIAL QUEUE for the power
  dialer. Dry-run by default; `--commit` + GHL_PIT_TOKEN to load live. Never
  dials, never texts. Tested.
- `bdc_diff` — footprint-wide signal loader (stage 1, top priority). Diffs two
  FCC BDC fixed-availability snapshots, isolates the AT&T-fiber location_ids
  that are NEW this period (the national "new fiber" set), rolls them up to
  ZIPs (via a fabric `location_id→ZIP` file or resolver; falls back to a
  per-census-block report), and enqueues the new-build ZIPs into the shared
  TargetQueue at buildout priority. Pure diff/rollup logic, no map scraping.
  Dry by default; `--enqueue` to load the queue. Tested.
- `weekly_run` — the orchestrator/cron (stage 7). One resumable command walks
  signals → scan → enrich → score → load in order, recording finished stages
  in a small state file so a re-run picks up where it left off. It checkpoints
  honestly at `enrich` (MapMan runs on Pydroid, a separate device): if MapMan's
  output isn't ready it stops cleanly and resumes there next run. Load stays
  DRY unless `--commit` + GHL_PIT_TOKEN. Never dials, never texts. Tested.

New to build (in priority order):
1. **More WIDE signal loaders** — news/Reddit watcher (wire to
   `optimus_targets.enqueue_news`), BEAD award loader. (`bdc_diff` — the
   footprint-wide backbone — is built; see above.)
2. **Dialer config** — GHL power dialer on the AT&T Commercial pipeline,
   pulling in score order, dispositions wired to opp stages. (Config in GHL,
   not code; `ghl_loader`/`weekly_run` already stage and order the work.)

## Compliance summary (non-negotiable)
Discovery + business calling only. Found businesses route to **DNC-scrubbed,
human-in-loop power-dialer calls**, 8am–9pm local. Verbal consent → then the
consented text drip. Never a predictive blast or a cold text to a
map/skip-traced number.
