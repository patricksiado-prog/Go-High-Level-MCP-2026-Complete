#!/usr/bin/env python3
"""
backend_probe.py  --  capture the AT&T fiber map's BACKEND traffic (the same
data you'd see in the browser's F12 -> Network tab) and WRITE IT TO THE SHEET so
Claude can read + analyze it remotely -- no screenshots, no copy/paste.

It answers: which endpoint ships the dots? what type/size is it? what FIELDS does
the dot data carry (does the backend include the dot COLOR / status / address,
or only geometry)? That tells us whether the hunter can classify dots straight
from the server instead of guessing from pixels.

Writes a "Backend Capture" tab in the leads sheet:
  - ENDPOINT rows  : every URL the page hit, biggest first (the dot feed is
                     usually a large JSON/tile response)
  - TILE FIELDS    : the property names decoded from the Mapbox vector tiles
  - LEADS PARSED   : how many addresses came off the wire + sample rows showing
                     whether status / lat / lng / ban are present
  - JSON TOP KEYS  : top-level keys of AT&T's serviceability JSON + a sample
It also saves serviceability_raw.json locally (the full raw response).

USAGE
  python backend_probe.py            # position map over DOTS, press Enter, it captures
  python backend_probe.py --pans 10  # pan more to trigger more fetches
Reuses the hunter's browser driver + NetCapture.
"""
import os
import json
import time
import socket
import argparse

from precise_fiber_hunter import (
    self_update, PROFILE_DIR, MAP_URL, VIEWPORT,
    open_map_view, on_map, mouse_drag, open_sheet, NetCapture,
)

HERE = os.path.dirname(os.path.abspath(__file__))
TAB = "Backend Capture"


def cap_tab(ws):
    """Get/create the 'Backend Capture' tab so the network analysis is readable
    on Drive. Returns a worksheet or None."""
    if ws is None:
        return None
    try:
        sh = ws.spreadsheet
        try:
            t = sh.worksheet(TAB)
            t.clear()
        except Exception:
            t = sh.add_worksheet(title=TAB, rows="2000", cols="6")
        t.append_row(["Time", "Kind", "URL / Field / Address", "Type", "Bytes/Count", "Sample"])
        return t
    except Exception as e:
        print("(Backend Capture tab unavailable: %s)" % str(e)[:70])
        return None


def w(t, row):
    if t is None:
        return
    try:
        t.append_row([str(c)[:480] for c in row])
    except Exception:
        pass


def main():
    self_update()
    ap = argparse.ArgumentParser(description="Capture the AT&T map backend traffic to the sheet.")
    ap.add_argument("--pans", type=int, default=6, help="pans to trigger backend fetches (default 6)")
    ap.add_argument("--auto", action="store_true", help="no 'press Enter' pause")
    ap.add_argument("--no-update", action="store_true", help="skip the GitHub auto-pull on start")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, viewport=VIEWPORT,
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        cap = NetCapture(debug=True)            # logs every response + decodes dot data
        page.on("response", cap.handle)

        print("Opening the AT&T fiber map ...")
        page.goto(MAP_URL, timeout=60000)
        time.sleep(4)
        open_map_view(page)
        time.sleep(2)
        if not on_map(page):
            open_map_view(page)
            time.sleep(2)

        if not args.auto:
            try:
                input("\nPosition the map over a DOTTED area, then press Enter to capture ... ")
            except EOFError:
                pass

        print("Capturing backend traffic (panning to trigger the dot fetches)...")
        dirs = ["right", "down", "left", "down", "right", "up", "left", "up"]
        for i in range(max(1, args.pans)):
            mouse_drag(page, dirs[i % len(dirs)])
            time.sleep(1.8)

        # write everything to the sheet so Claude can read it
        ws = open_sheet()
        t = cap_tab(ws)
        host = socket.gethostname()
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        w(t, [ts, "START", host, "", "", "F12/network capture"])

        # 1) endpoints the page hit, biggest first (the dot feed is usually big)
        rows = sorted(cap.seen_urls.items(), key=lambda kv: -kv[1][2])
        for base, (ct, hits, mx) in rows[:25]:
            w(t, [ts, "ENDPOINT", base, ct, "%d B / %d hits" % (mx, hits), ""])

        # 2) vector-tile property field names (the dot data schema)
        if cap.tile_keys:
            w(t, [ts, "TILE FIELDS", ", ".join(sorted(cap.tile_keys)), "",
                  "%d fields" % len(cap.tile_keys), ""])
        if cap.tile_status:
            for base, note in list(cap.tile_status.items())[:8]:
                w(t, [ts, "TILE DECODE", base, note, "", ""])

        # 3) addresses parsed off the wire + samples (status/lat/lng/ban present?)
        leads = cap.pending
        w(t, [ts, "LEADS PARSED", "", "", "%d" % len(leads), ""])
        for ld in leads[:6]:
            w(t, [ts, "SAMPLE LEAD", str(ld.get("address")),
                  "status=%s" % ld.get("status"),
                  "lat=%s lng=%s ban=%s" % (ld.get("lat"), ld.get("lng"), ld.get("ban")), ""])

        # 4) raw serviceability JSON (top keys + a sample), if NetCapture saved it
        raw = os.path.join(HERE, "serviceability_raw.json")
        if os.path.exists(raw):
            try:
                data = json.load(open(raw))
                keys = (list(data.keys()) if isinstance(data, dict)
                        else ["<list of %d>" % len(data)])
                w(t, [ts, "JSON TOP KEYS", ", ".join(map(str, keys)), "", "", ""])
                w(t, [ts, "JSON SAMPLE", "", "", "", json.dumps(data)[:1500]])
            except Exception:
                pass

        w(t, [ts, "DONE", host, "", "%d endpoints" % len(rows), "read the Backend Capture tab"])
        print("\nWrote the backend capture to the 'Backend Capture' tab in your sheet.")
        print("(Full raw AT&T response also saved locally -> serviceability_raw.json)")

        if not args.auto:
            try:
                input("Press Enter to close ... ")
            except EOFError:
                pass
        ctx.close()


if __name__ == "__main__":
    main()
