"""File-channel client for the claude_bridge Lua app."""
from __future__ import annotations

import json
import os
import time
from typing import Any

from . import paths


class BridgeError(RuntimeError):
    pass


def _read_json(p) -> dict | None:
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def status(max_age: float = 5.0) -> dict:
    """Heartbeat written by the Lua app about once per second."""
    st = _read_json(paths.STATUS_FILE)
    if not st:
        return {"alive": False, "reason": "no status file"}
    age = time.time() - os.path.getmtime(paths.STATUS_FILE)
    st["statusAgeSeconds"] = round(age, 2)
    st["alive"] = age <= max_age
    return st


def _next_id() -> int:
    last = 0
    for p in (paths.CMD_FILE, paths.RESULT_FILE):
        d = _read_json(p)
        if d and isinstance(d.get("id"), (int, float)):
            last = max(last, int(d["id"]))
    return max(last + 1, int(time.time() * 10) % 1_000_000_000)


def send(cmd: str, timeout: float = 30.0, **args: Any) -> dict:
    """Write a command and wait for its result. Raises BridgeError on timeout."""
    paths.BRIDGE_DIR.mkdir(parents=True, exist_ok=True)
    cid = _next_id()
    payload = {"id": cid, "cmd": cmd, "timeout": timeout, **args}
    tmp = paths.CMD_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, paths.CMD_FILE)
    deadline = time.time() + timeout + 5
    while time.time() < deadline:
        r = _read_json(paths.RESULT_FILE)
        if r and r.get("id") == cid:
            return r
        time.sleep(0.1)
    raise BridgeError(f"no result for '{cmd}' (id {cid}) within {timeout + 5:.0f}s; is AC running with the claude_bridge app?")


def wait_alive(timeout: float = 180.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = status()
        if st.get("alive"):
            return st
        time.sleep(1.0)
    raise BridgeError("bridge heartbeat not seen")
