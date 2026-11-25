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
    hm = hs.add_parser("make", help='paint, cut and check a puppet: tadam hero make <slug> "<description>"',
                       description="PAID: paints 2 pictures with YOUR OpenAI key (portrait + pattern sheet; one more "
                                   "per repainted sheet, at most 2) at medium quality unless --quality says otherwise: "
                                   "about $0.05 a hero at medium (Nov 2026), several times more at high. Prints the "
                                   "pictures painted and their cost from the API's usage.",
                       formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    hm.add_argument("slug")
    hm.add_argument("description")
    hm.add_argument("--style", help="the look (default: the world's bible style)")
    hm.add_argument("--rig", default="humanoid-a", help="the pattern: humanoid-a, humanoid-a-skirt-knee, ...")
    hm.add_argument("--quality", default="medium", choices=["low", "medium", "high"],
                    help="the image model's quality: high costs several times more")
    hm.add_argument("--model", default=None, help="the image model (default: the kit's, gpt-image-2.5-flare)")
    hm.add_argument("--attempts", type=int, default=3, help="sheets painted at most (the first + repaints)")
    hm.add_argument("--mannequin", action="store_true",
                    help="no painting: the wooden mannequin drawn by code (free), to block out scenes")
    hm.add_argument("--no-actions", action="store_true", help="do not run `tadam hero check` after making it")
    hc = hs.add_parser("check", help="play every action on the hero in the engine (free; ~30 s, a hero in a skirt "
                                     "longer): tadam hero check <slug>")
    hc.add_argument("slug")
    hc.add_argument("--json", action="store_true", help="print actions.json")

    st = sub.add_parser("set", help="sets: paint a set from its kit.json")
    ss = st.add_subparsers(dest="what", metavar="<what>")
    sm = ss.add_parser("make", help="paint the room and the pieces, write set.json: tadam set make <slug>",
                       description="PAID (unless --placeholder or --layout-only): paints 1 picture for the room and 1 "
                                   "per piece with YOUR OpenAI key at medium quality unless --quality says otherwise: "
                                   "about $0.04-0.1 a set at medium (Nov 2026), several times more at high. Prints the "
                                   "pictures painted and their cost from the API's usage; sets/<slug>/meta.json keeps "
                                   "them.",
                       formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    sm.add_argument("slug")
    sm.add_argument("--only", default="", help="only these parts: room,desk (default: all)")
    sm.add_argument("--layout-only", action="store_true", help="no painting: only lay out set.json again")
    sm.add_argument("--quality", default="medium", choices=["low", "medium", "high"],
                    help="the image model's quality: high costs several times more")
    sm.add_argument("--placeholder", action="store_true",
                    help="no painting: a plain room and flat shapes drawn by code (free), to block out scenes")

    ck = sub.add_parser("check", help="check the world and its scripts (exit 1 on errors)")
    ck.add_argument("episode", nargs="?", help="one episode (default: all)")
    ck.add_argument("--json", action="store_true", help="print the check-result JSON")
    ck.add_argument("--engine", action="store_true", help="also play every shot through in the engine, unseen")
    ck.add_argument("--verbose", "-v", action="store_true", help="also the info-level notes (a shot with no hero, ...)")

    cv = sub.add_parser("cover", help="the world's cover from a frame: tadam cover [episode] [--shot sh2 --at 1.5]")
    cv.add_argument("episode", nargs="?", default=None, help="the episode (default: the first)")
    cv.add_argument("--shot", help="the shot (default: the first, usually the title card)")
    cv.add_argument("--at", type=float, help="seconds into the shot (default: its middle)")
    cv.add_argument("--lang", help="the language of the texts (default: the world's first)")
    cv.add_argument("--board-preview", action="store_true", help="the site's look of the faces (see frames)")

    def show_args(x, shot_help=None):
        x.add_argument("episode")
        if shot_help:
            x.add_argument("--shot", help=shot_help)
        x.add_argument("--lang", help="the language of the texts (default: the world's first)")
        x.add_argument("--board-preview", action="store_true",
                       help="the site's look: a placeholder where the recorded face will be, the head as the site "
                            "enlarges it")
        x.add_argument("--no-voice", action="store_true", help="narration as subtitles, without asking the server")

    pl = sub.add_parser("play", help="play the episode in a window: tadam play <episode> [--shot sh3 --at 1.5 "
                                     "--paused]; Space pauses it; `tadam play where` says where it stands")
    show_args(pl, "begin at this shot")
    pl.add_argument("--size", default="450x800", help="the window, WxH (450x800)")
    pl.add_argument("--at", type=float, default=0.0, help="seconds into the shot to begin at")
    pl.add_argument("--paused", action="store_true", help="open paused there")
    pl.add_argument("--json", action="store_true", help="(tadam play where) the state as JSON")
    fr = sub.add_parser("frames", help="PNG frames: --shot sh3 --at 1.5, or --sheet (a frame from every shot)")
    show_args(fr, "the shot of the frame")
    fr.add_argument("--at", type=float, help="seconds into the shot (default: its middle)")
    fr.add_argument("--sheet", action="store_true", help="one contact sheet: the middle of every shot, labelled")
    fr.add_argument("--around", type=float, help="seconds into the shot: several frames round that moment, and a "
                                                  "strip of them (the motion, not one pose)")
    fr.add_argument("--frames", type=int, default=6, help="(--around) how many frames (6)")
    fr.add_argument("--span", type=float, default=1.0, help="(--around) over how many seconds (1.0)")
    fr.add_argument("--out", help="the PNG to write (default: .tadam/frames/<episode>/...)")
    fr.add_argument("--json", action="store_true", help="print the paths as JSON")
    fm = sub.add_parser("film", help="a draft MP4 of the episode (picture, narration, music, subtitles)")
    show_args(fm)
    fm.add_argument("--out", help="the MP4 (default: .tadam/films/<episode>.mp4)")

    jn = sub.add_parser("join", help="become an editor: your email, the code from the letter, the studio's rules, "
                                     "the agreement YOU type, a key (run it yourself in your own terminal)")
    jn.add_argument("email", nargs="?", help="your email (asked when left out)")
    jn.add_argument("--lang", choices=["ru", "en"], default="ru", help="the language of the rules (ru)")
    jn.add_argument("--terms", action="store_true", help="also show the full Editor Terms before the question")
    lg = sub.add_parser("login", help="this computer gets a studio key: by email and code (like join; the rules are "
                                      "accepted already), or --key (typed hidden, or TADAM_STUDIO_KEY)")
    lg.add_argument("email", nargs="?", help="your email (asked when left out)")
    lg.add_argument("--key", action="store_true", help="type an existing studio key (hidden) instead of the email")
    lg.add_argument("--staff", action="store_true", help="the project's owner: store the staff key (tdm_..., typed "
                                                          "hidden, or TADAM_STAFF_KEY) for `tadam review`")
    lg.add_argument("--lang", choices=["ru", "en"], default="ru", help="the language of the rules, if asked (ru)")
    lg.add_argument("--terms", action="store_true", help="also show the full Editor Terms, if the rules are asked")
    lg.add_argument("--json", action="store_true")
    lo = sub.add_parser("logout", help="forget the stored keys of this server")
    lo.add_argument("--staff", action="store_true", help="only the staff key")
    ru = sub.add_parser("rules", help="read the studio's rules (no sign-in needed)")
    ru.add_argument("--lang", choices=["ru", "en"], default="ru")
    ru.add_argument("--terms", action="store_true", help="also the full Editor Terms")
    ps = sub.add_parser("push", help="send the world folder to the server (only what changed)")
    ps.add_argument("--confirm", action="store_true",
                    help="accept a breaking change that makes other people's sent roles stale (the project's owner "
                         "only, after the person said yes to exactly that)")
    ps.add_argument("--json", action="store_true", help="print the server's answer as JSON")
    pu = sub.add_parser("pull", help="get the server's last revision: merge it into this folder, or fetch a world "
                                     "into a new folder")
    pu.add_argument("slug", nargs="?", help="the world (default: this folder's)")
    pu.add_argument("--dir", help="where the new folder goes (a first pull; default: here)")
    pu.add_argument("--json", action="store_true")
    df = sub.add_parser("diff", help="what changed: server -> this folder; <rev> -> this folder; <rev> <rev>")
    df.add_argument("revs", nargs="*", help="0, 1 or 2 revisions (revisions this folder pushed or pulled)")
    df.add_argument("--json", action="store_true")
    stt = sub.add_parser("status", help="your worlds and episodes on the server, submissions, remarks, what is "
                                        "missing before a submission")
    stt.add_argument("--json", action="store_true")

    sb = sub.add_parser("submit", help='send an episode to the owner: tadam submit <episode> "<note>" (only after '
                                       'the person said to send it)')
    sb.add_argument("episode", type=int)
    sb.add_argument("note", nargs="?", default="", help="a word to the owner")
    sb.add_argument("--kind", choices=["publish", "revision"], help="default: publish, or revision for a published "
                                                                     "episode")
    sb.add_argument("--json", action="store_true")
    wd = sub.add_parser("withdraw", help="take back the open submission of this world")
    rp = sub.add_parser("reply", help='answer in the thread of the open submission: tadam reply "<text>"')
    rp.add_argument("text")
    rp.add_argument("--shot", help="about this shot (sh3)")
    for x in (wd, rp):
        x.add_argument("--episode", type=int, help="the submission of this episode")
        x.add_argument("--id", help="the submission's id (`tadam status` lists them)")
        x.add_argument("--json", action="store_true")
    up = sub.add_parser("unpublish", help='ask the owner to take the world (or --episode N) off the site: '
                                          'tadam unpublish "<reason>"')
    up.add_argument("reason")
    up.add_argument("--episode", type=int)
    up.add_argument("--json", action="store_true")
    sv = sub.add_parser("studio-version", help="mark a film of your own scene as the episode's studio version: "
                                               "tadam studio-version <episode> <videoId> (none: unmark)")
    sv.add_argument("episode", type=int)
    sv.add_argument("version", help="the video's id from its page on the site, or none")
    sv.add_argument("--json", action="store_true")

    rv = sub.add_parser("review", help="the project's owner only (staff key): the queue of submissions and the "
                                       "decisions")
    rs = rv.add_subparsers(dest="what", metavar="<what>")
    rl = rs.add_parser("list", help="the queue (pending, oldest first)")
    rl.add_argument("--status", choices=["pending", "approved", "changes", "rejected", "withdrawn"], default="pending")
    rl.add_argument("--all", action="store_true", help="every status")
    rl.add_argument("--kind", choices=["publish", "revision", "unpublish"])
    rl.add_argument("--of", dest="of_world", metavar="SLUG", help="only this world")
    rl.add_argument("--json", action="store_true")
    rsh = rs.add_parser("show", help="one submission: video, world, heroes, script by shots, check, impact, thread")
    rsh.add_argument("id")
    rsh.add_argument("--lang", choices=["ru", "en"], default="ru")
    rsh.add_argument("--json", action="store_true")
    ra = rs.add_parser("approve", help="approve (you type the id to confirm)")
    ra.add_argument("id")
    ra.add_argument("--note", help="a word to the author")
    ra.add_argument("--stale-version", action="store_true", help="approve although the studio video is older than "
                                                                 "the current film (you watched it)")
    ra.add_argument("--confirm-breaking", action="store_true", help="accept a breaking revision that makes other "
                                                                    "people's sent roles stale")
    ra.add_argument("--slug", help="a new address for the world (its first publication only)")
    rr = rs.add_parser("return", help='return with remarks: tadam review return <id> "<remarks>" '
                                      '[--shot sh3 "<remark>"]...')
    rr.add_argument("id")
    rr.add_argument("text")
    rr.add_argument("--shot", nargs=2, action="append", default=[], metavar=("SHOT", "REMARK"),
                    help="a remark about one shot (repeat)")
    rj = rs.add_parser("reject", help="reject with a reason (you type the id to confirm)")
    rj.add_argument("id")
    rj.add_argument("reason")
    ry = rs.add_parser("reply", help="write in the thread as the owner")
    ry.add_argument("id")
    ry.add_argument("text")
    ry.add_argument("--shot")
    for x in (ra, rr, rj, ry):
        x.add_argument("--json", action="store_true")
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
    if a.what == "check":
        return _hero_check(_world(a), a.slug, a.json)
    if a.what != "make":
        _out('tadam hero make <slug> "<description>"  |  tadam hero check <slug>')
        return 2
    w = _world(a)
    if not a.mannequin:
        _out(f"Paints 2 pictures with YOUR OpenAI key at {a.quality} quality (portrait + pattern sheet; one more per "
             f"repainted sheet, at most {max(a.attempts - 1, 0)}): about $0.05 a hero at medium, several times more "
             f"at high.")
    r = hero.make(w, a.slug, a.description, style=a.style, rig=a.rig, quality=a.quality, model=a.model,
                  attempts=a.attempts, mannequin=a.mannequin, log=_out)
    _out(f"{a.slug}: {hero.describe(r)}")
    if not r["passed"]:
        return 1
    if a.no_actions:
        return 0
    from tadam.engine import EngineError
    _out(f"checking every action on {a.slug} in the engine ...")
    try:
        return _hero_check(w, a.slug, False)
    except EngineError as e:
        _out(f"the action check did not run ({e}); run `tadam hero check {a.slug}` when the engine works")
        return 0


def _hero_check(w, slug: str, as_json: bool) -> int:
    from tadam import actions
    res = actions.run(w, slug)
    _out(json.dumps(res, ensure_ascii=False, indent=1) if as_json else (slug + ":" + chr(10) + actions.table(res)))
    return 0 if res["passed"] else 1


def cmd_set(a) -> int:
    from tadam import setmake
    if a.what != "make":
        _out("tadam set make <slug>")
        return 2
    w = _world(a)
    if not (a.layout_only or a.placeholder):
        _out(f"Paints the room and every piece with YOUR OpenAI key at {a.quality} quality (one picture each): "
             f"about $0.04-0.1 a set at medium, several times more at high.")
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
        shown = found if a.verbose else [i for i in found if i.level != "info"]
        _out(issues.format_text(shown))
        hidden = len(found) - len(shown)
        if hidden:
            _out(f"({hidden} info note(s) not shown: --verbose shows them)")
        for line in check.lengths(w.root, a.episode):
            _out(line)
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


def _episode(a):
    from tadam import episode, tts
    w = _world(a)
    ep = episode.build(w, a.episode, lang=a.lang, link=None if a.no_voice else tts.link_from_env(),
                       voice=not a.no_voice)
    for note in ep.notes:
        _out(note)
    return ep


def cmd_play(a) -> int:
    from tadam import render
    if a.episode == "where":
        return cmd_play_where(a)
    try:
        win = tuple(int(x) for x in a.size.lower().split("x"))
        assert len(win) == 2 and min(win) > 0
    except (ValueError, AssertionError):
        _out(f"--size {a.size}: write WxH, like 450x800")
        return 2
    ep = _episode(a)
    start = ep.index(a.shot) if a.shot else 0
    if a.at < 0 or a.at > ep.shots[start].seconds:
        _out(f"--at {a.at:g}: shot {ep.shots[start].id} lasts {ep.shots[start].seconds:g} s")
        return 2
    _out(f"playing episode {ep.n} from {ep.shots[start].id} ({ep.seconds - ep.shots[start].start:.1f} s). "
         f"Space pauses, arrows step, M marks, B opens the action library, Esc closes; `tadam play where` tells "
         f"Claude where it stands. Changes in the world are played at once.")

    def again():
        from tadam import episode, tts
        e = episode.build(ep.world, a.episode, lang=a.lang, link=None if a.no_voice else tts.link_from_env(),
                          voice=not a.no_voice)
        for note in e.notes:
            _out(note)
        return e

    render.play(ep, start, a.board_preview, win, log=_out, start_at=a.at, paused=a.paused, rebuild=again)
    return 0


def cmd_play_where(a) -> int:
    from tadam import where
    w = _world(a)
    rep = where.report(w, where.read_state(w))
    if a.json:
        _out(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        _out(where.text(rep))
    return 0 if rep.get("found") else 1


def cmd_frames(a) -> int:
    from tadam import render
    clock = render.Clock()
    ep = _episode(a)
    if a.around is not None:
        if not a.shot:
            _out("tadam frames <episode> --shot <id> --around <seconds> [--frames 6] [--span 1.0]")
            return 2
        i = ep.index(a.shot)
        s = ep.shots[i]
        if a.around < 0 or a.around > s.seconds:
            _out(f"--around {a.around:g}: shot {s.id} lasts {s.seconds:g} s")
            return 2
        if a.frames < 1 or a.frames > 24 or a.span <= 0:
            _out("--frames: 1 to 24; --span: more than 0 seconds")
            return 2
        times = render.around_times(a.around, s.seconds, a.frames, a.span)
        d = render.frames_dir(ep)
        pngs = render.snaps(ep, [(i, t, d / f"{s.id}@{t:.2f}.png") for t in times], a.board_preview)
        out = Path(a.out).resolve() if a.out else d / f"{s.id}~{a.around:.2f}.png"
        strip = render.make_strip(ep, s.id, pngs, times, out, at=a.around)
        res = {"strip": strip.as_posix(), "frames": [{"shot": s.id, "at": t, "png": p.as_posix()}
                                                     for t, p in zip(times, pngs)]}
        res["seconds"] = clock()
        if a.json:
            _out(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            _out(res["strip"])
        return 0
    if a.sheet:
        out = Path(a.out).resolve() if a.out else None
        path, _ = render.sheet(ep, out, a.board_preview)
        res = {"sheet": path.as_posix(), "shots": [{"shot": s.id, "at": round(s.seconds / 2, 2),
                                                   "seconds": s.seconds, "remark": s.remark} for s in ep.shots]}
    else:
        if not a.shot:
            _out("tadam frames <episode> --shot <id> [--at seconds], or --sheet")
            return 2
        i = ep.index(a.shot)
        s = ep.shots[i]
        at = s.seconds / 2 if a.at is None else a.at
        if at < 0 or at > s.seconds:
            _out(f"--at {at:g}: shot {s.id} lasts {s.seconds:g} s")
            return 2
        out = Path(a.out).resolve() if a.out else render.frames_dir(ep) / f"{s.id}@{at:.2f}.png"
        render.snaps(ep, [(i, at, out)], a.board_preview)
        res = {"frames": [{"shot": s.id, "at": round(at, 2), "png": out.as_posix()}]}
    res["seconds"] = clock()
    if a.json:
        _out(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for f in res.get("frames", []):
            _out(f["png"])
        if "sheet" in res:
            _out(res["sheet"])
    return 0


def cmd_film(a) -> int:
    from tadam import render
    clock = render.Clock()
    ep = _episode(a)
    out = Path(a.out).resolve() if a.out else ep.world.work_dir() / "films" / f"{ep.n}.mp4"
    _out(f"filming episode {ep.n}: {len(ep.shots)} shots, {ep.seconds:.1f} s ...")
    render.film(ep, out, a.board_preview, log=_out)
    _out(f"{out.as_posix()}\nfilm {ep.seconds:.1f} s, rendered in {clock():.0f} s")
    return 0


def cmd_cover(a) -> int:
    from tadam import cover
    ep = _episode_of(a, a.episode)
    res = cover.make(ep, a.shot, a.at, a.board_preview)
    _out(f"cover: {res['path']} ({res['size'][0]}x{res['size'][1]}, a frame of shot {res['shot']} at {res['at']:g} s)")
    if res.get("moved"):
        _out(f"the old cover is kept in {res['moved']}")
    if res.get("declared"):
        _out(f"sources.json: {res['rel']} = generated by tadam cover (a frame of the world's own pictures)")
    return 0


def _episode_of(a, n):
    """The episode `n` (default: the world's first) for a command that needs one built, with no narration voice."""
    from tadam import episode
    from tadam.world import WorldError
    w = _world(a)
    eps = w.episodes()
    n = n or (eps[0] if eps else None)
    if not n:
        raise WorldError("the world has no episode yet: a cover is a frame of one (`tadam new episode 1`)")
    ep = episode.build(w, n, lang=a.lang, link=None, voice=False)
    return ep


# ------------------------------------------------------------------------------------------------ the server

def _api(required: bool = True):
    from tadam import api, link
    lk = link.current()
    if lk is None:
        if required:
            raise api.no_key()
        return None
    return api.Api(lk)


def _read_key(env_name: str | None = None, prompt: str = "studio key (tds_..., hidden): ") -> str | None:
    """The key: from the env, else typed (hidden) at a real keyboard. Never echoed, never printed."""
    import getpass
    import os
    from tadam import link
    env_name = env_name or link.KEY_ENV
    env = (os.environ.get(env_name) or "").strip()
    if env:
        return env
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        flag = "--staff" if env_name == link.STAFF_ENV else "--key"
        _out(f"tadam login {flag} reads the key from a real keyboard (hidden), or from {env_name}:\n"
             f"  run it yourself in a terminal, or: skey run --only {env_name} -- tadam login {flag}\n"
             "Never paste the key into a chat.")
        return None
    try:
        return getpass.getpass(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return None


def cmd_join(a) -> int:
    from tadam import join, keyboard, link
    keyboard.require("`tadam join` (your email, the code from the letter and your agreement to the studio's rules)")
    url = link.server_url()
    _out(f"joining the studio of {url}: a code goes to your email; then the studio's rules, in full; you accept them "
         f"by typing the word yourself")
    _joined(join.email_flow(url, keyboard.ask, _out, a.email, a.lang, a.terms, mode="join"))
    return 0


def _joined(j) -> None:
    if j.version:
        _out(f"accepted the studio's rules, version {j.version} (a copy comes by email)")
    if j.stored:
        _out(f"signed in as {j.email}; the studio key is stored in {j.stored} (only for you; never shown; "
             f"`tadam logout` removes it)")
        _out("next: `tadam new world <slug>`, or `tadam status`")
    else:
        _out(f"{j.email}: the rules are accepted, but no key came" + ("" if j.access else " (studio access is off)"))


def cmd_login(a) -> int:
    import os
    from tadam import api, join, keyboard, link
    if a.staff:
        return _login_staff(a)
    if not (a.key or (os.environ.get(link.KEY_ENV) or "").strip()):
        keyboard.require("`tadam login` (your email and the code from the letter)")
        _joined(join.email_flow(link.server_url(), keyboard.ask, _out, a.email, a.lang, a.terms, mode="login"))
        return 0
    key = _read_key()
    if not key:
        return 2
    if not link.looks_like_key(key):
        _out("that is not a studio key (tds_<8 letters>_<secret>): make one in the cabinet (studio.tadamshow.com)")
        return 2
    url = link.server_url()
    lk = link.Link(url, key)
    try:
        me = api.Api(lk).get("/api/studio/me")
    except api.ApiError as e:
        _out(f"not stored: {join.banned(e) or e}")
        return 1
    user = me.get("user") or {}
    who = {"id": user.get("id"), "handle": user.get("handle")}
    path = link.store(url, key, who)
    rules = me.get("rules") or {}
    info = {"server": url, "user": link.mask_email(user.get("email")), "access": bool(me.get("access")),
            "staff": bool(me.get("staff")), "rulesOutdated": bool(rules.get("outdated")), "stored": str(path)}
    if a.json:
        _out(json.dumps(info, ensure_ascii=False, indent=1))
        return 0
    _out(f"signed in to {url} as {info['user']}" + (" (the project's owner side)" if info["staff"] else ""))
    _out(f"the key is stored in {path} (only for you; `tadam logout` removes it)")
    if not info["access"] and not rules.get("accepted"):
        _out("studio access is not on yet: accept the studio's rules first (`tadam join`, yourself, in a terminal)")
    if info["rulesOutdated"] and info["staff"]:
        # the server does not ask the project's owner side (staff admin+) to accept the editors' rules
        _out("the studio's rules have a new version (the project's owner side is not asked to accept it)")
    elif info["rulesOutdated"]:
        if keyboard.real():
            v = join.accept_new_rules(api.Api(lk), keyboard.ask, _out, me, a.lang, a.terms)
            _out(f"accepted the studio's rules, version {v}")
        else:
            _out("the studio's rules have a new version: pushing and voicing wait until you accept it. Run "
                 "`tadam login --key` yourself in a terminal: it shows the rules and you type the agreement.")
    return 0


def _login_staff(a) -> int:
    from tadam import api, link
    key = _read_key(link.STAFF_ENV, "staff key (tdm_..., hidden): ")
    if not key:
        return 2
    if not link.looks_like_staff_key(key):
        _out("that is not a staff key (tdm_<8 letters>_<secret>): make one in the admin (API keys)")
        return 2
    url = link.server_url()
    try:
        api.Api(link.Link(url, key)).get("/api/admin/studio/submissions?limit=1")
    except api.ApiError as e:
        _out(f"not stored: {e}" + (" (the review needs an admin's key)" if e.status == 403 else ""))
        return 1
    path = link.store_staff(url, key)
    _out(f"the staff key for `tadam review` is stored in {path} (only for you; `tadam logout --staff` removes it)")
    return 0


def cmd_logout(a) -> int:
    import os
    from tadam import link
    url = link.server_url()
    if a.staff:
        _out(f"the staff key of {url} is removed" if link.forget(url, staff_only=True)
             else f"no stored staff key for {url}")
        return 0
    _out(f"the keys of {url} are removed" if link.forget(url) else f"no stored key for {url}")
    for env in (link.KEY_ENV, link.STAFF_ENV):
        if os.environ.get(env):
            _out(f"({env} is still set in this shell: it is used while it is set)")
    return 0


def cmd_rules(a) -> int:
    from tadam import api, join, link
    r = join.get_rules(api.Api(link.Link(link.server_url(), "")), a.lang)
    join.show_rules(r, _out, a.terms)
    _out("to accept them: `tadam join` (yourself, in your own terminal)")
    return 0


def cmd_push(a) -> int:
    from tadam import sync
    w = _world(a)
    res = sync.push(w.root, _api(), confirm=a.confirm, log=_out)
    _out(json.dumps(res.response, ensure_ascii=False, indent=1) if a.json else sync.describe_push(res))
    return 0 if (res.response.get("check") or {}).get("ok", True) else 1


def cmd_pull(a) -> int:
    from tadam import sync
    root = None if a.dir else sync.find_root(a.world)
    if root is not None and a.slug and sync.world_slug(root) != a.slug:
        raise sync.SyncError(f"you are inside the folder of another world: run `tadam pull {a.slug}` outside it, "
                             f"or add --dir <folder>")
    res = sync.pull(_api(), a.slug, root, Path(a.dir).resolve() if a.dir else None, log=_out)
    if a.json:
        _out(json.dumps({"root": str(res.root), "rev": res.rev, "first": res.first, "taken": res.taken,
                         "kept": res.kept, "conflicts": [p + ".server" for p in res.conflicts],
                         "removed": res.removed, "keptRemoved": res.kept_removed,
                         "movedTo": str(res.moved_to) if res.moved_to else None}, ensure_ascii=False, indent=1))
    else:
        _out(sync.describe_pull(res))
    return 0


def cmd_diff(a) -> int:
    from tadam import sync
    w = _world(a)
    if len(a.revs) > 2 or not all(r.isdigit() for r in a.revs):
        _out("tadam diff [rev [rev]]: revision numbers")
        return 2
    sides = ("server", "local") if not a.revs else (a.revs[0], "local") if len(a.revs) == 1 else tuple(a.revs)
    d = sync.diff(w.root, sides[0], sides[1], _api(required=sides[0] == "server"))
    _out(json.dumps(d, ensure_ascii=False, indent=1) if a.json else sync.describe_diff(d))
    return 0


def cmd_status(a) -> int:
    from tadam import sync
    s = _api().get("/api/studio/status")
    if a.json:
        _out(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    root = sync.find_root(a.world)
    _out(sync.describe_status(s, sync.read_link(root) if root else None))
    from tadam import submissions
    lines = submissions.threads(_api(), s)
    if lines:
        _out("the open submissions and their threads:")
        _out("\n".join(lines))
    return 0


# ------------------------------------------------------------------------------------------------ submissions

def _slug(a) -> str:
    from tadam import sync
    from tadam.world import WorldError
    root = sync.find_root(a.world)
    if root is None:
        raise WorldError("run it inside the world's folder (or name it with --world <folder>)")
    return sync.world_slug(root)


def _decided(a, d: dict) -> int:
    from tadam import submissions
    _out(json.dumps(d, ensure_ascii=False, indent=1) if a.json else submissions.describe_decided(d))
    return 0


def cmd_submit(a) -> int:
    from tadam import submissions
    slug = _slug(a)
    d = submissions.submit(_api(), slug, a.episode, a.note, a.kind)
    if not a.json:
        _out(f"episode {a.episode} of {slug} is ready and went to the owner: they watch the studio version and "
             f"approve it or return it with remarks (`tadam status` shows the answer and the thread)")
    return _decided(a, d)


def cmd_withdraw(a) -> int:
    from tadam import submissions
    api = _api()
    x = submissions.pick_open(api, _slug(a), a.episode, a.id)
    return _decided(a, submissions.withdraw(api, x["id"]))


def cmd_reply(a) -> int:
    from tadam import submissions
    api = _api()
    x = submissions.pick_open(api, _slug(a), a.episode, a.id)
    return _decided(a, submissions.reply(api, x["id"], a.text, a.shot))


def cmd_unpublish(a) -> int:
    from tadam import submissions
    return _decided(a, submissions.unpublish(_api(), _slug(a), a.reason, a.episode))


def cmd_studio_version(a) -> int:
    from tadam import submissions
    vid = None if a.version.strip().lower() in ("none", "null", "-") else a.version.strip()
    d = submissions.studio_version(_api(), _slug(a), a.episode, vid)
    _out(json.dumps(d, ensure_ascii=False, indent=1) if a.json else submissions.describe_marked(d))
    return 0


# ------------------------------------------------------------------------------------------------ the owner's review

def _staff_api():
    from tadam import api, link
    lk = link.staff()
    if lk is None:
        raise api.ApiError(0, "no_key", f"`tadam review` is for the project's owner: it needs a staff key "
                                        f"(`tadam login --staff`, or set {link.STAFF_ENV})")
    return api.Api(lk)


def _confirm_id(sid: str, verb: str, api) -> bool:
    """The person types the submission's id at their own keyboard; anything else stops, nothing is sent."""
    from tadam import keyboard, submissions
    keyboard.require(f"the confirmation to {verb} a submission")
    r = submissions.review(api, sid)
    s, w, e = r.get("submission") or {}, r.get("world") or {}, r.get("episode")
    _out(f"to {verb}: {s.get('kind')} of {w.get('slug')}" + (f" episode {e.get('number')}" if e else " (the world)")
         + f", now {s.get('status')}")
    try:
        typed = keyboard.ask(f"type the submission id to {verb} it ({sid}): ", f"the confirmation to {verb}")
    except (EOFError, KeyboardInterrupt):
        typed = ""
    if typed.strip() != sid:
        _out(f"not {verb}d: the id was not typed (nothing was sent)".replace("rejectd", "rejected"))
        return False
    return True


def cmd_review(a) -> int:
    from tadam import submissions
    if a.what is None:
        _out('tadam review list | show <id> | approve <id> | return <id> "<remarks>" [--shot sh3 "<remark>"] | '
             'reject <id> "<reason>" | reply <id> "<text>"')
        return 2
    api = _staff_api()
    if a.what == "list":
        rows = submissions.queue(api, None if a.all else a.status, a.kind, a.of_world)
        _out(json.dumps(rows, ensure_ascii=False, indent=1) if a.json else submissions.describe_queue(rows))
        return 0
    if a.what == "show":
        r = submissions.review(api, a.id, a.lang)
        _out(json.dumps(r, ensure_ascii=False, indent=1) if a.json else submissions.describe_review(r))
        return 0
    if a.what == "approve":
        if not _confirm_id(a.id, "approve", api):
            return 2
        return _decided(a, submissions.approve(api, a.id, a.note, a.confirm_breaking, a.stale_version, a.slug))
    if a.what == "reject":
        if not _confirm_id(a.id, "reject", api):
            return 2
        return _decided(a, submissions.reject(api, a.id, a.reason))
    if a.what == "return":
        return _decided(a, submissions.return_(api, a.id, a.text, [(sh, t) for sh, t in a.shot]))
    if a.what == "reply":
        return _decided(a, submissions.reply(api, a.id, a.text, a.shot, owner=True))
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    # (piped, as Claude reads it: UTF-8 whatever the console's code page is, so Russian texts come out right)
    if hasattr(sys.stdout, "reconfigure") and not sys.stdout.isatty():
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.command == "doctor":
        return doctor.main()
    if a.command is None:
        ap.print_help()
        return 0
    from tadam.api import ApiError
    from tadam.engine import EngineError
    from tadam.mix import MixError
    from tadam.openai_images import GenerationError
    from tadam.sync import SyncError
    from tadam.world import WorldError
    from tadam.join import Stop, banned
    from tadam.keyboard import NoKeyboard
    from tadam.submissions import Refused, missing_lines
    try:
        return {"new": cmd_new, "hero": cmd_hero, "set": cmd_set, "check": cmd_check, "play": cmd_play,
                "frames": cmd_frames, "film": cmd_film, "cover": cmd_cover, "login": cmd_login, "logout": cmd_logout, "join": cmd_join,
                "rules": cmd_rules, "push": cmd_push, "pull": cmd_pull, "diff": cmd_diff, "status": cmd_status,
                "submit": cmd_submit, "withdraw": cmd_withdraw, "reply": cmd_reply, "unpublish": cmd_unpublish,
                "studio-version": cmd_studio_version, "review": cmd_review}[a.command](a)
    except Refused as e:
        _out(f"tadam: {e}" + ("\n" + "\n".join(missing_lines(e.missing)) if e.missing else ""))
        return 1
    except Stop as e:
        _out(f"tadam: {e}")
        return e.code
    except NoKeyboard as e:
        _out(f"tadam: {e}")
        return 2
    except ApiError as e:
        _out(f"tadam: {banned(e) or e}")
        return 1
    except (WorldError, GenerationError, EngineError, MixError, SyncError) as e:
        _out(f"tadam: {e}")
        return 1
