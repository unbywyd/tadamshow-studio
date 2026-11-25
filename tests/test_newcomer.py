"""What a newcomer hit with the kit (examples/sock-bureau, made by following only the skill), each held by a test:
line endings that made every fresh clone's heroes "stale", puppets named "puppet", working files inside the world,
pictures stored large, the cost of painting, the cover, the outputs."""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from conftest import png_bytes
from tadam import actions, check, cli, folder, imgio, new, openai_images, prices, setmake
from tadam.jsonfile import content_sha, write_json
from tadam.paths import PACKAGE
from tadam.world import World


def crlf(path: Path) -> None:
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))


# ------------------------------------------------------------------------------------------------ 1. line endings

def test_every_json_writer_of_the_kit_writes_lf(tmp_path):
    write_json(tmp_path / "a.json", {"name": "Корова", "list": [1, 2]})
    raw = (tmp_path / "a.json").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n") and "Корова".encode() in raw
    # no writer of the kit goes around the one helper (text mode on Windows writes CRLF)
    bad = []
    for f in PACKAGE.rglob("*.py"):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"write_text\(json\.dumps", line):
                bad.append(f"{f.relative_to(PACKAGE)}:{n}")
    assert bad == []


def test_a_checkout_that_changes_line_endings_keeps_the_action_check(world):
    pdir = world / "heroes/cow/puppet"
    assert actions.state(pdir)[0] == "passed"
    crlf(pdir / "rig.json")                                         # what git or an editor may do on Windows
    assert actions.state(pdir)[0] == "passed"
    assert "hero_actions_stale" not in {i.code for i in check.check_world(world)}
    rig = json.loads((pdir / "rig.json").read_text(encoding="utf-8"))
    # the fingerprint is of the bytes with LF (what the server computes too): a checkout only changes line endings,
    # so that is all it forgives; a reformatted rig is a new rig for the server as well
    (pdir / "rig.json").write_text(json.dumps(rig, indent=4, sort_keys=True), encoding="utf-8")
    assert actions.state(pdir)[0] == "stale"
    rig["body_height"] = rig["body_height"] + 1                     # the content changed: a new check is needed
    write_json(pdir / "rig.json", rig)
    assert actions.state(pdir)[0] == "stale"


def test_an_old_raw_byte_fingerprint_is_still_good_with_either_line_ending(world):
    pdir = world / "heroes/cow/puppet"
    data = json.loads((pdir / "actions.json").read_text(encoding="utf-8"))
    crlf(pdir / "rig.json")
    data["rig"] = hashlib.sha256((pdir / "rig.json").read_bytes()).hexdigest()    # made on Windows, CRLF
    write_json(pdir / "actions.json", data)
    rig = (pdir / "rig.json").read_bytes().replace(b"\r\n", b"\n")
    (pdir / "rig.json").write_bytes(rig)                                           # a fresh clone: LF
    assert actions.state(pdir)[0] == "passed"


def test_content_sha_ignores_formatting_only():
    assert content_sha({"a": 1, "b": [1, 2]}) == content_sha(json.loads('{\r\n  "b": [1,2],\r\n  "a": 1\r\n}'))
    assert content_sha({"a": 1}) != content_sha({"a": 2})


def test_the_manifest_and_the_push_send_json_with_lf_on_every_system(world):
    lf = folder.scan(world).manifest
    crlf(world / "world.json")
    crlf(world / "episodes/1/script.json")
    got = folder.scan(world).manifest
    assert got == lf                                                 # the same world gives the same manifest
    data = folder.payload(world / "world.json")
    assert b"\r" not in data
    assert hashlib.sha256(data).hexdigest() == got["world.json"]["sha256"] and len(data) == got["world.json"]["bytes"]
    png = world / "cover.png"                                         # a picture is sent as it is
    assert folder.payload(png) == png.read_bytes()


def test_push_uploads_exactly_the_fingerprinted_bytes(world, monkeypatch):
    from tadam import sync
    crlf(world / "world.json")
    sent = {}

    class FakeApi:
        link = SimpleNamespace(url="https://studio.example")

        def post(self, path, body):
            if path.endswith("/push/begin"):
                self.man = body["manifest"]
                return {"pushId": "p1", "kept": 0, "uploads": [{"path": p, "url": f"u:{p}"} for p in body["manifest"]]}
            return {"rev": 1, "world": {"id": "w1", "slug": "moon-cow"}, "check": {"ok": True, "issues": []}}

        def upload(self, url, data, headers):
            sent[url[2:]] = data

    api = FakeApi()
    sync.push(world, api, log=lambda *_: None)
    for p, m in api.man.items():
        assert hashlib.sha256(sent[p]).hexdigest() == m["sha256"] and len(sent[p]) == m["bytes"], p
    assert b"\r" not in sent["world.json"]


# ------------------------------------------------------------------------------------------------ 2. puppet names

def test_hero_make_names_the_puppet_by_the_hero(tmp_path, fake_openai, mannequin_sheet_png):
    from tadam import hero
    w = World(new.world(tmp_path, "w"))
    fake_openai(lambda kind, kw, n: png_bytes((1024, 1536), (230, 220, 200, 255)) if kind == "generations"
                else mannequin_sheet_png)
    for slug in ("cow", "goat"):
        assert hero.make(w, slug, "a cow", log=lambda *_: None)["passed"]
        pdir = w.puppet_dir(slug)
        assert json.loads((pdir / "meta.json").read_text(encoding="utf-8"))["name"] == slug
        assert json.loads((pdir / "rig.json").read_text(encoding="utf-8"))["puppet"] == slug
        assert json.loads((pdir / "report.json").read_text(encoding="utf-8"))["name"] == slug
    assert "puppet_name_twice" not in {i.code for i in check.check_world(w.root)}


def test_the_mannequin_is_named_by_the_hero_too(tmp_path):
    w = World(new.world(tmp_path, "w"))
    assert cli.main(["--world", str(w.root), "hero", "make", "cow", "x", "--mannequin", "--no-actions"]) == 0
    assert json.loads((w.puppet_dir("cow") / "meta.json").read_text(encoding="utf-8"))["name"] == "cow"


def test_the_example_puppets_have_their_own_names():
    from tadam.paths import kit_root
    root = kit_root() / "examples" / "sock-bureau"
    for slug in ("archivist", "visitor"):
        assert json.loads((root / "heroes" / slug / "puppet/meta.json").read_text(encoding="utf-8"))["name"] == slug
        assert actions.state(root / "heroes" / slug / "puppet")[0] == "passed"


# ------------------------------------------------------------------------------------------------ 3. money

USAGE_PORTRAIT = {"input_tokens": 180, "input_tokens_details": {"image_tokens": 0, "text_tokens": 180},
                  "output_tokens": 343, "output_tokens_details": {"image_tokens": 343, "text_tokens": 0}}
USAGE_SHEET = {"input_tokens": 3624, "input_tokens_details": {"image_tokens": 3072, "text_tokens": 552},
               "output_tokens": 343, "output_tokens_details": {"image_tokens": 343, "text_tokens": 0}}


def test_prices_reproduce_the_observed_bills():
    assert prices.cost(USAGE_PORTRAIT) == pytest.approx(prices.OBSERVED["portrait"], abs=0.001)
    assert prices.cost(USAGE_SHEET) == pytest.approx(prices.OBSERVED["sheet"], abs=0.001)
    s = prices.summary([{"usage": USAGE_PORTRAIT}, {"usage": USAGE_SHEET}, {"usage": None}])
    assert s["pictures"] == 3 and s["unknown"] == 1 and s["usd"] == pytest.approx(0.049, abs=0.002)
    line = prices.describe([{"usage": USAGE_PORTRAIT}], "medium")
    assert "1 picture(s) at medium quality" in line and "$0.011" in line and prices.PRICES_DATE in line


def with_usage(images, usage_of):
    """The fake client's answers, each with the API's usage."""
    old = images._answer

    def answer(kind, kw):
        r = old(kind, kw)
        r.usage = SimpleNamespace(model_dump=lambda: usage_of(kind))
        return r
    images._answer = answer
    return images


def test_hero_make_prints_and_keeps_what_it_cost(tmp_path, fake_openai, mannequin_sheet_png, capsys):
    w = World(new.world(tmp_path, "w"))
    images = fake_openai(lambda kind, kw, n: png_bytes((1024, 1536), (230, 220, 200, 255)) if kind == "generations"
                         else mannequin_sheet_png)
    with_usage(images, lambda kind: USAGE_PORTRAIT if kind == "generations" else USAGE_SHEET)
    assert cli.main(["--world", str(w.root), "hero", "make", "cow", "a cow", "--no-actions"]) == 0
    out = capsys.readouterr().out
    assert "at medium quality" in out and "painted 2 picture(s) at medium quality" in out and "$0.049" in out
    meta = json.loads((w.puppet_dir("cow") / "meta.json").read_text(encoding="utf-8"))
    assert [c["step"] for c in meta["calls"]] == ["portrait", "sheet"] and meta["quality"] == "medium"


def test_a_repainted_sheet_keeps_the_portrait_on_the_record(tmp_path, fake_openai, mannequin_sheet_png):
    from tadam import hero
    w = World(new.world(tmp_path, "w"))
    n = {"sheets": 0}

    def answer(kind, kw, k):
        if kind == "generations":
            return png_bytes((1024, 1536), (230, 220, 200, 255))
        n["sheets"] += 1
        return png_bytes((1024, 1536), (0, 0, 0, 0)) if n["sheets"] == 1 else mannequin_sheet_png
    fake_openai(answer)
    r = hero.make(w, "cow", "a cow", log=lambda *_: None)
    assert r["attempts"] == 2
    meta = json.loads((w.puppet_dir("cow") / "meta.json").read_text(encoding="utf-8"))
    assert [c["step"] for c in meta["calls"]] == ["portrait", "sheet", "sheet"]


def test_set_make_records_its_usage_and_prints_the_cost(tmp_path, fake_openai, capsys):
    w = World(new.world(tmp_path, "w"))
    new.set_(w, "barn")
    kit = json.loads((w.set_dir("barn") / "kit.json").read_text(encoding="utf-8"))
    kit["room"]["prompt"] = "an empty barn"
    kit["props"] = [{"id": "crate", "prompt": "a crate", "x": 0.3, "base": 0.8, "width": 0.25}]
    write_json(w.set_dir("barn") / "kit.json", kit)
    images = fake_openai(lambda kind, kw, n: png_bytes((1024, 1536), (255, 0, 255, 255)) if "barn" in kw["prompt"]
                         else png_bytes((300, 200)))
    with_usage(images, lambda kind: USAGE_PORTRAIT)
    assert cli.main(["--world", str(w.root), "set", "make", "barn"]) == 0
    out = capsys.readouterr().out
    assert "painted 2 picture(s) at medium quality" in out and "$0.022" in out
    meta = json.loads((w.set_dir("barn") / "meta.json").read_text(encoding="utf-8"))
    assert sorted(c["step"] for c in meta["calls"]) == ["crate", "room"] and all(c["usage"] for c in meta["calls"])
    # a repaint adds to the record
    assert cli.main(["--world", str(w.root), "set", "make", "barn", "--only", "crate"]) == 0
    meta = json.loads((w.set_dir("barn") / "meta.json").read_text(encoding="utf-8"))
    assert len(meta["calls"]) == 3


@pytest.mark.parametrize("cmd", [["hero", "make", "--help"], ["set", "make", "--help"]])
def test_the_help_says_medium_and_the_price(cmd, capsys):
    with pytest.raises(SystemExit):
        cli.main(cmd)
    out = " ".join(capsys.readouterr().out.split())
    assert "(default: medium)" in out and "PAID" in out and "$0.0" in out


def test_the_docs_give_per_token_prices_not_a_per_picture_page():
    from tadam.paths import kit_root
    for f in ("skill/SKILL.md", "README.md", "README.ru.md"):
        text = (kit_root() / f).read_text(encoding="utf-8")
        assert "openai.com/api/pricing" not in text, f
        assert "medium" in text and "0.038" in text.replace(",", "."), f


# ------------------------------------------------------------------------------------------------ 4. working files

def test_hero_make_keeps_its_working_files_in_tadam(tmp_path, fake_openai, mannequin_sheet_png):
    from tadam import hero
    w = World(new.world(tmp_path, "w"))
    fake_openai(lambda kind, kw, n: png_bytes((1024, 1536), (230, 220, 200, 255)) if kind == "generations"
                else mannequin_sheet_png)
    hero.make(w, "cow", "a cow", log=lambda *_: None)
    pdir, work = w.puppet_dir("cow"), w.root / ".tadam/heroes/cow/puppet"
    for f in ("check.jpg", "_poses.jpg", "_sheet_check.jpg", "make.log"):
        assert (work / f).is_file() and not (pdir / f).exists(), f
    assert {p.name for p in pdir.iterdir()} == {"meta.json", "portrait.png", "sheet.png", "rig.json", "report.json",
                                                "parts"}


def test_set_make_keeps_the_raw_room_in_tadam(tmp_path, fake_openai):
    w = World(new.world(tmp_path, "w"))
    new.set_(w, "barn")
    kit = json.loads((w.set_dir("barn") / "kit.json").read_text(encoding="utf-8"))
    kit["room"]["prompt"] = "an empty barn"
    write_json(w.set_dir("barn") / "kit.json", kit)
    fake_openai(lambda kind, kw, n: png_bytes((1024, 1536), (255, 0, 255, 255)))
    setmake.make(w, "barn", log=lambda *_: None)
    assert (w.root / ".tadam/sets/barn/room_raw.png").is_file()
    assert not (w.set_dir("barn") / "room_raw.png").exists()


def test_push_never_sends_working_files(world):
    """What an older kit (or the person) left inside the layout stays home, and .tadam/ is never looked into."""
    left = ["heroes/cow/puppet/check.jpg", "heroes/cow/puppet/_poses.jpg", "heroes/cow/puppet/_sheet_check.jpg",
            "heroes/cow/puppet/make.log", "heroes/cow/puppet/_mouth_check.png", "sets/barn/room_raw.png",
            "sets/barn/_draft.png", "notes.md"]
    for p in left:
        (world / p).write_bytes(png_bytes() if p.endswith(".png") else b"x")
    (world / ".tadam/sets/barn").mkdir(parents=True)
    (world / ".tadam/sets/barn/room_raw.png").write_bytes(png_bytes())
    sc = folder.scan(world)
    assert not set(left) & set(sc.manifest)
    assert set(left) <= {p for p, _ in sc.local_only}
    assert not any(p.startswith(".tadam") for p in sc.manifest)
    assert "sets/barn/room.png" in sc.manifest and "heroes/cow/puppet/sheet.png" in sc.manifest


# ------------------------------------------------------------------------------------------------ 5. size

def test_compact_png_keeps_every_visible_pixel_and_is_smaller(tmp_path):
    rng = np.random.default_rng(1)
    a = rng.integers(0, 255, (300, 200, 4), dtype=np.uint8)
    a[..., 3] = 0
    a[100:200, 50:150, 3] = 255                  # a painted piece in the middle, noise in the invisible rest
    a[95:100, 50:150, 3] = 128                   # a soft edge
    f = tmp_path / "piece.png"
    Image.fromarray(a, "RGBA").save(f)
    before, after = imgio.compact_png(f)
    assert after < before
    b = np.array(Image.open(f).convert("RGBA"))
    vis = a[..., 3] > 0
    assert (a[vis] == b[vis]).all() and (a[..., 3] == b[..., 3]).all()
    # an invisible pixel next to the piece takes the piece's colour, not black (a scaled picture blends with it)
    assert (b[99, 60, :3] == a[99, 60, :3]).all() and (b[94, 60, :3] == a[95, 60, :3]).all()


def test_an_opaque_picture_loses_only_its_useless_alpha(tmp_path):
    f = tmp_path / "room.png"
    Image.new("RGBA", (64, 64), (10, 20, 30, 255)).save(f)
    imgio.compact_png(f)
    with Image.open(f) as im:
        assert im.mode == "RGB" and im.getpixel((5, 5)) == (10, 20, 30)


# ------------------------------------------------------------------------------------------------ 8. outputs

def test_new_english_world_does_not_copy_the_russian_title(tmp_path):
    root = new.world(tmp_path, "duo", "Дуэт", langs=("ru", "en"))
    t = json.loads((root / "world.json").read_text(encoding="utf-8"))["title"]
    assert t["ru"] == "Дуэт" and t["en"] == "TODO"


def test_film_says_its_length_and_how_long_it_took(world, monkeypatch, capsys):
    from tadam import render
    monkeypatch.setattr(render, "film", lambda ep, out, *a, **k: out)
    assert cli.main(["--world", str(world), "film", "1", "--no-voice"]) == 0
    out = capsys.readouterr().out
    assert re.search(r"film \d+\.\d s, rendered in \d+ s", out), out


def test_the_face_board_is_placed_not_repaired(mannequin_puppet):
    rep = json.loads((mannequin_puppet / "report.json").read_text(encoding="utf-8"))
    assert any(x.startswith("face board placed") for x in rep["made"])
    assert not any("face board" in x for x in rep["repairs"])


def test_doctor_says_a_key_per_command_is_fine():
    from tadam import doctor
    r = doctor.check_openai(SimpleNamespace(environ={}))
    assert r.status == "warn" and "skey run --only OPENAI_API_KEY" in r.hint and "FINE" in r.hint


# ------------------------------------------------------------------------------------------------ 6. the cover

needs_godot = pytest.mark.skipif(__import__("tadam.doctor", fromlist=["x"]).find_godot(
    __import__("tadam.doctor", fromlist=["x"]).System())[0] is None, reason="Godot 4.7 is not installed")


@needs_godot
def test_cover_from_a_frame(world, capsys):
    (world / "cover.png").unlink()
    data = json.loads((world / "sources.json").read_text(encoding="utf-8"))
    data["files"].pop("cover.png")
    write_json(world / "sources.json", data)
    assert cli.main(["--world", str(world), "cover", "--shot", "sh2", "--at", "1"]) == 0
    out = capsys.readouterr().out
    with Image.open(world / "cover.png") as im:
        assert im.size == (720, 1280) and "shot sh2" in out
    assert "cover.png" in json.loads((world / "sources.json").read_text(encoding="utf-8"))["files"]
    assert "cover_missing" not in {i.code for i in check.check_world(world)}
    # again: the old one is kept, not lost
    assert cli.main(["--world", str(world), "cover"]) == 0
    assert list((world / ".tadam/removed").rglob("cover.png"))
