"""Copies the server's JSON Schemas and the word list into the kit's schema/ (they are never written by hand):

    python devtools/refresh_schemas.py <contracts>

<contracts> is a checkout of the server's repository, its packages/contracts folder, or that folder's schemas/
(run `pnpm --filter @tadamshow/contracts schemas` there first). Every *.json of it is copied (the schemas and
bad-words.json); a schema the contracts no longer have is removed from schema/ (README.md stays). Then
skill/reference/script-fields.md is written again from the new script.v2.json. Prints what changed.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "schema"


def source_dir(arg: str) -> Path:
    p = Path(arg).expanduser().resolve()
    for cand in (p, p / "schemas", p / "packages" / "contracts" / "schemas"):
        if cand.is_dir() and (cand / "script.v2.json").is_file() and (cand / "bad-words.json").is_file():
            return cand
    raise SystemExit(f"no contracts schemas under {p} (looked for schemas/script.v2.json and bad-words.json)")


def refresh(src: Path, dest: Path = DEST) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"added": [], "changed": [], "removed": [], "same": []}
    names = sorted(f.name for f in src.glob("*.json"))
    for n in names:
        data = (src / n).read_bytes()
        json.loads(data.decode("utf-8"))                  # (a broken file is not copied)
        old = dest / n
        if not old.exists():
            out["added"].append(n)
        elif old.read_bytes() != data:
            out["changed"].append(n)
        else:
            out["same"].append(n)
            continue
        old.write_bytes(data)
    for f in sorted(dest.glob("*.json")):
        if f.name not in names:
            f.unlink()
            out["removed"].append(f.name)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    res = refresh(source_dir(argv[0]))
    for k in ("added", "changed", "removed"):
        if res[k]:
            print(f"{k}: {', '.join(res[k])}")
    print(f"{len(res['same'])} unchanged; schema/ now has {len(list(DEST.glob('*.json')))} files")
    spec = importlib.util.spec_from_file_location("script_fields", ROOT / "devtools" / "script_fields.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = ROOT / "skill" / "reference" / "script-fields.md"
    text = mod.render()
    if out.read_text(encoding="utf-8") != text:
        out.write_text(text, encoding="utf-8", newline="\n")
        print("skill/reference/script-fields.md written again")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
