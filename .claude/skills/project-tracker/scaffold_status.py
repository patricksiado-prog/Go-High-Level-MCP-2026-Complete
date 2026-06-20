#!/usr/bin/env python3
"""
PROJECT_STATUS scaffolder + journal -- the actionable half of the
project-tracker skill. No dependencies.

  python scaffold_status.py --init                 create PROJECT_STATUS.md if missing
  python scaffold_status.py --log "did the thing"  append a dated journal entry
  python scaffold_status.py --show                 print the file
  python scaffold_status.py --path PATH ...         operate on a specific file

The six live sections (NOW/NEXT/DONE/DECISIONS/BLOCKERS/HANDOFF) are edited by
hand; this script only scaffolds the file and appends dated lines under
"## Journal" so history accrues without bloating the live sections.
"""

import os, sys, argparse, datetime

DEFAULT_PATH = "PROJECT_STATUS.md"
JOURNAL_HEADER = "## Journal"

TEMPLATE = """# Project Status

> Living source of truth for this project. Keep the six sections below short
> and current. Newest journal entries are at the bottom.

## NOW
- (what's actively in progress)

## NEXT
1. (the very next thing a fresh session should pick up)

## DONE
- (shipped + verified milestones, newest first)

## DECISIONS
- {date}: initialized project tracker.

## BLOCKERS
- (anything waiting on the user / an external service / an open question)

## HANDOFF
- Branch: (working branch)
- Verified: (what is done and confirmed)
- Needs live run: (what still has to be run for real)
- Next step: (the literal next command or action)

{journal_header}
- {date}: project tracker created.
"""


def today():
    return datetime.date.today().isoformat()


def init_file(path):
    if os.path.exists(path):
        return False
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        f.write(TEMPLATE.format(date=today(), journal_header=JOURNAL_HEADER))
    return True


def append_log(path, message):
    """Append a dated entry under the Journal header, creating the file
    (and the header) if needed. Returns the line written."""
    if not os.path.exists(path):
        init_file(path)
    with open(path, "r") as f:
        text = f.read()
    line = "- %s: %s" % (today(), message.strip())
    if JOURNAL_HEADER in text:
        text = text.rstrip() + "\n" + line + "\n"
    else:
        text = text.rstrip() + "\n\n" + JOURNAL_HEADER + "\n" + line + "\n"
    with open(path, "w") as f:
        f.write(text)
    return line


def show(path):
    if not os.path.exists(path):
        print("(no %s yet -- run with --init)" % path)
        return 1
    with open(path) as f:
        sys.stdout.write(f.read())
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--log", metavar="MESSAGE", default=None)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args(argv)

    did = False
    if args.init:
        created = init_file(args.path)
        print("Created %s" % args.path if created else "%s already exists" % args.path)
        did = True
    if args.log is not None:
        print("Logged: %s" % append_log(args.path, args.log))
        did = True
    if args.show or not did:
        return show(args.path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
