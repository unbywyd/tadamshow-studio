"""The server's content checks inside `tadam check`: sources.json covers every picture and sound (tadam.sources),
the word list on every text (tadam.words, schema/bad-words.json); the kit's makers record their sources; the
schemas refresh from a contracts checkout. Same codes and levels as the server (services/studio/content.ts)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tadam import check, new, schema, setmake, sources, words
from tadam.paths import kit_root
from tadam.world import World, write_json


def codes(found, level=None) -> list[str]:
    return [i.code for i in found if level is None or i.level == level]


def by(found, code):
    return [i for i in found if i.code == code]


def edit(path: Path, fn):
    d = json.loads(path.read_text(encoding="utf-8"))
    fn(d)
    write_json(path, d)


# ------------------------------------------------------------------------------------------------ sources

def test_a_new_world_starts_with_an_empty_sources_json(tmp_path):
    root = new.world(tmp_path, "sock-test")
    data = json.loads((root / "sources.json").read_text(encoding="utf-8"))
    assert data == {"version": 1, "files": {}} and schema.validate("sources", data) == []
    assert not by(check.check_world(root), "no_source")              # (nothing to cover yet)


def test_the_test_world_is_covered(world):
    found = check.check_world(world)
    assert not [i for i in found if i.code in ("no_source", "no_sources", "source_unused")], found


def test_no_sources_json_is_an_error_per_file(world):
    (world / "sources.json").unlink()
    found = sources.check(world)
    (top,) = by(found, "no_sources")
    assert top.level == "error" and top.where == "sources.json" and "has no sources.json" in top.message
    missing = {i.where for i in by(found, "no_source")}
    assert {"cover.png", "heroes/cow/puppet/parts/chest.png"} <= missing          # (sorted, the first 40 listed)
    assert all(i.level == "error" for i in by(found, "no_source"))
    total = int(top.message.split(": ")[1].split()[0])
    assert total > 40 and len(by(found, "no_source")) == 41
    assert f"and {total - 40} more file(s) without a source" in by(found, "no_source")[-1].message
    from tadam import cli
    assert cli.main(["--world", str(world), "check"]) == 1


def test_a_missing_file_entry_is_an_error(world):
    edit(world / "sources.json", lambda d: d["files"].pop("media/"))
    found = sources.check(world)
    assert sorted(i.where for i in by(found, "no_source")) == ["media/cup.png", "media/theme.mp3"]
    assert not by(found, "no_sources")
    assert "media/theme.mp3 has no source" in by(found, "no_source")[1].message


def test_a_folder_key_covers_its_files_and_the_longest_key_wins():
    s = {"version": 1, "files": {
        "heroes/": {"source": "own"},
        "heroes/cow/puppet/": {"source": "generated", "tool": "gpt-image-2.5-flare"},
        "heroes/cow/puppet/portrait.png": {"source": "licensed", "licence": "CC0", "url": "https://example.com/x"},
        "media/music": {"source": "own"},              # (no "/": a file key, it covers no folder)
    }}
    assert sources.source_of(s, "heroes/cow/puppet/parts/head.png")["source"] == "generated"
    assert sources.source_of(s, "heroes/cow/puppet/portrait.png")["source"] == "licensed"
    assert sources.source_of(s, "heroes/det/puppet/parts/head.png")["source"] == "own"
    assert sources.source_of(s, "media/music/theme.mp3") is None
    assert sources.source_of(None, "cover.png") is None


def test_unused_keys_are_warnings(world):
    edit(world / "sources.json", lambda d: d["files"].update({"media/gone.mp3": {"source": "own"},
                                                               "sets/attic/": {"source": "own"}}))
    found = sources.check(world)
    assert sorted(i.where for i in by(found, "source_unused")) == ["sources.json#files.media/gone.mp3",
                                                                    "sources.json#files.sets/attic/"]
    assert all(i.level == "warning" for i in by(found, "source_unused")) and not by(found, "no_source")


def test_a_sources_json_that_breaks_its_schema(world):
    edit(world / "sources.json", lambda d: d["files"].update({"media/": {"source": "generated"},
                                                               "cover.png": {"source": "licensed", "licence": "x",
                                                                             "url": "ftp://x"}}))
    found = sources.check(world)
    assert by(found, "schema") and all(i.where.startswith("sources.json") for i in by(found, "schema"))
    assert by(found, "no_source")                     # (a broken list covers nothing, like on the server)
    (world / "sources.json").write_text("{nope", encoding="utf-8")
    assert by(sources.check(world), "json_invalid")


def test_files_that_stay_home_need_no_source(world):
    (world / "heroes" / "cow" / "puppet" / "check.jpg").write_bytes(b"\xff\xd8\xff")
    (world / "notes.png").write_bytes(b"x")           # (not a place of the layout: never sent)
    edit(world / "sources.json", lambda d: d["files"].pop("heroes/cow/puppet/"))
    wheres = {i.where for i in by(sources.check(world), "no_source")}
    assert "heroes/cow/puppet/parts/chest.png" in wheres
    assert "heroes/cow/puppet/check.jpg" not in wheres and "notes.png" not in wheres


def test_declare_keeps_what_is_there_unless_replaced(tmp_path):
    root = new.world(tmp_path, "w")
    assert sources.declare(root, "media/", {"source": "own"})
    assert not sources.declare(root, "media/", {"source": "generated", "tool": "x"})
    assert sources.declare(root, "media/", {"source": "generated", "tool": "x"}, replace=True)
    data = json.loads((root / "sources.json").read_text(encoding="utf-8"))
    assert data["files"] == {"media/": {"source": "generated", "tool": "x"}}
    with pytest.raises(AssertionError):
        sources.declare(root, "media/", {"source": "licensed"})        # (a source that breaks the schema)


def test_the_makers_record_their_sources(tmp_path):
    root = new.world(tmp_path, "w")
    w = World(root)
    from tadam import hero
    r = hero.make(w, "cow", "a cow", mannequin=True, log=lambda *_: None)
    assert r["passed"]
    new.set_(w, "barn")
    setmake.make(w, "barn", plain=True, log=lambda *_: None)
    files = json.loads((root / "sources.json").read_text(encoding="utf-8"))["files"]
    assert files["heroes/cow/puppet/"]["source"] == "own" and "mannequin" in files["heroes/cow/puppet/"]["note"]
    assert files["sets/barn/"]["source"] == "own"
    assert not by(sources.check(root), "no_source")


# ------------------------------------------------------------------------------------------------ words

@pytest.mark.parametrize("text,level", [
    ("what the fuck", "error"), ("Ах ты сука", "error"), ("FUCKING moon", "error"),
    ("Ты дурак", "warning"), ("какой идиот", "warning"), ("sexy cow", "warning"), ("Путин", "warning"),
    ("Где моя луна?", None), ("скука и сукно", None), ("assistant classic", None), ("ёлка", None),
])
def test_find_words_like_the_server(text, level):
    hits = words.find_words(text)
    assert (hits[0]["level"] if hits else None) == level, hits


def test_errors_come_first_and_each_word_once():
    hits = words.find_words("дурак, сука, дурак")
    assert [h["level"] for h in hits] == ["error", "warning"] and [h["word"] for h in hits] == ["сука", "дурак"]


def test_bad_words_in_the_world_are_errors_and_borderline_ones_warnings(world, capsys):
    def script(s):
        s["roles"]["cow"][0]["text"]["ru"] = "Где моя луна, сука?"
        s["shots"][1]["remark"]["ru"] = "Сыщик-дурак отвечает"
    edit(world / "episodes/1/script.json", script)
    edit(world / "heroes/cow/hero.json", lambda h: h.update(trait={"ru": "упрямая идиотка"}))
    found = check.check_world(world)
    (bad,) = by(found, "bad_word")
    assert bad.level == "error" and bad.where == "episodes/1/script.json#roles.cow[0].text.ru"
    assert "«сука» is swearing" in bad.message
    warn = sorted(i.where for i in by(found, "borderline_word"))
    assert warn == ["episodes/1/script.json#shots[1].remark.ru", "heroes/cow/hero.json#trait.ru"]
    from tadam import cli
    assert cli.main(["--world", str(world), "check"]) == 1
    capsys.readouterr()
    edit(world / "episodes/1/script.json", lambda s: s["roles"]["cow"][0]["text"].update(ru="Где моя луна?"))
    assert cli.main(["--world", str(world), "check"]) == 0             # warnings only: the check passes
    assert "borderline_word" in capsys.readouterr().out


def test_word_check_paths_follow_the_server():
    v = {"$schema": "fuck", "title": {"ru": "x", "en": "shit happens"}, "rules": [{"ru": "ok"}, {"en": "damn"}]}
    got = [(i.where, i.code) for i in words.word_issues("world.json", v)]
    assert got == [("world.json#title.en", "bad_word"), ("world.json#rules[1].en", "borderline_word")]
    assert [(i.where, i.code) for i in words.word_issues("sets/x/set.json#name", "Bitch room")] == \
        [("sets/x/set.json#name", "bad_word")]


# ------------------------------------------------------------------------------------------------ schemas

def test_the_kit_has_the_servers_schemas_and_word_list():
    names = {p.name for p in (kit_root() / "schema").glob("*.json")}
    assert len(names) == 43 and {"bad-words.json", "sources.json", "join-verify.response.json",
                                 "submission-review.response.json"} <= names
    assert "access-request.request.json" not in names


def test_refresh_schemas_copies_and_removes(tmp_path):
    spec = importlib.util.spec_from_file_location("refresh_schemas", kit_root() / "devtools" / "refresh_schemas.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = tmp_path / "packages" / "contracts" / "schemas"
    src.mkdir(parents=True)
    for n in ("script.v2.json", "bad-words.json", "new.json"):
        (src / n).write_text('{"a": 1}', encoding="utf-8")
    dest = tmp_path / "schema"
    dest.mkdir()
    (dest / "README.md").write_text("keep", encoding="utf-8")
    (dest / "old.json").write_text("{}", encoding="utf-8")
    (dest / "script.v2.json").write_text('{"a": 0}', encoding="utf-8")
    assert mod.source_dir(str(tmp_path)) == src.resolve()
    res = mod.refresh(src, dest)
    assert res["added"] == ["bad-words.json", "new.json"] and res["changed"] == ["script.v2.json"]
    assert res["removed"] == ["old.json"] and (dest / "README.md").exists()
    with pytest.raises(SystemExit):
        mod.source_dir(str(tmp_path / "nothing"))
