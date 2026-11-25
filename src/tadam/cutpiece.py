"""Cut a SET PIECE out of a scene's background: an armchair, a crate, a stump, so heroes can go behind it.

usage: python -m tadam.cutpiece <set or scene folder> <id> <x0> <y0> <x1> <y1> [--base Y] [--front] [--write]
  x0 y0 x1 y1   the box round the thing, shares of the BACKGROUND PICTURE (as you see it in scenes/<scene>/bg.png)
  --base Y      where the thing stands on the ground, share of the picture's height (default: the box's bottom)
  --front       a foreground frame: always in front of everyone (dark corners, grass at the bottom edge)
  --write       also put it into scenes/<scene>/scene.json ("pieces", replacing one with the same id)
  --not x0 y0 x1 y1   a box that is surely NOT the thing (a wall showing between its parts); may repeat
  --sure x0 y0 x1 y1  a box that surely IS the thing (a part GrabCut lost: a blanket over its arm); may repeat
  --moves       the piece will MOVE (engine/life.gd: a lamp that swings, a cloud that drifts): also writes
                <id>.under.png, the background in the box with the thing painted out (OpenCV inpaint), drawn under it
  --mask-pad N  (with --moves) px the painted-out place reaches past the thing's outline (default 6)
Writes scenes/<scene>/<id>.png: the picture's own pixels inside the box, transparent round the thing.

Nothing is painted anew: the piece is the background itself, laid over the same place, so it fits exactly. The
engine (stage.gd) draws it on a layer of its own, sorted in depth with the heroes by its base: a hero standing
deeper than the base is behind it. The outline is found by GrabCut (OpenCV, on this computer): the box's edge is
background for sure, the middle is the thing for sure, the rest is decided by colour.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from tadam import imgio
from tadam.jsonfile import write_json

STAGE = (720, 1280)


def cover(w, h):
    """The background is scaled to cover the stage and centred (stage.gd): picture px -> stage px."""
    k = max(STAGE[0] / w, STAGE[1] / h)
    return k, (STAGE[0] - w * k) / 2, (STAGE[1] - h * k) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="a set folder (set.json) or a scene folder (scene.json)")
    ap.add_argument("id")
    ap.add_argument("box", nargs=4, type=float)
    ap.add_argument("--base", type=float, default=None)
    ap.add_argument("--front", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--not", dest="nots", nargs=4, type=float, action="append", default=[])
    ap.add_argument("--sure", nargs=4, type=float, action="append", default=[])
    ap.add_argument("--core", type=float, default=0.35, help="share of the box in its middle that is surely the thing")
    ap.add_argument("--moves", action="store_true")
    ap.add_argument("--mask-pad", type=int, default=6)
    a = ap.parse_args()
    folder = Path(a.folder)
    spec_file = folder / "set.json" if (folder / "set.json").exists() else folder / "scene.json"
    scene = json.loads(spec_file.read_text(encoding="utf-8"))
    img = imgio.imread(str(folder / scene.get("background", "bg.png")), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = a.box
    bx0, by0, bx1, by1 = int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)
    pad = 6
    rx0, ry0, rx1, ry1 = max(bx0 - pad, 0), max(by0 - pad, 0), min(bx1 + pad, w), min(by1 + pad, h)

    mask = np.full((h, w), cv2.GC_BGD, np.uint8)
    mask[by0:by1, bx0:bx1] = cv2.GC_PR_FGD
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    hw, hh = (bx1 - bx0) * a.core / 2, (by1 - by0) * a.core / 2
    mask[int(cy - hh):int(cy + hh), int(cx - hw):int(cx + hw)] = cv2.GC_FGD
    # a box that touches the picture's edge: that side is the thing cut by the frame, not background
    if bx0 <= 1:
        mask[by0:by1, 0:3] = cv2.GC_PR_FGD
    if bx1 >= w - 1:
        mask[by0:by1, w - 3:w] = cv2.GC_PR_FGD
    if by1 >= h - 1:
        mask[h - 3:h, bx0:bx1] = cv2.GC_PR_FGD
    for nx0, ny0, nx1, ny1 in a.nots:
        mask[int(ny0 * h):int(ny1 * h), int(nx0 * w):int(nx1 * w)] = cv2.GC_BGD
    for sx0, sy0, sx1, sy1 in a.sure:
        mask[int(sy0 * h):int(sy1 * h), int(sx0 * w):int(sx1 * w)] = cv2.GC_FGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(img, mask, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)
    fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    # the biggest piece only, holes filled, a soft edge one pixel wide
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    if n > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = np.where(lab == big, 255, 0).astype(np.uint8)
    cnts, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    fg = np.zeros_like(fg)
    cv2.drawContours(fg, cnts, -1, 255, -1)
    fg = cv2.erode(fg, np.ones((3, 3), np.uint8))
    fg = cv2.GaussianBlur(fg, (3, 3), 0)

    crop = img[ry0:ry1, rx0:rx1]
    alpha = fg[ry0:ry1, rx0:rx1]
    out = np.dstack([crop, alpha])
    imgio.imwrite(str(folder / f"{a.id}.png"), out)

    k, ox, oy = cover(w, h)
    rect = [(rx0 * k + ox) / STAGE[0], (ry0 * k + oy) / STAGE[1], (rx1 - rx0) * k / STAGE[0], (ry1 - ry0) * k / STAGE[1]]
    base = (a.base if a.base is not None else y1) * h * k + oy
    piece = {"id": a.id, "image": f"{a.id}.png", "rect": [round(v, 4) for v in rect], "base": round(base / STAGE[1], 4)}
    if a.front:
        piece["front"] = True
    if a.moves:
        # the thing painted out of the background: what shows where it was as it swings or floats away
        hole = cv2.dilate((alpha > 20).astype(np.uint8) * 255, np.ones((2 * a.mask_pad + 1,) * 2, np.uint8))
        clean = cv2.inpaint(crop, hole, 9, cv2.INPAINT_TELEA)
        imgio.imwrite(str(folder / f"{a.id}.under.png"), clean)
        piece["under"] = f"{a.id}.under.png"
    if a.write:
        scene["pieces"] = [p for p in scene.get("pieces", []) if p.get("id") != a.id] + [piece]
        write_json(spec_file, scene, indent=1)
    print(json.dumps({**piece, "covered": round(float((alpha > 127).mean()), 2)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
