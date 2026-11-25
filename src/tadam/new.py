"""`tadam new world | hero | set | episode`: folder templates (studio-tz 3.3). Every template fits its schema;
the texts start with "TODO" until they are written (`tadam check` lists them)."""
from __future__ import annotations

from pathlib import Path

from tadam import schema, sources
from tadam.world import EPISODE, SLUG, HERO_KEY, World, WorldError, write_json

GITIGNORE = ".tadam/\n"


def _slug(kind: str, slug: str) -> str:
    if not SLUG.match(slug or "") or len(slug) > 80:
        raise WorldError(f"'{slug}' is not a {kind} name: latin small letters, digits and single '-' "
                         f"(like my-{kind})")
    return slug


def _fresh(path: Path, what: str):
    if path.exists():
        raise WorldError(f"{what} already exists: {path}")


def _check(name: str, data: dict):
    bad = schema.validate(name, data)
    if bad:                                          # (a template that does not fit is a bug of the kit)
        raise AssertionError(f"template {name}: {bad}")


def world(parent: Path, slug: str, title: str | None = None, langs=("ru",)) -> Path:
    """<parent>/<slug>/ with world.json and the empty folders of a world."""
    _slug("world", slug)
    root = Path(parent) / slug
    _fresh(root / "world.json", "a world")
    data = {
        "version": 1,
        "slug": slug,
        "title": {"ru": title or slug},
        "tagline": {"ru": "TODO: слоган в одну строку"},
        "description": {"ru": "TODO: о чём сериал, два-три предложения для зрителя"},
        "genre": "",
        "langs": list(langs),
        "bible": {
            "idea": {"ru": "TODO: идея сериала: кто герои, что с ними происходит, чем смешно"},
            "tone": {"ru": "TODO: тон: как шутим, о чём не шутим"},
            "style": {"ru": "TODO: как это выглядит (для картинок; лучше и по-английски, в style.en)"},
            "rules": [],
            "heroes": {"ru": "TODO: кто есть кто"},
        },
    }
    if "en" in langs:
        for k in ("title", "tagline", "description"):
            data[k]["en"] = "TODO"           # (never the Russian title: the check lists it until it is written)
        for k in ("idea", "tone", "style", "heroes"):
            data["bible"][k]["en"] = "TODO"
    _check("world", data)
    write_json(root / "world.json", data)
    for d in ("heroes", "sets", "media", "episodes"):
        (root / d).mkdir(parents=True, exist_ok=True)
    sources.starter(root)          # where every picture and sound comes from: filled as files are made
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text(GITIGNORE, encoding="utf-8", newline="\n")
    return root


def hero(w: World, slug: str, name: str | None = None, height: float = 0.42) -> Path:
    _slug("hero", slug)
    d = w.hero_dir(slug)
    _fresh(d / "hero.json", "a hero")
    data = {"version": 1, "name": {"ru": name or f"TODO: имя ({slug})"},
            "trait": {"ru": "TODO: черта характера в несколько слов"}, "height": height}
    if "en" in w.langs():
        data["name"]["en"] = "TODO"
        data["trait"]["en"] = "TODO"
    _check("hero", data)
    write_json(d / "hero.json", data)
    return d


def set_(w: World, slug: str, name: str | None = None) -> Path:
    """sets/<slug>/kit.json (what `tadam set make` paints) and set.json (what the engine plays: written again by
    `set make`)."""
    _slug("set", slug)
    d = w.set_dir(slug)
    _fresh(d / "set.json", "a set")
    ground = {"far": 0.675, "far_scale": 0.55, "tilt": 0.7}
    kit = {
        "name": name or slug,
        "about": "The parts of this set: an empty room, far layers, every piece of furniture as its own picture. "
                 "`tadam set make` paints the room and the pieces (props) and writes set.json. Window glass painted "
                 "flat pure magenta #FF00FF is keyed out (see-through); behind it go the far layers (far: "
                 "[{id, image, scale, rect}]), which are YOUR OWN pictures in this folder (a street, a sky): the kit "
                 "does not paint them; give each a source in sources.json.",
        "floor": 0.87,
        "ground": ground,
        "room": {"prompt": "TODO: the empty room, front view, vertical 9:16, floor in the lower part; window glass "
                           "(if any) filled with flat pure magenta #FF00FF"},
        "far": [],
        "props": [],
    }
    write_json(d / "kit.json", kit)
    write_json(d / "set.json", {"name": kit["name"], "background": "room.png", "floor": kit["floor"],
                                "ground": ground, "backdrops": [], "pieces": []})
    return d


def episode(w: World, n: str, set_slug: str | None = None, cast: dict | None = None) -> Path:
    """episodes/<n>/script.json: a version-2 script with one shot per hero of the cast (or one empty shot)."""
    n = str(n)
    if not EPISODE.match(n):
        raise WorldError(f"'{n}' is not an episode number: 1, 2, 3 ...")
    d = w.episode_dir(n)
    _fresh(d / "script.json", "an episode")
    if set_slug is None:
        sets = w.sets()
        set_slug = sets[0] if len(sets) == 1 else "main"
    _slug("set", set_slug)
    cast = dict(cast or {})
    for key, ch in cast.items():
        if not HERO_KEY.match(key):
            raise WorldError(f"'{key}' is not a cast key: a short latin key like det, cow")
        _slug("hero", ch)
    roles, shots = {}, []
    for i, key in enumerate(cast, 1):
        line = f"{key}-1"
        roles[key] = [{
            "key": line, "kind": "read",
            "text": {"ru": "TODO: реплика"},
            "hint": {"ru": "TODO: как сыграть и как держать телефон"},
            "look": [{"target": "lens"}],
            "maxSeconds": 6,
        }]
        shots.append({"id": f"sh{i}", "remark": {"ru": "TODO: что происходит в кадре, одной строкой"},
                      "say": line, "actors": [{"id": key, "x": 0.5}],
                      "camera": [{"at": 0, "camera": "medium", "on": key}]})
    if not shots:
        shots.append({"id": "sh1", "remark": {"ru": "TODO: что происходит в кадре, одной строкой"}, "seconds": 3})
    if "en" in w.langs():
        for steps in roles.values():
            for st in steps:
                st["text"]["en"] = "TODO"
                st["hint"]["en"] = "TODO"
        for sh in shots:
            sh["remark"]["en"] = "TODO"
    data = {"version": 2, "cast": {k: {"character": v} for k, v in cast.items()}, "roles": roles,
            "shots": shots, "film": {"set": set_slug}}
    _check("script.v2", data)
    write_json(d / "script.json", data)
    return d
