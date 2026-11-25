"""Measure how well a puppet is assembled: are the joints where a puppet maker would put them?

usage: python -m tadam.puppet.audit <puppet folder> [...] [--montage out.jpg] [--json out.json]
Reads <folder>/{rig.json, parts/*.png}; changes nothing. A view is the folder <puppet>/side or <puppet>/back.

The measurements do not know how the joints were chosen: they look only at the painted pieces and the rig.
  axis      a body block's own centre line (robust to a one-sided detail);
  centre    how far the neck and the waist pins are from the centre line of their block;
  stack     how far the head stands from the chest's centre line, and the chest from the pelvis's, in the rest pose;
  pairs     how unequal the left and right shoulders (and hips) are: distance from the centre line, and height;
  neck      how deep the neck pin sits under the real neckline, how much neck stays visible under the chin,
            and whether the pin is in the END of the neck (the paint under it stops about a radius away);
  bridge    the thinnest paint around a pin while its piece swings through its whole range (a gap = a low number);
  skirt     (if the puppet has one) how far the pelvis sticks out from behind it, how far its hem is from the floor,
            and what share of the legs it covers;
  overhang  how far a limb's end reaches past its pin, in units of the limb's own half-width there. A pin belongs in
            the middle of the rounded end (1.0); with more than that the end sticks out like a knob when the joint bends;
  flat      whether a limb's end at a pin is ROUNDED: its width seven tenths of the way from the pin to the tip,
            against its width at the pin (a round end: about 0.7; a piece cut off straight: about 1). A flat end
            shows its corners, and a gap beside them, as soon as the joint bends. Elbows and knees only: at a wrist
            or an ankle a flat end is a cuff or a hem the hand or the foot comes out of;
  views     (a view: "loaf/side", "loaf/back") whether it is the SAME character as its front view: the head as tall
            (against the body, neck to sole), the body as wide from behind, and seen from the side not thinner than a
            body can be (a heavy one, wide from the front, nearly as deep as it is wide). A profile painted into the
            slim profile pattern comes out with a small head and a thin body: a fat hero is fat only from the front;
  stance    how the puppet stands at rest: what share of each arm lies over the body (arms held in front),
            how far apart the legs are (in thigh widths), and how high the shoulder tops are against the chest top.
"""
import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from tadam.puppet import rigkit
from tadam.jsonfile import write_json

# What counts as a defect. Pixels are sheet pixels (a puppet is about 700 px from neck to sole).
CENTRE_TOL = 0.04      # a centre pin may be this share of its block's width away from the block's centre line
STACK_TOL = 0.07       # the head (chest) may stand this share of the chest (pelvis) width off the centre line
PAIR_TOL = 0.06        # left/right pins may differ by this share of the block's width
BRIDGE_MIN = 7.0       # px of paint around a pin, at the worst angle
NECK_DEPTH = (-0.5, 1.0)   # the neck pin sits this many neck radii under the neckline
NECK_TAIL = (0.4, 1.9)     # under the neck pin there are this many neck radii of paint, then the neck ends
OVERHANG = 1.3         # a limb end may reach this many of its own half-widths past its pin
FLAT_END = 0.92        # ...and seven tenths of the way to its tip it is at most this share of its width at the pin
ARMS_OVER = 0.30       # at most this share of a hanging arm may lie over the body
LEGS_APART = 1.45      # the hips are at most this many thigh widths apart (1 = the thighs touch)
HEAD_SAME = (0.88, 1.12)   # a view's head is this many times as tall as the front view's (against the body)
DEPTH_MIN = 0.6        # seen from the side the chest is at least this share of its width from the front...
DEPTH_HEAVY = 0.8      # ...and a heavy body's (wider than HEAVY of the body's height from the front) this share
HEAVY = 0.45
BACK_SAME = (0.8, 1.2)    # from behind, the chest as wide as from the front
SKIRT_POKE = 4.0       # px of pelvis allowed to show beside the skirt
SKIRT_DRAG = 8.0       # px the hem may hang below the soles
SKIRT_LEN_TOL = 0.2    # the skirt may cover this much more or less of the leg than its pattern asks for


def filled(mask):
    """The piece without its inner holes."""
    m = mask.astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = np.zeros_like(m)
    cv2.drawContours(out, cnts, -1, 1, -1)
    return out


def inscribed(mask):
    """Distance from every painted pixel to the nearest unpainted one, with inner holes filled first."""
    return cv2.distanceTransform(cv2.copyMakeBorder(filled(mask), 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0),
                                 cv2.DIST_L2, 5)[1:-1, 1:-1]


def axis_x(mask, reach=0.3):
    """The centre line of a piece: the vertical line about which it mirrors onto itself best. A parrot on one
    shoulder or a one-sided plume cannot pull it far, because the bulk of the piece still has to match."""
    m = filled(mask).astype(bool)
    w = m.shape[1]
    centre = float(np.nonzero(m)[1].mean())
    best, best_k = -1, int(round(2 * centre))
    for k in range(int(2 * (centre - reach * w)), int(2 * (centre + reach * w)) + 1):   # the line is x = k / 2
        lo, hi = max(0, k - (w - 1)), min(w - 1, k)
        if hi <= lo:
            continue
        score = int(np.count_nonzero(m[:, lo:hi + 1] & m[:, k - hi:k - lo + 1][:, ::-1]))
        if score > best or (score == best and abs(k / 2 - centre) < abs(best_k / 2 - centre)):
            best, best_k = score, k
    return best_k / 2


def head_axis(mask, agree=0.08):
    """The centre line of a head. Normally its mirror line; but a big one-sided thing (a feather, a side ponytail)
    pulls a mirror line, so it is checked against the middle of the biggest solid part of the head (the skull).
    When the two disagree by more than `agree` of the width, the skull is believed."""
    mirror = axis_x(mask)
    dt = inscribed(mask)
    skull = float(np.nonzero(dt >= 0.9 * dt.max())[1].mean())
    return mirror if abs(mirror - skull) <= agree * mask.shape[1] else skull


def rest_edge(mask, x, rho, top=True):
    """Where a ball of radius `rho` comes to rest when lowered onto the piece along the column `x` (from above if
    `top`, else from below): the row of the ball's lowest (highest) point. A notch narrower than the ball does not
    swallow it, a wide dip does. Row units are the mask's; the result may be fractional."""
    pad = int(math.ceil(rho)) + 3
    m = cv2.copyMakeBorder(filled(mask), pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    out = cv2.distanceTransform(1 - m, cv2.DIST_L2, 5)        # empty pixel -> distance to the nearest paint
    col = out[:, int(round(x)) + pad]
    ys = range(len(col)) if top else range(len(col) - 1, -1, -1)
    for y in ys:
        if col[y] <= rho:
            return (y + rho - pad) if top else (y - rho - pad)
    return 0.0 if top else float(mask.shape[0] - 1)


def span(mask, y):
    """(left, right) painted columns of row y, or None."""
    y = int(round(y))
    if not 0 <= y < mask.shape[0]:
        return None
    xs = np.nonzero(mask[y])[0]
    return (int(xs[0]), int(xs[-1])) if len(xs) else None


def load(pdir):
    """rig + {part: mask in the part's own box}. Works for a fitted puppet and for a pattern rig with a skin."""
    pdir = Path(pdir)
    rig = json.loads((pdir / "rig.json").read_text(encoding="utf-8"))
    pad = rig["pad"]
    masks = {}
    for n, p in rig["parts"].items():
        a = np.array(Image.open(pdir / "parts" / f"{n}.png").convert("RGBA"))[..., 3]
        masks[n] = a[pad:pad + p["box"][3], pad:pad + p["box"][2]] > 128
    return rig, masks


def _local(rig, n, pt):
    b = rig["parts"][n]["box"]
    return pt[0] - b[0], pt[1] - b[1]


def rest_shift(rig):
    """Where every part stands in the rest pose: part -> (dx, dy) to add to its sheet coordinates. All angles are 0,
    so the rest pose is pure translation; the root stays where it is on the sheet."""
    parts, out = rig["parts"], {}

    def solve(n):
        if n not in out:
            p = parts[n]
            if p["parent"] is None:
                out[n] = (0.0, 0.0)
            else:
                px, py = solve(p["parent"])
                j = p["joint"]
                out[n] = (px + j["parent_at"][0] - j["at"][0], py + j["parent_at"][1] - j["at"][1])
        return out[n]

    for n in parts:
        solve(n)
    return out


def placed(rig, masks, names, angles=None, margin=320):
    """The union of the parts `names` as one mask, in the pose `angles` (default: all zero), on a canvas that holds
    the whole rest pose plus `margin`. Returns (mask, (x0, y0)): canvas pixel + (x0, y0) = the root's sheet coords."""
    parts = rig["parts"]
    shift = rest_shift(rig)
    x0 = int(min(parts[n]["box"][0] + shift[n][0] for n in parts)) - margin
    y0 = int(min(parts[n]["box"][1] + shift[n][1] for n in parts)) - margin
    x1 = int(max(parts[n]["box"][0] + parts[n]["box"][2] + shift[n][0] for n in parts)) + margin
    y1 = int(max(parts[n]["box"][1] + parts[n]["box"][3] + shift[n][1] for n in parts)) + margin
    root = next(n for n in parts if parts[n]["parent"] is None)
    rp = rigkit.pivot(rig, root)
    mats = rigkit.world_matrices(rig, angles or {}, root=(rp[0] - x0, rp[1] - y0))
    canvas = np.zeros((y1 - y0, x1 - x0), np.uint8)
    for n in names:
        b, pv = parts[n]["box"], rigkit.pivot(rig, n)
        m = mats[n] @ np.array([[1, 0, b[0] - pv[0]], [0, 1, b[1] - pv[1]], [0, 0, 1]], float)
        canvas |= cv2.warpAffine(masks[n].astype(np.uint8), m[:2].astype(np.float32), (canvas.shape[1], canvas.shape[0]),
                                 flags=cv2.INTER_NEAREST)
    return canvas.astype(bool), (x0, y0)


def arm_over_body(rig, masks, side, spread=None):
    """What share of an arm (below its shoulder cap) lies over the body, with the arm turned `spread` degrees outward
    at the shoulder (None = as the rig's rest stance says). The body is the chest, the pelvis and the thighs: a hand
    resting on a wide skirt is not an arm held in front."""
    parts = rig["parts"]
    upper = f"upper_arm_{side}"
    out = 1.0 if side == "l" else -1.0
    rest = dict(rig.get("rest", {}))
    if spread is not None:
        rest[upper] = out * spread
    body, origin = placed(rig, masks, [n for n in ("chest", "pelvis", "thigh_l", "thigh_r") if n in parts])
    arm, _ = placed(rig, masks, [upper, f"forearm_{side}", f"hand_{side}"], rest)
    j = parts[upper]["joint"]
    cut = int(j["parent_at"][1] + rest_shift(rig)[parts[upper]["parent"]][1] - origin[1] + 1.2 * j.get("radius", 28))
    arm[:max(cut, 0)] = False
    return float(np.count_nonzero(arm & body)) / max(np.count_nonzero(arm), 1)


def _run(row, x):
    """The run of paint in a row that holds column x (or the nearest one): its width."""
    xs = np.nonzero(row)[0]
    if not len(xs):
        return 0
    k = int(np.argmin(np.abs(xs - x)))
    lo = hi = k
    while lo > 0 and xs[lo - 1] == xs[lo] - 1:
        lo -= 1
    while hi < len(xs) - 1 and xs[hi + 1] == xs[hi] + 1:
        hi += 1
    return int(xs[hi] - xs[lo] + 1)


def end_width(m, x, y, reach, top):
    """The width of a limb end seven tenths of the way from its pin (row y) to its tip, against its width at the pin."""
    at_pin = _run(m[y], x)
    yy = int(round(y - 0.7 * reach if top else y + 0.7 * reach))
    if at_pin <= 0 or not (0 <= yy < m.shape[0]):
        return None
    return _run(m[yy], x) / at_pin


def measure_overhang(rig, masks, out, problems):
    """For every pin between two limb pieces: how far each piece's end reaches past the pin, against how thick the
    piece is at the pin. Measured on the pieces alone."""
    parts = rig["parts"]
    worst = (0.0, "")
    flat = (0.0, "")
    for n, p in parts.items():
        if not p.get("joint") or p.get("kind") in ("block", "head", "skirt"):
            continue
        ends = [(n, _local(rig, n, p["joint"]["at"]), True)]                 # the child's top end
        if parts[p["parent"]].get("kind") == "limb":
            ends.append((p["parent"], _local(rig, p["parent"], p["joint"]["parent_at"]), False))   # the parent's bottom end
        for part, (x, y), top in ends:
            m = masks[part]
            xi, yi = int(round(min(max(x, 0), m.shape[1] - 1))), int(round(min(max(y, 0), m.shape[0] - 1)))
            col = np.nonzero(m[:, xi])[0]
            if not len(col):
                continue
            reach = float(yi - col[0]) if top else float(col[-1] - yi)
            r = float(inscribed(m)[yi, xi])
            ratio = reach / max(r, 1.0)
            if ratio > worst[0]:
                worst = (ratio, f"{part} at the {p['joint']['name'].split('_')[0]}")
            # (only at an elbow or a knee: at a wrist or an ankle a flat end is a cuff, a trouser hem, a boot top,
            # and the hand or the foot comes out of it)
            if reach > 0.4 * r and p["joint"]["name"].split("_")[0] in ("elbow", "knee"):
                w = end_width(m, xi, yi, reach, top)
                if w is not None and w > flat[0]:
                    flat = (w, f"{part} at the {p['joint']['name'].split('_')[0]}")
    out["overhang"], out["overhang_at"] = round(worst[0], 2), worst[1]
    out["flat"], out["flat_at"] = round(flat[0], 2), flat[1]
    if flat[0] > FLAT_END:
        problems.append(f"the end of {flat[1]} is cut off flat ({flat[0]:.2f} of its width near the tip): its corners "
                        f"show when the joint bends")
    if worst[0] > OVERHANG:
        problems.append(f"the end of {worst[1]} sticks {worst[0]:.2f} half-widths past its pin (a knob when it bends)")


def measure_stance(rig, masks, out, problems):
    parts = rig["parts"]
    out["arms_over"] = round(max(arm_over_body(rig, masks, "l"), arm_over_body(rig, masks, "r")), 2)
    hl, hr = parts["thigh_l"]["joint"], parts["thigh_r"]["joint"]
    width = np.mean([span(masks[n], _local(rig, n, parts[n]["joint"]["at"])[1]) for n in ("thigh_l", "thigh_r")], axis=0)
    out["legs_apart"] = round((hr["parent_at"][0] - hl["parent_at"][0]) / max(width[1] - width[0], 1.0), 2)   # 1 = thighs touch
    sh = parts["upper_arm_l"]["joint"]
    top = sh["parent_at"][1] - (sh["at"][1] - parts["upper_arm_l"]["box"][1])      # the top of the arm piece, chest coords
    out["shoulder_top"] = round((top - parts["chest"]["box"][1]) / max(sh.get("radius", 28), 1.0), 2)   # radii under the chest top
    if rig.get("view") == "side":      # in profile the near arm hangs across the body and the legs are one behind the other
        return
    if out["arms_over"] > ARMS_OVER:
        problems.append(f"the arms hang in front of the body: {out['arms_over']:.0%} of an arm lies over it")
    if out["legs_apart"] > LEGS_APART:
        problems.append(f"the legs stand wide apart: {out['legs_apart']:.2f} thigh widths between the hips")


def measure_skirt(rig, masks, out, problems):
    parts = rig["parts"]
    shift = rest_shift(rig)

    def rows(n):       # world row -> (left, right) of part n in the rest pose
        b, (dx, dy) = parts[n]["box"], shift[n]
        res = {}
        for y, row in enumerate(masks[n]):
            xs = np.nonzero(row)[0]
            if len(xs):
                res[int(round(b[1] + dy + y))] = (b[0] + dx + xs[0], b[0] + dx + xs[-1])
        return res

    skirt, pelvis = rows("skirt"), rows("pelvis")
    hem = max(skirt)
    poke = 0.0
    for y, (l, r) in pelvis.items():
        if y > hem:
            poke = max(poke, float(r - l))          # the pelvis hangs out under a very short skirt
        elif y in skirt:
            poke = max(poke, float(skirt[y][0] - l), float(r - skirt[y][1]))
    out["skirt_poke"] = round(poke, 1)
    soles = [parts[n]["sole"][1] + shift[n][1] for n in parts if "sole" in parts[n]]
    hips = [parts[n]["joint"]["parent_at"][1] for n in parts if parts[n].get("joint") and parts[n]["joint"]["name"].startswith("hip")]
    floor, hip = max(soles), float(np.mean(hips))
    out["skirt_hem"] = round(floor - hem, 1)                       # > 0: the hem is above the floor
    out["skirt_len"] = round((hem - hip) / max(floor - hip, 1.0), 2)   # share of the leg, hip to sole, that it covers
    thigh = 0.0
    for n in ("thigh_l", "thigh_r"):
        for y, (l, r) in rows(n).items():
            if y in skirt:
                thigh = max(thigh, float(skirt[y][0] - l), float(r - skirt[y][1]))
    out["skirt_thigh"] = round(thigh, 1)                           # how far a thigh shows beside the skirt
    if poke > SKIRT_POKE:
        problems.append(f"the pelvis shows {poke:.0f} px from behind the skirt")
    if -out["skirt_hem"] > SKIRT_DRAG:
        problems.append(f"the skirt is {-out['skirt_hem']:.0f} px longer than the legs")
    want = rig.get("skirt_length")
    if want and abs(out["skirt_len"] - want) > SKIRT_LEN_TOL:
        problems.append(f"the skirt covers {out['skirt_len']:.0%} of the leg, its pattern asks for {want:.0%}")


def chin_row(mask, pin):
    """Walking up the head from its neck pin: the first row clearly wider than the neck is the chin (or the beard)."""
    s0 = span(mask, pin[1])
    if not s0:
        return None
    w0 = s0[1] - s0[0] + 1
    for y in range(int(pin[1]), -1, -1):
        s = span(mask, y)
        if s and s[1] - s[0] + 1 >= 1.6 * w0:
            return y
    return None


def bridge(rig, masks, n, angles=None):
    """The least paint around the pin of part `n` (px) while it swings through its limits: the inscribed radius of
    parent + child together, measured at the pin. Returns (worst value, angle of the worst)."""
    p = rig["parts"][n]
    parent = p["parent"]
    j = p["joint"]
    cx, cy = _local(rig, n, j["at"])
    px, py = _local(rig, parent, j["parent_at"])
    pm, cm = masks[parent], masks[n]
    reach = int(math.hypot(*cm.shape)) + 4
    canvas = np.zeros((pm.shape[0] + 2 * reach, pm.shape[1] + 2 * reach), np.uint8)
    canvas[reach:reach + pm.shape[0], reach:reach + pm.shape[1]] = filled(pm)
    pin = (px + reach, py + reach)
    lo, hi = p.get("limits") or (-30, 30)
    worst = (1e9, 0.0)
    for a in (angles or (lo, lo / 2, 0.0, hi / 2, hi)):
        r = math.radians(a)
        c, s = math.cos(r), math.sin(r)
        # child pixel (x, y) -> pin + R(a) * ((x, y) - child pin)
        m = np.array([[c, -s, pin[0] - c * cx + s * cy], [s, c, pin[1] - s * cx - c * cy]], np.float32)
        moved = cv2.warpAffine(filled(cm), m, (canvas.shape[1], canvas.shape[0]), flags=cv2.INTER_NEAREST)
        dt = cv2.distanceTransform(np.maximum(canvas, moved), cv2.DIST_L2, 5)
        v = float(dt[int(round(pin[1])), int(round(pin[0]))])
        if v < worst[0]:
            worst = (v, float(a))
    return worst


def _size(rig, masks, part):
    """A part's painted width and height, against the body's height (neck to sole)."""
    m = masks[part]
    ys, xs = np.nonzero(m)
    if not len(xs):
        return 0.0, 0.0
    bh = float(rig.get("body_height", 1.0))
    return (xs.max() - xs.min() + 1) / bh, (ys.max() - ys.min() + 1) / bh


def front_of(pdir):
    """The front puppet a view belongs to (<puppet>/side -> <puppet>), or None for a front puppet."""
    pdir = Path(pdir)
    if pdir.name in ("side", "back") and (pdir.parent / "rig.json").exists():
        return pdir.parent
    return None


def measure_views(pdir, rig, masks, out, problems):
    """A view against its own front view (nothing to do for a front view)."""
    front = front_of(pdir)
    if front is None:
        return
    frig, fmasks = load(front)
    view = rig.get("view", Path(pdir).name)
    hf, hv = _size(frig, fmasks, "head")[1], _size(rig, masks, "head")[1]
    cf, cv = _size(frig, fmasks, "chest")[0], _size(rig, masks, "chest")[0]
    out["head_vs_front"] = round(hv / max(hf, 1e-6), 2)
    out["chest_vs_front"] = round(cv / max(cf, 1e-6), 2)
    if not HEAD_SAME[0] <= out["head_vs_front"] <= HEAD_SAME[1]:
        problems.append(f"the head is {out['head_vs_front']:.2f} times as tall as in the front view: not the same character")
    if view == "side":
        want = DEPTH_HEAVY if cf >= HEAVY else DEPTH_MIN
        if out["chest_vs_front"] < want:
            problems.append(f"seen from the side the body is {out['chest_vs_front']:.2f} of its front width, at least {want} "
                            f"wanted{' (a heavy body)' if cf >= HEAVY else ''}: thinner than the character")
    elif view == "back" and not BACK_SAME[0] <= out["chest_vs_front"] <= BACK_SAME[1]:
        problems.append(f"from behind the body is {out['chest_vs_front']:.2f} of its front width: not the same character")


def measure(rig, masks):
    """All measurements of one puppet, and the list of defects they add up to."""
    parts = rig["parts"]
    out, problems = {}, []
    axes = {"pelvis": axis_x(masks["pelvis"]), "chest": axis_x(masks["chest"]), "head": head_axis(masks["head"])}
    width = {n: masks[n].shape[1] for n in axes}

    def off(part, pt):                 # a sheet point of `part`, relative to that part's centre line
        return _local(rig, part, pt)[0] - axes[part]

    head, chest = parts["head"], parts["chest"]
    out["neck_dx"] = round(off("chest", head["joint"]["parent_at"]), 1)
    out["waist_dx_chest"] = round(off("chest", chest["joint"]["at"]), 1)
    out["waist_dx_pelvis"] = round(off("pelvis", chest["joint"]["parent_at"]), 1)
    for key, block in (("neck_dx", "chest"), ("waist_dx_chest", "chest"), ("waist_dx_pelvis", "pelvis")):
        if abs(out[key]) > CENTRE_TOL * width[block]:
            problems.append(f"{key.split('_')[0]} pin is {out[key]:+.0f} px off the centre line of the {block}")

    # the rest pose is pure translation: a child stands at parent_at - at
    out["head_dx"] = round(out["neck_dx"] - off("head", head["joint"]["at"]), 1)
    out["chest_dx"] = round(out["waist_dx_pelvis"] - out["waist_dx_chest"], 1)
    if abs(out["head_dx"]) > STACK_TOL * width["chest"] * (4 if rig.get("view") == "side" else 1):   # a profile head leans forward
        problems.append(f"the head stands {out['head_dx']:+.0f} px off the chest's centre line")
    if abs(out["chest_dx"]) > STACK_TOL * width["pelvis"]:
        problems.append(f"the chest stands {out['chest_dx']:+.0f} px off the pelvis's centre line")

    for name, l, r in (("shoulders", "upper_arm_l", "upper_arm_r"), ("hips", "thigh_l", "thigh_r")):
        block = parts[l]["parent"]
        (lx, ly), (rx, ry) = (_local(rig, block, parts[k]["joint"]["parent_at"]) for k in (l, r))
        dx = (axes[block] - lx) - (rx - axes[block])       # > 0: the left pin is farther out
        out[f"{name}_dx"], out[f"{name}_dy"] = round(dx, 1), round(ly - ry, 1)
        if max(abs(dx), abs(ly - ry)) > PAIR_TOL * width[block]:
            problems.append(f"{name} are uneven: {dx:+.0f} px sideways, {ly - ry:+.0f} px in height")

    # the neck: how deep under the real neckline, and how much of it shows
    hp = _local(rig, "head", head["joint"]["at"])
    cp = _local(rig, "chest", head["joint"]["parent_at"])
    rho = float(inscribed(masks["head"])[int(round(hp[1])), int(round(hp[0]))])
    line = rest_edge(masks["chest"], axes["chest"], max(rho, 6.0), top=True)
    out["neck_r"] = round(rho, 1)
    out["neck_depth"] = round(cp[1] - line, 1)
    chin = chin_row(masks["head"], hp)
    out["neck_shown"] = None if chin is None else round((hp[1] - chin) - (cp[1] - line), 1)
    # the neck pin must be in the END of the neck: under it, in its column, the paint stops about a radius away
    col = np.nonzero(masks["head"][int(round(hp[1])):, int(round(hp[0]))])[0]
    tail = float(col[-1]) if len(col) else 0.0
    for i in range(1, len(col)):
        if col[i] != col[i - 1] + 1:           # the first break in the paint under the pin
            tail = float(col[i - 1])
            break
    out["neck_tail"] = round(tail, 1)
    if not NECK_TAIL[0] * rho <= tail <= NECK_TAIL[1] * rho:
        problems.append(f"the neck pin is not in the end of the neck: {tail:.0f} px of paint under it, neck radius {rho:.0f}")
    k = out["neck_depth"] / max(rho, 1.0)
    if not NECK_DEPTH[0] <= k <= NECK_DEPTH[1]:
        problems.append(f"the neck pin is {out['neck_depth']:.0f} px under the neckline ({k:.1f} neck radii)")

    worst = (1e9, "", 0.0)
    out["bridges"] = {}
    for n, p in parts.items():
        if p.get("joint"):
            v, a = bridge(rig, masks, n)
            out["bridges"][n] = round(v, 1)
            if v < worst[0]:
                worst = (v, n, a)
            if v < BRIDGE_MIN:
                problems.append(f"a gap at the {p['joint']['name']} pin: {v:.0f} px of paint at {a:+.0f} deg")
    out["bridge_min"], out["bridge_at"] = round(worst[0], 1), worst[1]
    if "skirt" in parts:
        measure_skirt(rig, masks, out, problems)
    measure_stance(rig, masks, out, problems)
    measure_overhang(rig, masks, out, problems)
    out["problems"] = problems
    return out


def rest_tile(rig, pdir, size=(420, 700)):
    pdir = Path(pdir)
    images = {n: Image.open(pdir / "parts" / f"{n}.png").convert("RGBA") for n in rig["parts"]}
    for n, p in rig["parts"].items():
        for v in p.get("variants", {}):
            images[f"{n}.{v}"] = Image.open(pdir / "parts" / f"{n}.{v}.png").convert("RGBA")
    return rigkit.render_pose(rig, images, {}, size=size, floor_y=size[1] - 30, body_px=int(size[1] * 0.56))


def audit(pdir) -> dict:
    """The measurements and problems of one puppet folder (its views are checked against the front)."""
    rig, masks = load(pdir)
    r = measure(rig, masks)
    measure_views(pdir, rig, masks, r, r["problems"])
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tadam.puppet.audit")
    ap.add_argument("dirs", nargs="+", help="puppet folders (with rig.json and parts/)")
    ap.add_argument("--montage")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    names = [Path(d) for d in a.dirs]
    cols = ("neck_dx", "head_dx", "waist_dx_chest", "chest_dx", "shoulders_dx", "shoulders_dy",
            "hips_dx", "hips_dy", "neck_r", "neck_depth", "neck_shown", "arms_over", "legs_apart", "overhang", "bridge_min", "bridge_at")
    short = ("neck", "head", "wst_c", "chest", "sh_dx", "sh_dy", "hip_dx", "hip_dy", "n_r", "n_dep", "n_shown", "arms", "legs", "overhng", "bridge", "at")
    print("%-10s " % "puppet" + " ".join("%7s" % s for s in short))
    results, tiles, bad = {}, [], 0
    for n in names:
        rig, masks = load(n)
        r = audit(n)
        label = n.name if front_of(n) is None else f"{n.parent.name}/{n.name}"
        results[label] = r
        print("%-10s " % label + " ".join("%7s" % ("-" if r[c] is None else r[c]) for c in cols))
        if "skirt_len" in r:
            print(f"     skirt: covers {r['skirt_len']:.0%} of the leg, hem {r['skirt_hem']:+.0f} px from the floor, "
                  f"pelvis shows {r['skirt_poke']:.0f} px, thigh shows {r['skirt_thigh']:.0f} px")
        for pr in r["problems"]:
            print("   !", pr)
        bad += bool(r["problems"])
        if a.montage:
            t = rest_tile(rig, n)
            d = ImageDraw.Draw(t)
            d.text((8, 6), label, fill=(0, 0, 0, 255))
            if r["problems"]:
                d.rectangle([0, 0, t.width - 1, t.height - 1], outline=(210, 40, 40, 255), width=4)
            tiles.append(t.convert("RGB"))
    print(f"\n{len(names) - bad} of {len(names)} puppets with no defects")
    if a.json:
        write_json(a.json, results, indent=1)
    if tiles:
        per = 8
        w, h = tiles[0].size
        sheet = Image.new("RGB", (w * min(per, len(tiles)), h * ((len(tiles) + per - 1) // per)), (246, 244, 240))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % per) * w, (i // per) * h))
        sheet.save(a.montage, quality=86)
        print("montage:", a.montage)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
