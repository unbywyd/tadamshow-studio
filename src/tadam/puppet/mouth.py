"""Turns "the same head with the mouth open" (gen_mouth.py) into a second drawing of the head in which
ONLY the mouth differs. Used by cut_skin.py.

The image model never repaints a picture exactly: the hair, the eyes and the outline all shift by a hair, and a head
swapped for such a copy would twitch with every word. So the new picture is first laid exactly over the old one,
then the one place where the two differ most is found (that is the mouth, whatever the character is), and only
that patch, with a soft edge, is laid on the puppet's own head. Everywhere else the two drawings are the same pixels.
"""
import cv2
import numpy as np
from PIL import Image

from tadam.puppet import gen_mouth

AREA = (0.003, 0.40)      # the mouth patch is this share of the painted head (a frog or a pumpkin is mostly mouth)


def _on_white(rgba):
    a = rgba[..., 3:4].astype(np.float32) / 255
    return rgba[..., :3].astype(np.float32) * a + 255.0 * (1 - a)


def fit_mouth(pdir, parts, pad, images):
    """Adds parts["head"]["variants"]["open"] and parts["head"]["mouth"]. Returns (notes, problems)."""
    head = parts["head"]
    head.get("variants", {}).pop("open", None)
    if not head.get("variants"):
        head.pop("variants", None)
    head.pop("mouth", None)
    (pdir / "parts" / "head.open.png").unlink(missing_ok=True)
    src = pdir / "mouth_open.png"
    if not src.exists():
        return [], []

    im, _, x, y, w, h = gen_mouth.layout(pdir)
    orig = np.array(im)
    H0, W0 = orig.shape[:2]
    size = gen_mouth.SIZE
    shown = np.full((size, size, 3), 255, np.float32)                    # what the model was shown
    shown[y:y + h, x:x + w] = cv2.resize(_on_white(orig), (w, h), interpolation=cv2.INTER_AREA)
    new = _on_white(np.array(Image.open(src).convert("RGBA").resize((size, size), Image.LANCZOS)))

    # 1. lay the new picture exactly over the old one (the model moves and scales it a little)
    small = 512
    g0 = cv2.cvtColor(cv2.resize(shown, (small, small)).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    g1 = cv2.cvtColor(cv2.resize(new, (small, small)).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        cc, warp = cv2.findTransformECC(g0, g1, warp, cv2.MOTION_AFFINE,
                                        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6), None, 5)
    except cv2.error:
        cc, warp = 0.0, np.eye(2, 3, dtype=np.float32)
    warp[:, 2] *= size / small
    new = cv2.warpAffine(new, warp, (size, size), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))

    # 2. back in the head's own pixels: where do the two pictures differ?
    mine = _on_white(orig)
    theirs = cv2.resize(new[y:y + h, x:x + w], (W0, H0), interpolation=cv2.INTER_AREA)
    inside = cv2.erode((orig[..., 3] > 200).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)
    diff = np.abs(theirs - mine).mean(axis=2) / 255.0 * inside
    sigma = max(0.012 * W0, 1.5)
    soft = cv2.GaussianBlur(diff, (0, 0), sigma)
    top = float(soft.max())
    n, labels = cv2.connectedComponents((soft > max(0.45 * top, 0.06)).astype(np.uint8))
    if n < 2:
        return [], ["mouth: the new head does not differ from the old one anywhere"]
    best = max(range(1, n), key=lambda i: float(diff[labels == i].sum()))
    core = (labels == best).astype(np.uint8)
    # the whole changed place around that core: lower threshold, but only what touches the core
    n2, wide = cv2.connectedComponents((soft > max(0.2 * top, 0.035)).astype(np.uint8))
    region = np.isin(wide, np.unique(wide[core > 0])) & (wide > 0)
    r = max(int(0.03 * W0), 3)
    mask = cv2.dilate(region.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    share = float(mask.sum()) / max(float((orig[..., 3] > 128).sum()), 1.0)
    ys, xs = np.nonzero(mask)
    box = head["box"]
    centre = [round(float(xs.mean()) - pad + box[0], 1), round(float(ys.mean()) - pad + box[1], 1)]
    mouth_size = [int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]

    # 3. only that patch, with a soft edge, on the puppet's own head
    alpha = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma)[..., None]
    out = orig.copy()
    out[..., :3] = np.clip(mine * (1 - alpha) + theirs * alpha, 0, 255).astype(np.uint8)
    out[orig[..., 3] == 0] = 0

    check = np.hstack([mine, theirs, _on_white(out)]).astype(np.uint8)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(check, [c + np.array([[[2 * W0, 0]]]) for c in cnts], -1, (220, 40, 40), 1)
    Image.fromarray(check).save(pdir / "_mouth_check.jpg", quality=88)

    if not AREA[0] <= share <= AREA[1]:
        return [], [f"mouth: the changed place is {share:.1%} of the head (alignment {cc:.2f}); not used"]
    images["head.open"] = Image.fromarray(out, "RGBA")
    images["head.open"].save(pdir / "parts" / "head.open.png")
    at = head["joint"]["at"]
    head.setdefault("variants", {})["open"] = {"size": [box[2], box[3]], "at": [round(at[0] - box[0], 1), round(at[1] - box[1], 1)]}
    head["mouth"] = {"center": centre, "size": mouth_size}
    return [f"the head has an open mouth ({share:.1%} of the head changes, alignment {cc:.2f})"], []
