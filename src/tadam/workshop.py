"""THE WORKSHOP (`tadam workshop`): the engine's window engine/workshop.tscn on this world's heroes and the proof
bodies, and its talk with Claude through files in <world>/.tadam/workshop/:

    state.json   what is chosen now (hero, action, the pose in the action's measures, how many poses are fixed)
    poses.json   the poses fixed in this session, each with its way in (time, ease, hold)
    cmd.json     a request to the open window: {"n": <number>, "do": "fix" | "pose" | "play", ...}

`tadam workshop pose` prints the pose of the moment (state.json); `--fix` asks the window to keep it ("fix this
one") and waits until it has. `tadam action from-poses <id>` turns poses.json into a draft action.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from tadam import engine, proof
from tadam.jsonfile import write_json
from tadam.paths import engine_dir
from tadam.world import World, read_json

WINDOW = (1110, 960)        # the window (the stage 720 and the panel 740 wide, shown at 3/4)
HAND_PACE = 1.6             # arm lengths a second (engine/workshop.gd HAND_PACE)
EASES = ("inout", "out", "in", "linear")


class WorkshopError(RuntimeError):
    pass


def state_dir(root: Path | str) -> Path:
    return World(root).work_dir() / "workshop"


def _heroes_of(root: Path | str) -> list[dict]:
    heroes = []
    w = World(root)
    for s in w.heroes():
            pdir = w.puppet_dir(s)
            if not (pdir / "rig.json").is_file():
                continue
            try:
                hj = w.hero_json(s)
            except Exception:           # (a hero.json the check complains about: the workshop still shows it)
                hj = {}
            h = hj.get("height")
            name = hj.get("name")
            title = (name.get("ru") or name.get("en")) if isinstance(name, dict) else (name or s)
            heroes.append({"id": s, "title": str(title), "dir": pdir.resolve().as_posix(),
                           "height": float(h) if isinstance(h, (int, float)) else 0.42,
                           "checks": (pdir / "actions.json").resolve().as_posix(),
                           "ready": readiness(pdir)})
    return heroes


def readiness(pdir: Path | str) -> dict:
    """How complete a hero is, for a person: the steps a hero goes through (drawn and cut, the face oval, the
    movement check) and how many of the engine's actions it plays cleanly. {"percent", "items": [{title, ok, say}]}."""
    from tadam import actions as table
    pdir = Path(pdir)
    items = []
    rep, _ = read_json(pdir / "report.json")
    rep = rep if isinstance(rep, dict) else {}
    ok_parts, all_parts = rep.get("parts_ok", 0), rep.get("parts_total", 15)
    drawn = bool(rep.get("passed")) and ok_parts == all_parts
    items.append({"title": "Нарисован и разрезан", "ok": drawn,
                  "say": f"все {all_parts} частей на месте" if drawn else
                         f"частей в порядке: {ok_parts} из {all_parts}" if rep else "нет отчёта о сборке"})
    rig, _ = read_json(pdir / "rig.json")
    board = ((rig or {}).get("parts", {}).get("head", {}) if isinstance(rig, dict) else {}).get("board")
    items.append({"title": "Окно для лица", "ok": bool(board),
                  "say": "есть: сюда встанет записанное лицо" if board else "нет: лицо записи некуда поставить"})
    st, data = table.state(pdir)
    acts = (data or {}).get("actions", {}) if isinstance(data, dict) else {}
    s1 = (data or {}).get("stage1", []) if isinstance(data, dict) else []
    bad1 = (data or {}).get("stage1_failed", []) if isinstance(data, dict) else []
    items.append({"title": "Проверка движений", "ok": st == "passed",
                  "say": {"passed": f"пройдена: обязательных {len(s1) - len(bad1)} из {len(s1)}",
                          "failed": f"не пройдена: {', '.join(bad1)}",
                          "stale": "устарела: герой менялся после проверки (tadam hero check)",
                          "missing": "ещё не было (tadam hero check)"}[st]})
    good = sum(1 for a in acts.values() if a.get("pass"))
    total = len(acts)
    items.append({"title": "Чисто играет действий", "ok": total > 0 and good == total,
                  "say": f"{good} из {total}" if total else "неизвестно до проверки"})
    share = (good / total) if total else 0.0
    percent = round(100 * (sum(1 for i in items[:3] if i["ok"]) + share) / 4)
    return {"percent": percent, "items": items,
            "bad": sorted(k for k, a in acts.items() if not a.get("pass"))}


def world_title(root: Path | str) -> str:
    data, _ = read_json(Path(root) / "world.json")
    t = data.get("title") if isinstance(data, dict) else None
    if isinstance(t, dict):
        return str(t.get("ru") or t.get("en") or Path(root).name)
    return str(t or Path(root).name)


def recent_file() -> Path:
    return engine_dir().parent / "out" / "workshop" / "recent.json"


def known_worlds(current: Path | str | None) -> list[Path]:
    """The rubrics the window can switch between: this one, the world folders beside it, the ones opened lately,
    and the kit's own sample world. Each keeps its own heroes, actions and poses."""
    found: list[Path] = []

    def add(p: Path) -> None:
        p = Path(p).resolve()
        if (p / "world.json").is_file() and p not in found:
            found.append(p)
    if current is not None:
        add(Path(current))
        parent = Path(current).resolve().parent
        for d in sorted(parent.iterdir()) if parent.is_dir() else []:
            if d.is_dir() and not d.name.startswith("."):
                add(d)
    rec, _ = read_json(recent_file())
    for r in rec if isinstance(rec, list) else []:
        if isinstance(r, str):
            add(Path(r))
    ex = engine_dir().parent / "examples"
    for d in sorted(ex.iterdir()) if ex.is_dir() else []:
        if d.is_dir():
            add(d)
    return found


def remember(root: Path | str) -> None:
    rec, _ = read_json(recent_file())
    rec = [r for r in (rec if isinstance(rec, list) else []) if isinstance(r, str)]
    me = Path(root).resolve().as_posix()
    rec = [me] + [r for r in rec if r != me]
    write_json(recent_file(), rec[:12], indent=1)


def world_entry(root: Path | str, core: bool = False) -> dict:
    root = Path(root).resolve()
    acts = (root / "actions").as_posix()
    return {"root": root.as_posix(), "title": world_title(root), "heroes": _heroes_of(root),
            "state_dir": state_dir(root).resolve().as_posix(), "actions_dir": acts,
            "save_dir": (engine_dir() / "actions").resolve().as_posix() if core else acts}


def config(root: Path | str | None, hero: str | None = None, core: bool = False, with_proof: bool = True) -> dict:
    heroes = _heroes_of(root) if root is not None else []
    bodies = []
    if with_proof or not heroes:
        broot = proof.ensure(log=lambda *_: None)
        for n in proof.names():
            bodies.append({"id": "proof:" + n, "title": "проба: " + proof.TITLES.get(n, n),
                           "dir": (broot / n / "puppet").resolve().as_posix(), "height": 0.4})
    ids = [h["id"] for h in heroes + bodies]
    if hero and hero not in ids and "proof:" + hero in ids:
        hero = "proof:" + hero
    if hero and hero not in ids:
        raise WorkshopError(f"no hero {hero!r} with a puppet here (heroes: {', '.join(h['id'] for h in heroes) or 'none'})")
    cfg = {"lang": "ru", "hero": hero or (ids[0] if ids else ""), "heroes": heroes, "proof": bodies, "core": core}
    if root is not None:
        cfg["state_dir"] = state_dir(root).resolve().as_posix()
        cfg["actions_dir"] = (Path(root) / "actions").resolve().as_posix()
        cfg["save_dir"] = cfg["actions_dir"]
    if core:
        cfg["save_dir"] = (engine_dir() / "actions").resolve().as_posix()
    cfg["world"] = Path(root).resolve().as_posix() if root is not None else ""
    cfg["world_title"] = world_title(root) if root is not None else ""
    cfg["worlds"] = [world_entry(r, core) for r in known_worlds(root)]
    return cfg


def command(cfg_file: Path, window: tuple[int, int] = WINDOW) -> list[str]:
    return [engine.godot(), "--path", str(engine_dir()), "--resolution", f"{window[0]}x{window[1]}",
            "--position", "60,30", "res://workshop.tscn", "--", f"--config={Path(cfg_file).as_posix()}"]


def open_window(root: Path | str | None, hero: str | None = None, core: bool = False, wait: bool = False):
    engine.ensure_imported()
    cfg = config(root, hero, core)
    if root is not None:
        remember(root)
    base = state_dir(root) if root is not None else engine_dir().parent / "out" / "workshop"
    base.mkdir(parents=True, exist_ok=True)
    f = base / "config.json"
    write_json(f, cfg, indent=1)
    cmd = command(f)
    if wait:
        return subprocess.run(cmd)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def read_state(root: Path | str) -> dict:
    st, err = read_json(state_dir(root) / "state.json")
    if not isinstance(st, dict):
        raise WorkshopError("no open workshop here (no .tadam/workshop/state.json): `tadam workshop` first")
    return st


def ask(root: Path | str, do: str, wait: float = 6.0, **more) -> dict:
    """Send a request to the open window and wait until it says it has seen it (state.json cmd_seen)."""
    d = state_dir(root)
    old, _ = read_json(d / "cmd.json")
    st0 = read_state(root)
    n = max((int(old.get("n", 0)) if isinstance(old, dict) else 0), int(st0.get("cmd_seen", 0))) + 1
    write_json(d / "cmd.json", {"n": n, "do": do, **more}, indent=1)
    end = time.monotonic() + wait
    while time.monotonic() < end:
        st, _ = read_json(d / "state.json")
        if isinstance(st, dict) and int(st.get("cmd_seen", 0)) >= n:
            return st
        time.sleep(0.15)
    raise WorkshopError("the workshop window did not answer: is it open (and on the «Позы» tab for a fix)?")


# ------------------------------------------------------------------------------------------------ from poses

def _v(a) -> tuple[float, float]:
    return (float(a[0]), float(a[1])) if isinstance(a, (list, tuple)) and len(a) == 2 else (0.0, 0.0)


def _dist(a, b) -> float:
    (x0, y0), (x1, y1) = _v(a), _v(b)
    return ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5


def _num(x) -> float:
    return float(x) if isinstance(x, (int, float)) else 0.0


def way_time(a: dict, b: dict) -> float:
    """The time from pose a to pose b: the longest way at HAND_PACE (engine/workshop.gd way_time, the same)."""
    far = 0.0
    for ch in ("arm_l", "arm_r"):
        if isinstance(a.get(ch), dict) and isinstance(b.get(ch), dict):
            far = max(far, _dist(a[ch].get("at", [0, 0]), b[ch].get("at", [0, 0])))
    la, lb = a.get("legs"), b.get("legs")
    if isinstance(la, dict) and isinstance(lb, dict):
        far = max(far, 1.5 * abs(_num(la.get("drop", 0)) - _num(lb.get("drop", 0))))
        for f in ("foot_l", "foot_r"):
            far = max(far, 1.5 * _dist(la.get(f, [0, 0]), lb.get(f, [0, 0])))
    ba, bb = a.get("body"), b.get("body")
    if isinstance(ba, dict) and isinstance(bb, dict):
        far = max(far, abs(_num(ba.get("lean", 0)) - _num(bb.get("lean", 0))) / 40.0)
    far = max(far, abs(_num(a.get("head", 0)) - _num(b.get("head", 0))) / 50.0)
    return round(round(min(max(far / HAND_PACE + 0.15, 0.25), 2.0) / 0.05) * 0.05, 2)


def from_poses(poses: list[dict], aid: str, title: str | None = None, group: str = "gesture",
               keep_times: bool = True, base: dict | None = None) -> dict:
    """A draft action from the poses (in order): a phase a pose with only what changed from the pose before, its
    time (the pose's own, or by the length of the way), then back to rest. Claude refines it afterwards.
    `base`: the rest pose the first one starts from (the window's rest pose; without it everything of the first
    pose counts as changed)."""
    if not poses:
        raise WorkshopError("no poses: fix some in the workshop first («Фикс» or `tadam workshop pose --fix`)")
    phases, used = [], []
    prev: dict = base or {}
    for p in poses:
        pose = p.get("pose") or {}
        t = float(p["time"]) if keep_times and p.get("time") else way_time(prev or pose, pose)
        ph: dict = {"time": round(t, 2)}
        if p.get("ease", "inout") in EASES and p.get("ease", "inout") != "inout":
            ph["ease"] = p["ease"]
        if p.get("hold"):
            ph["loop"] = True
        for ch in ("legs", "body", "head", "arm_l", "arm_r"):
            if ch in pose and json.dumps(pose[ch], sort_keys=True) != json.dumps(prev.get(ch), sort_keys=True):
                ph[ch] = pose[ch]
                if ch not in used:
                    used.append(ch)
        phases.append(ph)
        prev = pose
    phases.append({"name": "return", "time": 0.45, **{ch: "rest" for ch in used}})
    return {"id": aid, "title": title or aid, "group": group, "params": {"side": "right"}, "phases": phases}


def read_poses(root: Path | str) -> tuple[list[dict], dict | None]:
    """The poses fixed in the window, and the rest pose they start from."""
    d, _ = read_json(state_dir(root) / "poses.json")
    if not isinstance(d, dict):
        return [], None
    return d.get("poses", []), d.get("rest") if isinstance(d.get("rest"), dict) else None
