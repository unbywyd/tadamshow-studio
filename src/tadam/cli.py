"""The `tadam` command line."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from tadam import __version__, doctor


def _out(text: str) -> None:
    """Print in UTF-8 whatever the console's code page is (Russian texts on a Windows console)."""
    try:
        sys.stdout.write(text + "\n")
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


def _world(a) -> "World":  # noqa: F821
    from tadam.world import World, find_world
    return World(find_world(a.world))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tadam", description="TadamShow Studio")
    ap.add_argument("--version", action="version", version=f"tadam {__version__}")
    ap.add_argument("--world", default=None, help="the world folder (default: this folder or the nearest one above "
                                                  "it with a world.json)")
    sub = ap.add_subparsers(dest="command", metavar="<command>")
    sub.add_parser("doctor", help="check that everything the studio needs is installed")

    new = sub.add_parser("new", help="a new world, hero, set or episode from the template")
    ns = new.add_subparsers(dest="what", metavar="<what>")
    nw = ns.add_parser("world", help="a new world folder: tadam new world <slug>")
    nw.add_argument("slug")
    nw.add_argument("--title", help="the world's title (Russian)")
    nw.add_argument("--en", action="store_true", help="the world is in Russian and English")
    nw.add_argument("--dir", default=".", help="where to make the folder (default: here)")
    nh = ns.add_parser("hero", help="heroes/<slug>/hero.json")
    nh.add_argument("slug")
    nh.add_argument("--name", help="the hero's name (Russian)")
    nh.add_argument("--height", type=float, default=0.42, help="neck to sole, share of the picture (0.42)")
    nst = ns.add_parser("set", help="sets/<slug>/kit.json and set.json")
    nst.add_argument("slug")
    nst.add_argument("--name")
    ne = ns.add_parser("episode", help="episodes/<n>/script.json (version 2)")
    ne.add_argument("n")
    ne.add_argument("--set", dest="set_slug", help="the set of the film (default: the world's only set, or 'main')")
    ne.add_argument("--cast", action="append", default=[], metavar="KEY=HERO",
                    help="a hero of the episode: det=detective (repeat for each)")

    hero = sub.add_parser("hero", help="heroes: make a puppet")
    hs = hero.add_subparsers(dest="what", metavar="<what>")
    hm = hs.add_parser("make", help='paint, cut and check a puppet: tadam hero make <slug> "<description>"')
    hm.add_argument("slug")
    hm.add_argument("description")
    hm.add_argument("--style", help="the look (default: the world's bible style)")
    hm.add_argument("--rig", default="humanoid-a", help="the pattern: humanoid-a, humanoid-a-skirt-knee, ...")
    hm.add_argument("--quality", default="medium", choices=["low", "medium", "high"])
    hm.add_argument("--model", default=None)
    hm.add_argument("--attempts", type=int, default=3)
    hm.add_argument("--mannequin", action="store_true",
                    help="no painting: the wooden mannequin drawn by code (free), to block out scenes")

    st = sub.add_parser("set", help="sets: paint a set from its kit.json")
    ss = st.add_subparsers(dest="what", metavar="<what>")
    sm = ss.add_parser("make", help="paint the room and the pieces, write set.json: tadam set make <slug>")
    sm.add_argument("slug")
    sm.add_argument("--only", default="", help="only these parts: room,desk")
    sm.add_argument("--layout-only", action="store_true", help="no painting: only lay out set.json again")
    sm.add_argument("--quality", default="medium", choices=["low", "medium", "high"])
    sm.add_argument("--placeholder", action="store_true",
                    help="no painting: a plain room and flat shapes drawn by code (free), to block out scenes")

    ck = sub.add_parser("check", help="check the world and its scripts (exit 1 on errors)")
    ck.add_argument("episode", nargs="?", help="one episode (default: all)")
    ck.add_argument("--json", action="store_true", help="print the check-result JSON")
    ck.add_argument("--engine", action="store_true", help="also play every shot through in the engine, unseen")
    return ap


def _cast(pairs: list[str]) -> dict:
    from tadam.world import WorldError
    out = {}
    for p in pairs:
        if "=" not in p:
            raise WorldError(f"--cast {p}: write KEY=HERO, like det=detective")
        k, v = p.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def cmd_new(a) -> int:
    from tadam import new
    if a.what == "world":
        root = new.world(Path(a.dir), a.slug, a.title, ("ru", "en") if a.en else ("ru",))
        _out(f"world: {root}\nnext: write world.json (title, bible), then `tadam new hero <slug>`")
        return 0
    w = _world(a)
    if a.what == "hero":
        d = new.hero(w, a.slug, a.name, a.height)
        _out(f"hero: {d / 'hero.json'}\nnext: `tadam hero make {a.slug} \"<what the hero looks like>\"`")
    elif a.what == "set":
        d = new.set_(w, a.slug, a.name)
        _out(f"set: {d}\nnext: describe the room and the pieces in kit.json, then `tadam set make {a.slug}`")
    elif a.what == "episode":
        d = new.episode(w, a.n, a.set_slug, _cast(a.cast))
        _out(f"episode: {d / 'script.json'}\nnext: write the script, then `tadam check {a.n}`")
    else:
        _out("tadam new world | hero | set | episode")
        return 2
    return 0


def cmd_hero(a) -> int:
    from tadam import hero
    if a.what != "make":
        _out('tadam hero make <slug> "<description>"')
        return 2
    w = _world(a)
    if not a.mannequin:
        _out("Paints 2 pictures with YOUR OpenAI key (portrait + pattern sheet; one more per repainted sheet).")
    r = hero.make(w, a.slug, a.description, style=a.style, rig=a.rig, quality=a.quality, model=a.model,
                  attempts=a.attempts, mannequin=a.mannequin, log=_out)
    _out(f"{a.slug}: {hero.describe(r)}")
    return 0 if r["passed"] else 1


def cmd_set(a) -> int:
    from tadam import setmake
    if a.what != "make":
        _out("tadam set make <slug>")
        return 2
    w = _world(a)
    if not (a.layout_only or a.placeholder):
        _out("Paints the room and every piece with YOUR OpenAI key (one picture each).")
    setmake.make(w, a.slug, set(filter(None, a.only.split(","))), a.layout_only, log=_out, quality=a.quality,
                 plain=a.placeholder)
    return 0


def cmd_check(a) -> int:
    from tadam import check, issues
    w = _world(a)
    found = check.check_world(w.root, a.episode)
    if a.engine and not any(i.level == "error" for i in found):
        found += _engine_checks(w, a.episode)
    if a.json:
        _out(json.dumps(issues.result(found), ensure_ascii=False, indent=1))
    else:
        _out(issues.format_text(found))
    return 1 if any(i.level == "error" for i in found) else 0


def _engine_checks(w, episode) -> list:
    from tadam import engine, resolve
    from tadam.issues import Issue
    from tadam.world import read_json
    out = []
    for n in ([episode] if episode else w.episodes()):
        script, _ = read_json(w.episode_dir(n) / "script.json")
        if not isinstance(script, dict):
            continue
        for d in resolve.write_scenes(w, n, script, w.langs()[0]):
            spec, _ = read_json(d / "scene.json")
            res = engine.run_check(d, float(spec.get("seconds", 4)))
            where = f"episodes/{n} shot {d.name}"
            if res is None:
                out.append(Issue("error", where, "engine_failed", "the scene did not play to its end in the engine"))
                continue
            for key, spans in res.get("problems", {}).items():
                kind, who = (key.split("|", 1) + [""])[:2]
                spans = [sp for sp in spans if isinstance(sp, list) and sp[1] - sp[0] >= 0.4] if kind != "never" else spans
                if spans or kind == "never":
                    out.append(Issue("error", f"{where} {who}", f"engine_{kind}", engine.WORDS.get(kind, kind)))
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.command == "doctor":
        return doctor.main()
    if a.command is None:
        ap.print_help()
        return 0
    from tadam.openai_images import GenerationError
    from tadam.world import WorldError
    try:
        return {"new": cmd_new, "hero": cmd_hero, "set": cmd_set, "check": cmd_check}[a.command](a)
    except (WorldError, GenerationError) as e:
        _out(f"tadam: {e}")
        return 1
