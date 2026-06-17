#!/usr/bin/env python3
"""
GOOGLE MAPS BUSINESS SCRAPER -- standalone (the "guts").
=============================================================================
Self-contained: asks for ZIP codes, searches Google Maps for small/in-home
businesses by category, and writes businesses.csv (Name, Address, Phone,
Website, Category). The only dependency is Playwright, which the setup file
installs. Lives in Drive so it can be updated without re-sharing the installer.

Run by SCRAPER_SETUP.bat, or directly:  python maps_scraper_standalone.py
"""

import os, csv, re, time, urllib.parse

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "businesses.csv")
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps_profile")
FIELDS = ["name", "address", "phone", "website", "category"]
PER_QUERY_MAX = 120
SCROLL_ROUNDS = 18
THROTTLE = 0.8
_PHONE_RE = re.compile(r"\+?\d[\d\-\.\s\(\)]{8,}\d")

# small-business + in-home categories (one Maps search each, per ZIP)
CATEGORIES = [
    "plumber", "electrician", "hvac", "roofing", "general contractor",
    "painter", "handyman", "landscaping", "pest control", "flooring",
    "house cleaning", "carpet cleaning", "junk removal", "moving company",
    "appliance repair", "garage door repair", "locksmith", "tree service",
    "pressure washing", "pool cleaning", "auto repair", "auto detailing",
    "mobile mechanic", "tire shop", "dog grooming", "pet sitting",
    "dog training", "hair salon", "barber shop", "nail salon",
    "massage therapist", "esthetician", "tattoo shop", "chiropractor",
    "dentist", "physical therapy", "catering", "bakery", "coffee shop",
    "food truck", "photographer", "bookkeeper", "real estate agent",
    "insurance agent", "tutoring", "home daycare", "notary public",
]


def _dismiss_consent(page):
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
    try:
        el = page.query_selector(selector)
        if el:
            return el.get_attribute("aria-label") or el.inner_text()
    except Exception:
        pass
    return None


def _collect_links(page):
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


def scrape_query(page, query, category):
    page.goto("https://www.google.com/maps/search/" + urllib.parse.quote(query),
              wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)
    _dismiss_consent(page)
    if "/sorry/" in page.url or "consent.google" in page.url:
        return None
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
            rows.append({"name": name,
                         "address": (addr or "").replace("Address: ", "").strip(),
                         "phone": phone, "website": website, "category": category})
        except Exception:
            continue
        time.sleep(THROTTLE)
    return rows


def main():
    print("=" * 56)
    print("  GOOGLE MAPS BUSINESS SCRAPER")
    print("=" * 56)
    zips = input("\nEnter ZIP codes (comma-separated, e.g. 77027,77019): ").strip()
    zips = [z.strip() for z in zips.split(",") if z.strip()]
    if not zips:
        print("No ZIPs entered. Exiting.")
        return
    queries = [("%s in %s" % (c, z), c) for z in zips for c in CATEGORIES]
    print("\nSearching %d categories x %d ZIPs = %d searches -> %s\n"
          % (len(CATEGORIES), len(zips), len(queries), OUT_PATH))

    from playwright.sync_api import sync_playwright
    os.makedirs(PROFILE_DIR, exist_ok=True)
    seen, total = set(), 0
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        out_f = open(OUT_PATH, "w", newline="", encoding="utf-8")
        writer = csv.DictWriter(out_f, fieldnames=FIELDS)
        writer.writeheader()
        for i, (q, cat) in enumerate(queries, 1):
            try:
                rows = scrape_query(page, q, cat)
            except Exception as e:
                print("  [%d/%d] %-30s ERROR %s" % (i, len(queries), q, str(e)[:40]))
                continue
            if rows is None:
                print("  Google blocked the search -- stopping. Try again later.")
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
            print("  [%d/%d] %-32s +%d (%d w/phone)" % (i, len(queries), q[:32], new, withp))
        out_f.close()
        ctx.close()
    print("\nDONE: %d businesses saved to:\n  %s" % (total, OUT_PATH))
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
