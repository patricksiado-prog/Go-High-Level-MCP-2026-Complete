#!/usr/bin/env python3
"""
GHL LOADER v1.0 -- scored fiber businesses -> GoHighLevel (Command) as
call-ready opportunities, plus a dial-queue export for the power dialer.
=============================================================================
This is the keystone: it turns the weekly ranked business list into something
your callers actually work. For each business it:
  1. upserts a CONTACT (dedupe by phone/email so the same biz is never
     loaded twice across weeks),
  2. creates/updates an OPPORTUNITY in the AT&T Commercial pipeline at the
     "Lead" stage, tagged {week, zone, status, score, source},
  3. assigns it round-robin to a caller (GHL user),
  4. appends it to a DIAL QUEUE (highest score first) for the power dialer.

CALLING MODE = POWER DIALER, HUMAN ON EVERY CALL.
  This loader only PREPARES and ORDERS the work and assigns it. The actual
  dialing is GHL's power/preview dialer pulling the AT&T Commercial pipeline
  in score order -- a live agent is connected to each business. We do NOT
  build a predictive/auto-blast: skip-traced lists are full of wireless
  numbers and that is the TCPA exposure ($500-$1,500/call) the brain-doc
  guardrails forbid. Human-in-loop = "automatic" for the team AND defensible.

SAFETY: this script makes live CRM writes, so it runs in --dry by default
(prints the payloads, writes nothing). Pass --commit to actually load. It
NEVER places a call and NEVER sends a text -- it only stages call-ready work.

GHL: Command location xZj500PjsflIQg2j9f9D, AT&T Commercial pipeline
trc5dwodtc1LBYHikmiK. Auth = the Private Integration token (pit-...) from
Railway env GHL_PIT_TOKEN (never hardcode it here).
"""

import os, sys, json, time, argparse
from datetime import datetime

LOCATION_ID = "xZj500PjsflIQg2j9f9D"            # Command (Patrick's)
PIPELINE_ID = "trc5dwodtc1LBYHikmiK"            # AT&T Commercial
DIALER_WORKFLOW_ID = "41e00387-a766-4975-bbcd-627c684a3ee1"  # "Optimus Fiber Biz — Power
# Dialer Queue" (published 2026-06-12): one Manual Call action that drops the
# contact into Conversations > Manual Actions so GHL's power dialer serves it.
# We enroll via API (below) because GHL's internal API rejected saving a
# contact-tag trigger; API enrollment is also more deterministic.
STAGE_LEAD = "Lead"                              # first stage name
API_BASE = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"
SOURCE_TAG = "optimus-fiber-biz"
DIAL_QUEUE_PATH = os.path.join(os.path.expanduser("~"), "Optimus", "dial_queue.json")


def now_str():
    return datetime.now().strftime("%m/%d/%Y %I:%M %p")


# -------------------------------------------------------------------------
# pure payload + assignment logic (unit-tested; no network)
# -------------------------------------------------------------------------
def contact_payload(biz, week_tag, assigned_to=None):
    """Build the GHL upsert-contact body from an enriched+scored business.
    assigned_to = the round-robin caller (GHL user id). It MUST be set on the
    CONTACT (not just the opportunity): GHL's Manual Call / power-dialer queue
    surfaces a call to the CONTACT'S OWNER, so assigning the contact is what
    makes the lead show up in that rep's Conversations > Manual Actions."""
    tags = [SOURCE_TAG, week_tag]
    if biz.get("zone_label"):
        tags.append("zone-%s" % biz["zone_label"].lower())
    if biz.get("status"):
        tags.append(biz["status"])
    if biz.get("phone_type"):
        tags.append("phone-%s" % biz["phone_type"])
    body = {
        "locationId": LOCATION_ID,
        "name": biz.get("name") or biz.get("address") or "Fiber business",
        "phone": biz.get("phone"),
        "address1": biz.get("address"),
        "city": biz.get("city"),
        "state": biz.get("state"),
        "postalCode": str(biz.get("zip") or ""),
        "source": SOURCE_TAG,
        "assignedTo": assigned_to,
        "tags": tags,
        "customFields": _custom_fields(biz),
    }
    return {k: v for k, v in body.items() if v not in (None, "", [])}


def _custom_fields(biz):
    out = []
    mapping = {
        "fiber_status": biz.get("status"),
        "fiber_zone": biz.get("zone_label"),
        "biz_score": biz.get("score"),
        "fiber_lat": biz.get("lat"),
        "fiber_lng": biz.get("lng"),
        "phone_type": biz.get("phone_type"),
    }
    for key, val in mapping.items():
        if val not in (None, ""):
            out.append({"key": key, "field_value": str(val)})
    return out


def opportunity_payload(biz, contact_id, assigned_to=None):
    body = {
        "locationId": LOCATION_ID,
        "pipelineId": PIPELINE_ID,
        "name": "%s - AT&T Fiber" % (biz.get("name") or biz.get("address") or "Business"),
        "pipelineStageName": STAGE_LEAD,
        "status": "open",
        "contactId": contact_id,
        "monetaryValue": biz.get("est_value", 0),
    }
    if assigned_to:
        body["assignedTo"] = assigned_to
    return body


def round_robin(items, agents):
    """Assign each item an agent id, evenly. Returns list of (item, agent)."""
    if not agents:
        return [(it, None) for it in items]
    return [(it, agents[i % len(agents)]) for i, it in enumerate(items)]


def dedupe_key(biz):
    """Same business across weeks -> one key. Phone is the strongest signal,
    else normalized name+zip."""
    ph = "".join(ch for ch in str(biz.get("phone") or "") if ch.isdigit())
    if len(ph) >= 10:
        return "ph:" + ph[-10:]
    name = (biz.get("name") or biz.get("address") or "").strip().lower()
    return "nm:%s|%s" % (name, str(biz.get("zip") or ""))


def filter_new(businesses, already_loaded_keys):
    """Drop businesses already loaded in a prior run (dedupe across weeks)."""
    seen = set(already_loaded_keys)
    out = []
    for b in businesses:
        k = dedupe_key(b)
        if k in seen:
            continue
        seen.add(k)
        out.append(b)
    return out


# -------------------------------------------------------------------------
# thin GHL REST client (only touched on --commit)
# -------------------------------------------------------------------------
class GHLClient:
    def __init__(self, token):
        import requests
        self._requests = requests
        self.h = {"Authorization": "Bearer %s" % token,
                  "Version": API_VERSION,
                  "Content-Type": "application/json"}

    def upsert_contact(self, body):
        r = self._requests.post("%s/contacts/upsert" % API_BASE,
                                headers=self.h, json=body, timeout=30)
        r.raise_for_status()
        c = r.json().get("contact", r.json())
        return c.get("id") or c.get("contactId")

    def create_opportunity(self, body):
        r = self._requests.post("%s/opportunities/" % API_BASE,
                                headers=self.h, json=body, timeout=30)
        r.raise_for_status()
        o = r.json().get("opportunity", r.json())
        return o.get("id")

    def add_to_workflow(self, contact_id, workflow_id=DIALER_WORKFLOW_ID):
        r = self._requests.post(
            "%s/contacts/%s/workflow/%s" % (API_BASE, contact_id, workflow_id),
            headers=self.h, json={}, timeout=30)
        r.raise_for_status()
        return True


# -------------------------------------------------------------------------
# load run
# -------------------------------------------------------------------------
def load_state_keys(path):
    try:
        with open(path) as f:
            return json.load(f).get("keys", [])
    except Exception:
        return []


def save_state_keys(path, keys):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"keys": keys, "updated": now_str()}, f)


def load_businesses(ranked_businesses, agents, week_tag, token=None,
                    commit=False, state_path=None, dial_queue_path=DIAL_QUEUE_PATH):
    """ranked_businesses: list of dicts (already scored+ordered best-first),
    each with 'score' set. Returns a summary dict."""
    state_path = state_path or os.path.join(os.path.expanduser("~"), "Optimus",
                                            "ghl_loaded_keys.json")
    prior = load_state_keys(state_path)
    fresh = filter_new(ranked_businesses, prior)
    assigned = round_robin(fresh, agents)

    client = GHLClient(token) if (commit and token) else None
    dial_queue = []
    loaded = 0
    new_keys = list(prior)
    for biz, agent in assigned:
        cbody = contact_payload(biz, week_tag, assigned_to=agent)
        if client:
            try:
                cid = client.upsert_contact(cbody)
                obody = opportunity_payload(biz, cid, assigned_to=agent)
                oid = client.create_opportunity(obody)
                # drop into the Manual Call queue the power dialer works from
                client.add_to_workflow(cid)
            except Exception as e:
                print("  GHL error for %s: %s" % (cbody.get("name"), str(e)[:120]))
                continue
        else:
            cid, oid = "(dry-contact)", "(dry-opp)"
            print("  [DRY] would load: %-34s score=%s agent=%s phone=%s"
                  % (cbody.get("name"), biz.get("score"), agent, cbody.get("phone")))
        dial_queue.append({
            "score": biz.get("score"), "name": cbody.get("name"),
            "phone": biz.get("phone"), "phone_type": biz.get("phone_type"),
            "contact_id": cid, "opportunity_id": oid, "assigned_to": agent,
            "address": biz.get("address"),
        })
        new_keys.append(dedupe_key(biz))
        loaded += 1

    dial_queue.sort(key=lambda d: -(d["score"] or 0))   # power dialer pulls top-down
    _write_dial_queue(dial_queue_path, dial_queue, commit)
    if commit:
        save_state_keys(state_path, new_keys)
    return {"input": len(ranked_businesses), "new": len(fresh),
            "loaded": loaded, "skipped_dupes": len(ranked_businesses) - len(fresh),
            "dial_queue": dial_queue_path, "committed": commit}


def _write_dial_queue(path, queue, commit):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"generated": now_str(), "mode": "power-dialer-human-in-loop",
                   "count": len(queue), "committed": commit, "queue": queue}, f, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True,
                    help="JSON file: list of scored business dicts (best-first)")
    ap.add_argument("--agents", default="",
                    help="comma-separated GHL user ids to round-robin assign")
    ap.add_argument("--week", default=datetime.now().strftime("week-%G-W%V"))
    ap.add_argument("--commit", action="store_true",
                    help="actually write to GHL (default: dry run, writes nothing)")
    args = ap.parse_args()

    with open(args.input) as f:
        businesses = json.load(f)
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    token = os.environ.get("GHL_PIT_TOKEN")
    if args.commit and not token:
        print("ERROR: --commit needs GHL_PIT_TOKEN in the environment.")
        sys.exit(1)

    summary = load_businesses(businesses, agents, args.week, token=token,
                              commit=args.commit)
    print("\n%s | input %d | new %d | loaded %d | dupes skipped %d"
          % ("COMMITTED" if args.commit else "DRY RUN",
             summary["input"], summary["new"], summary["loaded"],
             summary["skipped_dupes"]))
    print("dial queue (power dialer, human-in-loop) -> %s" % summary["dial_queue"])


if __name__ == "__main__":
    main()
