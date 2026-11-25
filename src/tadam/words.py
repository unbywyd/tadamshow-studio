"""THE WORD CHECK (studio-tz 3.5а «Что проверяет код»), the server's own rules (contracts words.ts, services/studio/
content.ts) applied to the same files with the same list, schema/bad-words.json, copied from the contracts:

  1. the text is lowercased and ё becomes е;
  2. words are the runs of [a-zа-я0-9];
  3. a word matches a pattern when the WHOLE word matches it;
  4. `{P}` in a pattern stands for an optional Russian prefix (`prefixes.ru`).

`error` `bad_word` = swearing and slurs (the check fails, the episode cannot be submitted); `warning`
`borderline_word` = insults, adult themes, politics, drugs (the owner looks at them). `where` = `file#json.path`,
as the server writes it. A help to the owner's eyes, not a replacement.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from tadam.issues import Issue
from tadam.paths import schema_dir

WORD = re.compile(r"[a-zа-я0-9]+")
TOPIC = {"swearing": "swearing", "slur": "a slur", "insult": "an insult", "adult": "adult content",
         "politics": "politics", "drugs": "drugs"}
MAX_ISSUES = 200


@lru_cache(maxsize=None)
def _rules() -> list[tuple[str, str, re.Pattern]]:
    data = json.loads((schema_dir() / "bad-words.json").read_text(encoding="utf-8"))
    p = "(?:" + "|".join(data["prefixes"]["ru"]) + ")?"
    return [(r["level"], r["topic"], re.compile("^(?:" + x.replace("{P}", p) + ")$"))
            for r in data["rules"] for x in r["patterns"]]


def find_words(text: str) -> list[dict]:
    """The words of a text the list names: [{level, topic, word}], each word once, errors first."""
    seen: dict[str, None] = {}
    for w in WORD.findall(text.lower().replace("ё", "е")):
        seen.setdefault(w)
    out = []
    for w in seen:
        rules = _rules()
        hit = next((r for r in rules if r[0] == "error" and r[2].match(w)), None) or \
            next((r for r in rules if r[2].match(w)), None)
        if hit:
            out.append({"level": hit[0], "topic": hit[1], "word": w})
    return sorted(out, key=lambda h: 0 if h["level"] == "error" else 1)


def _strings(v: object, path: str) -> Iterator[tuple[str, str]]:
    """Every string of a JSON value with its path (a.b[2].c), `$schema` left out."""
    if isinstance(v, str):
        yield path, v
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from _strings(x, f"{path}[{i}]")
    elif isinstance(v, dict):
        for k, x in v.items():
            if k != "$schema":
                yield from _strings(x, f"{path}.{k}" if path else str(k))


def word_issues(file: str, value: object) -> list[Issue]:
    out = []
    for path, text in _strings(value, ""):
        for h in find_words(text):
            where = file + (f"#{path}" if path else "")
            if h["level"] == "error":
                out.append(Issue("error", where, "bad_word", f"«{h['word']}» is {TOPIC[h['topic']]}: the house rules "
                                                             "(2. clean content) do not allow it"))
            else:
                out.append(Issue("warning", where, "borderline_word",
                                 f"«{h['word']}» may be {TOPIC[h['topic']]}: the owner will look at it"))
    return out


def _json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None                      # (an unreadable file is reported by the check itself)


def check_words(root: Path, episodes: list[str] | None = None) -> list[Issue]:
    """The words of world.json, every hero.json, every set's name and the episodes' episode.json and script.json
    (all of them, or these)."""
    root = Path(root)
    out = word_issues("world.json", _json(root / "world.json"))
    for d in sorted((root / "heroes").glob("*/hero.json")):
        out += word_issues(f"heroes/{d.parent.name}/hero.json", _json(d))
    for d in sorted((root / "sets").glob("*/set.json")):
        s = _json(d)
        if isinstance(s, dict) and s.get("name"):
            out += word_issues(f"sets/{d.parent.name}/set.json#name", s["name"])
    eps = episodes if episodes is not None else sorted(
        (p.name for p in (root / "episodes").glob("*") if p.is_dir()), key=lambda n: (len(n), n))
    for n in eps:
        for f in ("episode.json", "script.json"):
            v = _json(root / "episodes" / str(n) / f)
            if v is not None:
                out += word_issues(f"episodes/{n}/{f}", v)
    return out[:MAX_ISSUES]
