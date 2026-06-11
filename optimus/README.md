# Optimus Map Tools (fiber map -> exact addresses -> dial/door routes)

Operator: Patrick Siado, AT&T Fiber Authorized Sales Agent #247444.
The youachieve fiber map (`https://youachieve.att.com/yourefer/fiber`) is the
authorized dealer tool; these scripts reuse Patrick's own single human login
(saved Playwright profile, `--login` once) — no gate automation, no parallel
sessions, polite pacing.

## The pipeline, mapped exactly

```
SIGNAL (ZIP, e.g. competitor outage)
  -> COMMAND sheet 12PII... tab "COMMAND"  (A1="OUTAGE", B1="zip|note")
  -> fiber_precise_pipeline.py (--watch or --zip)
       PRIMARY:  capture the map's backend JSON (--api-substring)
                 -> exact Address + Lat/Lng + Subscriber BAN per dot
       FALLBACK: screenshot -> detect green dots -> click -> read popup
  -> sheet 1FhO2... ("ATT FIBER LEADS")
       BAN present  -> "Customers (has BAN)" tab   (existing customer, skip)
       no BAN       -> "Precise" tab               (lead; Lat/Lng filled)
       every signal -> "Outage Signals" tab
  -> themapman.py (MapMan v11.2.5, Pydroid)  [Drive 16bAkV_BFbwaakGOeXBZ8Ll-8ySXmv9gV]
       reads IN_TAB ("Hunter Green Commercial" by default — point it at
       "Precise" to consume this pipeline). Reads Address/Lat/Lng/State by
       header name; if Lat/Lng present it SKIPS geocoding and goes straight
       to Places nearby-search -> tenant name + PHONE
       writes "Fiber Commercial Leads" tab
  -> dial list -> DOOR-KNOCK + DNC-SCRUBBED MANUAL CALLS (never cold SMS)
```

`precise_fiber_hunter.py` is the wide-area grid tool (snake-scan cols x rows
viewports, click every dot) writing the "Precise Fiber" tab. Use the pipeline
for single-ZIP signal scans; use the hunter for broad sweeps or as fallback.

`optimus_install_v2/v3.py` (Drive) are **installers**, not MapMan: they set up
`C:\Users\patri\Optimus\` with `fiber_hunter.py`, `hunter_dot_extractor.py`,
`themapman.py`, creds, and RUN_*.bat launchers. v3 embeds the service-account
key (see Security below).

## What was wrong (why sheet addresses were "inaccurate")

The address TEXT was always exact (read from AT&T's popup). The errors were in
*which dot's popup got opened*:

1. **HiDPI drift** — hunter v0.2 clicked at screenshot-pixel coordinates; on
   scaled displays screenshot px != click px, so clicks missed or hit
   neighbors. Fixed in `precise_fiber_hunter.py` v0.3: `device_scale_factor=1`
   plus sx/sy scaling of detected coordinates (ported from the pipeline).
2. **Threshold disagreement** — hunter used HSV hue 70–95 (OpenCV scale =
   140–190 real degrees: teal/cyan, wrong); pipeline used RGB
   (30,130,30)–(100,210,80) (confirmed live 77070, 2026-05-31). They were
   claimed identical; they barely overlap. Now both import the ONE canonical
   detector in `optimus_dot_detect.py`.
3. **Overlap misattribution (the main one)** — overlapping dots meant a click
   opened a NEIGHBOR's popup, pinning a real address to the wrong house. No
   click-side fix is fully reliable, which is why:

## The real fix: backend API capture

The map loads its dots from a backend JSON API. `fiber_precise_pipeline.py`
v0.4 captures that response and reads **exact address + lat/lng + BAN for
every dot in the view** — no clicking, no pixels, no OCR. Procedure:

```
python fiber_precise_pipeline.py --login                 # once ever
python fiber_precise_pipeline.py --probe --zip 77070     # once per map version
#   pan/zoom, click "Search this area", click one dot, press Enter
#   -> prints ranked endpoints + suggested substring
python fiber_precise_pipeline.py --zip 77002 --signal "Comcast outage" \
       --api-substring <substring-from-probe>
```

The parser (`optimus_api_capture.extract_features`) is schema-tolerant (plain
JSON, nested lists, GeoJSON), so it should survive minor backend changes; if
AT&T moves the endpoint, just re-run `--probe`. The click/popup path remains
as automatic fallback when the capture matches nothing.

Lat/Lng now flow through to the Precise tab columns MapMan already reads, so
phone enrichment and door routes land on the exact rooftop.

## Files

| File | Role |
|---|---|
| `optimus_dot_detect.py` | Canonical color thresholds + dot detection + popup regexes (shared) |
| `optimus_api_capture.py` | Response sniffer (probe + capture) + JSON feature extractor |
| `fiber_precise_pipeline.py` | v0.4 signal->ZIP scanner; API capture primary, clicks fallback |
| `precise_fiber_hunter.py` | v0.3 wide-area grid scanner; HiDPI fix, unified detection |

Deps: `pip install playwright gspread google-auth numpy pillow scipy` then
`python -m playwright install chromium`. (OpenCV no longer needed.)

## Compliance — non-negotiable lanes

- Map addresses + skip-traced phones feed **DOOR-KNOCK + DNC-SCRUBBED COLD
  CALLS only** (National DNC re-scrub every 31 days, internal DNC, 8am–9pm
  local). Consent (verbal yes OK in TX) **before** any text; texts then go
  through the consented GHL drip from one registered number.
- **NEVER cold-text** map or skip-traced numbers — TCPA $500–$1,500 per text.
- youachieve automation stays one reused human login, polite delays; whether
  that fits AT&T's dealer-tool terms is Patrick's call to confirm with AT&T.

## Security flags (rotate, don't paste)

- `optimus_install_v3.py` on Drive **embeds the full service-account private
  key** (fiberscanner@fiberscanner-493900). Anyone with that Drive file has
  write access to the sheets. Rotate the key in GCP and stop embedding it.
- `themapman.py` embeds a Google Maps Places **API key** — restrict it (API +
  IP/app restrictions) or rotate; Places calls bill per request.
- The GHL `pit-` token exposure from CLAUDE.md §7 still stands.
