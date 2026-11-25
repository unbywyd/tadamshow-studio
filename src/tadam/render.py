"""THE ENGINE SHOWS AN EPISODE: `tadam play` (a window, in real time, with its sound), `tadam frames` (PNG frames
and the contact sheet: Claude's eyes) and `tadam film` (a draft MP4). All three run the same engine scene,
engine/player.tscn (engine/player.gd), on a playlist tadam writes for the run:

- every run has its own folder in the system temp (the playlist, the mixed sound, the raw film), removed after it;
  nothing is ever written into the engine folder (no engine/override.cfg), so two runs at once never collide.
  The window's size comes from the command line and the playlist;
- frames and films are made offline, frame by frame (--fixed-fps), the frames counted as the site's film counts
  them: the same scene gives the same pictures on every run;
- with no screen (Linux without DISPLAY / WAYLAND_DISPLAY) frames and films run under xvfb-run when it is there;
  elsewhere the window is put off the screen (a covered or minimised window is not drawn, and its frames are lost).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tadam import engine, mix
from tadam.engine import EngineError
from tadam.episode import Episode, sounds
from tadam.paths import FONTS, engine_dir

SNAP_FPS = 60                    # frames are taken one engine step apart
OFF_SCREEN = "6000,0"            # where an unseen window goes (the old make_scene.sh did the same)
PLAY_WINDOW = (450, 800)         # a window that fits a laptop's screen; the picture is drawn at this size
TEXT_FONT = FONTS / "PT_Serif-Web-Bold.ttf"
ITALIC_FONT = FONTS / "PT_Serif-Web-Italic.ttf"
MONO_FONT = FONTS / "PTM55FT.ttf"


# ------------------------------------------------------------------------------------------------ the command

def display_prefix(mode: str, environ=None, platform: str | None = None, which=shutil.which,
                   size: tuple[int, int] = (720, 1280)) -> list[str]:
    """What the engine runs under to get a window: nothing, or xvfb-run on a Linux without a screen."""
    env = os.environ if environ is None else environ
    plat = platform or sys.platform
    if not plat.startswith("linux") or env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"):
        return []
    if mode == "play":
        raise EngineError("`tadam play` needs a screen (DISPLAY is not set): use `tadam frames` or `tadam film`")
    x = which("xvfb-run")
    if not x:
        raise EngineError("no screen (DISPLAY is not set) and no xvfb-run: install xvfb (apt install xvfb) "
                          "or run on a computer with a screen")
    return [x, "-a", "-s", f"-screen 0 {size[0] + 64}x{size[1] + 64}x24"]


def command(godot: str, mode: str, playlist: Path, size: tuple[int, int], fps: int = 30, movie: Path | None = None,
            board_preview: bool = False, window: tuple[int, int] = PLAY_WINDOW, prefix: list[str] | None = None,
            platform: str | None = None) -> list[str]:
    """The engine's command line for one run (pure: tests read it)."""
    plat = platform or sys.platform
    cmd = list(prefix or []) + [godot, "--path", str(engine_dir())]
    if mode == "play":
        cmd += ["--resolution", f"{window[0]}x{window[1]}", "--position", "80,40"]
    else:
        cmd += ["--resolution", f"{size[0]}x{size[1]}"]
        if not (prefix and plat.startswith("linux")):
            cmd += ["--position", OFF_SCREEN]
        cmd += ["--disable-vsync", "--fixed-fps", str(SNAP_FPS if mode == "snap" else fps)]
        if mode == "snap":
            cmd += ["--audio-driver", "Dummy"]
        if mode == "film":
            cmd += ["--write-movie", str(movie)]
    cmd += ["res://player.tscn", "--", f"--playlist={Path(playlist).as_posix()}", f"--font={TEXT_FONT.as_posix()}"]
    if board_preview:
        cmd.append("--board-preview")
    return cmd


def playlist(ep: Episode, mode: str, start: int = 0, snaps: list | None = None, audio: Path | None = None) -> dict:
    """What engine/player.gd plays (pure)."""
    shots = []
    for s in ep.shots:
        shots.append({"id": s.id, "scene": s.dir.as_posix(), "seconds": s.seconds, "frames": s.frames,
                      "card": s.card, "subs": s.subs})
    return {"mode": mode, "fps": ep.fps, "size": list(ep.size), "start": start,
            "audio": audio.as_posix() if audio else "", "audio_from": ep.shots[start].start if ep.shots else 0.0,
            "fonts": {"text": TEXT_FONT.as_posix(), "italic": ITALIC_FONT.as_posix()},
            "shots": shots, "snaps": snaps or []}


def snap_frame(at: float) -> int:
    """The frame of a shot (counted as engine/player.gd counts them in snap mode: frame k is drawn after k + 1
    steps) that shows the shot `at` seconds in."""
    return max(int(round(at * SNAP_FPS)) - 1, 0)


@dataclass
class Run:
    dir: Path
    log: str = ""


def _new_run() -> Run:
    return Run(Path(tempfile.mkdtemp(prefix="tadam-run-")))


def _go(cmd: list[str], timeout: float, echo: bool = False) -> str:
    """Runs the engine to its end; returns what it printed (stdout + stderr)."""
    engine.ensure_imported()
    try:
        if echo:          # (play: what the engine says shows as it says it; only its errors)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace")
            out = []
            try:
                for line in p.stdout:
                    out.append(line)
                    if "ERROR" in line and "leaked" not in line and "still in use" not in line:
                        sys.stdout.write(line)
                p.wait()
            except KeyboardInterrupt:
                p.terminate()
                p.wait(10)
            return "".join(out)
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        raise EngineError(f"the engine did not finish in {timeout:g} s") from e


def _tail(text: str) -> str:
    keep = [ln for ln in text.splitlines() if "ERROR" in ln or "PLAYER" in ln or "error" in ln.lower()]
    return "\n".join(keep[-12:]) or text[-1200:]


# ------------------------------------------------------------------------------------------------ frames

def snaps(ep: Episode, wants: list[tuple[int, float, Path]], board_preview: bool = False,
          timeout: float = 600) -> list[Path]:
    """PNGs of the frames asked for: (shot index, seconds into the shot, out file). One engine run for all."""
    wants = sorted(wants, key=lambda w: (w[0], w[1]))
    run = _new_run()
    try:
        for _, _, out in wants:
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).unlink(missing_ok=True)
        pl = playlist(ep, "snap", snaps=[{"shot": i, "frame": snap_frame(min(t, ep.shots[i].seconds)),
                                          "out": Path(o).resolve().as_posix()} for i, t, o in wants])
        f = run.dir / "playlist.json"
        f.write_text(json.dumps(pl, ensure_ascii=False), encoding="utf-8")
        cmd = command(engine.godot(), "snap", f, ep.size, board_preview=board_preview,
                      prefix=display_prefix("snap", size=ep.size))
        out = _go(cmd, timeout)
        missing = [o for _, _, o in wants if not Path(o).is_file()]
        if missing:
            raise EngineError("the engine did not draw every frame:\n" + _tail(out))
        for _, _, o in wants:           # (a window the system made smaller than asked: the picture is put right)
            with Image.open(o) as im:
                if im.size != tuple(ep.size):
                    im.convert("RGB").resize(ep.size, Image.LANCZOS).save(o)
        return [Path(o) for _, _, o in wants]
    finally:
        shutil.rmtree(run.dir, ignore_errors=True)


def frames_dir(ep: Episode) -> Path:
    return ep.world.work_dir() / "frames" / ep.n


# ------------------------------------------------------------------------------------------------ the sheet

def sheet_layout(n: int, thumb: tuple[int, int], cols: int | None = None, label: int = 64, pad: int = 16,
                 gap: int = 12) -> tuple[tuple[int, int], list[tuple[int, int]]]:
    """(the sheet's size, the top-left corner of every frame): a grid, `cols` wide (up to 5 by default; fewer
    shots: one row), each frame with its label under it (pure)."""
    if n <= 0:
        return (2 * pad + thumb[0], 2 * pad + thumb[1] + label), []
    cols = cols or min(n, 5)
    rows = (n + cols - 1) // cols
    cw, ch = thumb[0] + gap, thumb[1] + label + gap
    size = (2 * pad + cols * cw - gap, 2 * pad + rows * ch - gap)
    return size, [(pad + (i % cols) * cw, pad + (i // cols) * ch) for i in range(n)]


BG, INK, SOFT, ACCENT = (246, 240, 230), (33, 32, 28), (110, 100, 88), (194, 53, 31)


def _fit(d: ImageDraw.ImageDraw, text: str, font, width: int, lines: int) -> list[str]:
    """`text` in at most `lines` lines of `width` px (the last one cut with …)."""
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= width:
            cur = t
            continue
        if cur:
            out.append(cur)
        cur = w
        if len(out) == lines:
            break
    if cur and len(out) < lines:
        out.append(cur)
    if len(out) == lines and " ".join(out) != text.strip():
        last = out[-1]
        while last and d.textlength(last + "…", font=font) > width:
            last = last[:-1]
        out[-1] = last.rstrip() + "…"
    return out


def make_sheet(ep: Episode, pngs: list[Path], out: Path, thumb_w: int = 240) -> Path:
    thumb = (thumb_w, int(round(thumb_w * ep.size[1] / ep.size[0])))
    label = 70
    size, corners = sheet_layout(len(pngs), thumb, label=label)
    img = Image.new("RGB", size, BG)
    d = ImageDraw.Draw(img)
    f_id = ImageFont.truetype(str(TEXT_FONT), 19)
    f_sec = ImageFont.truetype(str(MONO_FONT), 15)
    f_rem = ImageFont.truetype(str(ITALIC_FONT), 15)
    for s, png, (x, y) in zip(ep.shots, pngs, corners):
        with Image.open(png) as im:
            img.paste(im.convert("RGB").resize(thumb, Image.LANCZOS), (x, y))
        ty = y + thumb[1] + 6
        d.text((x, ty), s.id, font=f_id, fill=ACCENT)
        sec = f"{s.seconds:g} s" + (f" · {s.speaker}" if s.speaker else "")
        d.text((x + thumb[0] - d.textlength(sec, font=f_sec), ty + 4), sec, font=f_sec, fill=SOFT)
        for k, line in enumerate(_fit(d, s.remark, f_rem, thumb[0], 2)):
            d.text((x, ty + 26 + k * 18), line, font=f_rem, fill=INK)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def sheet(ep: Episode, out: Path | None = None, board_preview: bool = False) -> tuple[Path, list[Path]]:
    """A frame from the middle of every shot, labelled with its id and remark, on one PNG."""
    d = frames_dir(ep)
    wants = [(i, s.seconds / 2, d / f"_sheet_{s.id}.png") for i, s in enumerate(ep.shots)]
    pngs = snaps(ep, wants, board_preview)
    path = make_sheet(ep, pngs, out or d / "sheet.png")
    return path, pngs


# ------------------------------------------------------------------------------------------------ play and film

def _sound(ep: Episode, run: Run, log=print) -> Path | None:
    return mix.render(sounds(ep), ep.music, ep.seconds, run.dir / "sound.wav", log=log)


def play(ep: Episode, start: int = 0, board_preview: bool = False, window: tuple[int, int] = PLAY_WINDOW,
         log=print) -> str:
    run = _new_run()
    try:
        audio = _sound(ep, run, log)
        pl = playlist(ep, "play", start=start, audio=audio)
        f = run.dir / "playlist.json"
        f.write_text(json.dumps(pl, ensure_ascii=False), encoding="utf-8")
        cmd = command(engine.godot(), "play", f, ep.size, board_preview=board_preview, window=window,
                      prefix=display_prefix("play"))
        return _go(cmd, 24 * 3600, echo=True)
    finally:
        shutil.rmtree(run.dir, ignore_errors=True)


def film(ep: Episode, out: Path, board_preview: bool = False, timeout: float = 3600, log=print) -> Path:
    """The draft MP4: the picture (cards and subtitles on it) and the sound, H.264 + AAC."""
    run = _new_run()
    try:
        audio = _sound(ep, run, log)
        pl = playlist(ep, "film", audio=audio)
        f = run.dir / "playlist.json"
        f.write_text(json.dumps(pl, ensure_ascii=False), encoding="utf-8")
        avi = run.dir / "film.avi"
        cmd = command(engine.godot(), "film", f, ep.size, fps=ep.fps, movie=avi, board_preview=board_preview,
                      prefix=display_prefix("film", size=ep.size))
        said = _go(cmd, timeout)
        if not avi.is_file() or avi.stat().st_size < 1024:
            raise EngineError("the engine did not film the episode:\n" + _tail(said))
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.stem + ".part.mp4")
        p = subprocess.run([mix.ffmpeg(), "-v", "error", "-y", "-i", str(avi), "-t", f"{ep.seconds:.4f}",
                            "-map", "0:v", "-map", "0:a?", "-vf", f"scale={ep.size[0]}:{ep.size[1]}:flags=lanczos",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                            "-movflags", "+faststart", str(tmp)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode != 0 or not tmp.is_file():
            raise EngineError("ffmpeg could not make the MP4: " + p.stderr.strip()[-600:])
        tmp.replace(out)
        return out
    finally:
        shutil.rmtree(run.dir, ignore_errors=True)


class Clock:
    def __init__(self):
        self.t = time.perf_counter()

    def __call__(self) -> float:
        return round(time.perf_counter() - self.t, 2)
