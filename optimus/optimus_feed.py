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
          "fingerprint": "", "machine": ""}


def configure(run_id="", operator="", area="", fingerprint=""):
    _STATE["run_id"] = str(run_id or "")
    _STATE["operator"] = str(operator or "")
    _STATE["area"] = str(area or "")
    _STATE["fingerprint"] = str(fingerprint or "")
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
        "capture_diagnostic": dict(_DIAG),
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
