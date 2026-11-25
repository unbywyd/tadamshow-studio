"""Builds a pattern rig: rig.json (the contract), the pattern sheet for the image model,
a mannequin skin cut from the same pattern, and an assembled preview that proves the joint maths.

usage: python -m tadam.puppet.make_rig [<out folder>]   (builds every variant; default: the kit's own rigs)
  rigs/humanoid-a        15 pieces
  rigs/humanoid-a-side   the same 15 pieces seen in PROFILE, facing right: the left column of the sheet is the FAR
                         arm and the far leg (drawn behind the body), the right column the NEAR ones; both
                         shoulders are one point in the middle of the chest, both hips one point in the pelvis.
                         Facing left is the same puppet mirrored by the engine.
  rigs/humanoid-a-side-skirt-<length>   the profile pattern with the same skirt piece: a character's skirt must be the
                         same length from every side, so its front and its side are painted on patterns of one length
  rigs/humanoid-a-skirt-<length>   length = short | knee | calf | floor
                         the same skeleton drawn at 0.85 of the size, plus a 16th piece in the free bottom left
                         corner: the skirt, which hangs from the waist in front of the legs. The image model paints
                         a skirt as long as its grey shape, whatever the text says, so each length has its own sheet.

Coordinates: everything is in SHEET pixels (the pattern sheet, y down). A part is a box on the sheet.
A joint has two points: `parent_at` inside the parent's box and `at` inside the child's box; in the
assembled puppet these two points coincide. Sides are SCREEN sides: `_l` is on the viewer's left.
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

from tadam.paths import RIGS
from tadam.jsonfile import write_json

OUT = RIGS                # where build() writes; main() may point it elsewhere
SKIRT_K = 0.85  # the skirt variant draws the body smaller, so a floor-length skirt has room in the corner
SKIRT_DX = 80   # ... and further right, so a wide skirt has room beside the legs
SKIRT_LENGTHS = {"short": 0.22, "knee": 0.5, "calf": 0.75, "floor": 0.97}   # share of the leg, hip to sole, it covers
SKIRT_FLARE = 0.17   # each side of the skirt goes out by this share of its length
K = 1.0         # the scale of the variant being drawn (set by build)
SHEET = (1024, 1536)
R = 28          # joint disc radius: both parts must be painted inside this circle
PAD = 14        # every part image is its box grown by PAD on each side
SS = 3          # supersampling for anti-aliased drawing

CX = 512
ARM_X = {"l": 180, "r": 844}
LEG_X = {"l": 440, "r": 584}


def build_parts():
    parts = {
        "pelvis": {"parent": None, "box": [397, 610, 230, 170], "shape": "block", "z": 30, "origin": [CX, 690]},
        "chest": {"parent": "pelvis", "box": [382, 300, 260, 280], "shape": "block", "z": 40,
                  "joint": {"name": "waist", "parent_at": [CX, 640], "at": [CX, 550]}, "limits": [-25, 25]},
        # the head's box is a wide free zone (hats, hair, ears); its drawn shape is the inner `shape_box`
        "head": {"parent": "chest", "box": [212, -230, 600, 500], "shape_box": [412, 30, 200, 240], "shape": "head", "z": 50,
                 "joint": {"name": "neck", "parent_at": [CX, 330], "at": [CX, 240]}, "limits": [-35, 35],
                 "face": {"center": [CX, 132], "size": [128, 168]}},
    }
    for s, x in ARM_X.items():
        shoulder_x = 412 if s == "l" else 612
        parts[f"upper_arm_{s}"] = {"parent": "chest", "box": [x - 50, 300, 100, 260], "shape": "limb", "z": 60,
                                   "joint": {"name": f"shoulder_{s}", "parent_at": [shoulder_x, 335], "at": [x, 330]},
                                   "limits": [-180, 180]}
        parts[f"forearm_{s}"] = {"parent": f"upper_arm_{s}", "box": [x - 45, 590, 90, 240], "shape": "limb", "z": 62,
                                 "joint": {"name": f"elbow_{s}", "parent_at": [x, 530], "at": [x, 620]},
                                 "limits": [-150, 150]}
        parts[f"hand_{s}"] = {"parent": f"forearm_{s}", "box": [x - 50, 860, 100, 130], "shape": "hand", "z": 64,
                              "joint": {"name": f"wrist_{s}", "parent_at": [x, 800], "at": [x, 890]},
                              "limits": [-80, 80], "grip": [x, 940], "tip": [x, 975]}
    for s, x in LEG_X.items():
        parts[f"thigh_{s}"] = {"parent": "pelvis", "box": [x - 58, 810, 116, 270], "shape": "limb", "z": 20,
                               "joint": {"name": f"hip_{s}", "parent_at": [x, 745], "at": [x, 840]},
                               "limits": [-120, 120]}
        parts[f"shin_{s}"] = {"parent": f"thigh_{s}", "box": [x - 50, 1110, 100, 260], "shape": "limb", "z": 18,
                              "joint": {"name": f"knee_{s}", "parent_at": [x, 1050], "at": [x, 1140]},
                              "limits": [-150, 150]}
        # the foot lies over the end of the shin (like the hand over the forearm), under the thigh
        parts[f"foot_{s}"] = {"parent": f"shin_{s}", "box": [x - 65, 1400, 130, 100], "shape": "foot", "z": 19,
                              "joint": {"name": f"ankle_{s}", "parent_at": [x, 1340], "at": [x, 1430]},
                              "limits": [-40, 40], "sole": [x, 1492]}
    return parts


def side_parts():
    """The profile pattern, made from the front one. `_l` pieces are the far side, `_r` the near side."""
    parts = build_parts()
    parts["chest"]["box"] = [412, 300, 200, 280]
    parts["pelvis"]["box"] = [422, 610, 180, 170]
    parts["head"]["draw"] = "head_side"
    parts["chest"]["limits"] = [-25, 100]      # seen from the side a puppet can bow: forward is clockwise
    for _s in "lr":                            # ...and lift its thigh far forward: to sit on the floor, to kick
        parts[f"thigh_{_s}"]["limits"] = [-160, 160]
    parts["head"]["limits"] = [-45, 50]
    for s, far in (("l", True), ("r", False)):
        parts[f"upper_arm_{s}"]["joint"]["parent_at"] = [CX, 345]
        parts[f"thigh_{s}"]["joint"]["parent_at"] = [CX, 740]
        dx = -40 if far else 16                            # the legs further apart on the sheet: side feet are long
        for n in ("thigh", "shin", "foot"):
            q = parts[f"{n}_{s}"]
            q["box"][0] += dx
            q["joint"]["at"][0] += dx
            if n != "thigh":
                q["joint"]["parent_at"][0] += dx
        foot = parts[f"foot_{s}"]
        x = LEG_X[s] + dx
        foot["box"] = [x - 45, 1400, 150, 100]             # the toe points right, the ankle is over the heel
        foot["sole"] = [x + 20, 1492]
        foot["draw"] = "foot_side"
        foot["limits"] = [-75, 75]                         # a squat leans the shin far forward and the foot stays flat
        z = {"upper_arm": 60, "forearm": 62, "hand": 64, "thigh": 20, "shin": 18, "foot": 19}
        if far:                                            # the far arm behind the far leg, both behind the body
            z = {"upper_arm": 5, "forearm": 6, "hand": 7, "thigh": 14, "shin": 12, "foot": 13}
        for n, v in z.items():
            parts[f"{n}_{s}"]["z"] = v
    return parts


def scaled(parts, k, dx=0):
    """The same pattern drawn `k` times the size, about the top centre of the sheet, then moved `dx` to the right."""
    def pt(v):
        return [round(CX + dx + (v[0] - CX) * k, 1), round(v[1] * k, 1)]

    def box(b):
        return pt(b[:2]) + [round(b[2] * k, 1), round(b[3] * k, 1)]

    out = {}
    for n, p in parts.items():
        q = dict(p)
        for key in ("box", "shape_box"):
            if key in q:
                q[key] = [int(round(v)) for v in box(q[key])]
        for key in ("origin", "grip", "tip", "sole"):
            if key in q:
                q[key] = pt(q[key])
        if "joint" in q:
            q["joint"] = {"name": q["joint"]["name"], "parent_at": pt(q["joint"]["parent_at"]), "at": pt(q["joint"]["at"])}
        if "face" in q:
            q["face"] = {"center": pt(q["face"]["center"]), "size": [round(v * k, 1) for v in q["face"]["size"]]}
        out[n] = q
    return out


def add_skirt(parts, share):
    """The 16th piece. On the sheet it lies alone in the bottom left corner; on the puppet its waistband sits on
    the top of the pelvis and its hem covers `share` of the leg. Drawn after the legs and the pelvis, before the chest."""
    top = parts["pelvis"]["box"][1]
    mid = parts["pelvis"]["box"][0] + parts["pelvis"]["box"][2] / 2
    depth = 20
    hip = parts["thigh_l"]["joint"]["parent_at"][1]
    leg = (parts["shin_l"]["joint"]["parent_at"][1] - parts["thigh_l"]["joint"]["at"][1]
           + parts["foot_l"]["joint"]["parent_at"][1] - parts["shin_l"]["joint"]["at"][1]
           + parts["foot_l"]["sole"][1] - parts["foot_l"]["joint"]["at"][1])
    h = int(round(hip - top + share * leg))
    w = int(round(parts["pelvis"]["box"][2] * 1.05 + 2 * SKIRT_FLARE * h))
    box = [40, 880, w, h]
    parts["skirt"] = {"parent": "pelvis", "box": box, "shape": "skirt", "z": 35,
                      "joint": {"name": "skirt", "parent_at": [mid, top + depth], "at": [box[0] + box[2] / 2, box[1] + depth]},
                      "limits": [-25, 25]}
    return parts


def draw_shape(d, shape, box, fill, outline, width):
    x, y, w, h = [v * SS for v in box]
    lw = width * SS
    k = K * SS
    if shape == "limb":
        d.rounded_rectangle([x, y, x + w, y + h], radius=w // 2, fill=fill, outline=outline, width=lw)
    elif shape == "block":
        d.rounded_rectangle([x, y, x + w, y + h], radius=int(52 * k), fill=fill, outline=outline, width=lw)
    elif shape == "head":
        neck_w = int(76 * k)
        d.rounded_rectangle([x + w // 2 - neck_w // 2, y + int(h * 0.62), x + w // 2 + neck_w // 2, y + h],
                            radius=neck_w // 2, fill=fill, outline=outline, width=lw)
        d.ellipse([x + int(6 * k), y, x + w - int(6 * k), y + int(h * 0.80)], fill=fill, outline=outline, width=lw)
    elif shape == "hand":
        wrist_w = int(64 * k)
        d.rounded_rectangle([x + w // 2 - wrist_w // 2, y, x + w // 2 + wrist_w // 2, y + int(h * 0.55)],
                            radius=wrist_w // 2, fill=fill, outline=outline, width=lw)
        d.ellipse([x + int(4 * k), y + int(h * 0.28), x + w - int(4 * k), y + h], fill=fill, outline=outline, width=lw)
    elif shape == "foot":
        ankle_w = int(64 * k)
        d.rounded_rectangle([x + w // 2 - ankle_w // 2, y, x + w // 2 + ankle_w // 2, y + int(h * 0.7)],
                            radius=ankle_w // 2, fill=fill, outline=outline, width=lw)
        d.rounded_rectangle([x, y + int(h * 0.42), x + w, y + h], radius=int(28 * k), fill=fill, outline=outline, width=lw)
    elif shape == "head_side":                   # a profile facing right: the nose sticks out, the neck is a bit back
        neck_w = int(76 * k)
        nx = x + int(w * 0.44)
        d.rounded_rectangle([nx - neck_w // 2, y + int(h * 0.62), nx + neck_w // 2, y + h],
                            radius=neck_w // 2, fill=fill, outline=outline, width=lw)
        nose = [(x + w - int(14 * k), y + int(h * 0.32)), (x + w + int(20 * k), y + int(h * 0.46)),
                (x + w - int(14 * k), y + int(h * 0.54))]
        d.polygon(nose, fill=fill)
        d.line(nose, fill=outline, width=lw, joint="curve")
        d.ellipse([x + int(6 * k), y, x + w - int(6 * k), y + int(h * 0.80)], fill=fill, outline=outline, width=lw)
    elif shape == "foot_side":                   # the ankle over the heel, the toe to the right
        ankle_w = int(64 * k)
        ax = x + int(45 * k)
        d.rounded_rectangle([ax - ankle_w // 2, y, ax + ankle_w // 2, y + int(h * 0.7)],
                            radius=ankle_w // 2, fill=fill, outline=outline, width=lw)
        d.rounded_rectangle([x, y + int(h * 0.42), x + w, y + h], radius=int(28 * k), fill=fill, outline=outline, width=lw)
    elif shape == "skirt":                       # a waistband on top of a flared trapezoid
        inset = int(SKIRT_FLARE * h)
        body = [(x + inset, y + 8 * SS), (x + w - inset, y + 8 * SS), (x + w, y + h), (x, y + h)]
        d.polygon(body, fill=fill)
        d.line(body + body[:1], fill=outline, width=lw, joint="curve")
        d.rounded_rectangle([x + inset - 4 * SS, y, x + w - inset + 4 * SS, y + 34 * SS], radius=12 * SS,
                            fill=fill, outline=outline, width=lw)


def render_sheet(parts, *, bg, fill, outline, markers):
    img = Image.new("RGBA", (SHEET[0] * SS, SHEET[1] * SS), bg)
    d = ImageDraw.Draw(img)
    for p in parts.values():
        draw_shape(d, p.get("draw", p["shape"]), p.get("shape_box", p["box"]), fill, outline, 3)
    if markers:
        for name, p in parts.items():
            pts = [p["joint"]["at"]] if "joint" in p else []
            pts += [c["joint"]["parent_at"] for c in parts.values() if c.get("parent") == name]
            for (jx, jy) in pts:
                r = R * K
                d.ellipse([(jx - r) * SS, (jy - r) * SS, (jx + r) * SS, (jy + r) * SS], outline=markers, width=2 * SS)
                d.ellipse([(jx - 4) * SS, (jy - 4) * SS, (jx + 4) * SS, (jy + 4) * SS], fill=markers)
    return img.resize(SHEET, Image.LANCZOS)


def crop_part(sheet, box):
    x, y, w, h = box
    return sheet.crop((x - PAD, y - PAD, x + w + PAD, y + h + PAD))


def rest_positions(parts):
    """Sheet-space offset of every part in the assembled rest pose (all joint angles 0)."""
    shift = {}

    def resolve(name):
        if name in shift:
            return shift[name]
        p = parts[name]
        if p["parent"] is None:
            shift[name] = (0, 0)
        else:
            px, py = resolve(p["parent"])
            j = p["joint"]
            shift[name] = (int(round(px + j["parent_at"][0] - j["at"][0])), int(round(py + j["parent_at"][1] - j["at"][1])))
        return shift[name]

    for n in parts:
        resolve(n)
    return shift


def assemble(parts, images, shift):
    xs = [p["box"][0] + shift[n][0] for n, p in parts.items()] + [p["box"][0] + p["box"][2] + shift[n][0] for n, p in parts.items()]
    ys = [p["box"][1] + shift[n][1] for n, p in parts.items()] + [p["box"][1] + p["box"][3] + shift[n][1] for n, p in parts.items()]
    x0, y0, x1, y1 = min(xs) - PAD, min(ys) - PAD, max(xs) + PAD, max(ys) + PAD
    canvas = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    for n, p in sorted(parts.items(), key=lambda kv: kv[1]["z"]):
        canvas.alpha_composite(images[n], (p["box"][0] + shift[n][0] - PAD - x0, p["box"][1] + shift[n][1] - PAD - y0))
    return canvas, [x0, y0, x1 - x0, y1 - y0]


def build(name, parts, scale, extra=None):
    global K
    K = scale
    out = OUT / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "mannequin").mkdir(exist_ok=True)

    # 1. the pattern sheet the image model repaints
    template = render_sheet(parts, bg=(255, 255, 255, 255), fill=(222, 222, 222, 255), outline=(70, 70, 70, 255), markers=(150, 150, 150, 255))
    template.convert("RGB").save(out / "template.png")

    # 2. the mannequin skin: same shapes, wooden, transparent background, no markers
    wood = render_sheet(parts, bg=(0, 0, 0, 0), fill=(214, 170, 112, 255), outline=(92, 62, 34, 255), markers=None)
    images = {n: crop_part(wood, p["box"]) for n, p in parts.items()}
    for n, im in images.items():
        im.save(out / "mannequin" / f"{n}.png")

    shift = rest_positions(parts)
    preview, bbox = assemble(parts, images, shift)
    preview.save(out / "mannequin_rest.png")

    rig = {
        "rig": f"{name}@1",
        "sheet": list(SHEET),
        "joint_radius": R if scale == 1.0 else round(R * scale, 1),
        "pad": PAD,
        "sides": "screen: _l is on the viewer's left",
        "rest_bbox": bbox,
        "draw_order": [n for n, _ in sorted(parts.items(), key=lambda kv: kv[1]["z"])],
        "handles": {
            "body": {"part": "pelvis"},
            "chest": {"part": "chest", "kind": "angle"},
            "head": {"part": "head", "kind": "angle"},
            "hand_l": {"ik": ["upper_arm_l", "forearm_l"], "end": "hand_l"},
            "hand_r": {"ik": ["upper_arm_r", "forearm_r"], "end": "hand_r"},
            "foot_l": {"ik": ["thigh_l", "shin_l"], "end": "foot_l"},
            "foot_r": {"ik": ["thigh_r", "shin_r"], "end": "foot_r"},
        },
        "parts": {n: {k: v for k, v in p.items() if k not in ("shape", "draw")} | {"kind": p["shape"]} for n, p in parts.items()},
    } | (extra or {})
    write_json(out / "rig.json", rig, indent=2)
    print(name, "parts:", len(parts), "rest bbox:", bbox)


def main(argv=None):
    import sys
    global OUT
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        OUT = Path(args[0])
    build("humanoid-a", build_parts(), 1.0)
    build("humanoid-a-side", side_parts(), 1.0, {"view": "side"})
    build("humanoid-a-back", build_parts(), 1.0, {"view": "back"})     # the front pattern, seen from behind
    for length, share in SKIRT_LENGTHS.items():
        build(f"humanoid-a-skirt-{length}", add_skirt(scaled(build_parts(), SKIRT_K, SKIRT_DX), share), SKIRT_K,
              {"skirt_length": share})
        build(f"humanoid-a-back-skirt-{length}", add_skirt(scaled(build_parts(), SKIRT_K, SKIRT_DX), share), SKIRT_K,
              {"skirt_length": share, "view": "back"})
        side_skirt = add_skirt(scaled(side_parts(), SKIRT_K, SKIRT_DX + 30), share)
        side_skirt["skirt"]["limits"] = [-100, 100]     # in profile a seated skirt lies forward over the lap
        build(f"humanoid-a-side-skirt-{length}", side_skirt, SKIRT_K, {"skirt_length": share, "view": "side"})


if __name__ == "__main__":
    main()
