"""Paint a prop for a scene: one object on a transparent background, upright, to be held in a puppet's hand.

usage: tadam.puppet.gen_prop.paint_prop(<out.png>, "<what it is>", style=S, hat=False, natural=False)
  hat      the object is a hat seen from the front as it sits on a head (its opening at the bottom). Save it as
           <puppet>/hat.png and run cut_skin.cut(<puppet folder>): a puppet with a hat wears it on top of a
           recorded head, and nothing else of its painted head is shown.
  natural  as it normally stands (a mug, a crate), not upright like a tool.
Writes the picture cropped to the object (a world keeps its props in media/). In a scene the actor's "props" say
which hand holds it, how long it is (in arm lengths) and where along its length the hand grips it.
"""
import io
from pathlib import Path

from PIL import Image

from tadam import openai_images as oi
from tadam.puppet import gen_skin as G

PROMPT = """One object for a puppet theatre, alone in the picture: {what}.
It stands exactly upright, vertical, seen flat from the front, the whole object visible with margins, its working end at the top and its handle at the bottom.
Style: {style}.
No hand holding it, no ground, no shadow, no text.
Fully transparent background."""


NATURAL_PROMPT = """One object for a puppet theatre, alone in the picture: {what}.
It is seen flat from the front at eye level, standing the way it normally stands, the whole object visible with margins.
Style: {style}.
No hand holding it, no ground, no shadow, no text.
Fully transparent background."""


HAT_PROMPT = """One hat for a puppet theatre character, alone in the picture: {what}.
Upright, symmetrical, the whole hat visible with margins.
The hat is seen exactly from the front at eye level, never from below: its inside, its lining and the underside of its brim are NOT visible at all. The picture ends at the lower rim of the hat, which is one clean line, as if the hat already covered a head and hid everything inside it.
Style: {style}.
No head, no face, no hair, no mannequin, no shadow, no text.
Fully transparent background."""


def paint_prop(out_png, what, style="storybook", hat=False, natural=False, model=oi.DEFAULT_MODEL,
               quality="medium", log=print):
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    png, usage, sec = G.call("generations", {"model": model, "size": "1024x1536", "quality": quality, "output_format": "png",
                                             "n": 1, "background": "transparent",
                                             "prompt": (HAT_PROMPT if hat else NATURAL_PROMPT if natural else PROMPT).format(
                                                 what=what, style=G.STYLES.get(style, style))})
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    alpha = im.split()[3].point(lambda v: 255 if v > 40 else 0)
    box = alpha.getbbox()
    if box:
        im = im.crop(box)
    im.save(out_png)
    log(f"prop {out_png.name} {im.size} {sec} s")
    return out_png
