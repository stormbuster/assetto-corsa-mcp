"""Example tour (project-specific): Berliner Mitte Ring building test block (MODEL_10 bmr_mitte_bldtest.kn5).

AC world coordinates (AC x = Blender x, AC y = Blender z, AC z = -Blender y). Ground at the test block ~22.47,
eye height 1.7 m -> y 24.17.

Usage (AC already running with the session loaded, e.g. after ac_launch):
  .venv/Scripts/python.exe examples/bmr_bldtest_tour.py OUT_DIR [--times 12:00,19:00,21:00] [--date 15.12.2025] [--only name1,name2]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ac_mcp import api  # noqa: E402

EYE = 24.17
# name: (camera position, look-at target, vertical fov)
SHOTS: dict[str, tuple[list[float], list[float], float]] = {
    # row 1, inari / Torstr 114 copies, facades face north (-Z)
    "inari_A": ([195.0, EYE, 180.0], [195.0, 33.0, 205.0], 62),
    "inari_B": ([225.0, EYE, 180.0], [225.0, 33.0, 205.0], 62),
    "inari_C": ([254.5, EYE, 180.0], [254.5, 33.0, 205.0], 62),
    "inari_F": ([284.0, EYE, 180.0], [284.0, 33.0, 205.0], 62),
    # GF close-ups (shop windows) of row 1
    "inari_gf_A": ([195.0, EYE, 196.0], [195.0, 25.5, 205.0], 55),
    "inari_gf_B": ([225.0, EYE, 196.0], [225.0, 25.5, 205.0], 55),
    "inari_gf_C": ([254.5, EYE, 196.0], [254.5, 25.5, 205.0], 55),
    "inari_gf_F": ([284.0, EYE, 196.0], [284.0, 25.5, 205.0], 55),
    # row 2, rear courtyard blocks: only a ~4 m gap behind row 1, so wide angle from the gap + one diagonal from the east
    "rear_A": ([191.5, EYE, 223.0], [191.5, 36.0, 232.0], 85),
    "rear_B": ([214.5, EYE, 223.0], [214.5, 36.0, 232.0], 85),
    "rear_C": ([237.5, EYE, 223.0], [237.5, 36.0, 232.0], 85),
    "rear_diag_E": ([262.0, EYE, 224.0], [215.0, 30.0, 236.0], 60),
    # row 3, ivy house (corner house, ivy on the west / south-west)
    "ivy_A_west": ([160.0, EYE, 272.0], [195.0, 33.0, 270.0], 62),
    "ivy_A_sw": ([173.0, EYE, 292.0], [193.0, 30.0, 278.0], 62),
    "ivy_B_sw": ([213.0, EYE, 292.0], [233.0, 30.0, 278.0], 62),
    "ivy_C_sw": ([253.0, EYE, 292.0], [273.0, 30.0, 278.0], 62),
    # row 4, Budni pavilion (grass mound), shop front faces west-south-west
    "budni_A": ([175.0, EYE, 318.0], [198.0, 25.5, 312.0], 60),
    "budni_B": ([224.0, EYE, 318.0], [247.0, 25.5, 312.0], 60),
    "budni_C": ([273.0, EYE, 318.0], [296.0, 25.5, 312.0], 60),
    # aerial over the whole block, ~60 m above ground from the north-west
    "aerial_NW": ([150.0, 82.5, 160.0], [253.0, 22.0, 272.0], 60),
    # real Torstr 114 position (placeholder) from the north side of Torstrasse
    "torstr114_front": ([176.0, EYE, 80.0], [176.0, 33.0, 113.0], 62),
    "torstr114_oblique": ([140.0, EYE, 92.0], [180.0, 30.0, 115.0], 62),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--times", default="12:00,19:00,21:00")
    ap.add_argument("--date", default="15.12.2025")
    ap.add_argument("--only", default="")
    ap.add_argument("--settle", type=float, default=2.5)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    d, m, y = (int(v) for v in a.date.split("."))
    names = [n for n in SHOTS if not a.only or n in a.only.split(",")]
    log = []
    for t in a.times.split(","):
        hh, mm = (int(v) for v in t.split(":"))
        r = api.set_time(hh, mm, d, m, y, multiplier=0.0)
        print("time", t, r.get("ok"), r.get("time"))
        time.sleep(6)  # let lighting conditions / NIGHT_SMOOTH settle
        for n in names:
            pos, tgt, fov = SHOTS[n]
            api.camera_look_at(pos, tgt, fov)
            time.sleep(a.settle)
            fn = out / f"{n}_{hh:02d}{mm:02d}.png"
            r2 = api.screenshot(fn)
            print(n, t, r2.get("method"), r2.get("ok"))
            log.append({"shot": n, "time": t, "date": a.date, "pos": pos, "target": tgt, "fov": fov, "file": str(fn),
                        "ok": r2.get("ok"), "method": r2.get("method")})
    (out / "shots.json").write_text(json.dumps(log, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
