"""High-level helpers shared by the MCP server, scripts and tests."""
from __future__ import annotations

import calendar
import shutil
import time
from pathlib import Path
from typing import Sequence

from . import bridge, capture, coords, launcher, paths


def status() -> dict:
    st = bridge.status()
    return {"acRunning": launcher.is_running(), "bridgeAlive": bool(st.get("alive")),
            "sessionLoaded": bool(st.get("alive")),  # the Lua app only runs once a session has loaded
            "inPitMenu": st.get("isInMainMenu"),
            "status": st, "pendingConfigRestore": list(launcher._manifest().keys())}


def camera_free(x: float, y: float, z: float, yaw: float = 0.0, pitch: float = 0.0, fov: float | None = None) -> dict:
    return bridge.send("camera_set", position=[x, y, z], look=coords.yaw_pitch_to_look(yaw, pitch),
                       **({"fov": fov} if fov else {}))


def camera_look_at(pos: Sequence[float], target: Sequence[float], fov: float | None = None) -> dict:
    return bridge.send("camera_set", position=list(pos), target=list(target), **({"fov": fov} if fov else {}))


def set_time(hour: int, minute: int = 0, day: int | None = None, month: int | None = None, year: int | None = None,
             multiplier: float | None = 0.0) -> dict:
    """Sets the track-local wall-clock time (and date). multiplier 0 freezes time (None = leave as is)."""
    if day is None or month is None:
        st = bridge.status()
        ts = st.get("time", {}).get("timestampLocal")
        if ts:
            g = time.gmtime(ts)
            day = day or g.tm_mday
            month = month or g.tm_mon
            year = year or g.tm_year
    year = year or time.gmtime().tm_year
    local_epoch = calendar.timegm((year, month or 1, day or 1, hour, minute, 0))
    args = {"local_epoch": local_epoch}
    if multiplier is not None:
        args["multiplier"] = multiplier
    return bridge.send("set_time", timeout=15, **args)


def screenshot(path: str | Path, hide_apps: bool = True, timeout: float = 60.0) -> dict:
    """Screenshot via CSP (ac.makeScreenshot) to `path`; if CSP refuses the path, shoot into the AC screens folder
    and move the file; if that fails too, use the PowerShell window capture."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tries = []
    try:
        r = bridge.send("screenshot", timeout=timeout, path=str(path).replace("\\", "/"), hide_apps=hide_apps)
        tries.append(r)
        if r.get("ok") and _wait_file(path):
            return {"ok": True, "path": str(path), "method": "csp", "tries": tries}
        tmp = (paths.AC_DOCS / "screens" / ("claude_bridge_tmp" + path.suffix)).resolve()
        tmp.unlink(missing_ok=True)
        r = bridge.send("screenshot", timeout=timeout, path=str(tmp).replace("\\", "/"), hide_apps=hide_apps)
        tries.append(r)
        if r.get("ok") and _wait_file(tmp):
            shutil.move(str(tmp), str(path))
            return {"ok": True, "path": str(path), "method": "csp+move", "tries": tries}
    except bridge.BridgeError as e:
        tries.append({"error": str(e)})
    r = capture.capture_window(path)
    r["tries"] = tries
    return r


def _wait_file(p: Path, timeout: float = 15.0) -> bool:
    t0 = time.time()
    last = -1
    while time.time() - t0 < timeout:
        if p.exists():
            s = p.stat().st_size
            if s > 0 and s == last:
                return True
            last = s
        time.sleep(0.4)
    return p.exists() and p.stat().st_size > 0
