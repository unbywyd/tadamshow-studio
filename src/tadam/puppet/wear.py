"""Turns "the head with the face cut out" (gen_wear.py) into the piece a puppet WEARS over a recorded face.
Used by cut_skin.py.

The new picture is only trusted for its SHAPE: where it is opaque, the puppet's own head pixels are kept, so the
scarf is the very same scarf, pixel for pixel. Three things come out:
  parts/head.wear.png   the scarf / hat / hair around the face, with the hole
  parts/head.back.png   the hole filled with the worn thing's own colour, darkened: the shadow inside a scarf,
                        seen wherever the recorded face does not fill the hole
  rig parts.head.face   {"center": [x, y], "size": [w, h]} of the hole in sheet coordinates: where the face goes
"""
import cv2
import numpy as np
from PIL import Image

from tadam.puppet import gen_mouth

HOLE = (0.08, 0.6)        # the hole is this share of the head, or the result is not trusted
SAME = 0.86               # the outline of the new picture must match the head's own this well (overlap / union)


def fit_wear(pdir, parts, pad, images):
    """Returns (notes, problems)."""
    head = parts["head"]
    head.pop("face", None)
    for f in ("head.wear.png", "head.back.png"):
        (pdir / "parts" / f).unlink(missing_ok=True)
    src = pdir / "wear.png"
    if not src.exists():
        return [], []

    im, _, x, y, w, h = gen_mouth.layout(pdir)
    orig = np.array(im)
    H0, W0 = orig.shape[:2]
    size = gen_mouth.SIZE
    new_a = np.array(Image.open(src).convert("RGBA").resize((size, size), Image.LANCZOS))[..., 3]
    new_a = (new_a > 128).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(new_a)
    if n < 2:
        return [], ["wear: nothing is left of the head"]
    new_a = (lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)   # the piece, without specks

    # lay it over the head as shown to the model: the outer outline is the same, so the two boxes must coincide
    ys, xs = np.nonzero(new_a)
    oa = orig[..., 3] > 128
    oys, oxs = np.nonzero(oa)
    sx0, sy0 = x + oxs.min() * w / W0, y + oys.min() * h / H0            # the head's own box, in the shown picture
    sx1, sy1 = x + (oxs.max() + 1) * w / W0, y + (oys.max() + 1) * h / H0
    kx, ky = (sx1 - sx0) / (xs.max() + 1 - xs.min()), (sy1 - sy0) / (ys.max() + 1 - ys.min())
    m = np.array([[kx, 0, sx0 - kx * xs.min()], [0, ky, sy0 - ky * ys.min()]], np.float32)
    shown = cv2.warpAffine(new_a * 255, m, (size, size), flags=cv2.INTER_LINEAR)
    keep = cv2.resize(shown[y:y + h, x:x + w], (W0, H0), interpolation=cv2.INTER_AREA) > 128
    # is it still the same piece? Its outline, holes filled, must coincide with the head's own outline. A model that
    # "finishes" the drawing (adds a body, changes the shape) gives a picture whose hole is somewhere else.
    cn, _ = cv2.findContours(keep.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    outline = np.zeros(oa.shape, np.uint8)
    cv2.drawContours(outline, cn, -1, 1, -1)
    co, _ = cv2.findContours(oa.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    own = np.zeros(oa.shape, np.uint8)
    cv2.drawContours(own, co, -1, 1, -1)
    same = float((outline & own).sum()) / max(float((outline | own).sum()), 1.0)
    if same < SAME:
        return [], [f"wear: the head was redrawn, not cut (its outline matches the head only {same:.0%}); not used"]
    keep &= oa

    solid = np.zeros_like(new_a[:1, :1])                                   # the head without holes
    cnts, _ = cv2.findContours(oa.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    solid = np.zeros(oa.shape, np.uint8)
    cv2.drawContours(solid, cnts, -1, 1, -1)
    hole = (solid > 0) & ~keep
    n, lab, stats, _ = cv2.connectedComponentsWithStats(hole.astype(np.uint8))
    if n < 2:
        return [], ["wear: the face was not cut out"]
    hole = lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    share = float(hole.sum()) / max(float(solid.sum()), 1.0)
    if not HOLE[0] <= share <= HOLE[1]:
        return [], [f"wear: the hole is {share:.0%} of the head; not used"]
    keep = (solid > 0) & ~hole                                             # everything but the face hole is worn

    soft = cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 0.8)
    wear = orig.copy()
    wear[..., 3] = (orig[..., 3].astype(np.float32) * np.clip(soft * 1.4 - 0.2, 0, 1)).astype(np.uint8)
    wear[wear[..., 3] == 0] = 0
    images["head.wear"] = Image.fromarray(wear, "RGBA")
    images["head.wear"].save(pdir / "parts" / "head.wear.png")

    colour = orig[..., :3][keep].reshape(-1, 3).mean(axis=0) * 0.45         # the shadow inside it
    grown = cv2.dilate(hole.astype(np.uint8), np.ones((7, 7), np.uint8)) & solid
    back = np.zeros_like(orig)
    back[grown > 0] = [int(colour[0]), int(colour[1]), int(colour[2]), 255]
    Image.fromarray(back, "RGBA").save(pdir / "parts" / "head.back.png")

    ys, xs = np.nonzero(hole)
    box = head["box"]
    head["face"] = {"center": [round((xs.min() + xs.max()) / 2 - pad + box[0], 1), round((ys.min() + ys.max()) / 2 - pad + box[1], 1)],
                    "size": [int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]}
    return [f"the head can be worn over a recorded face (the hole is {share:.0%} of it)"], []
