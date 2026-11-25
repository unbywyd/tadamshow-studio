"""`tadam set make <slug>`: a SET for the films, made of PARTS: an empty room (its window glass see-through), far
layers, and every piece of furniture as its own picture on a transparent background, all in the world's style. What
each part is and where it stands comes from the kit file (sets/<slug>/kit.json), so nothing has to be recognised
afterwards; when a film is made the set is only DATA (set.json), no AI at all.

kit.json:
  { "name", "floor": 0.87, "ground": {far, far_scale, tilt},
    "style": "<optional: the look, else the world's bible style>",
    "style_ref": "<optional: a picture in the set's folder to copy the look from>",
    "room": { "prompt": "the empty room ..." },
    "far": [ { "id", "image", "scale", "rect" } ],              far layers (pictures in the set's folder)
    "props": [ { "id", "prompt", "x", "base", "width", "on", "surface" } ] }
Writes sets/<slug>/room.png, <prop>.png (trimmed to the drawing), set.json:
  { background, floor, ground, backdrops: [...], pieces: [{ id, image, rect, base, bias }] }   (rect/base: world shares)
A prop "on" another (a lamp on the desk) stands on that one's top surface ("surface": share of its height from the
top where the top surface is) and is drawn just in front of it.
Cost: one picture for the room and one per prop.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
from pathlib import Path

import numpy as np
from PIL import Image

from tadam import openai_images as oi
from tadam.world import World, WorldError, is_safe_name, write_json

WORLD = (720, 1280)
STYLE_DEFAULT = "a flat matte hand-painted illustration, simple shapes, muted colours, even flat light, no shadows"


def style_line(kit: dict, world_style: str) -> str:
    st = kit.get("style") or world_style or STYLE_DEFAULT
    if kit.get("style_ref"):
        return f"Style exactly as the reference picture: {st}."
    return f"Style: {st}."


def _ref(kit: dict, out: Path) -> list[Path] | None:
    ref = kit.get("style_ref")
    if not ref:
        return None
    if not is_safe_name(ref) or not (out / ref).is_file():
        raise WorldError(f"style_ref '{ref}': a picture inside the set's folder")
    return [out / ref]


def _paint(prompt: str, size: str, transparent: bool, refs, model: str, quality: str) -> tuple[bytes, float]:
    fields = {"model": model, "size": size, "quality": quality, "output_format": "png", "n": 1, "prompt": prompt}
    if transparent:
        fields["background"] = "transparent"
    png, _, sec = oi.call("edits" if refs else "generations", fields, images=refs)
    return png, sec


def gen_room(kit: dict, out: Path, style: str, model=oi.DEFAULT_MODEL, quality="medium"):
    prompt = kit["room"]["prompt"] + " " + style
    png, sec = _paint(prompt, "1024x1536", False, _ref(kit, out), model, quality)
    raw = out / "room_raw.png"
    raw.write_bytes(png)
    im = np.array(Image.open(raw).convert("RGBA")).astype(np.int16)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    # the magenta glass -> transparent, with its pinkish fringe (grown a little so no rim of it is left)
    key = ((r > 140) & (b > 140) & (g < 120) & (r - g > 60) & (b - g > 60)).astype(np.uint8)
    import cv2
    key = cv2.dilate(key, np.ones((5, 5), np.uint8)) > 0
    im[..., 3] = np.where(key, 0, 255)
    Image.fromarray(im.astype(np.uint8), "RGBA").save(out / "room.png")
    return "room", sec, int(key.sum())


def gen_prop(kit: dict, p: dict, out: Path, style: str, model=oi.DEFAULT_MODEL, quality="medium"):
    what = "From this picture draw ONLY" if kit.get("style_ref") else "Draw ONLY"
    prompt = (f"{what} {p['prompt']}, alone, whole, nothing cut off, on a fully transparent "
              f"background, no floor, no wall, no shadow on the ground. {style}")
    png, sec = _paint(prompt, "1024x1024", True, _ref(kit, out), model, quality)
    f = out / f"{p['id']}.png"
    f.write_bytes(png)
    im = Image.open(f).convert("RGBA")
    box = im.getchannel("A").point(lambda v: 255 if v > 30 else 0).getbbox()
    if box:
        im = im.crop(box)                                       # trimmed: the bottom edge is where it stands
        im.save(f)
    return p["id"], sec, im.size


def layout(kit: dict, out: Path) -> dict:
    """Rects of the props in world shares from x (centre), base (where it stands), width, and the picture's shape."""
    pieces, placed = [], {}
    for p in kit.get("props", []):
        f = out / f"{p['id']}.png"
        if not f.exists():
            continue
        w_img, h_img = Image.open(f).size
        w = float(p["width"])
        h = w * WORLD[0] * h_img / w_img / WORLD[1]
        base = float(p.get("base", 0.7))
        if p.get("on") in placed:
            parent = placed[p["on"]]
            base = parent["rect"][1] + parent["rect"][3] * float(parent.get("surface", 0.06)) + 0.004
            stand = parent["base"]                 # the SAME depth as what it stands on ...
            bias = 0.2                             # ... drawn over it (stage.gd: less bias = in front)
        else:
            stand, bias = base, 0.25
        rect = [round(float(p["x"]) - w / 2, 4), round(base - h, 4), round(w, 4), round(h, 4)]
        entry = {"id": p["id"], "image": f"{p['id']}.png", "rect": rect, "base": round(stand, 4), "bias": bias}
        pieces.append(entry)
        placed[p["id"]] = {**entry, "surface": p.get("surface", 0.06)}
    s = {"name": kit.get("name", out.name), "background": "room.png", "floor": kit.get("floor", 0.86),
         "ground": kit.get("ground", {}), "backdrops": kit.get("far", []), "pieces": pieces}
    write_json(out / "set.json", s)
    return s


def validate_kit(kit: dict) -> list[str]:
    bad = []
    if not isinstance(kit.get("room"), dict) or not str(kit["room"].get("prompt", "")).strip():
        bad.append("room.prompt: describe the empty room")
    elif str(kit["room"]["prompt"]).startswith("TODO"):
        bad.append("room.prompt is still the template's TODO")
    ids = set()
    for i, p in enumerate(kit.get("props", [])):
        if not isinstance(p, dict):
            bad.append(f"props[{i}] is not an object")
            continue
        pid = p.get("id")
        if not is_safe_name(f"{pid}.png") or "/" in str(pid):
            bad.append(f"props[{i}].id: latin letters, digits, - and _")
        if pid in ids:
            bad.append(f"props[{i}].id '{pid}' is used twice")
        ids.add(pid)
        for k in ("prompt", "x", "width"):
            if k not in p:
                bad.append(f"props[{i}] has no '{k}'")
    for i, b in enumerate(kit.get("far", [])):
        if not isinstance(b, dict) or not is_safe_name(b.get("image")):
            bad.append(f"far[{i}].image: a picture inside the set's folder")
    return bad


def placeholder(kit: dict, out: Path) -> None:
    """Plain pictures drawn by code (free, offline): a wall and a floor, a flat shape per prop. A stand-in to block
    out scenes before the set is painted."""
    from PIL import ImageDraw
    floor = float(kit.get("floor", 0.86))
    room = Image.new("RGBA", WORLD, (214, 206, 190, 255))
    ImageDraw.Draw(room).rectangle([0, int(WORLD[1] * (floor - 0.12)), WORLD[0], WORLD[1]], fill=(150, 126, 100, 255))
    room.save(out / "room.png")
    for i, p in enumerate(kit.get("props", [])):
        w = max(int(float(p.get("width", 0.2)) * WORLD[0]), 8)
        im = Image.new("RGBA", (w, max(int(w * 0.8), 8)), (96 + 20 * (i % 4), 80, 70, 255))
        im.save(out / f"{p['id']}.png")


def make(w: World, slug: str, only: set | None = None, layout_only: bool = False, log=print,
         model: str = oi.DEFAULT_MODEL, quality: str = "medium", plain: bool = False) -> dict:
    out = w.set_dir(slug)
    kp = out / "kit.json"
    if not kp.is_file():
        raise WorldError(f"no sets/{slug}/kit.json: `tadam new set {slug}` writes one to fill in")
    kit = json.loads(kp.read_text(encoding="utf-8"))
    bad = [b for b in validate_kit(kit) if not (plain and b.startswith("room.prompt"))]
    if bad:
        raise WorldError("kit.json: " + "; ".join(bad))
    if plain:
        placeholder(kit, out)
    elif not layout_only:
        style = style_line(kit, w.style())
        only = set(only or ())
        jobs = []
        with cf.ThreadPoolExecutor(8) as ex:
            if not only or "room" in only:
                jobs.append(ex.submit(gen_room, kit, out, style, model, quality))
            for p in kit.get("props", []):
                if not only or p["id"] in only:
                    jobs.append(ex.submit(gen_prop, kit, p, out, style, model, quality))
            for j in jobs:
                log(" ".join(str(x) for x in j.result()))
    s = layout(kit, out)
    log(f"set -> {out / 'set.json'}: {len(s['pieces'])} pieces")
    return s
