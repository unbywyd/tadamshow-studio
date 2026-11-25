"""CHECKS ONE ENGINE SCENE (the scene.json that engine/stage.gd plays) before it is filmed: every mistake a scene can
have, in plain words, plus where the heroes stand in the picture.

ONE module for the kit and the server: pure functions over JSON. Nothing here starts Godot, reads a file or touches
the network by itself; whatever the checks need to know about the world outside the scene (which actions, items,
sounds and colour grades the engine has, which files exist, what a puppet looks like) comes in a `Context`.
`Context.from_engine()` builds one from an engine folder on disk; the server can build its own from its data.

    issues = check_scene(scene_dict, ctx, where="sh3")      -> [Issue(level, where, code, message), ...]

What is checked (the codes are in CODES):
  1. the file: an unknown command, a hero, action, point, thing, instrument, view, sound or picture that does not
     exist, a time that cannot be worked out ("after" something nobody does, a phrase the voice does not have, a beat
     without the music's tempo), two actions at once that take the same part of the body;
  2. the picture (studio rules, docs: shooting): a vertical film, at most 3 heroes (a shot of a place or a thing has none), every hero in the frame and not standing
     on another one at the same depth, always facing us (no profile, no back, no walking sideways), the camera from
     the catalogue of framings.
What only the engine can tell (a hero that talks off the picture, a recorded face too small) is the engine's own
`--check` run (tadam.engine.run_check).
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tadam.issues import Issue

TIME_KEYS = {"at", "after", "of", "label", "delay", "phrase", "end", "voice", "beat"}
HERO_KEYS = {"who", "do", "side", "energy", "speed", "duration", "height", "item", "stop", "sit", "for", "stand", "turn",
             "go", "depth", "y", "x", "then", "style", "to", "spin", "time", "say", "stars", "take", "put", "throw",
             "catch", "give", "play", "facing", "with", "hands", "left", "right", "head", "lean", "bow", "show", "hide",
             "frontal"}
OVER_KEYS = {"title", "subtitle", "flash", "confetti", "grade", "sound", "volume", "music", "camera", "on", "zoom",
             "roll", "power", "focus", "aperture", "x", "y"}
KNOWN = TIME_KEYS | HERO_KEYS | OVER_KEYS
CAMERAS = {"wide", "full", "medium", "close", "two", "shake"}
TURNS = {"left", "right", "front", "back"}
STYLES = {"walk", "run", "sneak", "waddle", "march", "drunk", "skip"}
PLACES = {"down", "hips", "wave", "up", "wag", "wide", "beckon", "point", "chest", "rub", "show", "shoo"}
FINISHES = {"go", "turn", "say", "play", "take", "put", "throw", "sit", "spin", "give", "catch"}
CHANNELS = ["legs", "body", "head", "arm_l", "arm_r"]

STAGE_W, STAGE_H = 720.0, 1280.0
MAX_HEROES = 3
OFF_FRAME = 0.25        # a hero may stand this share of its own width past the edge of the picture
OVERLAP = 0.5           # two heroes at one depth may cover this share of the narrower one's width
SAME_DEPTH = 0.15       # ...when their depths differ by less than this
DEFAULT_WIDTH = 0.55    # a puppet's width against its height (neck to sole) when the rig is not known

# code -> (level, what it means). Every code a check can give is here (the tests hold each one to a failing and a
# passing case).
CODES = {
    "background_missing": ("error", "the scene's background picture does not exist"),
    "sound_missing": ("error", "a music, ambience or sound file does not exist"),
    "item_missing": ("error", "a thing of the scene has no card in the engine or the scene"),
    "no_actors": ("info", "a shot with no hero: a place or a thing (allowed)"),
    "scene_invalid": ("error", "the scene is not a JSON object"),
    "actor_duplicate": ("error", "two heroes with one id"),
    "puppet_missing": ("error", "a hero's puppet (rig.json) does not exist"),
    "clip_missing": ("error", "a hero's recording does not exist"),
    "actor_x_invalid": ("error", "a hero's x is a word other than out_left / out_right"),
    "actor_height_unusual": ("warning", "a hero's height is outside what usually works"),
    "point_missing": ("error", "a named point does not exist"),
    "unknown_command": ("error", "a script line has a key the engine does not know"),
    "unknown_hero": ("error", "a script line names a hero who is not in the scene"),
    "who_missing": ("error", "a command for a hero without `who` while there are several heroes"),
    "action_missing": ("error", "an action that does not exist"),
    "action_needs_side_view": ("info", "an action made for the profile, the hero has none: played from the front"),
    "action_use_play": ("info", "an instrument's action given with `do` instead of `play`"),
    "pair_half": ("error", "the second half of an action for two, which the partner plays by itself"),
    "pair_needs_with": ("error", "an action for two without `with`"),
    "pair_unknown_partner": ("error", "`with` names a hero who is not in the scene"),
    "pair_self": ("error", "an action for two done with oneself"),
    "target_unknown": ("error", "a blow, a throw or a gift aimed at a hero who is not in the scene"),
    "go_target_missing": ("error", "`go` to a point or hero that does not exist"),
    "go_self": ("error", "a hero walks to itself"),
    "go_off_stage": ("warning", "`go` to a place past the edge of the stage"),
    "walk_style_unknown": ("error", "an unknown way of walking"),
    "point_not_seat": ("error", "`sit` on a point with no seat"),
    "turn_unknown": ("error", "`turn` to something other than left / right / front / back"),
    "view_missing": ("error", "a turn to a view the hero has no drawing for"),
    "item_not_in_scene": ("error", "`take` of a thing that is not in the scene's items"),
    "instrument_missing": ("error", "`play` of an instrument the engine does not have"),
    "camera_unknown": ("error", "a framing that is not in the catalogue"),
    "camera_on_unknown": ("error", "the camera aimed at a hero who is not in the scene"),
    "camera_without_on": ("info", "a hero's framing without `on`: it shows the whole scene"),
    "grade_unknown": ("error", "an unknown colour grade"),
    "hand_place_unknown": ("error", "an unknown hand place"),
    "stop_unknown": ("error", "`stop` of an action that does not exist"),
    "timing_twice": ("error", "a line's time is given in two ways"),
    "at_not_number": ("error", "`at` is not a number"),
    "at_after_end": ("warning", "a line starts after the scene ends"),
    "phrase_no_voice": ("error", "`phrase` while no hero has a recorded voice"),
    "phrase_unknown": ("error", "the phrases of the recording are not known"),
    "phrase_out_of_range": ("error", "a phrase number the recording does not have"),
    "beat_no_bpm": ("error", "`beat` while the music has no tempo"),
    "after_unknown_label": ("error", "`after` a label no line has"),
    "after_unknown_hero": ("error", "`after` something of a hero who is not in the scene"),
    "after_unknown_action": ("error", "`after` an action that does not exist"),
    "after_never_started": ("error", "`after` an action the hero never does"),
    "actions_clash": ("warning", "two actions at one moment need the same part of the body"),
    "not_vertical": ("error", "the film is not vertical (9:16)"),
    "too_many_heroes": ("error", "more than three heroes in one shot"),
    "off_frame": ("error", "a hero stands (partly) outside the picture"),
    "heroes_overlap": ("error", "two heroes stand on each other at the same depth"),
    "not_frontal": ("error", "a hero turns its side or its back to us, or walks sideways"),
}


@dataclass
class PuppetInfo:
    views: set = field(default_factory=lambda: {"front"})   # front, side, back
    width: float = DEFAULT_WIDTH                            # rest width against neck-to-sole height


@dataclass
class Context:
    """What the checks know about the world outside the scene."""
    actions: dict = field(default_factory=dict)            # id -> action JSON (engine/actions)
    items: dict = field(default_factory=dict)              # card id -> item JSON (engine/items)
    sounds: set = field(default_factory=set)               # engine/sounds/<name>.wav stems
    grades: set = field(default_factory=set)               # engine/light.gd PRESETS
    file_exists: Callable[[str], bool] = lambda p: False   # a path as the scene writes it
    puppet: Callable[[str], PuppetInfo | None] = lambda p: None
    phrases: Callable[[str], int | None] = lambda clip: None   # how many phrases a recorded voice has

    @classmethod
    def from_engine(cls, engine_dir: Path, scene_dir: Path | None = None) -> "Context":
        """The real engine folder, files relative to `scene_dir` (or absolute)."""
        engine_dir = Path(engine_dir)
        actions = {}
        for f in sorted((engine_dir / "actions").glob("*.json")):
            try:
                actions[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                pass
        items = {}
        for f in sorted((engine_dir / "items").glob("*.json")):
            try:
                items[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                pass
        sounds = {f.stem for f in (engine_dir / "sounds").glob("*.wav")}
        light = engine_dir / "light.gd"
        grades = grades_of(light.read_text(encoding="utf-8")) if light.exists() else set()

        def exists(p: str) -> bool:
            q = Path(p)
            if not q.is_absolute():
                if scene_dir is None:
                    return False
                q = Path(scene_dir) / q
            return q.exists()

        def phrases(clip: str) -> int | None:
            q = Path(clip)
            if not q.is_absolute() and scene_dir is not None:
                q = Path(scene_dir) / q
            f = Path(str(q) + ".phrases.json")
            if not f.exists():
                return None
            try:
                return len(json.loads(f.read_text(encoding="utf-8")))
            except ValueError:
                return None

        return cls(actions=actions, items=items, sounds=sounds, grades=grades, file_exists=exists,
                   puppet=puppet_from_folder, phrases=phrases)


def grades_of(light_gd: str) -> set:
    """The colour grades engine/light.gd knows (its PRESETS table)."""
    if "const PRESETS" not in light_gd:
        return set()
    i = light_gd.index("const PRESETS")
    block = light_gd[i:light_gd.index("}\n\n", i)]
    return set(re.findall(r'"(\w+)": \{', block))


# ---------------------------------------------------------------------------------------------------- puppets

def rig_width(rig: dict) -> float:
    """A puppet's width in its rest pose against its height from the neck to the soles, from rig.json alone
    (the same forward kinematics as tadam.puppet.rigkit, without numpy)."""
    parts = rig.get("parts", {})
    rest = rig.get("rest", {})
    mats: dict = {}

    def pivot(n):
        p = parts[n]
        return p["joint"]["at"] if p.get("joint") else p.get("origin", [0, 0])

    def mul(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

    def T(x, y):
        return [[1, 0, x], [0, 1, y], [0, 0, 1]]

    def R(deg):
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        return [[c, -s, 0], [s, c, 0], [0, 0, 1]]

    def solve(n, depth=0):
        if n in mats:
            return mats[n]
        if depth > 64:
            raise ValueError("the rig's parts form a loop")
        p = parts[n]
        a = float(rest.get(n, 0.0))
        if p.get("limits"):
            a = max(p["limits"][0], min(p["limits"][1], a))
        if p.get("parent") is None:
            m = R(a)
        else:
            pp = pivot(p["parent"])
            j = p["joint"]["parent_at"]
            m = mul(mul(solve(p["parent"], depth + 1), T(j[0] - pp[0], j[1] - pp[1])), R(a))
        mats[n] = m
        return m

    try:
        xs, soles = [], []
        for n, p in parts.items():
            m = solve(n)
            pv = pivot(n)
            x, y, w, h = p["box"]
            for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
                xs.append(m[0][0] * (cx - pv[0]) + m[0][1] * (cy - pv[1]) + m[0][2])
            if "sole" in p:
                s = p["sole"]
                soles.append(m[1][0] * (s[0] - pv[0]) + m[1][1] * (s[1] - pv[1]) + m[1][2])
        neck = solve("head")[1][2] if "head" in parts else 0.0
        height = (max(soles) - neck) if soles else float(rig.get("body_height", 0) or 0)
        if not xs or height <= 0:
            return DEFAULT_WIDTH
        return (max(xs) - min(xs)) / height
    except (KeyError, TypeError, ValueError, IndexError):
        return DEFAULT_WIDTH


def puppet_from_folder(path: str) -> PuppetInfo | None:
    """A puppet folder on disk (rig.json, and side/ and back/ views if it has them)."""
    d = Path(path)
    if not (d / "rig.json").is_file():
        return None
    try:
        rig = json.loads((d / "rig.json").read_text(encoding="utf-8"))
    except ValueError:
        return None
    views = {"front"} | {v for v in ("side", "back") if (d / v / "rig.json").is_file()}
    return PuppetInfo(views=views, width=rig_width(rig))


# ---------------------------------------------------------------------------------------------------- the check

def _channels(action: dict, side="right") -> set:
    got = set()
    for ph in action.get("phases", []):
        for k in ph:
            if k == "arms":
                got |= {"arm_l", "arm_r"}
            elif k in CHANNELS:
                got.add(("arm_l" if k == "arm_r" else "arm_r") if side == "left" and k.startswith("arm") else k)
    if side == "both" and got & {"arm_l", "arm_r"}:
        got |= {"arm_l", "arm_r"}
    return got


class _Check:
    def __init__(self, spec: dict, ctx: Context, where: str):
        self.spec = spec
        self.ctx = ctx
        self.at = where
        self.out: list[Issue] = []

    def add(self, code: str, where: str, message: str):
        self.out.append(Issue(CODES[code][0], f"{self.at} {where}".strip(), code, message))

    def sound_exists(self, f: str) -> bool:
        if not isinstance(f, str) or not f:
            return False
        stem = f[:-4] if f.endswith(".wav") else f
        return self.ctx.file_exists(f) or self.ctx.file_exists(f + ".wav") or stem in self.ctx.sounds

    # ------------------------------------------------------------------ the scene's own parts
    def scene(self):
        s = self.spec
        self.seconds = float(s.get("seconds", 10))
        if s.get("background") and not self.ctx.file_exists(s["background"]):
            self.add("background_missing", "background", f"no picture '{s['background']}'")
        for key in ("music", "ambience"):
            m = s.get(key)
            f = m.get("file") if isinstance(m, dict) else m
            if f and not self.sound_exists(f):
                self.add("sound_missing", key, f"no file '{f}'")
        fmt = s.get("format")
        if fmt and fmt != "9:16":
            self.add("not_vertical", "format", f"format {fmt}: films are vertical, 9:16")
        self.points = s.get("points", {}) or {}
        self.items = {d.get("id"): d for d in s.get("items", []) if isinstance(d, dict)}
        for iid, d in self.items.items():
            card = d.get("card", iid)
            if card not in self.ctx.items and not self.ctx.file_exists(f"{card}.png"):
                self.add("item_missing", f"item {iid}", f"no thing '{card}' in the engine's items or the scene")
        self.heroes = {}
        actors = [a for a in s.get("actors", []) if isinstance(a, dict)]
        if not actors:
            self.add("no_actors", "actors", "no hero in this shot: a place or a thing")
        if len(actors) > MAX_HEROES:
            self.add("too_many_heroes", "actors", f"{len(actors)} heroes in one shot: at most {MAX_HEROES}")
        for a in actors:
            hid = a.get("id", a.get("puppet", "?"))
            w = f"hero {hid}"
            if hid in self.heroes:
                self.add("actor_duplicate", w, "two heroes with one id")
            info = self.ctx.puppet(str(a.get("puppet", "")))
            if info is None:
                self.add("puppet_missing", w, f"no puppet '{a.get('puppet')}' (a folder with rig.json)")
                info = PuppetInfo()
            for k in ("clip", "mouth"):
                if a.get(k) and not self.ctx.file_exists(a[k]):
                    self.add("clip_missing", w, f"no recording '{a[k]}'")
            x = a.get("x", 0.5)
            if isinstance(x, str) and x not in ("out_left", "out_right"):
                self.add("actor_x_invalid", w, f"x = '{x}': a number from 0 to 1, or out_left / out_right")
            h = a.get("height", 0.45)
            if isinstance(h, (int, float)) and not 0.08 <= float(h) <= 0.9:
                self.add("actor_height_unusual", w, f"height {h}: usually 0.15 to 0.6 of the picture")
            if a.get("at") and a["at"] not in self.points:
                self.add("point_missing", w, f"no point '{a['at']}'")
            if a.get("turn") in ("left", "right", "back") or a.get("view") in ("side", "back"):
                self.add("not_frontal", w, "heroes always face us: no profile, no back")
            self.heroes[hid] = {"info": info, "clip": a.get("clip") or a.get("mouth"), "def": a}
        if s.get("walk") not in (None, "front"):
            self.add("not_frontal", "walk", f"walk = '{s['walk']}': heroes walk facing us (\"walk\": \"front\")")

    # ------------------------------------------------------------------ where the heroes stand
    def geometry(self):
        g = self.spec.get("ground") or {}
        far_scale = float(g.get("far_scale", 1.0)) if isinstance(g, dict) else 1.0
        placed = []
        for hid, h in self.heroes.items():
            a = h["def"]
            x = a.get("x", 0.5)
            if isinstance(x, str) or not isinstance(x, (int, float)):
                continue
            height = float(a.get("height", 0.45)) if isinstance(a.get("height", 0.45), (int, float)) else 0.45
            depth = float(a["depth"]) if isinstance(a.get("depth"), (int, float)) else 0.0
            nv = a.get("near")
            near = isinstance(nv, (int, float)) and not isinstance(nv, bool) and nv > 1   # (over the shoulder: exempt)
            k = (1.0 + (far_scale - 1.0) * max(0.0, min(depth, 1.0)))
            half = h["info"].width * height * STAGE_H * k / STAGE_W / 2        # shares of the picture's width
            # x is where the hero is SEEN, at any depth (engine/stage.gd _ground_place: space.frame_x(x, z)); depth
            # only makes it smaller
            cx = float(x)
            if not near and (cx - half < -OFF_FRAME * 2 * half or cx + half > 1 + OFF_FRAME * 2 * half):
                self.add("off_frame", f"hero {hid}",
                         f"at x = {x} its body reaches {cx - half:.2f}..{cx + half:.2f} of the picture's width: "
                         "move it in, or make it smaller")
            placed.append((hid, cx, half, depth, near))
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                a, b = placed[i], placed[j]
                if a[4] or b[4] or abs(a[3] - b[3]) >= SAME_DEPTH:
                    continue
                cover = min(a[1] + a[2], b[1] + b[2]) - max(a[1] - a[2], b[1] - b[2])
                if cover > OVERLAP * 2 * min(a[2], b[2]):
                    self.add("heroes_overlap", f"heroes {a[0]}, {b[0]}",
                             "they stand on each other: move them apart (x) or one of them deeper (depth)")

    # ------------------------------------------------------------------ one line of the script
    def line(self, n: int, ln: dict):
        where = f"line {n + 1}" + (f" ({ln['who']})" if ln.get("who") else "")
        acts = self.ctx.actions
        own = set(acts.get(ln.get("do"), {}).get("params", {})) if isinstance(ln.get("do"), str) else set()
        for k in ln:
            if k not in KNOWN and k not in own and not str(k).startswith("_"):
                self.add("unknown_command", where, f"unknown command '{k}'")
        who = ln.get("who")
        if who is not None and who != "all" and who not in self.heroes:
            self.add("unknown_hero", where, f"no hero '{who}' (there are: {', '.join(self.heroes) or 'none'})")
            return
        targets = list(self.heroes) if who == "all" else ([who] if who else [])
        if not who and set(ln) & (HERO_KEYS - {"time", "for", "x", "y"}):
            if len(self.heroes) > 1:
                self.add("who_missing", where, f"a command for a hero without 'who': there are several, the first "
                                                f"({next(iter(self.heroes))}) would get it")
            targets = list(self.heroes)[:1]
        self.timing(where, ln)
        act = ln.get("do")
        if act is not None:
            if act in ("stamp_left", "stamp_right"):
                act = "stamp"
            if act not in acts:
                close = [a for a in acts if a.startswith(str(act)[:3])][:5]
                self.add("action_missing", where, f"no action '{act}'" + (f" (close: {', '.join(close)})" if close else ""))
            else:
                a = acts[act]
                for h in targets:
                    if a.get("view") == "side" and "side" not in self.heroes[h]["info"].views and "front" not in a:
                        self.add("action_needs_side_view", where, f"'{act}' is made for the profile and {h} has none: "
                                                                  "it is played from the front")
                if a.get("group") == "music":
                    self.add("action_use_play", where, f"for an instrument use 'play', not 'do': '{act}' gives none")
                if a.get("group") == "fight" and ln.get("to") and ln["to"] not in self.heroes:
                    self.add("target_unknown", where, f"a blow at '{ln['to']}': no such hero")
                if a.get("partner_only"):
                    self.add("pair_half", where, f"'{act}' is the second half of an action for two: the partner plays it")
                elif "pair" in a and not ln.get("with"):
                    self.add("pair_needs_with", where, f"'{act}' is done by two: add 'with': another hero")
                elif ln.get("with") and ln["with"] not in self.heroes:
                    self.add("pair_unknown_partner", where, f"with '{ln['with']}': no such hero")
                elif ln.get("with") and ln["with"] == who:
                    self.add("pair_self", where, "a hero cannot do this with itself")
        if "go" in ln:
            g = ln["go"]
            if isinstance(g, str):
                if g not in self.points and g not in self.heroes and g not in ("out_left", "out_right"):
                    self.add("go_target_missing", where, f"go to '{g}': no such point or hero")
                if g == who:
                    self.add("go_self", where, "a hero walks to itself")
            elif isinstance(g, (int, float)) and not 0 <= float(g) <= 1:
                self.add("go_off_stage", where, f"go = {g}: past the edge of the stage (0..1)")
            if ln.get("style") and ln["style"] not in STYLES:
                self.add("walk_style_unknown", where, f"walk style '{ln['style']}': {', '.join(sorted(STYLES))}")
            if ln.get("then") == "keep":
                self.add("not_frontal", where, "'then': 'keep' leaves the hero in profile: heroes face us")
        if "sit" in ln and isinstance(ln["sit"], str):
            pt = self.points.get(ln["sit"])
            if pt is None:
                self.add("point_missing", where, f"sit on '{ln['sit']}': no such point")
            elif "seat" not in pt:
                self.add("point_not_seat", where, f"the point '{ln['sit']}' has no seat")
        if "turn" in ln:
            t = ln["turn"]
            if t not in TURNS:
                self.add("turn_unknown", where, f"turn '{t}': left / right / front / back")
            else:
                if t != "front":
                    self.add("not_frontal", where, f"turn '{t}': heroes always face us")
                for h in targets:
                    views = self.heroes[h]["info"].views
                    if t in ("left", "right") and "side" not in views:
                        self.add("view_missing", where, f"{h} has no side view")
                    if t == "back" and "back" not in views:
                        self.add("view_missing", where, f"{h} has no back view")
        if "spin" in ln:
            self.add("not_frontal", where, "a spin shows the hero's side and back")
        if "take" in ln and ln["take"] not in self.items:
            self.add("item_not_in_scene", where, f"take '{ln['take']}': no such thing in the scene's items")
        if "give" in ln and ln["give"] not in self.heroes:
            self.add("target_unknown", where, f"give to '{ln['give']}': no such hero")
        if isinstance(ln.get("throw"), str) and ln["throw"] not in self.heroes:
            self.add("target_unknown", where, f"throw at '{ln['throw']}': no such hero")
        if "play" in ln and ln["play"] not in ("off", "stop", ""):
            if ln["play"] not in self.ctx.items and not self.ctx.file_exists(f"{ln['play']}.png"):
                have = sorted(k for k, v in self.ctx.items.items() if isinstance(v, dict) and "play" in v)
                self.add("instrument_missing", where, f"no instrument '{ln['play']}' (there are: {', '.join(have)})")
        if "camera" in ln:
            if ln["camera"] not in CAMERAS:
                self.add("camera_unknown", where, f"camera '{ln['camera']}': {', '.join(sorted(CAMERAS))}")
            on = ln.get("on", [])
            for h in (on if isinstance(on, list) else [on]):
                if h not in self.heroes:
                    self.add("camera_on_unknown", where, f"the camera on '{h}': no such hero")
            if ln["camera"] in ("full", "medium", "close", "two") and not on:
                self.add("camera_without_on", where, f"camera '{ln['camera']}' without 'on' shows the whole scene")
        if "sound" in ln and not self.sound_exists(ln["sound"]):
            self.add("sound_missing", where, f"no sound '{ln['sound']}'")
        if "music" in ln:
            m = ln["music"]
            f = m.get("file") if isinstance(m, dict) else m
            if f != "stop" and not self.sound_exists(f):
                self.add("sound_missing", where, f"no music '{f}'")
        if "grade" in ln and isinstance(ln["grade"], str) and ln["grade"] not in self.ctx.grades:
            self.add("grade_unknown", where, f"grade '{ln['grade']}': {', '.join(sorted(self.ctx.grades))}")
        for k in ("hands", "left", "right"):
            if k in ln and ln[k] not in PLACES:
                self.add("hand_place_unknown", where, f"{k} = '{ln[k]}': {', '.join(sorted(PLACES))}")
        if "stop" in ln and ln["stop"] != "all" and ln["stop"] not in acts:
            self.add("stop_unknown", where, f"stop '{ln['stop']}': no such action")
        if "label" in ln:
            self.labels.add(ln["label"])

    def timing(self, where: str, ln: dict):
        ways = [k for k in ("after", "phrase", "beat") if k in ln]
        if len(ways) > 1:
            self.add("timing_twice", where, f"the time is given twice: {', '.join(ways)} (one is enough)")
        at = ln.get("at", 0)
        if not isinstance(at, (int, float)) or isinstance(at, bool):
            self.add("at_not_number", where, f"at = '{at}': seconds, as a number")
        elif self.spec.get("time") != "share" and at > self.seconds:
            self.add("at_after_end", where, f"at = {at} s, but the scene lasts {self.seconds:g} s")
        if "phrase" in ln:
            # a voice: a recorded clip, or a line with no recording yet ("speech": the phrases the kit estimated)
            voice = ln.get("voice", ln.get("who"))

            def said(h):
                sp = h["def"].get("speech")
                return h["clip"] or (sp if isinstance(sp, list) and sp else None)
            clips = [said(self.heroes[voice])] if voice in self.heroes and said(self.heroes[voice]) else \
                [said(h) for h in self.heroes.values() if said(h)]
            if not clips:
                self.add("phrase_no_voice", where, "'phrase', but no hero has a recorded voice ('clip') or says a "
                                                   "line in this shot")
            else:
                count = len(clips[0]) if isinstance(clips[0], list) else self.ctx.phrases(clips[0])
                if count is None:
                    self.add("phrase_unknown", where, f"the phrases of {clips[0]} are not known (tadam.phrases)")
                elif not isinstance(ln["phrase"], int) or not 1 <= ln["phrase"] <= count:
                    self.add("phrase_out_of_range", where, f"phrase {ln['phrase']}: the recording has {count}")
        if "beat" in ln:
            m = self.spec.get("music")
            if not (isinstance(m, dict) and m.get("bpm")):
                self.add("beat_no_bpm", where, "'beat', but the music has no tempo (tadam.bpm finds it)")
        if "after" in ln:
            a = str(ln["after"])
            if a.startswith("#"):
                self.wants_labels.append((where, a[1:]))
            else:
                of = ln.get("of", ln.get("who"))
                if of and of != "all" and of not in self.heroes:
                    self.add("after_unknown_hero", where, f"after something of '{of}': no such hero")
                elif a not in self.ctx.actions and a not in FINISHES:
                    self.add("after_unknown_action", where, f"after '{a}': no such action")
                else:
                    self.wants_done.append((where, of, a))

    def overlaps(self, script: list):
        """Two actions starting at the same second for one hero that need the same part of the body: the second one
        takes it from the first."""
        acts = self.ctx.actions
        by: dict = {}
        for n, ln in enumerate(script):
            if not isinstance(ln.get("do"), str) or ln["do"] not in acts or any(k in ln for k in ("after", "phrase", "beat")):
                continue
            if not isinstance(ln.get("at", 0), (int, float)):
                continue
            for h in (list(self.heroes) if ln.get("who") == "all" else [ln.get("who")]):
                by.setdefault((h, round(float(ln.get("at", 0)), 2)), []).append((n, ln))
        for (h, t), lines in by.items():
            for i in range(len(lines)):
                for j in range(i + 1, len(lines)):
                    a, b = lines[i][1], lines[j][1]
                    shared = _channels(acts[a["do"]], a.get("side", "right")) & _channels(acts[b["do"]], b.get("side", "right"))
                    if shared:
                        self.add("actions_clash", f"line {lines[j][0] + 1} ({h})",
                                 f"'{b['do']}' and '{a['do']}' at {t:g} s both need {', '.join(sorted(shared))}: "
                                 f"only '{b['do']}' is left")

    def run(self) -> list[Issue]:
        self.scene()
        self.geometry()
        self.labels: set = set()
        self.wants_labels: list = []
        self.wants_done: list = []
        script = [ln for ln in self.spec.get("script", []) if isinstance(ln, dict)]
        for n, ln in enumerate(script):
            self.line(n, ln)
        for where, name in self.wants_labels:
            if name not in self.labels:
                self.add("after_unknown_label", where, f"after '#{name}': no line has \"label\": \"{name}\"")
        started = set()
        for ln in script:
            for h in (list(self.heroes) if ln.get("who") == "all" else [ln.get("who")]):
                if isinstance(ln.get("do"), str):
                    started.add((h, ln["do"]))
                for k in FINISHES:
                    if k in ln:
                        started.add((h, k))
                if "take" in ln:
                    started.add((h, "lift"))
        for where, of, a in self.wants_done:
            for h in (list(self.heroes) if of == "all" else [of]):
                if (h, a) not in started:
                    self.add("after_never_started", where, f"waits for {h} to finish '{a}', which {h} never does")
        self.overlaps(script)
        return self.out


def check_scene(spec: dict, ctx: Context, where: str = "") -> list[Issue]:
    """Every finding of one engine scene. `where` prefixes each finding's place (a shot's name)."""
    if not isinstance(spec, dict):
        return [Issue("error", where or "scene", "scene_invalid", "the scene is not a JSON object")]
    return _Check(spec, ctx, where).run()


def main(argv=None) -> int:
    """python -m tadam.scenecheck <scene folder> [--json]: check a scene.json against the kit's engine."""
    import argparse
    import sys

    from tadam.issues import format_text, result
    from tadam.paths import engine_dir
    ap = argparse.ArgumentParser(prog="python -m tadam.scenecheck")
    ap.add_argument("folder")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    folder = Path(a.folder)
    spec = json.loads((folder / "scene.json").read_text(encoding="utf-8"))
    issues = check_scene(spec, Context.from_engine(engine_dir(), folder), folder.name)
    if a.json:
        sys.stdout.write(json.dumps(result(issues), ensure_ascii=False, indent=1) + "\n")
    else:
        print(format_text(issues))
    return 1 if any(i.level == "error" for i in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
