#!/usr/bin/env python3
"""
sheet_feed.py  --  feed the ATT FIBER LEADS sheet to Claude in LITTLE CHUNKS.

Claude's remote sessions have no Google creds, and pulling whole tabs has
killed sessions twice (CLAUDE.md). This runs ON PATRICK'S PC (which has
google_creds.json AND the hunter's GitHub token) and publishes small JSON
files to the repo via gh_put, so Claude reads bounded chunks from GitHub
instead of touching the sheet at all.

USAGE (from the hunter folder)
  python sheet_feed.py
      Publish a SNAPSHOT: every tab's name + row count, plus for each core
      tab the header and the last 25 rows. Small (few KB). Run it whenever
      Claude asks "what's in the sheet right now".

  python sheet_feed.py --tab "Gold Confirmed"
      Publish that tab IN FULL, in chunks of --n rows (default 500) --
      _feed/sheet/chunk_001.json, chunk_002.json, ... capped at --max-rows
      (default 5000) so a fat tab can't blow up the push.

  python sheet_feed.py --match "Beaumont,Angleton,La Porte,Devonwood"
      Publish ONLY the rows whose address or city contains one of those,
      newest first. Add --color GREEN for fiber-eligible non-customers only.
      This is the one to run when Claude asks "what's new in <town>".

  python sheet_feed.py --tab "Precise Fiber" --start 12000 --n 500
      Publish one chunk: 500 rows starting at row 12000.

WHERE IT LANDS (Claude reads these off the repo)
  optimus/_feed/sheet/snapshot.json        the snapshot
  optimus/_feed/sheet/chunk_NNN.json       chunked tab reads
"""
import json
import re
import sys
import time

from precise_fiber_hunter import open_sheet, gh_put

CORE_TABS = ["Precise Fiber", "Gold Confirmed", "Grey Fiber Customers",
             "Unknown Customers", "Maps Businesses", "Fiber Green Biz",
             "Upgrade Orange Biz"]
FEED_DIR = "optimus/_feed/sheet"
TAIL_ROWS = 25          # rows of tail shown per tab in the snapshot
CHUNK_DEFAULT = 500
MAX_ROWS_DEFAULT = 5000


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def _publish(path, obj):
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if len(text) > 800_000:
        print("   (%s would be %dKB -- too big, narrow the chunk with --n)"
              % (path, len(text) // 1000))
        return False
    ok = gh_put(path, text)
    print("   %s %s (%dKB)" % ("pushed" if ok else "PUSH FAILED:", path,
                               max(1, len(text) // 1000)))
    return ok


def snapshot(ss):
    """Small overview of the whole sheet: tab list + counts + tails."""
    out = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "tabs": []}
    for ws in ss.worksheets():
        entry = {"title": ws.title}
        try:
            colA = ws.col_values(1)
            entry["rows"] = len(colA)
        except Exception as e:
            entry["error"] = str(e)[:60]
            out["tabs"].append(entry)
            continue
        if ws.title in CORE_TABS and entry["rows"]:
            try:
                first = 2 if entry["rows"] > 1 else 1
                start = max(first, entry["rows"] - TAIL_ROWS + 1)
                rng = "A%d:M%d" % (start, entry["rows"])
                entry["header"] = ws.row_values(1)
                entry["tail_from_row"] = start
                entry["tail"] = ws.get(rng)
            except Exception as e:
                entry["tail_error"] = str(e)[:60]
        out["tabs"].append(entry)
        print("   %-24s %s rows" % (ws.title, entry.get("rows", "?")))
    _publish(FEED_DIR + "/snapshot.json", out)


def chunk_tab(ss, title, start, n, max_rows):
    """Publish rows of one tab in bounded chunks."""
    try:
        ws = ss.worksheet(title)
    except Exception:
        print("No tab named %r. Tabs: %s"
              % (title, ", ".join(w.title for w in ss.worksheets())))
        return
    total = len(ws.col_values(1))
    header = ws.row_values(1)
    if start is None:            # whole tab (capped)
        start = 2
        end_cap = min(total, start + max_rows - 1)
    else:
        start = max(2, int(start))
        end_cap = min(total, start + int(_arg("--rows", n)) - 1) \
            if _arg("--rows") else min(total, start + n - 1)
    i, part = start, 1
    while i <= end_cap:
        j = min(i + n - 1, end_cap)
        rows = ws.get("A%d:M%d" % (i, j))
        _publish(FEED_DIR + "/chunk_%03d.json" % part,
                 {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "tab": title,
                  "total_rows": total, "header": header,
                  "from_row": i, "to_row": j, "rows": rows})
        i = j + 1
        part += 1
    if end_cap < total and _arg("--start") is None:
        print("   (stopped at row %d of %d -- rerun with --start %d for more)"
              % (end_cap, total, end_cap + 1))


def match_rows(ss, needles, color=None, newest=200):
    """Pull just the rows whose ADDRESS or CITY contains one of `needles`.

    This is the question Patrick actually asks -- "what's new in Beaumont,
    Angleton, La Porte, near Devonwood" -- and it is unanswerable any other way
    from here: Precise Fiber is ~474k rows and nothing can pull it whole. This
    reads the columns once ON HIS PC, filters locally, sorts NEWEST FIRST by
    Captured At, and publishes a small JSON that Claude can read off GitHub.

    Precise Fiber layout: A=Address B=Dot Color C=Captured At D=Business
    E=Phone F=Run ID G=Operator H=Lat I=Lng J=City K=State L=ZIP
    """
    try:
        ws = ss.worksheet("Precise Fiber")
    except Exception:
        print("No 'Precise Fiber' tab."); return
    print("   reading Precise Fiber (one pass, this can take a minute)...")
    rows = ws.get_all_values()
    if not rows:
        print("   (empty)"); return
    heads = [h.strip().lower() for h in rows[0]]
    hit = []
    lowered = [n.strip().lower() for n in needles if n.strip()]
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        addr = r[0].lower()
        city = r[9].lower() if len(r) > 9 else ""
        if not any(n in addr or n in city for n in lowered):
            continue
        if color and (len(r) < 2 or r[1].strip().upper() != color.upper()):
            continue
        hit.append(r)
    # NEWEST FIRST -- "newer fiber" is the whole point of the question
    hit.sort(key=lambda r: (r[2] if len(r) > 2 else ""), reverse=True)
    print("   %d row(s) matched %s%s"
          % (len(hit), needles, (" color=" + color) if color else ""))
    if not hit:
        return
    slug = "-".join(re.sub(r"[^a-z0-9]+", "", n.lower())[:12]
                    for n in lowered)[:60] or "match"
    _publish(FEED_DIR + "/match_%s.json" % slug,
             {"at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "needles": needles, "color": color,
              "total_matched": len(hit), "returned": min(len(hit), newest),
              "header": rows[0], "rows": hit[:newest]})


def main():
    match = _arg("--match")        # e.g. --match "Beaumont,Angleton,La Porte"
    color = _arg("--color")        # e.g. --color GREEN
    tab = _arg("--tab")
    start = _arg("--start")
    n = int(_arg("--n", CHUNK_DEFAULT))
    max_rows = int(_arg("--max-rows", MAX_ROWS_DEFAULT))

    sh = open_sheet()
    if sh is None:
        print("Could not open the sheet (check google_creds.json)."); return
    ss = getattr(sh, "spreadsheet", sh)

    if match:
        match_rows(ss, [x for x in match.split(",") if x.strip()], color=color)
    elif tab:
        chunk_tab(ss, tab, start, n, max_rows)
    else:
        snapshot(ss)
    print("Done. Claude reads these from optimus/_feed/sheet/ on GitHub.")


if __name__ == "__main__":
    main()
