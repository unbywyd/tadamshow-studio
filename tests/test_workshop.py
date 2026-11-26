"""The workshop and the action tools (mechanics-tz М0-М2): the proof bodies, the action schema, the world's own
actions (library, check, scenes), poses into actions, the clean switch and the window itself."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tadam import actionkit, check, doctor, engine, proof, schema, workshop
from tadam.paths import engine_dir, kit_root

needs_godot = pytest.mark.skipif(doctor.find_godot(doctor.System())[0] is None, reason="Godot 4.7 is not installed")
EXAMPLE = kit_root() / "examples" / "sock-bureau"


def _world(tmp_path: Path) -> Path:
    root = tmp_path / "w"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".tadam"))
    return root


# ------------------------------------------------------------------------------------------------ the schema

def test_every_core_action_fits_the_schema():
    bad = {}
    for f in sorted((engine_dir() / "actions").glob("*.json")):
        errs = schema.validate("action", json.loads(f.read_text(encoding="utf-8")))
        if errs:
            bad[f.name] = errs[:2]
    assert not bad, bad


@pytest.mark.parametrize("spoil", [
    lambda a: a.update(id="../wave"),
    lambda a: a["phases"][0].update(arm_r={"at": {"to": "C:/x.png"}}),
    lambda a: a["phases"][0].update(arm_r={"at": {"to": "https://x"}}),
    lambda a: a["phases"][0].update(time=99),
    lambda a: a.update(phases=[]),
    lambda a: a.update(group="flying"),
])
def test_the_schema_refuses_paths_links_and_wild_numbers(spoil):
    a = json.loads((engine_dir() / "actions" / "wave.json").read_text(encoding="utf-8"))
    spoil(a)
    assert schema.validate("action", a)


# ------------------------------------------------------------------------------------------------ the library

def test_a_world_action_is_listed_but_never_stands_in_for_a_core_one(tmp_path):
    root = _world(tmp_path)
    (root / "actions").mkdir()
    (root / "actions" / "wave.json").write_text(json.dumps({"id": "wave", "title": "fake", "group": "gesture",
                                                            "phases": [{"time": 1}]}), encoding="utf-8")
    actionkit.new(root, "my_wave", "мой взмах")
    lib = actionkit.library(root)
    assert lib["wave"].where == "core" and lib["my_wave"].where == "world"
    assert "[world]" in actionkit.listing(root)
    with pytest.raises(actionkit.ActionError):
        actionkit.new(root, "bow")                 # a core name
    with pytest.raises(actionkit.ActionError):
        actionkit.new(root, "Bad-Name")
    assert "phase 1" in actionkit.describe(lib["my_wave"])


def test_check_reports_world_actions(tmp_path):
    root = _world(tmp_path)
    acts = root / "actions"
    acts.mkdir()
    good = json.loads((engine_dir() / "actions" / "wave.json").read_text(encoding="utf-8"))
    for name, data in {"wave": good, "other": {**good, "id": "nope"}, "fresh": {**good, "id": "fresh"},
                       "broken": {**good, "id": "broken"}}.items():
        (acts / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    e = actionkit.Entry("broken", {**good, "id": "broken"}, acts / "broken.json", "world")
    (acts / "broken.check.json").write_text(json.dumps({"sha": actionkit.file_sha(e.path), "passed": False,
        "heroes": {"archivist": {"played": True, "pass": False}}}), encoding="utf-8")
    codes = {(i.code, i.where.split()[0], i.level) for i in check.check_world(root)}
    assert ("action_name_taken", "actions/wave.json", "error") in codes
    assert ("action_name", "actions/other.json", "error") in codes
    assert ("action_unchecked", "actions/fresh.json", "warning") in codes
    assert ("action_failed", "actions/broken.json", "warning") in codes
    # used by a script, a failed action is an error
    s = root / "episodes" / "1" / "script.json"
    s.write_text(s.read_text(encoding="utf-8").replace('"do": "think"', '"do": "broken"'), encoding="utf-8")
    codes = {(i.code, i.level) for i in check.check_world(root)}
    assert ("action_failed", "error") in codes
    assert not any(i.code == "action_unknown" for i in check.check_world(root))


# ------------------------------------------------------------------------------------------------ poses

REST = {"legs": {"drop": 0.0, "shift": 0.0, "foot_l": [0.0, 0.0], "foot_r": [0.0, 0.0]}, "body": {"lean": 0.0},
        "head": 0.0, "arm_l": {"at": [0.07, 1.0]}, "arm_r": {"at": [0.07, 1.0]}}


def _pose(**ch):
    p = json.loads(json.dumps(REST))
    p.update(ch)
    return p


def test_from_poses_keeps_only_what_changed_and_comes_back():
    up = _pose(arm_r={"at": [0.3, -0.95], "look": "palm"})
    nod = _pose(arm_r={"at": [0.3, -0.95], "look": "palm"}, head=12.0)
    a = workshop.from_poses([{"pose": up, "time": 0.6, "ease": "out"}, {"pose": nod, "time": 0.3, "hold": True}],
                            "hi", "привет", base=REST)
    ph = a["phases"]
    assert set(ph[0]) == {"time", "ease", "arm_r"} and ph[0]["ease"] == "out"
    assert set(ph[1]) == {"time", "loop", "head"}
    assert ph[-1] == {"name": "return", "time": 0.45, "arm_r": "rest", "head": "rest"}
    assert not schema.validate("action", a)
    re = workshop.from_poses([{"pose": up, "time": 0.6}], "hi", keep_times=False, base=REST)
    assert re["phases"][0]["time"] == workshop.way_time(REST, up)
    with pytest.raises(workshop.WorkshopError):
        workshop.from_poses([], "x")


def test_way_time_grows_with_the_way_and_is_bounded():
    near = _pose(arm_r={"at": [0.1, 0.9]})
    far = _pose(arm_r={"at": [0.3, -0.95]})
    assert workshop.way_time(REST, near) == 0.25
    assert 0.25 < workshop.way_time(REST, far) <= 2.0
    assert workshop.way_time(REST, _pose(legs={**REST["legs"], "drop": 0.5})) > 0.25


def test_the_engine_way_time_is_the_same_formula():
    gd = (engine_dir() / "workshop.gd").read_text(encoding="utf-8")
    assert "HAND_PACE := 1.6" in gd and "clampf(far / HAND_PACE + 0.15, 0.25, 2.0)" in gd
    assert workshop.HAND_PACE == 1.6


def test_workshop_config_has_the_heroes_and_the_proof_bodies(tmp_path):
    root = _world(tmp_path)
    cfg = workshop.config(root, "archivist")
    assert cfg["hero"] == "archivist" and {h["id"] for h in cfg["heroes"]} >= {"archivist", "visitor"}
    assert len(cfg["proof"]) == len(proof.names()) and cfg["save_dir"].endswith("/actions")
    with pytest.raises(workshop.WorkshopError):
        workshop.config(root, "nobody")
    assert workshop.config(root, core=True)["save_dir"].endswith("engine/actions")


# ------------------------------------------------------------------------------------------------ the proof bodies

def test_proof_bodies_differ_as_named():
    root = proof.ensure(log=lambda *_: None)
    rig = {n: json.loads((root / n / "puppet" / "rig.json").read_text(encoding="utf-8")) for n in proof.names()}

    def bone(r, a, b):
        p, q = r["parts"][a]["joint"]["at"], r["parts"][b]["joint"]["parent_at"]
        return abs(q[1] - p[1])
    assert bone(rig["tall"], "thigh_l", "shin_l") > 1.25 * bone(rig["plain"], "thigh_l", "shin_l")
    assert bone(rig["short"], "thigh_l", "shin_l") < 0.75 * bone(rig["plain"], "thigh_l", "shin_l")
    shoulders = lambda r: r["parts"]["upper_arm_r"]["joint"]["parent_at"][0] - r["parts"]["upper_arm_l"]["joint"]["parent_at"][0]
    assert shoulders(rig["heavy"]) > 1.3 * shoulders(rig["plain"])
    assert rig["bighead"]["parts"]["head"]["box"][3] > 1.5 * rig["plain"]["parts"]["head"]["box"][3]
    assert rig["skirt_floor"]["rig"].startswith("humanoid-a-skirt-floor")


# ------------------------------------------------------------------------------------------------ the engine

def _godot(args: list[str], timeout: float = 300, env: dict | None = None) -> str:
    engine.ensure_imported()
    p = subprocess.run([engine.godot(), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env={**os.environ, **(env or {})})
    return p.stdout + p.stderr


@needs_godot
def test_the_clean_switch_leaves_nothing_of_the_action_before():
    hero = (proof.ensure(["plain"], log=lambda *_: None) / "plain" / "puppet").as_posix()
    base = ["--headless", "--path", str(engine_dir()), "--script", "res://tools/switch_check.gd", "--", f"--hero={hero}"]
    res = json.loads(next(x for x in _godot(base).splitlines() if x.startswith("SWITCH "))[7:])
    assert res["runs"] >= 10 and res["bad"] == []
    old = json.loads(next(x for x in _godot(base + ["--layered"]).splitlines() if x.startswith("SWITCH "))[7:])
    assert old["bad"], "the check must catch actions layered the old way"


@needs_godot
def test_a_world_action_is_checked_on_the_proof_bodies(tmp_path):
    root = _world(tmp_path)
    act = workshop.from_poses([{"pose": _pose(arm_r={"at": [0.3, -0.95]}), "time": 0.7}], "hand_up", base=REST)
    (root / "actions").mkdir()
    (root / "actions" / "hand_up.json").write_text(json.dumps(act), encoding="utf-8")
    res = actionkit.check("hand_up", root, use_proof=True, log=lambda *_: None)
    assert res["where"] == "world" and res["passed"], actionkit.table(res)
    assert {k for k in res["heroes"]} == {"proof:" + n for n in proof.names()}
    assert actionkit.check_state(actionkit.find("hand_up", root))[0] == "passed"
    assert not any(i.code.startswith("action_") for i in check.check_world(root))


@needs_godot
def test_the_window_keeps_a_pose_and_gives_it_back(tmp_path):
    """Pull the right hand, fix the pose, go back to rest, pick the pose from the list: the hand is where it was
    (pose -> file -> reading gives the same pose); and the pose written is in the action's measures."""
    root = _world(tmp_path)
    cfg = workshop.config(root, "archivist", with_proof=False)
    d = workshop.state_dir(root)
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    a, b = (tmp_path / "a.json").as_posix(), (tmp_path / "b.json").as_posix()
    seq = f"still@5,tab:1@20,drag:hand_r:480:520@40,where:{a}@200,fix@210,rest@220,select:1@240,where:{b}@440,quit@450"
    cmd = workshop.command(d / "config.json")
    cmd[cmd.index("--position") + 1] = "6000,0"
    out = _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": seq})
    assert Path(a).exists() and Path(b).exists(), out[-2000:]
    pa, pb = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    # (the idle life is off: "still"; against the body all the same)
    rel = lambda p: [p["hand_r"][i] - p["body"][i] for i in range(2)]
    gap = max(abs(rel(pa)[i] - rel(pb)[i]) for i in range(2))
    assert gap < 6.0, (rel(pa), rel(pb))           # (the arm's springs settle within a few px of ~200)
    assert abs(pa["hand_r"][0] - 480) < 30 and abs(pa["hand_r"][1] - 520) < 30
    poses, rest = workshop.read_poses(root)
    assert len(poses) == 1 and rest is not None
    at = poses[0]["pose"]["arm_r"]["at"]
    assert at[0] > 0 and -1.0 <= at[1] <= 1.0
    st = workshop.read_state(root)
    assert st["hero"] == "archivist" and st["poses"] == 1
