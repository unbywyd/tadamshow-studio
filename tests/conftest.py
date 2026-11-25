"""Shared fixtures: a small, complete world folder whose path has spaces and non-latin letters, a code-drawn puppet
(the rig's own mannequin: no image model), and a fake OpenAI client. Nothing in the tests reaches the network."""
from __future__ import annotations

import base64
import io
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from tadam import new, openai_images
from tadam.puppet import mannequin
from tadam.world import World, write_json


def png_bytes(size=(64, 64), color=(200, 120, 80, 255), mode="RGBA") -> bytes:
    im = Image.new(mode, size, color if mode == "RGBA" else color[:3])
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def own_config(monkeypatch, tmp_path_factory):
    """No test sees the person's real studio key: the config folder is a fresh temp one, no key in the env."""
    monkeypatch.setenv("TADAM_CONFIG_DIR", str(tmp_path_factory.mktemp("config")))
    monkeypatch.delenv("TADAM_STUDIO_KEY", raising=False)
    monkeypatch.delenv("TADAM_STUDIO_URL", raising=False)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every test runs with a client that refuses to be made: a test that wants generation installs its fake."""
    def refuse():
        raise AssertionError("a test tried to reach the OpenAI API")
    old = openai_images.set_client(refuse)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    yield
    openai_images.set_client(old)


class FakeImages:
    """Stands in for client.images: answers each call from `answers` (a list of PNG bytes, or a function)."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def _answer(self, kind, kw):
        kw = {**kw, **kw.pop("extra_body", {})}
        self.calls.append((kind, kw))
        a = self.answers(kind, kw, len(self.calls)) if callable(self.answers) else self.answers[len(self.calls) - 1]
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(a).decode())], usage=None)

    def generate(self, **kw):
        return self._answer("generations", kw)

    def edit(self, image, **kw):
        kw["images"] = [Path(f.name).name for f in image]
        return self._answer("edits", kw)


@pytest.fixture
def fake_openai(monkeypatch):
    """fake_openai(answers) -> FakeImages; the env key is set to a dummy (never printed)."""
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-test-key-not-real")

    def install(answers):
        images = FakeImages(answers)
        openai_images.set_client(lambda: SimpleNamespace(images=images))
        return images
    return install


@pytest.fixture(scope="session")
def mannequin_puppet(tmp_path_factory) -> Path:
    """One cut mannequin puppet for the whole session (cutting takes a second or two)."""
    d = tmp_path_factory.mktemp("mannequin") / "puppet"
    report = mannequin.make(d, log=lambda *_: None)
    assert report["passed"], report
    write_passed_actions(d)
    return d


def write_passed_actions(pdir: Path) -> None:
    """actions.json as `tadam hero check` writes it for a hero that passes every stage-1 action (no engine run:
    tests/test_actions.py runs the engine itself)."""
    from tadam import actions
    raw = {"limits": {}, "runs": [{"action": a, "side": "right", "faults": []} for a in actions.STAGE1]}
    res = actions.summarise(raw, {}, actions.rig_sha(pdir), 0.0)
    (Path(pdir) / actions.FILE).write_text(json.dumps(res), encoding="utf-8")


@pytest.fixture(scope="session")
def mannequin_sheet_png() -> bytes:
    buf = io.BytesIO()
    mannequin.sheet("humanoid-a").save(buf, "PNG")
    return buf.getvalue()


def fill_texts(root: Path):
    """Replace the templates' TODO texts with real ones."""
    wj = root / "world.json"
    w = json.loads(wj.read_text(encoding="utf-8"))
    w["tagline"] = {"ru": "Корова ищет луну"}
    w["description"] = {"ru": "Короткие серии о корове и сыщике."}
    w["bible"] = {"idea": {"ru": "Сыщик и корова"}, "tone": {"ru": "Спокойно и смешно"},
                  "style": {"ru": "Плоская гуашь", "en": "flat gouache"}, "rules": [{"ru": "Без злобы"}],
                  "heroes": {"ru": "Корова и сыщик"}}
    write_json(wj, w)


def make_world(parent: Path, puppet: Path, name: str = "мир с пробелом") -> Path:
    """A complete world: two heroes with puppets, a set with a room and a piece, music, one episode of 3 shots."""
    parent = Path(parent) / name
    parent.mkdir(parents=True, exist_ok=True)
    root = new.world(parent, "moon-cow", "Корова и луна")
    fill_texts(root)
    Image.new("RGB", (90, 160), (90, 110, 140)).save(root / "cover.png")
    w = World(root)
    for slug, nm in (("cow", "Корова"), ("detective", "Сыщик")):
        d = new.hero(w, slug, nm)
        hj = json.loads((d / "hero.json").read_text(encoding="utf-8"))
        hj["trait"] = {"ru": "упрямая" if slug == "cow" else "сонный"}
        write_json(d / "hero.json", hj)
        shutil.copytree(puppet, w.puppet_dir(slug))
    sd = new.set_(w, "barn")
    room = Image.new("RGB", (720, 1280), (200, 210, 190))
    ImageDraw.Draw(room).rectangle([0, 1000, 720, 1280], fill=(150, 120, 90))
    room.save(sd / "room.png")
    Image.new("RGBA", (200, 150), (90, 60, 40, 255)).save(sd / "crate.png")
    st = json.loads((sd / "set.json").read_text(encoding="utf-8"))
    st["pieces"] = [{"id": "crate", "image": "crate.png", "rect": [0.05, 0.6, 0.3, 0.15], "base": 0.75}]
    write_json(sd / "set.json", st)
    (root / "media").mkdir(exist_ok=True)
    (root / "media" / "theme.mp3").write_bytes(b"ID3fake")
    (root / "media" / "cup.png").write_bytes(png_bytes((40, 60)))
    script = {
        "version": 2,
        "cast": {"cow": {"character": "cow"}, "det": {"character": "detective"}},
        "roles": {
            "cow": [{"key": "cow-1", "kind": "read", "text": {"ru": "Где моя луна?"},
                     "hint": {"ru": "Удивлённо, телефон на уровне глаз"}, "look": [{"target": "lens"}],
                     "maxSeconds": 5}],
            "det": [{"key": "det-1", "kind": "read", "text": {"ru": "Сейчас найдём."},
                     "hint": {"ru": "Спокойно"}, "look": [{"target": "mark_left"}], "maxSeconds": 5},
                    {"key": "det-2", "kind": "pause", "hint": {"ru": "Молча слушай"}, "look": [{"target": "lens"}]}],
        },
        "shots": [
            {"id": "sh1", "remark": {"ru": "Корова спрашивает"}, "say": "cow-1", "listen": {"det": "det-2"},
             "actors": [{"id": "cow", "x": 0.3}, {"id": "det", "x": 0.72, "depth": 0.5}],
             "camera": [{"at": 0, "camera": "medium", "on": "cow"}]},
            {"id": "sh2", "remark": {"ru": "Сыщик отвечает"}, "say": "det-1",
             "actors": [{"id": "det", "x": 0.5, "prop": "cup.png"}], "focus": {"on": "det"},
             "camera": [{"at": 0, "camera": "close", "on": "det"}]},
            {"id": "sh3", "remark": {"ru": "Двор"}, "seconds": 2, "actors": [{"id": "cow", "x": 0.5, "depth": 0.6}],
             "narration": {"text": {"ru": "А луна была рядом."}}},
        ],
        "film": {"set": "barn", "music": {"file": "theme.mp3", "db": -12}, "stage": {"faces": "board"}},
    }
    (root / "episodes" / "1").mkdir(parents=True, exist_ok=True)
    write_json(root / "episodes" / "1" / "script.json", script)
    return root


@pytest.fixture
def world(tmp_path, mannequin_puppet) -> Path:
    return make_world(tmp_path, mannequin_puppet)
