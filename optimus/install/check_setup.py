#!/usr/bin/env python3
"""
OPTIMUS SETUP CHECKER -- prints a PASS/FAIL line for everything the map
tools need. Run by the installer and the updater; safe to run by hand:
    python check_setup.py
"""

import os, subprocess, sys

HOME = os.path.join(os.path.expanduser("~"), "Optimus")
REPO = os.path.join(HOME, "repo")
TOOLS = ["precise_fiber_hunter.py", "fiber_zone_scanner.py",
         "optimus_dot_detect.py", "fiber_precise_pipeline.py",
         "business_score.py", "ghl_loader.py"]
PKGS = ["numpy", "PIL", "scipy", "playwright", "gspread", "google.auth",
        "requests"]
CREDS_PATHS = [os.path.join(HOME, "google_creds.json"),
               os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "google_creds.json")]

ok = True


def report(label, passed, hint=""):
    global ok
    print(" [%s] %s%s" % ("PASS" if passed else "FAIL", label,
                          ("  -> " + hint) if (hint and not passed) else ""))
    if not passed:
        ok = False


def main():
    print("\n OPTIMUS SETUP CHECK")
    print(" " + "-" * 50)

    report("Python %d.%d" % sys.version_info[:2], sys.version_info >= (3, 9),
           "install Python 3.9+")

    for p in PKGS:
        try:
            __import__(p)
            report("package: %s" % p, True)
        except Exception:
            report("package: %s" % p, False, "pip install -r requirements.txt")

    # chromium for playwright
    try:
        out = subprocess.run([sys.executable, "-m", "playwright", "install",
                              "--dry-run", "chromium"],
                             capture_output=True, text=True, timeout=60)
        blob = (out.stdout or "") + (out.stderr or "")
        report("playwright chromium", "is already installed" in blob.lower()
               or out.returncode == 0, "python -m playwright install chromium")
    except Exception:
        report("playwright chromium", False,
               "python -m playwright install chromium")

    # repo + tools present
    opt = os.path.join(REPO, "optimus")
    report("repo at %s" % REPO, os.path.isdir(os.path.join(REPO, ".git")),
           "run install_optimus.bat")
    for t in TOOLS:
        report("tool: %s" % t, os.path.exists(os.path.join(opt, t)),
               "run update_optimus.bat")

    # google sheets token
    creds = next((p for p in CREDS_PATHS if os.path.exists(p)), None)
    report("google_creds.json", bool(creds),
           "put your service-account JSON at %s" % CREDS_PATHS[0])

    # AT&T map login profile (created by --login)
    profile = os.path.join(opt, "att_profile")
    report("AT&T map login saved", os.path.isdir(profile),
           "cd %s && python precise_fiber_hunter.py --login" % opt)

    print(" " + "-" * 50)
    print(" ALL GOOD - ready to hunt.\n" if ok else
          " Fix the FAIL lines above, then re-run this check.\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
