"""`tadam check [episode]`: the world folder and its scripts, checked the way the server checks them on push
(studio-tz 6.3), as far as it can be done on the editor's computer: the schemas, the references inside a script, that
every name exists in the world (heroes, sets, media, exact case), that the puppets passed their audit, the texts in
every language of the world, the studio's filming rules, and every scene check of tadam.scenecheck on the scenes the
script turns into. The server checks again and does not trust this one.

    issues = check_world(Path("my-world"), episode="1")
Exit code of the command: 1 when there is an error. Codes: CODES here and tadam.scenecheck.CODES.
"""
from __future__ import annotations

from pathlib import Path

from tadam import resolve, schema, scenecheck
from tadam.issues import Issue
from tadam.paths import engine_dir
from tadam.world import EPISODE, SLUG, World, exact, is_safe_name, read_json

EPISODE_MAX_SECONDS = 300.0      # an episode's length (until the server names its own limit)
LINE_LONG = 20.0                 # a line longer than this, with no maxSeconds, is worth a warning
RECORDED = {"read", "pause", "look"}    # steps a person records on the phone: they need a hint and look marks
TODO = "TODO"

CODES = {
    "json_invalid": ("error", "a JSON file cannot be read"),
    "schema": ("error", "a file does not fit its JSON Schema"),
    "world_missing": ("error", "no world.json"),
    "todo_text": ("warning", "a text is still the template's TODO"),
    "bible_incomplete": ("warning", "the bible lacks its idea, tone or style (needed before a submission)"),
    "cover_missing": ("warning", "no cover.png"),
    "text_missing_lang": ("error", "a text lacks one of the world's languages"),
    "folder_name": ("error", "a hero, set or episode folder has a name that is not allowed"),
    "hero_json_missing": ("error", "a hero folder without hero.json"),
    "hero_missing": ("error", "the cast names a hero the world does not have"),
    "puppet_missing": ("error", "a hero has no puppet yet (tadam hero make)"),
    "puppet_not_passed": ("error", "a hero's puppet did not pass its audit"),
    "puppet_parts_missing": ("error", "a picture of the puppet's parts is missing"),
    "hero_actions_missing": ("warning", "the hero's actions were never checked in the engine (tadam hero check)"),
    "hero_actions_stale": ("warning", "the puppet changed after its action check (tadam hero check again)"),
    "hero_actions_failed": ("error", "the hero fails a stage-1 action: draw it again, never tune it"),
    "puppet_no_board": ("warning", "the head has no face board: the site shows the recorded head whole"),
    "set_missing": ("error", "the script names a set the world does not have"),
    "set_invalid": ("error", "a set.json is malformed"),
    "set_file_missing": ("error", "a picture a set names does not exist"),
    "media_missing": ("error", "a music, ambience or prop file the script names is not in media/"),
    "name_case": ("error", "a name differs from the file's name only in letter case"),
    "episode_missing": ("error", "no such episode folder"),
    "script_missing": ("error", "an episode without script.json"),
    "script_v1": ("info", "a version-1 script: only the server checks it in full"),
    "hero_not_in_cast": ("error", "roles of a hero who is not in the cast"),
    "hero_no_steps": ("error", "a hero of the cast without steps"),
    "step_key_twice": ("error", "a step key used twice"),
    "line_no_text": ("error", "a line (read step) without text"),
    "shot_id_twice": ("error", "a shot id used twice"),
    "say_unknown": ("error", "`say` names a step that does not exist"),
    "say_not_line": ("error", "`say` names a step that is not a line"),
    "listen_unknown": ("error", "`listen` names no step of that hero"),
    "shot_no_length": ("error", "a shot with no line and no narration needs seconds"),
    "film_not_vertical": ("error", "the film is not vertical"),
    "actor_not_in_cast": ("error", "a shot's hero is not in the cast"),
    "actor_twice": ("error", "a hero stands twice in one shot"),
    "speaker_not_in_shot": ("warning", "the hero who speaks is not in the shot"),
    "step_no_hint": ("error", "a recorded step has no hint for the person who records it"),
    "step_no_look": ("error", "a recorded step has no look marks"),
    "line_too_long": ("error", "a line takes longer to say than its maxSeconds"),
    "line_long": ("warning", "a long line with no maxSeconds"),
    "episode_too_long": ("error", "the episode is longer than the limit"),
    "stage_option_unknown": ("warning", "a stage option the engine does not take (it is dropped)"),
}
# scene checks reported once, at their source, by the world checks above
_SOURCE = {"puppet_missing", "background_missing"}


class _Run:
    def __init__(self, root: Path):
        self.w = World(root)
        self.out: list[Issue] = []
        self.langs = ["ru"]

    def add(self, code: str, where: str, message: str, level: str | None = None):
        self.out.append(Issue(level or CODES[code][0], where, code, message))

    # ------------------------------------------------------------------ helpers
    def load(self, rel: str, schema_name: str | None) -> object | None:
        data, err = read_json(self.w.root / rel)
        if err == "missing":
            return None
        if err:
            self.add("json_invalid", rel, err)
            return None
        if schema_name:
            for path, msg in schema.validate(schema_name, data):
                self.add("schema", f"{rel} {path}", msg)
        return data

    def texts(self, rel: str, path: str, loc: object, required: bool = True):
        """One bilingual text: every language of the world, and no template TODO left."""
        if not isinstance(loc, dict):
            return
        for lang in self.langs:
            v = loc.get(lang)
            if not (isinstance(v, str) and v.strip()):
                if required or any(isinstance(x, str) and x.strip() for x in loc.values()):
                    self.add("text_missing_lang", f"{rel} {path}", f"no '{lang}' text (the world is in "
                                                                     f"{', '.join(self.langs)})")
            elif v.strip().startswith(TODO):
                self.add("todo_text", f"{rel} {path}.{lang}", "still the template's TODO: write the real text")

    def media(self, rel: str, path: str, name: object):
        if not is_safe_name(name):
            return                                   # (the schema says what is wrong with the name)
        state = exact(self.w.root, f"media/{name}")
        if state == "case":
            self.add("name_case", f"{rel} {path}", f"media/{name}: the file's name differs in letter case")
        elif state == "missing":
            self.add("media_missing", f"{rel} {path}", f"no file media/{name}")

    # ------------------------------------------------------------------ the world
    def world(self):
        w = self.w
        if not (w.root / "world.json").is_file():
            self.add("world_missing", "world.json", f"no world.json in {w.root}: `tadam new world <slug>`")
            return
        data = self.load("world.json", "world")
        if not isinstance(data, dict):
            return
        self.langs = [x for x in (data.get("langs") or ["ru"]) if x in ("ru", "en")] or ["ru"]
        for k in ("title", "tagline", "description"):
            self.texts("world.json", k, data.get(k))
        bible = data.get("bible") if isinstance(data.get("bible"), dict) else {}
        for k in ("idea", "tone", "style", "heroes"):
            self.texts("world.json", f"bible.{k}", bible.get(k))
        for i, r in enumerate(bible.get("rules") or []):
            self.texts("world.json", f"bible.rules[{i}]", r)
        lacking = [k for k in ("idea", "tone", "style") if not isinstance(bible.get(k), dict)]
        if lacking:
            self.add("bible_incomplete", "world.json bible", f"no {', '.join(lacking)} yet: the bible is needed "
                                                             "before the first episode is submitted")
        if exact(w.root, "cover.png") != "ok":
            self.add("cover_missing", "cover.png", "no cover picture yet (cover.png, vertical)")

    def heroes(self, used: set):
        for slug in self.w.heroes():
            rel = f"heroes/{slug}"
            if not SLUG.match(slug):
                self.add("folder_name", rel, "a hero's folder name: latin small letters, digits and -")
                continue
            if not (self.w.hero_dir(slug) / "hero.json").is_file():
                self.add("hero_json_missing", rel, "no hero.json: `tadam new hero <slug>`")
                continue
            data = self.load(f"{rel}/hero.json", "hero")
            if isinstance(data, dict):
                self.texts(f"{rel}/hero.json", "name", data.get("name"))
                self.texts(f"{rel}/hero.json", "trait", data.get("trait"), required=False)
            self.puppet(slug, required=slug in used)

    def puppet(self, slug: str, required: bool):
        """The hero's puppet: there, cut, every part drawn, and passed its audit."""
        pdir = self.w.puppet_dir(slug)
        rel = f"heroes/{slug}/puppet"
        level = None if required else "warning"
        rig, err = read_json(pdir / "rig.json")
        if err == "missing":
            self.add("puppet_missing", rel, f"no puppet yet: `tadam hero make {slug} \"<description>\"`", level)
            return
        if not isinstance(rig, dict):
            self.add("json_invalid", f"{rel}/rig.json", err or "not an object")
            return
        missing = []
        for n, p in (rig.get("parts") or {}).items():
            if exact(pdir, f"parts/{n}.png") != "ok":
                missing.append(f"{n}.png")
            for v in (p.get("variants") or {}) if isinstance(p, dict) else {}:
                if exact(pdir, f"parts/{n}.{v}.png") != "ok":
                    missing.append(f"{n}.{v}.png")
        if missing:
            self.add("puppet_parts_missing", f"{rel}/parts", f"missing: {', '.join(missing[:8])}", level)
        rep, err = read_json(pdir / "report.json")
        if not (isinstance(rep, dict) and rep.get("passed") is True):
            why = "no report.json" if err else "the audit found problems (report.json)"
            self.add("puppet_not_passed", rel, f"{why}: make it again (`tadam hero make {slug} ...`)", level)
            return
        head = (rig.get("parts") or {}).get("head")
        if isinstance(head, dict) and rig.get("view", "front") == "front" and not isinstance(head.get("board"), dict):
            self.add("puppet_no_board", f"{rel}/rig.json", f"no parts.head.board: cut the puppet again "
                     f"(`tadam hero make {slug} ...`) so the face gets its oval", "warning" if required else "info")
        from tadam import actions
        st, data = actions.state(pdir)
        if st == "missing":
            self.add("hero_actions_missing", rel, f"no actions.json: run `tadam hero check {slug}`",
                     None if required else "info")
        elif st == "stale":
            self.add("hero_actions_stale", rel, f"the puppet changed after its action check: `tadam hero check {slug}`",
                     None if required else "info")
        elif st == "failed":
            bad = ", ".join((data or {}).get("stage1_failed") or (data or {}).get("stage1_missing") or []) or "?"
            self.add("hero_actions_failed", rel, f"fails stage-1 action(s) {bad} (actions.json): draw the hero again "
                     f"(`tadam hero make {slug} ...`); a hero is never tuned to pass", level)

    def sets(self):
        for slug in self.w.sets():
            rel = f"sets/{slug}"
            if not SLUG.match(slug):
                self.add("folder_name", rel, "a set's folder name: latin small letters, digits and -")
                continue
            self.one_set(slug)

    def one_set(self, slug: str):
        rel = f"sets/{slug}/set.json"
        sd = self.w.set_dir(slug)
        st, err = read_json(sd / "set.json")
        if err == "missing":
            self.add("set_missing", rel, f"no set.json: `tadam set make {slug}` makes it from kit.json")
            return
        if not isinstance(st, dict):
            self.add("json_invalid", rel, err or "not an object")
            return
        problems = []
        if not isinstance(st.get("background"), str):
            problems.append("'background' (the room's picture) is missing")
        fl = st.get("floor", 0.86)
        if not isinstance(fl, (int, float)) or not 0 < fl <= 1:
            problems.append("'floor' must be a share of the height (0..1)")
        files = []
        if isinstance(st.get("background"), str):
            files.append(("background", st["background"]))
        for key in ("pieces", "backdrops"):
            items = st.get(key, [])
            if not isinstance(items, list):
                problems.append(f"'{key}' must be a list")
                continue
            for i, p in enumerate(items):
                if not isinstance(p, dict) or not isinstance(p.get("image"), str):
                    problems.append(f"{key}[{i}] has no 'image'")
                    continue
                r = p.get("rect")
                if key == "pieces" and not (isinstance(r, list) and len(r) == 4 and
                                            all(isinstance(x, (int, float)) for x in r)):
                    problems.append(f"{key}[{i}].rect must be [x, y, w, h]")
                files.append((f"{key}[{i}].image", p["image"]))
                if isinstance(p.get("under"), str):
                    files.append((f"{key}[{i}].under", p["under"]))
        for path, name in files:
            if not is_safe_name(name):
                problems.append(f"{path} '{name}': a file inside the set's folder (latin, no '..', no '\\')")
                continue
            state = exact(sd, name)
            if state == "case":
                self.add("name_case", f"{rel} {path}", f"'{name}' differs from the file's name in letter case")
            elif state == "missing":
                self.add("set_file_missing", f"{rel} {path}", f"no file sets/{slug}/{name}")
        for p in problems:
            self.add("set_invalid", rel, p)

    # ------------------------------------------------------------------ an episode
    def episode(self, n: str):
        rel_dir = f"episodes/{n}"
        if not EPISODE.match(n):
            self.add("folder_name", rel_dir, "an episode's folder is its number: 1, 2, 3 ...")
            return
        if not self.w.episode_dir(n).is_dir():
            self.add("episode_missing", rel_dir, f"no episode {n}: `tadam new episode {n}`")
            return
        rel = f"{rel_dir}/script.json"
        s, err = read_json(self.w.root / rel)
        if err == "missing":
            self.add("script_missing", rel, "no script.json")
            return
        if err:
            self.add("json_invalid", rel, err)
            return
        if isinstance(s, dict) and s.get("version") == 1:
            self.add("script_v1", rel, "version 1 (server paths): the kit writes version 2")
            return
        for path, msg in schema.validate("script.v2", s):
            self.add("schema", f"{rel} {path}", msg)
        if not isinstance(s, dict):
            return
        self.refs(rel, s)
        self.names(rel, s)
        self.words(rel, s)
        self.rules(rel, s)
        self.scenes(rel, n, s)

    @staticmethod
    def _shots(s: dict) -> list[tuple[int, dict]]:
        return [(i, x) for i, x in enumerate(s.get("shots") or []) if isinstance(x, dict)]

    @staticmethod
    def _at(i: int, shot: dict) -> str:
        return f"shots[{i}]" + (f" ({shot['id']})" if isinstance(shot.get("id"), str) else "")

    def refs(self, rel: str, s: dict):
        """The rules every script keeps (the contract's checkScript), in the same words."""
        cast = s.get("cast") if isinstance(s.get("cast"), dict) else {}
        roles = s.get("roles") if isinstance(s.get("roles"), dict) else {}
        owner: dict = {}
        for hero, steps in roles.items():
            if hero not in cast:
                self.add("hero_not_in_cast", f"{rel} roles.{hero}", f"the hero {hero} is not in the cast")
            for st in steps if isinstance(steps, list) else []:
                if not isinstance(st, dict) or "key" not in st:
                    continue
                if st["key"] in owner:
                    self.add("step_key_twice", f"{rel} roles.{hero}", f"the step key {st['key']} is used twice")
                owner[st["key"]] = (hero, st)
                if st.get("kind") == "read" and not st.get("text"):
                    self.add("line_no_text", f"{rel} roles.{hero}", f"the line {st['key']} has no text")
        for hero in cast:
            if hero not in roles:
                self.add("hero_no_steps", f"{rel} cast.{hero}", f"the hero {hero} has no steps")
        ids = set()
        for i, shot in self._shots(s):
            at = f"{rel} {self._at(i, shot)}"
            if shot.get("id") in ids:
                self.add("shot_id_twice", at, f"the shot id {shot['id']} is used twice")
            ids.add(shot.get("id"))
            say = shot.get("say")
            if say:
                o = owner.get(say)
                if not o:
                    self.add("say_unknown", at, f"no step {say}")
                elif o[1].get("kind") != "read":
                    self.add("say_not_line", at, f"the step {say} is not a line")
            for hero, key in (shot.get("listen") or {}).items() if isinstance(shot.get("listen"), dict) else []:
                o = owner.get(key)
                if not o or o[0] != hero:
                    self.add("listen_unknown", at, f"no step {key} of {hero}")
            if not say and not shot.get("seconds") and not shot.get("narration"):
                self.add("shot_no_length", at, "a shot with no line needs seconds")
            seen = set()
            for j, a in enumerate(shot.get("actors") or []):
                if not isinstance(a, dict):
                    continue
                if a.get("id") not in cast:
                    self.add("actor_not_in_cast", f"{at} actors[{j}]", f"the hero {a.get('id')} is not in the cast")
                if a.get("id") in seen:
                    self.add("actor_twice", f"{at} actors[{j}]", f"the hero {a.get('id')} stands twice in the shot")
                seen.add(a.get("id"))
        film = s.get("film") if isinstance(s.get("film"), dict) else {}
        wd, ht = film.get("width"), film.get("height")
        if isinstance(wd, int) and isinstance(ht, int) and wd >= ht:
            self.add("film_not_vertical", f"{rel} film", "the film is vertical: height must be greater than width")

    def names(self, rel: str, s: dict):
        """Every name in the script exists in the world: heroes, sets, media."""
        cast = s.get("cast") if isinstance(s.get("cast"), dict) else {}
        heroes = set(self.w.heroes())
        for key, c in cast.items():
            ch = c.get("character") if isinstance(c, dict) else None
            if isinstance(ch, str) and SLUG.match(ch) and ch not in heroes:
                low = [h for h in heroes if h.lower() == ch.lower()]
                if low:
                    self.add("name_case", f"{rel} cast.{key}", f"heroes/{low[0]} differs in letter case from '{ch}'")
                else:
                    self.add("hero_missing", f"{rel} cast.{key}", f"no hero heroes/{ch}: `tadam new hero {ch}`")
        sets = set(self.w.sets())
        film = s.get("film") if isinstance(s.get("film"), dict) else {}
        wanted = [("film.set", film.get("set"))] + [(f"{self._at(i, x)}.set", x.get("set"))
                                                     for i, x in self._shots(s) if x.get("set")]
        for path, slug in wanted:
            if isinstance(slug, str) and SLUG.match(slug) and slug not in sets:
                self.add("set_missing", f"{rel} {path}", f"no set sets/{slug}: `tadam new set {slug}`")
        m = film.get("music") if isinstance(film.get("music"), dict) else {}
        if "file" in m:
            self.media(rel, "film.music.file", m["file"])
        amb = m.get("ambience") if isinstance(m.get("ambience"), dict) else {}
        if "file" in amb:
            self.media(rel, "film.music.ambience.file", amb["file"])
        for i, shot in self._shots(s):
            song = shot.get("song") if isinstance(shot.get("song"), dict) else {}
            if "file" in song:
                self.media(rel, f"{self._at(i, shot)}.song.file", song["file"])
            for j, a in enumerate(shot.get("actors") or []):
                if isinstance(a, dict) and "prop" in a:
                    self.media(rel, f"{self._at(i, shot)}.actors[{j}].prop", a["prop"])

    def words(self, rel: str, s: dict):
        """Texts in every language of the world, and what a person recording a step needs."""
        roles = s.get("roles") if isinstance(s.get("roles"), dict) else {}
        for hero, steps in roles.items():
            for k, st in enumerate(steps if isinstance(steps, list) else []):
                if not isinstance(st, dict):
                    continue
                at = f"roles.{hero}[{k}]" + (f" ({st['key']})" if "key" in st else "")
                self.texts(rel, f"{at}.text", st.get("text"))
                self.texts(rel, f"{at}.hint", st.get("hint"))
                if st.get("kind") in RECORDED:
                    if not isinstance(st.get("hint"), dict):
                        self.add("step_no_hint", f"{rel} {at}", "a recorded step needs a hint: how to play it and "
                                                                 "hold the phone")
                    if not st.get("look"):
                        self.add("step_no_look", f"{rel} {at}", "a recorded step needs look marks: where the eyes "
                                                                 "go (lens, mark_left, ...)")
                if st.get("kind") == "read" and isinstance(st.get("text"), dict):
                    for lang in self.langs:
                        t = st["text"].get(lang)
                        if not isinstance(t, str) or not t.strip():
                            continue
                        need = resolve.line_seconds(t)
                        mx = st.get("maxSeconds")
                        if isinstance(mx, (int, float)) and need > mx:
                            self.add("line_too_long", f"{rel} {at}.text.{lang}",
                                     f"about {need:g} s to say, maxSeconds is {mx:g}: shorten it or raise maxSeconds")
                        elif not isinstance(mx, (int, float)) and need > LINE_LONG:
                            self.add("line_long", f"{rel} {at}.text.{lang}",
                                     f"about {need:g} s to say: split it, or set maxSeconds")
        for i, shot in self._shots(s):
            at = self._at(i, shot)
            self.texts(rel, f"{at}.remark", shot.get("remark"))
            if isinstance(shot.get("narration"), dict):
                self.texts(rel, f"{at}.narration.text", shot["narration"].get("text"))
            if isinstance(shot.get("card"), dict):
                for k in ("title", "sub", "kicker"):
                    self.texts(rel, f"{at}.card.{k}", shot["card"].get(k))

    def rules(self, rel: str, s: dict):
        """The studio's filming rules that need the whole script."""
        steps = resolve.steps_by_key(s)
        total = 0.0
        for i, shot in self._shots(s):
            at = f"{rel} {self._at(i, shot)}"
            total += resolve.shot_seconds(shot, steps, self.langs[0])
            say = shot.get("say")
            if say in steps and shot.get("actors"):
                speaker = steps[say][0]
                if speaker not in {a.get("id") for a in shot["actors"] if isinstance(a, dict)}:
                    self.add("speaker_not_in_shot", at, f"{speaker} speaks but does not stand in the shot")
            for src, opts in (("stage", shot.get("stage")),):
                for k in (opts or {}) if isinstance(opts, dict) else {}:
                    if k not in resolve.STAGE_OPTIONS:
                        self.add("stage_option_unknown", f"{at}.{src}.{k}",
                                 f"the engine takes: {', '.join(sorted(resolve.STAGE_OPTIONS))}")
        film = s.get("film") if isinstance(s.get("film"), dict) else {}
        for k in (film.get("stage") or {}) if isinstance(film.get("stage"), dict) else {}:
            if k not in resolve.STAGE_OPTIONS:
                self.add("stage_option_unknown", f"{rel} film.stage.{k}",
                         f"the engine takes: {', '.join(sorted(resolve.STAGE_OPTIONS))}")
        if total > EPISODE_MAX_SECONDS:
            self.add("episode_too_long", f"{rel} shots", f"about {total:.0f} s: an episode is at most "
                                                         f"{EPISODE_MAX_SECONDS:.0f} s")

    def scenes(self, rel: str, n: str, s: dict):
        """Every shot as the engine scene it becomes, through the scene checks."""
        ctx = scenecheck.Context.from_engine(engine_dir())
        for i, (sid, scene) in enumerate(resolve.film_scenes(self.w, s, self.langs[0])):
            for issue in scenecheck.check_scene(scene, ctx, f"{rel} shot {sid}"):
                if issue.code not in _SOURCE:
                    self.out.append(issue)


def used_heroes(w: World, episodes: list[str]) -> set:
    out = set()
    for n in episodes:
        s, _ = read_json(w.episode_dir(n) / "script.json")
        if isinstance(s, dict) and isinstance(s.get("cast"), dict):
            out |= {c.get("character") for c in s["cast"].values() if isinstance(c, dict)}
    return out


def check_world(root: Path | str, episode: str | None = None) -> list[Issue]:
    """Every finding for the world folder and one episode (or all of them)."""
    r = _Run(Path(root))
    r.world()
    if not (r.w.root / "world.json").is_file():
        return r.out
    episodes = [episode] if episode else r.w.episodes()
    r.heroes(used_heroes(r.w, [e for e in episodes if r.w.episode_dir(e).is_dir()]))
    r.sets()
    for n in episodes:
        r.episode(str(n))
    return r.out
