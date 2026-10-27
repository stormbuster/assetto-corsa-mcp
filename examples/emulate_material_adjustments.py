"""Apply the [MATERIAL_ADJUSTMENT_*] sections of a CSP track INI at runtime through the bridge (memory only, nothing
on disk changes), for a given clock time. Useful when an INI is not (yet) included by ext_config.ini, or to preview
values without restarting AC.

Condition handling (approximation of CSP): a CONDITION is a product of names ("A * B"). Conditions defined in the same
file with INPUT=TIME and a LUT are evaluated (linear interpolation, seconds since midnight). Other names come from
--cond NAME=value (default: NIGHT_SMOOTH=1 and any *NIGHT* name = 1, i.e. full night). LAG is ignored.
Value: lerp(VALUE_n_OFF, VALUE_n, condition); "r,g,b,m" colours become (r/255*m, g/255*m, b/255*m).

  python examples/emulate_material_adjustments.py PATH_TO.ini --time 19:00 [--cond NIGHT_SMOOTH=1] [--dry]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ac_mcp import bridge  # noqa: E402


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    secs: dict[str, dict[str, str]] = {}
    cur = None
    for ln in text.splitlines():
        ln = ln.split(";", 1)[0].strip()
        if not ln:
            continue
        m = re.match(r"^\[(.+)\]$", ln)
        if m:
            cur = secs.setdefault(m.group(1), {})
        elif cur is not None and "=" in ln:
            k, v = ln.split("=", 1)
            cur[k.strip()] = v.strip()
    return secs


def lut_eval(lut: str, x: float) -> float:
    pts = [tuple(float(a) for a in p.split("=")) for p in lut.strip("()").split("|") if "=" in p]
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def parse_value(v: str) -> list[float]:
    nums = [float(a) for a in v.split(",")]
    if len(nums) == 4:  # r,g,b,mult
        return [nums[0] / 255 * nums[3], nums[1] / 255 * nums[3], nums[2] / 255 * nums[3]]
    if len(nums) == 3:
        return [n / 255 for n in nums] if max(nums) > 1.5 else nums
    return nums


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ini")
    ap.add_argument("--time", default="21:00")
    ap.add_argument("--cond", action="append", default=[])
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    secs = parse_ini(Path(a.ini).read_text(encoding="utf-8", errors="replace"))
    hh, mm = (int(v) for v in a.time.split(":"))
    t = hh * 3600 + mm * 60
    conds: dict[str, float] = {}
    for s in secs.values():
        if s.get("NAME") and s.get("INPUT") == "TIME" and "LUT" in s:
            conds[s["NAME"]] = lut_eval(s["LUT"], t)
    overrides = dict(c.split("=") for c in a.cond)

    def cond_value(expr: str) -> float:
        val = 1.0
        for name in (n.strip() for n in expr.split("*")):
            if name in overrides:
                val *= float(overrides[name])
            elif name in conds:
                val *= conds[name]
            elif "NIGHT" in name:
                val *= 1.0
            else:
                print(f"  unknown condition {name}, using 1")
        return val

    for name, s in secs.items():
        if not name.startswith("MATERIAL_ADJUSTMENT") or s.get("ACTIVE", "1") == "0":
            continue
        c = cond_value(s.get("CONDITION", "")) if s.get("CONDITION") else 1.0
        for mat in (m.strip() for m in s.get("MATERIALS", "").split(",") if m.strip()):
            for i in range(10):
                key = s.get(f"KEY_{i}")
                if not key:
                    continue
                on = parse_value(s[f"VALUE_{i}"])
                off = parse_value(s.get(f"VALUE_{i}_OFF", ",".join(["0"] * len(on))))
                if len(off) != len(on):
                    off = [0.0] * len(on)
                if len(on) == 1 and f"VALUE_{i}_OFF" not in s:
                    val = on if c > 0.5 else None  # scalar switches like ksAlphaRef: only while on
                    if val is None:
                        continue
                else:
                    val = [o + (n - o) * c for n, o in zip(on, off)]
                print(f"{a.time} {mat:32s} {key:12s} cond={c:.2f} -> {[round(v, 3) for v in val]}")
                if not a.dry:
                    r = bridge.send("material_set", filter=f"material:{mat}", property=key,
                                    value=val if len(val) > 1 else val[0], timeout=10)
                    if not r.get("ok") or not r.get("meshes"):
                        print("   !", r)


if __name__ == "__main__":
    main()
