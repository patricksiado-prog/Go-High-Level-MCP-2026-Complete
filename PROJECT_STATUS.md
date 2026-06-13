# Project Status — Optimus AT&T Fiber Outreach

> Living source of truth. Keep the six sections short and current.
> Engineering detail lives in `optimus/DESIGN.md`; this is the cross-session board.

## NOW
- Map capture hardening: precise_fiber_hunter v0.5 + `--fresh` mode ready; needs
  a live HP run on a known just-lit ZIP to confirm the Mapbox geo fast path
  fires (look for "viewport (mapbox)") vs. the pixel fallback.

## NEXT
1. Wire the front half: signal loaders (FCC BDC diff, news/Reddit watcher) →
   `optimus_targets` ZIP queue, so scans get fed automatically.
2. `weekly_run.py` orchestrator: signals → scan (`--fresh`) → score → load →
   dialer queue, on a schedule.
3. Assign the "Fiber Biz Call" workflow action to a caller (Sheika) in GHL.

## DONE
- Installer + GitHub updater + setup checker on Drive ("Optimus Installer").
- Power-dialer workflow live in Command; ghl_loader enrolls each loaded biz.
- business_score + ghl_loader (score → contact + AT&T Commercial opp → queue).
- precise_fiber_hunter v0.4 (click every dot) + v0.5 (Mapbox geo fast path) +
  `--fresh` new-zone mode; optimus_dot_detect.zone_freshness canonical.
- SMS stack verified: all 4 Command lines + 11 Frontline lines, two-way,
  multi-turn. A2P approved both accounts (operator-confirmed).

## DECISIONS
- 2026-06-12: Calling = power dialer, human on every call. No predictive
  auto-blast / no recorded calls to skip-traced numbers (TCPA).
- 2026-06-12: Map/skip-traced output = door-knock + DNC-scrubbed manual call
  only; never cold-text.
- 2026-06-12: Nominatim rejected for addresses (bans bulk grid queries, no unit
  numbers); use the map's own Mapbox geo features + popup instead.
- 2026-06-13: "New fiber" = lots of green+gold + little/no grey (zone_freshness
  FRESH); hunter `--fresh` skips MATURE zones fast.

## BLOCKERS
- Number enrichment billing: waiting on Zack to open a Google Cloud account +
  enable Billing (texted 2026-06-13). Need the enrichment vendor/API name to
  finish his setup instructions.
- Live HP run needed to confirm map paths (can't run Playwright/GHL from the
  build container).

## HANDOFF
- Branch: `claude/optimus-map-tools-setup-6dcl6o`
- Verified: all pure logic unit-tested in-container (detection, parsing,
  scoring, dedupe, freshness); SMS stack live-tested; installer tested.
- Needs live run: precise_fiber_hunter `--fresh` on the HP against a real ZIP;
  ghl_loader `--commit` with the pit token.
- Next step: on the HP — `git pull` (or run update_optimus.bat), then
  `python precise_fiber_hunter.py --zip <just-lit ZIP> --fresh --survey-out 2 --dry`

## Journal
- 2026-06-13: project tracker created; recorded hunter --fresh + skills work.
