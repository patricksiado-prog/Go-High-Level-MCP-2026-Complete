#!/usr/bin/env python3
"""
Optimus pure-logic test suite (stdlib unittest -- no pytest needed).
=============================================================================
Covers every module's NON-network logic: signal queueing, dot classification,
backend-JSON feature extraction, zone + business scoring, GHL payload/dedupe,
the FCC BDC new-build diff, and the weekly orchestrator's stage planning.

Run from the optimus/ dir (so the modules import):
    cd optimus && python -m unittest discover -s tests -v
    # or:  cd optimus && python -m pytest tests -q
Requires numpy (a listed dep; optimus_dot_detect imports it). No browser,
sheet, or GHL credentials are touched.
"""

import os, sys, json, time, tempfile, types, unittest

# make the optimus/ modules importable when run from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import optimus_targets as tgt
import optimus_api_capture as cap
import optimus_dot_detect as dot
import business_score as score
import ghl_loader as loader
import bdc_diff
import weekly_run
import themapman
import fiber_zone_scanner as fzs


class TestTargets(unittest.TestCase):
    def test_pick_claimable_priority_and_age(self):
        now = 1000.0
        rows = [
            {"zip": "1", "status": "open", "priority": 50, "enqueued": 10},
            {"zip": "2", "status": "open", "priority": 90, "enqueued": 20},
            {"zip": "3", "status": "open", "priority": 90, "enqueued": 5},  # older, same pri
        ]
        # highest priority, then oldest enqueue -> row index 2 (zip "3")
        self.assertEqual(tgt.pick_claimable(rows, now), 2)

    def test_pick_claimable_skips_done_and_live_lease(self):
        now = 1000.0
        rows = [
            {"zip": "1", "status": "done", "priority": 90, "enqueued": 1},
            {"zip": "2", "status": "claimed", "priority": 90, "lease_until": 2000, "enqueued": 1},
        ]
        self.assertIsNone(tgt.pick_claimable(rows, now))  # done skipped, lease still live

    def test_pick_claimable_expired_lease_reclaimable(self):
        now = 3000.0
        rows = [{"zip": "2", "status": "claimed", "priority": 50, "lease_until": 2000, "enqueued": 1}]
        self.assertEqual(tgt.pick_claimable(rows, now), 0)

    def test_parse_news_filters_and_extracts_zip(self):
        items = [
            {"title": "AT&T fiber now available in 77002 Houston"},
            {"title": "Local bakery opens"},                       # no keyword -> dropped
            {"title": "Comcast outage", "text": "no fiber mention"},  # no keyword -> dropped
        ]
        out = dict(tgt.parse_news_items(items))
        self.assertIn("77002", out)
        self.assertEqual(len(out), 1)

    def test_parse_news_zip_hint(self):
        items = [{"title": "AT&T fiber expansion reaches Katy this month"}]
        out = dict(tgt.parse_news_items(items, zip_hint={"katy": "77449"}))
        self.assertIn("77449", out)  # resolved via the city->ZIP hint

    def test_ingest_outage_signal(self):
        q = _temp_queue()
        self.assertTrue(tgt.ingest_outage_signal(q, "77002|Comcast outage"))
        pend = q.pending()
        self.assertEqual(pend[0]["zip"], "77002")
        self.assertEqual(pend[0]["priority"], tgt.PRI_OUTAGE)

    def test_queue_add_claim_complete_cycle(self):
        q = _temp_queue()
        q.add("77002", priority=tgt.PRI_MANUAL)
        q.add("77002", priority=tgt.PRI_OUTAGE)  # idempotent bump, not a dupe
        self.assertEqual(len(q.pending()), 1)
        self.assertEqual(q.pending()[0]["priority"], tgt.PRI_OUTAGE)
        row = q.claim("i1")
        self.assertEqual(row["zip"], "77002")
        q.complete("77002", "i1")
        self.assertEqual(q.pending(), [])

    def test_queue_rejects_bad_zip(self):
        q = _temp_queue()
        self.assertFalse(q.add("abc"))
        self.assertFalse(q.add("123"))


class TestApiCapture(unittest.TestCase):
    def test_extract_plain(self):
        obj = {"address": "13911 E Cypress St", "lat": 29.9, "lng": -95.5, "ban": "*1234"}
        out = cap.extract_features(obj)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["address"], "13911 E Cypress St")
        self.assertEqual(out[0]["lat"], 29.9)
        self.assertEqual(out[0]["ban"], "*1234")

    def test_extract_nested_list(self):
        obj = {"data": {"features": [
            {"siteAddress": "100 Main St", "latitude": 30.0, "longitude": -95.0},
            {"siteAddress": "200 Oak Ave", "latitude": 30.1, "longitude": -95.1},
        ]}}
        out = cap.extract_features(obj)
        self.assertEqual(len(out), 2)

    def test_extract_geojson_coord_order(self):
        obj = {"type": "Feature",
               "geometry": {"type": "Point", "coordinates": [-95.37, 29.76]},
               "properties": {"fullAddress": "55 Travis St", "status": "Fiber Eligible"}}
        out = cap.extract_features(obj)
        self.assertEqual(out[0]["lng"], -95.37)   # GeoJSON is [lng, lat]
        self.assertEqual(out[0]["lat"], 29.76)
        self.assertEqual(out[0]["status"], "Fiber Eligible")

    def test_rejects_non_address_and_bad_coords(self):
        self.assertEqual(cap.extract_features({"address": "no number here"}), [])
        out = cap.extract_features({"address": "5 A St", "lat": 999, "lng": -95})
        self.assertIsNone(out[0]["lat"])   # off-Earth latitude dropped
        self.assertEqual(out[0]["lng"], -95)


class TestDotDetect(unittest.TestCase):
    def test_classify_by_color(self):
        self.assertEqual(dot.classify_status(color="GREEN"), dot.STATUS_LEAD)
        self.assertEqual(dot.classify_status(color="GRAY"), dot.STATUS_CUSTOMER)
        self.assertEqual(dot.classify_status(color="GOLD"), dot.STATUS_COPPER_UPGRADE)

    def test_classify_by_text_priority(self):
        self.assertEqual(dot.classify_status(text="Copper customer"), dot.STATUS_COPPER_UPGRADE)
        self.assertEqual(dot.classify_status(text="Fiber eligible / non-customer"), dot.STATUS_LEAD)
        self.assertEqual(dot.classify_status(text="Existing subscriber"), dot.STATUS_CUSTOMER)

    def test_classify_ban_then_default(self):
        self.assertEqual(dot.classify_status(ban="*123"), dot.STATUS_CUSTOMER)
        self.assertEqual(dot.classify_status(), dot.STATUS_LEAD)

    def test_zone_freshness(self):
        self.assertEqual(dot.zone_freshness(20, 5, 0)[0], "FRESH")
        self.assertEqual(dot.zone_freshness(5, 1, 40)[0], "MATURE")
        self.assertEqual(dot.zone_freshness(10, 2, 5)[0], "WORKING")
        self.assertEqual(dot.zone_freshness(0, 0, 0)[0], "EMPTY")


class TestZoneScanner(unittest.TestCase):
    def test_score_zone_fresh_and_new_fiber(self):
        s = fzs.score_zone(green=20, gold=3, gray=0)
        self.assertEqual(s["label"], "FRESH")
        self.assertEqual(s["priority"], 1)
        mature = fzs.score_zone(green=2, gold=1, gray=40)
        self.assertEqual(mature["label"], "MATURE")
        self.assertEqual(mature["priority"], 3)
        # new green forces priority 1 even on an otherwise-mature zone
        forced = fzs.score_zone(green=2, gold=1, gray=40, new_green=3)
        self.assertEqual(forced["priority"], 1)
        self.assertIn("NEW FIBER", forced["action"])

    def test_diff_new_addresses_case_insensitive(self):
        prev = ["100 main st"]
        cur = ["100 MAIN ST", "200 OAK AVE"]
        self.assertEqual(fzs.diff_new_addresses(prev, cur), ["200 OAK AVE"])


class TestBusinessScore(unittest.TestCase):
    def test_hard_drops(self):
        self.assertFalse(score.score_business({"status": dot.STATUS_CUSTOMER, "has_phone": True})["callable"])
        self.assertFalse(score.score_business({"on_dnc": True, "has_phone": True})["callable"])
        self.assertEqual(score.score_business({"has_phone": False})["drop_reason"], "no phone")

    def test_score_and_factors(self):
        biz = {"zone_label": "FRESH", "status": dot.STATUS_LEAD, "types": ["restaurant"],
               "phone_type": "landline", "in_ghl": False, "has_phone": True}
        r = score.score_business(biz)
        self.assertTrue(r["callable"])
        # 40 zone + 30 status + 20 type + 10 phone + 15 new = 115
        self.assertEqual(r["score"], 115)

    def test_rank_orders_best_first_and_drops_uncallable(self):
        biz_hi = {"zone_label": "FRESH", "status": dot.STATUS_LEAD, "types": ["clinic"],
                  "phone_type": "landline", "has_phone": True}
        biz_lo = {"zone_label": "MATURE", "status": dot.STATUS_COPPER_UPGRADE, "types": ["atm"],
                  "phone_type": "wireless", "in_ghl": True, "has_phone": True}
        biz_drop = {"status": dot.STATUS_CUSTOMER, "has_phone": True}
        ranked = score.rank_businesses([biz_lo, biz_hi, biz_drop])
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["business"], biz_hi)


class TestGhlLoader(unittest.TestCase):
    def test_contact_payload_tags_and_fields(self):
        biz = {"name": "Joe's Cafe", "phone": "713-555-0100", "address": "5 Main St",
               "city": "Houston", "state": "TX", "zip": "77002", "status": dot.STATUS_LEAD,
               "zone_label": "FRESH", "phone_type": "landline", "score": 99,
               "lat": 29.7, "lng": -95.3}
        body = loader.contact_payload(biz, "week-2026-W24")
        self.assertEqual(body["locationId"], loader.LOCATION_ID)
        self.assertIn("optimus-fiber-biz", body["tags"])
        self.assertIn("week-2026-W24", body["tags"])
        self.assertIn("zone-fresh", body["tags"])
        self.assertIn("phone-landline", body["tags"])
        keys = {f["key"] for f in body["customFields"]}
        self.assertIn("biz_score", keys)
        self.assertIn("fiber_lat", keys)

    def test_contact_payload_drops_empties(self):
        body = loader.contact_payload({"name": "X", "phone": "7135550100"}, "wk")
        self.assertNotIn("city", body)   # empty values stripped

    def test_opportunity_payload(self):
        body = loader.opportunity_payload({"name": "Joe's"}, "cid123", assigned_to="agentA")
        self.assertEqual(body["pipelineId"], loader.PIPELINE_ID)
        self.assertEqual(body["contactId"], "cid123")
        self.assertEqual(body["assignedTo"], "agentA")
        self.assertEqual(body["pipelineStageName"], loader.STAGE_LEAD)

    def test_round_robin(self):
        pairs = loader.round_robin(["a", "b", "c"], ["u1", "u2"])
        self.assertEqual([p[1] for p in pairs], ["u1", "u2", "u1"])
        self.assertEqual(loader.round_robin(["a"], []), [("a", None)])

    def test_dedupe_key_phone_vs_name(self):
        self.assertEqual(loader.dedupe_key({"phone": "+1 (713) 555-0100"}), "ph:7135550100")
        self.assertTrue(loader.dedupe_key({"name": "Joe's", "zip": "77002"}).startswith("nm:joe's|77002"))

    def test_filter_new_dedupes_across_weeks(self):
        prior = [loader.dedupe_key({"phone": "7135550100"})]
        businesses = [{"phone": "7135550100"}, {"phone": "8325550111"}, {"phone": "7135550100"}]
        fresh = loader.filter_new(businesses, prior)
        self.assertEqual(len(fresh), 1)
        self.assertEqual(fresh[0]["phone"], "8325550111")

    def test_load_businesses_dry_run_writes_dial_queue(self):
        biz = [{"name": "Joe's", "phone": "7135550100", "score": 80, "phone_type": "landline"}]
        with tempfile.TemporaryDirectory() as d:
            dq = os.path.join(d, "dial_queue.json")
            state = os.path.join(d, "state.json")
            summary = loader.load_businesses(biz, ["u1"], "wk", token=None, commit=False,
                                             state_path=state, dial_queue_path=dq)
            self.assertEqual(summary["loaded"], 1)
            self.assertFalse(summary["committed"])
            with open(dq) as f:
                written = json.load(f)
            self.assertEqual(written["count"], 1)
            self.assertEqual(written["mode"], "power-dialer-human-in-loop")
            # dry run must NOT persist dedupe state
            self.assertFalse(os.path.exists(state))


ATT_FIBER = {"provider_id": "1001", "brand_name": "AT&T Inc.", "technology": "50",
             "location_id": "L1", "block_geoid": "482011000001000", "zip": "77002"}
ATT_COPPER = {"brand_name": "AT&T", "technology": "10", "location_id": "L2", "zip": "77002"}
COMP_FIBER = {"brand_name": "Comcast", "technology": "50", "location_id": "L3", "zip": "77003"}


class TestBdcDiff(unittest.TestCase):
    def test_is_att_fiber(self):
        self.assertTrue(bdc_diff.is_att_fiber(ATT_FIBER))
        self.assertFalse(bdc_diff.is_att_fiber(ATT_COPPER))   # not fiber tech
        self.assertFalse(bdc_diff.is_att_fiber(COMP_FIBER))   # not AT&T

    def test_provider_id_allowlist(self):
        row = {"provider_id": "999", "brand_name": "Acme Fiber", "technology": "50", "location_id": "L9"}
        self.assertTrue(bdc_diff.is_att_fiber(row, provider_ids={"999"}))

    def test_fiber_location_ids(self):
        ids = bdc_diff.fiber_location_ids([ATT_FIBER, ATT_COPPER, COMP_FIBER])
        self.assertEqual(ids, {"L1"})

    def test_diff_new_locations(self):
        cur = [ATT_FIBER, dict(ATT_FIBER, location_id="L5", zip="77019")]
        new = bdc_diff.diff_new_locations({"L1"}, cur)
        self.assertEqual([r["location_id"] for r in new], ["L5"])

    def test_rollup_by_zip_explicit_and_resolver_and_unmapped(self):
        rows = [
            dict(ATT_FIBER, location_id="A", zip="77002"),
            dict(ATT_FIBER, location_id="B", zip="77002"),
            dict(ATT_FIBER, location_id="C", zip=""),    # no zip on row
        ]
        # resolver maps the zip-less location C
        roll = bdc_diff.rollup_by_zip(rows, resolver={"C": "77019"})
        self.assertEqual(roll["zips"], {"77002": 2, "77019": 1})
        self.assertEqual(roll["unmapped"], 0)
        # without resolver, C is unmapped
        roll2 = bdc_diff.rollup_by_zip(rows)
        self.assertEqual(roll2["zips"], {"77002": 2})
        self.assertEqual(roll2["unmapped"], 1)

    def test_rollup_by_block(self):
        blocks = bdc_diff.rollup_by_block([ATT_FIBER, dict(ATT_FIBER, location_id="L7")])
        self.assertEqual(blocks, {"482011000001000": 2})

    def test_order_targets_min_new(self):
        ordered = bdc_diff.order_targets({"77002": 3, "77019": 1, "77003": 3}, min_new=2)
        # >= 2 only, count desc, then ZIP asc on ties
        self.assertEqual(ordered, [("77002", 3), ("77003", 3)])

    def test_baseline_roundtrip_and_fabric_resolver(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "baseline.json")
            bdc_diff.save_baseline(base, {"L1", "L2"})
            self.assertEqual(bdc_diff.load_baseline(base), {"L1", "L2"})
            fab = os.path.join(d, "fabric.csv")
            with open(fab, "w") as f:
                f.write("location_id,zip\nL1,77002\nL2,77019\n")
            resolver = bdc_diff.build_fabric_resolver(fab)
            self.assertEqual(resolver, {"L1": "77002", "L2": "77019"})

    def test_enqueue_targets(self):
        q = _temp_queue()
        n = bdc_diff.enqueue_targets(q, [("77002", 4), ("77019", 1)])
        self.assertEqual(n, 2)
        zips = {r["zip"]: r for r in q.pending()}
        self.assertEqual(zips["77002"]["source"], "bdc")
        self.assertEqual(zips["77002"]["priority"], bdc_diff.PRI_NEWS_BUILDOUT)


class TestWeeklyRun(unittest.TestCase):
    def test_plan_stages_resume(self):
        # signals already done -> resume at scan
        self.assertEqual(weekly_run.plan_stages(done=["signals"]),
                         ["scan", "enrich", "score", "load"])

    def test_plan_stages_only_and_skip(self):
        self.assertEqual(weekly_run.plan_stages(done=[], only=["score", "load"]),
                         ["score", "load"])
        self.assertEqual(weekly_run.plan_stages(done=[], skip=["scan"]),
                         ["signals", "enrich", "score", "load"])

    def test_plan_stages_force_ignores_done(self):
        self.assertEqual(weekly_run.plan_stages(done=["signals", "scan"], force=True),
                         weekly_run.STAGES)

    def test_plan_stages_all_done(self):
        self.assertEqual(weekly_run.plan_stages(done=weekly_run.STAGES), [])

    def test_week_tag_format(self):
        import datetime as _dt
        self.assertEqual(weekly_run.week_tag(_dt.datetime(2026, 6, 13)), "week-2026-W24")

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "state.json")
            st = weekly_run.load_state(p)
            self.assertEqual(st["done"], [])
            st["week"] = "week-2026-W24"
            st["done"].append("signals")
            weekly_run.save_state(p, st)
            self.assertEqual(weekly_run.load_state(p)["done"], ["signals"])


class TestMapMan(unittest.TestCase):
    def test_haversine(self):
        self.assertAlmostEqual(themapman.haversine(29.76, -95.37, 29.76, -95.37), 0.0, places=3)
        d = themapman.haversine(29.7600, -95.3700, 29.7600, -95.3690)  # ~10^-3 deg lng
        self.assertTrue(80 < d < 120)   # ~96 m at this latitude

    def test_is_blocked(self):
        self.assertTrue(themapman.is_blocked("Walmart Supercenter"))
        self.assertTrue(themapman.is_blocked("AT&T Store"))      # carrier chain blocked
        self.assertFalse(themapman.is_blocked("Joe's Taqueria"))
        self.assertFalse(themapman.is_blocked(""))

    def test_is_commercial(self):
        self.assertTrue(themapman.is_commercial(["restaurant", "point_of_interest"]))
        self.assertFalse(themapman.is_commercial(["route"]))
        self.assertFalse(themapman.is_commercial([]))

    def test_has_phone(self):
        self.assertTrue(themapman.has_phone("(713) 555-0100"))
        self.assertFalse(themapman.has_phone("12"))
        self.assertFalse(themapman.has_phone(None))

    def test_lead_to_business_shape(self):
        lead = {"address": "5 Main St", "lat": 29.7, "lng": -95.3, "state": "TX",
                "zone_label": "FRESH", "status": dot.STATUS_LEAD}
        resolved = {"name": "Joe's Cafe", "phone": "(713) 555-0100",
                    "address": "5 Main St, Houston, TX", "website": "x.com",
                    "types": "restaurant, food, point_of_interest",
                    "fiber_lat": 29.7, "fiber_lng": -95.3, "status": "RESOLVED"}
        b = themapman.lead_to_business(lead, resolved)
        self.assertEqual(b["name"], "Joe's Cafe")
        self.assertTrue(b["has_phone"])
        self.assertEqual(b["types"], ["restaurant", "food", "point_of_interest"])
        self.assertEqual(b["zone_label"], "FRESH")     # carried from the lead
        self.assertEqual(b["status"], dot.STATUS_LEAD)
        # the shaped dict scores as a callable business
        self.assertTrue(score.score_business(b)["callable"])

    def test_enrich_leads_uses_resolver(self):
        orig = themapman.resolve
        themapman.resolve = lambda addr, lat=None, lng=None, st=None, api_key=None: {
            "name": "Clinic", "phone": "7135550100", "address": addr,
            "types": "doctor", "fiber_lat": lat, "fiber_lng": lng, "status": "RESOLVED"}
        try:
            out = themapman.enrich_leads([{"address": "9 Oak", "lat": 1, "lng": 2,
                                           "status": dot.STATUS_LEAD}])
        finally:
            themapman.resolve = orig
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "Clinic")
        self.assertTrue(out[0]["has_phone"])

    def test_key_resolution(self):
        self.assertEqual(themapman._key("abc"), "abc")        # explicit key wins
        orig = themapman.API_KEY
        themapman.API_KEY = ""
        try:
            with self.assertRaises(RuntimeError):              # none anywhere -> error
                themapman._key(None)
        finally:
            themapman.API_KEY = orig


class TestWeeklyEnrichInProcess(unittest.TestCase):
    def test_enrich_runs_mapman_when_no_output_file(self):
        orig = themapman.resolve
        themapman.resolve = lambda addr, lat=None, lng=None, st=None, api_key=None: {
            "name": "Clinic", "phone": "7135550100", "address": addr,
            "types": "doctor", "fiber_lat": lat, "fiber_lng": lng, "status": "RESOLVED"}
        prev_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        os.environ["GOOGLE_MAPS_API_KEY"] = "test-key"
        try:
            with tempfile.TemporaryDirectory() as d:
                leads = os.path.join(d, "leads.json")
                enriched = os.path.join(d, "enriched.json")
                with open(leads, "w") as f:
                    json.dump([{"address": "9 Oak St", "lat": 1.0, "lng": 2.0,
                                "status": dot.STATUS_LEAD, "zone_label": "FRESH"}], f)
                args = types.SimpleNamespace(enriched=enriched, leads=leads)
                self.assertTrue(weekly_run.stage_enrich(args))
                with open(enriched) as f:
                    out = json.load(f)
                self.assertEqual(len(out), 1)
                self.assertEqual(out[0]["name"], "Clinic")
        finally:
            themapman.resolve = orig
            if prev_key is None:
                os.environ.pop("GOOGLE_MAPS_API_KEY", None)
            else:
                os.environ["GOOGLE_MAPS_API_KEY"] = prev_key

    def test_enrich_checkpoints_when_nothing_available(self):
        with tempfile.TemporaryDirectory() as d:
            args = types.SimpleNamespace(enriched=os.path.join(d, "missing.json"), leads=None)
            self.assertFalse(weekly_run.stage_enrich(args))


def _temp_queue():
    d = tempfile.mkdtemp()
    return tgt.TargetQueue(os.path.join(d, "q.json"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
