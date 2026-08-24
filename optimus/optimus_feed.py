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
FLUSH_EVERY = 10          # TESTING: publish every 10 records for real-time feedback to GitHub

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
EMPTY_CAP = 6             # specimens kept
EMPTY_BYTES = 4000        # per specimen

# Binary bodies are not failed JSON, they are images. Running them through the
# parser produced "NOT JSON -- First 120 chars: \x89PNG" noise that FILLED the
# evidence buffer, so the one specimen that mattered -- a 200 carrying real JSON
# that yielded zero leads -- was dropped before it could be read. Seen live
# 2026-08-23 on the first run that ever reached delivery=DATA_OK.
_BINARY_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"RIFF", b"\x00\x00\x01\x00",
                 b"%PDF", b"wOFF", b"wOF2", b"\x1f\x8b")


def is_binary(body):
    """True for an image/font/archive body -- never a failed JSON payload."""
    try:
        if isinstance(body, str):
            body = body.encode("utf-8", "ignore")
        head = (body or b"")[:8]
        if any(head.startswith(m) for m in _BINARY_MAGIC):
            return True
        return b"\x00" in (body or b"")[:512]      # NUL bytes: not text
    except Exception:
        return False


def note_empty(url, content_type, body):
    """Keep a specimen of a 200 response that decoded to ZERO leads.

    This is the failure that has cost the most time: AT&T answers, the bytes
    arrive, and nothing comes out. Without the body there is no way to tell an
    auth redirect from a changed payload shape from an empty viewport.

    Specimens are NOT first-come. A short redirect notice is nearly worthless;
    a 200 carrying JSON that yielded no leads is the whole answer. When the
    buffer is full, a valuable specimen evicts a worthless one.
    """
    try:
        if is_binary(body):
            return                    # an image is not a failed payload
        valuable = ("HTTP " not in str(body or "")[:8]
                    and len(str(body or "")) > 200)
        if len(_EMPTY) >= EMPTY_CAP:
            if not valuable:
                return
            for i, e in enumerate(_EMPTY):
                if e.get("total_bytes", 0) <= 200:
                    _EMPTY.pop(i)     # drop a redirect notice for real evidence
                    break
            else:
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


_STAGE_COUNTS = {}


def note_stages(d):
    """Stage counters from the hunter, carried into the report."""
    try:
        _STAGE_COUNTS.clear(); _STAGE_COUNTS.update(d or {})
    except Exception:
        pass


_CRASH = {}


def note_crash(summary, tb=""):
    """Record why a run died. Published, so nobody has to photograph a console.

    A run that exits before its first milestone reports all-nulls and looks
    exactly like a run that swept an empty street. The phase breadcrumb narrowed
    that to a window; this closes it by naming the exception itself.
    """
    try:
        _CRASH.clear()
        _CRASH.update({"summary": str(summary)[:300],
                       "traceback": str(tb or "")[-4000:],
                       "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# WIRE AUDIT -- one line per candidate backend record, appended, never
# overwritten within a run.
#
# The counters say WHERE leads are lost. This says WHAT each record actually
# carried, so gold and grey can be diffed field by field WITHOUT another field
# run. That is the whole point: the question "what separates gold from grey" has
# cost a day already, and the answer is in these records.
#
# SECRETS: any key containing 'ban' is published as a boolean. The account
# number never leaves the machine. Same for token/secret/auth/cookie/csrf.
# ---------------------------------------------------------------------------
AUDIT_CAP = 400              # lines per run, overall
# PER-COLOUR RESERVATION. A first-come cap is the wrong shape here: a
# green-heavy viewport fills 400 slots with green and leaves nothing to diff
# gold against, which is the entire question. Every colour gets a guaranteed
# quota, so ONE run always yields known-green, known-gold and known-grey
# records side by side from the same payload.
AUDIT_PER_COLOUR = 25
AUDIT_PATH = "optimus/_feed/wire_audit.jsonl"
_AUDIT = []
_AUDIT_BY_COLOUR = {}
_AUDIT_PUSHED = [0]


def audit_coverage():
    """What the audit has collected. A key prefixed '?' means the bucket is our
    own guess because AT&T's rendered colour was not available for that record --
    NOT ground truth, and it is marked so it can never be mistaken for it."""
    return dict(_AUDIT_BY_COLOUR)


def audit_disagreements():
    """Records where AT&T rendered one colour and our rule said another.

    This is the payload of the whole exercise: every row here is a case the
    current rule gets wrong, with the backend fields attached to explain why.
    """
    return [a for a in _AUDIT if a.get("agrees") is False]

_SECRET_HINT = ("ban", "token", "secret", "auth", "cookie", "csrf", "session",
                "password", "ssn")


def _safe_props(raw):
    """Every non-secret backend property, verbatim. Secrets -> boolean."""
    out = {}
    try:
        for k, v in (raw or {}).items():
            lk = str(k).lower()
            if any(h in lk for h in _SECRET_HINT):
                out[k] = bool(str(v or "").strip())
            elif isinstance(v, (str, int, float, bool)) or v is None:
                out[k] = v
            else:
                out[k] = str(v)[:120]
    except Exception:
        pass
    return out


def audit(cell=None, lat=None, lng=None, http_status=None, response_kind=None,
          raw=None, classification=None, reason="", queued=None,
          write_attempted=None, committed=None, seen=None, pending=None,
          observed_color=None):
    """Record one candidate. Never raises into a sweep.

    TWO SEPARATE VERDICTS, and they must never be conflated:

      classifier_result -- what OUR rule decided
      observed_color    -- what AT&T's own DOM marker is actually painted

    An earlier version bucketed the audit by `classification`, i.e. by the
    verdict of the classifier the audit exists to verify. That is circular: if
    the rule calls a real GOLD dot GREY, the audit files it under GREY and the
    error becomes invisible. observed_color must come from the rendered marker
    and NEVER from classify_wire.

    A row where the two disagree is the most valuable record this system can
    produce. It is the only thing that can prove the rule wrong.
    """
    try:
        # Bucket by what AT&T RENDERED when we know it; fall back to our own
        # verdict only to spread the sample, never as evidence.
        _obs = str(observed_color or "").upper()
        _col = _obs or ("?" + str(classification or "UNKNOWN").upper())
        _have = _AUDIT_BY_COLOUR.get(_col, 0)
        # Fill each colour's quota first; only then use the shared remainder.
        if _have >= AUDIT_PER_COLOUR and len(_AUDIT) >= AUDIT_CAP:
            return
        if _have >= AUDIT_PER_COLOUR:
            return
        r = raw or {}
        code = ""
        for k, v in r.items():
            if "bld_typ" in str(k).lower() or "bld_type" in str(k).lower():
                code = str(v or "")
        ban_present = False
        for k, v in r.items():
            if "ban" in str(k).lower() and "banner" not in str(k).lower():
                if str(v or "").strip():
                    ban_present = True
        _AUDIT.append({
            "run_id": _STATE.get("run_id"),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cell": cell, "lat": lat, "lng": lng,
            "http_status": http_status,
            "response_kind": response_kind,
            "subscriber_ban_present": ban_present,
            "curr_ntwrk_bld_type_cd": code,
            "backend_fields": _safe_props(r),
            "observed_color": _obs or None,   # AT&T's own rendering, or unknown
            "classifier_result": classification,
            "classifier_reason": reason,
            "agrees": (None if not _obs else
                       (_obs == str(classification or "").upper()
                        or (_obs == "GOLD" and str(classification).upper() == "ORANGE"))),
            "queued": queued, "write_attempted": write_attempted,
            "committed": committed, "seen": seen, "pending": pending,
        })
        _AUDIT_BY_COLOUR[_col] = _have + 1
    except Exception:
        pass


def publish_audit(gh_put, log=print):
    """Append this run's audit lines. Existing content is preserved, so a
    second run in the same session cannot erase the first one's evidence."""
    try:
        if not _AUDIT:
            return False
        lines = "\n".join(json.dumps(a, default=str) for a in _AUDIT)
        prev = ""
        try:
            prev = gh_get(AUDIT_PATH) or ""
        except Exception:
            prev = ""
        body = (prev.rstrip("\n") + "\n" + lines).lstrip("\n") if prev else lines
        ok = gh_put(AUDIT_PATH, body + "\n")
        if ok:
            _AUDIT_PUSHED[0] += len(_AUDIT)
            log("  WIRE AUDIT -> %d record(s) appended to %s"
                % (len(_AUDIT), AUDIT_PATH))
        return bool(ok)
    except Exception as e:
        log("  (wire audit skipped: %s)" % str(e)[:70])
        return False


_GH_GET = [None]


def arm_reader(fn):
    """Give the feed a way to READ a repo file, so the audit can append rather
    than overwrite. Without it each run would destroy the last run's evidence."""
    _GH_GET[0] = fn


def gh_get(path):
    fn = _GH_GET[0]
    return fn(path) if fn else ""


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
            blob = json.dumps({
                "run_id": _STATE["run_id"], "operator": _STATE["operator"],
                "machine": _STATE["machine"],
                "build_fingerprint": _STATE["fingerprint"],
                "mode": _STATE.get("mode", ""),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_phase": name,
                "phases": [list(p) for p in _PHASES],
            }, indent=1)
            put("optimus/_feed/heartbeat.json", blob)
            # ALSO per-run. The shared file is convenient but a second launch
            # overwrites it, and that is not hypothetical: on 2026-08-23 a
            # second window clobbered the breadcrumb of the run that was
            # actually working, leaving only the loser's trail to read.
            rid = _STATE.get("run_id")
            if rid:
                put("optimus/_feed/heartbeat_%s.json" % rid, blob)
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
        "stage_counters": dict(_STAGE_COUNTS),
        "crash": dict(_CRASH),
        "wire_audit_records": len(_AUDIT),
        "wire_audit_by_colour": dict(_AUDIT_BY_COLOUR),
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
