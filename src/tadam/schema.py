"""The JSON Schemas of the world folder and the script (schema/*.json, exported from the server's contracts: never
edited by hand) and validation against them."""
from __future__ import annotations

import json
from functools import lru_cache

from jsonschema import Draft202012Validator

from tadam.paths import schema_dir


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    """schema/<name>.json ("world", "hero", "script.v2", ...)."""
    return json.loads((schema_dir() / f"{name}.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(load(name))


def json_path(path) -> str:
    """["shots", 2, "say"] -> "shots[2].say"."""
    out = ""
    for p in path:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out


def validate(name: str, data: object) -> list[tuple[str, str]]:
    """[(json path, message)] for every way `data` breaks schema/<name>.json; [] when it fits."""
    errors = sorted(_validator(name).iter_errors(data), key=lambda e: (list(map(str, e.absolute_path)), e.message))
    out = []
    for e in errors:
        msg = e.message
        if e.validator == "not":                  # (the schemas forbid only the server's own fields this way)
            msg = "this field is set by the server: leave it out"
        out.append((json_path(e.absolute_path) or "(top)", msg[:500]))
    return out
