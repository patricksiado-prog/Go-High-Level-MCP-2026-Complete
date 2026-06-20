---
name: project-tracker
description: Manage long-running, multi-session projects by keeping a living PROJECT_STATUS.md (Now / Next / Done / Decisions / Blockers / Handoff) and a dated journal. Use this when a task spans many sessions, when the user asks to plan/track/resume a long-term project, check status, log a decision, record a blocker, or hand off work — so progress and context survive across sessions instead of being re-derived each time.
---

# Project Tracker — keep long-term work on the rails

Long projects fail at the seams between sessions: context is lost, decisions
get re-litigated, half-finished threads are forgotten. This skill keeps one
durable source of truth in the repo so any session (or person) can resume in
under a minute.

## The single file: PROJECT_STATUS.md
Maintain a `PROJECT_STATUS.md` at the repo root (or the project subfolder).
It has six sections — keep them short and current, not a diary:

- **NOW** — the 1–3 things actively in progress this session.
- **NEXT** — the ordered backlog of what to do after NOW. Top item is what a
  fresh session should pick up.
- **DONE** — shipped/verified milestones (newest first). Move items here only
  when committed/pushed and verified.
- **DECISIONS** — durable choices + one line of *why*, dated. This is what
  stops the same debate happening twice. Never silently reverse one; if a
  decision changes, add a new dated line that supersedes it.
- **BLOCKERS** — anything waiting on the user, an external service, or an
  unanswered question. Each with what would unblock it.
- **HANDOFF** — the paste-able "start here" block for the next session: branch,
  what's verified vs. unverified, and the exact next command/step.

## The journal: scaffold_status.py
`scaffold_status.py` (next to this skill) creates the file if missing and
appends timestamped journal entries under a "## Journal" section so you have a
running history without bloating the six live sections.

```
python scaffold_status.py --init                      # create PROJECT_STATUS.md
python scaffold_status.py --log "shipped --fresh mode" # append a dated entry
python scaffold_status.py --show                      # print current status
```

## How to use it every session
1. **Start**: read PROJECT_STATUS.md (or run `--show`). Pick up the top NEXT item.
2. **While working**: when you make a real choice, add a DECISIONS line. When
   you hit something only the user/an external thing can resolve, add a BLOCKER.
3. **On finishing a unit of work**: move it NOW → DONE (only after commit +
   push + verify), pull the next item into NOW, and `--log` a one-line entry.
4. **End**: refresh HANDOFF so it names the branch, what's verified vs. needs a
   live run, and the literal next step. Commit PROJECT_STATUS.md with the work.

## Rules that keep it trustworthy
- **DONE means verified**, not "wrote the code." If tests pass but a live run
  is still needed, it stays in NOW with that noted — don't over-claim.
- **One file, kept current** beats scattered notes. Edit in place; don't let
  stale NOW/NEXT items pile up.
- **Decisions are append-only** — supersede, never quietly delete, so the
  reasoning trail survives.
- Keep secrets and PII out of it (it's committed to the repo).
- It complements task tools: use this for the durable project narrative; use a
  task/todo list for the fine-grained steps within a single session.
