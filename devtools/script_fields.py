"""Writes skill/reference/script-fields.md: every field of episodes/<n>/script.json (version 2) as the JSON Schema says
it (schema/script.v2.json, exported from the server's contracts): type, required, allowed values, limits.

    python devtools/script_fields.py          (tests/test_skill.py fails when the file is out of date)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "script.v2.json"
OUT = ROOT / "skill" / "reference" / "script-fields.md"

HEAD = """# script.json version 2: every field

Generated from `schema/script.v2.json` (the server's contract) by `devtools/script_fields.py`: do not edit by hand.
What the fields mean and which ones matter: [script.md](script.md). `*` = required.

| Field | Type | Values and limits |
|---|---|---|
"""


def _type(s: dict) -> str:
    if "anyOf" in s:
        return " or ".join(_type(x) for x in s["anyOf"])
    if "const" in s:
        return json.dumps(s["const"])
    t = s.get("type")
    if isinstance(t, list):
        return " or ".join(t)
    if t == "array":
        it = s.get("items")
        return f"list of {_type(it)}" if isinstance(it, dict) else "list"
    if t == "object" and isinstance(s.get("additionalProperties"), dict) and not s.get("properties"):
        return f"map of {_type(s['additionalProperties'])}"
    if s.get("not") is not None:
        return "(set by the server)"
    return t or "any"


def _limits(s: dict) -> str:
    out = []
    if "enum" in s:
        out.append(" / ".join(f"`{v}`" for v in s["enum"]))
    for k, w in (("minimum", ">="), ("exclusiveMinimum", ">"), ("maximum", "<="), ("minLength", "length >="),
                 ("maxLength", "length <="), ("minItems", "items >="), ("maxItems", "items <=")):
        if k in s and not (k == "maximum" and s[k] > 1e15) and not (k == "minimum" and s[k] < -1e15):
            out.append(f"{w} {s[k]}")
    if "pattern" in s:
        out.append(f"pattern `{s['pattern']}`")
    if "propertyNames" in s and "pattern" in s["propertyNames"]:
        out.append(f"keys `{s['propertyNames']['pattern']}`")
    if "default" in s:
        out.append(f"default `{json.dumps(s['default'], ensure_ascii=False)}`")
    if s.get("not") is not None:
        out.append("leave it out")
    return "; ".join(out).replace("|", "\\|")


def rows(s: dict, path: str, required: bool, out: list[str]) -> None:
    out.append(f"| `{path}`{' *' if required else ''} | {_type(s)} | {_limits(s)} |")
    kids = None
    if s.get("type") == "object" and s.get("properties"):
        kids = (s["properties"], set(s.get("required") or []), path)
    elif s.get("type") == "object" and isinstance(s.get("additionalProperties"), dict):
        rows_of(s["additionalProperties"], f"{path}.<key>", out)
        return
    elif s.get("type") == "array" and isinstance(s.get("items"), dict):
        rows_of(s["items"], f"{path}[]", out)
        return
    elif "anyOf" in s:
        for alt in s["anyOf"]:
            if isinstance(alt, dict) and alt.get("type") == "object" and alt.get("properties"):
                kids = (alt["properties"], set(alt.get("required") or []), path)
    if kids:
        for k, v in kids[0].items():
            rows(v, f"{kids[2]}.{k}", k in kids[1], out)


def rows_of(s: dict, path: str, out: list[str]) -> None:
    """The fields of an item (of a list or a map) without a row of its own when it is an object."""
    if s.get("type") == "object" and s.get("properties"):
        req = set(s.get("required") or [])
        for k, v in s["properties"].items():
            rows(v, f"{path}.{k}", k in req, out)
    elif s.get("type") == "array" and isinstance(s.get("items"), dict):
        out.append(f"| `{path}` | {_type(s)} | {_limits(s)} |")
        rows_of(s["items"], f"{path}[]", out)
    else:
        out.append(f"| `{path}` | {_type(s)} | {_limits(s)} |")


def render() -> str:
    s = json.loads(SCHEMA.read_text(encoding="utf-8"))
    out: list[str] = []
    req = set(s.get("required") or [])
    for k, v in s["properties"].items():
        rows(v, k, k in req, out)
    return HEAD + "\n".join(out) + "\n"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8", newline="\n")
    print(OUT.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
