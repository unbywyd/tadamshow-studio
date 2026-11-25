"""Shared helpers: load a rig, pose it (forward kinematics) and composite the parts with PIL.
Used to judge a generated skin without the engine. Works with the pattern rig and with a puppet's fitted rig."""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from tadam.paths import RIGS


def load_rig(name="humanoid-a"):
    """A pattern rig of the kit (tadam/data/rigs/<name>/rig.json, drawn by make_rig.py)."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"not a rig name: {name!r}")
    return json.loads((RIGS / name / "rig.json").read_text(encoding="utf-8"))


def _T(x, y):
    return np.array([[1, 0, x], [0, 1, y], [0, 0, 1]], float)


def _S(k):
    return np.array([[k, 0, 0], [0, k, 0], [0, 0, 1]], float)


def _R(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]], float)


def pivot(rig, n):
    p = rig["parts"][n]
    return p["joint"]["at"] if p.get("joint") else p["origin"]


def world_matrices(rig, angles=None, root=(0.0, 0.0), scale=1.0):
    """Part name -> 3x3 matrix mapping (sheet point - part pivot) to world. Angles in degrees, clamped to limits."""
    angles = angles or {}
    parts = rig["parts"]
    out = {}

    def solve(n):
        if n in out:
            return out[n]
        p = parts[n]
        a = angles.get(n, 0.0)
        if p.get("limits"):
            a = max(p["limits"][0], min(p["limits"][1], a))
        if p["parent"] is None:
            m = _T(*root) @ _S(scale) @ _R(a)
        else:
            pp = pivot(rig, p["parent"])
            j = p["joint"]["parent_at"]
            m = solve(p["parent"]) @ _T(j[0] - pp[0], j[1] - pp[1]) @ _R(a)
        out[n] = m
        return m

    for n in parts:
        solve(n)
    return out


def rest_metrics(rig):
    """Where the neck and the soles are in the rest pose, relative to the root origin (sheet units)."""
    mats = world_matrices(rig)
    parts = rig["parts"]
    soles = []
    for n, p in parts.items():
        if "sole" in p:
            pv = pivot(rig, n)
            soles.append(float((mats[n] @ np.array([p["sole"][0] - pv[0], p["sole"][1] - pv[1], 1.0]))[1]))
    neck = float(mats["head"][1, 2]) if "head" in parts else 0.0
    return {"neck_y": neck, "sole_y": max(soles) if soles else 0.0}


def auto_variants(rig, mats):
    """Which second drawing each part shows in this pose. The one rule so far, the same as in the engine:
    a hand held higher than its elbow shows its palm."""
    out = {}
    for n, p in rig["parts"].items():
        if "palm" in p.get("variants", {}) and p.get("parent"):
            wrist, elbow = mats[n][:2, 2], mats[p["parent"]][:2, 2]
            d = float(np.hypot(*(wrist - elbow)))
            if d > 0 and (elbow[1] - wrist[1]) / d > 0.3:
                out[n] = "palm"
    return out


def render_pose(rig, images, angles=None, size=(700, 1150), floor_y=1090, body_px=640, bg=(246, 244, 240, 255), rivets=True):
    """Composite part images (name -> RGBA, each = box grown by rig['pad']) in the given pose.
    A variant image is under the key "<part>.<variant>" and is used when auto_variants() picks it.
    The puppet is scaled as a whole so that neck-to-sole is `body_px`, and stands on `floor_y` in the rest pose."""
    m0 = rest_metrics(rig)
    k = body_px / max(m0["sole_y"] - m0["neck_y"], 1.0)
    root = (size[0] / 2, floor_y - k * m0["sole_y"])
    mats = world_matrices(rig, {**rig.get("rest", {}), **(angles or {})}, root, k)   # a pose overrides the rest stance
    pad = rig["pad"]
    canvas = Image.new("RGBA", size, bg)
    shown = auto_variants(rig, mats)
    for n in rig["draw_order"]:
        p = rig["parts"][n]
        pv = pivot(rig, n)
        key = f"{n}.{shown[n]}" if n in shown and f"{n}.{shown[n]}" in images else n
        if key != n:
            at = p["variants"][shown[n]]["at"]
            a = mats[n] @ _T(-pad - at[0], -pad - at[1])                         # a variant is pinned by its own point
        else:
            a = mats[n] @ _T(p["box"][0] - pad - pv[0], p["box"][1] - pad - pv[1])   # image px -> world
        inv = np.linalg.inv(a)
        canvas.alpha_composite(images[key].transform(size, Image.AFFINE, tuple(inv[:2].flatten()), resample=Image.BICUBIC))
    d = ImageDraw.Draw(canvas)
    d.line([(40, floor_y), (size[0] - 40, floor_y)], fill=(200, 196, 188, 255), width=2)
    if rivets:
        for n, p in rig["parts"].items():
            if p.get("joint"):
                x, y = mats[n][0, 2], mats[n][1, 2]
                d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(60, 45, 30, 255), outline=(230, 200, 140, 255), width=2)
    return canvas


POSES = {
    "rest": {},
    "cheer": {"upper_arm_l": 150, "forearm_l": 25, "upper_arm_r": -150, "forearm_r": -25, "head": -8,
              "thigh_l": 12, "shin_l": -24, "thigh_r": -12, "shin_r": 24},
    "walk": {"upper_arm_l": -35, "forearm_l": -40, "upper_arm_r": 30, "forearm_r": -25, "chest": 6, "head": 4,
             "thigh_l": 38, "shin_l": -50, "foot_l": 10, "thigh_r": -30, "shin_r": -12},
    "point": {"upper_arm_r": -95, "forearm_r": -5, "hand_r": -10, "upper_arm_l": 20, "forearm_l": 95,
              "chest": -8, "head": -18, "thigh_l": 6, "thigh_r": -6},
}


def contact_sheet(rig, images, path, poses=("rest", "cheer", "walk", "point")):
    tiles = [render_pose(rig, images, POSES[p]) for p in poses]
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * len(tiles), h), (246, 244, 240))
    for i, t in enumerate(tiles):
        sheet.paste(t.convert("RGB"), (i * w, 0))
    sheet.save(path, quality=88)
    return path
