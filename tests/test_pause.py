"""The window that can be stopped (mechanics-tz 6a, stage П): the playlist's play-mode keys, where every shot's own
script lines begin, the frames round a moment, `tadam play where`, the world watched while the window is open
and, with Godot installed, the window itself driven by PLAYER_SEQ (keys pressed by the player at given ticks)."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image

from tadam import cli, doctor, engine, episode, render, where
from tadam.world import World, read_json, write_json

needs_godot = pytest.mark.skipif(doctor.find_godot(doctor.System())[0] is None, reason="Godot 4.7 is not installed")


def _script(world: Path) -> dict:
    return json.loads((world / "episodes" / "1" / "script.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------ the playlist

def test_the_window_gets_what_it_needs_to_say_where_it_is(world):
    w = World(world)
    ep = episode.build(w, "1")
    pl = render.playlist(ep, "play", start=1, start_at=0.5, paused=True, rev_file=Path("/x/rev.txt"), rev=3)
    assert pl["names"] == {"cow": "Корова", "det": "Сыщик"} and pl["lang"] == "ru" and pl["episode"] == "1"
    assert pl["start_step"] == 30 and pl["start_paused"] is True and pl["rev"] == 3 and pl["rev_file"] == "/x/rev.txt"
    assert pl["state_dir"] == render.state_dir(w).as_posix() and pl["state_dir"].endswith(".tadam/player")
    assert len(pl["script_sha"]) == 64 and Path(pl["fonts"]["mono"]).is_file()
    assert [s["start"] for s in pl["shots"]] == [s.start for s in ep.shots]
    assert [s["remark"] for s in pl["shots"]] == ["Корова спрашивает", "Сыщик отвечает", "Двор"]
    # sh2's hero holds a cup: the kit puts its own "show" line first, so the script's camera[0] is the scene's line 1
    assert [s["lines_from"] for s in pl["shots"]] == [0, 1, 0]
    scene, _ = read_json(ep.shots[1].dir / "scene.json")
    assert scene["script"][1] == _script(world)["shots"][1]["camera"][0]
    # frames and films are as they were: none of this
    assert "names" not in render.playlist(ep, "snap") and "state_dir" not in render.playlist(ep, "film")


def test_frames_round_a_moment():
    # the moment itself is one of them, a little more after it than before; whole steps apart; inside the shot
    assert render.around_times(0.8, 3.22) == [0.4, 0.6, 0.8, 1.0, 1.2, 1.4]
    assert render.around_times(0.0, 3.22) == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    assert render.around_times(3.2, 3.22) == [2.2, 2.4, 2.6, 2.8, 3.0, 3.2]
    assert render.around_times(2, 4, 5, 2) == [1.0, 1.5, 2.0, 2.5, 3.0]
    assert render.around_times(1.0, 0.5) == [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]          # a shot shorter than the span
    assert render.around_times(2, 4, 1) == [2.0]


# ------------------------------------------------------------------------------------------------ play where

def _state(world: Path, **over) -> dict:
    moment = {"shot": "sh2", "index": 1, "shots": 3, "remark": "Сыщик отвечает", "seconds": 2.4, "at": 1.2,
              "step": 72, "frame": 36, "from_start": 4.1, "png": "/w/.tadam/player/pause.png",
              "speaking": {"who": "Сыщик", "text": "Сейчас найдём.", "kind": "line"},
              "heroes": [{"key": "det", "name": "Сыщик", "view": "front", "going": False, "turning": False,
                          "off_stage": False, "actions": [{"id": "shrug", "phase": 2, "phases": 3, "t": 0.1}]},
                         {"key": "cow", "name": "Корова", "view": "front", "going": False, "turning": False,
                          "off_stage": False, "actions": [], "holds": "think"}],
              "lines": [{"n": 0, "line": {"at": 0, "camera": "close", "on": "det"}, "ran": 0.02, "status": "done"},
                        {"n": 1, "line": {"at": 0.5, "who": "det", "do": "shrug"}, "ran": 0.5, "status": "at_work"},
                        {"n": 2, "line": {"at": 2.0, "who": "det", "do": "nod"}, "due": 2.0, "status": "next"}]}
    st = {"running": True, "paused": True, "speed": 1.0, "loop": False, "unix": time.time(), "episode": "1",
          "rev": "0", "script_sha": "", "now": {k: moment[k] for k in ("shot", "at")}, "pause": moment,
          "marks": [{**moment, "n": 1, "png": "/w/.tadam/player/mark-1.png"}]}
    st.update(over)
    d = render.state_dir(World(world))
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / "state.json", st)
    return st


def test_where_tells_the_shot_the_picture_the_heroes_and_the_lines(world, capsys):
    import hashlib
    sha = hashlib.sha256((world / "episodes" / "1" / "script.json").read_bytes()).hexdigest()
    _state(world, script_sha=sha)
    assert cli.main(["--world", str(world), "play", "where"]) == 0
    out = capsys.readouterr().out
    assert "the window is open, paused · episode 1" in out
    assert 'shot sh2 (2 of 3) "Сыщик отвечает" · 1.20 of 2.40 s · frame 36' in out
    assert "the picture: /w/.tadam/player/pause.png" in out
    assert "heard: Сыщик: Сейчас найдём." in out
    assert "Сыщик (det, front): shrug (phase 2/3" in out and "Корова (cow, front): holds the last pose of think" in out
    assert "episodes/1/script.json → shots[1].camera[n]" in out
    lines = out.splitlines()
    work = next(i for i, l in enumerate(lines) if '"do": "shrug"' in l)
    nxt = next(i for i, l in enumerate(lines) if '"do": "nod"' in l)
    assert "at_work" in lines[work] and work < nxt                       # what is at work comes first
    assert "tadam frames 1 --shot sh2 --at 1.2" in out and "--around 1.2 --frames 6" in out
    assert "marks (1):" in out and "at work: [1]" in out
    assert "changed after this pause" not in out
    # JSON: the same, and where the lines are
    assert cli.main(["--world", str(world), "play", "where", "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["open"] and rep["script"]["shot_index"] == 1 and rep["script"]["path"] == "shots[1].camera"
    assert rep["script_changed"] is False


def test_where_when_the_window_is_gone_or_the_script_changed(world, capsys):
    _state(world, unix=time.time() - 60, script_sha="0" * 64)
    assert cli.main(["--world", str(world), "play", "where"]) == 0
    out = capsys.readouterr().out
    assert "the window is closed (this is where it was)" in out and "changed after this pause" in out
    # playing on since the pause: told so
    _state(world, paused=False, now={"shot": "sh3", "at": 0.4})
    cli.main(["--world", str(world), "play", "where"])
    assert "the last pause (playing on since; now shot sh3 at 0.4 s)" in capsys.readouterr().out
    # the viewer's last pick is passed on
    write_json(render.state_dir(World(world)) / "library.json", {"action": "wave", "title": "помахать",
                                                                 "hero": "cow", "at": "12:00"})
    cli.main(["--world", str(world), "play", "where"])
    assert "picked last in the action library: wave (помахать)" in capsys.readouterr().out
    # nothing at all
    render.clear_state(World(world))
    assert cli.main(["--world", str(world), "play", "where"]) == 1
    assert "no window has stood anywhere yet" in capsys.readouterr().out
    assert where.is_open({"running": True, "unix": 100.0}, now=105.0)
    assert not where.is_open({"running": False, "unix": 100.0}, now=101.0)


def test_a_new_window_starts_clean(world):
    w = World(world)
    d = render.state_dir(w)
    d.mkdir(parents=True)
    for n in ("state.json", "pause.png", "mark-1.png", "mark-12.png", "library.json", "keep.txt"):
        (d / n).write_text("x", encoding="utf-8")
    render.clear_state(w)
    assert sorted(p.name for p in d.iterdir()) == ["keep.txt"]


# ------------------------------------------------------------------------------------------------ the world watched

def test_the_window_is_given_the_episode_anew_when_the_world_changes(world, tmp_path):
    w = World(world)
    ep = episode.build(w, "1")
    run = render.Run(tmp_path / "run")
    run.dir.mkdir()
    said = []
    watch = render.Watch(ep, run, lambda: episode.build(w, "1"), log=said.append, every=0.05)
    watch.write(ep, None)
    assert (run.dir / "rev.txt").read_text() == "0"
    assert watch.check() is False                                         # nothing changed
    s = _script(world)
    s["shots"][1]["camera"].append({"at": 0.5, "who": "det", "do": "think"})
    write_json(world / "episodes" / "1" / "script.json", s)
    assert watch.check() is True
    assert (run.dir / "rev.txt").read_text() == "1" and "edit 1" in said[-1]
    pl, _ = read_json(run.dir / "playlist.json")
    assert pl["rev"] == 1 and pl["script_sha"] == watch.ep.script_sha != ep.script_sha
    scene, _ = read_json(Path(pl["shots"][1]["scene"]) / "scene.json")
    assert scene["script"][-1]["do"] == "think"
    # a script half-written: told, the window keeps the last good one
    (world / "episodes" / "1" / "script.json").write_text("{ not json", encoding="utf-8")
    assert watch.check() is False
    assert "cannot be played yet" in said[-1] and (run.dir / "rev.txt").read_text() == "1"
    # .tadam/ is not the world: the window's own pictures do not count as a change
    (world / ".tadam" / "player").mkdir(parents=True, exist_ok=True)
    (world / ".tadam" / "player" / "pause.png").write_bytes(b"x")
    stamp = render.world_stamp(w)
    assert all(not p.startswith(".tadam") for p, _, _ in stamp)


def test_play_says_no_to_a_moment_past_the_shot(world, capsys):
    assert cli.main(["--world", str(world), "play", "1", "--shot", "sh3", "--at", "9", "--no-voice"]) == 2
    assert "shot sh3 lasts 2 s" in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------ the engine

@needs_godot
def test_the_window_stops_steps_back_marks_and_plays_on(world, tmp_path):
    """The real window, driven by its own key list (one step a tick at 1x, so every place is exact): paused at sh2
    1.0 s (step 60); two frames on (64); a second back (4); played on from tick 130, a mark at tick 160 (34), paused
    at tick 170 (44): "think" (from 0.3 s, 0.6 s long) is at work then."""
    w = World(world)
    s = _script(world)
    s["shots"][1]["camera"].append({"at": 0.3, "who": "det", "do": "think"})
    write_json(world / "episodes" / "1" / "script.json", s)
    ep = episode.build(w, "1", voice=False)
    run = render.Run(tmp_path / "run")
    run.dir.mkdir()
    render.clear_state(w)
    f = render.Watch(ep, run, lambda: ep).write(ep, None, start=1, start_at=1.0, paused=True)
    hud = (tmp_path / "hud.png").as_posix()
    seq = f"30:right,40:right,60:shift+left,100:shot={hud},130:space,160:m,170:space,230:quit"
    cmd = render.command(engine.godot(), "play", f, ep.size, window=(450, 800))
    cmd[cmd.index("--position") + 1] = render.OFF_SCREEN
    engine.ensure_imported()
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                       env={**os.environ, "PLAYER_SEQ": seq})
    out = p.stdout + p.stderr
    assert "PLAYER done" in out and "SCRIPT ERROR" not in out, out[-2000:]
    assert "PLAYER seq shift+left at sh2 4" in out
    st, _ = read_json(render.state_dir(w) / "state.json")
    assert st["running"] is False and st["paused"] is True and st["episode"] == "1"
    assert st["script_sha"] == ep.script_sha
    mk, = st["marks"]
    assert (mk["shot"], mk["step"], mk["n"]) == ("sh2", 34, 1) and Path(mk["png"]).is_file()
    m = st["pause"]
    assert (m["shot"], m["step"], m["at"], m["frame"]) == ("sh2", 44, 0.73, 22)
    assert m["from_start"] == pytest.approx(ep.shots[1].start + 0.73, abs=0.01)
    with Image.open(m["png"]) as im:
        assert im.size[0] > 100                       # the picture of the window, without the notes
    det = next(h for h in m["heroes"] if h["key"] == "det")
    assert det["name"] == "Сыщик" and [a["id"] for a in det["actions"]] == ["think"]
    lines = {r["n"]: r for r in m["lines"]}
    assert lines[0]["status"] == "done" and lines[1]["status"] == "at_work" and lines[1]["line"]["do"] == "think"
    assert m["speaking"]["who"] == "Сыщик"
    assert Path(hud).is_file()
    # what `where` makes of it
    rep = where.report(w, st)
    assert rep["script"]["path"] == "shots[1].camera" and not rep["script_changed"]
    assert "[1] at_work" in where.text(rep)


@needs_godot
def test_frames_round_a_moment_from_the_engine(world, capsys):
    assert cli.main(["--world", str(world), "frames", "1", "--shot", "sh2", "--around", "0.8", "--frames", "3",
                     "--span", "0.4", "--json"]) == 0
    res = json.loads(capsys.readouterr().out.split("\n", 1)[1])
    assert [f["at"] for f in res["frames"]] == [0.6, 0.8, 1.0]
    assert all(Path(f["png"]).is_file() for f in res["frames"]) and Path(res["strip"]).name == "sh2~0.80.png"
    with Image.open(res["strip"]) as im:
        assert im.size[0] > im.size[1]                      # one row
    assert cli.main(["--world", str(world), "frames", "1", "--around", "0.8"]) == 2           # no shot
    assert cli.main(["--world", str(world), "frames", "1", "--shot", "sh2", "--around", "99"]) == 2
