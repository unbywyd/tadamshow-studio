"""The face board (rig parts.head.board): found from the head drawing, the same rule for every hero."""
from __future__ import annotations

import json

import numpy as np
from PIL import Image, ImageDraw

from tadam.puppet import board

SKIN = (236, 200, 170, 255)


def head_picture(hat: bool = True, ears: bool = True, horns: bool = False) -> tuple[Image.Image, tuple, tuple]:
    """A painted head as a pattern cut gives it (pad around it): a face, hair or a hat on top, ears or horns at the
    sides, a neck stub under the chin. Returns (picture, neck pin, the face ellipse box)."""
    im = Image.new("RGBA", (300, 360), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    face = (80, 70, 220, 270)                                  # the face: 140 wide, 200 tall
    d.rectangle([125, 250, 175, 330], fill=SKIN)               # the neck stub
    if ears:
        d.ellipse([58, 140, 92, 200], fill=SKIN)
        d.ellipse([208, 140, 242, 200], fill=SKIN)
    if horns:
        d.polygon([(90, 90), (20, 20), (110, 80)], fill=(240, 230, 210, 255))
        d.polygon([(210, 90), (280, 20), (190, 80)], fill=(240, 230, 210, 255))
    d.ellipse(face, fill=SKIN)
    d.ellipse([115, 140, 135, 160], fill=(30, 30, 30, 255))   # eyes
    d.ellipse([165, 140, 185, 160], fill=(30, 30, 30, 255))
    d.ellipse([130, 215, 170, 232], fill=(170, 40, 40, 255))  # mouth
    if hat:
        d.rectangle([60, 70, 240, 92], fill=(40, 60, 50, 255))    # the brim
        d.rectangle([95, 14, 205, 75], fill=(40, 60, 50, 255))    # the crown of the hat
    else:
        d.pieslice([78, 62, 222, 200], 180, 360, fill=(60, 40, 20, 255))   # hair
    return im, (150.0, 312.0), face


def _oval_mask(shape, b) -> np.ndarray:
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    (cx, cy), (bw, bh) = b["center"], b["size"]
    return ((xx - cx) / (bw / 2)) ** 2 + ((yy - cy) / (bh / 2)) ** 2 <= 1


def _skin(im) -> np.ndarray:
    a = np.array(im)
    return (np.abs(a[..., :3].astype(int) - SKIN[:3]).sum(axis=2) < 30) & (a[..., 3] > 128)


def test_board_sits_on_the_painted_face():
    for hat, ears, horns in ((True, True, False), (False, True, False), (False, False, True), (True, False, True)):
        im, joint, face = head_picture(hat, ears, horns)
        b = board.fit(im, joint)
        assert b is not None
        oval = _oval_mask((im.height, im.width), b)
        paint = np.array(im)[..., 3] > 128
        # the whole oval is on the painted head, almost all of it on the face itself (eyes and mouth inside)
        assert (oval & ~paint).sum() == 0
        a = np.array(im)[..., :3].astype(int)
        not_face = np.zeros(paint.shape, bool)
        for c in ((40, 60, 50), (60, 40, 20), (240, 230, 210)):      # the hat, the hair, the horns
            not_face |= np.abs(a - c).sum(axis=2) < 30
        assert (oval & not_face & paint).sum() / oval.sum() < 0.03
        fx0, fy0, fx1, fy1 = face
        (cx, cy), (w, h) = b["center"], b["size"]
        assert abs(cx - 150) <= 2                                 # on the head's centre line
        assert fy0 < cy - h / 2 and cy + h / 2 < fy1 + 5           # between the brow and the chin
        assert w <= (fx1 - fx0) * 0.95                             # snug: narrower than the face
        assert board.ASPECT[0] * h - 1 <= w <= board.ASPECT[1] * h + 1
        assert cy - h / 2 <= 150 <= cy + h / 2 and cy - h / 2 <= 224 <= cy + h / 2   # the eyes and the mouth show


def test_a_known_mouth_moves_the_board_a_little():
    im, joint, _ = head_picture()
    plain = board.fit(im, joint)
    low = board.fit(im, joint, mouth=(150, 300))           # a mouth far down: the pull is capped
    span = joint[1] - 14
    assert plain["center"][1] < low["center"][1] <= plain["center"][1] + board.MOUTH_PULL * span + 1


def test_nothing_over_the_pin_gives_no_board():
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    assert board.fit(im, (50, 90)) is None


def test_the_mannequin_gets_its_board(mannequin_puppet):
    rig = json.loads((mannequin_puppet / "rig.json").read_text(encoding="utf-8"))
    head = rig["parts"]["head"]
    b = head["board"]
    im = Image.open(mannequin_puppet / "parts" / "head.png").convert("RGBA")
    oval = _oval_mask((im.height, im.width), b)
    paint = np.array(im)[..., 3] > 128
    assert oval.sum() > 0 and (oval & ~paint).sum() / oval.sum() < 0.01
    pad, bx = rig["pad"], head["box"]
    jx = head["joint"]["at"][0] - bx[0] + pad
    assert abs(b["center"][0] - jx) <= 3
    mx, my = head["mouth"]["center"][0] - bx[0] + pad, head["mouth"]["center"][1] - bx[1] + pad
    assert _oval_mask((im.height, im.width), b)[int(my), int(mx)]      # its mouth shows in the oval
