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
    """Runs the engine; on a hang it closes the whole tree (the console wrapper AND the window it started),
    never leaving an off-screen window behind."""
    engine.ensure_imported()
    p = subprocess.Popen([engine.godot(), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", env={**os.environ, **(env or {})})
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        p.kill()
        out, err = p.communicate()
        raise AssertionError(f"the engine hung ({timeout} s) and was closed:\n{(out + err)[-2000:]}")
    return out + err


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
    arm = poses[0]["pose"]["arm_r"]              # (kept in angles since 26.11: the same on any body)
    assert -180 <= arm["raise"] <= 180 and -180 <= arm["elbow"] <= 180 and "at" not in arm
    st = workshop.read_state(root)
    assert st["hero"] == "archivist" and st["poses"] == 1


def test_the_wrist_dot_turns_the_hand_and_the_pose_keeps_it(tmp_path):
    """A small dot at the fingertips turns the hand in the wrist (a beckoning hand bends, not only the forearm); the
    turn is kept in the pose as "wrist" and the hand is drawn turned."""
    root = _world(tmp_path)
    cfg = workshop.config(root, "archivist", with_proof=False)
    d = workshop.state_dir(root)
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    a, b, h = (tmp_path / "a.json").as_posix(), (tmp_path / "b.json").as_posix(), (tmp_path / "h.json").as_posix()
    seq = (f"still@5,tab:1@20,drag:hand_r:480:520@40,dot:turn_r:{a}@120,dot:hand_r:{h}@120,drag:turn_r:620:440@130,"
           f"dot:turn_r:{b}@220,fix@230,quit@240")
    cmd = workshop.command(d / "config.json")
    cmd[cmd.index("--position") + 1] = "6000,0"
    out = _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": seq})
    assert Path(a).exists() and Path(b).exists(), out[-2000:]
    ta, tb, hand = json.loads(Path(a).read_text()), json.loads(Path(b).read_text()), json.loads(Path(h).read_text())
    assert ((ta[0] - tb[0]) ** 2 + (ta[1] - tb[1]) ** 2) ** 0.5 > 8, (ta, tb)      # the fingertips went round
    poses, _ = workshop.read_poses(root)
    arm = poses[0]["pose"]["arm_r"]
    assert abs(arm.get("wrist", 0)) >= 10 and abs(arm["wrist"]) <= 80, arm
    assert "raise" in arm and "elbow" in arm                                     # (the arm itself stays in angles)


def test_the_window_lists_the_rubrics_and_never_mixes_them(tmp_path):
    root = _world(tmp_path)
    twin = tmp_path / "twin"
    shutil.copytree(EXAMPLE, twin, ignore=shutil.ignore_patterns(".tadam"))
    cfg = workshop.config(root, with_proof=False)
    roots = [w["root"] for w in cfg["worlds"]]
    assert roots[0] == root.resolve().as_posix() and twin.resolve().as_posix() in roots
    assert cfg["world_title"] and cfg["world"] == roots[0]
    for w in cfg["worlds"]:          # each rubric its own heroes, actions and poses
        assert w["state_dir"].startswith(w["root"]) and w["actions_dir"].startswith(w["root"])
        assert all(h["dir"].startswith(w["root"]) for h in w["heroes"])


@needs_godot
def test_the_dots_follow_the_real_mouse(tmp_path):
    """A press on the hand's dot, a drag and a release as real mouse events (through the stage's own layers,
    which once ate every click): the hand goes up."""
    root = _world(tmp_path)
    cfg = workshop.config(root, "archivist", with_proof=False)
    d = workshop.state_dir(root)
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    cmd = workshop.command(d / "config.json", window=(1480, 1280))
    cmd[cmd.index("--position") + 1] = "6000,0"
    before = (tmp_path / "before.json").as_posix()
    _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": f"still@5,tab:1@20,dot:hand_r:{before}@60,quit@62"})
    x, y = json.loads(Path(before).read_text())
    after = (tmp_path / "after.json").as_posix()
    seq = (f"still@5,tab:1@20,press:{x:.0f}:{y:.0f}@60,move:{x + 10:.0f}:{y - 120:.0f}@64,"
           f"move:{x + 30:.0f}:{y - 300:.0f}@68,release:{x + 30:.0f}:{y - 300:.0f}@72,dot:hand_r:{after}@150,quit@152")
    _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": seq})
    ax, ay = json.loads(Path(after).read_text())
    assert ay < y - 150, ((x, y), (ax, ay))


@needs_godot
def test_the_hand_buttons_replay_the_action_at_once(tmp_path):
    """«Рука: Левая» while «помахать» plays: the wave goes to the other hand right away, with no new press."""
    root = _world(tmp_path)
    cfg = workshop.config(root, "archivist", with_proof=False)
    d = workshop.state_dir(root)
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    cmd = workshop.command(d / "config.json")
    cmd[cmd.index("--position") + 1] = "6000,0"
    a, b = (tmp_path / "a.json").as_posix(), (tmp_path / "b.json").as_posix()
    seq = f"still@5,play:wave@20,where:{a}@120,side:left@130,where:{b}@260,elbow:in@262,play:clap@266,state@270,quit@272"
    out = _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": seq})
    assert Path(a).exists() and Path(b).exists(), out[-2000:]
    pa, pb = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    up = lambda p, h: p["body"][1] - p[h][1]          # (how high the hand is over the pelvis)
    assert up(pa, "hand_r") > up(pa, "hand_l") + 60, pa
    assert up(pb, "hand_l") > up(pb, "hand_r") + 60, pb
    st = workshop.read_state(root)
    # a forced elbow belongs to the action it was chosen for: the next action starts with «Сам»
    assert st["action"] == "clap" and st["side"] == "left" and st["elbow"] == ""


def test_a_hero_says_how_complete_it_is(tmp_path):
    """The window's readiness bar: drawn and cut, the face oval, the movement check, the share of clean actions."""
    root = _world(tmp_path)
    h = workshop.config(root, with_proof=False)["heroes"][0]
    r = h["ready"]
    assert 0 <= r["percent"] <= 100 and len(r["items"]) == 4
    assert all(set(i) == {"title", "ok", "say"} and i["say"] for i in r["items"])
    assert isinstance(r["bad"], list)


@needs_godot
def test_an_arm_said_in_angles_is_drawn_at_those_angles():
    """«raise», «elbow» in an action: the drawn arm has those angles (ten poses, both arms) on bodies of very
    different build: what is written is what is seen, and the same on every body."""
    dirs = proof.ensure(["plain", "heavy", "short"], log=lambda *_: None)
    for name in ("plain", "heavy", "short"):
        hero = (dirs / name / "puppet").as_posix()
        out = _godot(["--headless", "--path", str(engine_dir()), "--script", "res://tools/angle_check.gd", "--", f"--hero={hero}"])
        res = json.loads(next(x for x in out.splitlines() if x.startswith("ANGLES "))[7:])
        assert len(res["rows"]) == 20 and res["worst"] <= 3.0, (name, res["worst"])


@needs_godot
def test_a_pose_made_by_hand_is_kept_in_angles(tmp_path):
    """A hand pulled by its dot and the pose kept: the kept pose says the arm in angles (raise, elbow), plays back
    to the same place, and its draft action carries the angles."""
    root = _world(tmp_path)
    cfg = workshop.config(root, "archivist", with_proof=False)
    d = workshop.state_dir(root)
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    a, b = (tmp_path / "a.json").as_posix(), (tmp_path / "b.json").as_posix()
    seq = f"still@5,tab:1@20,drag:hand_r:520:480@40,where:{a}@200,fix@210,rest@220,select:1@240,where:{b}@440,quit@450"
    cmd = workshop.command(d / "config.json")
    cmd[cmd.index("--position") + 1] = "6000,0"
    _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": seq})
    poses, rest = workshop.read_poses(root)
    arm = poses[0]["pose"]["arm_r"]
    assert "raise" in arm and "elbow" in arm and "at" not in arm, arm
    pa, pb = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    rel = lambda p: [p["hand_r"][i] - p["body"][i] for i in range(2)]
    assert max(abs(rel(pa)[i] - rel(pb)[i]) for i in range(2)) < 8.0, (rel(pa), rel(pb))
    act = workshop.from_poses(poses, "angled", base=rest)
    assert "raise" in act["phases"][0]["arm_r"]


@needs_godot
def test_a_pose_and_the_log_are_copied_for_the_assistant(tmp_path):
    """«⧉» on a pose: the clipboard says the rubric, the hero, the pose in words and numbers and where its picture
    is (and the picture is there); «весь журнал»: what was played, with its settings, and where the log file is."""
    root = _world(tmp_path)
    cfg = workshop.config(root, "archivist", with_proof=False)
    d = workshop.state_dir(root)
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    one, logc = (tmp_path / "one.txt").as_posix(), (tmp_path / "log.txt").as_posix()
    seq = (f"still@5,play:wave@20,tab:1@100,drag:hand_r:480:520@120,fix@180,copy:1@190,clip:{one}@300,"
           f"log:0@310,clip:{logc}@320,quit@322")
    cmd = workshop.command(d / "config.json")
    cmd[cmd.index("--position") + 1] = "6000,0"
    _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": seq})
    text = Path(one).read_text(encoding="utf-8")
    assert "Поза 1 из 1" in text and "raise" in text and "archivist" in text, text
    pic = next(l.split(": ", 1)[1] for l in text.splitlines() if l.startswith("Картинка"))
    assert Path(pic).is_file()
    log = Path(logc).read_text(encoding="utf-8")
    assert "«" in log and "wave" in log and "log.jsonl" in log, log
    assert (d / "log.jsonl").is_file()


@needs_godot
def test_a_pose_for_two_is_set_fixed_and_saved_as_a_pair(tmp_path):
    """«Пара»: two heroes side by side, the dots on the one picked («Правлю позу»), one «Запомнить» keeps both
    poses; «Сохранить» writes the lead (<id>, with "pair") and the partner (<id>_b, mirrored, "partner_only"),
    and played from the list the partner's hand goes where it was set."""
    root = _world(tmp_path)
    cfg = workshop.config(root, "archivist", with_proof=False)
    d = workshop.state_dir(root)
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    cmd = workshop.command(d / "config.json")
    cmd[cmd.index("--position") + 1] = "6000,0"
    a0, b0 = (tmp_path / "a0.json").as_posix(), (tmp_path / "b0.json").as_posix()
    out = _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": f"still@5,row:pair@8,tab:1@30,where:{a0}@60,edit:1@62,where:{b0}@64,quit@66"})
    assert Path(a0).exists() and Path(b0).exists(), out[-2000:]
    pa, pb = json.loads(Path(a0).read_text()), json.loads(Path(b0).read_text())
    assert pb["body"][0] > pa["body"][0] + 60                # (side by side: the partner on the right)
    meet = [(pa["hand_r"][0] + pb["hand_l"][0]) / 2, (pa["body"][1] + pb["body"][1]) / 2 - 40]
    a1, b1 = (tmp_path / "a1.json").as_posix(), (tmp_path / "b1.json").as_posix()
    shot = (tmp_path / "pair.png").as_posix()
    seq = (f"still@5,row:pair@8,tab:1@30,edit:0@40,drag:hand_r:{meet[0] - 8:.0f}:{meet[1]:.0f}@50,"
           f"edit:1@90,drag:hand_l:{meet[0] + 8:.0f}:{meet[1]:.0f}@100,fix@200,save:shake_two@210,"
           f"tab:0@230,play:shake_two@240,edit:0@372,where:{a1}@373,edit:1@374,where:{b1}@375,shot:{shot}@376,stand:1:600@390,state@430,quit@432")
    out = _godot(cmd[1:], timeout=180, env={"WORKSHOP_SEQ": seq})
    poses, _ = workshop.read_poses(root)
    assert len(poses) == 1 and "partner" in poses[0], out[-2000:]
    assert poses[0]["pose"]["arm_r"]["raise"] > 30 and poses[0]["partner"]["arm_l"]["raise"] > 30
    lead = json.loads((root / "actions" / "shake_two.json").read_text(encoding="utf-8"))
    half = json.loads((root / "actions" / "shake_two_b.json").read_text(encoding="utf-8"))
    assert lead["group"] == "two" and lead["pair"]["partner"] == "shake_two_b"
    assert half["partner_only"] and "arm_r" in half["phases"][0]     # (mirrored: its near hand is written as the right)
    # played as a pair: both near hands came up to where they were set, and met
    qa, qb = json.loads(Path(a1).read_text()), json.loads(Path(b1).read_text())
    assert abs(qa["hand_r"][1] - meet[1]) < 30 and abs(qb["hand_l"][1] - meet[1]) < 30, (meet, qa, qb)
    assert qa["hand_r"][0] < qb["hand_l"][0] + 10 and abs(qa["hand_r"][0] - qb["hand_l"][0]) < 40, (qa, qb)
    st = workshop.read_state(root)
    assert st["row"] == "pair" and st["partner"] == "visitor"
    assert "расстояние" in (d / "log.jsonl").read_text(encoding="utf-8")       # (the ⇆ dragged: the right one moved)


@needs_godot
def test_a_wheel_steered_by_many_never_throws_a_hand_off(tmp_path):
    """The proof bodies all at a wheel: its rim turned up to a shoulder sent the wrist back through the shoulder,
    and the hand flew round the outside to the edge of the stage and jumped back. No hand moves far in a frame."""
    root = _world(tmp_path)
    cfg = workshop.config(root, "archivist", with_proof=True)
    d = workshop.state_dir(root)
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    cmd = workshop.command(d / "config.json", window=(1480, 1280))
    cmd[cmd.index("--position") + 1] = "6000,0"
    track = (tmp_path / "track.jsonl").as_posix()
    _godot(cmd[1:], timeout=240, env={"WORKSHOP_SEQ": f"still@5,row:proof@8,play:drive@20,track:{track}@10,quit@420"})
    rows = [json.loads(line) for line in Path(track).read_text().splitlines() if line.strip()]
    assert len(rows) > 300
    worst = (0.0, None)
    for a, b in zip(rows, rows[1:]):
        for k in a:
            if k.endswith((".hand_l", ".hand_r")) and k in b:
                dd = ((a[k][0] - b[k][0]) ** 2 + (a[k][1] - b[k][1]) ** 2) ** 0.5
                worst = max(worst, (dd, (b["f"], k)), key=lambda w: w[0])
    assert worst[0] < 40, worst


@needs_godot
def test_the_elbow_is_set_by_hand_and_stays_where_it_was_put(tmp_path):
    """The elbow dot bends the arm the other way with the hand left where it is; the hand dragged on after that,
    fast, keeps the elbow on the side it was put (it never flips over by itself)."""
    root = _world(tmp_path)
    cfg = workshop.config(root, "archivist", with_proof=False)
    d = workshop.state_dir(root)
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    cmd = workshop.command(d / "config.json")
    cmd[cmd.index("--position") + 1] = "6000,0"
    w0 = (tmp_path / "w0.json").as_posix()
    _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": f"still@5,tab:1@20,where:{w0}@40,quit@42"})
    p0 = json.loads(Path(w0).read_text())
    sx, sy = p0["shoulder_r"]
    bx, by = p0["body"]
    w1, w2, w3 = ((tmp_path / f"w{i}.json").as_posix() for i in (1, 2, 3))
    hand = (bx + 10, sy + 60)                     # across the chest
    first = f"still@5,tab:1@20,drag:hand_r:{hand[0]:.0f}:{hand[1]:.0f}@40,where:{w1}@90,"
    _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": first + "quit@92"})
    q1 = json.loads(Path(w1).read_text())
    # the elbow pulled to its mirror over the line from the shoulder to the hand
    sh, hd, el = q1["shoulder_r"], q1["hand_r"], q1["elbow_r"]
    ux, uy = hd[0] - sh[0], hd[1] - sh[1]
    n = (ux * ux + uy * uy) ** 0.5
    ux, uy = ux / n, uy / n
    t = (el[0] - sh[0]) * ux + (el[1] - sh[1]) * uy
    fx, fy = sh[0] + t * ux, sh[1] + t * uy
    mirror = (2 * fx - el[0], 2 * fy - el[1])
    seq = first + f"drag:elbow_r:{mirror[0]:.0f}:{mirror[1]:.0f}@100,where:{w2}@150,"
    path = [(sx + 40 + 5 * i, sy - 20 - 9 * i) for i in range(12)]     # then up and out (in reach), a step a frame
    seq += "".join(f"drag:hand_r:{x:.0f}:{y:.0f}@{160 + i}," for i, (x, y) in enumerate(path))
    seq += f"where:{w3}@220,state@220,quit@222"
    _godot(cmd[1:], timeout=120, env={"WORKSHOP_SEQ": seq})
    q2, q3 = (json.loads(Path(w).read_text()) for w in (w2, w3))
    side = lambda q: (q["hand_r"][0] - q["shoulder_r"][0]) * (q["elbow_r"][1] - q["shoulder_r"][1]) \
        - (q["hand_r"][1] - q["shoulder_r"][1]) * (q["elbow_r"][0] - q["shoulder_r"][0])
    assert side(q1) * side(q2) < 0, (q1, q2)                  # the elbow went over to the other side
    # (the hand turns with the forearm: its middle moves by about the hand's size, the wrist stays)
    assert abs(q2["hand_r"][0] - q1["hand_r"][0]) < 45 and abs(q2["hand_r"][1] - q1["hand_r"][1]) < 45
    assert side(q3) * side(q2) > 0, (q2, q3)                  # and stayed there as the hand went on
    assert abs(q3["hand_r"][0] - path[-1][0]) < 30 and abs(q3["hand_r"][1] - path[-1][1]) < 30
    arm = workshop.read_state(root)["pose"]["arm_r"]
    assert "raise" in arm and "elbow" in arm and "at" not in arm
