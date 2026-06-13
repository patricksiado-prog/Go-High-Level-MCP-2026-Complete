---
name: optimus-fiber
description: Engineering playbook + project memory for the Optimus AT&T fiber outreach toolkit (the map scanners, scorer, GHL loader, dialer, and SMS tooling in /optimus). Use this whenever working on fiber lead capture, the precise hunter, MapMan/zone scanners, business scoring, the GHL power-dialer loader, or any longer-running task on this repo, so the work stays consistent across sessions.
---

# Optimus Fiber — engineering playbook & project memory

You are working on Patrick's AT&T fiber outreach factory. This skill keeps
multi-session work consistent: how the pieces fit, the rules that must never
be broken, and how to leave the repo so the next session can pick up cleanly.

## The pipeline (front to back)
1. **Signals → ZIP queue** — `optimus_targets.py` (TargetQueue) holds ZIPs to scan.
2. **Map capture** — get exact fiber-eligible addresses off the AT&T dealer map:
   - `precise_fiber_hunter.py` — wide-area grid; clicks every green+gold dot,
     reads the popup address; **Mapbox geo fast path** pulls addresses straight
     from `queryRenderedFeatures()` (no clicking) when the map hook is live.
     `--fresh` mode captures only just-lit zones (green+gold heavy, little/no
     grey); `--survey-out N` zooms out first to sweep for clusters.
   - `fiber_precise_pipeline.py` — MapMan single-ZIP capture via the map's
     backend JSON (exact address + lat/lng + BAN, no clicking).
   - `optimus_dot_detect.py` — the ONE canonical place for dot-color windows,
     the popup regexes, `classify_status`, and `zone_freshness`. Tune HERE
     only; both scanners import it so thresholds can never drift apart.
   - `fiber_zone_scanner.py` — classifies a ZIP's freshness (FRESH/WORKING/
     MATURE) to prioritize greenfield.
3. **Score** — `business_score.py` ranks each business (zone freshness +
   customer status + bandwidth-hungry type + reachable landline > wireless +
   new-to-us). Hard-drops customers, internal-DNC, no-phone.
4. **Load → GHL** — `ghl_loader.py` upserts contact + AT&T Commercial
   opportunity (pipeline `trc5dwodtc1LBYHikmiK`, Command location
   `xZj500PjsflIQg2j9f9D`), dedupes by phone across weeks, enrolls each into
   the **"Optimus Fiber Biz — Power Dialer Queue"** workflow
   (`41e00387-a766-4975-bbcd-627c684a3ee1`), and writes a score-ordered
   dial queue.
5. **Work** — GHL power dialer (Conversations → Manual Actions) serves callers
   one business at a time; callers are Sheika (Sheika Lomejor), Romeo, Zack.

## Hard rules (compliance — never engineer around these)
- Map/skip-traced output feeds **DOOR-KNOCK + DNC-scrubbed MANUAL CALL** only.
  **Never** cold-text these numbers (TCPA $500–$1,500 per text).
- SMS is for **consented/opted-in/inbound** contacts only, from a single
  registered number, throttled, opt-out intact. No sender rotation/snowshoeing.
- Calling = **power dialer with a human on every call**. No predictive
  auto-blast, no recorded calls to skip-traced numbers.
- Don't migrate or text Frontline's recent work into/out of Command.

## Working style on this repo (do this every time)
- **Pure logic is unit-tested in the container; Playwright/live-GHL runs on the
  HP.** When you add map/browser code, stub `playwright` and test the pure
  parts (detection, parsing, scoring, dedupe) with a synthetic screenshot or
  fake page — never claim a browser path works from here.
- **Compile then test**: `python3 -m py_compile <files>` and run the inline
  asserts before committing.
- **Commit small, push to the working branch** `claude/optimus-map-tools-setup-6dcl6o`.
  End commit messages with the session link footer. Don't open a PR unless asked.
- **Update `optimus/DESIGN.md`** when a stage is built or a decision is made,
  so the plan reflects reality for the next session.
- Secrets (the `pit-` GHL token, `google_creds.json`) live in env / the HP's
  `~/Optimus/`, never in the repo or on Drive.

## Leaving a clean handoff
At the end of a work session, make sure: code compiles + tests pass, changes
are committed and pushed, DESIGN.md reflects what's done vs. next, and any new
tool is listed in `optimus/README.md`. State plainly what's verified vs. what
still needs a live run on the HP.
