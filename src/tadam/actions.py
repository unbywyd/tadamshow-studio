"""`tadam hero check <slug>`: EVERY ACTION ON THIS HERO, measured by the engine (engine/tools/action_check.gd, the
action x hero table of the engine's framework, its section 4.7), without a window.

Each action is played from rest (one-sided ones on both sides: right and left), held, and sent back to rest; the
engine measures it and compares every number with the tool's own limits (LIMITS in its header: an elbow or knee on
the wrong side, a standing foot that slides, a hand inside the body, under the floor, a missed target, a hand's path
against the straight line, a jerk, out of the picture, the face covered, not back at rest, ...).

THE RULE: nothing is fitted to a hero. A failing action is reported, never tuned for this hero; a hero that fails a
stage-1 action is drawn again (`tadam hero make`), not adjusted.

Stage 1 (the engine's first stage, "the core of motion": poses, gestures, body moves in place, feelings, two
dances) is the gate: a hero must pass every one of them. The rest (walking, sitting, falling, fights, things in the
hands, music, actions of two) is reported too but does not fail the hero: many of them are made for a side view or a
second hero and are checked on the stage, in the scene. "out" (a part leaves the test picture: a hop of a tall hero)
is the camera's business in a scene and is reported without failing.

Writes heroes/<slug>/puppet/actions.json: {passed, stage1, seconds, rig (the sha-256 of rig.json's CONTENT,
tadam.jsonfile.content_sha: a re-cut puppet needs a new check, a checkout that only changed line endings does not),
limits, actions: {id: {group, stage1, pass, runs: [{side, pass, faults: {measure: value}}]}}}.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path

from tadam import engine
from tadam.engine import EngineError
from tadam.jsonfile import file_content_sha, write_json
from tadam.jsonfile import lf as file_lf
from tadam.paths import engine_dir
from tadam.world import World, read_json

# the engine's stage 1: 7 poses, 15 gestures, 4 feelings, 2 dances, 5 body moves in place (33 actions)
STAGE1 = (
    "rest", "hips", "think", "tired", "scared", "serious", "victory",
    "wave", "bye", "beckon", "point", "clap", "facepalm", "head_grab", "heart", "nod", "shake_head", "rub",
    "scratch_head", "shoo", "shrug", "spread",
    "angry", "cry", "laugh", "surprised",
    "dance_arms", "dance_twist",
    "bow", "curtsy", "hop", "jump", "squat",
)
NOT_A_FAULT = {"out"}          # the camera's business (see above)
FILE = "actions.json"


def rig_sha(pdir: Path) -> str:
    """The fingerprint of the puppet's rig.json: of its content, never of its bytes (CRLF/LF, indentation)."""
    return file_content_sha(Path(pdir) / "rig.json")


def _raw_shas(pdir: Path) -> set[str]:
    """What kits before 0.0.2 wrote: the sha-256 of the raw bytes, made on a system that may have used CRLF. Still
    accepted (with either line ending), so a check made before stays good after a checkout changed them."""
    lf = file_lf((Path(pdir) / "rig.json").read_bytes())
    return {hashlib.sha256(b).hexdigest() for b in (lf, lf.replace(b"\n", b"\r\n"))}


def _groups() -> dict[str, str]:
    out = {}
    for f in sorted((engine_dir() / "actions").glob("*.json")):
        try:
            a = json.loads(f.read_text(encoding="utf-8"))
            out[str(a["id"])] = str(a.get("group", ""))
        except (ValueError, KeyError):
            continue
    return out


def summarise(raw: dict, groups: dict[str, str], sha: str, seconds: float) -> dict:
    """The engine's runs → actions.json (pure: a test feeds it runs)."""
    limits = raw.get("limits") or {}
    acts: dict[str, dict] = {}
    for r in raw.get("runs") or []:
        aid = str(r.get("action"))
        faults = [f for f in (r.get("faults") or []) if isinstance(f, str)]
        hard = {f: round(float(r.get(f, 0.0)), 4) for f in faults if f not in NOT_A_FAULT}
        soft = {f: round(float(r.get(f, 0.0)), 4) for f in faults if f in NOT_A_FAULT}
        a = acts.setdefault(aid, {"group": groups.get(aid, ""), "stage1": aid in STAGE1, "pass": True, "runs": []})
        run = {"side": r.get("side", "right"), "pass": not hard, "faults": hard}
        if soft:
            run["notes"] = soft
        a["runs"].append(run)
        a["pass"] = a["pass"] and not hard
    missing = [a for a in STAGE1 if a not in acts]
    failed = [a for a in STAGE1 if a in acts and not acts[a]["pass"]]
    return {"passed": not missing and not failed, "stage1": list(STAGE1), "stage1_failed": failed,
            "stage1_missing": missing, "seconds": round(seconds, 1), "rig": sha, "limits": limits,
            "actions": dict(sorted(acts.items()))}


def run(w: World, slug: str, timeout: float = 900) -> dict:
    """Play every action on the hero in the engine; write and return actions.json."""
    pdir = w.puppet_dir(slug)
    if not (pdir / "rig.json").is_file():
        raise EngineError(f"heroes/{slug} has no puppet yet: `tadam hero make {slug} \"<description>\"`")
    engine.ensure_imported()
    tmp = Path(tempfile.mkdtemp(prefix="tadam-actions-"))
    try:
        out = tmp / "actions.json"
        started = time.monotonic()
        p = engine._run([engine.godot(), "--headless", "--path", str(engine_dir()), "--script",
                         "res://tools/action_check.gd", "--", f"--puppets={(w.root / 'heroes').as_posix()}",
                         f"--heroes={slug}", f"--out={out.as_posix()}"], timeout)
        raw, err = read_json(out)
        if not isinstance(raw, dict):
            raise EngineError("the engine did not finish the action check:\n" + engine_tail(p.stdout + p.stderr))
        if not raw.get("runs"):
            raise EngineError(f"the engine could not load heroes/{slug}/puppet:\n" + engine_tail(p.stdout + p.stderr))
        res = summarise(raw, _groups(), rig_sha(pdir), time.monotonic() - started)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    write_json(pdir / FILE, res, indent=1)
    return res


def engine_tail(text: str) -> str:
    lines = [x for x in text.splitlines() if x.strip()]
    return "\n".join(lines[-12:])


def table(res: dict) -> str:
    """A short table: stage 1 in one block (only what failed spelled out), then the other actions that failed."""
    acts = res.get("actions") or {}
    s1 = [a for a in res.get("stage1") or [] if a in acts]
    ok1 = sum(acts[a]["pass"] for a in s1)
    lines = [f"stage 1: {ok1}/{len(res.get('stage1') or [])} actions pass"
             + (f" (not played: {', '.join(res['stage1_missing'])})" if res.get("stage1_missing") else "")]

    def why(a: dict) -> str:
        bad = [f"{r['side']}: " + ", ".join(f"{k} {v:g}" for k, v in r["faults"].items()) for r in a["runs"] if r["faults"]]
        return "; ".join(bad)
    for a in s1:
        if not acts[a]["pass"]:
            lines.append(f"  FAIL {a:<14} {why(acts[a])}")
    other = [a for a in acts if not acts[a]["stage1"]]
    bad = [a for a in other if not acts[a]["pass"]]
    lines.append(f"other actions: {len(other) - len(bad)}/{len(other)} pass (reported, they do not fail the hero)")
    for a in bad:
        lines.append(f"  warn {a:<14} [{acts[a]['group']}] {why(acts[a])}")
    lines.append(f"{'PASSED' if res.get('passed') else 'FAILED'} ({res.get('seconds', 0):g} s)")
    return "\n".join(lines)


def state(pdir: Path) -> tuple[str, dict | None]:
    """'missing' | 'stale' (the rig changed since) | 'failed' | 'passed', with the file's data."""
    data, err = read_json(Path(pdir) / FILE)
    if not isinstance(data, dict):
        return "missing", None
    try:
        if data.get("rig") != rig_sha(pdir) and data.get("rig") not in _raw_shas(pdir):
            return "stale", data
    except OSError:
        return "missing", None
    except ValueError:                          # (rig.json is not JSON: the check says so on its own)
        return "stale", data
    return ("passed" if data.get("passed") else "failed"), data
