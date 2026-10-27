"""MCP server (stdio) exposing Assetto Corsa control through the claude_bridge CSP Lua app.

Run:  <repo>/.venv/Scripts/python.exe -m ac_mcp.server
Coordinates are AC world coordinates (Y up). From Blender: AC x = Bx, AC y = Bz, AC z = -By.
"""
from __future__ import annotations

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import api, bridge, coords, launcher, paths

mcp = _Server("assetto-corsa")


def _safe(fn, *a, **k) -> dict:
    try:
        return fn(*a, **k)
    except Exception as e:  # report instead of crashing the tool call
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def ac_launch(track: str, car: str = "abarth500", layout: str = "", skin: str = "", hour: float = 13.0,
              window_width: int = 0, window_height: int = 0, start_session: bool = True, timeout: float = 240) -> dict:
    """Start an offline practice session (writes a temporary race.ini after backing it up, starts acs.exe, waits
    for the bridge heartbeat, presses Drive). window_width/height > 0 temporarily switches video.ini to a single
    windowed screen of that size (restored by ac_quit). `hour` is the start time (08..18); use ac_set_time for any time/date."""
    win = (window_width, window_height) if window_width > 0 and window_height > 0 else None
    return _safe(launcher.launch, track, car, layout, skin, hour, win, True, start_session, timeout)


@mcp.tool()
def ac_status() -> dict:
    """Is acs.exe running, is the bridge alive (session loaded), plus the last heartbeat (camera, time, car)."""
    return _safe(api.status)


@mcp.tool()
def ac_get_state() -> dict:
    """Live state from the bridge: camera mode/position/look/fov, car position/speed, time and day of year, fps."""
    return _safe(bridge.send, "get_state", timeout=10)


@mcp.tool()
def ac_camera_free(x: float, y: float, z: float, yaw: float = 0.0, pitch: float = 0.0, fov: float = 0.0) -> dict:
    """Hold the camera at AC world position (x, y, z). yaw deg: 0 = look along -Z, 90 = +X, 180 = +Z, 270 = -X.
    pitch deg: + up, - down. fov: vertical FOV in degrees (0 = keep)."""
    return _safe(api.camera_free, x, y, z, yaw, pitch, fov or None)


@mcp.tool()
def ac_camera_look_at(pos: list[float], target: list[float], fov: float = 0.0) -> dict:
    """Hold the camera at `pos` [x, y, z] looking at `target` [x, y, z] (AC world coordinates)."""
    return _safe(api.camera_look_at, pos, target, fov or None)


@mcp.tool()
def ac_camera_mode(mode: str) -> dict:
    """Release the held camera and switch AC camera: 'free' (F7), 'cockpit', 'chase', 'chase2', 'bonnet', 'car' (F6),
    'track' (replay cams), or 'release' (only let go of the held camera)."""
    return _safe(bridge.send, "set_camera_mode", mode=mode)


@mcp.tool()
def ac_set_time(hour: int, minute: int = 0, day: int = 0, month: int = 0, year: int = 0, freeze: bool = True) -> dict:
    """Set track-local time and (optionally) date via ac.setWeatherExactUTC0Timestamp (offline only).
    day/month/year 0 = keep the current date. freeze=True sets the time multiplier to 0."""
    return _safe(api.set_time, hour, minute, day or None, month or None, year or None, 0.0 if freeze else None)


@mcp.tool()
def ac_screenshot(path: str, hide_apps: bool = True) -> dict:
    """Save a screenshot (PNG/JPG by extension) to `path` via CSP ac.makeScreenshot; falls back to a PowerShell
    capture of the AC window. Returns the path and the method used."""
    return _safe(api.screenshot, path, hide_apps)


@mcp.tool()
def ac_teleport_car(x: float, y: float, z: float, yaw: float = -1) -> dict:
    """Move the player car (physics.setCarPosition; aligned on the track surface). yaw < 0 aligns to the AI spline.
    Reports whether the car actually moved."""
    d = coords.yaw_pitch_to_look(yaw, 0) if yaw >= 0 else None
    return _safe(bridge.send, "teleport_car", position=[x, y, z], **({"direction": d} if d else {}))


@mcp.tool()
def ac_material_get(filter: str, properties: list[str] | None = None) -> dict:
    """Read material properties at runtime (first mesh matching a CSP mesh filter, e.g. 'material:MyMat').
    Default properties: ksEmissive, ksAmbient, ksDiffuse, ksAlphaRef."""
    args = {"filter": filter}
    if properties:
        args["properties"] = properties
    return _safe(bridge.send, "material_get", timeout=10, **args)


@mcp.tool()
def ac_material_set(filter: str, property: str, value: list[float]) -> dict:
    """Override a material property at runtime only (lost on restart; nothing is written to disk).
    value: 1-4 numbers, e.g. [1, 0.8, 0.5] for ksEmissive."""
    return _safe(bridge.send, "material_set", timeout=10, filter=filter, property=property,
                 value=value if len(value) > 1 else value[0])


@mcp.tool()
def ac_track_config(pattern: str = ".", values: bool = True, limit: int = 200) -> dict:
    """Sections of the track's CSP config as CSP parsed it (INCLUDEs merged), filtered by a Lua pattern on the
    section name (e.g. '^MATERIAL_ADJUSTMENT'). Useful to check whether an included INI was really loaded."""
    return _safe(bridge.send, "track_config", timeout=10, pattern=pattern, values=values, limit=limit)


@mcp.tool()
def ac_quit(restore_configs: bool = True) -> dict:
    """Quit AC (bridge shutdown first, taskkill only if it hangs) and restore race.ini/video.ini backups."""
    return _safe(launcher.quit, 45.0, restore_configs)


@mcp.tool()
def ac_restore_configs() -> dict:
    """Restore any configs still backed up by ac_launch (e.g. after a crash). Only when AC is not running."""
    if launcher.is_running():
        return {"ok": False, "error": "AC is running"}
    return _safe(lambda: {"ok": True, "restored": launcher.restore_configs()})


@mcp.tool()
def ac_blender_to_ac(x: float, y: float, z: float) -> list[float]:
    """Convert Blender coordinates to AC world coordinates (AC x = Bx, AC y = Bz, AC z = -By)."""
    return coords.blender_to_ac(x, y, z)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
