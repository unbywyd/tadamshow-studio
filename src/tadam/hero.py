"""`tadam hero make <slug> "<description>"`: a puppet end to end (the lab's make_puppet.sh, in Python).

    paint the portrait and the pattern sheet (OpenAI, the editor's own key)
    -> cut the sheet into parts and derive the skeleton (cut_skin)
    -> the independent audit of the assembled puppet (audit, inside cut_skin)
    -> a failed sheet is repainted from the same portrait, up to 3 attempts in all.

Writes heroes/<slug>/puppet/ (meta.json, sheet.png, portrait.png, rig.json, parts/*.png, report.json, check.jpg) and
heroes/<slug>/puppet/make.log. Cost: 2 pictures (portrait + sheet), one more per repainted sheet.
"""
from __future__ import annotations

import json
from pathlib import Path

from tadam import new, sources
from tadam import openai_images as oi
from tadam.puppet import cut_skin, gen_skin
from tadam.world import World

ATTEMPTS = 3


def _declare(w: World, slug: str, source: dict, log) -> None:
    """The puppet's folder in sources.json: what made its pictures."""
    if sources.declare(w.root, f"heroes/{slug}/puppet/", source, replace=True):
        log(f"sources.json: heroes/{slug}/puppet/ = {source['source']}" + (f" ({source['tool']})" if "tool" in source else ""))


def make(w: World, slug: str, description: str, *, style: str | None = None, rig: str = "humanoid-a",
         quality: str = "medium", model: str | None = None, attempts: int = ATTEMPTS, mannequin: bool = False,
         log=print) -> dict:
    """Make the hero's puppet. Returns {"passed", "attempts", "report", "dir"}.
    mannequin=True: the rig's wooden mannequin, drawn by code (free, offline): a stand-in to block out scenes."""
    if not (w.hero_dir(slug) / "hero.json").exists():
        new.hero(w, slug)
        log(f"new hero: heroes/{slug}/hero.json (write its name and trait)")
    pdir = w.puppet_dir(slug)
    pdir.mkdir(parents=True, exist_ok=True)
    if mannequin:
        from tadam.puppet import mannequin as mq
        report = mq.make(pdir, rig, character=description, log=log)
        _declare(w, slug, {"source": "own", "note": "the kit's wooden mannequin, drawn by code"}, log)
        return {"passed": bool(report.get("passed")), "attempts": 1, "report": report, "dir": pdir}
    logfile = pdir / "make.log"
    lines: list[str] = []

    def say(msg: str):
        lines.append(msg)
        log(msg)

    style = style or w.style() or gen_skin.STYLE_DEFAULT
    kw = {"style": style, "rig": rig, "quality": quality}
    if model:
        kw["model"] = model
    report: dict = {}
    tried = 0
    try:
        gen_skin.paint(pdir, description, log=say, **kw)
        _declare(w, slug, {"source": "generated", "tool": model or oi.DEFAULT_MODEL}, say)
        for tried in range(1, attempts + 1):
            report = cut_skin.cut(pdir, rig, log=say)
            if report.get("passed"):
                say(f"{slug}: PASS (attempt {tried})")
                break
            if tried == attempts:
                say(f"{slug}: FAIL after {attempts} attempts")
                break
            say(f"--- attempt {tried} failed, repainting the sheet")
            gen_skin.paint(pdir, description, reuse_portrait=True, log=say, **kw)
    finally:
        logfile.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"passed": bool(report.get("passed")), "attempts": tried, "report": report, "dir": pdir}


def status(w: World, slug: str) -> dict:
    rep = w.puppet_dir(slug) / "report.json"
    if not rep.exists():
        return {"passed": False, "why": "no puppet yet"}
    data = json.loads(rep.read_text(encoding="utf-8"))
    return {"passed": bool(data.get("passed")), "why": "" if data.get("passed") else "the audit found problems"}


def describe(result: dict) -> str:
    r = result["report"]
    if result["passed"]:
        return f"passed: {r.get('parts_ok')}/{r.get('parts_total')} parts, {Path(result['dir'])}"
    probs = list(r.get("sheet_problems") or [])
    for n, p in (r.get("parts") or {}).items():
        if isinstance(p, dict) and p.get("problems"):
            probs.append(f"{n}: {'; '.join(p['problems'])}")
    return "failed: " + ("; ".join(probs[:6]) or "see report.json")
