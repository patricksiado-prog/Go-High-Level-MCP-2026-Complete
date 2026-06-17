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

VERSION = "1.2 (2026-06-17)"   # bump this when the scraper changes; printed on start

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "businesses.csv")
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps_profile")
FIELDS = ["name", "address", "phone", "website", "category"]

# Google Sheet destination (option 2). Results go to this sheet's tab below.
SHEET_ID = "1FhO2BTMXGefm1tLwKbbMPXvzT1160882Auauzep7ooA"
SHEET_TAB = "Maps Businesses"
PER_QUERY_MAX = 120
SCROLL_ROUNDS = 18
THROTTLE = 0.8
_PHONE_RE = re.compile(r"\+?\d[\d\-\.\s\(\)]{8,}\d")

# category sets -- the run asks Light / Heavy / Deep at the start.
CATEGORIES_LIGHT = [
    "plumber", "electrician", "hvac", "roofing", "general contractor",
    "painter", "handyman", "landscaping", "house cleaning", "junk removal",
    "auto repair", "dog grooming", "hair salon", "barber shop", "nail salon",
    "chiropractor", "dentist", "photographer", "real estate agent",
    "insurance agent",
]
CATEGORIES_HEAVY = [
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
_DEEP_EXTRA = [
    "maid service", "window cleaning", "lawn mowing service", "gutter cleaning",
    "chimney sweep", "fence company", "blind cleaning", "home organizer",
    "air conditioning repair", "remodeling contractor", "tile installer",
    "drywall", "carpenter", "concrete contractor", "paving contractor",
    "solar installer", "welding", "masonry", "septic service",
    "insulation contractor", "cabinet maker", "countertop installer",
    "irrigation", "landscape lighting", "mobile detailing", "windshield repair",
    "transmission repair", "body shop", "oil change", "car wash",
    "window tinting", "mobile dog grooming", "dog walking", "pet boarding",
    "lash extensions", "eyebrow threading", "makeup artist", "spray tan",
    "med spa", "waxing salon", "piercing studio", "hair braiding",
    "mobile hairstylist", "acupuncture", "counseling", "therapist",
    "nutritionist", "dietitian", "personal trainer", "yoga studio",
    "pilates studio", "orthodontist", "optometrist", "podiatrist",
    "dermatologist", "personal chef", "cake decorator", "meal prep",
    "juice bar", "videographer", "graphic designer", "web designer",
    "marketing agency", "accountant", "tax preparer", "virtual assistant",
    "financial advisor", "mortgage broker", "life coach", "business consultant",
    "event planner", "wedding planner", "dj service", "florist",
    "interior designer", "architect", "travel agent", "computer repair",
    "phone repair", "tv repair", "upholstery", "sewing alterations", "tailor",
    "shoe repair", "watch repair", "jewelry repair", "screen printing",
    "embroidery", "sign shop", "print shop", "music lessons", "piano lessons",
    "guitar lessons", "art classes", "swim lessons", "driving school",
    "martial arts", "dance studio", "boutique", "consignment shop",
    "thrift store", "smoke shop", "vape shop", "gift shop", "bike shop",
    "hobby shop", "candle shop", "soap maker",
]
CATEGORIES_DEEP = CATEGORIES_HEAVY + _DEEP_EXTRA


def categories_for(level):
    """Pick a set: '1'/light, '3'/deep, else heavy ('2')."""
    lv = str(level or "2").strip().lower()
    if lv.startswith("1") or lv.startswith("l"):
        return CATEGORIES_LIGHT
    if lv.startswith("3") or lv.startswith("d"):
        return CATEGORIES_DEEP
    return CATEGORIES_HEAVY


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


def _find_creds():
    for p in (os.path.join(os.path.expanduser("~"), "maps_scraper", "google_creds.json"),
              os.path.join(os.path.expanduser("~"), "optimus", "google_creds.json"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "google_creds.json")):
        if os.path.exists(p):
            return p
    return None


def write_to_sheet(rows):
    """Append the businesses to the Google Sheet's 'Maps Businesses' tab.
    Needs google_creds.json on the machine. Dedupes against rows already there."""
    creds = _find_creds()
    if not creds:
        print("\n  (No google_creds.json found -- results are in the CSV only.)")
        return 0
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        client = gspread.authorize(Credentials.from_service_account_file(creds, scopes=scopes))
        sh = client.open_by_key(SHEET_ID)
        try:
            ws = sh.worksheet(SHEET_TAB)
        except Exception:
            ws = sh.add_worksheet(title=SHEET_TAB, rows="20000", cols="5")
        if not ws.get_all_values():
            ws.append_row(["Name", "Address", "Phone", "Website", "Category"])
        existing = set()
        try:
            for r in ws.get_all_values()[1:]:
                if len(r) >= 2:
                    existing.add((r[0].strip().upper() + "|" + r[1].strip().upper()))
        except Exception:
            pass
        new = [[r["name"] or "", r["address"] or "", r["phone"] or "",
                r["website"] or "", r["category"] or ""]
               for r in rows
               if ((r["name"] or "").strip().upper() + "|"
                   + (r["address"] or "").strip().upper()) not in existing]
        for i in range(0, len(new), 500):
            ws.append_rows(new[i:i + 500], value_input_option="RAW")
        return len(new)
    except Exception as e:
        print("\n  (Could not write to the sheet: %s -- results are in the CSV.)" % str(e)[:80])
        return 0


def main():
    print("=" * 56)
    print("  GOOGLE MAPS BUSINESS SCRAPER   v%s" % VERSION)
    print("=" * 56)
    zips = input("\nEnter ZIP codes (comma-separated, e.g. 77027,77019): ").strip()
    zips = [z.strip() for z in zips.split(",") if z.strip()]
    if not zips:
        print("No ZIPs entered. Exiting.")
        return
    print("\nWhere should the results go?")
    print("  [1] CSV file  (businesses.csv)")
    print("  [2] Google Sheet  ('%s' tab)" % SHEET_TAB)
    dest = (input("Choose 1 or 2 (press Enter for 1): ").strip() or "1")
    to_sheet = dest.startswith("2")
    print("\nHow deep should it search?")
    print("  [1] Light  (~20 categories - fastest)")
    print("  [2] Heavy  (~47 categories)")
    print("  [3] Deep   (~155 categories - most thorough, slowest)")
    cats = categories_for(input("Choose 1, 2, or 3 (press Enter for 2): ").strip() or "2")
    queries = [("%s in %s" % (c, z), c) for z in zips for c in cats]
    print("\nSearching %d categories x %d ZIPs = %d searches -> %s\n"
          % (len(cats), len(zips), len(queries), OUT_PATH))

    from playwright.sync_api import sync_playwright
    os.makedirs(PROFILE_DIR, exist_ok=True)
    seen, total, kept = set(), 0, []
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
                kept.append(r)
                new += 1
            out_f.flush()
            total += new
            withp = sum(1 for r in rows if r.get("phone"))
            print("  [%d/%d] %-32s +%d (%d w/phone)" % (i, len(queries), q[:32], new, withp))
        out_f.close()
        ctx.close()
    print("\nDONE: %d businesses saved to CSV:\n  %s" % (total, OUT_PATH))
    if to_sheet:
        print("\nUploading to your Google Sheet...")
        n = write_to_sheet(kept)
        if n:
            print("  +%d businesses added to the '%s' tab." % (n, SHEET_TAB))
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
