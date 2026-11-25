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
from tadam.puppet import rigkit


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


def make(pdir: Path, rig_name: str = "humanoid-a", character: str = "a wooden mannequin", log=print) -> dict:
    """A puppet from the mannequin: sheet.png, meta.json, then the usual cut and check. Returns the report."""
    from tadam.puppet import cut_skin
    pdir = Path(pdir)
    pdir.mkdir(parents=True, exist_ok=True)
    sheet(rig_name).save(pdir / "sheet.png")
    meta = {"name": pdir.name, "character": character, "style": "mannequin (drawn by code)", "rig": rig_name,
            "model": "none", "calls": []}
    (pdir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return cut_skin.cut(pdir, rig_name, log=log)
