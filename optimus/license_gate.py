"""
license_gate.py — a SPEED BUMP against stolen copies. Read this honestly:

  This is NOT a lock. precise_fiber_hunter.py ships as readable Python; a thief opens it
  in Notepad, deletes the check_license() import, and it's gone in 30 seconds. The REAL
  lock is credential rotation — no fiberscanner key, no GHL token, no AT&T profile means a
  stolen copy signs into nothing and writes nowhere, and that CANNOT be edited out of a .py.
  Rotate the creds. This gate just makes a casual copy stop working until someone bothers.

DESIGN (corrected after review — the earlier version had two serious bugs):

 * DEFAULT-ALLOW, remote DENY list.  Fail OPEN. If the deny list is unreachable or
   malformed, the software RUNS. Rationale, measured from this fleet's history: a gate that
   fails CLOSED once silently stopped every PC and cost 10 days. A gate that fails open just
   lets a thief run a few more days. The downside is wildly asymmetric — never fail closed.

 * KILL SWITCH still works: publish this machine's fingerprint into the deny list (or set
   kill_all), and it locks at next launch. One edit disables one machine or the whole field.

 * FINGERPRINT = MachineGuid only.  NOT hostname — hostname changes on rename and would lock
   a legit machine with no clue why. MachineGuid survives renames. On lock we print the
   fingerprint LOUDLY so authorizing/removing a machine is a copy-paste, not an investigation.

 * EXIT 0 on lock.  RUN_HUNTER.bat relaunches on ANY non-zero exit — so a non-zero here would
   loop lock->relaunch->lock forever and hammer the deny-list host (a self-DDoS). Exit 0 tells
   the launcher "closed on purpose", so it stops cleanly. The lock NOTICE is how the operator
   knows why — never a silent exit.

 * NO TOKEN embedded.  The deny list must live at a URL readable WITHOUT auth (it ships to
   every hunter PC, including the thief's — an embedded PAT would hand them your private repos).
   Host it somewhere that stays reachable after the repos go private. Point OPTIMUS_DENY_URL
   at it. Shape:
       { "kill_all": false, "denied": ["<fingerprint>", "..."] }

Wire-in (only after Patrick says go BY NAME — precise_fiber_hunter.py is in _CORE_FILES, so
pushing it self-deploys to every hunter PC; that's a fleet deploy, RULE 0):
    from license_gate import check_license
    check_license()          # very top of main()
"""
import os, sys, json, hashlib, subprocess, urllib.request, datetime

def fingerprint() -> str:
    """sha256(MachineGuid)[:16] — survives hostname changes."""
    guid = ""
    try:
        out = subprocess.check_output(
            ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
            stderr=subprocess.DEVNULL, text=True)
        guid = out.split()[-1]
    except Exception:
        guid = os.environ.get("COMPUTERNAME", "unknown")
    return hashlib.sha256(guid.encode()).hexdigest()[:16]

def _deny_reason(fp: str):
    """Returns (reason, source_url) if this machine should lock, else None. Fails OPEN."""
    url = os.environ.get("OPTIMUS_DENY_URL", "").strip()
    if not url:
        return None  # not configured -> ALLOW (fail open)
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return None  # unreachable / malformed -> ALLOW (fail open, deliberately)
    # kill_all is a footgun: a stray/stale/typo'd `true` in a valid, reachable file would
    # stop the whole fleet, and fail-open does NOT catch that (the fetch succeeded). So a
    # bare `true` is INERT — it is only honoured when kill_all_confirm equals TODAY's date.
    # Firing it deliberately is still a one-line edit; a leftover `true` does nothing.
    if data.get("kill_all") is True:
        today = datetime.date.today().isoformat()
        if str(data.get("kill_all_confirm", "")) == today:
            return ("kill_all (confirmed " + today + ")", url)
        # else: unconfirmed kill_all -> ignored, fall through to per-machine deny
    if fp in (data.get("denied") or []):
        return ("this machine's id is on the deny list", url)
    return None

def check_license():
    fp = fingerprint()
    hit = _deny_reason(fp)
    if hit:
        reason, src = hit
        sys.stderr.write(
            "\n============================================================\n"
            "  OPTIMUS - this copy has been DEACTIVATED by the owner.\n"
            f"  Machine id : {fp}\n"
            f"  Reason     : {reason}\n"
            f"  Source     : {src}\n"
            "  If this is a mistake, send the owner this machine id.\n"
            "============================================================\n\n")
        sys.exit(0)   # exit 0 so the relaunch loop stops cleanly. Notice above says why.

if __name__ == "__main__":
    fp = fingerprint()
    check_license()
    print("running (not on deny list).  machine id:", fp)
