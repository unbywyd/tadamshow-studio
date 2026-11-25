"""Draws the MUSICAL INSTRUMENTS of the engine's item library: flat, matte, no outlines, no shadows (the house style).
usage: python devtools/draw_instruments.py     -> engine/items/<id>.png and <id>.json

Drawn by code, not painted by a model: every spot a hand plays on (the strings, the neck, the drumhead) is exactly
where the card says. Any picture may be replaced by a painted one of the same layout (the same upright pose and
the same spots), the card stays.
  guitar      upright, the neck at the top          balalaika  the same, a triangle
  drum        a marching drum seen from the front   drumstick  upright, its tip at the top
  accordion   lying across, the bellows in the middle (they stretch between the hands)
  bass        a double bass, upright, its spike at the bottom (it stands on the floor)
  pipe        a wooden pipe, its mouth end at the top
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "engine" / "items"
SS = 3                                   # drawn this many times larger, then shrunk: smooth edges

WOOD = (224, 155, 76)
WOOD_DARK = (92, 58, 36)
WOOD_RED = (156, 74, 38)
HOLE = (59, 38, 24)
STRING = (243, 233, 210)
CREAM = (246, 238, 220)
GOLD = (231, 181, 74)
RED = (200, 70, 60)
NAVY = (46, 58, 79)
NAVY_LIGHT = (66, 82, 108)
INK = (42, 31, 26)


class Pic:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def _s(self, pts):
        return [(x * SS, y * SS) for x, y in pts]

    def ellipse(self, cx, cy, rx, ry, fill):
        self.d.ellipse([(cx - rx) * SS, (cy - ry) * SS, (cx + rx) * SS, (cy + ry) * SS], fill=fill)

    def circle(self, cx, cy, r, fill):
        self.ellipse(cx, cy, r, r, fill)

    def rect(self, x0, y0, x1, y1, fill, r=0):
        self.d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=r * SS, fill=fill)

    def poly(self, pts, fill):
        self.d.polygon(self._s(pts), fill=fill)

    def line(self, pts, fill, width):
        self.d.line(self._s(pts), fill=fill, width=int(width * SS), joint="curve")

    def save(self, name, card):
        im = self.im.resize((self.w, self.h), Image.LANCZOS)
        im.save(OUT / f"{name}.png")
        card = {"id": name, **card}
        (OUT / f"{name}.json").write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
        print(OUT / f"{name}.png", im.size)


def guitar():
    p = Pic(420, 1100)
    # body: two bouts and the waist between them
    p.circle(210, 860, 200, WOOD)
    p.circle(210, 620, 150, WOOD)
    p.circle(210, 640, 66, (190, 116, 58))            # the rosette round the hole
    p.circle(210, 640, 54, HOLE)
    p.rect(140, 872, 280, 902, WOOD_DARK, 10)         # bridge
    # neck and head
    p.rect(180, 150, 240, 600, WOOD_DARK, 6)
    for i, y in enumerate([200, 250, 296, 338, 377, 413, 446, 477, 506, 533]):
        p.rect(181, y, 239, y + 3, (201, 180, 142))
    for y in [314, 395, 461]:
        p.circle(210, y, 6, CREAM)
    p.rect(165, 8, 255, 152, WOOD_DARK, 22)
    for y in [40, 80, 120]:
        p.circle(150, y, 11, CREAM)
        p.circle(270, y, 11, CREAM)
    p.rect(176, 146, 244, 156, CREAM, 3)              # nut
    for i in range(6):
        x0 = 186 + i * 9.6
        x1 = 158 + i * 20.8
        p.line([(x0, 150), (x1, 886)], STRING, 2.2)
    p.save("guitar", {
        "title": "гитара", "size": 0.2, "hold": "wear", "grip": [0.5, 0.72],
        "wear": {"spots": {"strum": ["arm_l", 0.3, 0.8], "fret": ["arm_r", 0.45, 0.05]}, "fit": [1.6, 2.2], "over": "chest"},
        "spots": {"strum": [0.5, 0.66], "fret": [0.5, 0.3], "fret_hi": [0.5, 0.22], "fret_lo": [0.5, 0.4]},
        "play": "play_guitar", "bounce": 0.15})


def balalaika():
    p = Pic(420, 1100)
    p.poly([(210, 560), (395, 1040), (380, 1080), (40, 1080), (25, 1040)], WOOD)
    p.circle(210, 860, 40, (190, 116, 58))
    p.circle(210, 860, 28, HOLE)
    for a in range(8):                                 # a ring of little dots round the hole
        import math
        p.circle(210 + 52 * math.cos(a * math.pi / 4), 860 + 52 * math.sin(a * math.pi / 4), 6, RED)
    p.rect(160, 990, 260, 1012, WOOD_DARK, 8)          # bridge
    p.rect(189, 130, 231, 640, WOOD_DARK, 5)
    for y in [190, 240, 286, 328, 367, 403, 436, 467, 496, 523, 548]:
        p.rect(190, y, 230, y + 3, (201, 180, 142))
    p.poly([(175, 135), (245, 135), (255, 20), (210, 6), (165, 20)], WOOD_DARK)
    for y in [50, 100]:
        p.circle(158, y, 10, CREAM)
        p.circle(262, y, 10, CREAM)
    for i in range(3):
        p.line([(198 + i * 12, 135), (185 + i * 25, 1000)], STRING, 2.4)
    p.save("balalaika", {
        "title": "балалайка", "size": 0.2, "hold": "wear", "grip": [0.5, 0.8],
        "wear": {"spots": {"strum": ["arm_l", 0.3, 0.75], "fret": ["arm_r", 0.5, 0.0]}, "fit": [1.8, 2.3], "over": "chest"},
        "spots": {"strum": [0.5, 0.8], "fret": [0.5, 0.32], "fret_hi": [0.5, 0.24], "fret_lo": [0.5, 0.42]},
        "play": "play_balalaika", "bounce": 0.2})


def drum():
    p = Pic(600, 520)
    p.ellipse(300, 445, 285, 62, GOLD)
    p.rect(22, 80, 578, 445, RED)
    # the rope zigzag round the shell
    xs = [40 + i * 52 for i in range(11)]
    pts = [(x, 125 if i % 2 == 0 else 405) for i, x in enumerate(xs)]
    p.line(pts, CREAM, 9)
    p.rect(15, 395, 585, 445, GOLD, 4)
    p.ellipse(300, 82, 292, 72, GOLD)
    p.ellipse(300, 78, 268, 56, CREAM)
    p.save("drum", {
        "title": "барабан", "size": 0.12, "hold": "wear", "grip": [0.5, 0.42],
        "wear": {"spots": {"left": ["arm_l", 0.1, 1.05], "right": ["arm_r", 0.1, 1.05]}, "fit": [0.95, 1.15], "rot": 0,
                 "over": "chest"},
        "spots": {"left": [0.3, 0.14], "right": [0.7, 0.14]},
        "play": "play_drum", "with": [{"card": "drumstick", "hand": "right", "hold": -140}, {"card": "drumstick", "hand": "left", "hold": -140}],
        "bounce": 0.3})


def drumstick():
    p = Pic(80, 700)
    p.poly([(31, 60), (49, 60), (58, 688), (22, 688)], (240, 214, 160))
    p.circle(40, 42, 26, (250, 232, 196))
    p.circle(40, 686, 18, (240, 214, 160))
    p.save("drumstick", {"title": "барабанная палочка", "size": 0.06, "fit": 0.7, "hold": "hand", "grip": [0.5, 0.84],
                         "bounce": 0.4})


def accordion():
    p = Pic(900, 560)
    # bellows: folds, with the little corners at the top and the bottom
    for i in range(20):
        x = 200 + i * 25
        p.rect(x, 40, x + 25, 520, NAVY if i % 2 == 0 else NAVY_LIGHT)
        p.rect(x + 4, 40, x + 21, 60, CREAM)
        p.rect(x + 4, 500, x + 21, 520, CREAM)
    # the two ends
    for x0 in (0, 700):
        p.rect(x0, 10, x0 + 200, 550, RED, 26)
        p.rect(x0 + 18, 30, x0 + 182, 530, (176, 52, 52), 18)
    for row in range(3):                               # bass buttons on the left
        for k in range(6):
            p.circle(48 + row * 52 + (13 if k % 2 else 0), 90 + k * 76, 15, CREAM)
    for k in range(12):                                # keys on the right
        y = 48 + k * 40
        p.rect(722, y, 840, y + 34, CREAM, 5)
        if k % 7 not in (2, 6):
            p.rect(722, y + 24, 790, y + 46, INK, 5)
    p.save("accordion", {
        "title": "гармошка", "size": 0.12, "fit": 1.05, "hold": "both", "grip": [0.5, 0.5], "span": 1.0,
        "bellows": [0.2222, 0.7778], "carry": [0, 0.62], "play": "play_accordion", "bounce": 0.2})


def bass():
    p = Pic(520, 1500)
    p.ellipse(260, 1120, 250, 290, WOOD_RED)            # lower bout
    p.ellipse(260, 770, 195, 220, WOOD_RED)             # upper bout
    for sx in (-1, 1):                                  # f-holes
        x = 260 + sx * 92
        p.line([(x, 930), (x - sx * 6, 1000), (x, 1075)], INK, 9)
        p.circle(x, 926, 9, INK)
        p.circle(x, 1079, 9, INK)
    p.poly([(230, 1180), (290, 1180), (305, 1380), (215, 1380)], INK)       # tailpiece
    p.poly([(232, 165), (288, 165), (302, 905), (218, 905)], INK)           # fingerboard
    p.poly([(200, 1000), (320, 1000), (306, 1040), (214, 1040)], (232, 210, 166))   # bridge
    p.rect(228, 40, 292, 175, (138, 63, 31), 14)        # neck and peg box
    p.circle(260, 46, 40, (122, 54, 26))                # the scroll
    p.circle(260, 46, 18, (156, 74, 38))
    for y in (85, 130):
        p.circle(212, y, 12, CREAM)
        p.circle(308, y, 12, CREAM)
    p.rect(252, 1380, 268, 1500, (59, 42, 32), 6)       # the spike
    for i in range(4):
        p.line([(240 + i * 13, 172), (222 + i * 25, 1185)], STRING, 2.6)
    p.save("bass", {
        "title": "контрабас", "size": 0.5, "hold": "wear", "grip": [0.5, 1.0],
        "wear": {"spots": {"grip": ["floor", -0.1], "neck": ["arm_r", 0.3, 0.12]}, "over": "chest"},
        "spots": {"pluck": [0.5, 0.62], "neck": [0.5, 0.2], "neck_hi": [0.5, 0.15], "neck_lo": [0.5, 0.27]},
        "play": "play_bass", "bounce": 0.1, "heavy": True})


def pipe():
    p = Pic(140, 900)
    p.rect(36, 60, 104, 885, (217, 165, 92), 34)
    p.rect(44, 0, 96, 110, WOOD_DARK, 22)
    p.rect(32, 118, 108, 138, (176, 122, 62), 8)
    p.rect(32, 844, 108, 864, (176, 122, 62), 8)
    for y in [330, 410, 490, 600, 680, 760]:
        p.circle(70, y, 12, HOLE)
    p.save("pipe", {
        "title": "дудочка", "size": 0.07, "fit": 1.1, "hold": "wear", "grip": [0.5, 0.02],
        "wear": {"on": "mouth", "dx": 0.0, "dy": 0.0, "rot": -6, "over": "forearm_r"},
        "spots": {"up": [0.5, 0.4], "low": [0.5, 0.68]},
        "play": "play_pipe", "bounce": 0.3})


if __name__ == "__main__":
    for f in (guitar, balalaika, drum, drumstick, accordion, bass, pipe):
        f()
