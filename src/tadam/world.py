"""A WORLD FOLDER on the editor's disk (studio-tz 3.3): the one source of truth about a world.

    world.json                 the card and the bible
    cover.png
    heroes/<slug>/hero.json    name, trait, height;  heroes/<slug>/puppet/  the puppet (meta, rig, parts, report)
    sets/<slug>/               set.json, kit.json, the room, far layers, pieces
    media/                     music, ambience, props (referenced by name from the script)
    episodes/<n>/script.json   the script, version 2 (names, never paths)
    .tadam/                    the kit's own working files (scenes, caches); never sent, never committed

Paths are pathlib everywhere; names inside the world are compared with their exact case (Linux tells `Cow.png` from
`cow.png`, Windows and macOS do not: a world that works on one must work on all).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HERO_KEY = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
EPISODE = re.compile(r"^[1-9][0-9]{0,3}$")
# a file name inside the world (media names, set files): latin, digits, - _ . ; folders with "/"; no "..", no "\"
SAFE_NAME = re.compile(r"^(?:[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}/){0,3}[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$")


class WorldError(Exception):
    pass


def is_safe_name(name: object) -> bool:
    return isinstance(name, str) and bool(SAFE_NAME.match(name)) and ".." not in name


def find_world(start: Path | str | None = None) -> Path:
    """The world folder: `start` or the nearest folder above it with a world.json."""
    p = Path(start or Path.cwd()).resolve()
    for d in (p, *p.parents):
        if (d / "world.json").is_file():
            return d
    raise WorldError(f"no world.json in {p} or above it: make a world with `tadam new world <slug>` "
                     "or pass --world <folder>")


def exact(root: Path, rel: str) -> str:
    """'ok' if root/rel exists with exactly this case, 'case' if it exists only with another case, else 'missing'."""
    cur = Path(root)
    for part in rel.split("/"):
        try:
            names = os.listdir(cur)
        except OSError:
            return "missing"
        if part in names:
            cur = cur / part
            continue
        low = [n for n in names if n.lower() == part.lower()]
        return "case" if low else "missing"
    return "ok"


def read_json(path: Path) -> tuple[object | None, str | None]:
    """(data, None) or (None, why it cannot be read)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "missing"
    except UnicodeDecodeError:
        return None, "not UTF-8 text"
    except ValueError as e:
        return None, f"not valid JSON ({e})"


def write_json(path: Path, data: object, indent: int | None = 2) -> None:
    """Every JSON file of the kit: UTF-8, LF on every system (tadam.jsonfile)."""
    from tadam.jsonfile import write_json as _write
    _write(path, data, indent)


def work_place(folder: Path | str) -> Path:
    """Where the kit's working files of a folder of a world go (check pictures, logs, raw downloads): the same path
    under the world's .tadam/ (never sent, never committed): heroes/cow/puppet -> .tadam/heroes/cow/puppet. A folder
    that is not inside a world (a puppet made on its own) keeps them itself."""
    p = Path(folder).resolve()
    for d in p.parents:
        if (d / "world.json").is_file():
            out = d / ".tadam" / p.relative_to(d)
            out.mkdir(parents=True, exist_ok=True)
            return out
    p.mkdir(parents=True, exist_ok=True)
    return p


class World:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    # ------------------------------------------------------------------ places
    def rel(self, p: Path) -> str:
        try:
            return Path(p).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(p)

    def hero_dir(self, slug: str) -> Path:
        return self.root / "heroes" / slug

    def puppet_dir(self, slug: str) -> Path:
        return self.root / "heroes" / slug / "puppet"

    def set_dir(self, slug: str) -> Path:
        return self.root / "sets" / slug

    def media(self, name: str) -> Path:
        return self.root / "media" / name

    def episode_dir(self, n: str | int) -> Path:
        return self.root / "episodes" / str(n)

    def work_dir(self) -> Path:
        return self.root / ".tadam"

    # ------------------------------------------------------------------ contents
    def _dirs(self, sub: str) -> list[str]:
        d = self.root / sub
        if not d.is_dir():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith("."))

    def heroes(self) -> list[str]:
        return self._dirs("heroes")

    def sets(self) -> list[str]:
        return self._dirs("sets")

    def episodes(self) -> list[str]:
        return sorted(self._dirs("episodes"), key=lambda n: (not n.isdigit(), int(n) if n.isdigit() else 0, n))

    def world_json(self) -> dict:
        data, err = read_json(self.root / "world.json")
        return data if isinstance(data, dict) else {}

    def hero_json(self, slug: str) -> dict:
        data, _ = read_json(self.hero_dir(slug) / "hero.json")
        return data if isinstance(data, dict) else {}

    def langs(self) -> list[str]:
        langs = self.world_json().get("langs") or ["ru"]
        return [x for x in langs if x in ("ru", "en")] or ["ru"]

    def style(self) -> str:
        """The look of the world for the image model: the bible's style (English if written, else Russian)."""
        st = (self.world_json().get("bible") or {}).get("style") or {}
        text = (st.get("en") or st.get("ru") or "").strip()
        return "" if text.startswith("TODO") else text
