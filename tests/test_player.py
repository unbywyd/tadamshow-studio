"""The local player, the frames and the draft film (stage 1V): the pure parts (how long a shot is, where its words
are, the contact sheet's grid, the playlist, the engine's command line, the sound's mix) and, with Godot and
ffmpeg installed, the real thing on the fixture world: frames, a sheet, a short film, two runs at once."""
from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

import pytest
from PIL import Image

from tadam import cli, doctor, engine, episode, mix, render, resolve, timing
from tadam.engine import EngineError
from tadam.paths import engine_dir
from tadam.world import World, read_json, write_json

needs_godot = pytest.mark.skipif(doctor.find_godot(doctor.System())[0] is None, reason="Godot 4.7 is not installed")
needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="no ffmpeg")


# ------------------------------------------------------------------------------------------------ timing

def test_the_server_defaults_are_the_kit_defaults():
    # services/film-logic.ts linePhrases(lead = 0.4, trail = 0.25); services/film.ts timeline tail 0.4, seconds 4
    assert (timing.LEAD, timing.TRAIL, timing.TAIL, timing.DEFAULT_SECONDS) == (0.4, 0.25, 0.4, 4.0)


def test_a_line_shot_is_lead_speech_trail_tail():
    text = "раз два три четыре пять шесть"                         # 6 words
    assert timing.speech_seconds(text) == pytest.approx(6 / 2.3)
    assert timing.piece_seconds(text) == round(0.4 + 6 / 2.3 + 0.25, 2)
    assert timing.line_shot_seconds(text) == round(round(0.4 + 6 / 2.3 + 0.25, 2) + 0.4, 2)
    # the shot's own lead / trail / tail win; maxSeconds caps the piece (the recording cannot be longer)
    assert timing.line_shot_seconds(text, {"lead": 1, "tail": 0}) == round(1 + 6 / 2.3 + 0.25, 2)
    assert timing.line_shot_seconds(text, max_seconds=2) == 2.4
    # one short word still takes a moment; punctuation is not a word
    assert timing.speech_seconds("Ура!") == timing.SHORTEST_SPEECH
    assert timing.words("Да — нет , 5") == 3


def test_narration_and_plain_shots():
    assert timing.narration_shot_seconds(None, 2.0) == 0.5 + 2.0 + 0.7
    assert timing.narration_shot_seconds(1, 2.0, {"tail": 0.1}) == 3.1
    steps = {"a-1": ("a", {"text": {"ru": "раз два"}, "maxSeconds": 9})}
    assert resolve.shot_seconds({"seconds": 2.5}, steps) == 2.5
    assert resolve.shot_seconds({}, steps) == 4.0


def test_phrases_of_a_line():
    one = timing.line_phrases("Где моя луна?")
    assert len(one) == 1 and one[0][0] == timing.LEAD
    assert one[0][1] == pytest.approx(timing.LEAD + timing.speech_seconds("Где моя луна?"), abs=0.01)
    # three phrases by its three sentences, longer sentences longer, a breath between them, all inside the piece
    text = "Она была круглая. И жёлтая. Как сыр из лавки."
    ph = timing.line_phrases(text, 3)
    assert len(ph) == 3
    assert all(a < b for a, b in ph) and all(ph[i][1] < ph[i + 1][0] for i in range(2))
    assert ph[2][1] - ph[2][0] > ph[1][1] - ph[1][0]
    assert ph[-1][1] <= timing.piece_seconds(text) - timing.TRAIL + 0.01
    # more phrases than sentences: cut evenly; nonsense counts: one phrase
    assert len(timing.line_phrases("раз два три", 2)) == 2
    assert len(timing.line_phrases("раз", "x")) == 1


def test_the_speaker_gets_its_phrases_in_the_scene(world):
    w = World(world)
    s, _ = read_json(w.episode_dir("1") / "script.json")
    sc = resolve.shot_scene(w, s, s["shots"][0])
    cow = next(a for a in sc["actors"] if a["id"] == "cow")
    det = next(a for a in sc["actors"] if a["id"] == "det")
    assert cow["speech"] == timing.line_phrases("Где моя луна?") and "speech" not in det
    assert sc["seconds"] == timing.line_shot_seconds("Где моя луна?", s["shots"][0], 5)
    # a script cannot hand the engine speech of its own
    s["shots"][2]["actors"][0]["speech"] = [[0, 9]]
    assert "speech" not in resolve.shot_scene(w, s, s["shots"][2])["actors"][0]


# ------------------------------------------------------------------------------------------------ the episode

def test_the_episode_as_the_player_plays_it(world):
    w = World(world)
    ep = episode.build(w, "1", log=lambda *_: None)
    assert [s.id for s in ep.shots] == ["sh1", "sh2", "sh3"]
    assert ep.fps == 30 and ep.size == (720, 1280)
    # whole frames, starts from the frames before
    for a, b in zip(ep.shots, ep.shots[1:]):
        assert b.start == pytest.approx(a.start + a.frames / 30, abs=1e-4)
    assert ep.shots[0].frames == round(ep.shots[0].seconds * 30)
    # the line as a subtitle with the hero's name (hero.json), the narration as an italic subtitle (no key)
    sub = ep.shots[0].subs[0]
    assert sub["who"] == "Корова" and sub["text"] == "Где моя луна?" and sub["kind"] == "line"
    assert sub["from"] == timing.LEAD and sub["to"] <= ep.shots[0].seconds
    narr = ep.shots[2].subs[0]
    assert narr["kind"] == "narration" and narr["text"] == "А луна была рядом." and narr["who"] == ""
    assert any("no studio key" in n for n in ep.notes)
    # every scene is in .tadam, nothing in the engine folder
    assert all((s.dir / "scene.json").is_file() and w.work_dir() in s.dir.parents for s in ep.shots)


def test_a_title_card_is_drawn_once_into_tadam(world):
    w = World(world)
    s, _ = read_json(w.episode_dir("1") / "script.json")
    s["shots"][2]["card"] = {"title": {"ru": "Корова / и луна"}, "sub": {"ru": "Серия 1"}, "from": 0.2}
    write_json(w.episode_dir("1") / "script.json", s)
    ep = episode.build(w, "1")
    c = ep.shots[2].card
    png = Path(c["image"])
    assert png.is_file() and png.parent == w.work_dir() / "cards"
    assert c["from"] == 0.2 and c["to"] == round(ep.shots[2].seconds - 0.3, 2) and c["fade"] == 0.4
    with Image.open(png) as im:
        assert im.size == (720, 1280) and im.mode == "RGBA"
    t = png.stat().st_mtime_ns
    episode.build(w, "1")
    assert png.stat().st_mtime_ns == t            # (the same words: the same file, not drawn again)


def test_card_fingerprint_is_the_servers():
    # sha-256 of JSON.stringify({title, sub, kicker, size}), as Node computes it (services/studio/resolve.ts)
    assert episode.card_fingerprint("Корова", "", "", (720, 1280)) == "f31d1a3c2817cad61f725a7839129c27"


def test_a_shot_that_is_not_there(world):
    from tadam.world import WorldError
    ep = episode.build(World(world), "1")
    with pytest.raises(WorldError, match="no shot 'sh9'"):
        ep.index("sh9")


# ------------------------------------------------------------------------------------------------ the sheet

def test_sheet_layout():
    size, at = render.sheet_layout(10, (240, 427), label=70, pad=16, gap=12)
    assert len(at) == 10 and at[0] == (16, 16)
    assert at[5] == (16, 16 + 427 + 70 + 12)                      # 5 a row
    assert size == (16 * 2 + 5 * 252 - 12, 16 * 2 + 2 * (427 + 70 + 12) - 12)
    size3, at3 = render.sheet_layout(3, (240, 427))
    assert len({y for _, y in at3}) == 1 and size3[0] < size[0]    # fewer shots: one row
    assert render.sheet_layout(7, (100, 100), cols=2)[1][6] == (16, 16 + 3 * (100 + 64 + 12))
    assert render.sheet_layout(0, (100, 100))[1] == []


def test_make_sheet_labels_every_shot(world, tmp_path):
    ep = episode.build(World(world), "1")
    pngs = []
    for i, c in enumerate([(200, 60, 60), (60, 200, 60), (60, 60, 200)]):
        Image.new("RGB", (720, 1280), c).save(tmp_path / f"{i}.png")
        pngs.append(tmp_path / f"{i}.png")
    out = render.make_sheet(ep, pngs, tmp_path / "sheet.png", thumb_w=120)
    with Image.open(out) as im:
        size, at = render.sheet_layout(3, (120, 213), label=70)
        assert im.size == size
        assert im.getpixel((at[1][0] + 60, at[1][1] + 100)) == (60, 200, 60)        # the frame
        lab = im.crop((at[0][0], at[0][1] + 213, at[0][0] + 120, at[0][1] + 213 + 70))
        assert lab.convert("L").getextrema()[0] < 120                                # the label's letters


# ------------------------------------------------------------------------------------------------ the command

def test_the_engine_command_never_writes_into_the_engine(tmp_path):
    pl = tmp_path / "playlist.json"
    snap = render.command("godot", "snap", pl, (720, 1280), platform="win32")
    film = render.command("godot", "film", pl, (720, 1280), fps=30, movie=tmp_path / "f.avi", board_preview=True,
                          platform="win32")
    play = render.command("godot", "play", pl, (720, 1280), window=(450, 800), platform="win32")
    for c in (snap, film, play):
        assert c[c.index("--path") + 1] == str(engine_dir())
        assert "res://player.tscn" in c and f"--playlist={pl.as_posix()}" in c
        assert not any("override.cfg" in x for x in c)
        assert any(x.startswith("--font=") and x.endswith("PT_Serif-Web-Bold.ttf") for x in c)
    assert snap[snap.index("--resolution") + 1] == "720x1280" and snap[snap.index("--fixed-fps") + 1] == "60"
    assert snap[snap.index("--position") + 1] == render.OFF_SCREEN
    assert film[film.index("--write-movie") + 1] == str(tmp_path / "f.avi") and "--board-preview" in film
    assert film[film.index("--fixed-fps") + 1] == "30"
    assert play[play.index("--resolution") + 1] == "450x800" and "--fixed-fps" not in play


def test_no_screen_on_linux():
    linux = dict(platform="linux")
    assert render.display_prefix("snap", {"DISPLAY": ":0"}, **linux) == []
    assert render.display_prefix("snap", {"WAYLAND_DISPLAY": "w"}, **linux) == []
    assert render.display_prefix("snap", {}, platform="win32") == []
    assert render.display_prefix("snap", {}, platform="darwin") == []
    p = render.display_prefix("film", {}, which=lambda n: "/usr/bin/xvfb-run", size=(720, 1280), **linux)
    assert p[0] == "/usr/bin/xvfb-run" and "-a" in p and "-screen 0 784x1344x24" in p
    with pytest.raises(EngineError, match="xvfb"):
        render.display_prefix("snap", {}, which=lambda n: None, **linux)
    with pytest.raises(EngineError, match="needs a screen"):
        render.display_prefix("play", {}, which=lambda n: "/usr/bin/xvfb-run", **linux)
    # under xvfb the window is not pushed off a screen that is only a buffer
    c = render.command("godot", "snap", Path("p.json"), (720, 1280), prefix=p, platform="linux")
    assert c[0] == "/usr/bin/xvfb-run" and "--position" not in c


def test_the_playlist(world):
    ep = episode.build(World(world), "1")
    pl = render.playlist(ep, "play", start=1, audio=Path("/x/sound.wav"))
    assert pl["start"] == 1 and pl["audio_from"] == ep.shots[1].start and pl["audio"] == "/x/sound.wav"
    assert [s["frames"] for s in pl["shots"]] == [s.frames for s in ep.shots]
    assert pl["shots"][0]["subs"][0]["who"] == "Корова"
    assert Path(pl["fonts"]["italic"]).is_file() and json.dumps(pl, ensure_ascii=False)
    assert render.snap_frame(1.5) == 89 and render.snap_frame(0) == 0


# ------------------------------------------------------------------------------------------------ the sound

def test_the_tune_keeps_out_of_the_talking():
    shots = [mix.ShotSound(0, 3.0), mix.ShotSound(3.0, 3.0, talk=[[0.4, 2.0]]),
             mix.ShotSound(6.0, 4.0, narrator={"file": "n.mp3", "at": 0.5})]
    g = mix.graph(shots, {"file": "tune.mp3", "db": -12}, 10.0, {"tune.mp3": 60.0, "n.mp3": 2.0})
    inputs, flt = g
    assert inputs.count("-i") == 1 + 3          # the narrator, the tune in three pauses
    # pauses: 0 .. 3.1 (3.4 - 0.3), 5.25 .. 6.2 (6.5 - 0.3), 8.75 .. 10
    assert "adelay=0|0[m0]" in flt and "adelay=5250|5250[m1]" in flt and "adelay=8750|8750[m2]" in flt
    assert "adelay=6500|6500[s0]" in flt                                     # the narrator at 6 + 0.5
    assert flt.endswith("amix=inputs=5:normalize=0:duration=first,atrim=0:10.0000[a]")
    assert mix.graph([mix.ShotSound(0, 3.0)], None, 3.0, {}) is None         # nothing to hear
    # a tune the computer cannot read is simply not there
    assert mix.graph(shots, {"file": "broken.mp3"}, 10.0, {"n.mp3": 2.0})[0].count("-i") == 1


@needs_ffmpeg
def test_mix_renders_a_wav(tmp_path):
    import subprocess
    tune = tmp_path / "tune.wav"
    subprocess.run([mix.ffmpeg(), "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=5", str(tune)],
                   check=True)
    (tmp_path / "broken.mp3").write_bytes(b"ID3 not a sound")
    notes = []
    out = mix.render([mix.ShotSound(0, 2.0, talk=[[0.4, 1.2]]), mix.ShotSound(2.0, 1.5)],
                     {"file": tune.as_posix(), "ambience": {"file": (tmp_path / "broken.mp3").as_posix()}}, 3.5,
                     tmp_path / "out.wav", log=notes.append)
    assert out.is_file() and mix.duration(out) == pytest.approx(3.5, abs=0.05)
    assert any("broken.mp3" in n for n in notes)


# ------------------------------------------------------------------------------------------------ the engine

@needs_godot
def test_frames_and_sheet_from_the_engine(world, capsys):
    w = World(world)
    assert cli.main(["--world", str(world), "frames", "1", "--sheet", "--json"]) == 0
    res = json.loads(capsys.readouterr().out.split("\n", 1)[1])
    sheet = Path(res["sheet"])
    with Image.open(sheet) as im:
        assert im.size == render.sheet_layout(3, (240, 427), label=70)[0]
    assert [s["shot"] for s in res["shots"]] == ["sh1", "sh2", "sh3"]
    # one frame, twice: the same picture (made offline, frame by frame)
    a = render.frames_dir(episode.build(w, "1")) / "a.png"
    b = a.with_name("b.png")
    assert cli.main(["--world", str(world), "frames", "1", "--shot", "sh2", "--at", "0.8", "--out", str(a)]) == 0
    assert cli.main(["--world", str(world), "frames", "1", "--shot", "sh2", "--at", "0.8", "--out", str(b)]) == 0
    with Image.open(a) as x, Image.open(b) as y:
        assert x.size == (720, 1280) and x.tobytes() == y.tobytes()
    assert not (engine_dir() / "override.cfg").exists()
    assert cli.main(["--world", str(world), "frames", "1", "--shot", "sh2", "--at", "99"]) == 2


@needs_godot
def test_two_runs_at_once_do_not_collide(world, tmp_path, mannequin_puppet):
    from conftest import make_world
    other = make_world(tmp_path / "second", mannequin_puppet, "второй мир")
    before = sorted(p.name for p in engine_dir().iterdir())
    outs, errors = {}, []

    def run(root, name):
        try:
            ep = episode.build(World(root), "1")
            outs[name] = render.snaps(ep, [(0, 1.0, Path(root) / f"{name}.png")])[0]
        except Exception as e:          # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=run, args=(world, "a")), threading.Thread(target=run, args=(other, "b"))]
    for t in ts:
        t.start()
    for t in ts:
        t.join(300)
    assert not errors, errors
    assert outs["a"].is_file() and outs["b"].is_file()
    assert sorted(p.name for p in engine_dir().iterdir()) == before


@needs_godot
def test_an_unrecorded_line_must_be_seen(world):
    """The engine's own check counts a line with no recording ("speech") as talking: off the picture is a problem."""
    w = World(world)
    s, _ = read_json(w.episode_dir("1") / "script.json")
    s["shots"] = [s["shots"][1]]
    s["shots"][0]["actors"][0]["x"] = 1.45          # the detective talks from beyond the right edge
    s["shots"][0]["camera"] = [{"at": 0, "camera": "wide"}]
    d = resolve.write_scenes(w, "1", s)[0]
    spec, _ = read_json(d / "scene.json")
    res = engine.run_check(d, float(spec["seconds"]))
    assert res is not None and any(k.startswith("offscreen|det") for k in res["problems"]), res


@needs_godot
@needs_ffmpeg
def test_a_draft_film(world, capsys):
    w = World(world)
    s, _ = read_json(w.episode_dir("1") / "script.json")
    s["shots"] = s["shots"][:2]
    write_json(w.episode_dir("1") / "script.json", s)
    out = Path(world) / "draft.mp4"
    assert cli.main(["--world", str(world), "film", "1", "--out", str(out)]) == 0
    ep = episode.build(w, "1")
    import subprocess
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v",
                            "-show_entries", "stream=nb_read_frames,width,height", "-of", "json", str(out)],
                           capture_output=True, text=True).stdout
    v = json.loads(probe)["streams"][0]
    assert (v["width"], v["height"]) == (720, 1280)
    assert int(v["nb_read_frames"]) == sum(x.frames for x in ep.shots)
