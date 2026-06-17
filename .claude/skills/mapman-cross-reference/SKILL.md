---
name: mapman-cross-reference
description: Separate captured fiber leads into COMMERCIAL (business at the address → callable, with name+phone) vs RESIDENTIAL (home → door-knock) at scale, by bulk-scraping businesses per ZIP with the open-source gosom/google-maps-scraper and cross-referencing. Use when the goal is to split commercial vs residential leads, attach phones to the commercial ones, or scale phone enrichment past per-address lookups (which Google blocks).
---

# MapMan cross-reference: commercial vs residential split + phones

The scalable, block-resistant way to phone-up leads — the proven MapMan method,
now built on an open-source scraper.

## Why bulk, not per-address
Looking up 20,000 addresses one-by-one on Google Maps **gets blocked fast** (no
human loads 20k Maps pages). The MapMan way is **bulk**: search a *category in a
ZIP* ("restaurants in 77027") → one search returns ~120 businesses → a few
hundred searches cover a ZIP. That looks like a person browsing Maps, so it
slides past the bot blocking. Then **cross-reference** the business list against
the fiber addresses to classify + attach phones.

## The scraper (free, open source — does the bulk pull + anti-blocking)
**`gosom/google-maps-scraper`** — MIT, no API key, no usage limits, prebuilt
Windows binary. <https://github.com/gosom/google-maps-scraper/releases>
- Run: `google-maps-scraper -input queries.txt -results businesses.csv -depth 1`
- Output CSV columns: name, address, phone, website, lat/lng, category, …
- 120-results-per-search cap is normal → that's why we run many category searches.
(omkarcloud/google-maps-scraper is the same idea but a **desktop GUI** with no
CLI, so it's not auto-wireable — use gosom for the pipeline.)

## Workflow (`optimus/commercial_split.py`)
1. **Make the queries** (categories × ZIPs):
   `python commercial_split.py make-queries --zips 77027,77019` → `queries.txt`
   (categories live in `CATEGORIES` — bandwidth-hungry SMBs that buy fiber).
2. **Scrape** (the open-source binary does the work):
   `google-maps-scraper -input queries.txt -results businesses.csv -depth 1`
3. **Cross-reference + split**:
   `python commercial_split.py split --businesses businesses.csv`
   → reads the captured fiber addresses (`precise_addresses.jsonl`), and writes:
   - **`Commercial Leads`** tab — matched: Address, Business Name, Phone,
     Website, Dot Color, Zone, Category, Lat, Lng (call these).
   - **`Residential Leads`** tab — unmatched: Address, Dot Color, Zone, Lat, Lng
     (door-knock these; **no phone** — homes have no free public number).

## How the match works (the custom, tested part)
`normalize_address()` reduces both sides to `HOUSE|STREET CORE`:
- drops the unit/apt/suite tail, city/state/ZIP, and punctuation;
- canonicalizes the street suffix (Lane→LN, Road→RD, Avenue→AVE, …).
So `"3266 Locke Lane, Houston, TX 77019"` (scraped) matches `"3266 LOCKE LN"`
(captured). A fiber address that matches a scraped business = **commercial**;
no match = **residential**. The government/chain filter (`_is_callable_prospect`
from `enrich_phones`) still drops Walmart/police/etc. from the commercial tab.

## The hard truth this encodes
- **Commercial leads → free phones** (the scrape finds them).
- **Residential leads → no free phone anywhere.** OSM, Google Maps, Google
  search — none carry home numbers. Houses only get numbers via **skip-tracing**
  (paid people-data, e.g. the La Porte batch). So residential stays a door list
  unless a skip-trace source is wired in.

## Re-runs / dedupe
`split` skips addresses already in each tab (reads the existing rows first), so
re-running after more sweeps only appends new leads. Needs `google_creds.json`
on the box (same key the hunter uses); without it, it prints instead of writing.
