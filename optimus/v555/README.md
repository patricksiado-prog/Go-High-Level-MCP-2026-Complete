# THE WORKING BUILD — frozen 2026-07-02 (Patrick: "the build I'm using works")

`precise_fiber_hunter_WORKING_2026-07-02.py` is a byte-for-byte copy of git
commit `42a3c08` — the build that ended the "it keeps stopping" night:

- REAL-MOUSE MOTION: raw Windows input (ctypes SetCursorPos/mouse_event),
  nothing to install. The pan never waits on the browser.
- Presses "Search this area" when the button exists (page call, 1s-capped click).
- Console self-minimizes at the first pan; Windows QuickEdit disarmed.
- Writes off the motion (separate uploader process); no auto-restart of any kind.

Proven live 2026-07-02 ~23:49+: 143+ cells / 555+ leads through dense Houston
ground where every waiting-motion build died at cells 3-16, and kept going.

The main `optimus/precise_fiber_hunter.py` was reset to equal this build the
same night (the launchers serve it). If the main file ever drifts and breaks,
this copy is the restore point. A later "page-free loop" experiment (no search
presses at all) exists in git history at `b16ed1c` — unproven, shelved.
