"""`tadam doctor`: is everything the studio needs installed?

Checks Python, Godot 4.7, ffmpeg and ffprobe, the OpenAI key (only that it is set: its value is never read
out or printed) and a writable temp folder. Prints one line per check and, for whatever is missing, where to
get it. Exit code 1 when something REQUIRED is missing; warnings alone give 0.

Everything the checks touch goes through `System`, so the tests can replace the computer with a fake one.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

GODOT_MAJOR_MINOR = (4, 7)
PYTHON_MIN = (3, 11)
GODOT_NAMES = ("godot_console", "godot4", "godot")      # on PATH, in this order (console build first on Windows)
MAC_GODOT = ("/Applications/Godot.app/Contents/MacOS/Godot", "~/Applications/Godot.app/Contents/MacOS/Godot")

HINTS = {
    "python": "Install Python 3.11 or newer: https://www.python.org/downloads/",
    "godot": ("Install Godot 4.7 (standard build, not .NET): https://godotengine.org/download/ - then put it on "
              "PATH as godot / godot4 / godot_console, or set TADAM_GODOT to the full path of the executable."),
    "ffmpeg": "Install ffmpeg (it brings ffprobe too): https://ffmpeg.org/download.html",
    "ffprobe": "ffprobe comes with ffmpeg: https://ffmpeg.org/download.html",
    "libx264": "This ffmpeg cannot write H.264 (libx264): drafts cannot be saved as MP4. Install a full ffmpeg build.",
    "openai": ("Set your own OpenAI API key in the environment variable OPENAI_API_KEY "
               "(https://platform.openai.com/api-keys). Needed to paint puppets and sets; checking and playing "
               "a world work without it."),
    "temp": "The temp folder is not writable: set TMPDIR (macOS/Linux) or TEMP (Windows) to a folder you can write.",
}


@dataclass
class Result:
    name: str
    status: str                 # "ok" | "missing" | "warn"
    detail: str = ""
    hint: str = ""
    required: bool = True


@dataclass
class System:
    """The computer as the checks see it. Defaults are the real one."""
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    which: Callable[[str], str | None] = shutil.which
    run: Callable[[Sequence[str]], str | None] = None  # type: ignore[assignment]
    version_info: tuple = field(default_factory=lambda: tuple(sys.version_info[:3]))
    platform: str = sys.platform
    is_file: Callable[[str], bool] = lambda p: Path(p).expanduser().is_file()
    list_dir: Callable[[str], list[str]] = None  # type: ignore[assignment]
    temp_dir: Callable[[], str] = tempfile.gettempdir

    def __post_init__(self):
        if self.run is None:
            self.run = _run
        if self.list_dir is None:
            self.list_dir = _list_dir


def _run(cmd: Sequence[str]) -> str | None:
    """stdout (+ stderr) of a short command, or None when it cannot be run."""
    try:
        p = subprocess.run(list(cmd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return (p.stdout or "") + (p.stderr or "")


def _base(path: str) -> str:
    """The file name, whichever separator the path uses (a Windows path is read right on any OS)."""
    return re.split(r"[\\/]", path)[-1]


def _list_dir(d: str) -> list[str]:
    try:
        return [str(p) for p in Path(d).iterdir() if p.is_file()]
    except OSError:
        return []


# ---------------------------------------------------------------------------------------------------- checks

def check_python(s: System) -> Result:
    v = tuple(s.version_info[:3])
    text = ".".join(str(x) for x in v)
    if v[:2] >= PYTHON_MIN:
        return Result("Python", "ok", text)
    return Result("Python", "missing", f"{text} (need 3.11 or newer)", HINTS["python"])


def find_godot(s: System) -> tuple[str | None, str]:
    """(path, how it was found) or (None, why not)."""
    forced = (s.environ.get("TADAM_GODOT") or "").strip()
    if forced:
        if s.is_file(forced):
            return forced, "TADAM_GODOT"
        return None, "TADAM_GODOT is set but there is no file at that path"
    for name in GODOT_NAMES:
        p = s.which(name)
        if p:
            return p, f"PATH ({name})"
    # a downloaded build that was only unzipped into a folder on PATH: Godot_v4.7-stable_win64.exe and the like
    win = s.platform.startswith("win")
    for d in (s.environ.get("PATH") or "").split(";" if win else ":"):
        if not d:
            continue
        found = []
        for f in s.list_dir(d):
            name = _base(f).lower()
            ext = name.rsplit(".", 1)[-1] if "." in name else ""
            if name.startswith("godot") and (ext == "exe" if win else ext not in ("txt", "md", "zip")):
                found.append(f)
        if found:
            found.sort()
            console = [f for f in found if "console" in _base(f).lower()]
            return (console or found)[0], "PATH (Godot*)"
    if s.platform == "darwin":
        for p in MAC_GODOT:
            if s.is_file(p):
                return os.path.expanduser(p), "/Applications"
    return None, "not found"


def check_godot(s: System) -> Result:
    path, how = find_godot(s)
    if path is None:
        return Result("Godot 4.7", "missing", how, HINTS["godot"])
    out = s.run([path, "--version"])
    if out is None:
        return Result("Godot 4.7", "missing", f"{path} does not start", HINTS["godot"])
    m = re.search(r"\b(\d+)\.(\d+)(?:\.(\d+))?\.[a-z]", out) or re.search(r"\b(\d+)\.(\d+)(?:\.(\d+))?", out)
    if not m:
        return Result("Godot 4.7", "missing", f"{path}: cannot read its version", HINTS["godot"])
    ver = ".".join(g for g in m.groups() if g)
    if (int(m.group(1)), int(m.group(2))) != GODOT_MAJOR_MINOR:
        return Result("Godot 4.7", "missing", f"found {ver} at {path} (need 4.7.x)", HINTS["godot"])
    if "mono" in out.lower():
        return Result("Godot 4.7", "warn", f"{ver} .NET build at {path}; the standard build is enough",
                      required=False)
    return Result("Godot 4.7", "ok", f"{ver} ({how}: {path})")


def check_tool(s: System, name: str) -> Result:
    path = s.which(name)
    if not path:
        return Result(name, "missing", "not found on PATH", HINTS[name])
    out = s.run([path, "-version"])
    if out is None:
        return Result(name, "missing", f"{path} does not start", HINTS[name])
    first = out.strip().splitlines()[0] if out.strip() else ""
    m = re.search(r"version\s+(\S+)", first)
    return Result(name, "ok", f"{m.group(1) if m else '?'} ({path})")


def check_x264(s: System) -> Result | None:
    path = s.which("ffmpeg")
    if not path:
        return None
    out = s.run([path, "-hide_banner", "-encoders"])
    if out is not None and "libx264" in out:
        return Result("ffmpeg H.264", "ok", "libx264", required=False)
    return Result("ffmpeg H.264", "warn", "libx264 encoder not found", HINTS["libx264"], required=False)


def check_openai(s: System) -> Result:
    """Only whether the key is there. The value is never printed, logged or compared with anything."""
    v = s.environ.get("OPENAI_API_KEY")
    if v is None or not v.strip():
        return Result("OPENAI_API_KEY", "warn", "not set", HINTS["openai"], required=False)
    if not v.isascii() or any(c.isspace() for c in v.strip()):
        return Result("OPENAI_API_KEY", "warn", "set, but it does not look like a key (odd characters)",
                      HINTS["openai"], required=False)
    return Result("OPENAI_API_KEY", "ok", "set (value hidden)", required=False)


def check_temp(s: System) -> Result:
    d = s.temp_dir()
    try:
        fd, p = tempfile.mkstemp(prefix="tadam-doctor-", dir=d)
        try:
            os.write(fd, b"ok")
        finally:
            os.close(fd)
            os.remove(p)
    except OSError as e:
        return Result("temp folder", "missing", f"{d}: {e.strerror or e}", HINTS["temp"])
    return Result("temp folder", "ok", d)


def run_checks(s: System | None = None) -> list[Result]:
    s = s or System()
    out = [check_python(s), check_godot(s), check_tool(s, "ffmpeg"), check_tool(s, "ffprobe")]
    x = check_x264(s)
    if x is not None:
        out.append(x)
    out += [check_openai(s), check_temp(s)]
    return out


# ---------------------------------------------------------------------------------------------------- report

MARK = {"ok": "[ ok ]", "warn": "[warn]", "missing": "[MISS]"}


def report(results: list[Result]) -> tuple[str, int]:
    lines = ["tadam doctor", ""]
    for r in results:
        lines.append(f"{MARK[r.status]} {r.name}: {r.detail}".rstrip(": "))
    todo = [r for r in results if r.status != "ok" and r.hint]
    if todo:
        lines += ["", "What to do:"]
        for r in todo:
            lines.append(f"- {r.name}: {r.hint}")
    bad = [r for r in results if r.status == "missing" and r.required]
    lines.append("")
    if bad:
        lines.append(f"Missing (required): {', '.join(r.name for r in bad)}.")
    else:
        warn = [r for r in results if r.status == "warn"]
        lines.append("Ready." if not warn else "Ready, with warnings above.")
    return "\n".join(lines), (1 if bad else 0)


def main(system: System | None = None) -> int:
    text, code = report(run_checks(system))
    print(text)
    return code
