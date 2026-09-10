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

 * TWO DENY SOURCES, first that loads wins, both fail open:
     1. optimus_deny.json  — ships NEXT TO this gate, is in _CORE_FILES, and refreshes every
        launch through the hunter's self_update. THIS IS THE DEFAULT PATH. No hosting, no
        token, no URL: to lock a machine you edit this file and push; its next run locks.
     2. OPTIMUS_DENY_URL    — optional remote URL for an INSTANT kill without a deploy. If you
        use it, host it readable WITHOUT auth (it ships to every PC incl. the thief's — an
        embedded PAT would leak your private repos). Env var overrides the file.
   Shape (either source):  { "kill_all": false, "kill_all_confirm": "", "denied": ["<id>"] }

WIRED 2026-09-10 into precise_fiber_hunter.py main() (check_license() before self_update).
Both this gate and optimus_deny.json are in _CORE_FILES, so a push self-deploys to every
hunter PC — that push is a FLEET DEPLOY, Patrick's call BY NAME (RULE 0).

  TO LOCK ONE REP : put their 16-char machine id (printed in their DEACTIVATED notice and in
                    RUN_HUNTER's startup line) into "denied" in optimus_deny.json, then push.
  TO KILL THE FLEET: set "kill_all": true AND "kill_all_confirm" to TODAY's date, then push.
  TO UNLOCK        : remove the id (or clear kill_all), then push.
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

# Where the deny list is read from, in order. The FIRST source that loads wins;
# a source that is missing / unreachable / malformed is skipped, and if NONE load
# the machine RUNS (fail open, deliberately).
#   1. OPTIMUS_DENY_URL  -- a remote URL, if the env var is set. Lets you kill a
#      machine INSTANTLY, without waiting for a code deploy.
#   2. optimus_deny.json  -- the file that ships NEXT TO this gate. It is in
#      _CORE_FILES, so it refreshes every launch through the hunter's self_update.
#      Editing it + pushing locks a machine on its next run. NO hosting required --
#      this is the path that works today.
def _local_deny_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "optimus_deny.json")

def _evaluate(data, fp, source):
    """Apply the deny rules to one loaded list. Returns (reason, source) or None."""
    # kill_all is a footgun: a stray/stale/typo'd `true` in a valid, reachable list would
    # stop the whole fleet. So a bare `true` is INERT -- it is only honoured when
    # kill_all_confirm equals TODAY's date. A leftover `true` does nothing.
    if data.get("kill_all") is True:
        today = datetime.date.today().isoformat()
        if str(data.get("kill_all_confirm", "")) == today:
            return ("kill_all (confirmed " + today + ")", source)
        # else: unconfirmed kill_all -> ignored, fall through to per-machine deny
    if fp in (data.get("denied") or []):
        return ("this machine's id is on the deny list", source)
    return None

def _deny_reason(fp: str):
    """Returns (reason, source) if this machine should lock, else None. Fails OPEN."""
    url = os.environ.get("OPTIMUS_DENY_URL", "").strip()
    if url:
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                hit = _evaluate(json.loads(r.read().decode()), fp, url)
                if hit:
                    return hit
        except Exception:
            pass  # unreachable / malformed -> skip to the local file
    try:
        p = _local_deny_path()
        with open(p, encoding="utf-8") as f:
            hit = _evaluate(json.loads(f.read()), fp, p)
            if hit:
                return hit
    except Exception:
        pass  # missing / malformed -> ALLOW (fail open)
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
