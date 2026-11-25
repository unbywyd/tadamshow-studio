"""OpenCV pictures to and from files through Python's own file handling: cv2.imread / cv2.imwrite cannot open a path
with non-latin letters on Windows (a world folder called «мой мир» is normal here)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def imwrite(path, img, params=()) -> bool:
    ok, buf = cv2.imencode(Path(path).suffix or ".png", img, list(params))
    if ok:
        Path(path).write_bytes(buf.tobytes())
    return bool(ok)


def imread(path, flags=cv2.IMREAD_COLOR):
    try:
        data = np.frombuffer(Path(path).read_bytes(), np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, flags)
