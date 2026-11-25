"""NAMES -> ENGINE SCENES (studio-tz 6.1): a version-2 script names heroes, sets and media; the engine wants a
scene.json per shot with real files. This turns one into the other (the logic of the lab's shots.py, without the
recordings: locally every hero keeps its painted head).

The kit writes its scenes into the world folder's .tadam/scenes/<episode>/<shot>/ and every file in them is an
ABSOLUTE path (the engine takes absolute paths: engine/stage.gd _scene_file). So a scene works wherever the world
folder is, on any drive and under any name (spaces, non-latin letters).

Only what the script may say reaches the engine: stage options from an allow-list, the actors' places, the camera
lines. Puppets, pictures and sounds are always the world's own files, found by name here.
"""
from __future__ import annotations

from pathlib import Path

from tadam.world import World, is_safe_name, read_json

WORDS_PER_SECOND = 2.3          # a calm line, Russian or English: words a second
LEAD, TAIL, NARR_TAIL = 0.3, 0.4, 0.7
DEFAULT_SECONDS = 4.0
DEFAULT_HEIGHT = 0.42           # a hero's height (neck to sole) against the picture's, when hero.json has none
NEAR = 2.0                      # "near": true -> this many times the size at the front edge (over the shoulder)
# stage options a film or a shot may set (plain values; engine/stage.gd reads them from the scene's top level)
STAGE_OPTIONS = {"faces", "hands", "walk", "parallax", "vignette", "grade", "closest", "pins", "gloves", "clip_loop",
                 "sfx", "turn_style"}
# what a set.json may pass on to the scene besides its pictures
SET_KEYS = {"floor", "ground", "points", "life", "light", "grade", "haze", "vignette", "tint", "world", "parallax"}
# actor keys the script may not set (the kit fills them from the world's own files)
ACTOR_FIXED = {"puppet", "clip", "mouth", "props", "sound", "prop"}


def words(text: str) -> int:
    return len([w for w in str(text).split() if any(c.isalnum() for c in w)])


def line_seconds(text: str) -> float:
    """How long a line takes to say, roughly."""
    return round(0.4 + words(text) / WORDS_PER_SECOND, 2)


def steps_by_key(script: dict) -> dict:
    out = {}
    for hero, steps in (script.get("roles") or {}).items():
        for st in steps if isinstance(steps, list) else []:
            if isinstance(st, dict) and "key" in st:
                out[st["key"]] = (hero, st)
    return out


def text_of(loc: object, lang: str = "ru") -> str:
    if isinstance(loc, dict):
        return str(loc.get(lang) or loc.get("ru") or "")
    return ""


def shot_seconds(shot: dict, steps: dict, lang: str = "ru") -> float:
    """A shot lasts its "seconds", or as long as its line (or the narration over it) with a little air around."""
    if isinstance(shot.get("seconds"), (int, float)):
        return float(shot["seconds"])
    say = shot.get("say")
    if say in steps:
        st = steps[say][1]
        n = line_seconds(text_of(st.get("text"), lang))
        if isinstance(st.get("maxSeconds"), (int, float)):
            n = min(n, float(st["maxSeconds"]))
        return round(float(shot.get("lead", LEAD)) + n + float(shot.get("tail", shot.get("trail", TAIL))), 2)
    narr = shot.get("narration")
    if isinstance(narr, dict):
        at = narr.get("at", 0.5)
        at = float(at) if isinstance(at, (int, float)) else 0.5
        return round(at + line_seconds(text_of(narr.get("text"), lang)) + float(shot.get("tail", NARR_TAIL)), 2)
    return DEFAULT_SECONDS


def _set_part(world: World, slug: str) -> tuple[dict, list[str]]:
    """The set's pictures as absolute paths, and its other keys. (problems: files it names that are unsafe.)"""
    sd = world.set_dir(slug)
    st, err = read_json(sd / "set.json")
    if not isinstance(st, dict):
        return {}, [f"sets/{slug}/set.json: {err or 'not an object'}"]
    out, bad = {}, []

    def f(name):
        if not is_safe_name(name):
            bad.append(str(name))
            return None
        return (sd / name).as_posix()

    if st.get("background"):
        bg = f(st["background"])
        if bg:
            out["background"] = bg
    for k in SET_KEYS:
        if k in st:
            out[k] = st[k]
    out["backdrops"] = []
    for b in st.get("backdrops", []) if isinstance(st.get("backdrops"), list) else []:
        if isinstance(b, dict) and f(b.get("image")):
            out["backdrops"].append({**b, "image": f(b["image"])})
    out["pieces"] = []
    for p in st.get("pieces", []) if isinstance(st.get("pieces"), list) else []:
        if isinstance(p, dict) and f(p.get("image")):
            q = {**p, "image": f(p["image"])}
            if "under" in p:
                q["under"] = f(p["under"]) or ""
            out["pieces"].append(q)
    return out, bad


def shot_scene(world: World, script: dict, shot: dict, lang: str = "ru") -> dict:
    """The engine scene of one shot."""
    film = script.get("film") or {}
    cast = script.get("cast") or {}
    steps = steps_by_key(script)
    scene: dict = {"format": "9:16"}
    set_slug = shot.get("set") or film.get("set")
    if isinstance(set_slug, str):
        part, _ = _set_part(world, set_slug)
        scene.update(part)
    for src in (film.get("stage") or {}, shot.get("stage") or {}):
        for k, v in src.items():
            if k in STAGE_OPTIONS:
                scene[k] = v
    actors, lines = [], []
    for a in shot.get("actors") or []:
        if not isinstance(a, dict):
            continue
        hid = a.get("id")
        character = (cast.get(hid) or {}).get("character") if isinstance(cast.get(hid), dict) else None
        d = {k: v for k, v in a.items() if k not in ACTOR_FIXED}
        if isinstance(character, str):
            d["puppet"] = world.puppet_dir(character).as_posix()
            h = world.hero_json(character).get("height")
            d.setdefault("height", h if isinstance(h, (int, float)) else DEFAULT_HEIGHT)
        else:
            d["puppet"] = ""
            d.setdefault("height", DEFAULT_HEIGHT)
        if a.get("near") is True:
            d["near"] = NEAR
        elif a.get("near") is False:
            d.pop("near", None)
        if is_safe_name(a.get("prop")):
            d["props"] = {"prop": {"image": world.media(a["prop"]).as_posix(), "hand": "right", "length": 1.0,
                                   "grip": 0.7}}
            lines.append({"at": 0, "who": hid, "show": "prop"})
        actors.append(d)
    scene["actors"] = actors
    scene["seconds"] = shot_seconds(shot, steps, lang)
    if isinstance(shot.get("focus"), dict):
        scene["focus"] = shot["focus"]
    for c in shot.get("camera") or []:
        if isinstance(c, dict):
            # (every key goes on: one the engine does not know is reported by the scene check, not dropped silently)
            lines.append({k: v for k, v in c.items() if k != "who"})
    scene["script"] = lines
    return scene


def film_scenes(world: World, script: dict, lang: str = "ru") -> list[tuple[str, dict]]:
    """(shot id, engine scene) for every shot, in order."""
    return [(str(s.get("id", i + 1)), shot_scene(world, script, s, lang))
            for i, s in enumerate(script.get("shots") or []) if isinstance(s, dict)]


def write_scenes(world: World, episode: str, script: dict, lang: str = "ru") -> list[Path]:
    """.tadam/scenes/<episode>/<shot>/scene.json for every shot; returns the folders."""
    from tadam.world import write_json
    out = []
    for sid, scene in film_scenes(world, script, lang):
        d = world.work_dir() / "scenes" / str(episode) / sid
        write_json(d / "scene.json", scene)
        out.append(d)
    return out
