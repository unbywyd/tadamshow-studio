"""Running the kit's engine (Godot 4.7) without a window: the scene's own check (stage.gd --check).

Godot is found the way `tadam doctor` finds it (TADAM_GODOT, PATH, the macOS app). The engine project is imported
once (engine/.godot, never committed). Playing, frames and films: tadam.render (engine/player.tscn).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tadam import doctor
from tadam.paths import engine_dir


class EngineError(RuntimeError):
    pass


def godot() -> str:
    path, how = doctor.find_godot(doctor.System())
    if not path:
        raise EngineError(f"Godot 4.7 not found ({how}): run `tadam doctor`")
    return path


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def ensure_imported(timeout: float = 600) -> None:
    """Import the engine's pictures and sounds once (the first run after a clone)."""
    eng = engine_dir()
    if (eng / ".godot" / "imported").is_dir():
        return
    p = _run([godot(), "--headless", "--path", str(eng), "--import"], timeout)
    if not (eng / ".godot" / "imported").is_dir():
        raise EngineError("the engine could not import its files:\n" + (p.stdout + p.stderr)[-1500:])


def run_check(scene_dir: Path, seconds: float, timeout: float = 600) -> dict | None:
    """Play a scene through unseen, as fast as it goes; the engine's CHECK line: {"problems": {...}, "seconds"},
    or None when the scene did not play to its end (an error in the engine: the output says which)."""
    ensure_imported()
    eng = engine_dir()
    p = _run([godot(), "--headless", "--path", str(eng), "--fixed-fps", "60", "res://stage.tscn", "--",
              f"--scene={Path(scene_dir).resolve().as_posix()}", "--check", f"--seconds={seconds:g}"], timeout)
    for line in p.stdout.splitlines():
        if line.startswith("CHECK "):
            return json.loads(line[6:])
    return None


WORDS = {"never": "an 'after' line never got its moment: what it waits for did not happen before the end",
         "offscreen": "talks off the picture", "back": "talks with its back to us: the face is not seen",
         "small_face": "the recorded face is smaller than 12% of the picture: bring the camera closer"}
