"""decode_gold.py -- answer the `unavailable` question from data already on disk.

WHY
    Gold is decided by curr_ntwrk_bld_type_cd. AT&T's most common value for it
    is the literal string "unavailable", which is in neither the fiber nor the
    copper list, so every customer carrying it has been guessed at -- wrongly,
    in both directions.

    The hunter already saves AT&T's raw reply to serviceability_raw.json on
    every run. That file is the evidence. This reads it, cross-tabulates build
    code against whether the record has a subscriber account, and pushes the
    summary where Claude can read it.

RUN IT (in your optimus_hunter folder):

    py decode_gold.py

READ-ONLY on your data. It never touches the sheet or the map. The subscriber
BAN is reduced to yes/no before anything leaves the machine -- the account
number itself is never uploaded.
"""
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

REPO = "patricksiado-prog/Go-High-Level-MCP-2026-Complete"
BRANCH = "claude/optimus-map-tools-setup-6dcl6o"
CANDIDATES = ("serviceability_raw.json", "serviceability_raw.txt",
              "net_last_body.json", "last_response.json")


def find_file():
    here = os.getcwd()
    try:
        here = os.path.dirname(os.path.abspath(__file__)) or here
    except NameError:
        pass
    home = os.path.expanduser("~")
    for d in (here, os.path.join(home, "optimus_hunter"),
              os.path.join(home, "optimus", "repo", "optimus"), home, "."):
        for name in CANDIDATES:
            p = os.path.join(d, name)
            if os.path.exists(p) and os.path.getsize(p) > 20:
                return p
    return None


def gh_token():
    home = os.path.expanduser("~")
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        here = os.getcwd()
    for d in (here, os.path.join(home, "optimus_hunter"),
              os.path.join(home, "Downloads"), home):
        p = os.path.join(d, "github_token.txt")
        if os.path.exists(p):
            return open(p).read().strip()
    return None


def gh_put(token, path, text):
    api = "https://api.github.com/repos/%s/contents/%s" % (REPO, path)
    hdr = {"Authorization": "token " + token, "User-Agent": "optimus-decode",
           "Accept": "application/vnd.github+json"}
    sha = None
    try:
        req = urllib.request.Request(api + "?ref=" + BRANCH, headers=hdr)
        with urllib.request.urlopen(req, timeout=25) as r:
            sha = json.load(r).get("sha")
    except Exception:
        pass
    body = {"message": "decode: " + path, "branch": BRANCH,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    if sha:
        body["sha"] = sha
    try:
        req = urllib.request.Request(api, data=json.dumps(body).encode("utf-8"),
                                     headers=hdr, method="PUT")
        with urllib.request.urlopen(req, timeout=40):
            return True
    except Exception as e:
        print("   push failed: %s" % str(e)[:90])
        return False


def has_account(rec):
    """True when this record carries a real subscriber account."""
    for k, v in rec.items():
        if "ban" in str(k).lower():
            b = str(v or "").strip().lower()
            if b and b not in ("", "-", "0", "n/a", "na", "none", "null",
                               "false", "unavailable", "unknown"):
                return True
    return False


def push_net_log(token):
    """Send the endpoint log. This is what says whether AT&T was ever ASKED.

    A sweep that pans 150 cells and decodes 0 leads has two very different
    causes: the request is never made, or it is made and the reply cannot be
    read. The endpoint list separates them in one look, and it is the one file
    that never leaves the field PC.
    """
    log = None
    for d in _dirs():
        q = os.path.join(d, "net_responses.log")
        if os.path.exists(q):
            log = q
            break
    if not log:
        print("(no net_responses.log found)")
        return
    body = open(log, encoding="utf-8", errors="replace").read()
    lines = [l for l in body.split("\n") if l.strip()]
    api = [l for l in lines if "fibermap" in l.lower() or ".cfc" in l.lower()
           or "/api/" in l.lower()]
    print("\nENDPOINT LOG: %d lines, %d look like an API call" % (len(lines), len(api)))
    if api:
        print("  API-ish endpoints seen:")
        for l in api[:15]:
            print("   ", l.strip()[:140])
    else:
        print("  *** NO API/fiberMap.cfc CALL IN THE WHOLE LOG ***")
        print("  AT&T was never asked for dot data, so a zero is guaranteed")
        print("  no matter how many cells are swept.")
    tail = "\n".join(lines[-400:])
    if token:
        gh_put(token, "optimus/_feed/net_endpoints.txt",
               "lines=%d api_like=%d\n\nAPI-LIKE:\n%s\n\nTAIL:\n%s"
               % (len(lines), len(api), "\n".join(api[:60]), tail))
        print("  pushed -> optimus/_feed/net_endpoints.txt")


def _dirs():
    home = os.path.expanduser("~")
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        here = os.getcwd()
    return [here, os.path.join(home, "optimus_hunter"), home, "."]


COLOR_HINTS = ("fttp", "fttn", "gpon", "ftth", "ip-rt", "iprt", "adsl", "vdsl",
               "unavailable", "curr_ntwrk_bld_type_cd", "subscriber_ban",
               "orange", "#f", "gold", "grey", "gray", "copper")


def find_color_rule(token):
    """Read AT&T's OWN dot-colouring rule out of their map JavaScript.

    This is the one source that cannot be wrong. Their map paints gold and grey
    correctly from the same payload we receive, so the rule that separates them
    is in their code -- already downloaded into the browser. Everything else we
    have is reverse-engineering; this is the original.

    Looks for the bundle in the browser cache the hunter's profile keeps, then
    pulls out every line mentioning the build-code field or a known code.
    """
    import glob
    roots = []
    home = os.path.expanduser("~")
    for d in (os.path.join(home, "optimus_hunter", "optimus_profile"),
              os.path.join(home, "optimus_hunter"), os.getcwd()):
        if os.path.isdir(d):
            roots.append(d)
    hits, scanned = [], 0
    for root in roots:
        for path in glob.glob(os.path.join(root, "**", "*"), recursive=True):
            if not os.path.isfile(path):
                continue
            if os.path.getsize(path) > 12 * 1024 * 1024:
                continue
            low = path.lower()
            if not (low.endswith(".js") or "cache" in low):
                continue
            scanned += 1
            try:
                blob = open(path, "rb").read().decode("utf-8", "ignore")
            except Exception:
                continue
            if "curr_ntwrk_bld_type_cd" not in blob and "fttp" not in blob.lower():
                continue
            for m in re.finditer(r".{220}(?:curr_ntwrk_bld_type_cd|fttp|fttn).{220}",
                                 blob, re.I | re.S):
                frag = " ".join(m.group(0).split())
                if frag not in hits:
                    hits.append(frag)
                if len(hits) >= 25:
                    break
            if len(hits) >= 25:
                break
    print("\n=== AT&T's OWN COLOUR RULE ===")
    print("scanned %d cached files" % scanned)
    if not hits:
        print("No colouring code found in the browser cache.")
        print("Open the Fiber Map once with dots visible, then run this again --")
        print("the bundle has to be cached before it can be read.")
        return
    print("%d fragment(s) mentioning the build-code field:" % len(hits))
    for h in hits[:6]:
        print("   ...%s..." % h[:260])
    if token:
        gh_put(token, "optimus/_feed/att_color_rule.txt",
               "AT&T map colouring fragments (%d)\n\n%s"
               % (len(hits), "\n\n---\n\n".join(hits)))
        print("  pushed -> optimus/_feed/att_color_rule.txt")


def main():
    path = find_file()
    _tok = gh_token()
    push_net_log(_tok)
    find_color_rule(_tok)
    if not path:
        return 1
    print("\nreading: %s  (%d bytes)" % (path, os.path.getsize(path)))
    raw = open(path, encoding="utf-8", errors="replace").read()
    try:
        data = json.loads(raw)
    except Exception as e:
        print("That file is not JSON (%s). First 200 chars:" % str(e)[:50])
        print(raw[:200])
        return 1

    content = data.get("content") if isinstance(data, dict) else data
    if not isinstance(content, list):
        print("No 'content' list. Top-level keys: %s"
              % ", ".join(sorted(data.keys()))[:200])
        return 1
    print("records: %d\n" % len(content))

    # THE CROSS-TAB. Build code against whether there is an account behind it.
    # A code that appears ONLY on non-customers is a green code and means
    # nothing for gold. A code that appears on customers is the one that has to
    # be decoded -- and if `unavailable` shows up on both, that alone is worth
    # knowing, because it means the field is not describing the subscriber.
    table, samples, fields = {}, {}, {}
    for rec in content:
        if not isinstance(rec, dict):
            continue
        code = ""
        for k, v in rec.items():
            if "bld_type" in str(k).lower() or "bld_typ" in str(k).lower():
                code = str(v or "").strip().lower()
        cust = has_account(rec)
        key = (code or "(none)", cust)
        table[key] = table.get(key, 0) + 1
        if key not in samples:
            red = {}
            for k, v in rec.items():
                red[k] = bool(str(v or "").strip()) if "ban" in str(k).lower() else v
            samples[key] = red
        for k, v in rec.items():
            if str(v or "").strip():
                fields[k] = fields.get(k, 0) + 1

    print("%-24s %10s %10s" % ("BUILD CODE", "CUSTOMER", "NON-CUST"))
    print("-" * 46)
    codes = sorted(set(c for c, _ in table))
    for c in codes:
        print("%-24s %10d %10d"
              % (c, table.get((c, True), 0), table.get((c, False), 0)))
    n_cust = sum(v for (c, cu), v in table.items() if cu)
    print("-" * 46)
    print("%-24s %10d %10d" % ("TOTAL", n_cust, len(content) - n_cust))
    print("\nfields ever populated: %s"
          % ", ".join("%s(%d)" % (k, v) for k, v in
                      sorted(fields.items(), key=lambda kv: -kv[1])))

    if not n_cust:
        print("\nNOTE: ZERO customers in this capture -- every record is a")
        print("non-customer (green). This view cannot answer the gold")
        print("question. Re-run the hunter over a street with ORANGE dots.")

    out = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "source_file": os.path.basename(path),
           "record_count": len(content),
           "customers": n_cust,
           "cross_tab": dict(("%s|%s" % (c, "customer" if cu else "non_customer"), v)
                             for (c, cu), v in table.items()),
           "field_fill": fields,
           "samples": dict(("%s|%s" % (c, "customer" if cu else "non_customer"), s)
                           for (c, cu), s in samples.items())}
    text = json.dumps(out, indent=1, default=str)
    token = gh_token()
    if token and gh_put(token, "optimus/_feed/decode_gold.json", text):
        print("\nPushed to optimus/_feed/decode_gold.json -- Claude can read it now.")
    else:
        p = os.path.join(os.path.dirname(path), "decode_gold.json")
        open(p, "w").write(text)
        print("\nNo GitHub token, so it was saved locally instead:\n   %s" % p)
        print("Send that file to Claude.")
    return 0


raise SystemExit(main())
