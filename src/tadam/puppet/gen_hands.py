"""Paint a second drawing of a puppet's hands: the PALM side. The engine shows it when the hand is raised.

usage: tadam.puppet.gen_hands.paint_hands(<puppet folder>, kind="palm" | "fist")
  palm (default)  the open palm, shown when the hand is raised          -> <puppet>/hands.png
  fist            a closed hand that grips, shown when it holds a prop  -> <puppet>/hands_fist.png
Reads <puppet>/parts/hand_l.png and hand_r.png (the puppet must be cut already) and meta.json; writes
<puppet>/hands.png: the same two pieces repainted from the palm side, the hand of the left of the picture on the
left. Run cut_skin.cut(<puppet folder>) afterwards: it cuts the two palms, fits them to the puppet's own hands and adds
them to rig.json as the "palm" variant of hand_l and hand_r.

The model is shown the puppet's OWN two hand pieces, enlarged, and asked to turn them over. Shown the whole kit and
an empty pattern instead, it invents a sleeve on top of each hand.

Why the thumbs point outward here: the pieces are rigid. A hand that hangs with its fingers down and is then raised
is the same drawing turned upside down, so its outer side becomes the side nearer the head. A raised open palm has
the thumb towards the head; hanging, that is the outer side.
"""
import json
from pathlib import Path

from PIL import Image

from tadam import openai_images as oi
from tadam.puppet import gen_skin as G
SIZE = 1024
TALL = 560            # each hand piece is shown this tall

PROMPT = """The image shows the two hand pieces of a flat jointed puppet, seen from the BACK of the hand. Each piece has its wrist end at the top and the fingers pointing down.
Repaint both pieces turned over, seen from the PALM side.
Character: {character}.
Style: {style}.
Rules:
- Each piece stays in the same place, the same size and the same proportions.
- The top of each piece (the wrist end with its cuff, glove edge, bracelet or sleeve end) stays exactly as it is: the same shape, the same colours, rounded and fully painted. Do not add a sleeve, an arm or anything above it.
- Below the wrist paint the open palm facing the viewer, fingers pointing down and slightly apart, relaxed. The thumb of the left hand points to the left, the thumb of the right hand points to the right (thumbs on the outer sides).
- The same skin or glove colour, the same number of fingers, the same line weight and painting style. If the hand is not human (a claw, a mitten, a paw, a tool), paint the inner side of the same hand.
- Exactly two separate pieces with empty space between them. Nothing else: no text, no frame.
- Fully transparent background."""


FIST_PROMPT = """The image shows the two hand pieces of a flat jointed puppet, seen from the BACK of the hand. Each piece has its wrist end at the top and the fingers pointing down.
Repaint both pieces as CLOSED FISTS that grip a handle.
Character: {character}.
Style: {style}.
Rules:
- Each piece stays in the same place. The top of each piece (the wrist end with its cuff, glove edge, bracelet or sleeve end) stays exactly as it is: the same shape, the same width, the same colours, rounded and fully painted. Do not add a sleeve, an arm or anything above it.
- Below the wrist paint the hand closed into a fist, as if it holds the handle of a tool that runs straight down through it: the fingers curled round, the knuckles towards the viewer, the thumb wrapped across the fingers. The fist is compact, shorter than the open hand. Do not paint the handle or any object.
- The fist is ONE compact rounded shape: the back of the hand and the curled fingers together form a single ball, the curled fingers as wide as the hand. Never a flat open hand with a smaller fist added under it.
- The fist is closed TIGHT and seen from outside: no opening, no hole, no tunnel and no inside of the fist is visible, not at the top, not at the bottom, not between the fingers. (The handle will be laid behind the fist, so it looks as if it passes through it.)
- The same skin or glove colour, the same line weight and painting style. If the hand is not human (a claw, a mitten, a paw, a tool), close that hand the way it would grip.
- Exactly two separate pieces with empty space between them. Nothing else: no text, no frame.
- Fully transparent background."""


def reference(pdir):
    """The puppet's two hand pieces side by side on white, enlarged to TALL px."""
    ref = Image.new("RGB", (SIZE, SIZE), "white")
    for i, hand in enumerate(("hand_l", "hand_r")):
        im = Image.open(pdir / "parts" / f"{hand}.png").convert("RGBA")
        im = im.crop(im.getbbox())
        k = TALL / im.height
        im = im.resize((max(int(im.width * k), 1), TALL), Image.LANCZOS)
        ref.paste(im, (SIZE // 4 + i * SIZE // 2 - im.width // 2, (SIZE - TALL) // 2), im)
    path = pdir / "_hands_ref.png"
    ref.save(path)
    return path


def paint_hands(pdir, kind="palm", model=oi.DEFAULT_MODEL, quality="medium", log=print):
    if kind not in ("palm", "fist"):
        raise ValueError("kind is palm or fist")
    out = Path(pdir)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    ref = reference(out)
    png, usage, sec = G.call("edits", {"model": model, "size": f"{SIZE}x{SIZE}", "quality": quality, "output_format": "png",
                                       "n": 1, "background": "transparent",
                                       "prompt": (PROMPT if kind == "palm" else FIST_PROMPT).format(
                                           character=meta["character"], style=meta["style"])},
                             images=[ref])
    target = out / ("hands.png" if kind == "palm" else "hands_fist.png")
    target.write_bytes(png)
    meta["calls"].append({"step": "hands " + kind, "seconds": sec, "usage": usage})
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"hands {sec} s")
    return target
