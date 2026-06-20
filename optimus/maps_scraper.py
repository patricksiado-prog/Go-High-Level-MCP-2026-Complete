#!/usr/bin/env python3
"""
MAPS SCRAPER v1.0 -- self-contained Google Maps business scraper (Playwright).
=============================================================================
No download, no Docker, no separate program: this uses the SAME Playwright
browser OPTIMUS already installs. It reads queries.txt ("restaurants in 77027"
style, one per line), scrapes each business's NAME + ADDRESS + PHONE + WEBSITE
off Google Maps the MapMan way (category search -> scroll the results feed ->
open each listing), and writes businesses.csv -- exactly the file
commercial_split.py reads to split COMMERCIAL vs RESIDENTIAL.

Block-resistant by design (the MapMan lesson): bulk CATEGORY searches (a few
hundred), a real HEADED browser on the user's own connection, human pacing, and
a saved profile so Google's consent page is accepted once. It is NOT 20k
one-by-one lookups -- that's what gets blocked.

RUN:
    python maps_scraper.py                 # reads queries.txt -> businesses.csv
    python maps_scraper.py --headless      # no visible window (more block-prone)
MAPMAN.bat runs this automatically between make-queries and split.
"""

import os, sys, csv, re, time, argparse, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
QUERIES_PATH = os.path.join(HERE, "queries.txt")
OUT_PATH = os.path.join(HERE, "businesses.csv")
PROFILE_DIR = os.path.join(HERE, "maps_profile")   # accept consent once, reuse
FIELDS = ["name", "address", "phone", "website", "email", "category"]

PER_QUERY_MAX = 120          # Google caps a search at ~120 results anyway
SCROLL_ROUNDS = 18
THROTTLE = 0.8               # human pace between listings
_PHONE_RE = re.compile(r"\+?\d[\d\-\.\s\(\)]{8,}\d")


def _category_of(query):
    """'restaurants in 77027' -> 'restaurants' (for the Category column)."""
    return query.split(" in ")[0].strip() if " in " in query else query.strip()


def _dismiss_consent(page):
    """Click Google's cookie/consent 'Accept all' if it shows (first run)."""
    for sel in ("button[aria-label*='Accept all' i]",
                "button:has-text('Accept all')",
                "form[action*='consent'] button"):
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                page.wait_for_timeout(1500)
                return
        except Exception:
            pass


def _text_attr(page, selector):
    """aria-label text of a detail button (Phone:/Address: ...) or None."""
    try:
        el = page.query_selector(selector)
        if el:
            return el.get_attribute("aria-label") or el.inner_text()
    except Exception:
        pass
    return None


def _collect_links(page):
    """Map place-URL -> business name from the result feed cards."""
    out = {}
    for c in page.query_selector_all('a[href*="/maps/place/"]'):
        try:
            href = c.get_attribute("href")
            name = c.get_attribute("aria-label")
            if href and name and href not in out:
                out[href] = name
        except Exception:
            pass
    return out


def scrape_query(page, query, throttle=THROTTLE):
    """Scrape one 'category in ZIP' search. Returns list of business dicts."""
    cat = _category_of(query)
    page.goto("https://www.google.com/maps/search/" + urllib.parse.quote(query),
              wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)
    _dismiss_consent(page)
    if "/sorry/" in page.url or "consent.google" in page.url:
        return None                      # blocked -> signal caller to stop

    feed = page.query_selector('div[role="feed"]')
    links, last = {}, -1
    for _ in range(SCROLL_ROUNDS):
        links.update(_collect_links(page))
        if len(links) >= PER_QUERY_MAX or len(links) == last:
            break
        last = len(links)
        if feed:
            try:
                page.evaluate("(el) => el.scrollBy(0, el.scrollHeight)", feed)
            except Exception:
                pass
        page.wait_for_timeout(1400)

    rows = []
    for href, name in list(links.items())[:PER_QUERY_MAX]:
        try:
            page.goto(href, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1100)
            addr = _text_attr(page, "button[data-item-id='address']")
            phone_lbl = _text_attr(page, "button[data-item-id^='phone']")
            website = None
            w = page.query_selector("a[data-item-id='authority']")
            if w:
                website = w.get_attribute("href")
            phone = None
            if phone_lbl:
                m = _PHONE_RE.search(phone_lbl)
                phone = m.group(0).strip() if m else None
            rows.append({
                "name": name,
                "address": (addr or "").replace("Address: ", "").strip(),
                "phone": phone,
                "website": website,
                "email": "",            # not crawled here; gosom -email does that
                "category": cat,
            })
        except Exception:
            continue
        time.sleep(throttle)
    return rows


def run(queries_path=QUERIES_PATH, out_path=OUT_PATH, headless=False):
    from playwright.sync_api import sync_playwright
    if not os.path.exists(queries_path):
        print("No queries file at %s -- run: python commercial_split.py "
              "make-queries --zips ..." % queries_path)
        return 0
    with open(queries_path) as f:
        queries = [q.strip() for q in f if q.strip()]
    print("Scraping %d searches -> %s%s"
          % (len(queries), out_path, " (headless)" if headless else ""))

    os.makedirs(PROFILE_DIR, exist_ok=True)
    seen, total = set(), 0
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=headless, viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        out_f = open(out_path, "w", newline="", encoding="utf-8")
        writer = csv.DictWriter(out_f, fieldnames=FIELDS)
        writer.writeheader()
        for i, q in enumerate(queries, 1):
            try:
                rows = scrape_query(page, q)
            except Exception as e:
                print("  [%d/%d] %-32s ERROR %s" % (i, len(queries), q, str(e)[:50]))
                continue
            if rows is None:
                print("  [%d/%d] Google blocked the search -- stopping. Try again "
                      "later or run headed so you can clear a captcha." % (i, len(queries)))
                break
            new = 0
            for r in rows:
                key = (r["name"] or "") + "|" + (r["address"] or "")
                if key in seen:
                    continue
                seen.add(key)
                writer.writerow(r)
                new += 1
            out_f.flush()
            total += new
            withp = sum(1 for r in rows if r.get("phone"))
            print("  [%d/%d] %-34s +%d (%d w/phone)" % (i, len(queries), q[:34], new, withp))
        out_f.close()
        ctx.close()
    print("\nDone: %d businesses -> %s" % (total, out_path))
    print("Next: python commercial_split.py split --businesses %s" % out_path)
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", default=QUERIES_PATH)
    ap.add_argument("--out", default=OUT_PATH)
    ap.add_argument("--headless", action="store_true",
                    help="no visible window (faster, but more likely to be blocked)")
    args = ap.parse_args()
    run(args.queries, args.out, args.headless)


if __name__ == "__main__":
    main()
