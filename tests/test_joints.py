"""Joint placement on drawn shapes with a known right answer (pytest; or python tests/test_joints.py [--draw out.jpg]).

Every case is a body block or a head with one awkward feature (a collar dip, a notch, collar points, a parrot on a
shoulder, braids, a one-sided pompom). The right pin is known by construction; a case passes if the pin found is
within TOL pixels of it. Exit code 1 if any case fails.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

from tadam import imgio
from tadam.puppet import audit
from tadam.puppet import cut_skin as cs

TOL = 4.0
W, H = 240, 280          # the plain body block
OX, OY = 120, 120        # room around it on the canvas, for the features that stick out
DEPTH = 30               # how deep the pin goes under the edge in these tests
NECK_R = 28


def block():
    m = np.zeros((H + 2 * OY, W + 2 * OX), np.uint8)
    cv2.rectangle(m, (OX + 30, OY), (OX + W - 30, OY + H), 1, -1)
    cv2.rectangle(m, (OX, OY + 30), (OX + W, OY + H - 30), 1, -1)
    for cx in (OX + 30, OX + W - 30):
        for cy in (OY + 30, OY + H - 30):
            cv2.circle(m, (cx, cy), 30, 1, -1)
    return m


def crop(m):
    ys, xs = np.nonzero(m)
    x0, y0 = xs.min(), ys.min()
    return m[y0:ys.max() + 1, x0:xs.max() + 1].astype(bool), (x0, y0)


def poly(m, pts, v):
    cv2.fillPoly(m, [np.array(pts, np.int32)], v)


CX = OX + W // 2         # the true centre line of every block below

# name -> (how to spoil the block, which edge, the true edge row on the canvas)
BLOCKS = {}


def case(name, top, edge):
    def deco(fn):
        BLOCKS[name] = (fn, top, edge)
        return fn
    return deco


@case("plain top", True, OY)
def _(m):
    pass


@case("wide collar dip", True, OY + 18)
def _(m):
    cv2.ellipse(m, (CX, OY), (55, 18), 0, 0, 360, 0, -1)


@case("narrow V notch, 50 deep", True, OY)
def _(m):
    poly(m, [(CX - 10, OY - 2), (CX + 10, OY - 2), (CX, OY + 50)], 0)


@case("deep V neckline, wider than the neck", True, OY + 39)
def _(m):
    # a neck end of radius 28 lowered into a V 90 wide and 56 deep comes to rest with its lowest point
    # 56 - (28 / sin(atan(45 / 56)) - 28) = 39 px under the shoulder line
    poly(m, [(CX - 45, OY - 2), (CX + 45, OY - 2), (CX, OY + 56)], 0)


@case("tall collar points either side", True, OY)
def _(m):
    for s in (-1, 1):
        poly(m, [(CX + s * 40, OY + 2), (CX + s * 75, OY + 2), (CX + s * 70, OY - 70)], 1)


@case("parrot on one shoulder", True, OY)
def _(m):
    cv2.ellipse(m, (OX + 30, OY - 30), (32, 48), 0, 0, 360, 1, -1)


@case("parrot and a hanging cape corner", True, OY)
def _(m):
    cv2.ellipse(m, (OX + W - 25, OY - 25), (30, 40), 0, 0, 360, 1, -1)
    poly(m, [(OX - 40, OY + 60), (OX + 5, OY + 60), (OX + 5, OY + 200)], 1)


@case("neck bump painted on the chest", True, OY - 22)
def _(m):
    cv2.rectangle(m, (CX - 34, OY - 22), (CX + 34, OY + 2), 1, -1)


@case("plain bottom", False, OY + H)
def _(m):
    pass


@case("vest notch at the bottom", False, OY + H)
def _(m):
    poly(m, [(CX - 22, OY + H + 2), (CX + 22, OY + H + 2), (CX, OY + H - 45)], 0)


@case("tie hanging below the bottom", False, OY + H)
def _(m):
    poly(m, [(CX - 12, OY + H - 2), (CX + 12, OY + H - 2), (CX, OY + H + 50)], 1)


@case("round belly bottom", False, OY + H + 38)
def _(m):
    cv2.ellipse(m, (CX, OY + H - 30), (W // 2, 70), 0, 0, 180, 1, -1)


@case("coat tails either side of the bottom", False, OY + H)
def _(m):
    for s in (-1, 1):
        poly(m, [(CX + s * 60, OY + H - 2), (CX + s * 118, OY + H - 2), (CX + s * 100, OY + H + 60)], 1)


def head(feature):
    """A round head (r 80) with a neck stub (56 wide, rounded end) under it. Returns mask, true pin on the canvas."""
    m = np.zeros((520, 520), np.uint8)
    c = (260, 200)
    cv2.circle(m, c, 80, 1, -1)
    cv2.rectangle(m, (c[0] - 28, c[1] + 60), (c[0] + 28, c[1] + 120), 1, -1)
    cv2.circle(m, (c[0], c[1] + 120), 28, 1, -1)
    feature(m, c)
    return m, (c[0], c[1] + 120)


HEADS = {}


def hcase(name):
    def deco(fn):
        HEADS[name] = fn
        return fn
    return deco


@hcase("plain head")
def _(m, c):
    pass


@hcase("two braids lower than the neck")
def _(m, c):
    for s in (-1, 1):
        cv2.rectangle(m, (c[0] + s * 95 - 16, c[1]), (c[0] + s * 95 + 16, c[1] + 230), 1, -1)
        cv2.circle(m, (c[0] + s * 95, c[1] + 230), 22, 1, -1)
        cv2.rectangle(m, (c[0] + min(0, s * 95), c[1] - 20), (c[0] + max(0, s * 95), c[1] + 20), 1, -1)


@hcase("headcloth flaps beside the neck")
def _(m, c):
    for s in (-1, 1):
        poly(m, [(c[0] + s * 40, c[1]), (c[0] + s * 110, c[1]), (c[0] + s * 100, c[1] + 190), (c[0] + s * 50, c[1] + 190)], 1)


@hcase("headcloth flaps right against the neck")
def _(m, c):
    for s in (-1, 1):
        poly(m, [(c[0] + s * 31, c[1]), (c[0] + s * 110, c[1]), (c[0] + s * 95, c[1] + 200), (c[0] + s * 31, c[1] + 200)], 1)


@hcase("long hair joined to the neck, hanging lower")
def _(m, c):
    cv2.rectangle(m, (c[0] - 85, c[1]), (c[0] + 85, c[1] + 105), 1, -1)
    for s in (-1, 1):
        cv2.rectangle(m, (c[0] + s * 85, c[1]), (c[0] + s * 50, c[1] + 210), 1, -1)


@hcase("big one-sided feather: the centre line is pulled")
def _(m, c):
    cv2.ellipse(m, (c[0] - 120, c[1] - 30), (60, 110), -15, 0, 360, 1, -1)


@hcase("thin side ponytail lower than the neck")
def _(m, c):
    cv2.line(m, (c[0] + 60, c[1] - 40), (c[0] + 120, c[1] + 220), 1, 26)


@hcase("wide flat head (a frog)")
def _(m, c):
    cv2.ellipse(m, (c[0], c[1]), (170, 70), 0, 0, 360, 1, -1)


@hcase("tall hat wider than the face")
def _(m, c):
    cv2.rectangle(m, (c[0] - 100, c[1] - 190), (c[0] + 100, c[1] - 40), 1, -1)


@hcase("pompom hanging on one side")
def _(m, c):
    poly(m, [(c[0], c[1] - 110), (c[0] + 60, c[1] - 60), (c[0] - 60, c[1] - 60)], 1)
    cv2.line(m, (c[0] + 40, c[1] - 80), (c[0] + 130, c[1] + 150), 1, 14)
    cv2.circle(m, (c[0] + 130, c[1] + 160), 30, 1, -1)


@hcase("one-sided plume")
def _(m, c):
    cv2.ellipse(m, (c[0] + 70, c[1] - 90), (40, 80), 20, 0, 360, 1, -1)


@hcase("wide hat brim")
def _(m, c):
    cv2.ellipse(m, (c[0], c[1] - 50), (170, 26), 0, 0, 360, 1, -1)


@hcase("beard beside and above the neck end")
def _(m, c):
    poly(m, [(c[0] - 75, c[1] + 20), (c[0] + 75, c[1] + 20), (c[0] + 45, c[1] + 100), (c[0] - 45, c[1] + 100)], 1)


def run():
    rows, panels = [], []
    for name, (spoil, top, edge) in BLOCKS.items():
        m = block()
        spoil(m)
        solid, (x0, y0) = crop(m)
        dt = audit.inscribed(solid)
        half = NECK_R if top else cs.WAIST_BAND * solid.shape[1]
        x, y, _ = cs.centre_joint(solid, dt, top=top, depth=DEPTH, half=half)
        want = (CX, edge + DEPTH if top else edge - DEPTH)
        got = (x + x0, y + y0)
        rows.append((name, want, got))
        panels.append((m, want, got, name))
    for name, feature in HEADS.items():
        m, want = head(feature)
        solid, (x0, y0) = crop(m)
        dt = audit.inscribed(solid)
        ax = audit.head_axis(solid)
        w = solid.shape[1]
        x, y, _ = cs.end_joint(dt, top=False, band=cs.END_BAND["head"], corridor=cs.neck_corridor(ax, w))
        got = (x + x0, y + y0)
        rows.append((name, want, got))
        panels.append((m, want, got, name))
    bad = 0
    for name, want, got in rows:
        err = float(np.hypot(got[0] - want[0], got[1] - want[1]))
        ok = err <= TOL
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name:42s} want ({want[0]:.0f},{want[1]:.0f})  got ({got[0]:.1f},{got[1]:.1f})  off {err:.1f} px")
    print(f"\n{len(rows) - bad} of {len(rows)} cases pass")
    return bad, panels


def draw(panels, path):
    tiles = []
    for m, want, got, name in panels:
        t = cv2.cvtColor(((1 - m) * 60 + 180).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        t = cv2.resize(t, (360, int(360 * t.shape[0] / t.shape[1])))[:400]
        t = cv2.copyMakeBorder(t, 0, 400 - t.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(240, 240, 240))
        k = 360 / m.shape[1]
        cv2.circle(t, (int(want[0] * k), int(want[1] * k)), 9, (60, 170, 60), 2, cv2.LINE_AA)
        cv2.circle(t, (int(got[0] * k), int(got[1] * k)), 4, (40, 40, 220), -1, cv2.LINE_AA)
        cv2.putText(t, name, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        tiles.append(t)
    per = 7
    while len(tiles) % per:
        tiles.append(np.full_like(tiles[0], 240))
    imgio.imwrite(str(path), np.vstack([np.hstack(tiles[i:i + per]) for i in range(0, len(tiles), per)]),
                [cv2.IMWRITE_JPEG_QUALITY, 88])


def test_every_joint_case_within_tolerance():
    bad, _ = run()
    assert bad == 0


if __name__ == "__main__":
    failed, shown = run()
    if "--draw" in sys.argv:
        draw(shown, sys.argv[sys.argv.index("--draw") + 1])
    sys.exit(1 if failed else 0)
