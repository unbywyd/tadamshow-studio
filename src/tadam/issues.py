"""One finding of a check: {level, where, code, message} (schema/check-result.json). Shared by every check."""
from __future__ import annotations

from dataclasses import asdict, dataclass

LEVELS = ("error", "warning", "info")


@dataclass(frozen=True)
class Issue:
    level: str          # error | warning | info
    where: str          # a file and a place in it: "episodes/1/script.json shots[2] (sh3)"
    code: str           # stable, machine-readable: "say_unknown"
    message: str        # plain words: what is wrong and what to do

    def as_dict(self) -> dict:
        return asdict(self)


def result(issues: list[Issue]) -> dict:
    """The check-result document: ok when there is no error."""
    return {"ok": not any(i.level == "error" for i in issues), "issues": [i.as_dict() for i in issues]}


def format_text(issues: list[Issue]) -> str:
    mark = {"error": "ERROR", "warning": "warn ", "info": "info "}
    lines = [f"{mark[i.level]} {i.where}: {i.message} [{i.code}]" for i in issues]
    e = sum(i.level == "error" for i in issues)
    w = sum(i.level == "warning" for i in issues)
    lines.append(f"{e} error(s), {w} warning(s)" if issues else "no problems")
    return "\n".join(lines)
