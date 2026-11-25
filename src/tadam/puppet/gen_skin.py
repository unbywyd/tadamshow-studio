"""Paint a puppet with the OpenAI image API: a character portrait, then the repainted pattern sheet.

    tadam.puppet.gen_skin.paint(pdir, "<character>", rig="humanoid-a", style="<style>")

  rig humanoid-a          15 pieces (default)
  rig humanoid-a-skirt-<short|knee|calf|floor>
                          16 pieces: the same body plus a skirt of that length, which hangs from the waist in front
                          of the legs. For a character in a skirt, a dress, a gown, a robe or a kilt.
  style wood | cartoon | storybook | ... | "<any description>" (a world passes the style of its bible)

A VIEW of a character is a puppet of its own inside the character's puppet folder: <puppet>/side, <puppet>/back.
It is painted from the character's one portrait (<puppet>/portrait.png) on the matching profile pattern.
The key is read from the OPENAI_API_KEY environment variable only (tadam.openai_images).
Writes <pdir>/{portrait.png, sheet.png, meta.json}.
"""
from __future__ import annotations

import json
from pathlib import Path

from tadam import imgio
from tadam import openai_images as oi
from tadam.paths import RIGS as RIGS_DIR
from tadam.puppet import puppet_name
from tadam.jsonfile import write_json

STYLES = {
    "wood": ("a hand-painted wooden jointed puppet toy: flat front view, matte paint on carved wood, "
             "clear dark outline, a limited warm palette, even flat lighting, no cast shadows"),
    "cartoon": ("a modern 2D cartoon character from a children's animated series, made for cut-out animation: clean "
                "simple shapes, flat bright colours with one soft shadow tone, a thin dark outline, friendly "
                "proportions. Not a toy and not made of wood: no wood grain, no visible joints, pins, hinges or balls. "
                "Flat front view, even flat lighting, no cast shadows"),
    "storybook": ("a hand-painted children's storybook illustration in gouache: soft matte colours, a gentle brush "
                  "texture, a thin warm dark outline, expressive but simple shapes. Not a toy and not made of wood: "
                  "no wood grain, no visible joints, pins, hinges or balls. Flat front view, even flat lighting, "
                  "no cast shadows"),
}
STYLES["yokai"] = (
    "an eerie dark-fairytale illustration that mixes old Japanese yokai folklore prints with gothic European picture "
    "books: slightly wobbly hand-inked contour lines, fine hatching, flat muted night colours (deep teal, indigo, moss "
    "green, ash grey) with a few small warm accents of lantern orange and bone white, grainy paper texture. Creepy but "
    "whimsical and a little funny, strange proportions. Not a toy and not made of wood: no wood grain, no visible "
    "joints, pins, hinges or balls. Flat front view, even flat lighting, no cast shadows")
STYLES["ink"] = (
    "a rough hand-drawn cartoon in the manner of late-Soviet auteur cel animation and its comic adventure games: "
    "thick, uneven black brush-and-ink outlines with blots, stray strokes and scribbled hatching; flat saturated "
    "gouache colours filled in a little carelessly, with no gradients; bulging round white eyes with tiny pupils, a "
    "round red nose, red blush spots on the cheeks; lumpy potato-like shapes, everything a little crooked and funny. "
    "Absolutely no realistic texture, no photographic detail, no 3D shading, no soft rendering. Not a toy and not "
    "made of wood: no visible joints, pins, hinges or balls. Flat front view, even flat lighting, no cast shadows")
STYLES["clay"] = (
    "a handmade plasticine (modelling clay) stop-motion puppet, photographed: soft rounded sculpted shapes, a matte "
    "clay surface with faint fingerprints and tool marks, big round white bead eyes with small dark pupils, a big "
    "rounded nose, simple sausage-like arms ending in small rounded mitten hands without separate fingers, slightly "
    "crooked and funny proportions, muted earthy colours. Not wood: no visible joints, pins, hinges or balls. Flat "
    "front view, soft even frontal studio light, very gentle shading, no cast shadows")
STYLES["clay_relief"] = (
    "a flat plasticine relief, as in old hand-made clay cut-out animation: the figure is modelled from coloured "
    "plasticine pressed flat on a board, only slightly raised, a matte clay surface with fingerprints and smears, "
    "rolled clay strands for hair and moustaches, big round white bead eyes with small dark pupils, small rounded "
    "mitten hands without separate fingers, lumpy, crooked and funny shapes, muted warm colours. Not wood: no visible "
    "joints, pins, hinges or balls. Flat front view, soft even frontal light, no cast shadows")
STYLES["board"] = (
    "a jointed puppet cut from flat plywood boards and PAINTED BY HAND WITH A BRUSH, like a naive folk toy or a "
    "puppet-theatre prop: every board is painted in flat areas of matte colour with broad, visible, slightly careless "
    "brush strokes; clothes, patterns and details are simplified and painted, never real fabric: checks are a few "
    "crossing painted stripes, flowers are simple painted blobs, folds are one darker brush stroke; no fine texture, "
    "no fabric weave, no fur, no photographic detail; the plywood shows a little at the sanded rounded edges. NO pegs, "
    "pins, dots or circles painted at the joints, and no light wooden discs or end-grain circles at the ends of the "
    "pieces: the rounded end of every piece is painted just like the rest of it (the engine adds one peg per joint). Only the head is different: a sculpted plasticine (modelling clay) "
    "head, big for the body, with big round white bead eyes and funny exaggerated features, stuck on a short round "
    "wooden dowel stick instead of a neck. The hands are plain black glove shapes, the feet are simple painted shoes. "
    "Flat front view, soft even frontal light, no cast shadows")
STYLES["piying"] = (
    "a traditional shadow-play puppet of the old Chinese folk theatre, made of thin translucent dyed leather and lit "
    "from behind: every piece is a flat sheet of parchment-like leather, finely carved with openwork ornament (scrolls, "
    "clouds, flowers, rows of small dots, lattice borders) and coloured with transparent dyes in saturated vermilion "
    "red, jade green, turquoise blue, golden yellow and black, like stained glass; crisp, fine, elegant cut contours; "
    "black borders on hems and cuffs; the face is pale natural cream leather with fine carved lines for the brows, the "
    "eye, the nose and a small red mouth; wide flaring sleeves; long elegant proportions. The carved openwork is painted "
    "as fine pale cream lines and small light shapes on the colour, NOT as real holes: every piece is one solid "
    "connected shape. The hands are small carved leather hands with slender fingers. No rods, sticks or strings, no "
    "pins, knots or rivets at the joints. Flat view, the light shining evenly through the leather, no cast shadows")
STYLES["poster"] = (
    "a modern flat editorial illustration, like a contemporary screen-printed (risograph) poster: bold flat areas of "
    "colour with no gradients and no shading, a limited bright palette of cobalt blue, coral red, bubblegum pink, grass "
    "green and warm cream, crisp thin dark ink outlines drawn by hand, a light grainy print texture with tiny speckles; "
    "bold graphic patterns on the clothes (checkerboard, gingham, polka dots, stripes); quirky stylised elongated "
    "proportions, long necks, small faces with tiny features and bright red lips, oversized retro sunglasses; playful, "
    "fashionable, a little absurd and funny. Not a toy and not made of wood: no visible joints, pins, hinges or balls. "
    "Flat front view, even flat lighting, no cast shadows")
STYLES["paper"] = (
    "a character drawn by hand on thick white watercolour paper and then CUT OUT with scissors along its outline: a "
    "crisp black ink drawing with slightly scratchy lines and fine hatching, coloured with watercolour and coloured "
    "pencil in muted natural tones (mustard, olive, teal, rust, grey-blue), soft washes with visible paper grain and "
    "pigment blooms; slightly caricatured, deadpan, a little melancholic and funny: a big head with a long face, big "
    "expressive or tired half-closed eyes, a big nose, rosy cheeks; modern everyday clothes. A thin sliver of white "
    "paper shows along the cut edge. Not a toy and not made of wood: no visible joints, pins, hinges or balls. Flat "
    "front view, soft even light, no cast shadows")
STYLES["paper_muted"] = (
    "a character drawn by hand on thick white paper and then CUT OUT with scissors along its outline: a fine, slightly "
    "scratchy black ink drawing with soft marker and coloured-pencil shading; an almost monochrome, quiet palette: the "
    "clothes in cold greys, slate grey-blue and charcoal, softly shaded, with only the skin and the hair keeping a "
    "faint warm tone (pale skin, pink cheeks and nose); NO bright or saturated colours anywhere; slightly caricatured, "
    "deadpan, bored and a little grumpy: a big head with heavy-lidded sleepy eyes, a long thin nose, small pursed "
    "lips; modern everyday clothes. A thin sliver of white paper shows along the cut edge. Not a toy and not made of "
    "wood: no visible joints, pins, hinges or balls. Flat front view, soft even light, no cast shadows")
STYLES["paper_soft"] = (
    "a character drawn by hand on thick white paper and then CUT OUT with scissors along its outline: a lively black "
    "ink drawing with slightly scratchy lines and light hatching, coloured with soft watercolour and coloured pencil in "
    "muted natural tones (olive green, teal, rust brown, peach, mustard, faded denim blue), never bright or neon, with "
    "visible paper grain; a slightly caricatured, charming cartoon look: a big head, BIG ROUND expressive eyes with "
    "light irises, a big nose, freckles and rosy cheeks, a long thin neck; modern everyday clothes. A thin sliver of "
    "white paper shows along the cut edge. Not a toy and not made of wood: no visible joints, pins, hinges or balls. "
    "Flat front view, soft even light, no cast shadows")
STYLES["ink_night"] = (
    "a modern East Asian graphic-novel illustration with the feel of a woodblock print: confident dark ink outlines, "
    "flat layered colour with a subtle print grain and fine ink hatching in the folds, a deep night palette of indigo, "
    "slate blue and teal, with small warm accents of amber, ochre and dull red; serious, cinematic and a little "
    "mysterious, with a touch of dry humour in the faces; elegant long proportions, historical Chinese clothes drawn "
    "with long clean folds. Not a toy and not made of wood: no visible joints, pins, hinges or balls. Flat front view, "
    "even flat lighting, no cast shadows")
STYLES["naive_ink"] = (
    "a naive outsider-art illustration: dense fine black pen hatching and scratchy ink lines, flat matte gouache colours "
    "(mustard, grey-green, slate, brick red, cream) with speckled and flecked patterned fabrics, pale mask-like faces "
    "with tiny dot eyes, a long nose and small red lips, stiff deadpan poses, eerie and quietly funny. The hands and "
    "the shoes are drawn as their own small shapes with nothing painted around them. Not a toy and not made of wood: "
    "no visible joints, pins, hinges or balls. Flat front view, even flat lighting, no cast shadows")
STYLES["photo_bokeh"] = (
    "a real photograph taken with a fast lens: a very shallow depth of field, the whole place softly out of focus with "
    "creamy round bokeh lights, warm natural late-afternoon light, muted film colours, fine film grain")
STYLE_DEFAULT = "wood"

PORTRAIT_PROMPT = """Full-body character design, one character, front view, standing straight in a neutral pose with arms hanging slightly away from the body and legs apart, the whole figure visible from head to feet with margins.
Character: {character}.
Style: {style}.
Plain light background, no text, no props on the ground."""

BODY_PIECES = ("the head with a neck stub at the top; the chest below it; the pelvis below the chest; an arm on each side as "
               "three pieces from top to bottom (upper arm, forearm, hand); a leg on each side below the pelvis as three "
               "pieces from top to bottom (thigh, shin, foot)")
# per pattern: how many pieces, what the model is told is on the sheet, and extra rules
RIGS = {
    "humanoid-a": {"count": 15, "pieces": BODY_PIECES + ".", "rules": ""},
}
RIGS["humanoid-a-side"] = {
    "count": 15,
    "pieces": ("this puppet is seen in PROFILE, from its side, FACING RIGHT. The head in profile with a neck stub at the "
               "top; the chest seen from the side below it; the pelvis seen from the side below the chest; an arm on each "
               "side as three pieces from top to bottom (upper arm, forearm, hand): the LEFT column is the FAR arm, the one "
               "on the other side of the body, the RIGHT column is the NEAR arm; a leg on each side below the pelvis as "
               "three pieces (thigh, shin, foot): the left one is the FAR leg, the right one the NEAR leg."),
    "rules": """
- Everything is seen from the side, facing right: the head is a profile (one eye, the nose and chin pointing right, the back of the head on the left), the chest and the pelvis are side views (the belly and chest to the right, the back to the left), both feet are side views with the toes pointing right and the heel under the ankle, the hands are seen from the side with the thumb in front.
- The far arm and the far leg are the same as the near ones, painted a little darker, because they are on the other side of the body.
- It is the same character as in the second image, with the same clothes, colours and proportions, only seen from the side.""",
}
BACK_RULES = """
- This puppet is seen from BEHIND: its back is to us. The head shows the back of the head (hair, the back of a hat or a headscarf, the back of the ears), no face at all. The chest and the pelvis show the back and the bottom of the clothes, the hands show their backs, the feet show their heels.
- The LEFT column of the pattern is the character's LEFT arm and leg (seen from behind they are on our left).
- It is the same character as in the second image, with the same clothes, colours and proportions, only seen from behind."""
RIGS["humanoid-a-back"] = {"count": 15, "pieces": BODY_PIECES + ".", "rules": BACK_RULES}
SKIRT_RULES = """
- The skirt piece is the whole lower part of this character's skirt, dress, gown, robe or kilt, from the waist down: one flat piece seen from the front, hanging straight, with a straight waistband at the top. Its grey shape already has the right length for this character ({length}): keep that length, that width and that proportion. On the finished puppet it hangs from the waist in front of the legs.
- The pelvis and the leg pieces show what is UNDER the skirt: the pelvis is plain underwear, bloomers or a petticoat, and the legs are bare legs, stockings or tights, with the shoes on the feet. Do not paint the skirt on the pelvis or on the legs.
- Each leg is still three separate pieces (thigh, shin, foot) with empty space between them, even when the leg is bare or wears one long stocking.
- The skirt piece stays in its corner and never touches the legs, the hand above it or the edge of the image."""
for _name, _length in (("short", "very short, it ends high on the thighs"), ("knee", "knee-length"),
                       ("calf", "down to the middle of the calves"), ("floor", "floor-length, it ends at the ankles")):
    RIGS[f"humanoid-a-side-skirt-{_name}"] = {
        "count": 16,
        "pieces": RIGS["humanoid-a-side"]["pieces"] + " And one more piece alone in the bottom left corner: the skirt, "
                                                      "a flat flared shape with a waistband at its top.",
        "rules": RIGS["humanoid-a-side"]["rules"] + SKIRT_RULES.format(length=_length).replace(
            "one flat piece seen from the front", "one flat piece seen from the side"),
    }
    RIGS[f"humanoid-a-back-skirt-{_name}"] = {
        "count": 16,
        "pieces": BODY_PIECES + "; and one more piece alone in the bottom left corner: the skirt, a flat flared shape "
                                "with a waistband at its top.",
        "rules": BACK_RULES + SKIRT_RULES.format(length=_length).replace("one flat piece seen from the front",
                                                                         "one flat piece seen from behind"),
    }
    RIGS[f"humanoid-a-skirt-{_name}"] = {
        "count": 16,
        "pieces": BODY_PIECES + "; and one more piece alone in the bottom left corner: the skirt, a flat flared shape "
                                "with a waistband at its top.",
        "rules": SKIRT_RULES.format(length=_length),
    }

SHEET_PROMPT = """The first image is a cutting pattern for a flat jointed puppet, drawn as an exploded view of {count} separate grey pieces: {pieces}
{ref_line}
Paint this character as the puppet kit: one painted piece for every grey piece of the pattern, in the same arrangement and orientation. The pattern fixes WHICH pieces exist and WHERE they sit, not their proportions: give every piece the width, length and outline that fit this character's build — a fat character has a wide round chest and pelvis and thick limbs, a thin one has narrow long pieces, a child has a big head and short limbs, a strongman has huge upper arms, a monster may have long arms and short legs.
Character: {character}.
Style: {style}.
Rules:
- All {count} pieces stay separate, with empty transparent space between them. Pieces never touch or overlap.
- Pieces may be bigger or smaller than their grey shapes, but each stays centred on its own grey shape and far from its neighbours. Hair, a hat or cuffs belong to their piece.
- Both ends of every limb piece are rounded and fully painted in the colour of that body part or its clothing, because the pieces overlap at the joints. The neck is a rounded stub under the head. The top of the chest and the bottom of the pelvis are fully painted too.
- The clothing continues logically from piece to piece: sleeves on the arm pieces, trousers or stockings on the leg pieces, shoes on the feet.
- Left and right pieces mirror each other. Flat view, even flat lighting, no cast shadows, no ground.
- Do not draw the pattern's grey outlines, circles or dots. No text, no labels, no frame.{rules}
- Fully transparent background."""


def call(endpoint, fields, images=None):
    """One image from the API: (png bytes, usage, seconds). Raises oi.GenerationError."""
    return oi.call(endpoint, fields, images)


def front_sizes(pdir):
    """The front kit's sizes against the body's height (neck to sole): head height, chest width."""
    from PIL import Image
    rig = json.loads((pdir / "rig.json").read_text(encoding="utf-8"))
    bh = float(rig["body_height"])
    out = {}
    for part, key, i in (("head", "head_h", 3), ("chest", "chest_w", 2)):
        bb = Image.open(pdir / "parts" / f"{part}.png").getbbox()
        out[key] = ((bb[i] - bb[i - 2]) / bh) if bb else 0.0
    return out


def is_view(pdir: Path) -> bool:
    """<puppet>/side or <puppet>/back next to the character's own portrait: a view of that character."""
    return pdir.name in ("side", "back") and (pdir.parent / "portrait.png").exists()


def paint(pdir: Path, character: str, *, style: str = STYLE_DEFAULT, model: str = oi.DEFAULT_MODEL,
          quality: str = "medium", size: str = "1024x1536", rig: str = "humanoid-a", no_portrait: bool = False,
          reuse_portrait: bool = False, log=print) -> dict:
    """Paint the portrait (unless there is one to reuse) and the pattern sheet into pdir. Returns meta.json."""
    if rig not in RIGS:
        raise ValueError(f"unknown rig {rig!r}: {', '.join(sorted(RIGS))}")
    style = STYLES.get(style, style)
    out = Path(pdir)
    out.mkdir(parents=True, exist_ok=True)
    template = RIGS_DIR / rig / "template.png"
    base = {"model": model, "size": size, "quality": quality, "output_format": "png", "n": 1}
    meta = {"name": puppet_name(out), "character": character,
            "style": style, "rig": rig, "model": model, "quality": quality, "size": size, "calls": []}
    if reuse_portrait and (out / "meta.json").exists():
        # a repainted sheet: the calls painted before (the portrait, the earlier sheets) stay on the record
        try:
            meta["calls"] = list(json.loads((out / "meta.json").read_text(encoding="utf-8")).get("calls") or [])
        except (OSError, ValueError, AttributeError):
            pass

    refs = [template]
    view = is_view(out)
    own = out.parent / "portrait.png"          # a view (<puppet>/side) is painted from the character's portrait
    if view:
        refs.append(own)
    elif reuse_portrait and (out / "portrait.png").exists():
        refs.append(out / "portrait.png")
    elif not no_portrait:
        png, usage, sec = call("generations", base | {"background": "opaque",
                               "prompt": PORTRAIT_PROMPT.format(character=character, style=style)})
        imgio.write_png_bytes(png, out / "portrait.png")
        meta["calls"].append({"step": "portrait", "seconds": sec, "usage": usage})
        log(f"portrait {sec} s")
        refs.append(out / "portrait.png")

    ref_line = ("The second image is the character to paint." if len(refs) > 1 else "")
    # a VIEW (side, back) of a character that has its front kit already: the kit goes along as the third image, with
    # its sizes in words. Without it a heavy character came out slim in profile, with a smaller head: the model
    # filled the profile pattern's average shapes (audit "views" now rejects that)
    front_sheet = out.parent / "sheet.png"
    if view and front_sheet.exists() and (out.parent / "rig.json").exists():
        refs.append(front_sheet)
        sz = front_sizes(out.parent)
        heavy = sz["chest_w"] >= 0.45
        ref_line += (" The third image is THIS character's own kit seen from the FRONT, already painted: the new kit is the"
                     " same body from another side and keeps its sizes. The head is exactly as tall as the front head"
                     f" (about {sz['head_h']:.0%} of the height from the neck to the soles), the limbs as thick and as long.")
        if "side" in rig:
            ref_line += (f" Seen from the side the chest and the pelvis are {'nearly as deep as they are wide from the front: a heavy, round body, the belly and the chest bulging forward far past the hips' if heavy else 'about two thirds as deep as they are wide from the front'}"
                         " - never a thin slice.")
    png, usage, sec = call("edits", base | {"background": "transparent",
                           "prompt": SHEET_PROMPT.format(ref_line=ref_line, character=character, style=style,
                                                         **RIGS[rig])}, images=refs)
    imgio.write_png_bytes(png, out / "sheet.png")
    meta["calls"].append({"step": "sheet", "seconds": sec, "usage": usage})
    log(f"sheet {sec} s")
    write_json(out / "meta.json", meta, indent=2)
    return meta
