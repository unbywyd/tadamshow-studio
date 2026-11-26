"""The skill (skill/SKILL.md + skill/reference/*.md): its links work, its examples pass the schemas and `tadam check`,
the generated field list is current."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

from tadam.paths import engine_dir
from tadam import check, schema, setmake
from tadam.paths import kit_root
from tadam.world import write_json

SKILL = kit_root() / "skill"


def blocks(md: Path, lang: str = "json") -> list:
    text = md.read_text(encoding="utf-8")
    return [json.loads(b) for b in re.findall(rf"```{lang}\n(.*?)\n```", text, re.S)]


def test_skill_has_its_frontmatter_and_its_links_work():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: tadamshow-studio\ndescription: ")
    for md in [SKILL / "SKILL.md", *sorted((SKILL / "reference").glob("*.md"))]:
        for target in re.findall(r"\]\(([^)#:]+\.md)\)", md.read_text(encoding="utf-8")):
            assert (md.parent / target).is_file(), (md.name, target)
    for must in ("tadam check", "--sheet", "tadam play", "tadam push", "согласен", "price", "skey", "--confirm",
                 "tadam join", "sources.json", "tadam submit", "tadam studio-version", "tadam reply",
                 "reference/owner-review.md", "tadam review approve"):
        assert must.lower() in text.lower(), must
    assert len(text.splitlines()) < 90          # short and practical: the details are in the references


def test_the_script_example_passes_the_schema_and_the_check(world):
    (example,) = blocks(SKILL / "reference" / "script.md")
    assert schema.validate("script.v2", example) == []
    write_json(world / "episodes" / "1" / "script.json", example)
    found = check.check_world(world)
    assert not [i for i in found if i.level == "error"], [i.as_dict() for i in found]


def test_the_world_and_set_examples_fit(world):
    wj, src = blocks(SKILL / "reference" / "world-folder.md")
    assert schema.validate("world", wj) == []
    assert schema.validate("sources", src) == []
    kit, life = blocks(SKILL / "reference" / "puppets-and-sets.md")
    assert setmake.validate_kit(kit) == []
    life_gd = (engine_dir() / "life.gd").read_text(encoding="utf-8")       # the living set's kinds are the engine's
    for b in life["life"]:
        assert f'"{b["kind"]}"' in life_gd and (b.get("type") is None or f'"{b["type"]}"' in life_gd), b


def test_the_step_example_fits_the_schema():
    (step,) = blocks(SKILL / "reference" / "recording-steps.md")
    doc = {"version": 2, "cast": {"det": {"character": "detective"}}, "roles": {"det": [step]},
           "shots": [{"id": "sh1", "remark": {"ru": "x"}, "say": "det-1"}], "film": {"set": "barn"}}
    assert schema.validate("script.v2", doc) == []


def test_script_fields_is_generated_from_the_schema():
    spec = importlib.util.spec_from_file_location("script_fields", kit_root() / "devtools" / "script_fields.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (SKILL / "reference" / "script-fields.md").read_text(encoding="utf-8") == mod.render(), \
        "run: python devtools/script_fields.py"


def test_stage1_list_in_the_skill_is_the_kits():
    from tadam import actions
    text = (SKILL / "reference" / "shots-and-camera.md").read_text(encoding="utf-8")
    for a in actions.STAGE1:
        assert re.search(rf"\b{a}\b", text), a
