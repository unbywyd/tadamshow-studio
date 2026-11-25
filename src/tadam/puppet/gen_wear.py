"""Make the part of a puppet's head that is WORN: the headscarf, hat, helmet, hair or beard around the face.
When a recorded face (video) replaces the puppet's painted face, this piece stays on top of it.

usage: tadam.puppet.gen_wear.paint_wear(<puppet folder>, keep="<what stays>", hat="<the hat>")
  hat="<what it is>"     instead of a mask, take the puppet's own HAT off its head: writes <puppet>/hat.png.
                         With a hat the recorded head is shown whole and only the hat is put on it. This is the way
                         to go when the painted face is small (the engine refuses a hole it would have to blow up
                         more than 1.8 times).
Reads <puppet>/parts/head.png and meta.json; writes <puppet>/wear.png: the same head with the face
cut out (transparent), everything worn around it kept.
Run cut_skin.cut(<puppet folder>) afterwards: it lays the cut-out exactly over the puppet's own head, keeps the puppet's
own pixels where the new picture is opaque (so the scarf is the very same scarf), and writes the hole to rig.json
as parts.head.face, which is where the engine puts the recorded face.
"""
import json
from pathlib import Path

from tadam import openai_images as oi
from tadam.puppet import gen_mouth
from tadam.puppet import gen_skin as G
SIZE = gen_mouth.SIZE

PROMPT = """The image shows the head piece of a flat jointed puppet.
Make it a mask to wear: cut the FACE out, so that a real face can be seen through the hole.
Character: {character}.
Rules:
- The face becomes a hole, fully transparent: the skin of the face, the eyes, eyebrows, nose, mouth, cheeks, chin, glasses and the neck all go. The hole is one clean rounded opening, as wide as the face from cheek to cheek and reaching from the forehead to under the chin.
- Everything that is worn or grows around the face stays exactly as it is, in the same place and size: {keep}.
- Do not repaint or move what stays. Do not add anything: no body, no arms, no legs, no neck that is not there. The picture shows this one head piece and nothing else, with exactly the same outer outline as before.
- Fully transparent background, and fully transparent inside the hole."""

HAT_PROMPT = """The image shows the head piece of a flat jointed puppet.
Take the HAT off this head and show the hat alone: {hat}.
Character: {character}.
Rules:
- Only the hat stays. The face, the hair, the ears, the beard, the neck and the collar all go: fully transparent.
- It is the very same hat: same drawing style, same colours, same details, same size and same place in the picture.
- Where the head or the hair hid the lower edge of the hat, finish that edge, so the hat is whole.
- The hat is seen exactly from the front at eye level, never from below: its inside, its lining and the underside of its brim are NOT visible at all. The picture ends at the lower rim of the hat, which is one clean line, as if the hat already covered a head and hid everything inside it.
- Nothing else in the picture: no head, no mannequin, no shadow, no text. Fully transparent background."""

KEEP_DEFAULT = "the headscarf, hat, hood, helmet or crown, and the hair around the face"


def paint_wear(pdir, keep=KEEP_DEFAULT, hat="", model=oi.DEFAULT_MODEL, quality="medium", log=print):
    out = Path(pdir)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    png, usage, sec = G.call("edits", {"model": model, "size": f"{SIZE}x{SIZE}", "quality": quality, "output_format": "png",
                                       "n": 1, "background": "transparent",
                                       "prompt": (HAT_PROMPT.format(character=meta["character"], hat=hat) if hat
                                                  else PROMPT.format(character=meta["character"], keep=keep))},
                             images=[gen_mouth.reference(out)])
    target = out / ("hat.png" if hat else "wear.png")
    target.write_bytes(png)
    meta["calls"].append({"step": "hat" if hat else "wear", "seconds": sec, "usage": usage})
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wear {sec} s")
    return target
