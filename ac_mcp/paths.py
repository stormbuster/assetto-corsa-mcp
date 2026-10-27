"""Locations of Assetto Corsa and of the bridge channel.

Resolution order for the game folder:
  1. environment variable AC_ROOT
  2. Steam: registry (HKCU\\Software\\Valve\\Steam SteamPath, HKLM ... InstallPath), then every library listed in
     steamapps/libraryfolders.vdf, looking for steamapps/common/assettocorsa/acs.exe (app id 244210)
The "Documents/Assetto Corsa" folder: environment variable AC_DOCUMENTS, else the Windows "My Documents" shell folder.

All path constants (AC_ROOT, RACE_INI, ...) are resolved lazily on attribute access, so importing never fails.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

AC_APP_ID = "244210"


def _documents_dir() -> Path:
    try:
        import ctypes
        from ctypes import wintypes

        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        # CSIDL_PERSONAL = 5 (My Documents); handles redirected Documents folders
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
            return Path(buf.value)
    except Exception:
        pass
    return Path.home() / "Documents"


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        import winreg

        for hive, key, name in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    roots.append(Path(winreg.QueryValueEx(k, name)[0]))
            except OSError:
                pass
    except ImportError:
        pass
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]) / "Steam")
    return roots


def _libraries(steam: Path) -> list[Path]:
    libs = [steam]
    try:
        text = (steam / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        libs += [Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    except OSError:
        pass
    return libs


@lru_cache(maxsize=1)
def find_ac_root() -> Path | None:
    if os.environ.get("AC_ROOT"):
        return Path(os.environ["AC_ROOT"])
    for steam in _steam_roots():
        for lib in _libraries(steam):
            cand = lib / "steamapps" / "common" / "assettocorsa"
            if (cand / "acs.exe").exists():
                return cand
    return None


def ac_root() -> Path:
    root = find_ac_root()
    if root is None:
        raise FileNotFoundError("Assetto Corsa not found; set the AC_ROOT environment variable")
    return root


def ac_docs() -> Path:
    return Path(os.environ.get("AC_DOCUMENTS", str(_documents_dir() / "Assetto Corsa")))


_LAZY = {
    "AC_ROOT": lambda: ac_root(),
    "AC_DOCS": lambda: ac_docs(),
    "CFG_DIR": lambda: ac_docs() / "cfg",
    "RACE_INI": lambda: ac_docs() / "cfg" / "race.ini",
    "VIDEO_INI": lambda: ac_docs() / "cfg" / "video.ini",
    "BRIDGE_DIR": lambda: ac_docs() / "claude_bridge",
    "CMD_FILE": lambda: ac_docs() / "claude_bridge" / "cmd.json",
    "RESULT_FILE": lambda: ac_docs() / "claude_bridge" / "result.json",
    "STATUS_FILE": lambda: ac_docs() / "claude_bridge" / "status.json",
    "BACKUP_DIR": lambda: ac_docs() / "claude_bridge" / "backups",
    "RESTORE_MANIFEST": lambda: ac_docs() / "claude_bridge" / "backups" / "pending_restore.json",
    "CSP_LOG": lambda: ac_docs() / "logs" / "custom_shaders_patch.log",
    "LUA_APP_DIR": lambda: ac_root() / "apps" / "lua" / "claude_bridge",
}


def __getattr__(name: str):
    if name in _LAZY:
        return _LAZY[name]()
    raise AttributeError(name)
