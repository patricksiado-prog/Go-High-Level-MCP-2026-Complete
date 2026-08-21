"""
WHO SCANNED WHAT  --  operator identity for every row the hunter writes.
===========================================================================
Patrick, 2026-08-21: "add an initial part to the software so we can identify
who scanned what and mark to Google sheet."

THE PROBLEM THIS SOLVES
Five people now run the hunter (Dave, Ed, Zack, Ara, Daniel). Until today every
row they captured looked identical in the sheet. So:

  - nobody could be told "your sweeps are the best ones, do more of that"
  - nobody could be told "your last three sweeps captured nothing, something's
    wrong on your machine"
  - a bad or empty capture could not be traced back to a person or a PC
  - "who found this lead" -- the question that decides who gets paid -- had no
    answer in the data at all

RUN_ID already said WHICH RUN produced a row. It never said WHOSE.

HOW IT DECIDES WHO YOU ARE  (first hit wins, most explicit first)
  1. --operator "Dave"        command line, wins over everything
  2. OPTIMUS_OPERATOR=Dave    environment variable, for the launcher/scheduler
  3. operator.json            what you answered last time, saved next to the code
  4. an interactive prompt    asked ONCE, then remembered forever
  5. the machine's hostname   last resort, so a row is never left anonymous

RULE THAT MATTERS MOST: this must NEVER hang an unattended run. A scheduled
sweep or the write-worker subprocess has no human at the keyboard, so a prompt
there would block forever and the sweep would silently never start. Step 4 is
therefore skipped whenever stdin is not a real terminal, or --auto is on, or
the process is the uploader. Those fall straight through to step 5.
"""

import json
import os
import re
import socket
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_STORE = os.path.join(_HERE, "operator.json")

# Everyone currently running a hunter. Shown as a numbered menu so nobody has to
# type (and so we don't end up with "dave", "Dave ", "DAVE" as three operators).
# Typing a name that isn't listed is still allowed -- this is a convenience, not
# a whitelist, and a new person must never be locked out of scanning.
KNOWN_OPERATORS = ["Patrick", "Dave", "Ed", "Zack", "Ara", "Daniel"]

_CACHE = {"operator": None, "host": None}


def machine_name():
    """The PC this is running on. Cheap second identifier: two people sharing a
    login still show up as different machines, and one person on two PCs is
    still visibly one person."""
    if _CACHE["host"] is None:
        try:
            _CACHE["host"] = (socket.gethostname() or "unknown-pc").strip()
        except Exception:
            _CACHE["host"] = "unknown-pc"
    return _CACHE["host"]


def _tidy(name):
    """Normalise so 'dave', ' DAVE ' and 'Dave' are one operator, not three.
    Collapses whitespace, strips characters that would break a CSV/sheet cell,
    caps the length, and title-cases a plain single-word name."""
    s = re.sub(r"\s+", " ", str(name or "")).strip().strip(",;\"'")
    s = re.sub(r"[\r\n\t]", " ", s)[:40].strip()
    if not s:
        return ""
    # Title-case lowercase input and leave mixed-case alone, so "McGrew" keeps
    # its shape. SHORT all-caps is left alone too -- "JD" is a name here
    # (JD Dunn) and "Jd" is just wrong.
    if s.islower() or (s.isupper() and len(s) > 3):
        s = s.title()
    return s


def _load_saved():
    try:
        with open(_STORE, "r") as f:
            return _tidy((json.load(f) or {}).get("operator"))
    except Exception:
        return ""


def _save(name):
    """Remember the answer so we only ever ask once. Best-effort -- a read-only
    folder must not stop the sweep, it just means we ask again next time."""
    try:
        with open(_STORE, "w") as f:
            json.dump({"operator": name, "machine": machine_name()}, f, indent=2)
        return True
    except Exception:
        return False


def _can_prompt(auto=False):
    """True only when there is a real human at a real keyboard.

    Every one of these has to be checked. --auto is the scheduled/launcher run,
    the uploader is a headless subprocess, and a piped stdin means the console
    isn't interactive. Prompting in any of them blocks forever, and a hunter
    that never starts is far worse than a row tagged with a hostname."""
    if auto:
        return False
    if "--uploader" in sys.argv or "--auto" in sys.argv:
        return False
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def _ask():
    """The numbered menu. Returns "" if the person just hits Enter or the
    console can't be read -- the caller falls back to the hostname."""
    print("")
    print("=" * 68)
    print("  WHO IS RUNNING THIS SCAN?")
    print("=" * 68)
    print("  Every address you capture gets stamped with your name, so we can")
    print("  see whose sweeps are working. You only have to answer this once.")
    print("")
    for i, nm in enumerate(KNOWN_OPERATORS, 1):
        print("    %d) %s" % (i, nm))
    print("    or just type your name")
    print("")
    try:
        raw = input("  Name or number: ").strip()
    except Exception:
        return ""
    if not raw:
        return ""
    if raw.isdigit():
        i = int(raw)
        if 1 <= i <= len(KNOWN_OPERATORS):
            return KNOWN_OPERATORS[i - 1]
        # A number outside the menu is a typo, not a name. Asking again beats
        # silently saving "7" as somebody's identity for the next six months.
        print("  (%s isn't on the list -- type your name instead)" % raw)
        try:
            raw = input("  Name: ").strip()
        except Exception:
            return ""
    return _tidy(raw)


def resolve(cli_value=None, auto=False, force_ask=False):
    """Work out who is scanning. Returns a non-empty string, always.

    cli_value  -- whatever --operator was given (or None)
    auto       -- True for unattended runs; never prompts
    force_ask  -- True for --whoami; re-asks even if we already know
    """
    if _CACHE["operator"] and not force_ask:
        return _CACHE["operator"]

    name = ""
    if not force_ask:
        name = _tidy(cli_value) or _tidy(os.environ.get("OPTIMUS_OPERATOR")) \
            or _load_saved()

    if not name and _can_prompt(auto=auto):
        name = _ask()
        if name:
            if _save(name):
                print("  Saved. You won't be asked again on this PC.")
                print("  (To change it later: run with  --whoami)")
            else:
                print("  (couldn't save that -- you'll be asked again next time)")

    if not name:
        # Never anonymous. A hostname is a weak identity but it is an identity,
        # and it is always better than a blank column nobody can trace.
        name = "PC:" + machine_name()

    _CACHE["operator"] = name
    return name


def current():
    """Whoever resolve() settled on. Safe to call from anywhere afterwards."""
    return _CACHE["operator"] or resolve(auto=True)


def banner():
    """One line for the startup console, so the person can SEE who the sheet is
    about to credit -- and catch it immediately if it says the wrong name."""
    return "  SCANNING AS: %s   (machine %s)" % (current(), machine_name())
