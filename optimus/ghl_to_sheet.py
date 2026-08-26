#!/usr/bin/env python3
"""
ghl_to_sheet.py -- pull worked leads OUT of GoHighLevel and into the sheet.

WHY THIS EXISTS
GHL already holds what the sheet is missing: the phone number, the call notes,
the tags, whether the number is textable, and the pipeline stage. That data cost
nothing to produce -- DealMachine credits were already spent, or the number came
off Google Maps -- so pulling it back beats re-enriching anything.

WHERE IT WRITES  ->  the 'GHL Worked Leads' tab.
This tab is NOT hunter-owned. The hunter never writes it, so unlike Precise
Fiber or Gold Confirmed it is SAFE to sort, filter, colour and add disposition
columns to. That is the whole point: it is the one tab a human can mark up
without breaking the capture pipeline.

TWO WAYS TO GET THE DATA, tried in this order:

  1. LIVE from GHL, if GHL_PIT_TOKEN is set (the pit-... Private Integration
     token, same one ghl_loader.py uses). Pulls contacts by tag and fetches
     each contact's notes. Always current.

  2. THE PUBLISHED FILE optimus/_feed/ghl/worked_leads.json, committed to the
     repo by Claude, which has GHL access from its side. No token needed --
     this is the path that works on a fresh PC.

USAGE
  python ghl_to_sheet.py
      Dry run. Prints what it would write. Changes nothing.

  python ghl_to_sheet.py --yes
      Write the tab.

  python ghl_to_sheet.py --tag "dave new leads 08/26/2026" --yes
      Pull one specific tag (live mode only).
"""
import json
import os
import sys
import time

from precise_fiber_hunter import open_sheet, commit_rows

TAB = "GHL Worked Leads"
HEADER = ["Address", "Name", "Phone", "Email", "City", "State", "ZIP",
          "Lead Type", "Textable", "Tags", "Notes", "GHL Contact ID",
          "Last Updated", "DISPOSITION", "SOLD?", "Notes From Rep"]
# The last three are deliberately EMPTY and belong to the humans. The hunter
# never touches this tab, so anything typed there survives every sweep.
REP_COLS = 3
FEED_PATH = os.path.join("_feed", "ghl", "worked_leads.json")


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def from_file():
    """The no-token path: read what Claude published into the repo."""
    for path in (FEED_PATH, os.path.join("optimus", FEED_PATH)):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
            print("   read %d lead(s) from %s" % (len(rows), path))
            return rows
    print("   no published file at %s" % FEED_PATH)
    return []


def from_ghl(tag):
    """The live path. Needs GHL_PIT_TOKEN; returns [] without it."""
    token = os.environ.get("GHL_PIT_TOKEN")
    if not token:
        return []
    try:
        import urllib.request
        import urllib.parse
    except Exception:
        return []
    loc = os.environ.get("GHL_LOCATION_ID", "xZj500PjsflIQg2j9f9D")
    base = "https://services.leadconnectorhq.com"
    hdr = {"Authorization": "Bearer %s" % token,
           "Version": "2021-07-28", "Accept": "application/json"}

    def _get(url):
        req = urllib.request.Request(url, headers=hdr)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    out = []
    try:
        q = urllib.parse.urlencode({"locationId": loc, "query": tag, "limit": 100})
        data = _get("%s/contacts/?%s" % (base, q))
        for c in data.get("contacts", []):
            notes = ""
            try:                       # notes are per-contact; skip on failure
                nd = _get("%s/contacts/%s/notes" % (base, c.get("id")))
                notes = " | ".join((n.get("body") or "").replace("\n", " ")
                                   for n in nd.get("notes", []))[:1000]
            except Exception:
                pass
            dnd = ((c.get("dndSettings") or {}).get("SMS") or {})
            tags = c.get("tags") or []
            out.append({
                "address": c.get("address") or c.get("lastName") or "",
                "name": c.get("firstName") or "", "phone": c.get("phone") or "",
                "email": c.get("email") or "", "city": c.get("city") or "",
                "state": c.get("state") or "", "zip": c.get("postalCode") or "",
                "lead_type": ("GOLD upgrade" if "gold-dot" in tags
                              else "GREEN business" if "biz-call" in tags
                              else "GREEN residential"),
                "textable": ("NO - landline" if "30006" in (dnd.get("message") or "")
                             else "NO - DNC" if "dnc-flagged" in tags else "YES"),
                "tags": ",".join(tags), "notes": notes,
                "ghl_id": c.get("id"), "updated": (c.get("dateUpdated") or "")[:10],
            })
        print("   pulled %d lead(s) LIVE from GHL (tag %r)" % (len(out), tag))
    except Exception as e:
        print("   live GHL pull failed (%s) -- falling back to the file"
              % str(e)[:70])
        return []
    return out


def main():
    go = "--yes" in sys.argv
    tag = _arg("--tag", "dave new leads 08/26/2026")

    rows = from_ghl(tag) or from_file()
    if not rows:
        print("Nothing to write. Set GHL_PIT_TOKEN for a live pull, or ask "
              "Claude to publish %s." % FEED_PATH)
        return

    body = [[r.get("address", ""), r.get("name", ""), r.get("phone", ""),
             r.get("email", ""), r.get("city", ""), r.get("state", ""),
             r.get("zip", ""), r.get("lead_type", ""), r.get("textable", ""),
             r.get("tags", ""), (r.get("notes", "") or "")[:900],
             r.get("ghl_id", ""), r.get("updated", "")] + [""] * REP_COLS
            for r in rows]

    print("\n  %-32s %-11s %-17s %s" % ("ADDRESS", "PHONE", "TYPE", "TEXTABLE"))
    for b in body[:12]:
        print("  %-32s %-11s %-17s %s" % (b[0][:32], b[2], b[7], b[8]))
    if len(body) > 12:
        print("  ... +%d more" % (len(body) - 12))
    print("\n  %d lead(s) -> '%s'" % (len(body), TAB))

    if not go:
        print("  Dry run. Re-run with --yes to write.")
        return

    sh = open_sheet()
    if sh is None:
        print("Could not open the sheet (check google_creds.json).")
        return
    ss = getattr(sh, "spreadsheet", sh)
    try:
        ws = ss.worksheet(TAB)
        # Re-running must not duplicate. Keep whatever the reps typed in the
        # last columns by matching on phone, then rewrite the tab.
        keep = {}
        try:
            for row in ws.get_all_values()[1:]:
                if len(row) >= len(HEADER) and row[2]:
                    keep[row[2]] = row[-REP_COLS:]
        except Exception:
            pass
        for b in body:
            if b[2] in keep:
                b[-REP_COLS:] = keep[b[2]]
        ws.clear()
    except Exception:
        ws = ss.add_worksheet(title=TAB, rows=str(len(body) + 200),
                              cols=str(len(HEADER)))
        print("   created '%s'" % TAB)
    ws.update("A1", [HEADER], value_input_option="RAW")
    n, failed = commit_rows(ws, TAB, body)
    print("   wrote %d row(s)%s" % (n, (", %d parked" % failed) if failed else ""))
    print("   DISPOSITION / SOLD? / Notes From Rep are yours -- the hunter "
          "never writes this tab, so what you type there survives every sweep.")


if __name__ == "__main__":
    main()
