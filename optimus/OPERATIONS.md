# OPTIMUS — Local Operations

> The **how it keeps running without Patrick babysitting it**.
> Companion to `optimus_hunter/DESIGN.md` (the what/why of the lead factory).
> Written 2026-09-06 from a live session on LAPTOP-JLCQ24SO.

---

## 1. Start everything

```
control\START_OPTIMUS.bat              by hand
Scheduled Task "Optimus Autostart"     at logon, and on session unlock
```

Both run the same `START_ALL.ps1`, so the manual and automatic paths cannot
drift. It is guarded — running it twice never produces a second supervisor.

It starts exactly **two** things:

| | |
|---|---|
| `supervisor.ps1` | owns the Hunter, the uploader and the Maps Scraper |
| `control_center.py` | the dashboard on <http://localhost:8787> |

The Hunter is deliberately **not** started here as well; that would give it two
owners.

**Why Task Scheduler, not the Startup folder:** the Startup folder only fires at
logon and cannot retry. The task adds a **session-unlock trigger** (lid open /
resume, which `AtLogOn` does not fire on), `StartWhenAvailable`, and
restart-on-failure (3 × 5 min). A boot-level SYSTEM task needs elevation this
account does not have — logon + unlock covers every real case, especially now
that sleep is off.

### Sleep is off (2026-09-06)

```
standby   AC 0 / DC 0        hibernate AC 0 / DC 0        monitor AC 15 min
```

A suspend kills the Hunter and no wrapper survives it — that is what killed it at
4:12am. Hibernate-on-battery was still 3 hours; it is now 0 as well.

---

## 2. The Control Center

```
py control_center.py           -> http://localhost:8787   (refreshes every 10s)
py control_center.py --once    -> one text report
py control_center.py --json    -> machine-readable
```

Layers: Claude → OpenClaw → Playwright → Supervisor → Hunter → Uploader →
Scraper → Sheets → GHL → DealMachine. Each shows state, detail, last heartbeat,
last error.

Two rules, because a dashboard that lies is worse than none:

- a layer that cannot be checked reports **N/A, never OK**, and *not installed*
  is shown differently from *installed but dead*;
- every probe is **cheap and local**. Sheet health is read from the uploader's
  own log — the record of what actually reached Google — not from API calls.

It earned its keep within a minute: it caught a Hunter that had not captured for
1h26m, and a false "rate limited" that was a street number containing `429` in
my own regex.

**A cost worth remembering:** the first version spawned ~11 `powershell.exe` per
page load and took >15s on this laptop — a monitor costing more than the thing it
monitors. It now takes ONE process snapshot per refresh, cached 6s (2.8s/report).

---

## 3. How "stuck" is decided (and why it must not false-positive)

A live process parked on a dead page still looks alive to `Get-Process`, so
health is judged by **progress files**:

| Tool | Progress signal |
|---|---|
| Hunter | `precise_addresses.jsonl` (appended on every capture), `run_status.json`, `_feed/heartbeat.json` |
| Scraper | `businesses.csv`, `maps_zips_done.json`, `maps_progress.json` |

**A file only counts if it was written AFTER the current process started.** The
hunter folder is full of heartbeats days old; trusting one is how a watchdog
decides a healthy run is hung and kills it seconds after launch.

`optimus_feed.phase()` used to only **push** the heartbeat to GitHub and never
write it locally, so the on-disk copy was always stale. It now mirrors to disk.

**The login screen is not "stuck."** While the browser title shows a login page
the supervisor leaves the Hunter alone for `login_grace_minutes` (60), so a
restart can never yank the page away mid-MFA.

### Two supervisor defects, found by them misfiring (2026-09-06)

1. **It killed the uploader.** The uploader is the *same file* run with
   `--uploader`, so matching `precise_fiber_hunter` hit both. A Hunter reset took
   the uploader with it and sheet writes stopped while capture continued — which
   looks exactly like a working run until you open the sheet. Now matched with
   `-notmatch '--uploader'`, and the uploader is checked separately.
2. **Its threshold was tighter than the Hunter's own status cadence.**
   `run_status.json` lands every 15 cells, which on a slow sweep exceeds 25
   minutes, so a healthy Hunter was killed at 15:31. Progress is now judged on
   `precise_addresses.jsonl`; threshold 40 minutes.

### Killing the browser costs the AT&T session

`Stop-Process -Force` on Chromium can stop it flushing cookies to `att_profile` —
observed 2026-09-06: a forced browser kill during a Hunter reset put the next
launch back on the access chooser, costing a human password + MFA. The supervisor
now calls `CloseMainWindow()`, waits 5s, and only then forces.

---

## 4. Settings — `config.json`

| Key | Value | Meaning |
|---|---|---|
| `seed_zips` | `77070,77002` | Where the Scraper starts; it auto-advances outward. **The one knob you normally touch.** |
| `scrape_depth` | `2` | 1 light / 2 heavy / 3 deep |
| `hunter_login_wait_secs` | `3600` | 60 min for AT&T login (stock 600 expired mid-MFA) |
| `hunter_stuck_minutes` | `40` | No capture for this long → reset |
| `scraper_stuck_minutes` | `30` | No writes for this long → reset |
| `login_grace_minutes` | `60` | Hands off while parked on the AT&T login |
| `min_free_mb_for_scraper` | `500` | Do not even start the Scraper below this |
| `scraper_yield_mb` | `250` | Stop the Scraper if the box gets this tight |
| `command_center` | Desktop folder | Where folder orders are read from |

---

## 5. This laptop cannot run both tools at once

**3.8 GB total RAM.** With Hunter + Chromium + uploader + Scraper + a headless
Chrome, free memory hit **79 MB (2.1%)**, and a Python file write died with
`MemoryError` mid-edit. The Hunter's own source blames low RAM for the WebGL
blank-map freeze — so this is very likely the real cause of the lockups.

The supervisor treats memory as the scarce resource: **the Hunter always wins**,
and the Scraper only starts above `min_free_mb_for_scraper`, and is stopped below
`scraper_yield_mb`. In practice the Scraper will usually **not** run while the
Hunter hunts. That is a hardware limit, not a bug — more RAM, or run them in
shifts.

---

## 6. Local fixes, and why they keep disappearing

**Both tools re-download themselves and silently wipe local patches:**

- `RUN_HUNTER.bat` re-downloads `precise_fiber_hunter.py` (+5 files) every start.
- `maps_scraper_standalone.py::self_update()` re-downloads itself unless
  `SCRAPER_NO_UPDATE=1`.

So the supervisor runs the Hunter **directly** (`py precise_fiber_hunter.py`) and
sets `SCRAPER_NO_UPDATE=1` for the Scraper. **Trade-off, stated plainly:** the
Hunter no longer auto-updates from GitHub. To take an upstream build, run
`RUN_HUNTER.bat` once by hand, then re-apply:

```
py control\apply_hunter_fix.py        # idempotent, atomic
py control\apply_scraper_fix.py       # idempotent, atomic
```

### Rule: never edit these files in place

An edit that opened `precise_fiber_hunter.py` with mode `"w"` truncated it
instantly; a MemoryError landed before the rewrite and left the 400 KB Hunter at
**0 bytes** while the supervisor was trying to launch it. Restored from
`precise_fiber_hunter.py.bak-*`. Both patch scripts now write to a temp file,
parse it, then `os.replace` — and refuse to touch anything if an anchor is
missing or ambiguous.

### The fixes currently applied

| Fix | File | Why |
|---|---|---|
| open the map after login | `precise_fiber_hunter.py` | see §7 |
| within-run dedupe | `precise_fiber_hunter.py` | see §8 |
| folder orders hook | `precise_fiber_hunter.py` | see §10 |
| US-only addresses | `maps_scraper_standalone.py` | see §9 |
| local heartbeat mirror | `optimus_feed.py` | see §3 |

---

## 7. The Hunter waited forever for a map it never opened

Signing in drops you on `youachieve.att.com/yourefer/` — the **portal**, not the
map. `_wait_for_login()` only ever asked *"is the map showing?"* and slept. The
portal never becomes the map on its own, so a correct login still ended in
`LOGIN_TIMEOUT`. The Hunter already had `open_map_view()`; it was just never
called until *after* the wait succeeded — too late.

**Fixed:** the moment the login markers are gone, `_wait_for_login` navigates to
`MAP_URL` and opens the map itself (rate-limited to one attempt per 20s).

---

## 8. Dedupe was switched off, and it cost 81% of a day's work

Left behind from a test, in both write paths:

```python
_already = False  # key in seen  # DISABLED FOR TEST
# if key in seen:
#     continue
```

Measured on the live queue 2026-09-06: **83,500 captured records for 15,713 real
addresses — 81.2% duplicates**, one address written **80 times**. That is what
filled the production workbook to its 10,000,000-cell ceiling (the code's own
note: *"Precise Fiber is ~8.4M of the workbook's 10M cells… every write is
refused"*).

The **cross-run** check stays off on purpose (gold/grey must be re-classifiable).
The fix is a **within-run** set in `flush_local`: an address is written to the
JSONL once per run. Re-classifying the same address twice in one run cannot change
its answer, so nothing is lost.

---

## 9. The Scraper walked out of Texas and into Germany

`nearby_zips()` invents every numeric ZIP within ±2 SCF with no check that it is
real or American. It ran off the end of Houston's `77xxx` into **77694 = Kehl,
Germany**. The guard was `target_zip in addr` — and a German address *does*
contain `77694`, so it passed. German notaries landed in `Maps Businesses`, and
invented ZIPs 32497–32500 were recorded as "done".

**Fixed:** searches pinned to `"<category> in <zip>, USA"`; `_US_ADDR_RE` requires
a real **US state code + ZIP** at the end (comma before the state optional —
`OKLAHOMA CITY OK 73129` is a real lead and a stricter version threw those away);
invented ZIPs removed from `maps_zips_done.json`.

---

## 10. Folder orders (remote control without walking to the PC)

`optimus_orders.py` — in the repo (pushed `c852285`) and on this PC. Drop into
`ORDERS.json` in the COMMAND CENTER folder:

```json
{"orders": [{"id": "u1", "machine": "LAPTOP-JLCQ24SO", "action": "resume"}]}
```

`resume` / `pause` / `stop` / `note` work — each maps onto a control the Hunter
already has on the keyboard. `claim` / `release` are **declined at that call site**
and say so in the RESULT file: territory lives in the sheet and the pause loop has
no spreadsheet handle. Anything outside the six words is ignored. The module has
no subprocess and cannot execute anything.

Verified live: this machine's order returned, another PC's filtered out,
`launch_missiles` rejected, RESULT written back.

**Two limits here:**
1. `find_folder()` searches the profile, Documents and drive letters — **not the
   Desktop**, which is where the folder is. Handled with the module's own
   `OPTIMUS_COMMAND_CENTER` override rather than by patching tested code.
2. **Google Drive is installed but not running** — no mount, no process. Until it
   is, that folder is local-only and orders from another machine will not arrive.

---

## 11. Where the leads actually go

| Workbook | ID | Holds |
|---|---|---|
| ATT FIBER LEADS | `1FhO2BTM…` | Maps Businesses, Fiber Green Biz, Upgrade Orange Biz |
| ATT FIBER LEADS — Precise Fiber | `1DXu-nuQ…` | Precise Fiber, Grey Fiber Customers, Gold Confirmed, Hunter Status |
| OPTIMUS LEADS — TEXAS | `1qMjCktl…` | Green / Gold / Grey / Biz / Fiber Biz — **empty, see §12** |
| OPTIMUS LEADS — NON-TEXAS | `1kE7Xsjc…` | same — **empty, see §12** |

The Hunter writes to `precise_addresses.jsonl` locally; a **separate uploader
process** ships it (`uploader_log.txt` is the receipt). So an empty workbook does
**not** mean the hunt is failing — check the uploader log first. If the uploader
is not running, capture piles up locally and **nothing** reaches Google.

Verified 2026-09-06: **6,132 rows written, 2,957 new GREEN**, Houston 77070,
including commercial suites (`10927 LOUETTA RD STE 220/170/140`).

---

## 12. The TX / non-TX split already exists — and is empty

`maps_scraper_standalone.py` already carries it (added 2026-09-05):

```python
TX_SHEET_ID     = "1qMjCktl..."   # OPTIMUS LEADS - TEXAS
NONTX_SHEET_ID  = "1kE7Xsjc..."   # OPTIMUS LEADS - NON-TEXAS
TX_ZIP_PREFIXES = ("75","76","77","78","79","733")
```

Both workbooks open and are shared with the service account. Both contain **one
empty "Untitled" tab**.

**Cause: there is no GoHighLevel token on this machine.** The rebuild is
GHL-driven; the loader looks for `maps_scraper\ghl_token.txt`, then
`GHL_PIT_TOKEN`. Neither exists, and nothing on disk holds a `pit-` token. With no
token the whole GHL STATUS step returns quietly — empty sheets, no explanation.

**Fix (Patrick's action — a token cannot be generated from here):** GHL → Settings
→ Private Integrations → token with contacts read scope → save as one line in
`C:\Users\patri\maps_scraper\ghl_token.txt`. The next Scraper launch rebuilds both
workbooks. The GHL location itself is healthy: `xZj500PjsflIQg2j9f9D` / T-OPTIMUS /
Houston TX 77070, verified live.

> **Do not add a second TX/non-TX mechanism.** A "Precise Fiber NON-TX" tab was
> briefly added to the Hunter during this session and has been **reverted**. The
> split belongs to the Scraper's state workbooks. Two mechanisms for one job is
> how the gold/grey tabs drifted apart.

---

## 13. The AT&T login — the one manual step

Chromium runs on a persistent profile at `optimus_hunter/att_profile`, so the
session survives restarts. Everything before and after the password — clicking
`AT&T Employee`, opening the Fiber Map, resuming the scan — is automatic.

`att_login.py` (2026-09-06) does the sign-in itself:

```
stop the hunter  ->  py att_login.py  ->  restart the hunter
```

It reads `optimus_hunter\ATT_LOGINS.txt` (`username:` / `password:`, several
formats, multiple accounts via `--account`), never prints the password, refuses to
run while the Hunter holds the profile (exit 3), and stops with the screen text
printed and the window left open on anything unexpected — including MFA, which it
cannot and will not answer.

**Tested:** credential parsing, MFA detection, the profile-lock guard.
**Untested:** the live AT&T flow — it needs the credentials file.

> **One caution, concrete:** `optimus_hunter/` is wired to a **public** GitHub repo
> (the launcher pulls `raw.githubusercontent.com` with no auth; the Hunter pushes
> heartbeats there). Anything in that folder can end up public, and an AT&T Global
> Logon is an *employee* credential governing far more than the fiber map. Keep
> credentials in `optimus\control\` or `ATT_LOGINS.txt` — never commit them.

---

## 14. OpenClaw — researched, not installed

Real project, but **the name is contested**, so nothing was installed:

| Project | What it is |
|---|---|
| `openclaw/openclaw` | The real one. Local AI agent, OpenClaw Foundation. `irm https://openclaw.ai/install.ps1 \| iex` |
| `openclaw/openclaw-windows-node` | **Official Windows companion** — screen capture, shell, Chromium control; runs a **local MCP server** + `winnode` CLI; gateway `ws://localhost:18789` |
| `wzdavid/…`, `agentkernel/…`, `ValueCell-ai/ClawX`, `niteshdangi/…` | Third-party wrappers. Not official. |
| `OpenClaw` (older) | Unrelated — a reimplementation of the 1997 *Captain Claw* game |

**Prerequisites on this PC:** `node` NOT installed, `npm` NOT installed, WSL NOT
installed, 9.3 GB disk free, **3.8 GB RAM**. Adding a Node gateway + companion
will compete with the Hunter for the exact resource already freezing it.

Installer reviewed (88 KB / 2,307 lines): legitimate, pulls Node from
`nodejs.org`, installs via winget/choco/npm.

**Blocked:** the Claude Code auto-mode permission classifier refuses software
installs. Patrick must run it himself:

```
! powershell -c "irm https://openclaw.ai/install.ps1 | iex"
```

The Control Center already probes `ws://localhost:18789` and will turn OpenClaw
green on its own the moment it answers.

---

## 15. Open blockers

| # | Blocker | Who | Effect until cleared |
|---|---|---|---|
| 1 | `optimus_hunter\ATT_LOGINS.txt` missing | Patrick | Hunter parks on the AT&T chooser; **no leads at all** |
| 2 | `maps_scraper\ghl_token.txt` missing | Patrick | TX + NON-TX workbooks stay empty |
| 3 | OpenClaw install blocked by the permission classifier | Patrick | no Windows control layer |
| 4 | Google Drive installed but not running | Patrick | folder orders are local-only |
| 5 | 3.8 GB RAM | hardware | Scraper cannot run beside the Hunter |
