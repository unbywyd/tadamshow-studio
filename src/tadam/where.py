"""WHERE THE WINDOW STANDS (`tadam play where`): what engine/player.gd wrote on its last pause into
.tadam/player/state.json, told for Claude — the shot and second, the picture, who speaks, what every hero plays and
which lines of episodes/<n>/script.json are at work (shots[i].camera[n]); the marks; what was picked last in the
action library. When the person says "here", "this place", "тут", Claude asks this first and looks at the picture.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from tadam import render
from tadam.world import World, read_json

QUIET = 8.0          # seconds without a heartbeat from the window: it is closed (or hung)


def read_state(world: World) -> dict | None:
    data, _ = read_json(render.state_dir(world) / "state.json")
    return data if isinstance(data, dict) else None


def is_open(state: dict, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    return bool(state.get("running")) and now - float(state.get("unix") or 0) < QUIET


def script_ref(world: World, episode: str, shot_id: str) -> dict:
    """Where a shot's lines are in the script: {"file", "shot_index", "path", "sha"} (shot_index -1: not there)."""
    f = world.episode_dir(episode) / "script.json"
    script, _ = read_json(f)
    shots = script.get("shots") if isinstance(script, dict) else None
    idx = -1
    for i, s in enumerate(shots if isinstance(shots, list) else []):
        if isinstance(s, dict) and str(s.get("id", i + 1)) == shot_id:
            idx = i
            break
    try:
        import hashlib
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
    except OSError:
        sha = ""
    rel = f"episodes/{episode}/script.json"
    return {"file": rel, "shot_index": idx, "path": f"shots[{idx}].camera" if idx >= 0 else "", "sha": sha}


def report(world: World, state: dict | None, now: float | None = None) -> dict:
    """The state with what Claude needs on top: open or not, the moment to look at, where its lines are."""
    if state is None:
        return {"open": False, "found": False}
    out = dict(state)
    out["found"] = True
    out["open"] = is_open(state, now)
    moment = state.get("pause") or {}
    out["moment"] = "pause" if moment else "none"
    if moment:
        ref = script_ref(world, str(state.get("episode", "")), str(moment.get("shot", "")))
        out["script"] = ref
        out["script_changed"] = bool(state.get("script_sha")) and ref["sha"] != state.get("script_sha")
        out["frame_cmd"] = (f"tadam frames {state.get('episode')} --shot {moment.get('shot')} "
                            f"--at {moment.get('at')}")
        out["around_cmd"] = out["frame_cmd"].replace(" --at ", " --around ") + " --frames 6"
    lib, _ = read_json(Path(str(state.get("library") or render.state_dir(world) / "library.json")))
    if isinstance(lib, dict):
        out["library_pick"] = lib
    return out


def _line(rec: dict) -> str:
    st = rec.get("status", "")
    when = (f"ran at {rec['ran']:.2f} s" if "ran" in rec else f"due at {rec['due']:.2f} s" if "due" in rec
            else "waits for 'after'")
    return f"[{rec.get('n')}] {st:<7} {json.dumps(rec.get('line', {}), ensure_ascii=False)}  ({when})"


def _heroes(hs: list) -> list[str]:
    out = []
    for h in hs or []:
        doing = [f"{a['id']} (phase {a['phase']}/{a['phases']}, {a['t']:.2f} s into it)" for a in h.get("actions", [])]
        if h.get("going"):
            doing.append("walking")
        if h.get("turning"):
            doing.append("turning")
        if h.get("off_stage"):
            doing.append("off stage")
        if h.get("holds"):
            doing.append(f"holds the last pose of {h['holds']} (over, nothing has moved it since)")
        out.append(f"  {h.get('name')} ({h.get('key')}, {h.get('view')}): {', '.join(doing) or 'still'}")
    return out


def _moment_text(m: dict, ref: dict | None) -> list[str]:
    L = [f"shot {m.get('shot')} ({int(m.get('index', 0)) + 1} of {m.get('shots')})"
         + (f" \"{m.get('remark')}\"" if m.get("remark") else "")
         + f" · {m.get('at'):.2f} of {m.get('seconds'):.2f} s · frame {m.get('frame')} · "
         f"{m.get('from_start'):.2f} s from the start"]
    if m.get("png"):
        L.append(f"the picture: {m['png']}")
    sp = m.get("speaking") or {}
    if sp:
        who = "narration" if sp.get("kind") == "narration" else sp.get("who")
        L.append(f"heard: {who}: {sp.get('text')}")
    L.append("heroes:")
    L += _heroes(m.get("heroes", []))
    lines = m.get("lines") or []
    if lines:
        where = f"{ref['file']} → {ref['path']}[n]" if ref and ref.get("path") else "the shot's camera[n]"
        L.append(f"lines of this shot ({where}):")
        order = {"at_work": 0, "holds": 1, "done": 2, "next": 3, "waits": 4}
        for rec in sorted(lines, key=lambda r: (order.get(r.get("status"), 9), -(r.get("ran") or 0))):
            L.append("  " + _line(rec))
    return L


def text(rep: dict) -> str:
    if not rep.get("found"):
        return ("no window has stood anywhere yet: start it (`tadam play <episode>`, in the background), "
                "and the person pauses it with Space")
    L = []
    state = "open" if rep["open"] else "closed (this is where it was)"
    L.append(f"the window is {state}, {'paused' if rep.get('paused') else 'playing'}"
             + (f" at {rep['speed']}×" if rep.get("speed") not in (1, 1.0, None) else "")
             + f" · episode {rep.get('episode')}")
    m = rep.get("pause") or {}
    if not m:
        now = rep.get("now") or {}
        L.append(f"no pause yet; it plays shot {now.get('shot')} at {now.get('at')} s")
    else:
        if not rep.get("paused"):
            now = rep.get("now") or {}
            L.append(f"the last pause (playing on since; now shot {now.get('shot')} at {now.get('at')} s):")
        L += _moment_text(m, rep.get("script"))
        if rep.get("script_changed"):
            L.append("NOTE: script.json changed after this pause: the lines' numbers are of the script as it was")
        L.append(f"full size: {rep['frame_cmd']}   ·   the motion round it: {rep['around_cmd']}")
    marks = rep.get("marks") or []
    if marks:
        L.append(f"marks ({len(marks)}):")
        for mk in marks:
            work = [f"[{r['n']}] {json.dumps(r['line'], ensure_ascii=False)}" for r in mk.get("lines", [])
                    if r.get("status") == "at_work"]
            L.append(f"  {mk.get('n')}) shot {mk.get('shot')} at {mk.get('at'):.2f} s · {mk.get('png', '')}"
                     + (f" · at work: {'; '.join(work)}" if work else ""))
    lib = rep.get("library_pick")
    if lib:
        L.append(f"picked last in the action library: {lib.get('action')} ({lib.get('title')}) at {lib.get('at')}")
    return "\n".join(L)
