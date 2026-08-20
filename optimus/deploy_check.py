"""
deploy_check.py -- prove a push actually reached the machine that runs the hunter.

WHY THIS EXISTS
    Three separate times on 2026-08-20 a fix was believed live when it was not:

    1. It was pushed to optimus-map-tools while the hunter pulls
       Go-High-Level-MCP-2026-Complete. Different repo. Never arrived.
    2. The commit was reset off the branch, and `git fetch` in the dev
       environment served a STALE tip, so 25 pushes were rejected against a tip
       git insisted was an ancestor.
    3. BUILD_DATE still read the old date because the bump was a separate edit
       that had not been pushed -- so the console reported old code while
       running new code.

    Every one of those is invisible to `git log` and `git status`. The only
    thing that settles it is fetching the bytes the hunter itself downloads.

RUN
    python deploy_check.py                 # check every core file
    python deploy_check.py --show BUILD_DATE   # also print matching lines

WHAT IT DOES
    Downloads each file in _CORE_FILES straight from the raw URL the hunter
    uses, and compares it byte-for-byte with the copy next to this script.
    IN SYNC means a launch on that machine will run exactly what you have.
"""
import hashlib
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# Must match _CORE_FILES in precise_fiber_hunter.py. Anything absent from that
# tuple is NOT auto-deployed to a machine without git -- pushing it changes
# nothing there. Keep the two lists identical.
CORE_FILES = ("precise_fiber_hunter.py", "optimus_dot_detect.py",
              "optimus_api_capture.py", "hunter_fixes.py",
              "backend_classifier.py", "build_codes.json",
              "verify_gold_capture.py", "deploy_check.py")

GH_REPO = "patricksiado-prog/Go-High-Level-MCP-2026-Complete"
GH_BRANCH = "claude/optimus-map-tools-setup-6dcl6o"


def fetch(name):
    url = ("https://raw.githubusercontent.com/%s/%s/optimus/%s?cb=%d"
           % (GH_REPO, GH_BRANCH, name, int(time.time())))
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    return urllib.request.urlopen(req, timeout=30).read()


def main():
    show = None
    if "--show" in sys.argv:
        i = sys.argv.index("--show")
        if i + 1 < len(sys.argv):
            show = sys.argv[i + 1]

    print("\nrepo   %s" % GH_REPO)
    print("branch %s" % GH_BRANCH)
    print("(this is what a launch downloads -- not what git says)\n")
    print("%-28s %-10s %s" % ("FILE", "STATUS", "NOTE"))
    print("-" * 72)

    drift = []
    for name in CORE_FILES:
        local_path = os.path.join(HERE, name)
        try:
            remote = fetch(name)
        except Exception as e:
            print("%-28s %-10s %s" % (name, "NO REMOTE", str(e)[:32]))
            drift.append(name)
            continue
        if not os.path.exists(local_path):
            print("%-28s %-10s remote only" % (name, "NO LOCAL"))
            continue
        local = open(local_path, "rb").read()
        if local == remote:
            print("%-28s %-10s %s" % (name, "IN SYNC", hashlib.sha256(remote).hexdigest()[:12]))
        else:
            print("%-28s %-10s local %d B vs remote %d B" % (
                name, "*DRIFT*", len(local), len(remote)))
            drift.append(name)
        if show:
            for line in remote.decode("utf-8", "replace").splitlines():
                if show in line:
                    print("      remote: %s" % line.strip()[:88])
                    break

    print("-" * 72)
    if drift:
        print("NOT DEPLOYED: %s" % ", ".join(drift))
        print("A launch on the hunter PC will NOT run your local copy of these.")
        return 1
    print("All core files match the branch. A launch runs exactly this code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
