"""Paint a puppet's head again with the mouth open. The engine swaps the two drawings to make the puppet talk.

usage: tadam.puppet.gen_mouth.paint_mouth(<puppet folder>)
Reads <puppet>/parts/head.png (the puppet must be cut already) and meta.json; writes
<puppet>/mouth_open.png: the same head, same place and size, with the mouth open.
Run cut_skin.cut(<puppet folder>) afterwards: it keeps only the MOUTH of the new picture (the place where the two
pictures differ most), lays it on the puppet's own head and adds the result to rig.json as the "open" variant
of the head. So nothing but the mouth moves when the drawings are swapped.
"""
import json
from pathlib import Path

from PIL import Image

from tadam import openai_images as oi
from tadam.puppet import gen_skin as G
SIZE = 1024
FIT = 880             # the head piece is shown this big (its longer side)

PROMPT = """The image shows the head piece of a flat jointed puppet: a head with a short neck end under it.
Repaint exactly the same head with the MOUTH OPEN, as if the character is speaking and saying "ah".
Character: {character}.
Style: {style}.
Rules:
- Change only the mouth: the lips part, the lower lip and the chin drop a little, and the inside of the mouth is dark; a hint of teeth or tongue only if it suits this character. If a moustache or a beard covers the mouth, the mouth opens under it and the hair around it moves just enough.
- If the character has no human mouth (a carved pumpkin, a robot's grille, a skull, an animal's muzzle), open the mouth or jaw it has.
- Everything else stays exactly as it is, pixel for pixel if you can: the same place and size in the picture, the same outline, eyes, eyebrows, nose, cheeks, hair, hat, ears, neck, colours and line weight. Do not change the expression of the eyes.
- One piece, nothing else: no body, no text, no frame.
- Fully transparent background."""


def layout(pdir):
    """How the head piece is laid on the SIZE x SIZE picture shown to the model: (image, scale, x, y)."""
    im = Image.open(pdir / "parts" / "head.png").convert("RGBA")
    k = FIT / max(im.size)
    w, h = max(int(round(im.width * k)), 1), max(int(round(im.height * k)), 1)
    return im, k, (SIZE - w) // 2, (SIZE - h) // 2, w, h


def reference(pdir):
    im, _, x, y, w, h = layout(pdir)
    ref = Image.new("RGB", (SIZE, SIZE), "white")
    big = im.resize((w, h), Image.LANCZOS)
    ref.paste(big, (x, y), big)
    path = pdir / "_mouth_ref.png"
    ref.save(path)
    return path


def paint_mouth(pdir, model=oi.DEFAULT_MODEL, quality="medium", log=print):
    out = Path(pdir)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    png, usage, sec = G.call("edits", {"model": model, "size": f"{SIZE}x{SIZE}", "quality": quality, "output_format": "png",
                                       "n": 1, "background": "transparent",
                                       "prompt": PROMPT.format(character=meta["character"], style=meta["style"])},
                             images=[reference(out)])
    (out / "mouth_open.png").write_bytes(png)
    meta["calls"].append({"step": "mouth_open", "seconds": sec, "usage": usage})
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"mouth {sec} s")
    return out / "mouth_open.png"
