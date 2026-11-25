"""The generators with the OpenAI client MOCKED: what they ask for, what they write, how they fail. No test reaches
the network (conftest.no_network refuses to make a real client)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from PIL import Image

from tadam import cli, hero, new, openai_images, setmake
from tadam.puppet import gen_mouth, gen_prop, gen_skin
from tadam.world import World, WorldError, write_json

from conftest import png_bytes

KEY = "dummy-test-key-not-real"


def answers_for_puppet(sheet_png, bad_first=0):
    """portrait -> a picture; sheet -> the mannequin (after `bad_first` blank sheets)."""
    state = {"sheets": 0}

    def answer(kind, kw, n):
        if kind == "generations":
            return png_bytes((1024, 1536), (230, 220, 200, 255))
        state["sheets"] += 1
        return png_bytes((1024, 1536), (0, 0, 0, 0)) if state["sheets"] <= bad_first else sheet_png
    return answer


@pytest.fixture
def bare_world(tmp_path):
    return World(new.world(tmp_path / "папка мира", "moon-cow"))


def test_hero_make_passes_first_time(bare_world, fake_openai, mannequin_sheet_png, capsys):
    fake = fake_openai(answers_for_puppet(mannequin_sheet_png))
    w = bare_world
    code = cli.main(["--world", str(w.root), "hero", "make", "cow", "a calm brown cow in a raincoat"])
    out = capsys.readouterr().out
    assert code == 0, out
    pdir = w.puppet_dir("cow")
    for f in ("portrait.png", "sheet.png", "meta.json", "rig.json", "report.json", "check.jpg", "make.log"):
        assert (pdir / f).is_file(), f
    assert json.loads((pdir / "report.json").read_text(encoding="utf-8"))["passed"] is True
    assert len(list((pdir / "parts").glob("*.png"))) == 15
    assert (w.hero_dir("cow") / "hero.json").is_file()                 # made on the way
    kinds = [k for k, _ in fake.calls]
    assert kinds == ["generations", "edits"]                          # 2 pictures: portrait + sheet
    sheet_call = fake.calls[1][1]
    assert sheet_call["images"] == ["template.png", "portrait.png"]
    assert "a calm brown cow in a raincoat" in sheet_call["prompt"]
    assert sheet_call["background"] == "transparent" and sheet_call["model"] == openai_images.DEFAULT_MODEL
    assert KEY not in out and KEY not in (pdir / "make.log").read_text(encoding="utf-8")
    assert KEY not in (pdir / "meta.json").read_text(encoding="utf-8")


def test_hero_make_repaints_a_failed_sheet(bare_world, fake_openai, mannequin_sheet_png):
    fake = fake_openai(answers_for_puppet(mannequin_sheet_png, bad_first=1))
    r = hero.make(bare_world, "cow", "a cow", log=lambda *_: None)
    assert r["passed"] and r["attempts"] == 2
    assert [k for k, _ in fake.calls] == ["generations", "edits", "edits"]   # the portrait is painted once
    assert "attempt 1 failed" in (bare_world.puppet_dir("cow") / "make.log").read_text(encoding="utf-8")


def test_hero_make_gives_up_after_three(bare_world, fake_openai, mannequin_sheet_png, capsys):
    fake = fake_openai(answers_for_puppet(mannequin_sheet_png, bad_first=99))
    assert cli.main(["--world", str(bare_world.root), "hero", "make", "cow", "a cow"]) == 1
    assert [k for k, _ in fake.calls].count("edits") == 3
    assert "FAIL after 3 attempts" in capsys.readouterr().out


def test_hero_make_uses_the_world_style(bare_world, fake_openai, mannequin_sheet_png):
    wj = bare_world.root / "world.json"
    data = json.loads(wj.read_text(encoding="utf-8"))
    data["bible"]["style"] = {"ru": "гуашь", "en": "matte gouache on grey paper"}
    write_json(wj, data)
    fake = fake_openai(answers_for_puppet(mannequin_sheet_png))
    hero.make(bare_world, "cow", "a cow", log=lambda *_: None)
    assert "matte gouache on grey paper" in fake.calls[0][1]["prompt"]


def test_no_key_is_a_clear_error_and_no_call(bare_world, capsys):
    code = cli.main(["--world", str(bare_world.root), "hero", "make", "cow", "a cow"])
    out = capsys.readouterr().out
    assert code == 1 and "OPENAI_API_KEY" in out


def test_key_comes_only_from_the_environment(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=from-a-file", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(openai_images.GenerationError):
        openai_images.key()
    monkeypatch.setenv("OPENAI_API_KEY", "has space")
    with pytest.raises(openai_images.GenerationError):
        openai_images.key()
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    assert openai_images.key() == KEY


def test_api_errors_become_generation_errors(fake_openai, tmp_path):
    class Boom:
        def generate(self, **kw):
            raise RuntimeError("Error code: 400 - bad prompt")
    openai_images.set_client(lambda: SimpleNamespace(images=Boom()))
    with pytest.raises(openai_images.GenerationError) as e:
        openai_images.call("generations", {"prompt": "x"})
    assert "400" in str(e.value) and KEY not in str(e.value)


def test_unknown_fields_go_in_extra_body():
    def generate(prompt, model=None, extra_body=None):
        return (prompt, model, extra_body)
    assert openai_images._split(generate, {"prompt": "p", "model": "m", "moderation": "low"}) == \
        {"prompt": "p", "model": "m", "extra_body": {"moderation": "low"}}


def test_a_view_is_painted_from_the_front(bare_world, fake_openai, mannequin_sheet_png, mannequin_puppet):
    import shutil
    pdir = bare_world.puppet_dir("cow")
    shutil.copytree(mannequin_puppet, pdir)
    Image.new("RGB", (64, 96), "white").save(pdir / "portrait.png")
    fake = fake_openai(lambda kind, kw, n: mannequin_sheet_png)
    gen_skin.paint(pdir / "side", "a cow", rig="humanoid-a-side", log=lambda *_: None)
    assert [k for k, _ in fake.calls] == ["edits"]                    # no new portrait for a view
    assert fake.calls[0][1]["images"] == ["template.png", "portrait.png", "sheet.png"]
    assert "seen from the FRONT" in fake.calls[0][1]["prompt"]


def test_unknown_rig_is_refused(tmp_path, fake_openai):
    fake_openai([])
    with pytest.raises(ValueError):
        gen_skin.paint(tmp_path / "p", "x", rig="octopus")


def test_set_make(bare_world, fake_openai, capsys):
    w = bare_world
    new.set_(w, "barn")
    kit = json.loads((w.set_dir("barn") / "kit.json").read_text(encoding="utf-8"))
    kit["room"]["prompt"] = "an empty barn, front view"
    kit["props"] = [{"id": "crate", "prompt": "a wooden crate", "x": 0.3, "base": 0.8, "width": 0.25},
                    {"id": "lamp", "prompt": "an oil lamp", "on": "crate", "x": 0.3, "width": 0.08}]
    write_json(w.set_dir("barn") / "kit.json", kit)
    room = png_bytes((1024, 1536), (255, 0, 255, 255))
    fake = fake_openai(lambda kind, kw, n: room if "barn" in kw["prompt"] else png_bytes((300, 200)))
    assert cli.main(["--world", str(w.root), "set", "make", "barn"]) == 0
    st = json.loads((w.set_dir("barn") / "set.json").read_text(encoding="utf-8"))
    assert st["background"] == "room.png" and [p["id"] for p in st["pieces"]] == ["crate", "lamp"]
    lamp, crate = st["pieces"][1], st["pieces"][0]
    assert lamp["base"] == crate["base"] and lamp["bias"] < crate["bias"]      # stands on the crate, drawn over it
    assert len(fake.calls) == 3 and all(k == "generations" for k, _ in fake.calls)
    assert all("Style:" in kw["prompt"] for _, kw in fake.calls)
    alpha = Image.open(w.set_dir("barn") / "room.png").getchannel("A")
    assert alpha.getextrema() == (0, 0)                                         # the magenta glass is see-through
    from tadam import check
    assert not [i for i in check.check_world(w.root) if i.where.startswith("sets/")]


def test_set_make_with_a_style_picture_uses_edits(bare_world, fake_openai):
    w = bare_world
    new.set_(w, "barn")
    kit = json.loads((w.set_dir("barn") / "kit.json").read_text(encoding="utf-8"))
    kit.update(room={"prompt": "an empty barn"}, style_ref="look.png")
    write_json(w.set_dir("barn") / "kit.json", kit)
    Image.new("RGB", (32, 32), "grey").save(w.set_dir("barn") / "look.png")
    fake = fake_openai(lambda kind, kw, n: png_bytes((1024, 1536)))
    setmake.make(w, "barn", log=lambda *_: None)
    assert fake.calls[0][0] == "edits" and fake.calls[0][1]["images"] == ["look.png"]


@pytest.mark.parametrize("kit, why", [
    ({"room": {"prompt": "TODO: x"}}, "TODO"),
    ({"room": {}}, "room.prompt"),
    ({"room": {"prompt": "r"}, "props": [{"id": "../x", "prompt": "p", "x": 0.1, "width": 0.1}]}, "props[0].id"),
    ({"room": {"prompt": "r"}, "style_ref": "../../secret.png"}, "style_ref"),
])
def test_set_make_refuses_a_bad_kit(bare_world, fake_openai, kit, why):
    fake = fake_openai([])
    new.set_(bare_world, "barn")
    write_json(bare_world.set_dir("barn") / "kit.json", kit)
    with pytest.raises(WorldError) as e:
        setmake.make(bare_world, "barn", log=lambda *_: None)
    assert why in str(e.value)
    assert fake.calls == []


def test_set_make_layout_only_needs_no_key(bare_world):
    new.set_(bare_world, "barn")
    kit = json.loads((bare_world.set_dir("barn") / "kit.json").read_text(encoding="utf-8"))
    kit["room"]["prompt"] = "a room"
    write_json(bare_world.set_dir("barn") / "kit.json", kit)
    assert cli.main(["--world", str(bare_world.root), "set", "make", "barn", "--layout-only"]) == 0


def test_prop_and_mouth(tmp_path, fake_openai, mannequin_puppet):
    import shutil
    fake = fake_openai(lambda kind, kw, n: png_bytes((200, 400)))
    out = gen_prop.paint_prop(tmp_path / "media" / "cup.png", "a tin cup", natural=True, log=lambda *_: None)
    assert Image.open(out).size == (200, 400)
    pdir = tmp_path / "puppet"
    shutil.copytree(mannequin_puppet, pdir)
    gen_mouth.paint_mouth(pdir, log=lambda *_: None)
    assert (pdir / "mouth_open.png").is_file()
    meta = json.loads((pdir / "meta.json").read_text(encoding="utf-8"))
    assert meta["calls"][-1]["step"] == "mouth_open"
    assert [k for k, _ in fake.calls] == ["generations", "edits"]
