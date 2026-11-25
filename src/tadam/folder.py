"""THE WORLD FOLDER AS THE SERVER SEES IT: which files are sent and their manifest (path -> sha-256, bytes).

The paths follow the server's rules exactly (apps/api services/studio/paths.ts, checkPath): relative, `/`, latin
letters, digits, `- _ .`, no segment starting or ending with a dot, at most 8 levels, a known kind of file in its
place of the layout:

    world.json · sources.json · cover.<png|webp|jpg|jpeg>
    heroes/<slug>/hero.json · heroes/<slug>/puppet/** (png, webp, json; at most 3 levels inside puppet/)
    sets/<slug>/** (png, webp, jpg, jpeg, json)
    media/** (png, webp, jpg, jpeg, mp3, wav, ogg)
    episodes/<n>/script.json · episodes/<n>/episode.json · episodes/<n>/cover.<png|webp|jpg|jpeg>

Everything else stays on this computer and is never sent: .tadam/ (the kit's own working files), hidden files, the
puppet's check pictures (check.jpg, _poses.jpg) and logs, notes, `<file>.server` copies left by a pull.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

EXT = {"png": "png", "webp": "webp", "jpg": "jpeg", "jpeg": "jpeg", "mp3": "mp3", "wav": "wav", "ogg": "ogg",
       "json": "json"}
IMAGES = {"png", "webp", "jpeg"}
SOUNDS = {"mp3", "wav", "ogg"}
WORLD_PATH = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}(?:/[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}){0,7}$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.I)
DOUBLE_EXT = re.compile(r"\.(lnk|url|exe|bat|cmd|sh|ps1|js|html?|svg|desktop)\.", re.I)
MAX_FILES = 5000
CHUNK = 1 << 20


def _slug_ok(s: str | None) -> bool:
    return bool(s) and bool(SLUG.match(s)) and len(s) <= 60


def why_not(p: str) -> str | None:
    """None if the server takes this path, else why not (the server's checkPath, word for word where it matters)."""
    if not p:
        return "empty path"
    if len(p) > 300:
        return "path too long"
    if any(ord(c) < 32 or ord(c) == 127 for c in p):
        return "control characters"
    if "\\" in p:
        return "backslash: use /"
    if ":" in p:
        return 'no ":"'
    if p.startswith("/"):
        return "absolute path"
    if "%" in p:
        return 'no "%"'
    segs = p.split("/")
    if any(s == "" for s in segs):
        return "empty segment (//)"
    if any(s in (".", "..") for s in segs):
        return '"." or ".." segment'
    if any(s.startswith(".") for s in segs):
        return "hidden file or folder"
    if any(s.endswith(".") for s in segs):
        return 'a segment ending with "."'
    if any(RESERVED.match(s) for s in segs):
        return "a name Windows reserves (con, nul, com1...)"
    if not WORLD_PATH.match(p):
        return "only latin letters, digits, - _ . and / (at most 8 levels)"
    m = re.search(r"\.([a-z0-9]+)$", p)
    kind = EXT.get(m.group(1)) if m else None
    if not kind:
        return "this kind of file is not sent (only png, webp, jpg, mp3, wav, ogg, json; lowercase extension)"
    if DOUBLE_EXT.search(p):
        return "a double extension"
    if not _placed(segs, kind):
        return "not a place of the world folder layout"
    return None


def _placed(segs: list[str], kind: str) -> bool:
    top = segs[0]
    if len(segs) == 1:
        return top in ("world.json", "sources.json") or bool(re.match(r"^cover\.(png|webp|jpe?g)$", top))
    a = segs[1]
    b = segs[2] if len(segs) > 2 else None
    rest = segs[3:]
    if top == "heroes" and _slug_ok(a):
        if len(segs) == 3 and b == "hero.json":
            return True
        return b == "puppet" and 1 <= len(rest) <= 3 and kind in ("json", "png", "webp")
    if top == "sets" and _slug_ok(a) and b and len(segs) <= 5:
        return kind == "json" or kind in IMAGES
    if top == "media" and len(segs) <= 5:
        return kind in IMAGES or kind in SOUNDS
    if top == "episodes" and re.match(r"^[1-9][0-9]{0,3}$", a) and len(segs) == 3:
        return b in ("script.json", "episode.json") or bool(re.match(r"^cover\.(png|webp|jpe?g)$", b or ""))
    return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Scan:
    manifest: dict[str, dict] = field(default_factory=dict)   # path -> {sha256, bytes}
    local_only: list[tuple[str, str]] = field(default_factory=list)   # (path, why it is not sent)
    empty: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)            # symbolic links (never followed, never sent)
    server_copies: list[str] = field(default_factory=list)    # <file>.server left by a pull, not merged yet
    case_clashes: list[str] = field(default_factory=list)


def scan(root: Path) -> Scan:
    """Walk the world folder (not .tadam/, not hidden folders) and sort every file: sent or kept here."""
    root = Path(root)
    out = Scan()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        d = Path(dirpath)
        rel_dir = d.relative_to(root).as_posix()
        keep = []
        for n in sorted(dirnames):
            if n.startswith(".") or (d / n).is_symlink():
                if (d / n).is_symlink():
                    out.links.append(n if rel_dir == "." else f"{rel_dir}/{n}")
                continue
            keep.append(n)
        dirnames[:] = keep
        for n in sorted(filenames):
            rel = n if rel_dir == "." else f"{rel_dir}/{n}"
            f = d / n
            if f.is_symlink():
                out.links.append(rel)
                continue
            if n.endswith(".server"):
                out.server_copies.append(rel)
                continue
            if n.startswith("."):
                continue                           # (.DS_Store and the like: not part of the world)
            why = why_not(rel)
            if why:
                out.local_only.append((rel, why))
                continue
            size = f.stat().st_size
            if size == 0:
                out.empty.append(rel)
                continue
            out.manifest[rel] = {"sha256": sha256_file(f), "bytes": size}
    seen: dict[str, str] = {}
    for p in sorted(out.manifest):
        k = p.lower()
        if k in seen and seen[k] != p:
            out.case_clashes.append(p)
        seen.setdefault(k, p)
    return out


def manifest(root: Path) -> dict[str, dict]:
    return scan(root).manifest
