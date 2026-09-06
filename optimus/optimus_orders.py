#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OPTIMUS ORDERS -- a second input to the controls the hunter already has.

Patrick can press Ctrl+UP to resume a paused sweep. This lets that same thing
happen from the shared Google Drive folder, so a machine in another room can be
un-paused without walking to it.

WHAT IT IS NOT, deliberately:

  * It does NOT run commands. There is no subprocess in this file and there
    never should be. Every order maps to a control the hunter already exposes
    on the keyboard. The worst a malformed order can do is pause a sweep.
  * It is NOT a new program. Nothing launches it. The hunter calls poll() from
    inside loops it is already sitting in.
  * It does NOT reach a PC that has no shared folder. No folder, no orders,
    nothing happens -- which is exactly the scoping Patrick asked for: only the
    machines he syncs the folder to are ever under remote control.

THE VOCABULARY. Anything else is ignored and reported as unknown.

    resume   -- same as Ctrl+UP     (un-pause, sweep from the current view)
    pause    -- same as Ctrl+DOWN   (let go of the map, capture stays on)
    stop     -- same as Ctrl+Shift+S (finish the cell, close cleanly)
    claim    -- args {"area": "Angleton, TX"}   take territory
    release  -- args {"area": "..."}            give it back
    note     -- args {"text": "..."}  print a line on the console for whoever
                                      is sitting at that PC
"""

import os
import json
import time
import socket

MACHINE = socket.gethostname()
HOME = os.path.expanduser("~")
FOLDER_NAME = "OPTIMUS COMMAND CENTER"
ORDERS_FILE = "ORDERS.json"

KNOWN = ("resume", "pause", "stop", "claim", "release", "note")

_FOLDER = [None, 0.0]      # cached path, last look
_DONE = set()              # order ids carried out in THIS process
_LAST_POLL = [0.0]
_DONE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "_orders_done.json")


def _load_done():
    try:
        with open(_DONE_FILE, "r") as f:
            for i in json.load(f):
                _DONE.add(str(i))
    except Exception:
        pass


def _save_done():
    try:
        with open(_DONE_FILE, "w") as f:
            json.dump(sorted(_DONE)[-500:], f)
    except Exception:
        pass


def find_folder():
    """Google Drive for Desktop mounts as a drive letter OR under the profile,
    and the letter is not the same on every machine -- so look, do not assume.
    Cached for 60s so a poll in a 0.25s loop costs nothing."""
    now = time.time()
    if _FOLDER[0] is not None and (now - _FOLDER[1]) < 60:
        return _FOLDER[0]
    cands = []
    env = os.environ.get("OPTIMUS_COMMAND_CENTER")
    if env:
        cands.append(env)
    for base in (HOME, os.path.join(HOME, "Documents")):
        for mid in ("My Drive", "Google Drive",
                    os.path.join("Google Drive", "My Drive")):
            cands.append(os.path.join(base, mid, FOLDER_NAME))
    for letter in "GHIJKLMNOPQRSTUVWXYZ":
        cands.append("%s:\\My Drive\\%s" % (letter, FOLDER_NAME))
    found = None
    for c in cands:
        try:
            if os.path.isdir(c):
                found = c
                break
        except Exception:
            pass
    _FOLDER[0] = found
    _FOLDER[1] = now
    return found


def _read_orders(folder):
    try:
        with open(os.path.join(folder, ORDERS_FILE), "r") as f:
            doc = json.load(f)
    except Exception:
        return []
    if isinstance(doc, dict):
        doc = doc.get("orders") or []
    if not isinstance(doc, list):
        return []
    out = []
    for o in doc:
        if not isinstance(o, dict):
            continue
        target = str(o.get("machine") or "any")
        if target != "any" and target.lower() != MACHINE.lower():
            continue
        oid = str(o.get("id") or "")
        if not oid or oid in _DONE:
            continue
        if str(o.get("action") or "") not in KNOWN:
            continue
        out.append(o)
    return out


def _write_result(folder, carried):
    try:
        p = os.path.join(folder, "RESULT-%s.json" % MACHINE)
        prev = {}
        try:
            with open(p, "r") as f:
                prev = json.load(f) or {}
        except Exception:
            pass
        log = (prev.get("carried_out") or [])[-40:]
        log.extend(carried)
        with open(p, "w") as f:
            json.dump({"machine": MACHINE,
                       "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "carried_out": log[-40:]}, f, indent=1)
    except Exception:
        pass


def poll(every=20.0, force=False):
    """Return the orders waiting for THIS machine. Never raises, never blocks.

    Safe to call from a 0.25s loop: it only touches the disk every `every`
    seconds. The CALLER applies each order using the hunter's own functions --
    this module deliberately has no power to do anything itself.
    """
    try:
        now = time.time()
        if not force and (now - _LAST_POLL[0]) < every:
            return []
        _LAST_POLL[0] = now
        folder = find_folder()
        if not folder:
            return []
        if not _DONE:
            _load_done()
        return _read_orders(folder)
    except Exception:
        return []


def mark_done(order, ok=True, detail=""):
    """Call after applying one. Records it so it never fires twice, and reports
    back into the shared folder so Claude can see what the machine did."""
    try:
        oid = str(order.get("id") or "")
        if not oid:
            return
        _DONE.add(oid)
        _save_done()
        folder = find_folder()
        if folder:
            _write_result(folder, [{
                "id": oid,
                "action": order.get("action"),
                "ok": bool(ok),
                "detail": detail,
                "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }])
    except Exception:
        pass
