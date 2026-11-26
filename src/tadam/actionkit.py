"""THE ACTIONS: the core's library (engine/actions) and this world's own (actions/ in the world folder), for
`tadam action list / show / new / check / sheet / from-poses` and the workshop (docs: skill/reference/mechanics.md).

An action is the core's, not a hero's: the same file moves every hero (every number is in the hero's own measures).
A world's own action plays on every hero of that world; it may not take a name of the library (`tadam check`:
action_name_taken) - the library always wins in the engine.

`check`: the engine plays the action on the world's heroes and/or the PROOF BODIES (tadam.proof: tall, short, heavy,
big-headed, four skirts) and measures it (engine/tools/action_check.gd: a joint on the wrong side, a sliding foot, a
hand in the body or under the floor, a jerk, not back at rest ...). A world action's result is kept beside it as
actions/<id>.check.json with the fingerprint of the file, so `tadam check` knows when it is stale.
`sheet`: the same run with pictures: a PNG, one row per hero, N frames through the action - Claude's eyes.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from tadam import engine, proof
from tadam.engine import EngineError
from tadam.jsonfile import lf, write_json
from tadam.paths import engine_dir
from tadam.world import World, read_json

ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
GROUPS = ("pose", "gesture", "body", "move", "feeling", "dance", "item", "fight", "silly", "music", "two")
GROUP_TITLES = {"pose": "позы", "gesture": "жесты", "body": "тело", "move": "перемещение", "feeling": "чувства",
                "dance": "танцы", "item": "предметы", "fight": "драка", "silly": "дурачества", "music": "музыка",
                "two": "вдвоём"}
MAX_BYTES = 16384          # the contracts' ACTION_MAX_BYTES
CHECK_SUFFIX = ".check.json"


class ActionError(RuntimeError):
    pass


@dataclass
class Entry:
    id: str
    data: dict
    path: Path
    where: str             # "core" | "world"

    @property
    def title(self) -> str:
        t = self.data.get("title", self.id)
        return str(t.get("ru") or t.get("en") or self.id) if isinstance(t, dict) else str(t)


def core_dir() -> Path:
    return engine_dir() / "actions"


def world_dir(root: Path | str) -> Path:
    return Path(root) / "actions"


def _read_dir(d: Path, where: str) -> dict[str, Entry]:
    out: dict[str, Entry] = {}
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        if f.name.endswith(CHECK_SUFFIX):
            continue
        data, err = read_json(f)
        if isinstance(data, dict):
            out[f.stem] = Entry(f.stem, data, f, where)
    return out


def library(root: Path | str | None = None) -> dict[str, Entry]:
    """Every action the engine plays here: the core's, then the world's that do not take a core name."""
    out = _read_dir(core_dir(), "core")
    if root is not None:
        for k, e in _read_dir(world_dir(root), "world").items():
            out.setdefault(k, e)
    return out


def find(aid: str, root: Path | str | None = None) -> Entry:
    lib = library(root)
    if aid not in lib:
        near = [k for k in lib if aid in k or k in aid][:6]
        raise ActionError(f"no action {aid!r}" + (f" (perhaps: {', '.join(near)})" if near else "")
                          + ": `tadam action list` shows them all")
    return lib[aid]


def file_sha(path: Path) -> str:
    return hashlib.sha256(lf(Path(path).read_bytes())).hexdigest()


# ------------------------------------------------------------------------------------------------ list / show

def listing(root: Path | str | None) -> str:
    lib = library(root)
    lines = []
    by: dict[str, list[Entry]] = {}
    for e in lib.values():
        by.setdefault(str(e.data.get("group", "other")), []).append(e)
    for g in list(GROUPS) + sorted(k for k in by if k not in GROUPS):
        if g not in by:
            continue
        lines.append(f"{g} ({GROUP_TITLES.get(g, g)}):")
        for e in sorted(by[g], key=lambda x: x.id):
            mark = "  [world]" if e.where == "world" else ""
            view = f"  view {e.data['view']}" if e.data.get("view") else ""
            lines.append(f"  {e.id:<16} {e.title}{view}{mark}")
    own = sum(e.where == "world" for e in lib.values())
    lines.append(f"{len(lib)} actions ({len(lib) - own} of the core library" + (f", {own} of this world" if own else "") + ")")
    return "\n".join(lines)


def _val(v) -> str:
    if isinstance(v, dict) and "amp" in v:
        return f"swing {v.get('base', 0)}±{v['amp']} at {v.get('rate', 1)} Hz"
    return json.dumps(v, ensure_ascii=False)


def describe(e: Entry) -> str:
    """The action in words, phase by phase (the file itself follows in `tadam action show --json`)."""
    d = e.data
    lines = [f"{e.id}: {e.title}  [{d.get('group', '?')}, {'this world' if e.where == 'world' else 'core library'}]",
             f"file: {e.path}"]
    if d.get("params"):
        lines.append("params: " + ", ".join(f"{k}={v}" for k, v in d["params"].items()))
    for k in ("view", "two", "covers_face", "seated", "author"):
        if k in d:
            lines.append(f"{k}: {d[k]}")
    total = 0.0
    for i, ph in enumerate(d.get("phases") or []):
        t = float(ph.get("time", 0.5))
        total += t
        tags = [x for x in (ph.get("name"), "loop" if ph.get("loop") else None, ph.get("ease")) if x]
        lines.append(f"phase {i + 1}: {t:g} s" + (f" ({', '.join(tags)})" if tags else ""))
        for ch in ("legs", "body", "head", "arm_l", "arm_r", "arms"):
            if ch in ph:
                v = ph[ch]
                if isinstance(v, dict):
                    lines.append(f"   {ch:<6} " + "; ".join(f"{k} {_val(x)}" for k, x in v.items()))
                else:
                    lines.append(f"   {ch:<6} {_val(v)}")
    lines.append(f"about {total:g} s (a loop lasts its call's duration)")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ new

TEMPLATE_PHASES = [
    {"time": 0.4, "arm_r": {"at": [0.5, -0.5], "look": "palm"}, "head": 5},
    {"time": 1.0, "loop": True, "arm_r": {"wrist": {"base": 0, "amp": 20, "rate": 2.0}}},
    {"name": "return", "time": 0.45, "arm_r": "rest", "head": "rest"},
]


def new(root: Path | str, aid: str, title: str | None = None, group: str = "gesture", author: str | None = None) -> Path:
    if not ID.match(aid):
        raise ActionError("an action's name: latin small letters, digits and _, starting with a letter (up to 40)")
    if (core_dir() / f"{aid}.json").exists():
        raise ActionError(f"{aid!r} is an action of the core library: a world's own action needs another name")
    if group not in GROUPS:
        raise ActionError(f"group: one of {', '.join(GROUPS)}")
    f = world_dir(root) / f"{aid}.json"
    if f.exists():
        raise ActionError(f"actions/{aid}.json is there already")
    data = {"id": aid, "title": title or aid, "group": group, "params": {"side": "right"},
            "phases": TEMPLATE_PHASES}
    if author:
        data["author"] = author
    write_json(f, data, indent=1)
    return f


# ------------------------------------------------------------------------------------------------ the engine runs

def heroes_of(w: World) -> dict[str, Path]:
    """slug -> puppet folder, for the world's heroes that have a puppet."""
    return {s: w.puppet_dir(s) for s in w.heroes() if (w.puppet_dir(s) / "rig.json").is_file()}


def bodies(names: list[str] | None = None, log=print) -> dict[str, Path]:
    root = proof.ensure(names, log=log)
    return {n: root / n / "puppet" for n in (names or proof.names())}


def _run_engine(e: Entry, who: dict[str, Path], root: Path | str | None, shots: Path | None = None, frames: int = 6,
                timeout: float = 900) -> dict:
    """The engine's action check of one action on these puppets: {slug: [runs]} (and pictures into `shots`)."""
    if not who:
        raise ActionError("no hero to try it on: the world has no puppet yet (`tadam hero make`), or add --proof")
    engine.ensure_imported()
    tmp = Path(tempfile.mkdtemp(prefix="tadam-action-"))
    try:
        out = tmp / "runs.json"
        cmd = [engine.godot()]
        if shots is None:
            cmd.append("--headless")
        else:
            from tadam.render import OFF_SCREEN
            cmd += ["--position", OFF_SCREEN]
        cmd += ["--path", str(engine_dir()), "--script", "res://tools/action_check.gd", "--",
                "--heroes=" + ",".join(p.resolve().as_posix() for p in who.values()),
                f"--actions={e.id}", f"--out={out.as_posix()}"]
        if root is not None and world_dir(root).is_dir():
            cmd.append(f"--extra-actions={world_dir(root).resolve().as_posix()}")
        if shots is not None:
            cmd += [f"--shots={shots.as_posix()}", f"--frames={frames}"]
        p = engine._run(cmd, timeout)
        raw, err = read_json(out)
        if not isinstance(raw, dict):
            from tadam.actions import engine_tail
            raise EngineError("the engine did not finish the action check:\n" + engine_tail(p.stdout + p.stderr))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    by_dir = {p.resolve().as_posix().lower(): s for s, p in who.items()}
    res: dict[str, list] = {s: [] for s in who}
    for r in raw.get("runs") or []:
        slug = by_dir.get(str(r.get("hero", "")).replace("\\", "/").rstrip("/").lower())
        if slug is None:
            continue
        faults = [f for f in (r.get("faults") or []) if f != "out"]
        res[slug].append({"side": r.get("side", "right"), "pass": not faults,
                          "faults": {f: round(float(r.get(f, 0.0)), 4) for f in faults},
                          "seconds": round(float(r.get("seconds", 0.0)), 2), "shots": r.get("shots") or []})
    return {"limits": raw.get("limits") or {}, "heroes": res}


def check(aid: str, root: Path | str | None, heroes: list[str] | None = None, use_proof: bool = False,
          log=print) -> dict:
    """Play the action on the heroes and/or the proof bodies; a world action's result goes to actions/<id>.check.json."""
    e = find(aid, root)
    who: dict[str, Path] = {}
    w = World(root) if root is not None else None
    if w is not None and (heroes or not use_proof):
        all_h = heroes_of(w)
        for h in heroes or list(all_h):
            if h not in all_h:
                raise ActionError(f"heroes/{h} has no puppet")
            who[h] = all_h[h]
    if use_proof or w is None:
        for n, p in bodies(log=log).items():
            who["proof:" + n] = p
    started = time.monotonic()
    run = _run_engine(e, who, root)
    res = {"action": e.id, "where": e.where, "sha": file_sha(e.path), "limits": run["limits"],
           "seconds": round(time.monotonic() - started, 1), "heroes": {}}
    for slug, runs in run["heroes"].items():
        for r in runs:
            r.pop("shots", None)
        res["heroes"][slug] = {"pass": bool(runs) and all(r["pass"] for r in runs), "runs": runs,
                               "played": bool(runs)}
    played = [h for h in res["heroes"].values() if h["played"]]
    res["passed"] = bool(played) and all(h["pass"] for h in played)
    res["proof"] = any(k.startswith("proof:") for k in res["heroes"])
    if e.where == "world" and root is not None:
        write_json(e.path.with_name(e.id + CHECK_SUFFIX), res, indent=1)
    return res


def table(res: dict) -> str:
    lines = [f"{res['action']} ({'this world' if res['where'] == 'world' else 'core library'}):"]
    for slug, h in res["heroes"].items():
        if not h["played"]:
            lines.append(f"  --   {slug:<20} not played (an action for another view, or for two)")
            continue
        bad = "; ".join(f"{r['side']}: " + ", ".join(f"{k} {v:g}" for k, v in r["faults"].items())
                        for r in h["runs"] if r["faults"])
        lines.append(f"  {'ok  ' if h['pass'] else 'FAIL'} {slug:<20} {bad}")
    if res.get("limits") and not res["passed"]:
        lines.append("limits: " + ", ".join(f"{k} {v:g}" for k, v in res["limits"].items()))
    lines.append(f"{'PASSED' if res['passed'] else 'FAILED'} ({res['seconds']:g} s)")
    return "\n".join(lines)


def check_state(e: Entry) -> tuple[str, dict | None]:
    """A world action's last check: 'missing' | 'stale' (the file changed since) | 'failed' | 'passed'."""
    data, err = read_json(e.path.with_name(e.id + CHECK_SUFFIX))
    if not isinstance(data, dict):
        return "missing", None
    if data.get("sha") != file_sha(e.path):
        return "stale", data
    return ("passed" if data.get("passed") else "failed"), data


# ------------------------------------------------------------------------------------------------ sheet

def sheet(aid: str, root: Path | str | None, out: Path | None = None, heroes: list[str] | None = None,
          use_proof: bool = False, frames: int = 6, log=print) -> tuple[Path, dict]:
    """A storyboard PNG: a row per hero, `frames` pictures spread through the action (and its faults under it)."""
    from PIL import Image, ImageDraw, ImageFont

    from tadam.render import BG, INK, SOFT, ACCENT, TEXT_FONT
    e = find(aid, root)
    who: dict[str, Path] = {}
    w = World(root) if root is not None else None
    if w is not None and (heroes or not use_proof):
        all_h = heroes_of(w)
        for h in heroes or list(all_h):
            if h not in all_h:
                raise ActionError(f"heroes/{h} has no puppet")
            who[h] = all_h[h]
    if use_proof or w is None:
        for n, p in bodies(log=log).items():
            who["proof:" + n] = p
    shots = Path(tempfile.mkdtemp(prefix="tadam-sheet-"))
    try:
        run = _run_engine(e, who, root, shots=shots, frames=frames)
        rows = []
        for slug, runs in run["heroes"].items():
            first = next((r for r in runs if r["shots"]), None)
            if first:
                rows.append((slug, first, runs))
        if not rows:
            raise ActionError(f"{aid}: no pictures (an action for another view, or for two heroes)")
        # every row cut to what moves in it (the hero and its things), the same box for its frames
        boxes = {}
        for slug, first, runs in rows:
            box = None
            for p in first["shots"]:
                im = Image.open(p).convert("RGB")
                bg = Image.new("RGB", im.size, im.getpixel((2, 2)))
                from PIL import ImageChops
                bb = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 24 else 0).getbbox()
                if bb:
                    box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3]))
            if box is None:
                box = (0, 0, *Image.open(first["shots"][0]).size)
            w0, h0 = Image.open(first["shots"][0]).size
            cx = (box[0] + box[2]) / 2
            half = max((box[2] - box[0]) / 2 + 24, (box[3] - box[1] + 48) * 0.36)
            boxes[slug] = (int(max(0, cx - half)), int(max(0, box[1] - 24)), int(min(w0, cx + half)), h0)
        th = 300
        thumb_w = max(int(round((b[2] - b[0]) * th / (b[3] - b[1]))) for b in boxes.values())
        label_w, pad, head = 200, 14, 64
        n = max(len(r[1]["shots"]) for r in rows)
        W = pad * 2 + label_w + n * (thumb_w + 6)
        H = head + pad + len(rows) * (th + 8) + pad
        sh = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(sh)
        f_big = ImageFont.truetype(str(TEXT_FONT), 30)
        f_small = ImageFont.truetype(str(TEXT_FONT), 20)
        d.text((pad, 16), f"{e.id}: {e.title}  ({frames} кадров, правая сторона)", font=f_big, fill=INK)
        y = head
        for slug, first, runs in rows:
            ok = all(r["pass"] for r in runs)
            d.text((pad, y + 10), slug.replace("proof:", "проба: "), font=f_small, fill=INK)
            d.text((pad, y + 40), "ok" if ok else "БРАК", font=f_small, fill=SOFT if ok else ACCENT)
            yy = y + 70
            for r in runs:
                for k, v in r["faults"].items():
                    if yy < y + th - 20:
                        d.text((pad, yy), f"{r['side'][0]}: {k} {v:g}", font=f_small, fill=ACCENT)
                        yy += 24
            for i, p in enumerate(first["shots"]):
                b = boxes[slug]
                t = Image.open(p).convert("RGB").crop(b)
                t = t.resize((max(1, int(round(t.width * th / t.height))), th), Image.LANCZOS)
                cell = Image.new("RGB", (thumb_w, th), t.getpixel((1, 1)))
                cell.paste(t, ((thumb_w - t.width) // 2, 0))
                sh.paste(cell, (pad + label_w + i * (thumb_w + 6), y))
            y += th + 8
        if out is None:
            base = (World(root).work_dir() if root is not None else engine_dir().parent / "out") / "actions"
            out = base / f"{e.id}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        sh.save(out)
    finally:
        shutil.rmtree(shots, ignore_errors=True)
    return out, run
