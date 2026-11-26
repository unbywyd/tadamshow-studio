"""Paths: spaces, non-latin letters, letter case, absolute scene paths, the kit's own files."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tadam import paths, resolve
from tadam.world import World, exact, find_world, is_safe_name, read_json


def test_world_found_from_a_deep_folder(world):
    deep = world / "episodes" / "1"
    assert find_world(deep) == world.resolve()


def test_exact_case(world):
    assert exact(world, "media/theme.mp3") == "ok"
    assert exact(world, "media/Theme.mp3") == "case"
    assert exact(world, "MEDIA/theme.mp3") == "case"
    assert exact(world, "media/none.mp3") == "missing"
    assert exact(world, "nowhere/x") == "missing"


@pytest.mark.parametrize("name, ok", [
    ("theme.mp3", True), ("music/theme.mp3", True), ("a/b/c/d.png", True),
    ("../x.png", False), ("a/../x.png", False), ("/abs.png", False), ("C:/x.png", False), ("a\\b.png", False),
    ("res://x.png", False), ("user://x", False), ("https://x/y.png", False), (".hidden", False),
    ("мой.png", False), ("a b.png", False), ("a/b/c/d/e.png", False), (None, False), (3, False),
])
def test_safe_names(name, ok):
    assert is_safe_name(name) is ok


def test_scenes_use_absolute_paths_inside_the_world(world):
    w = World(world)
    s, _ = read_json(w.episode_dir("1") / "script.json")
    dirs = resolve.write_scenes(w, "1", s)
    assert [d.name for d in dirs] == ["sh1", "sh2", "sh3"]
    assert all(d.parent == w.work_dir() / "scenes" / "1" for d in dirs)
    sh1 = json.loads((dirs[0] / "scene.json").read_text(encoding="utf-8"))
    files = [sh1["background"]] + [p["image"] for p in sh1["pieces"]] + [a["puppet"] for a in sh1["actors"]]
    for f in files:
        assert Path(f).is_absolute() and Path(f).exists(), f
        assert "\\" not in f                                    # one separator on every OS
        assert Path(f).resolve().is_relative_to(w.root)
    assert "мир с пробелом" in sh1["background"]
    assert sh1["format"] == "9:16" and sh1["faces"] == "board"
    assert sh1["script"] == [{"at": 0, "camera": "medium", "on": "cow"}]
    assert sh1["actors"][1]["depth"] == 0.5 and sh1["actors"][0]["height"] == 0.42
    sh2 = json.loads((dirs[1] / "scene.json").read_text(encoding="utf-8"))
    prop = sh2["actors"][0]["props"]["prop"]["image"]
    assert prop.endswith("media/cup.png") and Path(prop).exists()
    assert {"at": 0, "who": "det", "show": "prop"} in sh2["script"]
    assert sh2["focus"] == {"on": "det"}


def test_script_cannot_point_the_engine_at_other_files(world):
    """Paths a script or a set might smuggle in never reach a scene."""
    w = World(world)
    s, _ = read_json(w.episode_dir("1") / "script.json")
    s["shots"][0]["actors"][0].update(puppet="C:/elsewhere", clip="/etc/x.ogv", mouth="res://m", prop="../../x.png")
    s["shots"][0]["stage"] = {"background": "/etc/passwd", "vignette": 0.3}
    st = json.loads((w.set_dir("barn") / "set.json").read_text(encoding="utf-8"))
    st["pieces"].append({"id": "x", "image": "../../../outside.png", "rect": [0, 0, 1, 1], "base": 1})
    (w.set_dir("barn") / "set.json").write_text(json.dumps(st), encoding="utf-8")
    scene = resolve.shot_scene(w, s, s["shots"][0])
    a = scene["actors"][0]
    assert a["puppet"] == w.puppet_dir("cow").as_posix()
    assert "clip" not in a and "mouth" not in a and "props" not in a
    assert scene["vignette"] == 0.3 and not scene["background"].startswith("/etc")
    assert all("outside" not in p["image"] for p in scene["pieces"])


def test_near_true_is_a_number_for_the_engine(world):
    w = World(world)
    s, _ = read_json(w.episode_dir("1") / "script.json")
    s["shots"][0]["actors"][0]["near"] = True
    assert resolve.shot_scene(w, s, s["shots"][0])["actors"][0]["near"] == resolve.NEAR


def test_shot_lengths():
    steps = {"a-1": ("a", {"key": "a-1", "kind": "read", "text": {"ru": "раз два три четыре"}})}
    assert resolve.shot_seconds({"seconds": 2.5}, steps) == 2.5
    # (tadam.timing: lead 0.4 + words / 2.3 + trail 0.25 + tail 0.4; a line wins over "seconds", as on the server)
    assert resolve.shot_seconds({"say": "a-1"}, steps) == round(0.4 + 4 / 2.3 + 0.25 + 0.4, 2)
    assert resolve.shot_seconds({"say": "a-1", "seconds": 9}, steps) == round(0.4 + 4 / 2.3 + 0.25 + 0.4, 2)
    assert resolve.shot_seconds({"narration": {"text": {"ru": "раз"}, "at": 1}}, {}) == round(1 + 0.6 + 0.7, 2)
    assert resolve.shot_seconds({"narration": {"text": {"ru": "раз"}, "at": 1}}, {}, narration_seconds=2.5) == 4.2
    assert resolve.shot_seconds({}, {}) == resolve.DEFAULT_SECONDS


def test_kit_files_are_where_the_code_looks():
    assert (paths.engine_dir() / "project.godot").is_file()
    assert (paths.engine_dir() / "stage.gd").is_file()
    assert (paths.schema_dir() / "script.v2.json").is_file()
    assert len([d for d in paths.RIGS.iterdir() if (d / "rig.json").is_file()]) == 15
    for f in ("PT_Serif-Web-Bold.ttf", "PT_Serif-Web-Italic.ttf", "PTM55FT.ttf", "OFL-PT-Serif.txt", "OFL-PT-Mono.txt"):
        assert (paths.FONTS / f).is_file(), f


def test_engine_main_scene_is_the_stage():
    proj = (paths.engine_dir() / "project.godot").read_text(encoding="utf-8")
    assert 'run/main_scene="res://stage.tscn"' in proj and "demo" not in proj


def test_engine_has_nothing_it_must_not():
    eng = paths.engine_dir()
    names = [p.relative_to(eng).as_posix() for p in eng.rglob("*") if p.is_file() and ".godot" not in p.parts]
    # hands/ ships since 26.11: the shared gloves every hero wears (the owner's own generations; he said to commit them)
    for bad in ("media/", "puppets/", "demo.", "headtest", "selftest", "handles.gd", "export_presets"):
        assert not any(n.startswith(bad) or ("/" + bad) in n or n.startswith(bad) for n in names), bad
    assert not any(re.search(r"\.(ogv|mp4|avi|mp3)$", n) for n in names)
    for owner_made in ("ball", "book", "crate", "mug", "shovel", "sword", "wheel"):
        assert not (eng / "items" / f"{owner_made}.png").exists()
    assert not any(n.startswith("hands/") and "sheet" in n for n in names)     # only the cut gloves, no source sheets


def test_engine_has_the_default_gloves():
    gl = paths.engine_dir() / "hands" / "glove"
    for f in ("hands.json", "back.png", "edge.png", "fist.png", "palm.png", "point.png"):
        assert (gl / f).is_file(), f


def test_title_card_draws_cyrillic(tmp_path):
    from PIL import Image

    from tadam import titlecard
    out = tmp_path / "карточка" / "card.png"
    titlecard.card(out, "Корова / и луна", "Серия первая", "ТадамШоу")
    im = Image.open(out)
    assert im.size == (720, 1280) and im.getchannel("A").getbbox() is not None
