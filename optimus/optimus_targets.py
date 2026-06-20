#!/usr/bin/env python3
"""
OPTIMUS TARGETS v1.0 -- shared ZIP work-queue + news/signal ingestion.
=============================================================================
This is the "find new fiber FIRST" front of the pipeline. It turns signals
(AT&T buildout press, competitor outages, manual hunches) into a queue of
ZIPs, and lets MANY scanner instances drain that queue without scanning the
same ZIP twice.

Two pieces:

1) TargetQueue -- a lease-based ZIP queue. Each instance CLAIMS a ZIP (with a
   short lease), scans it, then marks it DONE. If an instance dies mid-scan
   its lease expires and another instance picks the ZIP back up. This is how
   you run i1/i2/i3... in parallel safely. Backed by a JSON file here (point
   every instance at one Drive-synced path) -- the same lease logic drops onto
   a Google Sheet tab for true cross-machine coordination (see pick_claimable).

2) SignalIngest -- normalize incoming signals into prioritized ZIP targets,
   deduped. Sources:
     - the COMMAND sheet OUTAGE mechanism (A1=OUTAGE, B1="77002|note")
     - AT&T fiber-expansion news (pluggable fetcher; parse_news_items tested)
     - manual enqueue

NOTE ON COMPLIANCE: this module only decides WHERE to look for fiber. It does
no outreach. Found addresses still flow door-knock + DNC-scrubbed call ->
consent -> consented drip, never auto-text.
"""

import os, re, json, time, tempfile

DEFAULT_QUEUE_PATH = os.path.join(os.path.expanduser("~"), "Optimus", "fiber_targets.json")
DEFAULT_LEASE_SECS = 1800   # 30 min: longer than any single ZIP scan

# priorities (higher = scanned sooner)
PRI_OUTAGE = 90       # competitor outage now -> strike while it's down
PRI_NEWS_BUILDOUT = 70  # AT&T announced/booked fiber here
PRI_MANUAL = 50
PRI_REFRESH = 20      # routine re-scan to catch new green dots

STATUS_OPEN = "open"
STATUS_CLAIMED = "claimed"
STATUS_DONE = "done"

_ZIP_RE = re.compile(r"\b(\d{5})\b")


# -------------------------------------------------------------------------
# pure leasing decision (unit-tested; shared by JSON + Sheet backends)
# -------------------------------------------------------------------------
def pick_claimable(rows, now_ts, lease_secs=DEFAULT_LEASE_SECS):
    """Given target rows, return the index of the best one to claim, or None.

    A row is claimable if it is OPEN, or CLAIMED but its lease has expired
    (the claimer died). Among claimable rows, pick highest priority, then
    oldest enqueue time. `rows` is a list of dicts with keys:
    zip, status, priority, enqueued, lease_until.
    """
    best = None
    best_key = None
    for i, r in enumerate(rows):
        if r.get("status") == STATUS_DONE:
            continue
        claimable = (r.get("status") == STATUS_OPEN or
                     (r.get("status") == STATUS_CLAIMED and
                      float(r.get("lease_until", 0)) <= now_ts))
        if not claimable:
            continue
        # higher priority first, then older enqueue first
        key = (-int(r.get("priority", PRI_MANUAL)), float(r.get("enqueued", 0)))
        if best_key is None or key < best_key:
            best_key = key
            best = i
    return best


class TargetQueue:
    """Lease-based ZIP queue backed by a JSON file.

    Point every scanner instance at the SAME path (e.g. a Drive-synced
    folder) so they coordinate. All writes are atomic (tmp + os.replace).
    """

    def __init__(self, path=DEFAULT_QUEUE_PATH, lease_secs=DEFAULT_LEASE_SECS):
        self.path = path
        self.lease_secs = lease_secs
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    # ---- storage ----
    def _load(self):
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path) as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, rows):
        d = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(rows, f, indent=2)
        os.replace(tmp, self.path)

    # ---- ops ----
    def add(self, zipc, priority=PRI_MANUAL, note="", source="manual"):
        """Enqueue a ZIP (idempotent: bumps priority if already queued/open)."""
        zipc = str(zipc).strip()
        if not re.fullmatch(r"\d{5}", zipc):
            return False
        rows = self._load()
        for r in rows:
            if r["zip"] == zipc and r["status"] != STATUS_DONE:
                if priority > r.get("priority", 0):
                    r["priority"] = priority
                    r["note"] = note or r.get("note", "")
                    r["source"] = source
                self._save(rows)
                return True
        rows.append({
            "zip": zipc, "status": STATUS_OPEN, "priority": int(priority),
            "note": note, "source": source, "enqueued": time.time(),
            "claimed_by": None, "lease_until": 0, "scans": 0,
        })
        self._save(rows)
        return True

    def claim(self, instance_id):
        """Claim the best available ZIP for this instance. Returns the row or None."""
        rows = self._load()
        i = pick_claimable(rows, time.time(), self.lease_secs)
        if i is None:
            return None
        rows[i]["status"] = STATUS_CLAIMED
        rows[i]["claimed_by"] = str(instance_id)
        rows[i]["lease_until"] = time.time() + self.lease_secs
        self._save(rows)
        return dict(rows[i])

    def complete(self, zipc, instance_id, requeue_refresh_after=None):
        """Mark a ZIP done. Optionally re-enqueue it as a low-priority refresh
        (so the area gets re-scanned later to catch newly-lit green dots)."""
        rows = self._load()
        for r in rows:
            if r["zip"] == zipc and r["status"] == STATUS_CLAIMED:
                r["status"] = STATUS_DONE
                r["scans"] = r.get("scans", 0) + 1
                r["done_at"] = time.time()
                break
        if requeue_refresh_after is not None:
            rows.append({
                "zip": zipc, "status": STATUS_OPEN, "priority": PRI_REFRESH,
                "note": "auto-refresh", "source": "refresh",
                "enqueued": time.time() + requeue_refresh_after,
                "claimed_by": None, "lease_until": 0, "scans": 0,
            })
        self._save(rows)

    def release(self, zipc):
        """Give a claimed ZIP back to the queue (e.g. scan failed)."""
        rows = self._load()
        for r in rows:
            if r["zip"] == zipc and r["status"] == STATUS_CLAIMED:
                r["status"] = STATUS_OPEN
                r["claimed_by"] = None
                r["lease_until"] = 0
        self._save(rows)

    def pending(self):
        return [r for r in self._load() if r["status"] != STATUS_DONE]


# -------------------------------------------------------------------------
# signal ingestion -> ZIP targets
# -------------------------------------------------------------------------
def ingest_outage_signal(queue, b1_value):
    """COMMAND sheet OUTAGE format: B1 = '77002|Comcast outage'."""
    parts = str(b1_value).split("|", 1)
    zipc = parts[0].strip()
    note = parts[1].strip() if len(parts) > 1 else "outage"
    if re.fullmatch(r"\d{5}", zipc):
        return queue.add(zipc, priority=PRI_OUTAGE, note=note, source="outage")
    return False


# keywords that mark a news item as an AT&T fiber-expansion signal
NEWS_KEYWORDS = ("at&t fiber", "att fiber", "fiber expansion", "fiber buildout",
                 "fiber availability", "lighting up", "now available", "gigapower")


def parse_news_items(items, zip_hint=None):
    """Extract (zip, note) targets from news items.

    `items` is a list of dicts with 'title' and/or 'summary'/'text'. A ZIP is
    pulled from the item text; if none is present and zip_hint is given (a
    {city_or_keyword: zip} map), the first matching keyword's ZIP is used.
    Only items mentioning AT&T fiber expansion are kept. Returns a deduped
    list of (zip, note) tuples.
    """
    out = {}
    for it in items:
        blob = " ".join(str(it.get(k, "")) for k in ("title", "summary", "text")).strip()
        low = blob.lower()
        if not any(k in low for k in NEWS_KEYWORDS):
            continue
        zips = _ZIP_RE.findall(blob)
        if not zips and zip_hint:
            for key, z in zip_hint.items():
                if key.lower() in low:
                    zips = [z]
                    break
        for z in zips:
            note = (it.get("title") or blob)[:120]
            out.setdefault(z, note)
    return list(out.items())


def enqueue_news(queue, items, zip_hint=None):
    """Parse news items and enqueue any AT&T fiber-expansion ZIPs found."""
    added = 0
    for z, note in parse_news_items(items, zip_hint):
        if queue.add(z, priority=PRI_NEWS_BUILDOUT, note=note, source="news"):
            added += 1
    return added
