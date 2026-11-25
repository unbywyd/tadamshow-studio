"""WHERE EVERY PICTURE AND SOUND COMES FROM: sources.json at the root of the world folder (studio-tz 3.5а; the
server's services/studio/content.ts, schema/sources.json):

    {"version": 1, "files": {
        "heroes/cow/puppet/": {"source": "generated", "tool": "gpt-image-2.5-flare"},
        "media/theme.mp3":    {"source": "licensed", "licence": "CC BY 4.0", "url": "https://…", "author": "…"},
        "cover.png":          {"source": "own"}}}

A key is a file of the folder or a folder ending with "/"; the longest key that covers a file wins, so a folder can
say "generated" and one file in it "own". Every png / webp / jpg / mp3 / wav / ogg the push sends needs a source:
`no_sources` (no sources.json at all) and `no_source` (per file, 40 listed) are errors; a key that names nothing is a
`source_unused` warning. The same codes, levels and words as the server.

`declare()` is how the kit's own makers record what they made (`tadam hero make` → the puppet folder is
"generated" with the model; `--mannequin` / `--placeholder` → "own", drawn by the kit's code).
"""
from __future__ import annotations

import json
from pathlib import Path

from tadam import folder, schema
from tadam.issues import Issue

FILE = "sources.json"
MAX_LISTED = 40
HOW = ('add it to sources.json: { "source": "own" } / { "source": "generated", "tool": "<service or model>" } / '
       '{ "source": "licensed", "licence": "<name>", "url": "<link>" } (a folder key ending with "/" covers every '
       'file in it)')
STARTER = {"version": 1, "files": {}}


def kind(path: str) -> str | None:
    """image / audio / None, by the extension (the server's file types)."""
    ext = folder.EXT.get(path.rsplit(".", 1)[-1]) if "." in path else None
    return "image" if ext in folder.IMAGES else "audio" if ext in folder.SOUNDS else None


def load(root: Path) -> tuple[dict | None, list[Issue]]:
    """(sources.json when it fits its schema else None, the problems with it)."""
    f = Path(root) / FILE
    if not f.is_file():
        return None, []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, [Issue("error", FILE, "json_invalid", f"cannot be read: {e}")]
    bad = schema.validate("sources", data)
    if bad:
        return None, [Issue("error", FILE + ("" if p == "(top)" else f"#{p}"), "schema", m) for p, m in bad[:20]]
    return data, []


def source_of(sources: dict | None, path: str) -> dict | None:
    """The source of one file: the file's own key, else the longest folder key that holds it."""
    if not sources:
        return None
    files = sources.get("files") or {}
    if path in files:
        return files[path]
    best = None
    for k in files:
        if k.endswith("/") and path.startswith(k) and (best is None or len(k) > len(best)):
            best = k
    return files[best] if best else None


def check(root: Path, paths: list[str] | None = None) -> list[Issue]:
    """Every picture and sound the push would send has a source. `paths`: the folder's sent files (default: scan)."""
    root = Path(root)
    if paths is None:
        paths = list(folder.scan(root, hashing=False).manifest)
    sources, out = load(root)
    media = sorted(p for p in paths if kind(p))
    missing = [p for p in media if not source_of(sources, p)]
    if missing and FILE not in paths:
        out.append(Issue("error", FILE, "no_sources", f"the folder has no sources.json: {len(missing)} picture(s) and "
                                                      f"sound(s) have no source; {HOW}"))
    for p in missing[:MAX_LISTED]:
        out.append(Issue("error", p, "no_source", f"{p} has no source: {HOW}"))
    if len(missing) > MAX_LISTED:
        out.append(Issue("error", FILE, "no_source", f"and {len(missing) - MAX_LISTED} more file(s) without a source"))
    names = set(paths)
    for k in (sources or {}).get("files") or {}:
        hit = any(p.startswith(k) for p in media) if k.endswith("/") else k in names
        if not hit:
            out.append(Issue("warning", f"sources.json#files.{k}", "source_unused", f"{k} is not in the folder"))
    return out


def write(root: Path, data: dict) -> Path:
    f = Path(root) / FILE
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return f


def starter(root: Path) -> Path | None:
    """A new world's sources.json (nothing declared yet); an existing one is left alone."""
    if (Path(root) / FILE).exists():
        return None
    return write(root, dict(STARTER, files={}))


def declare(root: Path, key: str, source: dict, replace: bool = False) -> bool:
    """Record the source of a file or a folder ("<folder>/") the kit just made. An existing entry is kept unless
    `replace`. Returns True when sources.json changed. Never raises over an unreadable sources.json (the check
    reports it); it is then left as it is."""
    assert not schema.validate("sources", {"version": 1, "files": {key: source}}), (key, source)
    root = Path(root)
    f = root / FILE
    if f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not (isinstance(data, dict) and isinstance(data.get("files"), dict)):
            return False
    else:
        data = dict(STARTER, files={})
    if key in data["files"] and (not replace or data["files"][key] == source):
        return False
    data["files"][key] = source
    write(root, data)
    return True
