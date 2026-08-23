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


def main():
    path = find_file()
    if not path:
        print("No saved AT&T response found. Run the hunter once (it saves")
        print("serviceability_raw.json), then run this from that same folder.")
        return 1
    print("reading: %s  (%d bytes)" % (path, os.path.getsize(path)))
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
