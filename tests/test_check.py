"""`tadam check` on the fixture world: clean as made, and every check code given by a world spoiled just so."""
from __future__ import annotations

import json
import shutil

import pytest
from jsonschema import Draft202012Validator

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
    "set_missing": (script(lambda s: s["film"].update(set="attic")), None),
    "set_invalid": (lambda r: edit(r, "sets/barn/set.json", lambda d: d.update(floor=5)), None),
    "set_file_missing": (lambda r: (r / "sets/barn/crate.png").unlink(), None),
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
