"""TITLE CARDS for a film: the series name in cut-out letters (each on its own scrap of paper, like the app's
CutoutTitle), the episode under it on a cream strip, a typewriter line. A transparent PNG laid over a shot
(a shot's "card").

usage: python -m tadam.titlecard <out.png> "<title>" ["<sub>"] ["<kicker>"]
Fonts: PT Serif Bold / Italic and PT Mono (ParaType, SIL Open Font License 1.1, with Cyrillic), shipped with the kit
in tadam/data/fonts with their licence texts; the same letters on every computer.
"""
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tadam.paths import FONTS

TITLE_FONT = FONTS / "PT_Serif-Web-Bold.ttf"       # the cut-out letters
SUB_FONT = FONTS / "PT_Serif-Web-Italic.ttf"       # the episode's name on the strip
TYPE_FONT = FONTS / "PTM55FT.ttf"                  # the typewriter line (PT Mono)
INK, SCRAP, RED, SKY, CREAM = (33, 32, 28), (236, 214, 189), (194, 53, 31), (63, 97, 113), (246, 237, 226)
TILES = [(INK, CREAM), (SCRAP, INK), (RED, CREAM), (SCRAP, INK), (SCRAP, INK), (SKY, CREAM), (SCRAP, INK), (RED, CREAM)]


def tile_word(word: str, h: int, seed: int) -> Image.Image:
    """One word of cut-out letters: a tile per letter, colours in turn, each a little turned and lifted."""
    rnd = random.Random(seed)
    font = ImageFont.truetype(str(TITLE_FONT), int(h * 0.72))
    tiles = []
    for i, ch in enumerate(word):
        bg, fg = TILES[(i + seed) % len(TILES)]
        w = int(font.getlength(ch) + h * 0.32)
        t = Image.new("RGBA", (w, h), bg + (255,))
        d = ImageDraw.Draw(t)
        box = d.textbbox((0, 0), ch, font=font)
        d.text(((w - (box[2] - box[0])) / 2 - box[0], (h - (box[3] - box[1])) / 2 - box[1]), ch, font=font, fill=fg)
        tiles.append(t.rotate(rnd.uniform(-6, 6), resample=Image.BICUBIC, expand=True))
    W = sum(t.width for t in tiles) - int(h * 0.06) * (len(tiles) - 1)
    out = Image.new("RGBA", (W, h + 24), (0, 0, 0, 0))
    x = 0
    for t in tiles:
        out.alpha_composite(t, (x, 12 + rnd.randint(-8, 8) - (t.height - h) // 2))
        x += t.width - int(h * 0.06)
    return out


def card(out: Path, title: str, sub: str = "", kicker: str = "", size=(720, 1280), top: float = 0.16) -> None:
    W, H = size
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    y = int(H * top)
    h = int(W * 0.11)
    for n, word in enumerate(title.upper().split("/")):
        word = word.strip()
        t = tile_word(word.replace(" ", ""), h, seed=n * 3 + 1) if " " not in word else None
        if t is None:     # several words on one line: a gap between them
            parts = [tile_word(p, h, seed=n * 3 + k) for k, p in enumerate(word.split())]
            gap = int(h * 0.55)
            t = Image.new("RGBA", (sum(p.width for p in parts) + gap * (len(parts) - 1), max(p.height for p in parts)))
            x = 0
            for p in parts:
                t.alpha_composite(p, (x, 0))
                x += p.width + gap
        if t.width > W * 0.92:
            t = t.resize((int(W * 0.92), int(t.height * W * 0.92 / t.width)), Image.LANCZOS)
        img.alpha_composite(t, ((W - t.width) // 2, y))
        y += t.height + int(h * 0.1)
    d = ImageDraw.Draw(img)
    if kicker:
        size_k = int(W * 0.032)
        text = " ".join(kicker.upper())
        while True:     # spaced typewriter letters, as wide as fits
            f = ImageFont.truetype(str(TYPE_FONT), size_k)
            bw = d.textlength(text, font=f)
            if bw <= W * 0.84 or size_k <= 12:
                break
            size_k -= 1
        y += int(h * 0.35)
        d.rectangle([(W - bw) / 2 - 14, y - 6, (W + bw) / 2 + 14, y + f.size + 8], fill=INK + (235,))
        d.text(((W - bw) / 2, y), text, font=f, fill=CREAM)
        y += f.size + 22
    if sub:
        f = ImageFont.truetype(str(SUB_FONT), int(W * 0.075))
        bw = d.textlength(sub, font=f)
        d.rectangle([(W - bw) / 2 - 22, y, (W + bw) / 2 + 22, y + f.size * 1.35], fill=CREAM + (245,))
        d.text(((W - bw) / 2, y + f.size * 0.12), sub, font=f, fill=INK)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    card(Path(a[0]), a[1], a[2] if len(a) > 2 else "", a[3] if len(a) > 3 else "")
