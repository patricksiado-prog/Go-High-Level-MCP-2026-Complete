#!/usr/bin/env python3
"""optimus_summary.py -- THE DATA SUMMARY CONVERTER.

WHY THIS EXISTS: the production leads sheet ("ATT FIBER LEADS") is 180k+ rows,
which is too big for Google to export -- so Claude (or any tool) can't read it
whole (Google returns "File too large for export"). This is the standard fix for
that known limitation: run a small job ON THE MACHINE (where gspread can page
through the sheet with NO size limit), compute the analysis, and write a SMALL
sheet -- "OPTIMUS DATA SUMMARY" -- that Claude reads fully in one shot.

It uses the SAME google_creds.json the hunter already uses -- no new setup, no
token. The service account creates + owns the small summary sheet and shares it
with Patrick; Claude finds it by its fixed title and reads it.

Run once:            python optimus_summary.py
Keep it fresh:       python optimus_summary.py --loop 15      (refresh every 15 min)
"""
import os
import sys
import time
import argparse
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Reuse the hunter's proven helpers (creds picker, sheet id, tab names, updater).
try:
    from precise_fiber_hunter import (
        find_creds, SHEET_ID, SCOPES, OUT_TAB, MAPS_TAB,
        GREEN_BIZ_TAB, ORANGE_BIZ_TAB, self_update)
    try:
        from precise_fiber_hunter import GOLD_TAB
    except Exception:
        # 'Gold Dots' is RETIRED and contaminated with gold-by-default rows
        # (BRAIN 22.14). Falling back to it reported bad gold as good.
        GOLD_TAB = "Gold Confirmed"
except Exception as _e:  # pragma: no cover - only if run outside the suite
    print("Could not import hunter helpers (%s). Run this from the optimus folder."
          % str(_e)[:120])
    raise

SUMMARY_TITLE = "OPTIMUS DATA SUMMARY"
OWNER_EMAIL = "patricksiado@gmail.com"


def _last10(s):
    """Last 10 digits of a phone (for unique-by-phone dedupe)."""
    d = re.sub(r"\D", "", s or "")
    return d[-10:] if len(d) >= 10 else ""


def _zip_of(addr):
    """First 5-digit run in an address = its ZIP (Maps rows carry a ZIP)."""
    m = re.search(r"\b(\d{5})\b", addr or "")
    return m.group(1) if m else ""


def _col_idx(header, name):
    """1-based column index for a header name (case-insensitive), else None."""
    for i, h in enumerate(header):
        if (h or "").strip().lower() == name.strip().lower():
            return i + 1
    return None


def _client():
    import gspread
    from google.oauth2.service_account import Credentials
    cf = find_creds()
    if not cf:
        print("No valid google_creds.json found -- cannot read the sheet. "
              "Drop the fiberscanner key at ~/optimus/google_creds.json.")
        return None
    print("Using creds: %s" % cf)
    try:
        return gspread.authorize(
            Credentials.from_service_account_file(cf, scopes=SCOPES))
    except Exception as e:
        print("  (auth failed: %s)" % str(e)[:100])
        return None


def compute(client):
    """Read the big sheet in pages and return a small dict of stats."""
    sh = client.open_by_key(SHEET_ID)
    out = {}

    # -- Precise Fiber: count dots by color (one column read, not the whole tab) --
    try:
        ws = sh.worksheet(OUT_TAB)
        header = ws.row_values(1)
        cc = _col_idx(header, "Dot Color") or 2
        colors = ws.col_values(cc)[1:]  # drop header
        up = [(c or "").strip().upper() for c in colors]
        out["precise_total"] = len(up)
        out["precise_green"] = sum(1 for c in up if c == "GREEN")
        out["precise_orange"] = sum(1 for c in up if c == "ORANGE")
        out["precise_grey"] = sum(1 for c in up if c in ("GREY", "GRAY"))
    except Exception as e:
        out["precise_error"] = str(e)[:140]

    # -- Green/Orange biz tabs: rows + UNIQUE by phone (these tabs are small) --
    for tab, key in ((GREEN_BIZ_TAB, "green_biz"), (ORANGE_BIZ_TAB, "orange_biz")):
        try:
            ws = sh.worksheet(tab)
            header = ws.row_values(1)
            pc = _col_idx(header, "Phone") or 2
            phones = ws.col_values(pc)[1:]
            uniq = set(p for p in (_last10(x) for x in phones) if p)
            out[key + "_rows"] = len(phones)
            out[key + "_unique"] = len(uniq)
        except Exception as e:
            out[key + "_error"] = str(e)[:140]

    # -- Maps Businesses: total + top ZIPs (where coverage is) --
    try:
        ws = sh.worksheet(MAPS_TAB)
        header = ws.row_values(1)
        ac = (_col_idx(header, "Address") or _col_idx(header, "Company Address")
              or _col_idx(header, "Full Address") or 3)
        addrs = ws.col_values(ac)[1:]
        out["maps_total"] = len(addrs)
        zc = {}
        for a in addrs:
            z = _zip_of(a)
            if z:
                zc[z] = zc.get(z, 0) + 1
        out["maps_by_zip"] = sorted(zc.items(), key=lambda kv: -kv[1])[:15]
    except Exception as e:
        out["maps_error"] = str(e)[:140]

    return out


def render_rows(out):
    """Turn the stats dict into rows for the summary sheet + a text block."""
    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    rows = [
        ["OPTIMUS DATA SUMMARY", ""],
        ["Updated", stamp],
        ["", ""],
        ["PRECISE FIBER  (every captured dot)", ""],
        ["  Total dots captured", out.get("precise_total", "?")],
        ["  GREEN  (new-fiber lead)", out.get("precise_green", "?")],
        ["  ORANGE (gold / copper upgrade)", out.get("precise_orange", "?")],
        ["  GREY   (existing fiber customer)", out.get("precise_grey", "?")],
        ["", ""],
        ["CALLABLE BUSINESS MATCHES  (deduped by phone)", ""],
        ["  Fiber Green Biz - raw rows", out.get("green_biz_rows", "?")],
        ["  Fiber Green Biz - UNIQUE phones", out.get("green_biz_unique", "?")],
        ["  Upgrade Orange Biz - raw rows", out.get("orange_biz_rows", "?")],
        ["  Upgrade Orange Biz - UNIQUE phones", out.get("orange_biz_unique", "?")],
        ["", ""],
        ["MAPS BUSINESSES scraped - total", out.get("maps_total", "?")],
        ["", ""],
        ["TOP ZIPS scraped (business count)", ""],
    ]
    for z, n in out.get("maps_by_zip", []):
        rows.append(["  " + z, n])
    for k in sorted(out):
        if k.endswith("_error"):
            rows.append(["NOTE (" + k + ")", out[k]])
    return rows


def collect_leads(client, cap=8000):
    """Read the callable lead tabs IN FULL, dedup by phone, tag GREEN/GOLD.
    These tabs are small (a few thousand rows) so the REAL rows -- not a summary --
    fit in a sheet Claude reads completely. GREEN = new-fiber lead, GOLD = copper
    upgrade. Deduped by last-10-of-phone so each business appears once."""
    sh = client.open_by_key(SHEET_ID)
    header = ["Type", "Business Name", "Phone", "Address", "Website", "Category"]
    seen = set()
    rows = []
    for tab, typ in ((GREEN_BIZ_TAB, "GREEN"), (ORANGE_BIZ_TAB, "GOLD")):
        try:
            vals = sh.worksheet(tab).get_all_values()
        except Exception:
            continue
        if not vals:
            continue
        hdr = vals[0]

        def ci(name):
            for i, h in enumerate(hdr):
                if (h or "").strip().lower() == name.lower():
                    return i
            return None

        bi, pi, ai = ci("Business Name"), ci("Phone"), ci("Address")
        wi, cti = ci("Website"), ci("Category")

        def g(r, i):
            return (r[i] if (i is not None and i < len(r)) else "") or ""

        for r in vals[1:]:
            ph = _last10(g(r, pi))
            key = ph or (g(r, bi) + "|" + g(r, ai)).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append([typ, g(r, bi), g(r, pi), g(r, ai), g(r, wi), g(r, cti)])
            if len(rows) >= cap:
                break
        if len(rows) >= cap:
            break
    return header, rows


def _street_core(addr):
    """Strip the leading house number -> street name, for clustering gold dots."""
    a = (addr or "").strip()
    m = re.match(r"^\s*\d+\s+(.*)$", a)
    return (m.group(1) if m else a).strip().upper()


def collect_gold_addresses(client, cap=20000):
    """Pull JUST the GOLD (ORANGE) dot addresses out of the big Precise Fiber tab
    -- a small slice (most dots are green) -- so Claude can see WHERE the gold is
    and spot new-fiber clusters. Returns (unique gold addresses, top gold streets).
    Reads two columns (Address + Dot Color); ORANGE = copper-upgrade = the tell.
    Reads the canonical gold tab (GOLD_TAB). It does NOT fall back to scanning
    Precise Fiber: that tab is GREEN ONLY as of 2026-08-26, so an ORANGE scan
    there matches nothing while reading two 474k-row columns to prove it."""
    sh = client.open_by_key(SHEET_ID)
    gold, seen = [], set()
    # fast path: the dedicated Gold Dots tab (every gold dot, already isolated)
    try:
        gw = sh.worksheet(GOLD_TAB)
        for a in gw.col_values(1)[1:]:       # col A = Address, skip header
            a = (a or "").strip()
            if not a or a.upper() in seen:
                continue
            seen.add(a.upper())
            gold.append(a)
            if len(gold) >= cap:
                break
    except Exception:
        gold = []
    # There is deliberately NO fallback to Precise Fiber. Every colour used to
    # land there, so scanning it for ORANGE once made sense; since 2026-08-26 it
    # is green-only and that scan can only ever return nothing -- after pulling
    # roughly a million cells. If GOLD_TAB is empty, say so instead.
    if not gold:
        print("   (no gold found in %r -- gold lives only on that tab now; "
              "if it looks empty, the sheet may be out of cells: run "
              "FREE_SPACE.bat)" % GOLD_TAB)
    clusters = {}
    for a in gold:
        core = _street_core(a)
        if core:
            clusters[core] = clusters.get(core, 0) + 1
    top = sorted(clusters.items(), key=lambda kv: -kv[1])[:50]
    return gold, top


def _open_summary_sheet(client):
    """Create/reuse the 'OPTIMUS DATA SUMMARY' sheet and share it with Patrick."""
    sh = None
    try:
        sh = client.open(SUMMARY_TITLE)          # reuse by title
    except Exception:
        sh = None
    if sh is None:
        try:
            sh = client.create(SUMMARY_TITLE)
            print("Created the summary sheet: %s" % SUMMARY_TITLE)
        except Exception as e:
            print("  (couldn't create the summary sheet: %s)" % str(e)[:120])
            return None
    try:
        sh.share(OWNER_EMAIL, perm_type="user", role="writer")
    except Exception:
        pass
    return sh


def _write_tab(sh, title, rows, first=False):
    """Overwrite one tab with rows (clear + write). first=True reuses sheet1."""
    ws = None
    try:
        ws = sh.worksheet(title)
    except Exception:
        ws = None
    if ws is None:
        if first:
            ws = sh.sheet1
            try:
                ws.update_title(title)
            except Exception:
                pass
        else:
            need = max(len(rows) + 5, 100)
            wide = max((len(r) for r in rows), default=2)
            ws = sh.add_worksheet(title=title, rows=str(need), cols=str(wide))
    try:
        ws.clear()
    except Exception:
        pass
    if not rows:
        rows = [["(none)"]]
    try:
        ws.update(values=rows, range_name="A1")     # newer gspread
    except TypeError:
        ws.update("A1", rows)                         # older gspread


def run_once(client):
    out = compute(client)
    stat_rows = render_rows(out)
    print("\n==================== OPTIMUS DATA SUMMARY ====================")
    for r in stat_rows:
        a = str(r[0]); b = "" if len(r) < 2 else str(r[1])
        print(("  %-42s %s" % (a, b)).rstrip())
    print("==============================================================")

    sh = _open_summary_sheet(client)
    if sh is None:
        return out
    _write_tab(sh, "Summary", stat_rows, first=True)
    # the REAL deduped leads (not a summary) -- Claude reads these row by row
    try:
        lead_hdr, lead_rows = collect_leads(client)
        _write_tab(sh, "Callable Leads", [lead_hdr] + lead_rows)
        print("Wrote %d unique callable leads to the 'Callable Leads' tab."
              % len(lead_rows))
    except Exception as e:
        print("  (leads tab hiccup: %s)" % str(e)[:120])
    # GOLD DOT ADDRESSES -- where the new fiber is. The actual ORANGE addresses
    # (a small slice of the 418k) + the streets with the most gold (new-fiber
    # clusters). This is what lets Claude say "new fiber is hitting X street/area."
    try:
        gold_addrs, gold_streets = collect_gold_addresses(client)
        addr_rows = [["Gold Dot Address (copper upgrade = new-fiber tell)"]]
        addr_rows += [[a] for a in gold_addrs]
        _write_tab(sh, "Gold Dot Addresses", addr_rows)
        hot = [["GOLD HOTSPOTS -- streets with the most gold (new fiber)", ""],
               ["Street", "Gold dots"]]
        hot += [[s, n] for s, n in gold_streets]
        _write_tab(sh, "Gold Hotspots", hot)
        print("Wrote %d gold-dot addresses + %d hotspot streets."
              % (len(gold_addrs), len(gold_streets)))
    except Exception as e:
        print("  (gold-address tab hiccup: %s)" % str(e)[:120])
    print("Summary sheet '%s' (id %s) -- shared with %s."
          % (SUMMARY_TITLE, sh.id, OWNER_EMAIL))
    return out


def main():
    self_update()  # canonical: git first, HTTPS raw fallback (see the brain)
    ap = argparse.ArgumentParser(description="Optimus data summary converter")
    ap.add_argument("--loop", type=float, default=0,
                    help="refresh every N minutes (0 = run once)")
    ap.add_argument("--no-update", action="store_true",
                    help="skip the self-update (the launcher already curled fresh)")
    args = ap.parse_args()

    client = _client()
    if client is None:
        sys.exit(1)

    if args.loop and args.loop > 0:
        print("Refreshing the summary every %g minutes (close the window to stop)."
              % args.loop)
        while True:
            try:
                run_once(client)
            except Exception as e:
                print("  (summary hiccup, will retry: %s)" % str(e)[:120])
            time.sleep(args.loop * 60)
    else:
        run_once(client)


if __name__ == "__main__":
    main()
