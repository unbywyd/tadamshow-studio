"""Cut a generated pattern sheet into parts AS PAINTED and derive this puppet's own skeleton from them.

usage: tadam.puppet.cut_skin.cut(<puppet folder>, rig=None)   (rig defaults to the pattern the sheet was painted
on: meta.json); also python -m tadam.puppet.cut_skin <puppet folder> [--rig R].
Reads <puppet>/sheet.png, writes <puppet>/{parts/<part>.png, rig.json, report.json, check.jpg}.

No AI here, and no stretching: every piece keeps its painted size, so a fat chef stays fat. The image model is
trusted with one thing: to paint the pieces as separate blobs in the same ARRANGEMENT as the pattern.
  1. find the painted blobs; tiny detached bits join the nearest big blob; if two pieces of one limb were painted
     as one (a shin with its foot, a forearm with its hand), the blob is cut at its narrowest row there and both
     halves keep a band of the other, so the joint has paint to turn on;
  2. match blobs to parts by their relative arrangement (optimal assignment on normalised centres);
  3. place the joints on the pieces themselves:
       limb ends, wrists, ankles -> the centre of the rounded end (largest inscribed circle there);
       the neck stub of the head -> the same, but only inside a corridor around the head's centre line,
       so a braid, a beard or a hat flap hanging lower than the neck cannot take the pin;
       neck and waist on the body blocks -> on the block's own centre line, measured from the block's REAL edge
       there (a collar dip or a vest notch moves the pin with it); the neck pin sits only a little under the
       neckline, so the neck shows and the head is not sunk into the chest;
       shoulders -> a little OUTSIDE the chest's side edge and well under its top, so the arms hang beside the
       body with the shoulders down, not in front of the chest with the shoulders up;
       hips -> at the pattern's height, side by side under the middle of the pelvis: the legs stand together;
       in a PROFILE puppet (pattern "view": "side") both shoulders are one point on the chest's centre line and
       both hips one point on the pelvis's, and there is no rest stance to work out;
  3b. the rest stance: the arms are turned outward at the shoulder just enough to hang clear of the body
       (rig "rest": joint angles of the neutral pose);
  3c. second drawings of a part ("variants"): if <puppet>/hands.png exists (gen_hands.py), its two
       palms become the "palm" variant of hand_l and hand_r, each fitted to the puppet's own hand (the same length
       from the wrist pin to the fingertips) and pinned by its own wrist;
       if <puppet>/mouth_open.png exists (gen_mouth.py), the head gets the variant "open": its own
       picture with only the mouth taken from the new one (mouth.py);
       a skirt -> its waistband on the top edge of the pelvis, both on their own centre lines. A skirt is a garment,
       not a body part: the model paints it at its own scale, so it is FITTED as a whole (never stretched): to the
       length its pattern asks for, but big enough to hide the pelvis and small enough to end above the floor;
  4. write the puppet's rig (same schema as the pattern rig, its own boxes and joints) and check it with
     audit.py, which measures the assembled puppet without knowing how the pins were chosen.
"""
import argparse
import copy
import itertools
import json
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.optimize import linear_sum_assignment

from tadam import imgio
from tadam.puppet import audit, mouth, rigkit, wear
from tadam.puppet.audit import axis_x, inscribed
SPECK = 40            # blobs smaller than this many pixels are noise
DETAIL = 0.10         # a blob smaller than this share of the median piece is a detached detail
R_MIN = 11            # a joint needs at least this much paint around it (pixels), or the limb is too thin there
SIDE_RATIO = 1.3      # left and right limbs may differ in length by this factor before we warn
END_BAND = {"limb": 0.40, "hand": 0.30, "foot": 0.30, "head": 0.16}
END_ROUND = 0.92      # a row is still "in the rounded end" while its inscribed radius is this share of its depth


def clean_alpha(rgba):
    """The model never writes alpha 255 and leaves a faint haze: snap both ends."""
    a = rgba[..., 3].astype(np.int32)
    a[a >= 240] = 255
    a[a <= 12] = 0
    out = rgba.copy()
    out[..., 3] = a.astype(np.uint8)
    return out


def find_blobs(solid, want):
    """Connected components -> `want` big blobs (label lists), with small detached details attached to the nearest one."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(solid.astype(np.uint8), connectivity=8)
    ids = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= SPECK]
    if not ids:
        return labels, [], "nothing painted"
    ids.sort(key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    median = float(np.median([stats[i, cv2.CC_STAT_AREA] for i in ids[:want]]))
    big = [i for i in ids if stats[i, cv2.CC_STAT_AREA] >= DETAIL * median]
    groups = {i: [i] for i in big}

    def gap(i, j):   # distance between bounding boxes
        ax, ay, aw, ah = stats[i, :4]
        bx, by, bw, bh = stats[j, :4]
        return float(np.hypot(max(bx - (ax + aw), ax - (bx + bw), 0), max(by - (ay + ah), ay - (by + bh), 0)))

    for s in (i for i in ids if i not in big):
        groups[min(big, key=lambda b: gap(s, b))].append(s)
    note = None if len(big) == want else f"found {len(big)} separate pieces, expected {want}"
    return labels, list(groups.values()), note


def unmerge(masks, boxes, names, bparts, slot_boxes):
    """Fewer blobs than pieces: find which neighbours of one limb were painted as one blob, and cut them apart.
    Every limb (upper arm - forearm - hand, thigh - shin - foot) may have come as three pieces, as its upper two in
    one, its lower two in one, or all three in one; every combination that accounts for the missing pieces is
    tried and the one whose blobs sit most like the pattern is kept. Returns (masks in pattern order, notes) or None."""
    missing = len(names) - len(masks)
    limbs = []
    for n in names:                                    # a limb = a part with a limb parent that is itself a limb's child
        par = bparts[n].get("parent")
        if par and bparts[par]["kind"] == "limb" and bparts[par].get("parent") and bparts[bparts[par]["parent"]]["kind"] != "limb" \
                and bparts[n]["kind"] == "limb":
            end = next((c for c in names if bparts[c].get("parent") == n), None)
            if end:
                limbs.append((par, n, end))
    slot = dict(zip(names, slot_boxes))
    options = [[(), (l[0], l[1]), (l[1], l[2]), l] for l in limbs]
    best = None
    for combo in itertools.product(*options):
        groups = [g for g in combo if g]
        if sum(len(g) - 1 for g in groups) != missing:
            continue
        used = {n for g in groups for n in g}
        keys = [n for n in names if n not in used] + groups
        slots = [slot[k] if isinstance(k, str) else
                 (min(slot[n][0] for n in k), slot[k[0]][1], max(slot[n][2] for n in k), slot[k[-1]][3]) for k in keys]
        pairing, residual = match(boxes, slots)
        if best is None or residual < best[0]:
            best = (residual, keys, slots, pairing)
    if best is None or best[0] > 0.12:
        return None
    _, keys, slots, pairing = best
    blob_of = {keys[si]: bi for bi, si in pairing.items()}
    made, notes = {}, []
    for k in keys:
        m = masks[blob_of[k]]
        if isinstance(k, str):
            made[k] = m
            continue
        x0, y0, x1, y1 = boxes[blob_of[k]]
        h = y1 - y0
        u = slots[keys.index(k)]
        cuts = []                                      # (row, band) between every two neighbours in the blob
        for upper, lower in zip(k, k[1:]):
            share = ((slot[upper][3] + slot[lower][1]) / 2 - u[1]) / (u[3] - u[1])     # where the pattern has the gap
            rows = range(y0 + int((share - 0.12) * h), y0 + int((share + 0.12) * h) + 1)
            widths = {y: int(np.count_nonzero(m[y])) for y in rows if y0 < y < y1 - 1}
            narrow = min(widths.values())
            cut = min((y for y, w in widths.items() if w <= narrow + 2), key=lambda y: abs(y - (y0 + share * h)))
            # Each of the two pieces ends in a HALF DISC around the middle of the cut, as wide as the limb is there.
            # The joint is pinned in that middle, so the two discs stay one on the other however the joint bends:
            # no square corner sticks out and no gap opens. A straight cut looks like a broken stick.
            xs = np.nonzero(m[cut])[0]
            cuts.append((cut, (xs.min() + xs.max()) / 2.0, (xs.max() - xs.min() + 1) / 2.0))
        yy, xx = np.ogrid[:m.shape[0], :m.shape[1]]
        for i, n in enumerate(k):
            piece = m.copy()
            if i > 0:
                cy, cx, r = cuts[i - 1]
                piece &= (yy >= cy) | ((xx - cx) ** 2 + (yy - cy) ** 2 <= r * r)
            if i < len(k) - 1:
                cy, cx, r = cuts[i]
                piece &= (yy <= cy) | ((xx - cx) ** 2 + (yy - cy) ** 2 <= r * r)
            made[n] = piece
        notes.append(" and ".join(k) + " were painted as one piece: cut apart at row " + ", ".join(str(c[0]) for c in cuts)
                     + ", the ends rounded")
    return [made[n] for n in names], notes


def trim_grown_ends(masks, boxes, names, bparts, blob_of):
    """A forearm painted WITH A HAND on its end (or a shin with a foot), although the hand is a piece of its own:
    the model did not keep to the pattern. Pinned to such a piece, the real hand hangs after the painted one: two
    hands in a row. The sign is in the outline: the piece is much longer than the one above it (a forearm is about
    as long as an upper arm), and near its far end it narrows to a neck (the wrist) and widens again (the hand).
    Everything past the neck is cut off, the end rounded like every cut limb. Returns notes."""
    notes = []
    for n in names:
        par = bparts[n].get("parent")
        if not par or bparts[n]["kind"] != "limb" or bparts[par]["kind"] != "limb":
            continue                                    # only the middle piece of a limb: forearm, shin
        if not any(bparts[c].get("parent") == n for c in names):
            continue
        m = masks[blob_of[n]]
        x0, y0, x1, y1 = boxes[blob_of[n]]
        ux0, uy0, ux1, uy1 = boxes[blob_of[par]]
        h = y1 - y0
        if os.environ.get("CUT_DEBUG"):
            print("TRIM?", n, "h", h, "upper", uy1 - uy0)
        if h < 1.15 * (uy1 - uy0):
            continue
        widths = np.array([np.count_nonzero(m[y]) for y in range(y0, y1)], float)
        k = max(3, h // 40)
        smooth = np.convolve(widths, np.ones(k) / k, mode="same")
        lo, hi = int(0.45 * h), int(0.9 * h)
        neck = lo + int(np.argmin(smooth[lo:hi]))
        after = smooth[neck:h - k]
        if os.environ.get("CUT_DEBUG"):
            print("  neck", neck, "width %.0f" % smooth[neck], "after rows", len(after), "bulge %.2f" % (after.max() / max(smooth[neck], 1) if len(after) else 0))
        # (a hand or a foot is at least half again as long as the wrist is wide; a frill or a cuff at the end is short)
        if len(after) < 1.5 * smooth[neck] or after.max() < 1.25 * smooth[neck]:
            continue                                    # no hand after it: a long sleeve, a long glove, a frill
        cy = y0 + neck
        xs = np.nonzero(m[cy])[0]
        cx, r = (xs.min() + xs.max()) / 2.0, (xs.max() - xs.min() + 1) / 2.0
        yy, xx = np.ogrid[:m.shape[0], :m.shape[1]]
        m &= (yy <= cy) | ((xx - cx) ** 2 + (yy - cy) ** 2 <= r * r)
        boxes[blob_of[n]] = bbox_of(m)
        end = next(c for c in names if bparts[c].get("parent") == n)
        notes.append(f"{n} was painted with a {end.split('_')[0]} on its end: cut off at its neck (row {cy}), the end rounded")
    return notes


def bbox_of(mask):
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def match(blob_boxes, slot_boxes):
    """Optimal blob->slot assignment on centres normalised by each set's own mean and spread."""
    def norm(boxes):
        c = np.array([[(x0 + x1) / 2, (y0 + y1) / 2] for x0, y0, x1, y1 in boxes], float)
        return (c - c.mean(0)) / (c.std(0) + 1e-6)
    a, b = norm(blob_boxes), norm(slot_boxes)
    cost = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)
    rows, cols = linear_sum_assignment(cost)
    return dict(zip(rows.tolist(), cols.tolist())), float(cost[rows, cols].mean())


def end_joint(dt, top, band, corridor=None):
    """Centre of the rounded end of a piece: the deepest point whose inscribed circle still touches the tip. `corridor` = (x0, x1) says which columns the end is in: the tip is
    the last paint THERE, so something hanging lower beside it is not taken for the end. In the chosen row the
    centre is then followed uphill, so an end that is a little off the corridor is still centred.
    Returns (x, y, radius) in the piece's own pixels."""
    h, w = dt.shape
    x0, x1 = (0, w) if corridor is None else (max(int(corridor[0]), 0), min(int(corridor[1]) + 1, w))
    d = dt[:, x0:x1]
    rows = [r for r in (range(h) if top else range(h - 1, -1, -1)) if d[r].max() > 0]   # from the tip of what is there
    rows = rows[:max(int(h * band), 3)]
    rowmax = np.array([d[r].max() for r in rows])
    # The pin goes in the MIDDLE OF THE ROUNDED END: the deepest row whose inscribed circle still reaches the tip
    # (its radius is as large as its depth). Deeper than that the end would stick out past the pin like a knob
    # when the joint bends. A thin tip (a tassel, a frayed edge) is skipped: the end starts where the piece is thick.
    start = int(np.argmax(rowmax >= 0.35 * rowmax.max()))
    tip = start - rowmax[start]
    deep = [i for i in range(start, len(rows)) if rowmax[i] >= END_ROUND * (i - tip)]
    r = rows[max(deep) if deep else start]
    xs = np.nonzero(d[r] >= 0.97 * d[r].max())[0]
    if corridor is None:
        return float(x0 + xs.mean()), float(r), float(d[r].max())
    x = int(round(x0 + xs.mean()))
    row = dt[r]
    while True:                                   # uphill along the row to the ridge of this end
        nxt = max((c for c in (x - 1, x + 1) if 0 <= c < w), key=lambda c: row[c])
        if row[nxt] <= row[x]:
            break
        x = nxt
    top_xs = [c for c in range(max(x - int(row[x]), 0), min(x + int(row[x]) + 1, w)) if row[c] >= 0.97 * row[x]]
    return float(np.mean(top_xs)), float(r), float(row[x])


def edge_row(solid, x, half, top):
    """The block's real edge near the column x: the median over the columns x-half..x+half of the first (last)
    painted row. The median ignores a narrow notch and a narrow bump alike."""
    w = solid.shape[1]
    rows = []
    for c in range(max(int(round(x - half)), 0), min(int(round(x + half)) + 1, w)):
        ys = np.nonzero(solid[:, c])[0]
        if len(ys):
            rows.append(ys[0] if top else ys[-1])
    return float(np.median(rows)) if rows else (0.0 if top else float(solid.shape[0] - 1))


def centre_joint(solid, dt, top, depth, half):
    """A neck or waist pin on a body block: on the block's centre line, `depth` px inside its real top (bottom)
    edge. Never moved sideways, and never moved to find paint: a cut-out narrower than the band is covered by the
    piece that sits there. The radius is the most paint found at that height inside the band."""
    h, w = solid.shape
    x = axis_x(solid)
    edge = edge_row(solid, x, half, top)
    y = int(round(min(max(edge + depth if top else edge - depth, 0), h - 1)))
    x0, x1 = max(int(round(x - half)), 0), min(int(round(x + half)) + 1, w)
    return float(x), float(y), float(dt[y, x0:x1].max())


def side_joint(dt, v, side, r_child, k, drop=0.0):
    """A shoulder or a hip: hung from the block's real EDGE at that height, `k` limb-radii inside it, so the limb
    sticks out a little past the body outline. Walks towards the middle of the block until the paint is solid
    (rounded corners). Returns (x, y, radius) or None."""
    h, w = dt.shape
    y0 = int(round(v * (h - 1)))
    if drop:                                  # a shoulder: the top of the sleeve sits a little below the shoulder line
        y0 = max(y0, int(round(drop * r_child)))
    step = 1 if v < 0.5 else -1
    for d in range(int(0.25 * h) + 1):
        y = y0 + step * d
        if not 0 <= y < h:
            break
        xs = np.nonzero(dt[y] > 0)[0]
        if len(xs) < 4:
            continue
        xl, xr = int(xs.min()), int(xs.max())
        inset = min(max(k * r_child, 8.0), 0.3 * (xr - xl))
        x = int(round(xl + inset if side < 0 else xr - inset))
        if dt[y, x] >= 0.7 * inset:
            return float(x), float(y), float(dt[y, x])
    return None


HAND_SHEETS = {"palm": "hands.png", "fist": "hands_fist.png"}


def same_colour(piece, like):
    """A fist painted in another colour than the hand it replaces (a white fist for a dark glove: the model took the
    palm's colour) is brought to the hand's colour: the mean and the spread of its Lab colours become the hand's.
    Left alone when the two are close already (their means under 18 apart)."""
    if like is None:
        return piece
    a, b = piece[..., 3] > 128, like[..., 3] > 128
    if a.sum() < 50 or b.sum() < 50:
        return piece
    lab_p = cv2.cvtColor(piece[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    lab_l = cv2.cvtColor(like[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    mp, ml = lab_p[a].mean(axis=0), lab_l[b].mean(axis=0)
    if np.linalg.norm(mp - ml) < 18:
        return piece
    sp, sl = lab_p[a].std(axis=0) + 1e-3, lab_l[b].std(axis=0) + 1e-3
    out = (lab_p - mp) * np.clip(sl / sp, 0.6, 1.6) + ml
    rgb = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    piece = piece.copy()
    piece[..., :3] = rgb
    return piece


def hand_variants(pdir, parts, pad, images):
    """Cuts the second drawings of the hands: the open palm (hands.png) and the gripping fist (hands_fist.png).
    Returns (notes, problems); on a problem the puppet simply lacks that drawing. A variant is an image of its own:
    parts[hand]["variants"][kind] = {"size": [w, h], "at": [x, y]} where `at` is the wrist pin in that image
    (without the pad). A palm is fitted by its length (wrist pin to fingertips, like the hand's own); a fist is
    shorter than a hand by nature, so it is fitted by the thickness of its wrist, and made at least as wide as the
    hand it replaces or the forearm's end (the narrower)."""
    notes, problems = [], []
    for hand in ("hand_l", "hand_r"):
        parts[hand].pop("variants", None)
        for kind in HAND_SHEETS:
            (pdir / "parts" / f"{hand}.{kind}.png").unlink(missing_ok=True)
    for kind, sheet in HAND_SHEETS.items():
        src = pdir / sheet
        if not src.exists():
            continue
        rgba = clean_alpha(np.array(Image.open(src).convert("RGBA")))
        labels, groups, note = find_blobs(rgba[..., 3] > 128, 2)
        if len(groups) != 2:
            problems.append(f"{sheet}: {note}")
            continue
        masks = [np.isin(labels, g) for g in groups]
        boxes = [bbox_of(m) for m in masks]
        made, bad = {}, []
        for hand, i in zip(("hand_l", "hand_r"), sorted(range(2), key=lambda i: boxes[i][0] + boxes[i][2])):
            x0, y0, x1, y1 = boxes[i]
            crop = rgba[y0:y1, x0:x1].copy()
            crop[~masks[i][y0:y1, x0:x1]] = 0
            p = parts[hand]
            _, cy, cr = end_joint(inscribed(crop[..., 3] > 128), top=True, band=END_BAND["hand"])
            if kind == "fist":
                k = p["joint"]["radius"] / max(cr, 1.0)                      # the same wrist
                # ...but never narrower than what it has to cover: the hand's own width or the end of the forearm
                # (the narrower of the two). A model that paints the wrist cap big gives a tiny fist otherwise, and
                # the forearm's round end shows round it like a second hand.
                fore = images.get("forearm_" + hand[-1])
                cover = float(p["box"][2])
                if fore is not None:
                    solid = np.array(fore)[..., 3] > 128
                    rows = np.where(solid.any(axis=1))[0]
                    if len(rows):
                        lo = int(rows.max() - 0.25 * (rows.max() - rows.min()))
                        cover = min(cover, float(max(solid[y].sum() for y in range(lo, rows.max() + 1))))
                k = max(k, 0.95 * cover / max(crop.shape[1], 1.0))
            else:
                own = p["box"][1] + p["box"][3] - p["joint"]["at"][1]        # the same length, wrist pin to fingertips
                k = own / max(crop.shape[0] - cy, 1.0)
            crop = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
            if kind == "fist":
                crop = same_colour(crop, np.array(images[hand]) if hand in images else None)
            cx, cy, cr = end_joint(inscribed(crop[..., 3] > 128), top=True, band=END_BAND["hand"])
            ratio = cr / max(p["joint"]["radius"], 1.0)
            if not PALM_WRIST[0] <= ratio <= PALM_WRIST[1]:
                bad.append(f"{sheet}: the {kind} of {hand} has a wrist {ratio:.2f}x as thick as the hand's own")
            made[hand] = (crop, cx, cy)
        if bad:
            problems += bad
            continue
        for hand, (crop, cx, cy) in made.items():
            frame = np.zeros((crop.shape[0] + 2 * pad, crop.shape[1] + 2 * pad, 4), np.uint8)
            frame[pad:pad + crop.shape[0], pad:pad + crop.shape[1]] = crop
            images[f"{hand}.{kind}"] = Image.fromarray(frame, "RGBA")
            images[f"{hand}.{kind}"].save(pdir / "parts" / f"{hand}.{kind}.png")
            parts[hand].setdefault("variants", {})[kind] = {"size": [crop.shape[1], crop.shape[0]], "at": [round(cx, 1), round(cy, 1)]}
        notes.append("the hands have a palm side" if kind == "palm" else "the hands can close into a fist")
    return notes, problems


def shoulder_joint(solid, side, r, out, drop):
    """A shoulder pin: `drop` arm radii under the top of the chest, `out` arm radii OUTSIDE the chest's side edge at
    that height (the edge is the median over one radius of rows, so a rounded corner or a frill does not move it).
    The pin may lie off the chest: the arm's own rounded top covers it. Returns (x, y)."""
    h = solid.shape[0]
    y0 = min(int(round(drop * r)), h - 1)
    edges = []
    for y in range(y0, min(y0 + max(int(r), 4), h)):
        xs = np.nonzero(solid[y])[0]
        if len(xs):
            edges.append(xs[0] if side < 0 else xs[-1])
    if not edges:
        return None
    edge = float(np.median(edges))
    return (edge - out * r if side < 0 else edge + out * r), float(y0)


def skirt_scale(skirt, pelvis_mask):
    """How much to enlarge a skirt so that, hung by its waistband, it hides the pelvis: at every height of the pelvis
    the skirt must be SKIRT_COVER times as wide. 1.0 if it already is."""
    ys, xs = np.nonzero(pelvis_mask)
    pelvis = pelvis_mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    need = 1.0
    for y in range(0, min(pelvis.shape[0], int(0.9 * skirt.shape[0])), 4):   # not the hem itself: it curves and frays
        pw = np.count_nonzero(pelvis[y])
        sw = max(np.count_nonzero(r) for r in skirt[y:y + 12])       # the edge of a waistband is never clean
        if pw and sw:
            need = max(need, SKIRT_COVER * pw / sw)
    return need


def neck_corridor(axis, width):
    half = max(NECK_CORRIDOR * width, 8.0)
    return axis - half, axis + half


SIDE_INSET = {"shoulder": 0.15, "hip": 0.75}   # how deep inside the body edge the limb is pinned, in limb radii
SIDE_DROP = {"shoulder": 1.3, "hip": 0.0}      # how far below the top of the block, in limb radii (0 = pattern height)
SHOULDER_OUT = 0.25       # a shoulder pin is this many arm radii outside the chest's side edge
SHOULDER_DROP = 1.6       # ... and this many arm radii under the top of the chest (the arm's top: 0.6 radii under)
SHOULDER_DROP_SIDE = 1.3  # the same in a profile puppet, where the shoulder is in the middle of the chest
HIP_GAP = 0.1             # the thighs stand this share of a thigh radius apart
NECK_SINK = 0.2           # the neck pin sits this many neck radii under the neckline
ARM_CLEAR = 0.12          # at rest at most this share of a hanging arm may lie over the body
PALM_WRIST = (0.6, 1.6)   # a palm's wrist may be this much thinner or thicker than the hand's own wrist
ARM_SPREAD_IN = 12        # degrees: the most it turns an arm inward, towards the body
ARM_SPREAD_MAX = 14       # degrees: the most the rest stance turns an arm outward to get there
SKIRT_COVER = 1.06        # a skirt is at least this much wider than the pelvis, at every height of the pelvis
SKIRT_CLEAR = 6           # px a floor-length hem stays above the soles
SKIRT_FIT = (0.55, 1.6)   # a skirt that needs more shrinking or enlarging than this was painted wrong
SKIRT_TRIM = 0.2          # at most this share of the pelvis may be trimmed away to hide it under the skirt
NECK_CORRIDOR = 0.08      # the neck stub is the paint on the head's centre line: this share of its width either side
WAIST_BAND = 0.2          # the waist edge is read over this share of the block's width either side of the centre line


def cut(pdir, rig_name=None, log=print) -> dict:
    """Cut <pdir>/sheet.png into a puppet; returns the report (also written to <pdir>/report.json)."""
    pdir = Path(pdir)
    name = pdir.name if audit.front_of(pdir) is None else f"{pdir.parent.name}/{pdir.name}"
    meta = json.loads((pdir / "meta.json").read_text(encoding="utf-8")) if (pdir / "meta.json").exists() else {}
    base = rigkit.load_rig(rig_name or meta.get("rig") or "humanoid-a")
    sheet = Image.open(pdir / "sheet.png").convert("RGBA")
    W, H = base["sheet"]
    if sheet.size != (W, H):
        sheet = sheet.resize((W, H), Image.LANCZOS)
    rgba = clean_alpha(np.array(sheet))
    solid = rgba[..., 3] > 128
    pad = base["pad"]
    bparts = base["parts"]
    names = list(bparts)
    shape_box = {n: bparts[n].get("shape_box", bparts[n]["box"]) for n in names}
    slot_boxes = [(b[0], b[1], b[0] + b[2], b[1] + b[3]) for b in (shape_box[n] for n in names)]

    def rel(n, pt):   # a pattern point as a fraction of that part's pattern shape
        b = shape_box[n]
        return (pt[0] - b[0]) / b[2], (pt[1] - b[1]) / b[3]

    labels, groups, note = find_blobs(solid, len(names))
    sheet_problems = [note] if note else []
    masks = [np.isin(labels, g) for g in groups]
    boxes = [bbox_of(m) for m in masks]
    repairs = []
    if 0 < len(names) - len(masks) <= 8:
        fixed = unmerge(masks, boxes, names, bparts, slot_boxes)
        if fixed:
            masks, repairs = fixed
            boxes = [bbox_of(m) for m in masks]
            sheet_problems = []
    if len(masks) != len(names):
        summary = {"name": name, "passed": False, "sheet_problems": sheet_problems, "parts": {}}
        (pdir / "report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        al = rgba[..., 3:4].astype(float) / 255
        vis = cv2.cvtColor((rgba[..., :3] * al + np.array([236, 236, 236]) * (1 - al)).astype(np.uint8), cv2.COLOR_RGB2BGR)
        for x0, y0, x1, y1 in boxes:
            cv2.rectangle(vis, (x0, y0), (x1, y1), (40, 40, 220), 2)
        imgio.imwrite(str(pdir / "check.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 86])
        log(f"{name}: FAIL - {note}")
        return summary
    pairing, residual = match(boxes, slot_boxes)
    blob_of = {names[slot]: blob for blob, slot in pairing.items()}
    if residual > 0.12:
        sheet_problems.append(f"pieces are not arranged like the pattern (residual {residual:.2f})")
    repairs += trim_grown_ends(masks, boxes, names, bparts, blob_of)

    # every piece as painted: its box is its own bounding box, its texture that box grown by pad
    rig = copy.deepcopy(base)
    rig["rig"] = base["rig"] + "/fitted"
    rig["puppet"] = name
    parts = rig["parts"]
    dts, images, solids = {}, {}, {}
    (pdir / "parts").mkdir(exist_ok=True)
    painted = {}

    def set_piece(n, crop):
        """The texture of part n (its box keeps its corner on the sheet and takes the size of `crop`)."""
        parts[n]["box"][2:] = [crop.shape[1], crop.shape[0]]
        solids[n] = audit.filled(crop[..., 3] > 128).astype(bool)
        dts[n] = inscribed(crop[..., 3] > 128)
        frame = np.zeros((crop.shape[0] + 2 * pad, crop.shape[1] + 2 * pad, 4), np.uint8)
        frame[pad:pad + crop.shape[0], pad:pad + crop.shape[1]] = crop
        images[n] = Image.fromarray(frame, "RGBA")
        images[n].save(pdir / "parts" / f"{n}.png")

    for n in names:
        m = masks[blob_of[n]]
        x0, y0, x1, y1 = boxes[blob_of[n]]
        parts[n]["box"] = [x0, y0, x1 - x0, y1 - y0]
        parts[n].pop("shape_box", None)
        crop = rgba[y0:y1, x0:x1].copy()
        crop[~m[y0:y1, x0:x1]] = 0
        painted[n] = crop
        set_piece(n, crop)

    def to_sheet(n, pt):
        return [round(parts[n]["box"][0] + pt[0], 1), round(parts[n]["box"][1] + pt[1], 1)]

    # joints: the child's own end, and the matching point on the parent
    report = {n: {"ok": True, "problems": []} for n in names}
    for n in names:
        p, bp = parts[n], bparts[n]
        if not p.get("joint"):
            u, v = rel(n, bp["origin"])
            p["origin"] = to_sheet(n, (u * (p["box"][2] - 1), v * (p["box"][3] - 1)))
            continue
        kind, parent = p["kind"], p["parent"]
        jname = bp["joint"]["name"]
        hc, wc = solids[n].shape
        hp_, wp_ = solids[parent].shape
        centre = parts[parent]["kind"] == "block" and not any(jname.startswith(k) for k in SIDE_INSET)
        if kind == "skirt":                                    # the waistband: as deep under its top as the pin is
            depth = rel(parent, bp["joint"]["parent_at"])[1] * hp_   # under the top of the pelvis, so the tops meet
            cx, cy, cr = centre_joint(solids[n], dts[n], top=True, depth=depth, half=WAIST_BAND * wc)
        elif kind == "block":                                  # chest on the pelvis: its own bottom edge
            v = rel(n, bp["joint"]["at"])[1]
            cx, cy, cr = centre_joint(solids[n], dts[n], top=False, depth=(1 - v) * hc, half=WAIST_BAND * wc)
        elif kind == "head":                                   # the head sits on its neck stub, under its own centre line
            ax = audit.head_axis(solids[n])
            cx, cy, cr = end_joint(dts[n], top=False, band=END_BAND[kind], corridor=neck_corridor(ax, wc))
        else:                                                  # limbs, hands, feet hang from their top
            cx, cy, cr = end_joint(dts[n], top=True, band=END_BAND[kind])
        if centre:                                             # neck on the chest, waist on the pelvis
            v = rel(parent, bp["joint"]["parent_at"])[1]
            depth = NECK_SINK * cr if kind == "head" else v * hp_
            px, py, pr = centre_joint(solids[parent], dts[parent], top=True, depth=depth,
                                      half=cr if kind == "head" else WAIST_BAND * wp_)
            pr = max(pr, cr) if kind == "head" else pr         # the neck stub covers its own pin
        elif parts[parent]["kind"] == "block":                 # shoulders and hips
            u, v = rel(parent, bp["joint"]["parent_at"])
            side = next(kk for kk in SIDE_INSET if jname.startswith(kk))
            sign = -1 if u < 0.5 else 1
            if base.get("view") == "side":        # seen from the side, left and right are the same point
                hung = (axis_x(solids[parent]), min(SHOULDER_DROP_SIDE * cr, 0.4 * hp_) if side == "shoulder" else v * (hp_ - 1))
            elif side == "shoulder":
                hung = shoulder_joint(solids[parent], sign, cr, SHOULDER_OUT, SHOULDER_DROP)
            else:
                hung = side_joint(dts[parent], v, sign, cr, SIDE_INSET[side], SIDE_DROP[side])
                if hung:                          # the legs together: side by side under the middle of the pelvis
                    mid = axis_x(solids[parent])
                    hung = (mid + sign * min(abs(hung[0] - mid), cr * (1 + HIP_GAP)), hung[1])
            px, py = hung[:2] if hung else (u * (wp_ - 1), v * (hp_ - 1))
            pr = cr if hung else 0.0              # pinned by the limb's own disc, which covers the joint
        else:
            px, py, pr = end_joint(dts[parent], top=False, band=END_BAND["limb"])
        p["joint"] = {"name": bp["joint"]["name"], "parent_at": to_sheet(parent, (px, py)), "at": to_sheet(n, (cx, cy)),
                      "radius": round(min(cr, pr), 1)}
        if cr < R_MIN:
            report[n]["problems"].append(f"too thin at the {bp['joint']['name']} joint ({cr:.0f} px)")
        if pr < R_MIN:
            report[parent]["problems"].append(f"too thin at the {bp['joint']['name']} joint ({pr:.0f} px)")

    # a skirt is fitted to the body it hangs on, now that the legs are known
    if "skirt" in parts:
        sk, j = parts["skirt"], parts["skirt"]["joint"]
        depth = j["at"][1] - sk["box"][1]                       # the pin's depth under the waistband, kept as it is
        shift = audit.rest_shift(rig)
        floor = max(parts[n]["box"][1] + rel(n, bparts[n]["sole"])[1] * (parts[n]["box"][3] - 1) + shift[n][1]
                    for n in names if "sole" in bparts[n])      # the soles in the rest pose (the helper points come later)
        room = floor - SKIRT_CLEAR - (j["parent_at"][1] - depth)   # from the top of the waistband to just above the floor
        k_min = skirt_scale(painted["skirt"][..., 3] > 128, masks[blob_of["pelvis"]])
        k_max = room / painted["skirt"].shape[0]
        k = 1.0
        if base.get("skirt_length"):               # the length this pattern asks for: a share of the leg, hip to sole
            hip = float(np.mean([parts[n]["joint"]["parent_at"][1] for n in names
                                 if parts[n].get("joint") and parts[n]["joint"]["name"].startswith("hip")]))
            want = hip - (j["parent_at"][1] - depth) + base["skirt_length"] * (floor - hip)
            k = want / painted["skirt"].shape[0]
        # With a wanted length, the length wins: the skirt of one character must be equally long from every side.
        # What then shows of the pelvis beside a narrow skirt is trimmed away below (up to SKIRT_TRIM of it).
        k = min(k if base.get("skirt_length") else max(k, k_min), k_max)
        # if the floor wins over the pelvis here, the audit below says how much of the pelvis shows
        if not SKIRT_FIT[0] <= k <= SKIRT_FIT[1]:
            sheet_problems.append(f"the skirt was painted at the wrong size: it needs {k:.2f}x to fit")
        if abs(k - 1.0) > 0.01:
            set_piece("skirt", cv2.resize(painted["skirt"], None, fx=k, fy=k,
                                          interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC))
            cx, cy, cr = centre_joint(solids["skirt"], dts["skirt"], top=True, depth=depth,
                                      half=WAIST_BAND * solids["skirt"].shape[1])
            j["at"] = to_sheet("skirt", (cx, cy))
        sk["fitted_scale"] = round(k, 3)

        # what is under a skirt must not show beside it: the pelvis is trimmed to the skirt's outline (rest pose)
        pv = parts["pelvis"]
        dx = int(round(sk["box"][0] + j["parent_at"][0] - j["at"][0] - pv["box"][0]))
        dy = int(round(sk["box"][1] + j["parent_at"][1] - j["at"][1] - pv["box"][1]))
        cover = np.zeros(solids["pelvis"].shape, bool)
        sm = cv2.erode(solids["skirt"].astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        ys, xs = np.nonzero(sm)
        keep = (ys + dy >= 0) & (ys + dy < cover.shape[0]) & (xs + dx >= 0) & (xs + dx < cover.shape[1])
        cover[ys[keep] + dy, xs[keep] + dx] = True
        hem = dy + sm.shape[0]
        cover[max(hem, 0):] = True                 # below a short skirt the pelvis stays as it is
        trimmed = painted["pelvis"].copy()
        cut = (trimmed[..., 3] > 128) & ~cover
        if cut.any():
            lost = float(np.count_nonzero(cut)) / max(np.count_nonzero(trimmed[..., 3] > 128), 1)
            trimmed[cut] = 0
            box = list(pv["box"])
            set_piece("pelvis", trimmed)
            pv["box"] = box
            repairs.append(f"the pelvis was trimmed to the skirt's outline ({lost:.0%} of it)")
            if lost > SKIRT_TRIM:
                sheet_problems.append(f"the skirt is much narrower than the pelvis: {lost:.0%} of the pelvis had to go")

    # helper points follow the pieces too
    for n in names:
        p, bp = parts[n], bparts[n]
        for key in ("grip", "tip", "sole"):
            if key in bp:
                u, v = rel(n, bp[key])
                p[key] = to_sheet(n, (u * (p["box"][2] - 1), min(v, 1.0) * (p["box"][3] - 1)))
        if "face" in bp:
            p.pop("face")   # the face slot of a fitted head is found separately (not yet)

    # left/right sanity: bone lengths should be close
    def bone(n):
        kids = [c for c in names if parts[c].get("parent") == n]
        if not kids or not parts[n].get("joint"):
            return None
        a0, a1 = parts[n]["joint"]["at"], parts[kids[0]]["joint"]["parent_at"]
        return float(np.hypot(a1[0] - a0[0], a1[1] - a0[1]))
    for n in names:
        if n.endswith("_l"):
            bl, br = bone(n), bone(n[:-2] + "_r")
            if bl and br and max(bl, br) / max(min(bl, br), 1) > SIDE_RATIO:
                report[n]["problems"].append(f"left/right lengths differ: {bl:.0f} vs {br:.0f} px")

    metrics = rigkit.rest_metrics(rig)
    rig["body_height"] = round(metrics["sole_y"] - metrics["neck_y"], 1)
    rig["joint_radius"] = round(float(np.median([p["joint"]["radius"] for p in parts.values() if p.get("joint")])), 1)
    rig.pop("rest_bbox", None)
    # second drawings: the palm side of the hands, if it was painted
    notes, variant_problems = hand_variants(pdir, parts, pad, images)
    repairs += notes
    notes, mouth_problems = mouth.fit_mouth(pdir, parts, pad, images)
    repairs += notes
    variant_problems += mouth_problems
    notes, wear_problems = wear.fit_wear(pdir, parts, pad, images)     # what stays on over a recorded face
    repairs += notes
    variant_problems += wear_problems
    # a hat of its own (gen_prop.paint_prop(..., hat=True)): worn on top of a recorded head, with nothing else of the painted head
    parts["head"].pop("hat", None)
    (pdir / "parts" / "head.hat.png").unlink(missing_ok=True)
    if (pdir / "hat.png").exists():
        hat = Image.open(pdir / "hat.png").convert("RGBA")
        hat.putalpha(hat.split()[3].point(lambda v: max(0, (v - 40) * 255 // 215)))     # no faint glow around it
        hat = hat.crop(hat.split()[3].getbbox())
        hat.save(pdir / "parts" / "head.hat.png")
        parts["head"]["hat"] = {"size": list(hat.size)}
        repairs.append("the head has a hat to wear on a recorded head")

    # the rest stance: the arms ALONG the body, the same on both sides: from turned inward (a jacket wider than the
    # trousers would leave the hands hanging in the air beside the legs) to outward, the first angle at which the
    # arm lies over the body no more than ARM_CLEAR - so the hand comes down just touching the hip or the thigh
    rig.pop("rest", None)
    over = {a: max(audit.arm_over_body(rig, solids, s, a) for s in "lr") for a in range(-ARM_SPREAD_IN, ARM_SPREAD_MAX + 1, 2)}
    spread = next((a for a in over if over[a] <= ARM_CLEAR), min(over, key=over.get))
    if spread and rig.get("view") != "side":       # in profile an arm hangs across the body, and that is right
        rig["rest"] = {"upper_arm_l": spread, "upper_arm_r": -spread}

    (pdir / "rig.json").write_text(json.dumps(rig, indent=2, ensure_ascii=False), encoding="utf-8")

    # the independent check of the assembled puppet
    measured = audit.measure(rig, {n: solids[n] for n in names})
    # a view (side, back) must be the same character as its front view: the head as tall, the body as heavy
    audit.measure_views(pdir, rig, {n: solids[n] for n in names}, measured, measured["problems"])
    sheet_problems += measured.pop("problems")

    for r in report.values():
        r["ok"] = not r["problems"]
    ok = sum(r["ok"] for r in report.values())
    passed = ok == len(names) and not sheet_problems
    bones = {n: round(bone(n)) for n in names if bone(n)}
    summary = {"name": name, "passed": passed, "parts_ok": ok, "parts_total": len(names), "sheet_problems": sheet_problems,
               "body_height": rig["body_height"], "bones": bones, "repairs": repairs, "variant_problems": variant_problems,
               "measured": measured, "parts": report}
    (pdir / "report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # check image: the sheet with the pieces, their names and joints, next to four poses
    al = rgba[..., 3:4].astype(float) / 255
    vis = cv2.cvtColor((rgba[..., :3] * al + np.array([236, 236, 236]) * (1 - al)).astype(np.uint8), cv2.COLOR_RGB2BGR)
    for n in names:
        x, y, w, h = parts[n]["box"]
        cv2.rectangle(vis, (x, y), (x + w, y + h), (60, 170, 60) if report[n]["ok"] else (40, 40, 220), 2)
        cv2.putText(vis, n, (x + 3, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (20, 20, 20), 1, cv2.LINE_AA)
        if parts[n].get("joint"):
            j = parts[n]["joint"]
            for pt, col in ((j["at"], (200, 60, 20)), (j["parent_at"], (20, 60, 200))):
                cv2.circle(vis, (int(pt[0]), int(pt[1])), int(j["radius"]), col, 1, cv2.LINE_AA)
                cv2.circle(vis, (int(pt[0]), int(pt[1])), 3, col, -1, cv2.LINE_AA)
    imgio.imwrite(str(pdir / "_sheet_check.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 88])
    rigkit.contact_sheet(rig, images, pdir / "_poses.jpg")
    left, right = Image.open(pdir / "_sheet_check.jpg"), Image.open(pdir / "_poses.jpg")
    hgt = 1000
    l2 = left.resize((int(left.width * hgt / left.height), hgt))
    r2 = right.resize((int(right.width * hgt / right.height), hgt))
    both = Image.new("RGB", (l2.width + r2.width + 20, hgt), (255, 255, 255))
    both.paste(l2, (0, 0))
    both.paste(r2, (l2.width + 20, 0))
    both.save(pdir / "check.jpg", quality=86)

    log(f"{name}: {'PASS' if passed else 'FAIL'} {ok}/{len(names)} parts ok, body height {rig['body_height']:.0f} px")
    for s in repairs:
        log(f"  + repaired: {s}")
    for s in variant_problems:
        log(f"  - variant not made: {s}")
    for s in sheet_problems:
        log(f"  - sheet: {s}")
    for n, r in report.items():
        if not r["ok"]:
            log(f"  - {n}: " + "; ".join(r["problems"]))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m tadam.puppet.cut_skin")
    ap.add_argument("dir", help="the puppet folder with sheet.png")
    ap.add_argument("--rig")
    a = ap.parse_args(argv)
    return 0 if cut(Path(a.dir), a.rig).get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
