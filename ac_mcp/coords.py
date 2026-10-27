"""Coordinate helpers.

AC world: Y is up, X and Z horizontal (left-handed as seen by AC). A Blender scene exported with the usual
FBX/ksEditor settings maps as:   AC x = Blender x,   AC y = Blender z,   AC z = -Blender y.

Camera angles used by the tools:
  yaw   degrees, 0 = looking along -Z (Blender +Y, "north" on most real-world tracks built that way),
        90 = looking along +X (Blender +X), 180 = +Z, 270 = -X.
  pitch degrees, positive looks up, negative looks down.
"""
from __future__ import annotations

import math
from typing import Sequence


def blender_to_ac(x: float, y: float, z: float) -> list[float]:
    return [x, z, -y]


def ac_to_blender(x: float, y: float, z: float) -> list[float]:
    return [x, -z, y]


def yaw_pitch_to_look(yaw_deg: float, pitch_deg: float) -> list[float]:
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    return [math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch)]


def look_to_yaw_pitch(look: Sequence[float]) -> tuple[float, float]:
    x, y, z = look
    h = math.hypot(x, z)
    return (math.degrees(math.atan2(x, -z)) % 360.0, math.degrees(math.atan2(y, h)))
