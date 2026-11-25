"""`tadam new`: the templates fit their schemas, refuse bad names and never overwrite."""
from __future__ import annotations

import json

import pytest

from tadam import cli, new, schema
from tadam.world import World, WorldError


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_new_world_hero_set_episode(tmp_path, capsys):
    parent = tmp_path / "Мои миры с пробелом"
    parent.mkdir()
    assert cli.main(["new", "world", "moon-cow", "--title", "Корова и луна", "--dir", str(parent)]) == 0
    root = parent / "moon-cow"
    w = ["--world", str(root)]
    assert cli.main(w + ["new", "hero", "cow", "--name", "Корова"]) == 0
    assert cli.main(w + ["new", "set", "barn"]) == 0
    assert cli.main(w + ["new", "episode", "1", "--cast", "cow=cow"]) == 0
    assert schema.validate("world", load(root / "world.json")) == []
    assert load(root / "world.json")["title"] == {"ru": "Корова и луна"}
    assert schema.validate("hero", load(root / "heroes/cow/hero.json")) == []
    s = load(root / "episodes/1/script.json")
    assert schema.validate("script.v2", s) == []
    assert s["film"]["set"] == "barn" and s["cast"] == {"cow": {"character": "cow"}}
    assert s["shots"][0]["say"] == "cow-1"
    assert load(root / "sets/barn/set.json")["background"] == "room.png"
    assert "room" in load(root / "sets/barn/kit.json")
    for d in ("heroes", "sets", "media", "episodes"):
        assert (root / d).is_dir()
    assert ".tadam/" in (root / ".gitignore").read_text(encoding="utf-8")
    # the files are UTF-8 with real letters, LF line ends
    raw = (root / "world.json").read_bytes()
    assert "Корова".encode("utf-8") in raw and b"\r\n" not in raw


def test_english_world_templates_have_both_languages(tmp_path):
    root = new.world(tmp_path, "duo", langs=("ru", "en"))
    w = World(root)
    new.hero(w, "cat")
    new.episode(w, "1", "main", {"cat": "cat"})
    assert load(root / "world.json")["bible"]["idea"]["en"] == "TODO"
    assert load(root / "heroes/cat/hero.json")["name"]["en"] == "TODO"
    s = load(root / "episodes/1/script.json")
    assert s["roles"]["cat"][0]["text"]["en"] == "TODO" and s["shots"][0]["remark"]["en"] == "TODO"
    assert schema.validate("script.v2", s) == []


def test_empty_episode_without_cast(tmp_path):
    w = World(new.world(tmp_path, "solo"))
    s = load(new.episode(w, "3") / "script.json")
    assert s["film"]["set"] == "main" and s["shots"][0]["seconds"] == 3
    assert schema.validate("script.v2", s) == []


@pytest.mark.parametrize("slug", ["Moon", "moon_cow", "-moon", "moon--cow", "../moon", "луна", "", "a" * 81])
def test_bad_world_names(tmp_path, slug):
    with pytest.raises(WorldError):
        new.world(tmp_path, slug)


@pytest.mark.parametrize("args", [["new", "hero", "Cow"], ["new", "set", "my set"], ["new", "episode", "0"],
                                  ["new", "episode", "one"], ["new", "episode", "2", "--cast", "Cow=cow"],
                                  ["new", "episode", "2", "--cast", "cow"]])
def test_bad_names_in_a_world(tmp_path, capsys, args):
    root = new.world(tmp_path, "w")
    assert cli.main(["--world", str(root)] + args) == 1
    assert "tadam:" in capsys.readouterr().out


def test_never_overwrites(tmp_path):
    root = new.world(tmp_path, "w")
    w = World(root)
    new.hero(w, "cow")
    new.set_(w, "barn")
    new.episode(w, "1")
    for fn in (lambda: new.world(tmp_path, "w"), lambda: new.hero(w, "cow"), lambda: new.set_(w, "barn"),
               lambda: new.episode(w, "1")):
        with pytest.raises(WorldError):
            fn()


def test_clean_folder_to_a_clean_check(tmp_path, capsys):
    """The stage's condition: on a clean folder, a world made by commands checks with no errors (stand-ins drawn by
    code, nothing paid)."""
    assert cli.main(["new", "world", "first", "--dir", str(tmp_path)]) == 0
    w = ["--world", str(tmp_path / "first")]
    assert cli.main(w + ["new", "hero", "cow", "--name", "Корова"]) == 0
    assert cli.main(w + ["hero", "make", "cow", "a cow", "--mannequin"]) == 0
    assert cli.main(w + ["new", "set", "barn"]) == 0
    assert cli.main(w + ["set", "make", "barn", "--placeholder"]) == 0
    assert cli.main(w + ["new", "episode", "1", "--cast", "cow=cow"]) == 0
    capsys.readouterr()
    assert cli.main(w + ["check"]) == 0
    out = capsys.readouterr().out
    assert "ERROR" not in out and "todo_text" in out           # only the template's texts are left to write
