"""Pictures to and from files.

OpenCV through Python's own file handling: cv2.imread / cv2.imwrite cannot open a path with non-latin letters on
Windows (a world folder called «мой мир» is normal here).

COMPACT PNG (`save_png`, `compact_png`): every picture the kit keeps in a world is a PNG saved small WITHOUT any
visible change: a fully transparent pixel (never seen; an image model leaves noise there) takes the colour of the
nearest visible one (what the eye could ever get from it: a scaled picture blends an edge with its neighbours, so
they keep the edge's colour, not black), an alpha channel that is opaque everywhere is dropped, and the file is
deflated as hard as Pillow can. Every pixel anyone can see stays exactly as it was (the tests compare them). The names stay .png: the engine loads a
puppet's parts as PNG only (engine/puppet.gd), and the server shows portrait.png and sheet.png by those names.
"""
from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


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


def compact(im: Image.Image) -> Image.Image:
    """The same picture to the eye, cheaper to store (see the module's header)."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        a = np.array(im.convert("RGBA"))
        alpha = a[..., 3]
        if alpha.min() == 255:
            return Image.fromarray(a[..., :3], "RGB")
        hidden = alpha == 0
        if hidden.any() and not hidden.all():
            from scipy import ndimage
            iy, ix = ndimage.distance_transform_edt(hidden, return_distances=False, return_indices=True)
            a[..., :3] = a[iy, ix, :3]
        return Image.fromarray(a, "RGBA")
    if im.mode in ("RGB", "L", "P"):
        return im
    return im.convert("RGB")


def _deflated(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def png_bytes(im: Image.Image) -> bytes:
    """The smallest of the picture as it is and compact(), both deflated hard (they look the same)."""
    return min(_deflated(im), _deflated(compact(im)), key=len)


def save_png(im: Image.Image, path) -> Path:
    """Save `im` as a compact PNG at `path`."""
    p = Path(path)
    p.write_bytes(png_bytes(im))
    return p


def compact_png(path) -> tuple[int, int]:
    """Make the PNG file at `path` compact, in place (only when that is smaller). Returns (bytes before, after)."""
    p = Path(path)
    before = p.stat().st_size
    with Image.open(p) as im:
        im.load()
        data = png_bytes(im)
    if len(data) < before:
        p.write_bytes(data)
        return before, len(data)
    return before, before


def write_png_bytes(data: bytes, path) -> Path:
    """PNG bytes from an image model, kept compact at `path`."""
    p = Path(path)
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        out = png_bytes(im)
    p.write_bytes(out if len(out) < len(data) else data)
    return p
