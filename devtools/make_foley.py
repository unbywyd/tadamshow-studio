"""FOLEY, synthesized here (free; can be swapped for recorded sounds later):
  engine/sounds/tick.wav        a wall clock: tick-tock, 4 seconds (loops)
  engine/sounds/typewriter.wav  a few typewriter key clacks and a carriage bell
  room tone (room()): a low hum, faint distant traffic, 30 seconds; written only with --room <out.wav>
usage: python devtools/make_foley.py
"""
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000
ROOT = Path(__file__).resolve().parent.parent
rng = np.random.default_rng(7)


def save(p: Path, x: np.ndarray) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    x = np.clip(x, -1, 1)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def click(dur=0.03, freq=2600, decay=180, noise=0.6, amp=0.6):
    t = np.arange(int(SR * dur)) / SR
    env = np.exp(-t * decay)
    return amp * env * ((1 - noise) * np.sin(2 * np.pi * freq * t) + noise * rng.uniform(-1, 1, t.size))


def lowpass(x, k=60):
    return np.convolve(x, np.ones(k) / k, mode="same")


def tick():
    out = np.zeros(SR * 4)
    for i in range(8):     # tick, tock: a slightly different pitch, a wooden case under it
        c = click(0.06, 2200 if i % 2 == 0 else 1700, 120, 0.5, 0.5) + click(0.06, 420, 60, 0.0, 0.25)
        s = int(i * 0.5 * SR)
        out[s:s + c.size] += c
    return out


def typewriter():
    out = np.zeros(int(SR * 2.6))
    t = 0.05
    while t < 2.0:          # uneven key strokes
        c = click(0.05, rng.uniform(1500, 2400), 140, 0.75, 0.55) + click(0.05, 300, 50, 0.0, 0.3)
        s = int(t * SR)
        out[s:s + c.size] += c
        t += rng.uniform(0.09, 0.22)
    tt = np.arange(int(SR * 0.6)) / SR   # the bell at the end of the line
    bell = 0.25 * np.exp(-tt * 6) * (np.sin(2 * np.pi * 1975 * tt) + 0.5 * np.sin(2 * np.pi * 3950 * tt))
    s = int(2.0 * SR)
    out[s:s + bell.size] += bell
    return out


def room():
    n = SR * 30
    brown = np.cumsum(rng.normal(0, 1, n)); brown -= lowpass(brown, 4000); brown /= np.abs(brown).max()
    t = np.arange(n) / SR
    hum = 0.15 * np.sin(2 * np.pi * 50 * t) + 0.07 * np.sin(2 * np.pi * 100 * t)
    traffic = lowpass(rng.normal(0, 1, n), 200) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 11.0) ** 2)
    x = 0.5 * brown + hum * 0.4 + 0.6 * traffic / np.abs(traffic).max()
    fade = np.minimum(1, np.minimum(t, t[-1] - t) / 1.0)          # (soft ends: it loops)
    return 0.5 * x / np.abs(x).max() * fade


save(ROOT / "engine/sounds/tick.wav", tick())
save(ROOT / "engine/sounds/typewriter.wav", typewriter())
if "--room" in sys.argv:
    save(Path(sys.argv[sys.argv.index("--room") + 1]), room())
print("ok")
