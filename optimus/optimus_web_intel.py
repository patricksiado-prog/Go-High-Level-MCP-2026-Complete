"""optimus_web_intel.py -- outage and new-build signals pulled off the open web.

WHY THIS EXISTS
---------------
The opening-intel banner used to read two Google Sheets tabs, `Outage Signals`
and `Fiber Zones`. Audited 2026-08-22: NEITHER TAB EXISTS and neither ever has.
So the banner printed "none open" and "no zone scans" on every launch, which
reads as "we checked and there is nothing" when the truth was "nothing was ever
checked". Patrick asked for the banner to go to the internet instead.

THE THREE RULES THIS MODULE OBEYS
---------------------------------
1. **It can never delay or break a sweep.** One wall-clock budget for ALL
   network work (default 6s). Past it, no further source is even started. Every
   call is wrapped. A machine that is offline, behind a captive portal or
   through a corporate proxy loses the intel and nothing else.
2. **It never fails silently.** Every source reports bytes, items parsed, and
   the reason on failure. That is the whole lesson of the tab bug above: a
   reader that returns [] and says nothing is worse than one that crashes.
3. **Results are cached with a TTL** so relaunching the hunter ten times in an
   hour costs one fetch, not ten.

STATUS OF THE SOURCE LIST
-------------------------
The sandbox this was written in blocks all outbound hosts, so the feeds below
could NOT be live-verified. They are therefore *data*, not logic, and every
parser is defensive. Run `python optimus_web_intel.py --test` on a real machine:
it prints exactly which sources answered, how many items each yielded and why
any failed. Prune the list from that output rather than from guesswork.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request

_STALE = []       # an expired cache, held in case the network is unreachable

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Optimus territory. A national AT&T outage story is noise; a Beaumont one is work.
TERRITORY = (
    "houston", "beaumont", "angleton", "clute", "brazoria", "lake jackson",
    "freeport", "pearland", "katy", "cypress", "spring", "humble", "conroe",
    "baytown", "port arthur", "orange", "vidor", "nederland", "groves",
    "silsbee", "lumberton", "galveston", "sugar land", "missouri city",
    "texas city", "league city", "tomball", "richmond", "rosenberg",
)
# Texas ZIPs only: 75000-79999. Houston 770xx-775xx, Beaumont 776xx-777xx.
ZIP_RE = re.compile(r"\b(7[5-9]\d{3})\b")

# OUTAGES stay local. An outage is a selling event where we already have reps
# standing; a cut in Ohio is not our problem.
# FOOTPRINT-WIDE, not Texas. Territory is all 21 AT&T states (CLAUDE.md,
# Patrick 2026-08-25). An outage anywhere AT&T sells is a phone/text selling
# event; only the door-knock needs boots nearby, and _relevant() flags which
# is which rather than throwing the rest away.
OUTAGE_Q = ('"AT&T" (outage OR "fiber cut" OR "service interruption" OR '
            '"internet down")')

# CABLE outages are the OPPOSITE of an AT&T outage: the competitor's customers
# are sitting in the dark and we are the fix. Same territory rule as our own
# outages -- it is only work where a rep can stand on the street today.
CABLE_Q = ('("Comcast" OR "Xfinity" OR "Spectrum" OR "Charter" OR "Cox") '
           '(outage OR "internet down" OR "service interruption" OR "no service")')

# NEW BUILDS go NATIONWIDE across the AT&T footprint. This is the one that
# answers "where do we point the scanner next", and the answer is not confined
# to where we happen to have already scanned. Patrick, 2026-08-22.
BUILD_Q = ('"AT&T Fiber" ("now available" OR expansion OR "new market" OR '
           '"lights up" OR launches OR "brings fiber" OR "expands to")')

# The AT&T fiber footprint. A headline naming a state outside it is somebody
# else's build.
STATES = {
    "alabama": "AL", "arkansas": "AR", "california": "CA", "florida": "FL",
    "georgia": "GA", "illinois": "IL", "indiana": "IN", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "michigan": "MI", "mississippi": "MS",
    "missouri": "MO", "nevada": "NV", "north carolina": "NC", "ohio": "OH",
    "oklahoma": "OK", "south carolina": "SC", "tennessee": "TN", "texas": "TX",
    "wisconsin": "WI",
}
ABBR = set(STATES.values())

_CITY_ST = re.compile(r"\b([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){0,2}),\s*"
                      r"(" + "|".join(sorted(ABBR)) + r")\b")
_IN_CITY = re.compile(r"\b(?:in|to|across|throughout)\s+"
                      r"([A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){0,2})\b")
# Words that look like a place to a regex but are not one.
_NOT_A_PLACE = {"at&t", "att", "fiber", "internet", "gig", "gigs", "more",
                "new", "the", "its", "their", "america", "us", "u.s.",
                "united states", "customers", "homes", "businesses", "week",
                "monday", "tuesday", "wednesday", "thursday", "friday"}


def extract_places(title):
    """Pull (city, state) out of a headline. Returns [] when it cannot tell.

    Deliberately conservative: a wrong city sends somebody to the wrong state
    for a day, so an unparseable headline yields nothing and simply prints
    without a target rather than guessing one.
    """
    out, seen = [], set()
    for city, st in _CITY_ST.findall(title):
        k = (city.lower(), st)
        if city.lower() in _NOT_A_PLACE or k in seen:
            continue
        seen.add(k)
        out.append((city.strip(), st))
    if out:
        return out
    low = title.lower()
    st = ""
    for name, ab in STATES.items():
        if name in low:
            st = ab
            break
    if not st:
        for ab in ABBR:
            if re.search(r"\b%s\b" % ab, title):
                st = ab
                break
    if not st:
        return []
    for city in _IN_CITY.findall(title):
        k = (city.lower(), st)
        if city.lower() in _NOT_A_PLACE or k in seen:
            continue
        if city.lower() in STATES:          # "in Texas" -> statewide, not a city
            continue
        seen.add(k)
        out.append((city.strip(), st))
    return out or [("", st)]


def _news_rss(q):
    return ("https://news.google.com/rss/search?q=%s&hl=en-US&gl=US&ceid=US:en"
            % urllib.parse.quote(q))


def _bing_rss(q):
    return ("https://www.bing.com/news/search?q=%s&format=RSS"
            % urllib.parse.quote(q))


def _reddit(q):
    return ("https://www.reddit.com/r/ATT/search.json?q=%s&restrict_sr=on"
            "&sort=new&t=month&limit=25" % urllib.parse.quote(q))


# name, kind ('outage'|'build'), url, parser
SOURCES = [
    ("google-news", "outage", _news_rss(OUTAGE_Q), "rss"),
    ("bing-news",   "outage", _bing_rss(OUTAGE_Q), "rss"),
    ("reddit-att",  "outage", _reddit("outage Houston OR Beaumont"), "reddit"),
    ("google-news", "build",  _news_rss(BUILD_Q), "rss"),
    ("bing-news",   "build",  _bing_rss(BUILD_Q), "rss"),
    ("reddit-att",  "build",  _reddit("fiber available OR new build Texas"), "reddit"),
    ("google-news", "cable",  _news_rss(CABLE_Q), "rss"),
    ("bing-news",   "cable",  _bing_rss(CABLE_Q), "rss"),
]


def _fetch(url, timeout):
    """Returns (bytes, None) or (None, reason). Never raises."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "*/*"})
        return urllib.request.urlopen(req, timeout=timeout).read(), None
    except Exception as e:
        return None, ("%s: %s" % (e.__class__.__name__, e))[:90]


def _text(s):
    """Strip tags and unescape the handful of entities feeds actually emit."""
    s = re.sub(r"<[^>]+>", " ", s)
    for a, b in (("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"),
                 ("&apos;", "'"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _parse_rss(raw):
    """RSS 2.0. Regex rather than a parser because feeds arrive malformed and a
    strict parse throwing loses the whole source over one bad character."""
    body = raw.decode("utf-8", "replace")
    out = []
    for item in re.findall(r"<item[ >].*?</item>|<item>.*?</item>", body, re.S):
        t = re.search(r"<title[^>]*>(.*?)</title>", item, re.S)
        l = re.search(r"<link[^>]*>(.*?)</link>", item, re.S)
        d = re.search(r"<pubDate[^>]*>(.*?)</pubDate>", item, re.S)
        title = _text(t.group(1)) if t else ""
        if title:
            out.append({"title": title,
                        "url": _text(l.group(1)) if l else "",
                        "when": _text(d.group(1))[:16] if d else ""})
    return out


def _parse_reddit(raw):
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return []
    out = []
    for c in (data.get("data", {}) or {}).get("children", []) or []:
        d = c.get("data", {}) or {}
        title = _text(str(d.get("title") or ""))
        if not title:
            continue
        when = ""
        try:
            when = time.strftime("%Y-%m-%d",
                                 time.localtime(float(d.get("created_utc") or 0)))
        except Exception:
            pass
        out.append({"title": title,
                    "url": "https://reddit.com" + str(d.get("permalink") or ""),
                    "when": when})
    return out


PARSERS = {"rss": _parse_rss, "reddit": _parse_reddit}


OUTAGE_WORDS = ("outage", "outages", "down", "cut", "damaged", "disruption",
                "interruption", "restore", "restored", "knocked out", "offline",
                "service issue", "no service")
BUILD_WORDS = ("now available", "expansion", "expands", "expanding", "new market",
               "lights up", "lit up", "launch", "launches", "launched", "rollout",
               "rolls out", "bringing fiber", "build", "builds", "coming to")


CABLE_BRANDS = ("comcast", "xfinity", "spectrum", "charter", "cox",
                "optimum", "suddenlink", "altice")


def classify(title):
    """Which bucket an item BELONGS in, judged on its own words.

    The query that surfaced an item is a weak signal -- news search is fuzzy and
    both queries return each other's stories. Outage words win ties: calling a
    cut 'a new build' costs a wasted day on the doors, the reverse costs a
    glance.
    """
    t = " " + title.lower() + " "
    if any(w in t for w in OUTAGE_WORDS):
        # Whose outage decides what it MEANS. Ours is a problem; the cable
        # company's is a selling event on streets we already cover.
        if any(b in t for b in CABLE_BRANDS):
            return "cable"
        return "outage"
    if any(w in t for w in BUILD_WORDS):
        return "build"
    return None


def _relevant(item, kind):
    """Keep anything inside the AT&T footprint, and flag whether it is LOCAL.

    Outages used to be Texas-only, which made sense when the territory was
    Houston/Beaumont. It is the whole footprint now, so an outage in Ohio is
    still a phone/text selling event -- it just is not a door-knock. Rather
    than discard it, mark `local` and let the caller rank: boots-on-ground
    towns first, the rest of the footprint after.
    """
    title = item.get("title", "")
    blob = (title + " " + item.get("url", "")).lower()
    zips = sorted(set(ZIP_RE.findall(title)))
    item = dict(item)
    item["zips"] = zips
    item["local"] = any(t in blob for t in TERRITORY)

    hit = [t for t in TERRITORY if t in blob]
    if hit:                                  # a town where we have feet
        item["where"] = hit[0].title()
        item["city"] = hit[0].title()
        item["state"] = "TX"
        return item
    if kind != "build" and zips:             # a Texas ZIP in an outage headline
        item["where"] = zips[0]
        item["city"] = ""
        item["state"] = "TX"
        item["local"] = True
        return item

    places = extract_places(title)            # anywhere else in the footprint
    if not places:
        return None
    city, st = places[0]
    item["places"] = places
    item["state"] = st
    item["city"] = city
    item["where"] = ("%s, %s" % (city, st)) if city else st
    return item


def gather(budget_s=6.0, per_source_s=3.0, cache_path=None, ttl_s=21600,
           force=False):
    """Fetch both kinds inside ONE wall-clock budget. Returns a dict:

        {"outage": [...], "build": [...], "zips": [...],
         "notes": ["google-news outage: 12 items", ...],
         "cached": bool, "age_s": int}

    Never raises. `notes` always explains what happened, including the reasons
    sources failed -- that is what makes an empty result diagnosable.
    """
    now = time.time()
    del _STALE[:]                      # before the read below fills it, not after
    if cache_path and not force:
        try:
            with open(cache_path) as fh:
                c = json.load(fh)
            age = now - float(c.get("fetched_at") or 0)
            if "cable" not in c:
                age = ttl_s + 1        # pre-cable cache: refetch, don't hide it
            if age < ttl_s:
                c["cached"], c["age_s"] = True, int(age)
                return c
            c["stale"] = True                 # kept as a fallback if the net is down
            _STALE.append(c)
        except Exception:
            pass

    res = {"outage": [], "build": [], "cable": [], "zips": [], "notes": [],
           "cached": False, "age_s": 0}
    started = time.time()
    for name, kind, url, ptype in SOURCES:
        left = budget_s - (time.time() - started)
        if left <= 0.2:
            res["notes"].append("%s %s: skipped, %.0fs budget spent"
                                % (name, kind, budget_s))
            continue
        raw, why = _fetch(url, min(per_source_s, left))
        if raw is None:
            res["notes"].append("%s %s: %s" % (name, kind, why))
            continue
        try:
            items = PARSERS[ptype](raw)
        except Exception as e:
            res["notes"].append("%s %s: parse failed (%s)"
                                % (name, kind, e.__class__.__name__))
            continue
        kept, misfiled = [], 0
        for i in items:
            actual = classify(i.get("title", ""))
            if actual is None:
                continue
            r = _relevant(i, actual)
            if not r:
                continue
            if actual != kind:
                misfiled += 1
            r["source"] = name
            kept.append(r)
            res[actual].append(r)
        res["notes"].append("%s %s: %d bytes, %d items, %d in territory%s"
                            % (name, kind, len(raw), len(items), len(kept),
                               (", %d refiled by content" % misfiled) if misfiled else ""))

    for kind in ("outage", "build", "cable"):
        seen, dedup = set(), []
        for it in res[kind]:
            k = it["title"].lower()[:70]
            if k in seen:
                continue
            seen.add(k)
            dedup.append(it)
        res[kind] = dedup
    res["zips"] = sorted({z for k in ("outage", "build", "cable")
                          for it in res[k] for z in it.get("zips", [])})
    res["fetched_at"] = time.time()

    # Nothing fetched but a stale cache exists: show it, clearly labelled, rather
    # than an empty banner. Old intel beats no intel as long as it says it is old.
    if not res["outage"] and not res["build"] and _STALE:
        old = _STALE[0]
        old["cached"], old["stale"] = True, True
        old["age_s"] = int(time.time() - float(old.get("fetched_at") or 0))
        old["notes"] = list(res["notes"]) + ["falling back to cached intel"]
        return old

    if cache_path and (res["outage"] or res["build"]):
        try:
            tmp = cache_path + ".new"
            with open(tmp, "w") as fh:
                json.dump(res, fh)
            os.replace(tmp, cache_path)
        except Exception:
            pass
    return res


def self_test():
    """Print exactly which sources answer from THIS machine. Prune from this."""
    print("Testing %d web-intel sources (no cache, generous timeouts)\n"
          % len(SOURCES))
    r = gather(budget_s=60.0, per_source_s=15.0, cache_path=None, force=True)
    for n in r["notes"]:
        print("  " + n)
    print("\n  OUTAGE items in territory: %d" % len(r["outage"]))
    for it in r["outage"][:5]:
        print("     [%s] %s" % (it["where"], it["title"][:90]))
    print("  NEW BUILD items in territory: %d" % len(r["build"]))
    for it in r["build"][:5]:
        print("     [%s] %s" % (it["where"], it["title"][:90]))
    print("  ZIPs mentioned: %s" % (", ".join(r["zips"]) or "none"))


if __name__ == "__main__":
    self_test()
