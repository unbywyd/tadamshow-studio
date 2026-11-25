"""THE FACE BOARD of a puppet's head: where the recorded face shows on the site (scene "faces": "board").

The hero keeps its painted head whole (hat, horns, ears, hair: who it is) and only an OVAL of the recorded face shows
in a hole cut in it (engine/video_head.gd). The oval is rig parts.head.board = {"center": [x, y], "size": [w, h]} in
the pixels of parts/head.png (the picture with its pad), the format the engine and the site read.

Found from the drawing alone, the same rule for every hero (nothing is fitted by hand):
  - the head's centre line is its neck pin (a puppet is painted from the front, its head upright over the neck);
  - its crown is the top of the paint in a corridor around that line (horns and ears to the sides do not count;
    a hat does, as on the owner's hand-set heads);
  - the oval is about half as tall as crown-to-neck-pin and sits low on that span (a long neck stub: the span
    ends just under the chin, where the paint narrows into the neck), over the painted face; when the
    head has a known mouth (rig parts.head.mouth, from its open-mouth drawing) the oval's bottom is just under it;
  - its width is a share of the head's solid width at the oval's middle (thin ears and horns opened away), kept
    between a tall and a round oval, and never wider than the paint there.
Snug, not wide: an oval that crops the brow and the cheeks a little reads as a hole cut in a board (the owner's
choice, 23.11); a wide one shows too much of the dark hole. `tadam frames --board-preview` shows it on the heroes.
"""
from __future__ import annotations

import numpy as np
import cv2
from PIL import Image

HEIGHT = 0.51          # the oval's height against crown-to-neck-pin
CENTRE = 0.67          # its middle, down from the crown, against the same span
UNDER_MOUTH = 0.08     # with a known mouth: the oval's bottom this far under the mouth's middle (same span)
MOUTH_PULL = 0.10      # ...but the mouth moves the oval at most this far from where the shape puts it
WIDTH = 0.60           # the oval's width against the head's solid width at its middle
ASPECT = (0.62, 0.95)  # width / height: from a tall oval to an almost round one
CHIN = 2.0            # the chin: the first row over the pin whose solid width is this many times the neck's
CHIN_LOW = 0.70        # ...looked for only this low on crown-to-pin (higher up it is a hat brim, not a chin)
CHIN_BELOW = 0.15      # ...and the span ends this far under it (share of crown-to-chin) when that is above the pin
CORRIDOR = 0.12        # the crown is looked for this far (share of the picture's width) each side of the centre line


def fit(head: Image.Image, joint: tuple[float, float], mouth: tuple[float, float] | None = None) -> dict | None:
    """The board of a head picture. `joint`: the neck pin in the picture's pixels; `mouth`: the mouth's middle in the
    picture's pixels, when known. None when the picture has no paint over the pin."""
    a = np.array(head.convert("RGBA"))[..., 3] > 128
    H, W = a.shape
    jx, jy = float(joint[0]), min(float(joint[1]), H - 1.0)
    x0, x1 = max(int(jx - CORRIDOR * W), 0), min(int(jx + CORRIDOR * W) + 1, W)
    rows = np.nonzero(a[: int(jy) + 1, x0:x1].any(axis=1))[0]
    if not len(rows):
        return None
    crown = float(rows[0])
    span = jy - crown
    if span < 8:
        return None
    # the solid paint: ears, horns and hair strands opened away
    k = max(3, int(0.12 * span) | 1)
    solid = cv2.morphologyEx(a.astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    # a long neck stub: the pin far under the chin. The chin is where the paint grows from the neck's width to
    # CHIN times it; the span ends a little under it instead of at the pin
    neck = _run_at(np.nonzero(a[int(jy)])[0], jx)
    if neck:
        nw = neck[1] - neck[0] + 1
        for y in range(int(jy), int(crown), -1):
            run = _run_at(np.nonzero(solid[y])[0], jx)
            if y < crown + CHIN_LOW * span:
                break                      # (no chin low on the head: the pin is under the face itself)
            if run and run[1] - run[0] + 1 >= CHIN * nw:
                end = y + CHIN_BELOW * (y - crown)
                if end < jy:
                    span = end - crown
                break
    h = HEIGHT * span
    cy = crown + CENTRE * span
    if mouth is not None:
        want = float(mouth[1]) + UNDER_MOUTH * span - h / 2
        cy = float(np.clip(want, cy - MOUTH_PULL * span, cy + MOUTH_PULL * span))
    row = np.nonzero(solid[int(round(cy))])[0]
    run = _run_at(row, jx)
    w = WIDTH * (run[1] - run[0] + 1) if run else ASPECT[0] * h
    w = float(np.clip(w, ASPECT[0] * h, ASPECT[1] * h))
    if run:
        w = min(w, 0.9 * (run[1] - run[0] + 1))
        # the centre line, unless the paint there is lopsided around it (then the middle of the paint)
        cx = jx if run[0] + w / 2 <= jx <= run[1] - w / 2 else (run[0] + run[1]) / 2
    else:
        cx = jx
    return {"center": [round(cx), round(cy)], "size": [round(w), round(h)]}


def _run_at(xs: np.ndarray, x: float) -> tuple[int, int] | None:
    """The run of consecutive painted columns that holds x (or the nearest one)."""
    if not len(xs):
        return None
    cuts = np.nonzero(np.diff(xs) > 1)[0]
    starts = np.r_[xs[0], xs[cuts + 1]]
    ends = np.r_[xs[cuts], xs[-1]]
    i = int(np.argmin([0 if s <= x <= e else min(abs(s - x), abs(e - x)) for s, e in zip(starts, ends)]))
    return int(starts[i]), int(ends[i])


def fit_board(pdir, parts: dict, pad: int, images: dict, view: str = "front") -> tuple[list[str], list[str]]:
    """Sets parts["head"]["board"] from parts/head.png (cut_skin, after the mouth is found). (notes, problems)."""
    head = parts.get("head")
    if not isinstance(head, dict):
        return [], []
    head.pop("board", None)
    if view in ("back", "side"):
        return [], []          # (the recorded face is filmed from the front: a board only on a front head)
    img = images.get("head")
    if img is None:
        return [], ["board: no head picture"]
    bx, by = head["box"][0], head["box"][1]
    at = head["joint"]["at"]
    joint = (at[0] - bx + pad, at[1] - by + pad)
    m = head.get("mouth")
    mouth = (m["center"][0] - bx + pad, m["center"][1] - by + pad) if isinstance(m, dict) else None
    b = fit(img, joint, mouth)
    if b is None:
        return [], ["board: the head has no paint over its neck pin"]
    head["board"] = b
    return [f"face board placed (oval {b['size'][0]}x{b['size'][1]} px at {b['center'][0]},{b['center'][1]})"], []
