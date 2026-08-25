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

  python sheet_feed.py --tab "Precise Fiber" --start 12000 --n 500
      Publish one chunk: 500 rows starting at row 12000.

WHERE IT LANDS (Claude reads these off the repo)
  optimus/_feed/sheet/snapshot.json        the snapshot
  optimus/_feed/sheet/chunk_NNN.json       chunked tab reads
"""
import json
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


def main():
    tab = _arg("--tab")
    start = _arg("--start")
    n = int(_arg("--n", CHUNK_DEFAULT))
    max_rows = int(_arg("--max-rows", MAX_ROWS_DEFAULT))

    sh = open_sheet()
    if sh is None:
        print("Could not open the sheet (check google_creds.json)."); return
    ss = getattr(sh, "spreadsheet", sh)

    if tab:
        chunk_tab(ss, tab, start, n, max_rows)
    else:
        snapshot(ss)
    print("Done. Claude reads these from optimus/_feed/sheet/ on GitHub.")


if __name__ == "__main__":
    main()
