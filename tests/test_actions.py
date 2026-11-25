"""`tadam hero check`: every action on a hero, measured by the engine (engine/tools/action_check.gd)."""
from __future__ import annotations

import json
import shutil
import time

import pytest

from tadam import actions, check, cli, doctor
from tadam.world import World

needs_godot = pytest.mark.skipif(doctor.find_godot(doctor.System())[0] is None, reason="Godot 4.7 is not installed")


def raw(**faults) -> dict:
    """The engine's runs: every stage-1 action clean, plus what is given (action -> {measure: value})."""
    runs = [{"action": a, "side": "right", "faults": []} for a in actions.STAGE1]
    for a, f in faults.items():
        runs = [r for r in runs if r["action"] != a]
        runs.append({"action": a, "side": "right", "faults": list(f), **f})
        runs.append({"action": a, "side": "left", "faults": []})
    return {"limits": {"inside": 0.15}, "runs": runs}


def test_stage1_is_the_engines_first_stage():
    assert len(actions.STAGE1) == 33 and len(set(actions.STAGE1)) == 33


def test_a_stage1_fault_fails_the_hero_and_names_the_measure():
    res = actions.summarise(raw(wave={"inside": 0.4}), {"wave": "gesture"}, "sha", 1.0)
    assert not res["passed"] and res["stage1_failed"] == ["wave"]
    w = res["actions"]["wave"]
    assert not w["pass"] and w["runs"][0]["faults"] == {"inside": 0.4} and w["runs"][1]["pass"]
    assert "FAIL wave" in actions.table(res) and "inside 0.4" in actions.table(res)


def test_other_actions_and_out_of_picture_do_not_fail_the_hero():
    res = actions.summarise(raw(kick={"inside": 1.5}, hop={"out": 0.06}), {"kick": "fight"}, "sha", 1.0)
    assert res["passed"]
    assert not res["actions"]["kick"]["pass"] and res["actions"]["hop"]["pass"]
    assert res["actions"]["hop"]["runs"][0]["notes"] == {"out": 0.06}
    assert "warn kick" in actions.table(res)


def test_a_stage1_action_not_played_fails():
    r = raw()
    r["runs"] = [x for x in r["runs"] if x["action"] != "bow"]
    res = actions.summarise(r, {}, "sha", 1.0)
    assert not res["passed"] and res["stage1_missing"] == ["bow"]


@needs_godot
def test_the_mannequin_passes_every_stage1_action(world, capsys):
    """The real engine run on the code-drawn mannequin: it must pass; tadam check then reports it clean."""
    w = World(world)
    (w.puppet_dir("cow") / actions.FILE).unlink()
    shutil.rmtree(w.hero_dir("detective"))
    t = time.monotonic()
    code = cli.main(["--world", str(world), "hero", "check", "cow"])
    took = time.monotonic() - t
    out = capsys.readouterr().out
    assert code == 0, out
    assert "stage 1: 33/33 actions pass" in out and "PASSED" in out
    data = json.loads((w.puppet_dir("cow") / actions.FILE).read_text(encoding="utf-8"))
    assert data["passed"] and data["rig"] == actions.rig_sha(w.puppet_dir("cow"))
    assert {"wave", "bow", "jump"} <= set(data["actions"]) and data["actions"]["wave"]["runs"][0]["side"] == "right"
    sides = {r["side"] for r in data["actions"]["point"]["runs"]}
    assert sides == {"right", "left"}                               # one-sided actions on both sides
    print(f"\n[hero check on the mannequin: {took:.1f} s]")
    codes = {i.code for i in check.check_world(world) if i.where.startswith("heroes/cow")}
    assert not codes & {"hero_actions_missing", "hero_actions_failed", "hero_actions_stale"}
