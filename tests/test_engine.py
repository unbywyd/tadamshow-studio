"""The ported engine opens a scene of a world folder (absolute paths, spaces, non-latin letters) and plays it
through, unseen. Needs Godot 4.7 (`tadam doctor`); skipped without it."""
from __future__ import annotations

import json

import pytest

from tadam import cli, doctor, engine, resolve
from tadam.world import World, read_json

needs_godot = pytest.mark.skipif(doctor.find_godot(doctor.System())[0] is None, reason="Godot 4.7 is not installed")


@needs_godot
def test_engine_plays_a_world_scene(world):
    w = World(world)
    s, _ = read_json(w.episode_dir("1") / "script.json")
    d = resolve.write_scenes(w, "1", s)[0]
    res = engine.run_check(d, 1.0, timeout=600)
    assert res is not None, "the engine did not play the scene to its end"
    assert res["seconds"] == 1.0
    assert json.dumps(res)


@needs_godot
def test_check_with_the_engine(world, capsys):
    assert cli.main(["--world", str(world), "check", "1", "--engine"]) == 0, capsys.readouterr().out
