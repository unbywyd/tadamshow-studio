"""`tadam cover [episode] [--shot sh2] [--at 1.5]`: THE WORLD'S COVER FROM A FRAME of an episode (free: the engine
draws it from the world's own pictures, as `tadam frames` does), without the subtitles.

    default: the first episode, its first shot (usually the title card), the middle of the shot
    written to: world.json "cover" when it names a picture (png / jpg / webp), else cover.png; vertical, the film's
    size (720x1280 by default), a compact PNG (tadam.imgio). A cover that was there is moved to
    .tadam/removed/<time>/ first: nothing is lost.

sources.json: a cover with no source yet is declared "generated" by the kit (a frame of the world's own pictures,
each with its own source); one that has a source keeps it (say what changed if it is not true any more).
"""
from __future__ import annotations

import copy
import shutil
import time
from pathlib import Path

from PIL import Image

from tadam import imgio, render, sources
from tadam.episode import Episode
from tadam.world import WorldError, is_safe_name

COVERS = ("cover.png", "cover.jpg", "cover.jpeg", "cover.webp")


def target(world) -> str:
    """The cover's file: world.json "cover" when it names a picture of the world folder, else cover.png."""
    c = world.world_json().get("cover")
    if isinstance(c, str) and is_safe_name(c) and c.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        return c
    return "cover.png"


def make(ep: Episode, shot: str | None = None, at: float | None = None, board_preview: bool = False) -> dict:
    w = ep.world
    if not ep.shots:
        raise WorldError(f"episode {ep.n} has no shots")
    i = ep.index(shot) if shot else 0
    s = ep.shots[i]
    at = s.seconds / 2 if at is None else float(at)
    if not 0 <= at <= s.seconds:
        raise WorldError(f"--at {at:g}: shot {s.id} lasts {s.seconds:g} s")
    clean = copy.copy(ep)                              # (the same episode, no subtitles on the picture)
    clean.shots = [copy.copy(x) for x in ep.shots]
    for x in clean.shots:
        x.subs = []
    frame = w.work_dir() / "frames" / ep.n / f"_cover_{s.id}.png"
    render.snaps(clean, [(i, at, frame)], board_preview)
    rel = target(w)
    out = w.root / rel
    moved = None
    if out.exists():
        moved = w.work_dir() / "removed" / time.strftime("%Y%m%d-%H%M%S") / rel
        moved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out), str(moved))
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(frame) as im:
        im.load()
        size = im.size
        if rel.lower().endswith(".png"):
            imgio.save_png(im, out)
        elif rel.lower().endswith(".webp"):
            im.convert("RGB").save(out, "WEBP", lossless=True)
        else:
            im.convert("RGB").save(out, "JPEG", quality=92)
    data, _ = sources.load(w.root)
    declared = False
    if not sources.source_of(data, rel):
        declared = sources.declare(w.root, rel, {
            "source": "generated", "tool": f"tadam cover (a frame of episode {ep.n}, shot {s.id}, drawn by the kit's "
                                           f"engine from the world's own pictures)"})
    return {"path": out, "rel": rel, "size": size, "shot": s.id, "at": round(at, 2), "moved": moved,
            "declared": declared}


def existing(root: Path) -> list[str]:
    """The cover files at the world's root (any of the names the server takes)."""
    return [c for c in COVERS if (Path(root) / c).is_file()]
