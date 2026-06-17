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

import os, csv, re, time, json, urllib.parse

VERSION = "1.6 (2026-06-17)"   # bump this when the scraper changes; printed on start

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "businesses.csv")
PROFILE_DIR = os.path.join(HERE, "maps_profile")
PROGRESS_PATH = os.path.join(HERE, "maps_progress.json")   # resume: done searches
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
    "auto repair", "dog grooming", "hair salon", "barber shop",
    "chiropractor", "photographer", "real estate agent", "insurance agent",
]
CATEGORIES_HEAVY = [
    "plumber", "electrician", "hvac", "roofing", "general contractor",
    "painter", "handyman", "landscaping", "pest control", "flooring",
    "house cleaning", "carpet cleaning", "junk removal", "moving company",
    "appliance repair", "garage door repair", "locksmith", "tree service",
    "pressure washing", "pool cleaning", "auto repair", "auto detailing",
    "mobile mechanic", "tire shop", "dog grooming", "pet sitting",
    "dog training", "hair salon", "barber shop",
    "massage therapist", "esthetician", "tattoo shop", "chiropractor",
    "physical therapy", "catering", "bakery", "coffee shop",
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


# Big-box + national chains + franchises -- SKIP these. On a chain/franchise the
# person on site can't decide on fiber (it's corporate-procured), so they're not
# a callable prospect. We only keep local, owner-operated businesses.
CHAINS = {
    # big-box / retail / grocery / pharmacy
    "walmart", "wal-mart", "target", "costco", "sam's club", "sams club",
    "home depot", "lowe's", "lowes", "best buy", "apple store", "kroger",
    "h-e-b", "heb", "central market", "whole foods", "trader joe", "cvs",
    "walgreens", "rite aid", "ikea", "macy's", "nordstrom", "dillard",
    "jcpenney", "jc penney", "kohl's", "ross", "marshalls", "tj maxx",
    "t.j. maxx", "homegoods", "home goods", "petco", "petsmart", "gamestop",
    "hobby lobby", "michaels", "barnes & noble", "dick's sporting",
    "academy sports", "office depot", "staples", "five below", "aldi",
    "publix", "safeway", "dollar general", "dollar tree", "family dollar",
    "sephora", "ulta", "bath & body", "crate & barrel", "crate and barrel",
    "pottery barn", "williams sonoma", "west elm", "anthropologie",
    "restoration hardware",
    # banks / telecom / shipping
    "bank of america", "chase bank", "wells fargo", "capital one", "citibank",
    "us bank", "fedex", "ups store", "usps", "verizon", "t-mobile", "at&t store",
    "xfinity", "spectrum",
    # fast food / chain restaurants
    "mcdonald", "starbucks", "chick-fil-a", "chickfila", "chipotle", "subway",
    "wendy's", "burger king", "taco bell", "panera", "dunkin", "panda express",
    "olive garden", "chili's", "applebee", "ihop", "denny's", "buffalo wild",
    "raising cane", "whataburger", "jack in the box", "sonic drive", "in-n-out",
    "popeyes", "kfc", "pizza hut", "domino", "little caesars", "jimmy john",
    "jersey mike", "papa john", "wingstop", "5 guys", "five guys", "dairy queen",
    # gas / convenience
    "7-eleven", "7 eleven", "shell", "exxon", "chevron", "circle k", "valero",
    "buc-ee", "quiktrip", "racetrac",
    # service-category FRANCHISES (on-site mgr can't decide on fiber)
    "jiffy lube", "valvoline", "midas", "meineke", "firestone", "discount tire",
    "ntb", "take 5", "christian brothers", "aamco", "maaco",
    "great clips", "supercuts", "sport clips", "fantastic sams", "sola salon",
    "planet fitness", "la fitness", "24 hour fitness", "anytime fitness",
    "orangetheory", "crunch fitness", "gold's gym", "ymca",
    "massage envy", "european wax", "hand and stone", "drybar",
    "servpro", "stanley steemer", "chem-dry", "molly maid", "merry maids",
    "the maids", "two maids", "terminix", "orkin", "truly nolen", "mosquito joe",
    "1-800-got-junk", "college hunks", "junk king", "two men and a truck",
    "mr. handyman", "ace handyman", "roto-rooter", "roto rooter",
    "benjamin franklin", "mr. rooter", "mr. electric", "one hour", "aire serv",
    "kumon", "mathnasium", "sylvan", "goldfish swim", "british swim",
    "the ups store", "postal annex", "fastsigns", "signarama", "minuteman press",
}


def _is_local(name):
    """True if this looks like a local, owner-operated business (skip chains)."""
    n = (name or "").lower()
    return not any(c in n for c in CHAINS)


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
    target_zip = query.split(" in ")[-1].strip() if " in " in query else ""
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
        if not _is_local(name):        # skip big-box / chains / franchises
            continue
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
            addr = (addr or "").replace("Address: ", "").strip()
            if target_zip and target_zip not in addr:
                continue                 # keep only businesses actually in the ZIP
            rows.append({"name": name, "address": addr,
                         "phone": phone, "website": website, "category": category})
        except Exception:
            continue
        time.sleep(THROTTLE)
    return rows


def load_progress():
    """Searches already completed in a prior run (so a stopped run resumes)."""
    try:
        with open(PROGRESS_PATH) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_progress(done):
    try:
        with open(PROGRESS_PATH, "w") as f:
            json.dump(sorted(done), f)
    except Exception:
        pass


def clear_progress():
    """Wipe progress after a clean full run, so the next run starts fresh."""
    try:
        os.remove(PROGRESS_PATH)
    except Exception:
        pass


def _find_creds():
    for p in (os.path.join(os.path.expanduser("~"), "maps_scraper", "google_creds.json"),
              os.path.join(os.path.expanduser("~"), "optimus", "google_creds.json"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "google_creds.json")):
        if os.path.exists(p):
            return p
    return None


def open_sheet():
    """Open (or create) the 'Maps Businesses' tab ONCE at the start, and read the
    rows already there so we don't duplicate. Returns (worksheet, seen-keys-set)
    or (None, set()) if there's no key. Needs google_creds.json on the machine."""
    creds = _find_creds()
    if not creds:
        print("\n  (No google_creds.json found -- results go to the CSV only.)")
        return None, set()
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
        seen = set()
        try:
            for r in ws.get_all_values()[1:]:
                if len(r) >= 2:
                    seen.add(r[0].strip().upper() + "|" + r[1].strip().upper())
        except Exception:
            pass
        print("  -> writing to the '%s' tab live, as it runs." % SHEET_TAB)
        return ws, seen
    except Exception as e:
        print("\n  (Could not open the sheet: %s -- results go to the CSV.)" % str(e)[:80])
        return None, set()


def append_sheet(ws, rows, sheet_seen):
    """Append the new (not-already-in-sheet) rows NOW. Updates sheet_seen.
    Called after each category so the sheet fills continually."""
    if ws is None or not rows:
        return 0
    new = []
    for r in rows:
        key = ((r.get("name") or "").strip().upper() + "|"
               + (r.get("address") or "").strip().upper())
        if key in sheet_seen:
            continue
        sheet_seen.add(key)
        new.append([r.get("name") or "", r.get("address") or "", r.get("phone") or "",
                    r.get("website") or "", r.get("category") or ""])
    if not new:
        return 0
    try:
        for i in range(0, len(new), 500):
            ws.append_rows(new[i:i + 500], value_input_option="RAW")
        return len(new)
    except Exception as e:
        print("  (sheet write hiccup, will retry next batch: %s)" % str(e)[:60])
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

    # RESUME: skip searches finished in a prior run that stopped early
    done = load_progress()
    pending = [(q, cat) for (q, cat) in queries if q not in done]
    resuming = bool(done) and len(pending) < len(queries)
    if resuming:
        print("\nResuming -- %d of %d searches already done; %d left."
              % (len(queries) - len(pending), len(queries), len(pending)))
    print("\nSearching %d categories x %d ZIPs = %d searches (%d to do) -> %s\n"
          % (len(cats), len(zips), len(queries), len(pending), OUT_PATH))
    if not pending:
        print("Nothing left to do (already complete). Starting over next time.")
        clear_progress()

    from playwright.sync_api import sync_playwright
    os.makedirs(PROFILE_DIR, exist_ok=True)
    sheet_ws, sheet_seen = (open_sheet() if to_sheet else (None, set()))
    seen, total, sheet_added, stopped = set(), 0, 0, False
    csv_mode = "a" if (resuming and os.path.exists(OUT_PATH)) else "w"
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        out_f = open(OUT_PATH, csv_mode, newline="", encoding="utf-8")
        writer = csv.DictWriter(out_f, fieldnames=FIELDS)
        if csv_mode == "w":
            writer.writeheader()
        for i, (q, cat) in enumerate(pending, 1):
            try:
                rows = scrape_query(page, q, cat)
            except Exception as e:
                print("  [%d/%d] %-30s ERROR %s" % (i, len(pending), q, str(e)[:40]))
                continue
            if rows is None:
                print("  Google blocked the search -- stopping. Run again to RESUME here.")
                stopped = True
                break
            new, q_new = 0, []
            for r in rows:
                key = (r["name"] or "") + "|" + (r["address"] or "")
                if key in seen:
                    continue
                seen.add(key)
                writer.writerow(r)
                q_new.append(r)
                new += 1
            out_f.flush()
            if sheet_ws is not None and q_new:      # add to the sheet as we go
                sheet_added += append_sheet(sheet_ws, q_new, sheet_seen)
            total += new
            done.add(q)                              # mark this search complete
            save_progress(done)
            withp = sum(1 for r in rows if r.get("phone"))
            print("  [%d/%d] %-32s +%d (%d w/phone)" % (i, len(pending), q[:32], new, withp))
        out_f.close()
        ctx.close()
    if not stopped:
        clear_progress()                             # finished -> fresh next time
    print("\nDONE: %d businesses saved to CSV:\n  %s" % (total, OUT_PATH))
    if to_sheet:
        print("  %d added to the '%s' tab (written live as it ran)." % (sheet_added, SHEET_TAB))
    if stopped:
        print("\n  Stopped early -- just run this again and it picks up where it left off.")
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
