"""optimus_feed.py -- push each run's classification evidence to GitHub.

WHY
    Debugging the gold classifier has been running on photographs of a console.
    That is slow, lossy, and the one field that decides gold vs grey --
    curr_ntwrk_bld_type_cd -- never survives a phone camera.

    The hunter already holds a GitHub token (gh_put). So it publishes a small
    JSON report per run to the repo, where Claude reads it directly. No sheet,
    no Autosheet credits, no screenshots.

WHAT IT PUBLISHES
    optimus/_feed/latest.json         always the most recent run
    optimus/_feed/<run_id>.json       one per run, kept as history

    counts            green / fiber / copper / unknown / no_code
    undecoded_codes   every build code we could not decode + a sample address
    samples           up to SAMPLE_CAP real records with their BUILD CODE and
                      resulting classification -- this is the payload that
                      actually answers "why is this dot grey"
    dedupe            duplicates seen, GOLD->GREY flips, failed writes

PRIVACY / SIZE
    Addresses and coordinates only. The subscriber BAN is reduced to a boolean:
    the account number itself is never published. Capped so a long sweep cannot
    push a huge file.
"""
import json
import os
import time

SAMPLE_CAP = 300          # records carried per run
FLUSH_EVERY = 250         # publish mid-run too, so a force-quit still reports

_SAMPLES = []
_STATE = {"pushed": 0, "run_id": "", "operator": "", "area": "",
          "fingerprint": "", "machine": "", "mode": ""}


def configure(run_id="", operator="", area="", fingerprint="", mode=""):
    _STATE["run_id"] = str(run_id or "")
    _STATE["operator"] = str(operator or "")
    _STATE["area"] = str(area or "")
    _STATE["fingerprint"] = str(fingerprint or "")
    _STATE["mode"] = str(mode or "")
    _STATE["machine"] = (os.environ.get("COMPUTERNAME")
                         or os.environ.get("HOSTNAME") or "")


def note(address, lat, lng, ban, build_code, classification, color):
    """Record one classified dot. Never raises into the sweep.

    Keeps a spread rather than the first N: once full, it replaces an earlier
    entry so late cells are represented too. GOLD and undecoded records are
    always kept -- those are the ones worth looking at.
    """
    try:
        if len(_SAMPLES) >= SAMPLE_CAP:
            keep = color in ("ORANGE", "GOLD") or not build_code
            if not keep:
                return
            _SAMPLES.pop(0)
        _SAMPLES.append({
            "address": str(address or "")[:120],
            "lat": lat, "lng": lng,
            "ban_present": bool(ban),           # never the account number
            "build_code": str(build_code or ""),
            "status": str(classification or ""),
            "color": str(color or ""),
        })
    except Exception:
        pass


_EMPTY = []
EMPTY_CAP = 3             # specimens kept
EMPTY_BYTES = 4000        # per specimen


def note_empty(url, content_type, body):
    """Keep a specimen of a 200 response that decoded to ZERO leads.

    This is the failure that has cost the most time: AT&T answers, the bytes
    arrive, and nothing comes out. Without the body there is no way to tell an
    auth redirect from a changed payload shape from an empty viewport.
    """
    try:
        if len(_EMPTY) >= EMPTY_CAP:
            return
        if isinstance(body, bytes):
            body = body.decode("utf-8", "replace")
        body = str(body or "")
        _EMPTY.append({
            "url": str(url or "")[:300],
            "content_type": str(content_type or "")[:80],
            "total_bytes": len(body),
            "body_head": body[:EMPTY_BYTES],
        })
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CUSTOMER SPECIMENS -- the evidence that decodes `unavailable`.
#
# Gold is decided by curr_ntwrk_bld_type_cd, and `unavailable` -- AT&T's most
# common value -- is in neither the fiber nor the copper list. Every customer
# carrying it has been guessed at all day. Guessing has now been wrong in both
# directions: "gold" put existing fiber customers on the call list, "grey" threw
# real copper away.
#
# So stop guessing and look. These are FULL records for CUSTOMER dots (a BAN is
# present), which is the population the question is about. Some other field --
# `speed` is the obvious candidate -- almost certainly separates a DSL customer
# from a fiber one, and it is already in the payload we are throwing away.
#
# The BAN itself is redacted to a boolean. It is an account number and it is not
# needed to answer the question.
# ---------------------------------------------------------------------------
CUSTOMER_CAP = 40

_CUSTOMERS = []
_CUST_SEEN = set()


def note_customer(raw, code, color):
    """Keep a full specimen of a CUSTOMER record. Never raises into a sweep.

    Spread across build codes rather than first-come: one specimen of forty
    different codes answers the question, forty of the same code does not.
    """
    try:
        if not isinstance(raw, dict):
            return
        key = (str(code or "").strip().lower(), str(color or ""))
        if key in _CUST_SEEN and len(_CUSTOMERS) >= 8:
            return                      # already have this code represented
        if len(_CUSTOMERS) >= CUSTOMER_CAP:
            return
        _CUST_SEEN.add(key)
        rec = {}
        for k, v in raw.items():
            lk = str(k).lower()
            if "ban" in lk:             # subscriber_ban, subscriber_ban_masked
                rec[k] = bool(str(v or "").strip())
            else:
                rec[k] = v
        rec["_our_color"] = color
        _CUSTOMERS.append(rec)
    except Exception:
        pass


_DIAG = {}


def note_diagnostic(d):
    """Store the capture-state diagnostic for this run (last one wins)."""
    try:
        _DIAG.clear()
        _DIAG.update(d or {})
    except Exception:
        pass


_AUTH_HINTS = ("sign in", "log in", "login", "session has expired",
               "session expired", "not authorized", "unauthorized",
               "access denied", "csrf", "please authenticate",
               "you achieve is a 24/7 platform", "choose your method of access")


def diagnose(body, content_type=""):
    """Say IN ENGLISH why a 200 response produced no leads.

    A silent zero is indistinguishable from an empty neighbourhood, and that
    ambiguity has cost more time here than any real bug. JSON is tried FIRST:
    this endpoint is declared text/html but actually serves JSON, so sniffing
    the content-type would misread a legitimate error envelope as a login page.
    """
    try:
        if isinstance(body, bytes):
            body = body.decode("utf-8", "replace")
        body = (body or "").strip()
        if not body:
            return ("EMPTY RESPONSE -- AT&T returned nothing at all.", "empty")
        low = body[:4000].lower()

        import json as _j
        try:
            data = _j.loads(body)
        except Exception:
            data = None

        if data is None:                       # not JSON: HTML of some kind
            if any(h in low for h in _AUTH_HINTS):
                return ("SESSION EXPIRED -- AT&T sent a login page, not data. "
                        "Log OUT of youachieve.att.com, close the browser, log "
                        "back in, then re-run.", "auth")
            return ("NOT JSON -- AT&T sent something this parser cannot read. "
                    "First 120 chars: %s" % body[:120].replace("\n", " "),
                    "notjson")

        if not isinstance(data, dict):
            return ("JSON was a %s, not an object -- shape changed."
                    % type(data).__name__, "shape")

        err = data.get("error")
        if isinstance(err, dict) and str(err.get("status")) not in ("200", "None"):
            return ("AT&T ERROR %s: %s -- usually a stale csrfToken. Log out "
                    "and back in." % (err.get("status"), err.get("message")),
                    "error")
        if data.get("success") is False:
            return ("AT&T replied success=false -- the request was rejected. "
                    "Usually a stale csrfToken: log out and back in.", "auth")

        content = data.get("content")
        if isinstance(content, list) and not content:
            return ("VALID reply, but AT&T returned ZERO addresses for this "
                    "viewport. Nothing serviceable here, or the search centre "
                    "moved off the dots.", "novalues")
        if isinstance(content, list) and content:
            rec = content[0] if isinstance(content[0], dict) else {}
            keys = sorted(rec.keys())
            flat = set(k.lower().replace("_", "") for k in keys)
            if flat & {"address", "addr", "fulladdress", "serviceaddress",
                       "streetaddress", "addressline", "address1"}:
                return ("%d records WITH an address came back -- the payload is "
                        "fine, so the failure is downstream of the parse. Keys: "
                        "%s" % (len(content), ", ".join(keys)[:200]), "parsed")
            return ("PAYLOAD SHAPE CHANGED -- %d records came back but none "
                    "carry a readable address. Record keys: %s"
                    % (len(content), ", ".join(keys)[:200]), "shape")
        return ("VALID JSON but no 'content' list. Top-level keys: %s"
                % ", ".join(sorted(data.keys()))[:200], "shape")
    except Exception as e:
        return ("could not diagnose (%s)" % str(e)[:60], "unknown")


# ---------------------------------------------------------------------------
# RUN PHASE -- how far the run actually got.
#
# Every boundary counter below lives INSIDE the sweep, so a run that dies before
# the sweep starts reports all-nulls and the report cannot say why. That is what
# happened all of 2026-08-23: six runs, six empty reports, and no way to tell
# "swept and found nothing" from "never reached the map". The phase list is the
# breadcrumb -- each milestone is stamped as it is passed AND pushed live, so a
# run that hangs or is force-quit still names the last thing it did.
# ---------------------------------------------------------------------------
PHASES = ("start", "browser_up", "page_loaded", "sheet_open", "resume_loaded",
          "wait_done", "diag_done", "sweep_start", "pass_done", "exit")

_PHASES = []          # [(name, "HH:MM:SS", seconds_since_start)]
_T0 = [None]
_HEARTBEAT = [None]   # gh_put, set by arm_heartbeat()


def arm_heartbeat(gh_put):
    """Give the feed an uploader so phase() can push live. Optional."""
    _HEARTBEAT[0] = gh_put


def phase(name, log=None):
    """Stamp a milestone and push it immediately.

    Pushed rather than buffered on purpose: the whole point is to survive a run
    that never reaches its own exit report.
    """
    try:
        now = time.time()
        if _T0[0] is None:
            _T0[0] = now
        _PHASES.append((str(name), time.strftime("%H:%M:%S"),
                        round(now - _T0[0], 1)))
        if log:
            log("  [phase] %s" % name)
        put = _HEARTBEAT[0]
        if put:
            put("optimus/_feed/heartbeat.json", json.dumps({
                "run_id": _STATE["run_id"], "operator": _STATE["operator"],
                "machine": _STATE["machine"],
                "build_fingerprint": _STATE["fingerprint"],
                "mode": _STATE.get("mode", ""),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_phase": name,
                "phases": [list(p) for p in _PHASES],
            }, indent=1))
    except Exception:
        pass


def last_phase():
    return _PHASES[-1][0] if _PHASES else ""


def phase_report(log=print):
    """Where the run got to, and how long each step took."""
    log("")
    log("=== RUN PHASES ===")
    if not _PHASES:
        log("  (none stamped -- this build predates phase tracking)")
        return
    for name, at, secs in _PHASES:
        log("  %-14s %s  (+%ss)" % (name, at, secs))
    reached = set(n for n, _, _ in _PHASES)
    missed = [p for p in PHASES if p not in reached]
    if missed:
        log("  NEVER REACHED: %s" % ", ".join(missed))


# ---------------------------------------------------------------------------
# CAPTURE TRUTH -- counters at every boundary, so the FIRST place the dots
# disappear is named instead of inferred. A viewport with visible dots that
# reports zero is lying somewhere; this says where.
# ---------------------------------------------------------------------------
_BOUNDARIES = [
    ("delivery",       "AT&T response"),
    ("raw_features",   "features parsed from the payload"),
    ("rendered",       "features the live map is rendering"),
    ("classified",     "classify_wire output"),
    ("written",        "rows written to the sheet"),
]

_TRUTH = {"delivery": None, "raw_features": None, "rendered": None,
          "classified": None, "written": None, "auth_ok": None,
          "map_ok": None, "zoom_ok": None, "notes": []}


def truth(**kw):
    """Record a boundary count. Unset stays None -- never confuse 'not measured'
    with 'measured zero', which is the whole point of the exercise."""
    try:
        for k, v in kw.items():
            if k == "note":
                _TRUTH["notes"].append(str(v)[:160])
            elif k in _TRUTH:
                _TRUTH[k] = v
    except Exception:
        pass


def first_failure():
    """The first boundary where a nonzero upstream becomes zero.

    Returns (boundary_key, human_label) or (None, '') when nothing broke.
    A boundary that was never measured cannot be blamed.
    """
    prev = None
    measured = False
    for key, label in _BOUNDARIES:
        v = _TRUTH.get(key)
        if v is None:
            continue
        if not measured and v == 0:
            # Nothing upstream was ever measured, so this boundary did not lose
            # the dots -- the run never got far enough to hand it any. Blaming
            # it sends the next hour to the wrong file.
            continue
        measured = True
        if isinstance(v, str):          # delivery is a verdict, not a count
            if v not in ("DATA_OK", "OK"):
                return key, label
            prev = None
            continue
        if v == 0 and (prev is None or prev > 0):
            return key, label
        prev = v
    return None, ""


def truth_report(log=print):
    """One readable block per run. No interpretation required."""
    t = _TRUTH
    log("")
    log("=== PRECISE HUNTER CAPTURE TRUTH ===")
    log("  auth / delivery   : %s" % (t.get("delivery") or "not measured"))
    log("  map + style ok    : %s" % t.get("map_ok"))
    log("  zoom inside band  : %s" % t.get("zoom_ok"))
    for key, label in _BOUNDARIES[1:]:
        v = t.get(key)
        log("  %-17s : %s" % (label[:17], "not measured" if v is None else v))
    for n in t.get("notes", [])[:6]:
        log("    - %s" % n)
    k, label = first_failure()
    if k:
        log("  RESULT: BROKEN AT %s" % k.upper())
        log("  FIRST FAILURE: %s" % label)
    elif not any(t.get(b) for b, _ in _BOUNDARIES):
        # All zeros with nothing upstream measured is NOT health. It means the
        # sweep never ran, and calling that "HEALTHY" is how six empty reports
        # in a row read as six clean runs.
        log("  RESULT: THE SWEEP NEVER RAN -- no boundary was ever measured.")
        log("  See RUN PHASES below for how far it got.")
    else:
        log("  RESULT: HEALTHY (no boundary lost the dots)")
    log("=" * 36)


def build_report(counts=None, undecoded=None, undecoded_samples=None,
                 dedupe=None, note_text=""):
    codes = {}
    for code, n in (undecoded or {}).items():
        codes[code] = {"count": n,
                       "sample_address": (undecoded_samples or {}).get(code, "")}
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_id": _STATE["run_id"],
        "operator": _STATE["operator"],
        "machine": _STATE["machine"],
        "area": _STATE["area"],
        "build_fingerprint": _STATE["fingerprint"],
        "counts": dict(counts or {}),
        "undecoded_codes": codes,
        "dedupe": dict(dedupe or {}),
        "mode": _STATE.get("mode", ""),
        "phases": [list(p) for p in _PHASES],
        "last_phase": last_phase(),
        "capture_truth": dict(_TRUTH),
        "first_failure": first_failure()[0],
        "capture_diagnostic": dict(_DIAG),
        "customer_specimens": list(_CUSTOMERS),
        "customer_specimen_count": len(_CUSTOMERS),
        "zero_lead_responses": list(_EMPTY),
        "sample_count": len(_SAMPLES),
        "samples": list(_SAMPLES),
        "note": note_text,
    }


def publish(gh_put, counts=None, undecoded=None, undecoded_samples=None,
            dedupe=None, note_text="", log=print):
    """Push the report. `gh_put(path, text)` is the hunter's own uploader.

    Returns True if anything landed. Best-effort: a failure here must never
    affect a sweep, so every path is caught.
    """
    try:
        rep = build_report(counts, undecoded, undecoded_samples, dedupe,
                           note_text)
        body = json.dumps(rep, indent=1, default=str)
        ok = gh_put("optimus/_feed/latest.json", body)
        rid = rep.get("run_id") or "run"
        if rid:
            gh_put("optimus/_feed/%s.json" % rid, body)
        if ok:
            _STATE["pushed"] += 1
            log("  FEED -> pushed %d samples to optimus/_feed/latest.json"
                % len(_SAMPLES))
        else:
            log("  (feed push failed -- is github_token.txt present?)")
        return bool(ok)
    except Exception as e:
        log("  (feed skipped: %s)" % str(e)[:70])
        return False


def should_flush():
    """True every FLUSH_EVERY samples, so a killed run still reports."""
    n = len(_SAMPLES)
    return n and n % FLUSH_EVERY == 0
