"""JSON FILES OF THE KIT: one way to write them, one way to fingerprint them.

    write_json(path, data)     UTF-8, LF line endings on every system (never CRLF, also on Windows), a final newline.
                               Every JSON file the kit writes goes through it (world.write_json is this one).
    content_sha(data)          the sha-256 of a document's CONTENT: parsed JSON dumped canonically (sorted keys, no
                               spaces, UTF-8), so line endings, indentation and key order never change it.
    file_content_sha(path)     the same for a file on disk.

Why both: git, an editor or another system may turn LF into CRLF in a checkout (or back); a fingerprint of the raw
bytes then says "changed" when nothing did (a fresh clone reported every hero's action check as stale).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def dumps(data: object, indent: int | None = 2) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent) + "\n"


def write_json(path: Path | str, data: object, indent: int | None = 2) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(dumps(data, indent).encode("utf-8"))      # (bytes: no newline translation on any system)
    return p


def canonical(data: object) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_sha(data: object) -> str:
    return hashlib.sha256(canonical(data)).hexdigest()


def file_content_sha(path: Path | str) -> str:
    return content_sha(json.loads(Path(path).read_text(encoding="utf-8")))


def lf(data: bytes) -> bytes:
    """Text bytes with CRLF (and a lone CR) turned into LF."""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
