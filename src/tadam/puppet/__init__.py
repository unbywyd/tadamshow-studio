"""The puppet makers: painting (gen_*), cutting (cut_skin), the audit, the mannequin."""
from __future__ import annotations

from pathlib import Path


def puppet_name(pdir: Path | str) -> str:
    """The puppet's name (meta.json "name", rig.json "puppet", report.json "name"). The server keys a world's puppets
    by it, so it is the HERO's slug for a world's puppet (heroes/<slug>/puppet -> <slug>), never the folder's name
    "puppet"; a view inside it (heroes/<slug>/puppet/side) is "<slug>/side"; a puppet folder of its own keeps its
    folder's name."""
    p = Path(pdir)
    if p.name in ("side", "back") and p.parent.name == "puppet" and p.parent.parent.parent.name == "heroes":
        return f"{p.parent.parent.name}/{p.name}"
    if p.name in ("side", "back") and ((p.parent / "rig.json").exists() or (p.parent / "portrait.png").exists()):
        return f"{puppet_name(p.parent)}/{p.name}"
    if p.name == "puppet" and p.parent.parent.name == "heroes":
        return p.parent.name
    return p.name
