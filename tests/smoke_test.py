"""End-to-end smoke test without MCP: launch AC, move the free camera, change the time, take screenshots, quit.

Requires Assetto Corsa + CSP with the claude_bridge app installed. It changes race.ini (and video.ini when --window is
given) temporarily; both are restored on quit.

  .venv/Scripts/python.exe tests/smoke_test.py --track ks_vallelunga --car abarth500 --pos 0 50 0 --target 50 0 50
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ac_mcp import api, bridge, launcher  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True)
    ap.add_argument("--car", default="abarth500")
    ap.add_argument("--layout", default="")
    ap.add_argument("--pos", nargs=3, type=float, default=[0.0, 60.0, 0.0])
    ap.add_argument("--target", nargs=3, type=float, default=[50.0, 0.0, 50.0])
    ap.add_argument("--window", nargs=2, type=int, default=[1920, 1080])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "out" / "smoke"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ok = True
    try:
        r = launcher.launch(a.track, a.car, a.layout, hour=12, window=tuple(a.window))
        print("launch", r["ok"], r["loadSeconds"], "s")
        print("state", json.dumps(bridge.send("get_state"))[:300])
        print("camera", api.camera_look_at(a.pos, a.target, fov=60).get("ok"))
        for hh in (12, 21):
            t = api.set_time(hh, 0, 15, 12, 2025)
            print("time", hh, t.get("ok"), t.get("time", {}).get("hours"))
            time.sleep(4)
            s = api.screenshot(out / f"smoke_{hh:02d}00.png")
            print("screenshot", s.get("ok"), s.get("method"), s.get("path"))
            ok &= bool(s.get("ok")) and bool(t.get("ok"))
    except Exception as e:  # always quit + restore
        print("FAILED:", type(e).__name__, e)
        ok = False
    finally:
        print("quit", launcher.quit())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
