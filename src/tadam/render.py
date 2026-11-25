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
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tadam import engine, mix
from tadam.engine import EngineError
from tadam.episode import Episode, sounds
from tadam.paths import FONTS, engine_dir
from tadam.jsonfile import write_json

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


def playlist(ep: Episode, mode: str, start: int = 0, snaps: list | None = None, audio: Path | None = None,
             start_at: float = 0.0, paused: bool = False, rev_file: Path | None = None, rev: int = 0) -> dict:
    """What engine/player.gd plays (pure). The window (play) also gets what it needs to stop and say where it
    stands: the names, where every shot begins, where its own script lines begin, the folder for its state."""
    shots = []
    for s in ep.shots:
        shots.append({"id": s.id, "scene": s.dir.as_posix(), "seconds": s.seconds, "frames": s.frames,
                      "card": s.card, "subs": s.subs, "start": s.start, "remark": s.remark,
                      "lines_from": s.lines_from})
    pl = {"mode": mode, "fps": ep.fps, "size": list(ep.size), "start": start,
          "audio": audio.as_posix() if audio else "", "audio_from": ep.shots[start].start if ep.shots else 0.0,
          "fonts": {"text": TEXT_FONT.as_posix(), "italic": ITALIC_FONT.as_posix(), "mono": MONO_FONT.as_posix()},
          "shots": shots, "snaps": snaps or []}
    if mode == "play":
        pl.update({"lang": ep.lang, "names": ep.names, "episode": ep.n, "script_sha": ep.script_sha, "rev": rev,
                   "state_dir": state_dir(ep.world).as_posix(),
                   "start_step": int(round(max(start_at, 0.0) * 60)), "start_paused": bool(paused),
                   "rev_file": rev_file.as_posix() if rev_file else ""})
    return pl


def state_dir(world) -> Path:
    """Where the window writes its pause: state.json, pause.png, mark-<n>.png (and the viewer's library.json)."""
    return world.work_dir() / "player"


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
        write_json(f, pl, indent=None)
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


def _replace(src: Path, dst: Path, tries: int = 20) -> None:
    """src over dst at once (the engine may be reading dst that moment on Windows: a few more tries)."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05)


def world_stamp(world) -> tuple:
    """What changes when the world does: every file's path, size and time, .tadam/ and hidden ones left out."""
    root = Path(world.root)
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for name in files:
            if name.startswith("."):
                continue
            p = Path(dirpath) / name
            try:
                st = p.stat()
            except OSError:
                continue
            out.append((p.relative_to(root).as_posix(), st.st_size, st.st_mtime_ns))
    return tuple(sorted(out))


def clear_state(world) -> None:
    """A new window starts with no pause and no marks (the pictures of the last one go)."""
    d = state_dir(world)
    if not d.is_dir():
        return
    for f in [d / "state.json", d / "pause.png", d / "library.json", *d.glob("mark-*.png")]:
        f.unlink(missing_ok=True)


class Watch:
    """While the window is open: the world changed (Claude edited the script) -> the episode built again, its
    sound mixed again, the playlist written anew and a new number in rev.txt; the window reads it and stands on
    the same shot and second, paused."""

    def __init__(self, ep: Episode, run: Run, rebuild, log=print, every: float = 0.7):
        self.ep, self.run, self.rebuild, self.log, self.every = ep, run, rebuild, log, every
        self.rev = 0
        self.stop = threading.Event()
        self.stamp = world_stamp(ep.world)
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def write(self, ep: Episode, audio: Path | None, start: int = 0, start_at: float = 0.0,
              paused: bool = False) -> Path:
        f = self.run.dir / "playlist.json"
        part = self.run.dir / "playlist.json.part"
        write_json(part, playlist(ep, "play", start=start, audio=audio, start_at=start_at, paused=paused,
                                  rev_file=self.run.dir / "rev.txt", rev=self.rev), indent=None)
        _replace(part, f)
        rv = self.run.dir / "rev.txt.part"
        rv.write_text(str(self.rev), encoding="utf-8")
        _replace(rv, self.run.dir / "rev.txt")
        return f

    def check(self) -> bool:
        """One look at the world; True when the window was given the episode anew."""
        now = world_stamp(self.ep.world)
        if now == self.stamp:
            return False
        if self.stop.wait(0.4) or world_stamp(self.ep.world) != now:
            return False                       # (still being written: next time)
        self.stamp = now
        try:
            ep = self.rebuild()
            audio = mix.render(sounds(ep), ep.music, ep.seconds, self.run.dir / f"sound-{self.rev + 1}.wav",
                               log=lambda *_: None)
        except Exception as e:               # noqa: BLE001 (a script half-written: told, the window keeps on)
            self.log(f"the world changed but cannot be played yet: {e}")
            return False
        self.rev += 1
        self.ep = ep
        self.write(ep, audio)
        self.log(f"the world changed: the window reads episode {ep.n} again (edit {self.rev})")
        return True

    def _loop(self) -> None:
        while not self.stop.wait(self.every):
            self.check()


def play(ep: Episode, start: int = 0, board_preview: bool = False, window: tuple[int, int] = PLAY_WINDOW,
         log=print, start_at: float = 0.0, paused: bool = False, rebuild=None) -> str:
    """The window. `rebuild`: builds the episode again (the window then follows changes in the world)."""
    run = _new_run()
    watch = Watch(ep, run, rebuild or (lambda: ep), log)
    try:
        clear_state(ep.world)
        audio = _sound(ep, run, log)
        f = watch.write(ep, audio, start=start, start_at=start_at, paused=paused)
        cmd = command(engine.godot(), "play", f, ep.size, board_preview=board_preview, window=window,
                      prefix=display_prefix("play"))
        if rebuild is not None:
            watch.thread.start()
        return _go(cmd, 24 * 3600, echo=True)
    finally:
        watch.stop.set()
        if watch.thread.is_alive():
            watch.thread.join(5)
        shutil.rmtree(run.dir, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ around a moment

def around_times(at: float, seconds: float, n: int = 6, span: float = 1.0) -> list[float]:
    """`n` moments of a shot `span` seconds long all told, evenly apart, the moment `at` one of them (a little more
    of what comes after it than before), moved by whole steps to stay inside the shot (pure)."""
    n = max(int(n), 1)
    at = min(max(float(at), 0.0), seconds)
    if n == 1 or span <= 0:
        return [round(at, 3)]
    step = min(float(span), seconds) / (n - 1)
    if step <= 0:
        return [round(at, 3)]
    c = (n - 1) // 2
    first = at - c * step
    while first < -1e-9:
        first += step
    while first + (n - 1) * step > seconds + 1e-9 and first - step >= -1e-9:
        first -= step
    out = []
    for i in range(n):
        t = round(first + i * step, 3) + 0.0      # (never -0.0)
        if 0 <= t <= seconds + 1e-9 and (not out or t > out[-1]):
            out.append(min(t, round(seconds, 3)))
    return out


def make_strip(ep: Episode, shot_id: str, pngs: list[Path], times: list[float], out: Path, at: float | None = None,
               thumb_w: int = 220) -> Path:
    """The frames in a row, each with its second; the one nearest `at` framed."""
    thumb = (thumb_w, int(round(thumb_w * ep.size[1] / ep.size[0])))
    size, corners = sheet_layout(len(pngs), thumb, cols=len(pngs), label=40)
    img = Image.new("RGB", size, BG)
    d = ImageDraw.Draw(img)
    f_sec = ImageFont.truetype(str(MONO_FONT), 17)
    near = min(range(len(times)), key=lambda i: abs(times[i] - at)) if at is not None and times else -1
    for i, (png, t, (x, y)) in enumerate(zip(pngs, times, corners)):
        with Image.open(png) as im:
            img.paste(im.convert("RGB").resize(thumb, Image.LANCZOS), (x, y))
        if i == near:
            d.rectangle([x - 4, y - 4, x + thumb[0] + 3, y + thumb[1] + 3], outline=ACCENT, width=4)
        d.text((x, y + thumb[1] + 8), f"{shot_id} {t:.2f} s", font=f_sec, fill=ACCENT if i == near else INK)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def film(ep: Episode, out: Path, board_preview: bool = False, timeout: float = 3600, log=print) -> Path:
    """The draft MP4: the picture (cards and subtitles on it) and the sound, H.264 + AAC."""
    run = _new_run()
    try:
        audio = _sound(ep, run, log)
        pl = playlist(ep, "film", audio=audio)
        f = run.dir / "playlist.json"
        write_json(f, pl, indent=None)
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
