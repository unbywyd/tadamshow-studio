"""`tadam check` on the fixture world: clean as made, and every check code given by a world spoiled just so."""
from __future__ import annotations

import json
import shutil

import pytest
from jsonschema import Draft202012Validator
from PIL import Image

from tadam import check, cli, schema, scenecheck
from tadam.world import write_json


def edit(root, rel, fn):
    p = root / rel
    data = json.loads(p.read_text(encoding="utf-8"))
    fn(data)                    # (every change is made in place; what fn returns is ignored)
    write_json(p, data)


def script(fn):
    return lambda root: edit(root, "episodes/1/script.json", fn)


def step(s, key):
    return next(st for steps in s["roles"].values() for st in steps if st["key"] == key)


def shot(s, sid):
    return next(x for x in s["shots"] if x["id"] == sid)


def codes(root, episode=None):
    return {i.code for i in check.check_world(root, episode)}


def action(name, data=None, check=None):
    """A world's own action (actions/<name>.json; data: the core wave under this name, or as given)."""
    def spoil(root):
        from tadam import actionkit
        wave = json.loads((actionkit.core_dir() / "wave.json").read_text(encoding="utf-8"))
        d = root / "actions"
        d.mkdir(exist_ok=True)
        f = d / f"{name}.json"
        if isinstance(data, bytes):
            f.write_bytes(data)
        else:
            write_json(f, data if data is not None else {**wave, "id": name})
        if check is not None:
            write_json(d / f"{name}.check.json", {**check, "sha": actionkit.file_sha(f)})
    return spoil


# code -> (how to spoil the world, which episode to check)
SPOIL = {
    "json_invalid": (lambda r: (r / "heroes/cow/hero.json").write_text("{", encoding="utf-8"), None),
    "schema": (lambda r: edit(r, "world.json", lambda w: w.update(slug="Bad Slug")), None),
    "world_missing": (lambda r: (r / "world.json").unlink(), None),
    "todo_text": (lambda r: edit(r, "world.json", lambda w: w.update(tagline={"ru": "TODO: потом"})), None),
    "bible_incomplete": (lambda r: edit(r, "world.json", lambda w: w["bible"].pop("tone")), None),
    "cover_missing": (lambda r: (r / "cover.png").unlink(), None),
    "text_missing_lang": (lambda r: edit(r, "world.json", lambda w: w.update(langs=["ru", "en"])), None),
    "folder_name": (lambda r: (r / "heroes" / "Bad_Name").mkdir(), None),
    "hero_json_missing": (lambda r: (r / "heroes" / "ghost").mkdir(), None),
    "hero_missing": (script(lambda s: s["cast"]["cow"].update(character="unicorn")), None),
    "puppet_missing": (lambda r: shutil.rmtree(r / "heroes/cow/puppet"), None),
    "puppet_not_passed": (lambda r: edit(r, "heroes/cow/puppet/report.json", lambda d: d.update(passed=False)), None),
    "puppet_parts_missing": (lambda r: (r / "heroes/cow/puppet/parts/head.png").unlink(), None),
    "hero_actions_missing": (lambda r: (r / "heroes/cow/puppet/actions.json").unlink(), None),
    "hero_actions_stale": (lambda r: edit(r, "heroes/cow/puppet/rig.json", lambda d: d.update(note="re-cut")), None),
    "hero_actions_failed": (lambda r: edit(r, "heroes/cow/puppet/actions.json",
                                           lambda d: d.update(passed=False, stage1_failed=["wave"])), None),
    "puppet_no_board": (lambda r: edit(r, "heroes/cow/puppet/rig.json", lambda d: d["parts"]["head"].pop("board")), None),
    "puppet_name_twice": (lambda r: edit(r, "heroes/cow/puppet/meta.json", lambda d: d.update(name="detective")), None),
    "cover_file_missing": (lambda r: edit(r, "world.json", lambda w: w.update(cover="art/cover.webp")), None),
    "set_missing": (script(lambda s: s["film"].update(set="attic")), None),
    "set_invalid": (lambda r: edit(r, "sets/barn/set.json", lambda d: d.update(floor=5)), None),
    "set_file_missing": (lambda r: (r / "sets/barn/crate.png").unlink(), None),
    "frames_invalid": (lambda r: edit(r, "sets/barn/set.json",
                                      lambda d: d["pieces"][0].update(frames={"count": 1})), None),
    "frames_size": (lambda r: (Image.new("RGBA", (20, 20)).save(r / "sets/barn/crate.f2.png"),
                               edit(r, "sets/barn/set.json", lambda d: d["pieces"][0].update(frames={"count": 2}))),
                    None),
    "frames_ignored": (lambda r: edit(r, "heroes/cow/puppet/rig.json",
                                      lambda d: d["parts"]["head"].update(frames={"count": 2})), None),
    "frames_heavy": (lambda r: ([Image.new("RGBA", (2000, 1600)).save(r / f"sets/barn/crate{k}.png")
                                 for k in ("", ".f2", ".f3", ".f4", ".f5", ".f6", ".f7", ".f8")],
                                edit(r, "sets/barn/set.json", lambda d: d["pieces"][0].update(frames={"count": 8}))),
                     None),
    "action_name": (action("mine", {"id": "other", "title": "t", "group": "gesture", "phases": [{"time": 1}]}), None),
    "action_name_taken": (action("wave"), None),
    "action_heavy": (action("big", b"{" + b" " * 17000 + b"}"), None),
    "action_unchecked": (action("mine"), None),
    "action_failed": (action("mine", None, {"passed": False, "heroes": {"cow": {"played": True, "pass": False}}}), None),
    "frames_unused": (lambda r: Image.new("RGBA", (200, 150)).save(r / "sets/barn/crate.f2.png"), None),
    "media_missing": (script(lambda s: s["film"]["music"].update(file="nope.mp3")), None),
    "name_case": (script(lambda s: s["film"]["music"].update(file="Theme.mp3")), None),
    "episode_missing": (lambda r: None, "7"),
    "script_missing": (lambda r: (r / "episodes/1/script.json").unlink(), None),
    "script_v1": (script(lambda s: s.update(version=1)), None),
    "hero_not_in_cast": (script(lambda s: s["roles"].update(ghost=[{"key": "g-1", "kind": "info"}])), None),
    "hero_no_steps": (script(lambda s: s["cast"].update(dog={"character": "cow"})), None),
    "step_key_twice": (script(lambda s: step(s, "det-2").update(key="det-1")), None),
    "line_no_text": (script(lambda s: step(s, "cow-1").pop("text")), None),
    "shot_id_twice": (script(lambda s: shot(s, "sh2").update(id="sh1")), None),
    "say_unknown": (script(lambda s: shot(s, "sh1").update(say="zzz")), None),
    "say_not_line": (script(lambda s: shot(s, "sh1").update(say="det-2")), None),
    "listen_unknown": (script(lambda s: shot(s, "sh1").update(listen={"det": "cow-1"})), None),
    "shot_no_length": (script(lambda s: [shot(s, "sh3").pop(k) for k in ("seconds", "narration")]), None),
    "film_not_vertical": (script(lambda s: s["film"].update(width=1920, height=1080)), None),
    "actor_not_in_cast": (script(lambda s: shot(s, "sh1")["actors"].append({"id": "dog", "x": 0.9})), None),
    "actor_twice": (script(lambda s: shot(s, "sh2")["actors"].append({"id": "det", "x": 0.1})), None),
    "speaker_not_in_shot": (script(lambda s: shot(s, "sh2").update(actors=[{"id": "cow", "x": 0.5}])), None),
    "step_no_hint": (script(lambda s: step(s, "cow-1").pop("hint")), None),
    "step_no_look": (script(lambda s: step(s, "cow-1").pop("look")), None),
    "line_too_long": (script(lambda s: step(s, "cow-1").update(maxSeconds=1)), None),
    "line_long": (script(lambda s: [step(s, "cow-1").pop("maxSeconds"),
                                    step(s, "cow-1").update(text={"ru": "слово " * 60})]), None),
    "episode_too_long": (script(lambda s: s["shots"].extend(
        [{"id": f"x{i}", "remark": {"ru": "Пауза"}, "seconds": 120, "actors": [{"id": "cow", "x": 0.5}]}
         for i in range(3)])), None),
    "stage_option_unknown": (script(lambda s: s["film"].update(stage={"bogus": 1})), None),
    # the server's content checks
    "bad_word": (script(lambda s: step(s, "cow-1").update(text={"ru": "Где моя луна, сука?"})), None),
    "borderline_word": (script(lambda s: s["shots"][0].update(remark={"ru": "Корова-дурак спрашивает"})), None),
    "no_sources": (lambda r: (r / "sources.json").unlink(), None),
    "no_source": (lambda r: edit(r, "sources.json", lambda d: d["files"].pop("media/")), None),
    "source_unused": (lambda r: edit(r, "sources.json", lambda d: d["files"].update({"media/gone.mp3": {"source": "own"}})), None),
}


def test_fixture_world_is_clean(world):
    found = check.check_world(world)
    assert found == [], [i.as_dict() for i in found]


def test_every_world_code_has_a_case():
    assert set(SPOIL) == set(check.CODES)


@pytest.mark.parametrize("code", sorted(SPOIL))
def test_code_fails_and_passes(world, code):
    assert code not in codes(world)                       # passing: the world as made
    spoil, episode = SPOIL[code]
    spoil(world)
    found = check.check_world(world, episode)
    assert code in {i.code for i in found}, [i.as_dict() for i in found]
    for i in found:
        if i.code == code:
            assert i.level == check.CODES[code][0]


def test_scene_checks_run_on_every_shot(world):
    """A scene-level mistake in a v2 shot comes back through tadam check, with the shot named."""
    edit(world, "episodes/1/script.json", lambda s: shot(s, "sh1")["camera"].append({"at": 1, "camera": "drone"}))
    found = [i for i in check.check_world(world) if i.code == "camera_unknown"]
    assert found and "sh1" in found[0].where


def test_the_format_is_a_stage_option_as_on_the_server(world):
    # the server passes film.stage.format "9:16" to the engine (resolve.ts stageOf): the kit takes it too, and a
    # landscape format is the scene check's not_vertical, not an unknown option
    script(lambda s: s["film"].update(stage={**(s["film"].get("stage") or {}), "format": "9:16"}))(world)
    assert not {"stage_option_unknown", "not_vertical"} & codes(world, "1")
    script(lambda s: s["film"]["stage"].update(format="16:9"))(world)
    found = codes(world, "1")
    assert "not_vertical" in found and "stage_option_unknown" not in found


def test_heroes_overlap_through_check(world):
    edit(world, "episodes/1/script.json", lambda s: shot(s, "sh1").update(
        actors=[{"id": "cow", "x": 0.5}, {"id": "det", "x": 0.52}]))
    assert "heroes_overlap" in codes(world)


def test_unused_hero_without_puppet_is_only_a_warning(world):
    from tadam import new
    from tadam.world import World
    new.hero(World(world), "goat", "Коза")
    found = [i for i in check.check_world(world) if "goat" in i.where]
    assert {i.code for i in found} >= {"puppet_missing"}
    assert all(i.level != "error" for i in found)


def test_one_episode_only(world):
    shutil.copytree(world / "episodes" / "1", world / "episodes" / "2")
    edit(world, "episodes/2/script.json", lambda s: shot(s, "sh1").update(say="zzz"))
    assert "say_unknown" not in codes(world, "1")
    assert "say_unknown" in codes(world, "2")
    assert "say_unknown" in codes(world)


def test_cli_exit_codes_and_json(world, capsys):
    assert cli.main(["--world", str(world), "check"]) == 0
    out = capsys.readouterr().out
    assert "no problems" in out
    edit(world, "episodes/1/script.json", lambda s: shot(s, "sh1").update(say="zzz"))
    assert cli.main(["--world", str(world), "check", "1", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    Draft202012Validator(schema.load("check-result")).validate(data)
    assert data["ok"] is False
    assert any(i["code"] == "say_unknown" and i["level"] == "error" for i in data["issues"])


def test_cli_finds_the_world_from_a_subfolder(world, monkeypatch, capsys):
    monkeypatch.chdir(world / "episodes" / "1")
    assert cli.main(["check"]) == 0


def test_cli_outside_a_world(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["check"]) == 1
    assert "no world.json" in capsys.readouterr().out


def test_codes_do_not_collide_in_meaning():
    """A code shared by the world and the scene checks must mean the same thing at the same level."""
    for code in set(check.CODES) & set(scenecheck.CODES):
        assert check.CODES[code][0] == scenecheck.CODES[code][0], code


# ------------------------------------------------------------------------------------------------ the cover

@pytest.mark.parametrize("name", ["cover.png", "cover.jpg", "cover.jpeg", "cover.webp"])
def test_any_cover_the_server_takes_is_a_cover(world, name):
    (world / "cover.png").rename(world / name)
    edit(world, "sources.json", lambda d: d["files"].update({name: d["files"].pop("cover.png")}))
    assert "cover_missing" not in codes(world)


def test_world_json_names_its_cover(world):
    (world / "art").mkdir()
    (world / "cover.png").rename(world / "art" / "front.webp")
    edit(world, "sources.json", lambda d: d["files"].update({"art/front.webp": d["files"].pop("cover.png")}))
    assert "cover_missing" in codes(world)
    edit(world, "world.json", lambda w: w.update(cover="art/front.webp"))
    found = codes(world)
    assert "cover_missing" not in found and "cover_file_missing" not in found


def test_two_heroes_with_one_puppet_name_is_an_error_that_names_both(world):
    edit(world, "heroes/detective/puppet/meta.json", lambda d: d.update(name="puppet"))
    edit(world, "heroes/cow/puppet/meta.json", lambda d: d.update(name="puppet"))
    (issue,) = [i for i in check.check_world(world) if i.code == "puppet_name_twice"]
    assert issue.level == "error" and "cow" in issue.where and "detective" in issue.where


# ------------------------------------------------------------------------------------------------ the output

def test_check_hides_info_unless_verbose_and_says_the_length(world, capsys):
    edit(world, "episodes/1/script.json", lambda s: shot(s, "sh3").pop("actors"))       # a shot of a place: info
    assert "no_actors" in codes(world)
    assert cli.main(["--world", str(world), "check"]) == 0
    out = capsys.readouterr().out
    assert "no_actors" not in out and "--verbose" in out
    assert "episode 1: 3 shot(s), about" in out
    assert cli.main(["--world", str(world), "check", "--verbose"]) == 0
    assert "no_actors" in capsys.readouterr().out


# ------------------------------------------------------------------------------------------------ the examples

def _examples():
    from tadam.paths import kit_root
    return sorted(p.parent for p in (kit_root() / "examples").glob("*/world.json"))


@pytest.mark.parametrize("root", _examples(), ids=lambda p: p.name)
def test_every_example_passes_check_with_no_errors_and_no_warnings(root):
    found = [i for i in check.check_world(root) if i.level != "info"]
    assert found == [], [i.as_dict() for i in found]


def test_there_is_an_example():
    assert _examples()
