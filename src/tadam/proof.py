"""THE PROOF BODIES: free heroes of different build to try an action on (`tadam action check --proof`, the
workshop's "on the proof bodies"). An action is the core's, not a hero's: it has to work on a tall hero and a short
one, a heavy one, one with a big head and one in a skirt to the floor, so it is tried on all of them.

Every body is the kit's wooden mannequin (drawn by code, tadam.puppet.mannequin: it costs nothing), cut as usual and
then STRETCHED: chosen pieces grow or shrink round their own joint (longer legs, a wider chest, a bigger head), the
joints of the pieces hanging on them move with them, and the rest stance and the body height are measured again
the way the cutter measures them. The skirts are the pattern's own skirt rigs.

They are made once into <kit>/out/proof/<name>/puppet (out/ is never committed) and made again when BUILD changes.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from tadam import imgio
from tadam.jsonfile import write_json
from tadam.paths import kit_root

BUILD = 1          # raise when a body changes: the bodies are made again

ARMS = ("upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r")
LEGS = ("thigh_l", "thigh_r", "shin_l", "shin_r")

## name -> (pattern rig, {piece: (across, along)}): the stretch of each piece round its joint
BODIES: dict[str, tuple[str, dict[str, tuple[float, float]]]] = {
    "plain": ("humanoid-a", {}),
    "tall": ("humanoid-a", {**{n: (1.0, 1.32) for n in LEGS}, **{n: (1.0, 1.15) for n in ARMS}, "chest": (1.0, 1.12)}),
    "short": ("humanoid-a", {**{n: (1.0, 0.68) for n in LEGS}, **{n: (1.0, 0.85) for n in ARMS}, "chest": (1.0, 0.9)}),
    "heavy": ("humanoid-a", {"pelvis": (1.5, 1.05), "chest": (1.45, 1.0), **{n: (1.35, 1.0) for n in ("thigh_l", "thigh_r")},
                             **{n: (1.2, 1.0) for n in ("shin_l", "shin_r")}, **{n: (1.25, 1.0) for n in ARMS}}),
    "bighead": ("humanoid-a", {"head": (1.6, 1.6)}),
    "skirt_short": ("humanoid-a-skirt-short", {}),
    "skirt_knee": ("humanoid-a-skirt-knee", {}),
    "skirt_calf": ("humanoid-a-skirt-calf", {}),
    "skirt_floor": ("humanoid-a-skirt-floor", {}),
}
TITLES = {"plain": "обычный", "tall": "высокий", "short": "низкий", "heavy": "грузный", "bighead": "большеголовый",
          "skirt_short": "юбка короткая", "skirt_knee": "юбка до колена", "skirt_calf": "юбка до икры",
          "skirt_floor": "юбка до пола"}


def root() -> Path:
    return kit_root() / "out" / "proof"


def names() -> list[str]:
    return list(BODIES)


def ensure(only: list[str] | None = None, log=print) -> Path:
    """Make the bodies that are missing or of an older BUILD; returns the folder they are in (<name>/puppet)."""
    out = root()
    for name in only or names():
        pdir = out / name / "puppet"
        stamp = out / name / "build.json"
        try:
            if json.loads(stamp.read_text(encoding="utf-8")).get("build") == BUILD and (pdir / "rig.json").is_file():
                continue
        except (OSError, ValueError):
            pass
        log(f"making the proof body {name} ...")
        make(name, pdir)
        write_json(stamp, {"build": BUILD, "body": name}, indent=1)
    return out


def make(name: str, pdir: Path) -> dict:
    from tadam.puppet import mannequin
    rig_name, scales = BODIES[name]
    if pdir.exists():
        shutil.rmtree(pdir)
    report = mannequin.make(pdir, rig_name, character=f"a wooden mannequin, {name}", log=lambda *_: None, talking=False)
    if not report.get("passed"):
        raise RuntimeError(f"the proof body {name} did not cut: {report}")
    if scales:
        stretch(pdir, scales)
    return report


def _scale_point(pt, piv, s):
    return [round(piv[0] + (float(pt[0]) - piv[0]) * s[0], 1), round(piv[1] + (float(pt[1]) - piv[1]) * s[1], 1)]


def stretch(pdir: Path, scales: dict[str, tuple[float, float]]) -> dict:
    """Grow or shrink pieces of a cut puppet round their own joint (pure data and pictures: rig.json and parts/)."""
    from tadam.puppet import audit, rigkit
    pdir = Path(pdir)
    rig = json.loads((pdir / "rig.json").read_text(encoding="utf-8"))
    parts, pad = rig["parts"], float(rig.get("pad", 0))
    for n, s in scales.items():
        p = parts[n]
        piv = [float(v) for v in (p["joint"]["at"] if p.get("joint") else p["origin"])]
        # the picture: pixel (0, 0) is sheet point box.xy - pad, and it must stay over the same stretched point
        for f in [pdir / "parts" / f"{n}.png", *sorted((pdir / "parts").glob(f"{n}.*.png"))]:
            im = Image.open(f).convert("RGBA")
            w, h = max(1, round(im.width * s[0])), max(1, round(im.height * s[1]))
            imgio.save_png(im.resize((w, h), Image.LANCZOS), f)
            if f.name == f"{n}.png":
                corner = _scale_point([p["box"][0] - pad, p["box"][1] - pad], piv, s)
                p["box"] = [round(corner[0] + pad), round(corner[1] + pad), w - 2 * round(pad), h - 2 * round(pad)]
        for key in ("grip", "tip", "sole"):
            if key in p:
                p[key] = _scale_point(p[key], piv, s)
        if "mouth" in p:
            p["mouth"]["center"] = _scale_point(p["mouth"]["center"], piv, s)
            p["mouth"]["size"] = [round(p["mouth"]["size"][0] * s[0]), round(p["mouth"]["size"][1] * s[1])]
        if "board" in p:           # (in the picture's own pixels)
            p["board"] = {"center": [round(p["board"]["center"][0] * s[0]), round(p["board"]["center"][1] * s[1])],
                          "size": [round(p["board"]["size"][0] * s[0]), round(p["board"]["size"][1] * s[1])]}
        for v in (p.get("variants") or {}).values():
            v["size"] = [round(v["size"][0] * s[0]), round(v["size"][1] * s[1])]
            v["at"] = [round(v["at"][0] * s[0], 1), round(v["at"][1] * s[1], 1)]
        for c in parts.values():                        # the pieces hanging on it move with it
            if c.get("parent") == n:
                c["joint"]["parent_at"] = _scale_point(c["joint"]["parent_at"], piv, s)
    # measured again as the cutter measures them (tadam.puppet.cut_skin): the body height, the rest stance
    metrics = rigkit.rest_metrics(rig)
    rig["body_height"] = round(metrics["sole_y"] - metrics["neck_y"], 1)
    if rig.get("view", "front") != "side":
        from tadam.puppet import cut_skin
        solids = {}
        ip = round(pad)
        for n in parts:
            a = np.asarray(Image.open(pdir / "parts" / f"{n}.png").convert("RGBA"))[..., 3]
            solids[n] = audit.filled(a[ip:a.shape[0] - ip, ip:a.shape[1] - ip] > 128).astype(bool)
        rig.pop("rest", None)
        over = {a: max(audit.arm_over_body(rig, solids, sd, a) for sd in "lr")
                for a in range(-cut_skin.ARM_SPREAD_IN, cut_skin.ARM_SPREAD_MAX + 1, 2)}
        spread = next((a for a in over if over[a] <= cut_skin.ARM_CLEAR), min(over, key=over.get))
        if spread:
            rig["rest"] = {"upper_arm_l": spread, "upper_arm_r": -spread}
    rig["stretched"] = {n: list(s) for n, s in scales.items()}
    write_json(pdir / "rig.json", rig, indent=2)
    return rig
