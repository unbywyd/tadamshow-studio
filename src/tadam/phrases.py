"""PHRASES of a recorded voice: where each one starts and ends, found by the pauses between them (loudness only, on
this computer; no words are recognised, nothing is sent anywhere).
usage: python -m tadam.phrases <clip (head.ogv, mouth.ogv, any audio or video)> [--show]
  -> <clip>.phrases.json: [[start, end], ...] seconds. A scene line { "phrase": 3, "who": "hag" } happens as that
     hero's third phrase begins ({ "phrase": 3, "end": true }: as it ends; "delay": seconds after that).
A phrase is speech with no pause longer than GAP inside it; a sound shorter than SHORTEST is not one (a cough, a
click). Speech is what is louder than the quiet of this recording by LOUDER dB.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from tadam.jsonfile import write_json

SR = 16000
FRAME = 0.02          # seconds
GAP = 0.35            # a pause this long ends a phrase
SHORTEST = 0.25       # seconds: shorter is not a phrase
LOUDER = 14.0         # dB over the quiet


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


def phrases(x):
    n = int(SR * FRAME)
    frames = x[:len(x) // n * n].reshape(-1, n)
    db = 10 * np.log10(np.mean(frames ** 2, axis=1) + 1e-10)
    quiet = np.percentile(db, 10)
    loud = np.percentile(db, 95)
    # (a recording that is all speech: the line is between the quiet and the loud, not above the quiet only)
    line = min(quiet + LOUDER, (quiet + loud) / 2)
    on = db > line
    out = []
    start = None
    last = None
    for i, v in enumerate(on):
        t = i * FRAME
        if v:
            if start is None:
                start = t
            last = t + FRAME
        elif start is not None and t - last >= GAP:
            out.append([start, last])
            start = None
    if start is not None:
        out.append([start, last])
    return [[round(a, 2), round(b, 2)] for a, b in out if b - a >= SHORTEST]


def write(clip) -> list:
    """<clip>.phrases.json next to the clip; returns the phrases."""
    clip = Path(clip)
    ph = phrases(audio(clip))
    write_json(clip.with_name(clip.name + ".phrases.json"), ph, indent=None)
    return ph


def main():
    clip = Path(sys.argv[1])
    ph = write(clip)
    out = clip.with_name(clip.name + ".phrases.json")
    print(f"{len(ph)} phrases -> {out}")
    if "--show" in sys.argv:
        for i, (a, b) in enumerate(ph, 1):
            print(f"  {i:2d}: {a:6.2f} - {b:6.2f}")


if __name__ == "__main__":
    main()
