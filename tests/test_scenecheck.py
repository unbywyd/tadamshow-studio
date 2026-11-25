"""tadam.scenecheck: pure functions over one engine scene. A clean scene, and every code given by a scene spoiled
just so. The context is made of plain data here, as the server will make it (no files, no Godot)."""
from __future__ import annotations

import copy
import json

import pytest

from tadam import scenecheck as sc
from tadam.paths import engine_dir

ACTIONS = {
    "wave": {"phases": [{"arm_r": {}}]},
    "hips": {"phases": [{"arms": {}}]},
    "jump": {"phases": [{"legs": {}}]},
    "sit_act": {"view": "side", "phases": [{"legs": {}}]},
    "guitar_strum": {"group": "music", "phases": [{"arms": {}}]},
    "punch": {"group": "fight", "phases": [{"arm_r": {}}]},
    "handshake": {"pair": {"partner": "handshake_b"}, "phases": [{"arm_r": {}}]},
    "handshake_b": {"partner_only": True, "phases": [{"arm_r": {}}]},
}
FILES = {"bg.png", "music.ogg", "head.ogv"}
PUPPETS = {"p/a": sc.PuppetInfo(views={"front"}, width=0.55),
           "p/b": sc.PuppetInfo(views={"front", "side", "back"}, width=0.55)}


def ctx(phrases=3):
    return sc.Context(actions=ACTIONS, items={"guitar": {"play": {}}, "mug": {}}, sounds={"step"},
                      grades={"evening"}, file_exists=lambda p: p in FILES, puppet=PUPPETS.get,
                      phrases=lambda clip: phrases if clip == "head.ogv" else None)


BASE = {
    "background": "bg.png", "seconds": 6, "format": "9:16",
    "points": {"door": {"x": 0.8, "y": 0.8}, "bench": {"x": 0.2, "y": 0.8, "seat": {}}},
    "items": [{"id": "mug", "card": "mug"}],
    "actors": [{"id": "a", "puppet": "p/a", "x": 0.25, "height": 0.4},
               {"id": "b", "puppet": "p/b", "x": 0.75, "height": 0.4, "clip": "head.ogv"}],
    "music": {"file": "music.ogg", "bpm": 120},
    "script": [
        {"at": 0.5, "who": "a", "do": "wave"},
        {"at": 1, "who": "b", "go": "door"},
        {"after": "go", "of": "b", "who": "a", "do": "jump"},
        {"at": 1.5, "camera": "medium", "on": "a", "time": 0.5},
        {"at": 2, "label": "x", "who": "a", "do": "hips"},
        {"after": "#x", "who": "b", "do": "wave"},
        {"phrase": 1, "who": "b", "do": "jump"},
        {"beat": 2, "who": "a", "do": "jump"},
        {"at": 3, "grade": "evening"},
        {"at": 3, "sound": "step"},
        {"at": 3.5, "who": "a", "take": "mug"},
        {"at": 4, "who": "a", "sit": "bench"},
        {"at": 4.5, "who": "a", "stand": True},
        {"at": 5, "who": "b", "play": "guitar", "for": 1},
        {"at": 5, "who": "a", "do": "handshake", "with": "b"},
    ],
}


def line(**kw):
    return lambda s, c: s["script"].append(kw)


def actor(i, **kw):
    return lambda s, c: s["actors"][i].update(kw)


def setc(attr, value):
    return lambda s, c: setattr(c, attr, value)


SPOIL = {
    "background_missing": lambda s, c: s.update(background="nope.png"),
    "sound_missing": lambda s, c: s["music"].update(file="nope.ogg"),
    "item_missing": lambda s, c: s["items"][0].update(card="anvil"),
    "no_actors": lambda s, c: s.update(actors=[], script=[]),
    "actor_duplicate": actor(1, id="a"),
    "puppet_missing": actor(0, puppet="p/zzz"),
    "clip_missing": actor(1, clip="nope.ogv"),
    "actor_x_invalid": actor(0, x="left"),
    "actor_height_unusual": actor(0, height=0.95),
    "point_missing": actor(0, at="attic"),
    "unknown_command": line(at=1, who="a", dance_floor=1),
    "unknown_hero": line(at=1, who="zed", do="wave"),
    "who_missing": line(at=1, do="wave"),
    "action_missing": line(at=1, who="a", do="moonwalk"),
    "action_needs_side_view": line(at=1, who="a", do="sit_act"),
    "action_use_play": line(at=1, who="a", do="guitar_strum"),
    "pair_half": line(at=1, who="a", do="handshake_b"),
    "pair_needs_with": line(at=1, who="a", do="handshake"),
    "pair_unknown_partner": line(at=1, who="a", do="handshake", **{"with": "zed"}),
    "pair_self": line(at=1, who="a", do="handshake", **{"with": "a"}),
    "target_unknown": line(at=1, who="a", give="zed"),
    "go_target_missing": line(at=1, who="a", go="attic"),
    "go_self": line(at=1, who="a", go="a"),
    "go_off_stage": line(at=1, who="a", go=1.5),
    "walk_style_unknown": line(at=1, who="a", go="door", style="moonwalk"),
    "point_not_seat": line(at=1, who="a", sit="door"),
    "turn_unknown": line(at=1, who="a", turn="up"),
    "view_missing": line(at=1, who="a", turn="back"),
    "item_not_in_scene": line(at=1, who="a", take="anvil"),
    "instrument_missing": line(at=1, who="a", play="harp"),
    "camera_unknown": line(at=1, camera="drone"),
    "camera_on_unknown": line(at=1, camera="medium", on="zed"),
    "camera_without_on": line(at=1, camera="close"),
    "grade_unknown": line(at=1, grade="neon"),
    "hand_place_unknown": line(at=1, who="a", hands="nowhere"),
    "stop_unknown": line(at=1, who="a", stop="moonwalk"),
    "timing_twice": line(after="go", of="b", beat=3, who="a", do="jump"),
    "at_not_number": line(at="soon", who="a", do="wave"),
    "at_after_end": line(at=99, who="a", do="wave"),
    "phrase_no_voice": lambda s, c: s["actors"][1].pop("clip"),
    "phrase_unknown": setc("phrases", lambda clip: None),
    "phrase_out_of_range": line(phrase=9, who="b", do="wave"),
    "beat_no_bpm": lambda s, c: s["music"].pop("bpm"),
    "after_unknown_label": line(after="#nolabel", who="a", do="wave"),
    "after_unknown_hero": line(after="go", of="zed", who="a", do="wave"),
    "after_unknown_action": line(after="fly", who="a", do="wave"),
    "after_never_started": line(after="turn", of="b", who="a", do="wave"),
    "actions_clash": lambda s, c: s["script"].extend([{"at": 2.5, "who": "a", "do": "wave"},
                                                      {"at": 2.5, "who": "a", "do": "punch"}]),
    "not_vertical": lambda s, c: s.update(format="16:9"),
    "too_many_heroes": lambda s, c: s["actors"].extend([{"id": "c", "puppet": "p/a", "x": 0.5, "depth": 0.5},
                                                        {"id": "d", "puppet": "p/a", "x": 0.5, "depth": 0.9}]),
    "off_frame": actor(0, x=0.02),
    "heroes_overlap": actor(1, x=0.3),
    "not_frontal": line(at=1, who="b", turn="left"),
}


def run(spoil=None):
    s, c = copy.deepcopy(BASE), ctx()
    if spoil:
        spoil(s, c)
    return sc.check_scene(s, c, "sh1")


def test_clean_scene_has_no_findings():
    found = run()
    assert found == [], [i.as_dict() for i in found]


def test_every_scene_code_has_a_case():
    # scene_invalid cannot be made by spoiling a scene: it is the scene not being an object (test below)
    assert set(SPOIL) | {"scene_invalid"} == set(sc.CODES)


def test_scene_that_is_not_an_object():
    found = sc.check_scene(["not", "a", "scene"], sc.Context(), "sh1")
    assert [i.code for i in found] == ["scene_invalid"] and found[0].level == "error"


def test_a_shot_with_no_hero_is_allowed():
    # the first episode opens on the city at night, the desk, the clock: places and things, nobody in them
    found = run(SPOIL["no_actors"])
    assert not [i for i in found if i.level == "error"], [i.as_dict() for i in found]


@pytest.mark.parametrize("code", sorted(SPOIL))
def test_code_fails_and_passes(code):
    assert code not in {i.code for i in run()}
    found = run(SPOIL[code])
    hits = [i for i in found if i.code == code]
    assert hits, [i.as_dict() for i in found]
    assert all(i.level == sc.CODES[code][0] for i in hits)
    assert all(i.where.startswith("sh1") for i in hits)


def test_heroes_at_different_depths_may_overlap():
    s = copy.deepcopy(BASE)
    s["ground"] = {"far": 0.66, "far_scale": 0.6}
    s["actors"][1].update(x=0.3, depth=0.8)
    assert "heroes_overlap" not in {i.code for i in sc.check_scene(s, ctx())}


def test_over_the_shoulder_hero_is_exempt():
    s = copy.deepcopy(BASE)
    s["actors"][0].update(x=0.05, near=2.3)
    s["actors"][1].update(x=0.6)
    assert not {"off_frame", "heroes_overlap"} & {i.code for i in sc.check_scene(s, ctx())}


def test_garbage_does_not_crash():
    for spec in ({}, {"actors": "no"}, {"actors": [None, 3]}, {"script": [None, "x"]}, []):
        sc.check_scene(spec, ctx())


def test_result_is_json_serialisable():
    json.dumps([i.as_dict() for i in run(SPOIL["camera_unknown"])])


def test_context_from_the_kits_engine():
    c = sc.Context.from_engine(engine_dir())
    assert len(c.actions) >= 80 and "wave" in c.actions
    assert {"guitar", "drum", "accordion"} <= set(c.items)
    assert "step" in c.sounds and len(c.grades) >= 3


def test_rig_width_of_a_real_puppet(mannequin_puppet):
    info = sc.puppet_from_folder(str(mannequin_puppet))
    assert info is not None and info.views == {"front"}
    assert 0.3 < info.width < 1.2
    assert sc.puppet_from_folder(str(mannequin_puppet / "nope")) is None


def test_rig_width_survives_a_broken_rig():
    assert sc.rig_width({"parts": {"x": {"parent": "y"}}}) == sc.DEFAULT_WIDTH
    assert sc.rig_width({}) == sc.DEFAULT_WIDTH
