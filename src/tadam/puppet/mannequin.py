"""The wooden MANNEQUIN of a pattern rig as a painted sheet: every piece of rigs/<rig>/mannequin/ put back in its
place on the pattern. Drawn by code (make_rig.py), so it costs nothing: it stands in for the image model where a
real painting is not needed (tests, a first look at a scene, the engine's own check).

    sheet("humanoid-a").save(pdir / "sheet.png"); cut_skin.cut(pdir)   ->  a working puppet
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tadam.paths import RIGS
from tadam import imgio
from tadam.puppet import puppet_name, rigkit
from tadam.jsonfile import write_json


def sheet(rig_name: str = "humanoid-a") -> Image.Image:
    rig = rigkit.load_rig(rig_name)
    w, h = rig["sheet"]
    pad = rig["pad"]
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for n in sorted(rig["parts"], key=lambda n: rig["parts"][n].get("z", 0)):
        p = rig["parts"][n]
        im = Image.open(RIGS / rig_name / "mannequin" / f"{n}.png").convert("RGBA")
        x, y = int(p["box"][0]) - pad, int(p["box"][1]) - pad
        out.alpha_composite(im, (max(x, 0), max(y, 0)), (max(-x, 0), max(-y, 0)))
    return out


def make(pdir: Path, rig_name: str = "humanoid-a", character: str = "a wooden mannequin", log=print,
         talking: bool = True) -> dict:
    """A puppet from the mannequin: sheet.png, meta.json, then the usual cut and check. Returns the report.
    `talking`: its head also gets an open mouth (the "open" drawing), so it moves its mouth when it says a line."""
    from tadam.puppet import cut_skin
    pdir = Path(pdir)
    pdir.mkdir(parents=True, exist_ok=True)
    imgio.save_png(sheet(rig_name), pdir / "sheet.png")
    (pdir / "mouth_open.png").unlink(missing_ok=True)
    meta = {"name": puppet_name(pdir), "character": character, "style": "mannequin (drawn by code)", "rig": rig_name,
            "model": "none", "calls": []}
    write_json(pdir / "meta.json", meta, indent=2)
    if not talking:
        return cut_skin.cut(pdir, rig_name, log=log)
    report = cut_skin.cut(pdir, rig_name, log=lambda *_: None)
    if not report.get("passed"):
        return report
    # a mouth that opens (drawn by code too): the engine swaps the two heads while the mannequin says a line
    mouth_open(pdir)
    return cut_skin.cut(pdir, rig_name, log=log)


def mouth_open(pdir: Path) -> Path:
    """<puppet>/mouth_open.png as tadam.puppet.gen_mouth would paint it: the same head on the same picture, with a
    dark open mouth in the lower part of the face (cut_skin keeps only the mouth: the head's "open" drawing)."""
    from PIL import ImageDraw

    from tadam.puppet import gen_mouth
    im, _, x, y, w, h = gen_mouth.layout(Path(pdir))
    out = Image.new("RGBA", (gen_mouth.SIZE, gen_mouth.SIZE), (0, 0, 0, 0))
    big = im.resize((w, h), Image.LANCZOS)
    out.alpha_composite(big, (x, y))
    # the round head is the upper part of the piece (the neck below it): the mouth sits low on the round
    cx, cy = x + w * 0.5, y + h * 0.56
    rx, ry = w * 0.13, h * 0.055
    ImageDraw.Draw(out).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(70, 34, 24, 255))
    f = Path(pdir) / "mouth_open.png"
    out.save(f)
    return f
