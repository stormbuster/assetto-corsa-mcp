"""Launch / quit Assetto Corsa with a temporary race.ini (and optional temporary video.ini override).

Every config file that is changed is first copied to BACKUP_DIR and listed in pending_restore.json;
restore_configs() puts the originals back (called by quit(), and at the start of the next launch if a
previous run crashed).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from . import bridge, paths

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


# ---------------------------------------------------------------- process helpers
def is_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq acs.exe", "/NH"], capture_output=True, text=True,
                         creationflags=CREATE_NO_WINDOW).stdout
    return "acs.exe" in out.lower()


# ---------------------------------------------------------------- config backup / restore
def _manifest() -> dict:
    try:
        return json.loads(paths.RESTORE_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _backup(p: Path) -> None:
    paths.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    m = _manifest()
    if str(p) in m:  # already backed up in this run: keep the first (original) copy
        return
    dst = paths.BACKUP_DIR / (p.name + ".orig")
    existed = p.exists()
    if existed:
        shutil.copy2(p, dst)
    m[str(p)] = {"backup": str(dst), "existed": existed, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    paths.RESTORE_MANIFEST.write_text(json.dumps(m, indent=1), encoding="utf-8")


def restore_configs() -> list[str]:
    """Restore every file listed in the manifest. Returns the restored paths."""
    m = _manifest()
    done = []
    for target, info in m.items():
        t = Path(target)
        if info.get("existed"):
            shutil.copy2(info["backup"], t)
        elif t.exists():
            t.unlink()
        done.append(target)
    if paths.RESTORE_MANIFEST.exists():
        paths.RESTORE_MANIFEST.unlink()
    return done


def _set_ini_values(text: str, values: dict[str, dict[str, str]]) -> str:
    """Line-based INI edit that keeps everything else untouched."""
    lines = text.splitlines()
    section = None
    seen: set[tuple[str, str]] = set()
    out = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("[") and s.endswith("]"):
            # append missing keys of the section we are leaving
            if section in values:
                for k, v in values[section].items():
                    if (section, k) not in seen:
                        out.append(f"{k}={v}")
                        seen.add((section, k))
            section = s[1:-1]
        elif section in values and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in values[section]:
                out.append(f"{k}={values[section][k]}")
                seen.add((section, k))
                continue
        out.append(ln)
    if section in values:
        for k, v in values[section].items():
            if (section, k) not in seen:
                out.append(f"{k}={v}")
                seen.add((section, k))
    for sec, kv in values.items():
        missing = [(k, v) for k, v in kv.items() if (sec, k) not in seen]
        if missing:
            out.append(f"[{sec}]")
            out += [f"{k}={v}" for k, v in missing]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- race.ini
def _first_skin(car: str) -> str:
    skins = paths.AC_ROOT / "content" / "cars" / car / "skins"
    try:
        return sorted(d.name for d in skins.iterdir() if d.is_dir())[0]
    except Exception:
        return ""


def sun_angle_for_hour(hour: float) -> float:
    """Kunos SUN_ANGLE: -80 at 08:00 .. 0 at 13:00 .. +80 at 18:00 (16 deg per hour). Clamped to that range;
    use set_time() afterwards for other times."""
    return max(-80.0, min(80.0, (hour - 13.0) * 16.0))


def build_race_ini(track: str, car: str, layout: str = "", skin: str = "", hour: float = 13.0,
                   weather: str = "3_clear", driver: str = "Player", time_mult: float = 1.0) -> str:
    skin = skin or _first_skin(car)
    return f"""[HEADER]
VERSION=2

[RACE]
TRACK={track}
CONFIG_TRACK={layout}
MODEL={car}
MODEL_CONFIG=
SKIN={skin}
CARS=1
AI_LEVEL=90
FIXED_SETUP=0
PENALTIES=0
JUMP_START_PENALTY=0
DRIFT_MODE=0
RACE_LAPS=0

[CAR_0]
SETUP=
SKIN={skin}
MODEL=-
MODEL_CONFIG=
BALLAST=0
RESTRICTOR=0
DRIVER_NAME={driver}
NATIONALITY=
NATION_CODE=

[SESSION_0]
NAME=Practice
TYPE=1
DURATION_MINUTES=0
SPAWN_SET=PIT

[REMOTE]
ACTIVE=0

[REPLAY]
ACTIVE=0
FILENAME=

[RESTART]
ACTIVE=0

[BENCHMARK]
ACTIVE=0

[AUTOSPAWN]
ACTIVE=1

[GHOST_CAR]
RECORDING=0
PLAYING=0
LOAD=0
FILE=
ENABLED=0
SECONDS_ADVANTAGE=0

[LAP_INVALIDATOR]
ALLOWED_TYRES_OUT=-1

[OPTIONS]
USE_MPH=0

[LIGHTING]
SUN_ANGLE={sun_angle_for_hour(hour):.1f}
TIME_MULT={time_mult}
CLOUD_SPEED=0.2

[WEATHER]
NAME={weather}

[TEMPERATURE]
AMBIENT=18
ROAD=22

[WIND]
SPEED_KMH_MIN=0
SPEED_KMH_MAX=0
DIRECTION_DEG=0

[DYNAMIC_TRACK]
SESSION_START=100
RANDOMNESS=0
LAP_GAIN=1
SESSION_TRANSFER=100
"""


# ---------------------------------------------------------------- launch / quit
def launch(track: str, car: str, layout: str = "", skin: str = "", hour: float = 13.0,
           window: tuple[int, int] | None = None, single_screen: bool = True,
           start_session: bool = True, timeout: float = 240.0) -> dict:
    if is_running():
        raise RuntimeError("acs.exe is already running; quit it first (ac_quit)")
    leftover = restore_configs()  # crashed earlier run
    if not (paths.AC_ROOT / "content" / "tracks" / track).is_dir():
        raise FileNotFoundError(f"track not found: {track}")
    if not (paths.AC_ROOT / "content" / "cars" / car).is_dir():
        raise FileNotFoundError(f"car not found: {car}")
    if not (paths.LUA_APP_DIR / "manifest.ini").exists():
        raise FileNotFoundError(f"bridge Lua app not installed at {paths.LUA_APP_DIR} (run scripts/install_lua_app.ps1)")

    _backup(paths.RACE_INI)
    paths.RACE_INI.write_text(build_race_ini(track, car, layout, skin, hour), encoding="utf-8")
    changed = [str(paths.RACE_INI)]
    if window:
        _backup(paths.VIDEO_INI)
        vals = {"VIDEO": {"FULLSCREEN": "0", "WIDTH": str(window[0]), "HEIGHT": str(window[1])}}
        if single_screen:
            vals["CAMERA"] = {"MODE": "DEFAULT"}
        paths.VIDEO_INI.write_text(_set_ini_values(paths.VIDEO_INI.read_text(encoding="utf-8", errors="replace"), vals),
                                   encoding="utf-8")
        changed.append(str(paths.VIDEO_INI))

    t0 = time.time()
    subprocess.Popen([str(paths.AC_ROOT / "acs.exe")], cwd=str(paths.AC_ROOT), creationflags=DETACHED_PROCESS,
                     close_fds=True)
    # wait for a fresh heartbeat (written after the session has loaded and Lua apps run)
    st = None
    while time.time() - t0 < timeout:
        if not is_running() and time.time() - t0 > 20:
            raise RuntimeError("acs.exe exited during loading (see Documents/Assetto Corsa/logs/log.txt)")
        s = bridge.status(max_age=3)
        if s.get("alive") and s.get("wallClock", 0) >= t0:
            st = s
            break
        time.sleep(1)
    if st is None:
        raise TimeoutError(f"bridge heartbeat not seen within {timeout:.0f}s (AC running: {is_running()})")
    started = None
    if start_session:
        time.sleep(2)
        started = bridge.send("start_session", timeout=10)
    return {"ok": True, "loadSeconds": round(time.time() - t0, 1), "changedConfigs": changed,
            "restoredLeftovers": leftover, "startSession": started, "status": st}


def quit(timeout: float = 45.0, restore: bool = True) -> dict:
    method = "not running"
    if is_running():
        method = "bridge"
        try:
            bridge.send("quit", timeout=5)
        except Exception:
            method = "taskkill"
        t0 = time.time()
        while is_running() and time.time() - t0 < timeout:
            time.sleep(1)
        if is_running():
            method = "taskkill"
            subprocess.run(["taskkill", "/IM", "acs.exe"], capture_output=True, creationflags=CREATE_NO_WINDOW)
            time.sleep(8)
        if is_running():
            method = "taskkill /F"
            subprocess.run(["taskkill", "/F", "/IM", "acs.exe"], capture_output=True, creationflags=CREATE_NO_WINDOW)
            time.sleep(3)
    restored = restore_configs() if restore else []
    return {"ok": not is_running(), "method": method, "restored": restored}
