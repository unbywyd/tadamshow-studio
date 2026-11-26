"""FRAMES OF A DRAWING (`tadam strip`; the engine's side is engine/frames.gd).

A part of a puppet or a piece of a set may be several drawings shown in turn, round and round, each drawing with
its own speed: a flame, a flag, cloth that stirs a little, a wing. The record is the same in both places
(rig.json parts.<name>, set.json pieces[i]):

    "frames": {"count": 4, "fps": 8, "mode": "loop", "offset": 0.25}

Frame 1 is the drawing itself (skirt.png); frames 2..count lie beside it (skirt.f2.png ... skirt.f4.png), every one
THE SAME SIZE as the first, so they share its joint and its place and nothing jumps.

A person or a picture model draws a STRIP: `count` equal cells in one row, each the whole canvas of the drawing.
    template()   the strip to start from: the drawing repeated in every cell (redraw cells 2..count in it)
    cut()        the strip cut into frames, laid beside the drawing, the record written
    clear()      the frames and the record taken away again
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from tadam import imgio
from tadam.world import World, WorldError, read_json, write_json

MAX = 16                       # frames of one drawing (engine/frames.gd MAX)
MAX_ORDER = 64
MODES = ("loop", "pingpong", "once")
FPS = (0.5, 30.0)
HEAVY = 24_000_000             # pixels of all the frames of one drawing: more is a warning (memory on a phone)
FRAME_NAME = re.compile(r"\.f([0-9]+)$")
NO_FRAMES = ("head",)          # a face and a mouth are put into the head; hands are drawn by the engine


def frame_names(first: str, count: int) -> list[str]:
    """The file names of frames 2..count beside the first one: skirt.png -> [skirt.f2.png, ...]."""
    stem, dot, ext = first.rpartition(".")
    return [f"{stem}.f{k}.{ext}" for k in range(2, count + 1)]


def problems(rec: object) -> list[str]:
    """What is wrong with a "frames" record (an empty list: nothing)."""
    if not isinstance(rec, dict):
        return ["'frames' must be an object: {\"count\": 4, \"fps\": 8}"]
    out = []
    n = rec.get("count")
    if not isinstance(n, int) or isinstance(n, bool) or not 2 <= n <= MAX:
        out.append(f"frames.count must be a whole number 2..{MAX}")
        n = None
    fps = rec.get("fps", 8)
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or not FPS[0] <= fps <= FPS[1]:
        out.append(f"frames.fps must be {FPS[0]:g}..{FPS[1]:g} (frames a second)")
    if rec.get("mode", "loop") not in MODES:
        out.append(f"frames.mode must be one of {', '.join(MODES)}")
    off = rec.get("offset", 0)
    if not isinstance(off, (int, float)) or isinstance(off, bool) or not 0 <= off <= 1:
        out.append("frames.offset must be 0..1 (the share of the round it starts at)")
    if "order" in rec:
        o = rec["order"]
        if not (isinstance(o, list) and 1 <= len(o) <= MAX_ORDER
                and all(isinstance(v, int) and not isinstance(v, bool) for v in o)):
            out.append(f"frames.order must be a list of frame numbers (at most {MAX_ORDER})")
        elif n and any(not 1 <= v <= n for v in o):
            out.append(f"frames.order names a frame outside 1..{n}")
    extra = sorted(set(rec) - {"count", "fps", "mode", "offset", "order"})
    if extra:
        out.append(f"frames: unknown key {', '.join(extra)}")
    return out


def can_have(part: str) -> bool:
    """Whether a puppet's part may be frames (not the head, not a hand)."""
    return part not in NO_FRAMES and not part.startswith("hand_")


def files_state(folder: Path, first: str, rec: dict) -> dict:
    """The frames' files against the first drawing: {"missing": [names], "size": [names], "pixels": total}."""
    out = {"missing": [], "size": [], "pixels": 0}
    try:
        with Image.open(folder / first) as im:
            size = im.size
    except OSError:
        return out
    n = rec.get("count")
    if not isinstance(n, int) or isinstance(n, bool) or not 2 <= n <= MAX:
        return out
    out["pixels"] = size[0] * size[1] * n
    for name in frame_names(first, n):
        try:
            with Image.open(folder / name) as im:
                if im.size != size:
                    out["size"].append(f"{name} is {im.size[0]}x{im.size[1]}, the first frame is {size[0]}x{size[1]}")
        except OSError:
            out["missing"].append(name)
    return out


def unused(folder: Path, records: dict) -> list[str]:
    """Frames' files in `folder` that no record shows: `records` is {first drawing's file name: its "frames" record
    or None}. A puppet made again or a set painted again writes its JSON anew, and the frames cut before are left
    lying (and would be sent to the server for nothing)."""
    out = []
    try:
        names = sorted(f.name for f in folder.iterdir() if f.is_file())
    except OSError:
        return out
    for name in names:
        stem, dot, ext = name.rpartition(".")
        m = FRAME_NAME.search(stem)
        if not m or not dot:
            continue
        rec = records.get(f"{stem[:m.start()]}.{ext}")
        n = rec.get("count") if isinstance(rec, dict) else None
        if not isinstance(n, int) or isinstance(n, bool) or int(m.group(1)) > n or int(m.group(1)) < 2:
            out.append(name)
    return out


# ------------------------------------------------------------------------------------------- where the record is

class Target:
    """The drawing a strip is for: its file, the JSON file its record lives in and how to reach the record."""

    def __init__(self, world: World, image: Path):
        self.world = world
        self.image = image
        try:
            rel = image.resolve().relative_to(world.root.resolve()).as_posix()
        except ValueError:
            raise WorldError(f"{image} is not inside this world") from None
        self.rel = rel
        if not image.is_file():
            raise WorldError(f"no drawing {rel}")
        if FRAME_NAME.search(image.stem):
            raise WorldError(f"{rel} is a frame itself: name the first drawing")
        seg = rel.split("/")
        if seg[0] == "heroes" and len(seg) >= 5 and seg[2] == "puppet" and seg[-2] == "parts":
            self.kind = "part"
            self.name = image.stem
            self.json = image.parent.parent / "rig.json"
            if "." in self.name:
                raise WorldError(f"{rel} is a second drawing of a part (a variant): frames go on its first drawing")
            if not can_have(self.name):
                raise WorldError(f"the {self.name} cannot be frames: a face is put into the head, and hands are "
                                 f"drawn by the engine")
        elif seg[0] == "sets" and len(seg) >= 3:
            self.kind = "piece"
            self.name = "/".join(seg[2:])
            self.json = world.root / "sets" / seg[1] / "set.json"
        else:
            raise WorldError("frames go on a puppet's part (heroes/<hero>/puppet/parts/<part>.png) or on a set "
                             "piece (sets/<set>/<piece>.png)")
        self.data, err = read_json(self.json)
        if not isinstance(self.data, dict):
            raise WorldError(f"{self.json.relative_to(world.root).as_posix()}: {err or 'not an object'}")
        self.holder = self._holder()

    def _holder(self) -> dict:
        if self.kind == "part":
            p = (self.data.get("parts") or {}).get(self.name)
            if not isinstance(p, dict):
                raise WorldError(f"rig.json has no part '{self.name}'")
            return p
        for p in self.data.get("pieces") or []:
            if isinstance(p, dict) and p.get("image") == self.name:
                return p
        raise WorldError(f"set.json has no piece with the image '{self.name}' (frames are for set pieces: cut the "
                         f"thing out of the room first)")

    def where(self) -> str:
        j = self.json.relative_to(self.world.root).as_posix()
        return f"{j} parts.{self.name}.frames" if self.kind == "part" else f"{j} pieces[image={self.name}].frames"

    def save(self) -> None:
        write_json(self.json, self.data)


def _rgba(path: Path) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("RGBA")


# ------------------------------------------------------------------------------------------- the three actions

def template(world: World, image: Path, count: int, out: Path | None = None) -> dict:
    """A strip to start from: the drawing repeated in `count` cells. Written into .tadam/strip/ unless `out`."""
    t = Target(world, image)
    if not 2 <= count <= MAX:
        raise WorldError(f"2..{MAX} frames")
    first = _rgba(image)
    w, h = first.size
    strip = Image.new("RGBA", (w * count, h), (0, 0, 0, 0))
    for k in range(count):
        strip.paste(first, (k * w, 0))
    out = out or world.root / ".tadam" / "strip" / f"{t.rel.replace('/', '~').rsplit('.', 1)[0]}.strip{count}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    strip.save(out)
    return {"strip": out.as_posix(), "cells": count, "cell": [w, h], "drawing": t.rel}


def cut(world: World, image: Path, strip: Path, count: int, fps: float = 8.0, mode: str = "loop",
        offset: float = 0.0, order: list[int] | None = None, replace_first: bool = False) -> dict:
    """The strip cut into `count` frames beside the drawing, and the record written. The drawing itself stays as
    it is (it is frame 1) unless `replace_first`: then the strip's first cell is written over it."""
    t = Target(world, image)
    rec: dict = {"count": count, "fps": fps}
    if mode != "loop":
        rec["mode"] = mode
    if offset:
        rec["offset"] = offset
    if order:
        rec["order"] = order
    bad = problems(rec)
    if bad:
        raise WorldError("; ".join(bad))
    if not strip.is_file():
        raise WorldError(f"no strip {strip}")
    first = _rgba(image)
    w, h = first.size
    sheet = _rgba(strip)
    if sheet.size[0] % count:
        raise WorldError(f"the strip is {sheet.size[0]} px wide: that is not {count} equal cells")
    cw, ch = sheet.size[0] // count, sheet.size[1]
    if abs(cw / ch - w / h) > 0.01 * (w / h):
        raise WorldError(f"a cell of the strip is {cw}x{ch}, the drawing is {w}x{h}: another shape. Every cell must "
                         f"be the whole canvas of the drawing (start from `tadam strip {t.rel} --template {count}`)")
    cells = []
    for k in range(count):
        c = sheet.crop((k * cw, 0, (k + 1) * cw, ch))
        cells.append(c if (cw, ch) == (w, h) else c.resize((w, h), Image.LANCZOS))
    same_first = cells[0].tobytes() == first.tobytes()
    out = {"drawing": t.rel, "record": rec, "where": t.where(), "frames": [t.rel], "first": "kept"}
    if replace_first and not same_first:
        keep = world.root / ".tadam" / "strip" / f"{t.rel.replace('/', '~').rsplit('.', 1)[0]}.before.png"
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_bytes(image.read_bytes())
        imgio.save_png(cells[0], image)
        out["first"] = "replaced"
        out["before"] = keep.as_posix()
    elif not same_first:
        out["first"] = "kept_differs"
    for name, c in zip(frame_names(image.name, count), cells[1:]):
        imgio.save_png(c, image.parent / name)
        out["frames"].append(f"{t.rel.rsplit('/', 1)[0]}/{name}")
    _drop_beyond(image, count)
    t.holder["frames"] = rec
    t.save()
    if t.kind == "part":
        out["hero"] = t.rel.split("/")[1]      # (its rig.json changed: `tadam hero check` is due again)
    return out


def clear(world: World, image: Path) -> dict:
    """The drawing is one picture again: its frames' files and its record are taken away."""
    t = Target(world, image)
    gone = _drop_beyond(image, 1)
    had = t.holder.pop("frames", None) is not None
    if had:
        t.save()
    return {"drawing": t.rel, "removed": gone, "record": had}


def _drop_beyond(image: Path, count: int) -> list[str]:
    """Removes <stem>.f<k>.<ext> with k > count (frames left by a longer strip). Returns their names."""
    gone = []
    for f in sorted(image.parent.glob(f"{image.stem}.f*{image.suffix}")):
        m = FRAME_NAME.search(f.stem)
        if m and f.stem[:m.start()] == image.stem and int(m.group(1)) > count:
            f.unlink()
            gone.append(f.name)
    return gone
