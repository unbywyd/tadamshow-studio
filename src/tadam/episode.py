"""AN EPISODE AS THE PLAYER PLAYS IT: the engine scenes of its shots (tadam.resolve), how long each shot is and
where it starts (tadam.timing, in whole frames of the film as the server cuts them), the title cards drawn
(tadam.titlecard, into .tadam/cards/), the narration (the bridge, tadam.tts, cached in .tadam/tts/) or, without
it, its subtitles, the subtitles of the lines with the speakers' names, and the sound to mix (tadam.mix).

Nothing here starts the engine: tadam.render does, for `play`, `frames` and `film`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from tadam import mix, resolve, timing, tts
from tadam.world import World, WorldError, is_safe_name, read_json

SUB_HOLD = 0.35          # a subtitle stays this long after its words
CARD_FROM, CARD_BEFORE_END, CARD_FADE = 0.5, 0.3, 0.4      # the site's card over a shot (services/film.ts)


@dataclass
class Shot:
    id: str
    remark: str
    dir: Path                        # .tadam/scenes/<episode>/<shot>
    seconds: float                   # as the scene says (timing)
    frames: int                      # whole frames of the film
    start: float = 0.0               # seconds from the episode's start (frames / fps)
    speaker: str | None = None       # the cast key of who says the line
    talk: list = field(default_factory=list)       # [[a, b], ...] the phrases of the line (no recording)
    card: dict | None = None         # {image, from, to, fade}
    narration: dict | None = None    # {text, at, file | None, seconds}
    subs: list = field(default_factory=list)       # [{from, to, who, text, kind}]
    song: dict | None = None
    quiet: bool = False


@dataclass
class Episode:
    world: World
    n: str
    lang: str
    fps: int
    size: tuple[int, int]
    shots: list[Shot]
    music: dict | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def seconds(self) -> float:
        return round(sum(s.frames for s in self.shots) / self.fps, 4)

    def index(self, shot_id: str) -> int:
        for i, s in enumerate(self.shots):
            if s.id == shot_id:
                return i
        raise WorldError(f"episode {self.n} has no shot '{shot_id}': it has {', '.join(s.id for s in self.shots)}")


def frames_of(seconds: float, fps: int) -> int:
    """Whole frames of a shot (services/film.ts fps30): never fewer than one."""
    return max(1, int(round(seconds * fps)))


def card_fingerprint(title: str, sub: str, kicker: str, size: tuple[int, int]) -> str:
    """The server's cardFingerprint (services/studio/resolve.ts): sha-256 (32 hex) of the card's words and size."""
    data = json.dumps({"title": title, "sub": sub, "kicker": kicker, "size": f"{size[0]}x{size[1]}"},
                      ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:32]


def _num(x, default):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else default


def _media(world: World, name) -> str | None:
    if not is_safe_name(name):
        return None
    f = world.media(name)
    return f.as_posix() if f.is_file() else None


def _sound(world: World, d) -> dict | None:
    if not isinstance(d, dict):
        return None
    f = _media(world, d.get("file"))
    return {**d, "file": f} if f else None


def hero_name(world: World, script: dict, key: str, lang: str) -> str:
    c = (script.get("cast") or {}).get(key)
    slug = c.get("character") if isinstance(c, dict) else None
    if isinstance(slug, str):
        nm = world.hero_json(slug).get("name")
        t = resolve.text_of(nm, lang) if isinstance(nm, dict) else (nm if isinstance(nm, str) else "")
        if t:
            return t
    return key


def build(world: World, n: str, lang: str | None = None, link: tts.Link | None = None, voice: bool = True,
          client: tts.Client | None = None, log=print) -> Episode:
    n = str(n)
    script, err = read_json(world.episode_dir(n) / "script.json")
    if not isinstance(script, dict):
        raise WorldError(f"episodes/{n}/script.json: {err or 'not a script'} (tadam new episode {n})")
    if script.get("version") != 2:
        raise WorldError(f"episodes/{n}/script.json is not a version-2 script: the player plays version 2")
    lang = lang or world.langs()[0]
    film = script.get("film") or {}
    fps = int(film.get("fps") or 30)
    size = (int(film.get("width") or 720), int(film.get("height") or 1280))
    steps = resolve.steps_by_key(script)
    shots_in = [s for s in script.get("shots") or [] if isinstance(s, dict)]
    narrator = {"voice": "eduard", "fx": "none", **(script.get("narrator") or {})}
    notes: list[str] = []

    # the narration: from the cache or the bridge; without it, subtitles
    narr_files: dict[str, dict] = {}
    why_not: set[str] = set()
    for i, s in enumerate(shots_in):
        narr = s.get("narration")
        if not isinstance(narr, dict):
            continue
        sid = str(s.get("id", i + 1))
        voiced = resolve.text_of(narr.get("text"), "ru")         # (the film's voice speaks the Russian text)
        f, why = (None, "turned off") if not voice else tts.narration(
            voiced, str(narrator["voice"]), str(narrator["fx"]), world.work_dir() / "tts", link, client)
        if f is not None:
            d = mix.duration(f)
            if d:
                narr_files[sid] = {"file": f.as_posix(), "seconds": round(d, 3)}
                continue
            why = f"{f.name} cannot be read as sound"
        why_not.add(why)
    if why_not:
        if why_not == {"no studio key"}:
            notes.append(f"narration as subtitles: no studio key ({tts.KEY_ENV}; `tadam login` sets it up)")
        elif why_not != {"turned off"}:
            notes.append("narration as subtitles: " + "; ".join(sorted(why_not)))

    dirs = resolve.write_scenes(world, n, script, lang, {k: v["seconds"] for k, v in narr_files.items()})
    out: list[Shot] = []
    start_frames = 0
    for i, (s, d) in enumerate(zip(shots_in, dirs)):
        sid = d.name
        scene, _ = read_json(d / "scene.json")
        seconds = float(scene.get("seconds", timing.DEFAULT_SECONDS)) if isinstance(scene, dict) else timing.DEFAULT_SECONDS
        fr = frames_of(seconds, fps)
        sh = Shot(id=sid, remark=resolve.text_of(s.get("remark"), lang), dir=d, seconds=seconds, frames=fr,
                  start=round(start_frames / fps, 4), song=_sound(world, s.get("song")), quiet=bool(s.get("quiet")))
        start_frames += fr
        speaker, talk = resolve.line_phrases(s, steps, lang)
        if speaker:
            sh.speaker, sh.talk = speaker, talk
            text = resolve.text_of(steps[s["say"]][1].get("text"), lang)
            if text and talk:
                sh.subs.append({"from": talk[0][0], "to": round(min(talk[-1][1] + SUB_HOLD, seconds - 0.05), 2),
                                "who": hero_name(world, script, speaker, lang), "text": text, "kind": "line"})
        narr = s.get("narration")
        if isinstance(narr, dict):
            at = _num(narr.get("at"), timing.NARRATION_AT)
            text = resolve.text_of(narr.get("text"), lang)
            nf = narr_files.get(sid)
            sh.narration = {"text": text, "at": at, "db": _num(narr.get("db"), 0.0),
                            "file": nf["file"] if nf else None,
                            "seconds": nf["seconds"] if nf else round(timing.speech_seconds(text), 2)}
            if not nf and text:
                sh.subs.append({"from": at, "to": round(min(at + sh.narration["seconds"] + SUB_HOLD, seconds - 0.05), 2),
                                "who": "", "text": text, "kind": "narration"})
        c = s.get("card")
        if isinstance(c, dict) and resolve.text_of(c.get("title"), lang):
            sh.card = _card(world, c, lang, size, seconds)
        out.append(sh)
    music = None
    m = film.get("music")
    if isinstance(m, dict):
        music = _sound(world, m)
        if music is None and m.get("file"):
            notes.append(f"music: media/{m.get('file')} is not in the world: the draft has no tune")
        if music is not None and isinstance(m.get("ambience"), dict):
            music["ambience"] = _sound(world, m["ambience"])
    return Episode(world, n, lang, fps, size, out, music, notes)


def _card(world: World, c: dict, lang: str, size: tuple[int, int], seconds: float) -> dict:
    from tadam import titlecard
    title = resolve.text_of(c.get("title"), lang)
    sub = resolve.text_of(c.get("sub"), lang)
    kicker = resolve.text_of(c.get("kicker"), lang)
    top = _num(c.get("top"), None)
    name = card_fingerprint(title, sub, kicker, size) + ("" if top is None else f"-top{round(top * 100)}")
    png = world.work_dir() / "cards" / f"{name}.png"
    if not png.is_file():
        titlecard.card(png, title, sub, kicker, size=size, **({"top": top} if top is not None else {}))
    return {"image": png.as_posix(), "from": _num(c.get("from"), CARD_FROM),
            "to": _num(c.get("to"), round(seconds - CARD_BEFORE_END, 2)), "fade": CARD_FADE}


def sounds(ep: Episode) -> list[mix.ShotSound]:
    out = []
    for s in ep.shots:
        nar, talk = None, list(s.talk)
        if s.narration and s.narration.get("file"):
            nar = {"file": s.narration["file"], "at": s.narration["at"], "db": s.narration.get("db", 0)}
        elif s.narration and s.narration.get("text"):
            # (a narration that is only a subtitle here is talk all the same: the tune keeps out of it, as it will)
            talk.append([s.narration["at"], s.narration["at"] + s.narration["seconds"]])
        out.append(mix.ShotSound(start=s.start, seconds=s.frames / ep.fps, talk=talk, quiet=s.quiet,
                                 song=s.song, narrator=nar))
    return out
