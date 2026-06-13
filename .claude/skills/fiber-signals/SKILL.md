---
name: fiber-signals
description: Find newly-lit AT&T fiber areas automatically so the hunters get pointed at fresh ZIPs instead of guessing. Covers the FCC Broadband Data Collection (BDC) / National Broadband Map data, news/Reddit buildout signals, and how they feed the optimus_targets ZIP queue. Use when building or running the front of the pipeline — sourcing where to hunt — or when deciding which ZIPs are worth a precise-hunter pass.
---

# Fiber signals — find the new buildout, then hunt it

The hunters are only as good as where you point them. This is how to source
fresh ZIPs automatically and feed them to `optimus_targets` (the ZIP queue).

## Sources, best first
1. **FCC Broadband Data Collection (BDC) / National Broadband Map** — the
   authoritative, footprint-wide source. ISPs file fixed-broadband availability
   **per location, twice a year**; the Fixed map shows fiber/cable/DSL/etc. and
   max advertised speed at each home/small business.
   - **Public Data API** (`broadbandmap.fcc.gov`, "National Broadband Map Public
     Data API") lets you pull availability programmatically — no manual file
     juggling. Bulk CSVs are also downloadable per state/technology.
   - **The high-value move = a diff.** Pull AT&T fiber availability this filing
     vs. last; every location/block that flipped to fiber is freshly lit →
     derive its ZIP → enqueue. That's "find new fiber before competitors,"
     automated and free.
   - Cadence note: BDC windows are ~biannual (an 8th window opened Jan 2026;
     specs restored/updated spring 2026), so the diff is a periodic batch, not
     real-time — pair it with the faster signals below.
2. **News / press / Reddit (fast, partial).** AT&T press releases + local news +
   r/ATTFiber for "fiber now available in <city/area>" → enqueue those ZIPs
   same-day. Catches buildout before the next BDC filing.
3. **Operator hunches / field intel.** Manual enqueue into `optimus_targets`
   (priority lane) when a tech/crew reports a newly-lit street.

## How signals feed the hunt
signal source → ZIP(s) → `optimus_targets` queue → **fiber hunter** (fast
color-only sweep) confirms freshness (green-heavy, low grey via
`zone_freshness`) → flags the genuinely fresh ZIPs → **precise hunter** pulls
exact addresses → `enrich_phones` → score → load → call.

- The BDC tells you *where fiber exists now*; the fiber hunter tells you *which
  of those is unworked/fresh*; the precise hunter gets the *exact addresses*.
  Use all three — they answer different questions.

## Build notes (not yet built — roadmap)
- `bdc_diff.py`: fetch AT&T fiber availability via the BDC API for the target
  states, diff against the last snapshot, emit newly-fiber locations → ZIPs →
  `TargetQueue.add(zip, priority, source="bdc")`. Cache snapshots so each diff
  is cheap.
- `news_watch.py`: poll a few feeds/subreddits for availability phrases, extract
  place → ZIP, enqueue with `source="news"`.
- Keep both **free** and **decoupled** from the scan (write to the queue; the
  hunter reads it), same pattern as enrichment.

## Compliance
Signals only decide WHERE to look. Everything captured still routes to
door-knock + DNC-scrubbed manual call; SMS stays consented-only. Availability
data is public; lists are not consent.
