"""THE SOUND OF A DRAFT: one track for the whole episode, mixed by ffmpeg the way the server mixes a film's sound
(apps/api worker/film_worker.py `mix`, after the lab's tools/shots.py), only with no recorded lines:

  - a line with no recording is silent (it is a subtitle), but it is TALK all the same: the music keeps out of it;
  - the narrator (a file from the narration bridge) and the songs of their shots, where the shots say;
  - the film's tune (film.music) in every pause between the talking, at least `min_gap` long, faded in and out;
  - the place's own sound (film.music.ambience) under the whole film.

`graph()` is pure (tests read the filter it builds); `render()` runs ffmpeg. A file ffmpeg cannot read is left out
with a note, so a broken tune does not stop a draft.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class MixError(RuntimeError):
    pass


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise MixError("ffmpeg is not on PATH: run `tadam doctor`")
    return exe


def duration(path: Path) -> float | None:
    """Seconds of a sound file (ffprobe), or None when it cannot be read."""
    exe = shutil.which("ffprobe")
    if not exe:
        raise MixError("ffprobe is not on PATH: run `tadam doctor`")
    p = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        d = float(p.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return None
    return d if d > 0 else None


@dataclass
class ShotSound:
    start: float                      # seconds from the film's start
    seconds: float
    talk: list = field(default_factory=list)     # [[a, b], ...] seconds of the shot: someone says a line
    quiet: bool = False
    song: dict | None = None          # {file (absolute), db, from, fade_in, fade_out}
    narrator: dict | None = None      # {file (absolute), at, db, seconds}


def graph(shots: list[ShotSound], music: dict | None, total: float, lengths: dict) -> tuple[list[str], str] | None:
    """(ffmpeg input arguments, filter graph ending in [a]) or None when there is nothing to hear.
    `lengths`: file -> seconds (for songs and the narrator)."""
    inputs: list[str] = []
    chains: list[str] = []
    labels: list[str] = []
    talk: list[list[float]] = []

    def add_input(*a) -> int:
        inputs.extend(str(x) for x in a)
        return inputs.count("-i") - 1

    songs = []
    for s in shots:
        talk += [[s.start + a, s.start + b] for a, b in s.talk]
        if s.quiet or s.song:
            talk.append([s.start, s.start + s.seconds])
        if s.song and s.song.get("file") in lengths:
            songs.append((s.start, s.seconds, s.song))
        if s.narrator and s.narrator.get("file") in lengths:
            v = s.narrator
            va, vn = s.start + float(v.get("at", 0.5)), lengths[v["file"]]
            talk.append([va, va + vn])
            songs.append((va, vn, {"file": v["file"], "from": 0, "db": float(v.get("db", 0)), "fade_in": 0.01,
                                   "fade_out": 0.05}))
    for k, (t0, n, sg) in enumerate(songs):
        sd = lengths[sg["file"]]
        a = float(sg.get("from", 0))
        a = max(sd + a, 0.0) if a < 0 else a
        sfo = float(sg.get("fade_out", 1.0))
        i = add_input("-i", sg["file"])
        ms = int(t0 * 1000)
        chains.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,atrim={a}:{min(a + n, sd)},"
                      f"asetpts=PTS-STARTPTS,volume={float(sg.get('db', -6))}dB,afade=t=in:d={float(sg.get('fade_in', 0.05))},"
                      f"afade=t=out:st={max(n - sfo, 0):.3f}:d={sfo},adelay={ms}|{ms}[s{k}]")
        labels.append(f"[s{k}]")
    m = music or {}
    if m.get("file") in lengths:
        pb, pa = float(m.get("pad_before", 0.3)), float(m.get("pad_after", 0.25))
        merged: list[list[float]] = []
        for a, b in sorted([max(a - pb, 0.0), b + pa] for a, b in talk):
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        gaps, t = [], 0.0
        for a, b in merged + [[total, total]]:
            if a - t >= float(m.get("min_gap", 0.6)):
                gaps.append((t, a))
            t = max(t, b)
        fi, fo = float(m.get("fade_in", 0.06)), float(m.get("fade_out", 0.35))
        start, db = float(m.get("start", 0)), float(m.get("db", -12))
        for g, (a, b) in enumerate(gaps):
            n = b - a
            i = add_input("-i", m["file"])
            ms = int(a * 1000)
            chains.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,atrim={start}:{start + n},"
                          f"asetpts=PTS-STARTPTS,volume={db}dB,afade=t=in:d={fi},"
                          f"afade=t=out:st={max(n - fo, 0):.3f}:d={fo},adelay={ms}|{ms}[m{g}]")
            labels.append(f"[m{g}]")
    amb = m.get("ambience") if isinstance(m.get("ambience"), dict) else None
    if amb and amb.get("file") in lengths:
        i = add_input("-stream_loop", "-1", "-i", amb["file"])
        chains.append(f"[{i}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
                      f"volume={float(amb.get('db', -26))}dB,afade=t=in:d=1.0,afade=t=out:st={max(total - 1.0, 0):.3f}:d=1.0[amb]")
        labels.append("[amb]")
    if not labels:
        return None
    # a silent bed exactly as long as the film first: amix ends with it (duration=first)
    chains.insert(0, f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.4f},asetpts=PTS-STARTPTS[bed]")
    g = ";".join(chains) + f";[bed]{''.join(labels)}amix=inputs={len(labels) + 1}:normalize=0:duration=first,atrim=0:{total:.4f}[a]"
    return inputs, g


def render(shots: list[ShotSound], music: dict | None, total: float, out: Path, log=print) -> Path | None:
    """The episode's sound as a WAV (48 kHz stereo), or None when there is nothing to hear."""
    files = set()
    for s in shots:
        for x in (s.song, s.narrator):
            if x and x.get("file"):
                files.add(x["file"])
    m = music or {}
    for x in (m, m.get("ambience") if isinstance(m.get("ambience"), dict) else None):
        if x and x.get("file"):
            files.add(x["file"])
    lengths = {}
    for f in sorted(files):
        d = duration(Path(f))
        if d is None:
            log(f"note: {Path(f).name} cannot be read as sound: left out of the draft")
        else:
            lengths[f] = d
    g = graph(shots, music, total, lengths)
    if g is None:
        return None
    inputs, flt = g
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([ffmpeg(), "-v", "error", "-y", *inputs, "-filter_complex", flt, "-map", "[a]",
                        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(out)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0 or not out.is_file():
        raise MixError("mixing the sound failed: " + p.stderr.strip()[-600:])
    return out
