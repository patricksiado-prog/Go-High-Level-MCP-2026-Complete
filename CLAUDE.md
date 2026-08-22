# CLAUDE.md — Go-High-Level-MCP-2026-Complete

**This repo is the CODE.** The hunter, the scrapers, the GHL connector.

**Business context is NOT here.** It lives in `patricksiado-prog/optimus-map-tools`,
branch `claude/lead-gen-software-research-brho9a`, in `BRAIN.md` (3,110 lines, 22 parts)
with `INDEX.md` as the map. Read those for anything about leads, pay, markets, doctrine or
what happened when.

The full 2,042-line historical version of this file is preserved at
`docs/CLAUDE_ARCHIVE_2026-08-22.md`. Nothing was deleted. It is history — do not act on
it without checking BRAIN.md first, because most of its business content is superseded.

---

## The dot legend — get this right or everything downstream is wrong

| Dot | Means | Pays |
|---|---|---|
| **GREEN** | fiber live, NOT an AT&T customer | **$500** |
| **GOLD / ORANGE** | fiber live, AT&T customer still on copper | **$140** |
| GREY | already an AT&T fiber customer | skip — never written to the sheet |

---

## The hunter

`optimus/precise_fiber_hunter.py` — **5,127 lines / 233 KB. It is the whole product.**
19 modules, 12,229 lines of Python total.

**Full architecture with real code is BRAIN part 21.** Read it before changing anything.
The short version:

- It does **not** scrape the page and does **not** read pixels (that path exists but is
  OFF by default — clicking "dots" on a transitioning page hits nav buttons).
- It attaches to `page.on('response')` and **decodes Mapbox vector tiles (protobuf)**,
  converting tile-local coordinates to lng/lat. That is the only source of lat/lng, which
  is why `Gold Dots` has coordinates and `Precise Fiber` does not.
- `_is_basemap_tile()` filters Mapbox's own street tiles. Without it, street names decode
  as bogus addresses. **First suspect if garbage rows appear.**
- `classify_wire()` decides colour from two fields: `subscriber_ban` and
  `curr_ntwrk_bld_type_cd`, against `build_codes.json`. No BAN → GREEN. BAN + confirmed
  fiber → GREY. BAN + confirmed copper → GOLD.
- **An undecodable customer defaults to GREY** (`OPTIMUS_UNKNOWN_CUSTOMER`). A false grey
  costs nothing; a false gold puts a rep on the phone with an existing fiber customer.

### Read the classification report

`wire_classification_report()` prints at the end of every run and includes
*"X% of customer dots were a guess, not a decode"* plus the undecoded build codes.
**It already answers why gold reads 2% when the map shows 9–11%, and nobody has read it.**
Confirm an undecoded code on the dealer map, add it to `build_codes.json`, gold jumps.

---

## Deploy — the one path

**NORMAL UPDATE = RELAUNCH.** Nobody reinstalls to get new code. Two layers, same source:

1. `self_update()` at the top of `main()` — `git fetch` + `reset --hard origin/<branch>`
   when git exists, else **HTTPS raw re-download** with stdlib `urllib`. Then re-exec
   once, guarded by `*_NO_UPDATE=1`.
2. The desktop launcher also curls the core files each launch, downloading to `.new` and
   only swapping on success.

**Git is not installed on the hunter PCs.** `_raw_refresh()` is the real updater in the
field.

### `_CORE_FILES` — the deploy allowlist

```python
_CORE_FILES = ("precise_fiber_hunter.py", "optimus_operator.py",
               "optimus_dot_detect.py", "optimus_api_capture.py",
               "hunter_fixes.py", "backend_classifier.py",
               "build_codes.json", "verify_gold_capture.py",
               "deploy_check.py")
```

**A new module not in this tuple never reaches a field machine.** That is the single most
common deploy mistake here.

**Docs and markdown are NOT in `_CORE_FILES`.** Editing this file, or anything in `docs/`,
cannot reach or break a hunter PC.

### Version stamps

`BUILD_DATE` is typed by hand and has already disagreed with the running code. **Trust
`_file_stamp()`** — it derives the mtime and a byte fingerprint from the file itself and
cannot go stale.

---

## Key CLI flags

| Flag | Effect |
|---|---|
| `--login` | log into AT&T once, then quit |
| `--zip 77070` | search a ZIP before scanning |
| `--net` | network-capture mode (the good path) |
| `--dry` | classify and print, write nothing |
| `--auto` | unattended; never prompts |
| **`--backfill-gold`** | **seed `Gold Dots` from existing ORANGE rows. ~6,324 rows. Still not run.** |
| `--operator NAME` / `--whoami` | set/re-ask scanning identity |
| `--allow-click` | re-enable pixel clicking (off for a reason) |

---

## Known bugs, unfixed

- **Street-only capture.** `Upgrade Orange Biz` addresses have no city or ZIP —
  "708 W MAIN ST". Two consequences: DealMachine `enrich_address` hard-fails without a
  ZIP, and the combo matcher joins on street name alone. Confirmed damage: an Oklahoma
  405 number matched to a Texas "W Main St". **Fix it at capture, not downstream.**
- **`backend_classifier.py` is a second copy of the wire classifier.** Nobody has diffed
  it against `precise_fiber_hunter.py`. Two copies of the gold/grey logic is exactly the
  shape of bug that cost weeks before.
- **Gold reads 2.05% vs 9–11% visible on the map.** See the classification report above.

---

## Conventions

- **Never write placeholder text into a phone field.** The sheet once stored the literal
  string `(all DNC)` instead of digits, and the numbers were lost — that cost a full day
  of selling. Actual digits, stored as text.
- **A failure that returns 0 instead of raising is worse than a crash.** Gold silently
  never wrote for weeks because `client.create()` threw on a Drive-quota limit and the
  caller swallowed it. Say it out loud.
- **`_ensure_header()` only writes missing cells** at the end of row 1. It never rewrites
  existing labels and never touches row 2+. Keep it that way — the naive version would
  destroy live data.
- **The service account has zero Drive storage quota.** It can read and update files
  already shared with it. It cannot create a new file. Use `add_worksheet()` on an
  existing spreadsheet.

## The sheet

`1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA` — `Precise Fiber` is 474,075 rows and
live. Never read it wholesale.
