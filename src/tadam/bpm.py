"""The BEAT of a piece of music: its tempo and where the first beat falls (on this computer, numpy only).
usage: python -m tadam.bpm <music file> [--scene <scene folder>]
  prints "bpm offset"; with --scene writes them into that scene's "music": {"file", "bpm", "offset"}.
A scene line { "beat": 17, ... } then happens on the 17th beat (beat 1 is at "offset" seconds), and a dance started
on a beat goes at the music's tempo (stage.gd). Songs with a steady beat are found well; if the number is off by
twice or half, write the right one into the scene by hand ("bpm" is only a number).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 11025
HOP = 256


def ffmpeg() -> str:
    """ffmpeg from PATH (tadam doctor says where to get it)."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg is not on PATH: run `tadam doctor`")
    return exe


def audio(path):
    raw = subprocess.run([ffmpeg(), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


def onsets(x):
    """How much louder each moment gets (spectral flux): peaks where notes and drums start."""
    win = np.hanning(1024)
    n = (len(x) - 1024) // HOP
    spec = np.abs(np.stack([np.fft.rfft(x[i * HOP:i * HOP + 1024] * win) for i in range(n)]))
    spec = np.log1p(100 * spec)
    flux = np.maximum(np.diff(spec, axis=0), 0).sum(axis=1)
    flux -= np.convolve(flux, np.ones(16) / 16, mode="same")       # (only the rises, not the loudness)
    return np.maximum(flux, 0)


def tempo(env):
    rate = SR / HOP                                                 # onset frames a second
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    best, bpm = -1.0, 120.0
    for b in np.arange(60, 181, 0.5):
        lag = rate * 60 / b
        # the beat, its double and its half all line up for the true tempo; a slight preference for 90-140
        score = sum(np.interp(lag * k, np.arange(len(ac)), ac) for k in (1, 2, 4)) * (1.0 if 90 <= b <= 140 else 0.9)
        if score > best:
            best, bpm = score, b
    period = rate * 60 / bpm
    # where the beats fall: the shift of an even grid that catches the most onset strength
    shifts = np.arange(0, period, 0.5)
    sums = [env[np.round(np.arange(s, len(env) - 1, period)).astype(int)].sum() for s in shifts]
    # (a rise is seen as soon as the note enters the analysis window, a window's length before it is heard)
    offset = (shifts[int(np.argmax(sums))] / rate + 1024 / SR) % (60 / bpm)
    return float(bpm), float(round(offset, 3))


def main():
    f = Path(sys.argv[1])
    bpm, offset = tempo(onsets(audio(f)))
    print(f"{bpm:g} {offset:g}")
    if "--scene" in sys.argv:
        p = Path(sys.argv[sys.argv.index("--scene") + 1]) / "scene.json"
        spec = json.loads(p.read_text(encoding="utf-8"))
        m = spec.get("music", {})
        m = {"file": m} if isinstance(m, str) else m
        m.setdefault("file", f.name)
        m["bpm"], m["offset"] = bpm, offset
        spec["music"] = m
        p.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        print("written to", p)


if __name__ == "__main__":
    main()
