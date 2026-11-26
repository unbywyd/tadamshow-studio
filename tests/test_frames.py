"""A drawing that is frames shown in turn (mechanics-tz 6b): the "frames" record, `tadam strip` (the strip to start
from, the cut, the way back), what `tadam check` says, the paths the server takes and, with Godot installed, the
engine itself: which frame is shown when (engine/frames.gd), on a puppet's part and on a set piece of a scene."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from tadam import check, cli, doctor, engine, episode, folder, render, strip
from tadam.paths import engine_dir
from tadam.world import World, WorldError, read_json, write_json

needs_godot = pytest.mark.skipif(doctor.find_godot(doctor.System())[0] is None, reason="Godot 4.7 is not installed")
RGB = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)]


def _strip_of(first: Path, colors, out: Path, cell=None) -> Path:
    """A strip whose cells are flat colours, each cell the size of `first` (or `cell`)."""
    with Image.open(first) as im:
        w, h = cell or im.size
    sheet = Image.new("RGBA", (w * len(colors), h))
    for k, c in enumerate(colors):
        sheet.paste(Image.new("RGBA", (w, h), c), (k * w, 0))
    sheet.save(out)
    return out


def _codes(world: Path) -> dict:
    out: dict = {}
    for i in check.check_world(world):
        out.setdefault(i.code, []).append(i)
    return out


# ------------------------------------------------------------------------------------------------- the record

def test_the_record_is_checked_field_by_field():
    assert strip.problems({"count": 4, "fps": 8, "mode": "pingpong", "offset": 0.25}) == []
    assert strip.problems({"count": 2}) == []
    assert strip.problems({"count": 3, "order": [1, 1, 2, 3, 2]}) == []
    assert "count" in strip.problems({"count": 1})[0] and "count" in strip.problems({"count": 17})[0]
    assert "count" in strip.problems({"count": 2.5})[0] and "count" in strip.problems({"fps": 8})[0]
    assert "fps" in strip.problems({"count": 2, "fps": 0})[0] and "fps" in strip.problems({"count": 2, "fps": 60})[0]
    assert "mode" in strip.problems({"count": 2, "mode": "bounce"})[0]
    assert "offset" in strip.problems({"count": 2, "offset": 2})[0]
    assert "outside 1..3" in strip.problems({"count": 3, "order": [1, 4]})[0]
    assert "order" in strip.problems({"count": 3, "order": []})[0]
    assert "unknown key speed" in strip.problems({"count": 2, "speed": 2})[0]
    assert "object" in strip.problems([4, 8])[0]
    assert strip.frame_names("skirt.png", 4) == ["skirt.f2.png", "skirt.f3.png", "skirt.f4.png"]
    assert strip.frame_names("a/b/flame.webp", 2) == ["a/b/flame.f2.webp"]
    assert strip.can_have("skirt") and strip.can_have("chest")
    assert not strip.can_have("head") and not strip.can_have("hand_l")


def test_the_server_takes_the_frames_files():
    for p in ("heroes/cow/puppet/parts/skirt.f2.png", "heroes/cow/puppet/parts/chest.f16.png",
              "sets/barn/crate.f2.png", "sets/barn/fire/flame.f3.webp"):
        assert folder.why_not(p) is None, p


# ------------------------------------------------------------------------------------------------- tadam strip

def test_a_strip_to_start_from_and_the_cut_on_a_set_piece(world, tmp_path, capsys):
    crate = world / "sets" / "barn" / "crate.png"
    assert cli.main(["--world", str(world), "strip", "sets/barn/crate.png", "--template", "3", "--json"]) == 0
    res = json.loads(capsys.readouterr().out)
    with Image.open(res["strip"]) as im, Image.open(crate) as first:
        assert im.size == (first.size[0] * 3, first.size[1]) and res["cell"] == list(first.size)
        assert im.crop((first.size[0], 0, first.size[0] * 2, first.size[1])).convert("RGBA").tobytes() \
            == first.convert("RGBA").tobytes()
    assert ".tadam/strip/" in res["strip"]                 # (the kit's own working files: never sent)

    sheet = _strip_of(crate, RGB[:3], tmp_path / "s.png")
    assert cli.main(["--world", str(world), "strip", "sets/barn/crate.png", str(sheet), "--count", "3", "--fps", "2",
                     "--offset", "0.5", "--json"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["frames"] == ["sets/barn/crate.png", "sets/barn/crate.f2.png", "sets/barn/crate.f3.png"]
    assert res["first"] == "kept_differs" and "hero" not in res
    st, _ = read_json(world / "sets" / "barn" / "set.json")
    assert st["pieces"][0]["frames"] == {"count": 3, "fps": 2.0, "offset": 0.5}
    with Image.open(crate) as first, Image.open(crate.with_name("crate.f2.png")) as f2, \
            Image.open(crate.with_name("crate.f3.png")) as f3:
        assert f2.size == f3.size == first.size
        assert f2.convert("RGBA").getpixel((5, 5)) == RGB[1] and f3.convert("RGBA").getpixel((5, 5)) == RGB[2]
        assert first.convert("RGBA").getpixel((5, 5)) == (90, 60, 40, 255)        # the drawing itself was kept
    assert "frames_invalid" not in _codes(world) and "set_file_missing" not in _codes(world)
    assert cli.main(["--world", str(world), "check"]) == 0


def test_the_first_cell_goes_over_the_drawing_only_when_asked(world, tmp_path, capsys):
    crate = world / "sets" / "barn" / "crate.png"
    sheet = _strip_of(crate, RGB[:2], tmp_path / "s.png")
    res = strip.cut(World(world), crate, sheet, 2, replace_first=True)
    assert res["first"] == "replaced" and Path(res["before"]).is_file()
    with Image.open(crate) as first, Image.open(res["before"]) as before:
        assert first.convert("RGBA").getpixel((5, 5)) == RGB[0]
        assert before.convert("RGBA").getpixel((5, 5)) == (90, 60, 40, 255)
    # the same strip once more: its first cell IS the drawing now
    assert strip.cut(World(world), crate, sheet, 2)["first"] == "kept"


def test_a_shorter_strip_and_the_way_back(world, tmp_path, capsys):
    w = World(world)
    crate = world / "sets" / "barn" / "crate.png"
    strip.cut(w, crate, _strip_of(crate, RGB, tmp_path / "s4.png"), 4, mode="pingpong", order=None)
    assert crate.with_name("crate.f4.png").is_file()
    assert read_json(world / "sets" / "barn" / "set.json")[0]["pieces"][0]["frames"]["mode"] == "pingpong"
    strip.cut(w, crate, _strip_of(crate, RGB[:2], tmp_path / "s2.png"), 2)
    assert crate.with_name("crate.f2.png").is_file() and not crate.with_name("crate.f3.png").exists()
    assert cli.main(["--world", str(world), "strip", "sets/barn/crate.png", "--off"]) == 0
    assert "one picture again" in capsys.readouterr().out
    assert not crate.with_name("crate.f2.png").exists() and crate.is_file()
    assert "frames" not in read_json(world / "sets" / "barn" / "set.json")[0]["pieces"][0]


def test_a_strip_on_a_part_of_a_puppet(world, tmp_path, capsys):
    part = world / "heroes" / "cow" / "puppet" / "parts" / "chest.png"
    sheet = _strip_of(part, RGB[:3], tmp_path / "s.png")
    assert cli.main(["--world", str(world), "strip", str(part), str(sheet), "--count", "3", "--order", "1,1,2,3"]) == 0
    out = capsys.readouterr().out
    assert "heroes/cow/puppet/rig.json parts.chest.frames" in out and "tadam hero check cow" in out
    rig, _ = read_json(part.parent.parent / "rig.json")
    assert rig["parts"]["chest"]["frames"] == {"count": 3, "fps": 8.0, "order": [1, 1, 2, 3]}
    assert part.with_name("chest.f3.png").is_file()
    codes = _codes(world)
    assert "puppet_parts_missing" not in codes and "frames_invalid" not in codes
    assert "hero_actions_stale" in codes                  # (the rig changed: its actions are played again)


def test_what_a_strip_cannot_be(world, tmp_path):
    w = World(world)
    parts = world / "heroes" / "cow" / "puppet" / "parts"
    crate = world / "sets" / "barn" / "crate.png"
    good = _strip_of(crate, RGB[:3], tmp_path / "s.png")
    for image, why in ((parts / "head.png", "head cannot be frames"), (parts / "hand_l.png", "cannot be frames"),
                       (world / "cover.png", "a puppet's part"), (world / "sets" / "barn" / "room.png", "no piece"),
                       (world / "sets" / "barn" / "nothing.png", "no drawing"),
                       (tmp_path / "s.png", "not inside this world")):
        with pytest.raises(WorldError, match=why):
            strip.cut(w, image, good, 3)
    with pytest.raises(WorldError, match="not 3 equal cells"):
        strip.cut(w, crate, _strip_of(crate, RGB[:1], tmp_path / "odd.png", cell=(200, 150)), 3)
    with pytest.raises(WorldError, match="another shape"):
        strip.cut(w, crate, _strip_of(crate, RGB[:3], tmp_path / "tall.png", cell=(100, 150)), 3)
    with pytest.raises(WorldError, match="count"):
        strip.cut(w, crate, good, 1)
    with pytest.raises(WorldError, match="2..16"):
        strip.template(w, crate, 40)
    strip.cut(w, crate, good, 3)
    with pytest.raises(WorldError, match="a frame itself"):
        strip.cut(w, crate.with_name("crate.f2.png"), good, 3)
    # a strip drawn at half the size is made the drawing's size (the same shape)
    res = strip.cut(w, crate, _strip_of(crate, RGB[:2], tmp_path / "half.png", cell=(100, 75)), 2)
    with Image.open(world / res["frames"][1]) as f2:
        assert f2.size == (200, 150)
    assert cli.main(["--world", str(world), "strip", "sets/barn/crate.png"]) == 2


# ------------------------------------------------------------------------------------------------- tadam check

def test_check_says_what_is_wrong_with_frames(world, tmp_path):
    sd = world / "sets" / "barn"
    st, _ = read_json(sd / "set.json")
    st["pieces"][0]["frames"] = {"count": 3, "fps": 4}
    write_json(sd / "set.json", st)
    missing = _codes(world)["set_file_missing"]
    assert {i.message for i in missing} == {"no file sets/barn/crate.f2.png", "no file sets/barn/crate.f3.png"}
    Image.new("RGBA", (200, 150), RGB[1]).save(sd / "crate.f2.png")
    Image.new("RGBA", (100, 150), RGB[2]).save(sd / "crate.f3.png")
    codes = _codes(world)
    assert "set_file_missing" not in codes
    assert "crate.f3.png is 100x150, the first frame is 200x150" in codes["frames_size"][0].message
    st["pieces"][0]["frames"] = {"count": 40, "fps": 400, "mode": "x"}
    write_json(sd / "set.json", st)
    assert len(_codes(world)["frames_invalid"]) == 3

    pdir = world / "heroes" / "cow" / "puppet"
    rig, _ = read_json(pdir / "rig.json")
    rig["parts"]["head"]["frames"] = {"count": 2}
    rig["parts"]["chest"]["frames"] = {"count": 2}
    write_json(pdir / "rig.json", rig)
    codes = _codes(world)
    assert "head cannot be frames" in codes["frames_ignored"][0].message
    assert any("chest.f2.png" in i.message for i in codes["puppet_parts_missing"])


def test_many_large_frames_are_a_warning(world):
    sd = world / "sets" / "barn"
    Image.new("RGBA", (2000, 1600), RGB[0]).save(sd / "crate.png")
    for k in range(2, 9):
        Image.new("RGBA", (2000, 1600), RGB[1]).save(sd / f"crate.f{k}.png")
    st, _ = read_json(sd / "set.json")
    st["pieces"][0]["frames"] = {"count": 8}
    write_json(sd / "set.json", st)
    assert "26 megapixels" in _codes(world)["frames_heavy"][0].message


def test_frames_left_without_a_record_are_named(world, tmp_path):
    """A puppet made again writes its rig.json anew: the frames cut before are left lying and are named."""
    w = World(world)
    part = world / "heroes" / "cow" / "puppet" / "parts" / "chest.png"
    crate = world / "sets" / "barn" / "crate.png"
    strip.cut(w, part, _strip_of(part, RGB[:3], tmp_path / "p.png"), 3)
    strip.cut(w, crate, _strip_of(crate, RGB[:3], tmp_path / "c.png"), 3)
    assert "frames_unused" not in _codes(world)
    rig, _ = read_json(part.parent.parent / "rig.json")
    rig["parts"]["chest"]["frames"]["count"] = 2            # (a record that shows fewer than there are)
    write_json(part.parent.parent / "rig.json", rig)
    st, _ = read_json(crate.parent / "set.json")
    del st["pieces"][0]["frames"]
    write_json(crate.parent / "set.json", st)
    left = {i.where: i.message for i in _codes(world)["frames_unused"]}
    assert "chest.f3.png" in left["heroes/cow/puppet/parts"] and "chest.f2.png" not in left["heroes/cow/puppet/parts"]
    assert "crate.f2.png, crate.f3.png" in left["sets/barn"]
    strip.clear(w, crate)
    assert list(_codes(world)["frames_unused"][0].where.split("/"))[0] == "heroes"


# ------------------------------------------------------------------------------------------------- the engine

def _frames_check(*args: str) -> dict:
    engine.ensure_imported()
    p = subprocess.run([engine.godot(), "--headless", "--path", str(engine_dir()), "--script",
                        "res://tools/frames_check.gd", "--", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    for line in p.stdout.splitlines():
        if line.startswith("FRAMES "):
            return json.loads(line[7:])
    raise AssertionError(p.stdout[-2000:] + p.stderr[-2000:])


@needs_godot
def test_which_frame_is_shown_when(tmp_path):
    specs = [{"count": 3, "fps": 30},                                   # a frame is two steps
             {"count": 3, "fps": 30, "mode": "pingpong"},
             {"count": 3, "fps": 30, "mode": "once"},
             {"count": 2, "fps": 30, "order": [1, 1, 2]},
             {"count": 4, "fps": 30, "offset": 0.5},
             {"count": 1}, "nonsense"]
    (tmp_path / "specs.json").write_text(json.dumps(specs), encoding="utf-8")
    got = _frames_check(f"--specs={(tmp_path / 'specs.json').as_posix()}", "--steps=12")["specs"]
    assert got[0] == [1, 2, 2, 3, 3, 1, 1, 2, 2, 3, 3, 1]
    assert got[1] == [1, 2, 2, 3, 3, 2, 2, 1, 1, 2, 2, 3]
    assert got[2] == [1, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3]
    assert got[3] == [1, 1, 1, 2, 2, 1, 1, 1, 1, 2, 2, 1]
    assert got[4] == [3, 4, 4, 1, 1, 2, 2, 3, 3, 4, 4, 1]
    assert got[5] == [0] * 12 and got[6] == [0] * 12                    # (no frames asked for)


@needs_godot
def test_parts_of_a_puppet_go_each_at_its_own_speed(world, tmp_path):
    w = World(world)
    pdir = world / "heroes" / "cow" / "puppet"
    for part, n, fps in (("chest", 3, 30), ("pelvis", 2, 15)):
        img = pdir / "parts" / f"{part}.png"
        strip.cut(w, img, _strip_of(img, RGB[:n], tmp_path / f"{part}.png"), n, fps=fps)
    # the head's record is not played, and a part whose frame is missing stays one drawing
    rig, _ = read_json(pdir / "rig.json")
    rig["parts"]["head"]["frames"] = {"count": 2}
    rig["parts"]["thigh_l"]["frames"] = {"count": 2}
    write_json(pdir / "rig.json", rig)
    Image.new("RGBA", (10, 10), RGB[0]).save(pdir / "parts" / "head.f2.png")
    res = _frames_check(f"--puppet={pdir.as_posix()}", "--steps=12")
    assert sorted(res["framed"]) == ["chest", "pelvis"] and res["shown"] is True
    assert res["parts"]["chest"] == [1, 2, 2, 3, 3, 1, 1, 2, 2, 3, 3, 1]
    assert res["parts"]["pelvis"] == [1, 1, 1, 2, 2, 2, 2, 1, 1, 1, 1, 2]
    # twice as fast, standing still, and from the first frame again
    res = _frames_check(f"--puppet={pdir.as_posix()}", "--steps=8", "--speed=chest:2,pelvis:0")
    assert res["parts"]["chest"] == [2, 3, 1, 2, 3, 1, 2, 3] and res["parts"]["pelvis"] == [1] * 8
    res = _frames_check(f"--puppet={pdir.as_posix()}", "--steps=8", "--restart=chest:5")
    assert res["parts"]["chest"] == [1, 2, 2, 3, 1, 2, 2, 3]


def _dominant(png: str) -> str:
    """Which of the pure test colours fills the most of a picture: r, g or b."""
    with Image.open(png) as im:
        raw = im.convert("RGB").resize((180, 320)).tobytes()
    n = {"r": 0, "g": 0, "b": 0}
    for r, g, b in zip(raw[0::3], raw[1::3], raw[2::3]):
        if r > 180 and g < 90 and b < 90:
            n["r"] += 1
        elif g > 180 and r < 90 and b < 90:
            n["g"] += 1
        elif b > 180 and r < 90 and g < 90:
            n["b"] += 1
    best = max(n, key=n.get)
    assert n[best] > 200 and sum(n.values()) - n[best] < n[best] / 20, n
    return best


@needs_godot
def test_a_set_piece_of_a_scene_plays_its_frames_and_a_seek_lands_on_the_same_one(world, tmp_path, capsys):
    crate = world / "sets" / "barn" / "crate.png"
    strip.cut(World(world), crate, _strip_of(crate, RGB[:3], tmp_path / "s.png"), 3, fps=2, replace_first=True)
    seen = {}
    for at in ("0.25", "0.75", "1.25", "1.75", "0.75"):                # (sh3 lasts 2 s; a frame is half a second)
        out = tmp_path / f"at{at}-{len(seen)}.png"
        assert cli.main(["--world", str(world), "frames", "1", "--shot", "sh3", "--at", at, "--out", str(out)]) == 0
        capsys.readouterr()
        seen.setdefault(at, []).append(_dominant(str(out)))
    assert seen == {"0.25": ["r"], "0.75": ["g", "g"], "1.25": ["b"], "1.75": ["r"]}


@needs_godot
def test_in_the_window_a_step_on_and_back_shows_the_same_frame(world, tmp_path):
    """The real window (keys from PLAYER_SEQ, as in test_pause): stopped in sh3 at 0.75 s the crate shows frame 2
    (green); a second on, frame 1 of the next round (red); a second back, frame 2 again."""
    w = World(world)
    crate = world / "sets" / "barn" / "crate.png"
    strip.cut(w, crate, _strip_of(crate, RGB[:3], tmp_path / "s.png"), 3, fps=2, replace_first=True)
    ep = episode.build(w, "1", voice=False)
    run = render.Run(tmp_path / "run")
    run.dir.mkdir()
    render.clear_state(w)
    f = render.Watch(ep, run, lambda: ep).write(ep, None, start=2, start_at=0.75, paused=True)
    a, b, c = ((tmp_path / f"{n}.png").as_posix() for n in "abc")
    seq = f"30:shot={a},40:shift+right,70:shot={b},80:shift+left,110:shot={c},130:quit"
    cmd = render.command(engine.godot(), "play", f, ep.size, window=(450, 800))
    cmd[cmd.index("--position") + 1] = render.OFF_SCREEN
    engine.ensure_imported()
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                       env={**os.environ, "PLAYER_SEQ": seq})
    out = p.stdout + p.stderr
    assert "PLAYER done" in out and "SCRIPT ERROR" not in out, out[-2000:]
    assert "PLAYER seq shift+right at sh3 105" in out and "PLAYER seq shift+left at sh3 45" in out
    assert [_dominant(x) for x in (a, b, c)] == ["g", "r", "g"]
