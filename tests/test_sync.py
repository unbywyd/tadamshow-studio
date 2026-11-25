"""The kit and the server: login, push, pull (the three-way merge), diff, status, against a local fake server that
answers as the contract says (tests/fake_studio.py). Nothing reaches the real or the dev server."""
from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

import pytest

from fake_studio import EMAIL, KEY, Server
from tadam import api, cli, folder, link, sync
from tadam.world import write_json


@pytest.fixture
def fake(monkeypatch):
    with Server() as f:
        monkeypatch.setenv(link.URL_ENV, f.base)
        yield f


@pytest.fixture
def keyed(fake, monkeypatch):
    monkeypatch.setenv(link.KEY_ENV, KEY)
    return fake


def run(capsys, *argv) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def edit_script(root: Path, fn):
    p = root / "episodes/1/script.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    fn(s)
    write_json(p, s)


# ------------------------------------------------------------------------------------------------ login

def test_login_stores_the_key_privately_and_never_prints_it(fake, monkeypatch, capsys, world):
    monkeypatch.setenv(link.KEY_ENV, KEY)
    code, out = run(capsys, "login")
    assert code == 0, out
    assert KEY not in out and "S3cret" not in out
    assert link.mask_email(EMAIL) in out and EMAIL not in out and link.mask_email(EMAIL).startswith("e***")
    f = link.config_dir() / link.FILE
    assert f.is_file() and KEY in f.read_text(encoding="utf-8")
    assert world not in f.parents                           # never inside a world folder
    if os.name == "posix":
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
        assert stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    # without the env var, the stored key is used (and the repr never shows it)
    monkeypatch.delenv(link.KEY_ENV)
    lk = link.current()
    assert lk is not None and lk.key == KEY and lk.source == "stored" and KEY not in repr(lk)
    code, out = run(capsys, "status")
    assert code == 0 and KEY not in out
    # the narration bridge uses it too
    from tadam import tts
    assert tts.link_from_env().key == KEY
    code, out = run(capsys, "logout")
    assert code == 0 and not f.exists() and link.current() is None


@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX")
def test_private_file_mode(tmp_path):
    f = tmp_path / "c" / "credentials.json"
    link._write_private(f, "{}")
    assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_login_refuses_a_wrong_key_and_stores_nothing(fake, monkeypatch, capsys):
    monkeypatch.setenv(link.KEY_ENV, "tds_zzzz9999_" + "W" * 24)
    code, out = run(capsys, "login")
    assert code == 1 and "refused" in out and "W" * 24 not in out
    assert not (link.config_dir() / link.FILE).exists()


def test_login_wants_a_keyboard_or_the_env(fake, capsys):
    code, out = run(capsys, "login")                         # (pytest's stdin is not a terminal)
    assert code == 2 and "real keyboard" in out and not (link.config_dir() / link.FILE).exists()
    code, out = run(capsys, "login", "--key")
    assert code == 2 and "real keyboard" in out and not (link.config_dir() / link.FILE).exists()
    assert not fake.mails                                    # (no code was asked for without a person)


def test_login_refuses_what_is_not_a_studio_key(fake, monkeypatch, capsys):
    monkeypatch.setenv(link.KEY_ENV, "tdm" + "_staffkey_" + "x" * 30)
    code, out = run(capsys, "login")
    assert code == 2 and "not a studio key" in out and "x" * 30 not in out


def test_config_dir_per_system(monkeypatch):
    monkeypatch.delenv(link.CONFIG_ENV)
    assert link.config_dir({"APPDATA": r"C:\A"}, "win32") == Path(r"C:\A") / "tadam"
    assert link.config_dir({"HOME": "/h"}, "darwin") == Path("/h/Library/Application Support/tadam")
    assert link.config_dir({"HOME": "/h"}, "linux") == Path("/h/.config/tadam")
    assert link.config_dir({"HOME": "/h", "XDG_CONFIG_HOME": "/x"}, "linux") == Path("/x/tadam")


def test_no_key_says_what_to_do(fake, capsys, world):
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 1 and "tadam login" in out


# ------------------------------------------------------------------------------------------------ the manifest

def test_manifest_keeps_the_kits_own_files_home(world):
    (world / ".tadam" / "x").mkdir(parents=True)
    (world / ".tadam" / "x" / "a.json").write_text("{}", encoding="utf-8")
    (world / "heroes/cow/puppet/check.jpg").write_bytes(b"jpg")
    (world / "notes.txt").write_text("mine", encoding="utf-8")
    (world / ".DS_Store").write_bytes(b"x")
    sc = folder.scan(world)
    assert "world.json" in sc.manifest and "episodes/1/script.json" in sc.manifest
    assert "heroes/cow/puppet/parts/head.png" in sc.manifest and "heroes/cow/puppet/actions.json" in sc.manifest
    assert not any(p.startswith(".tadam") for p in sc.manifest)
    assert {p for p, _ in sc.local_only} >= {"heroes/cow/puppet/check.jpg", "notes.txt"}
    m = sc.manifest["world.json"]
    import hashlib
    assert m["sha256"] == hashlib.sha256((world / "world.json").read_bytes()).hexdigest()
    assert m["bytes"] == (world / "world.json").stat().st_size


@pytest.mark.parametrize("path", ["../../etc/passwd.json", "media/x.exe", "media\\x.png", "user://x.png",
                                  "media/.hidden.png", "heroes/Cow/hero.json", "episodes/0/script.json",
                                  "media/a.svg.png", "con.json", "media/x.PNG", "heroes/cow/puppet/a/b/c/d.png"])
def test_paths_the_server_refuses(path):
    assert folder.why_not(path)


@pytest.mark.parametrize("path", ["world.json", "sources.json", "cover.jpg", "heroes/cow/hero.json",
                                  "heroes/cow/puppet/parts/head.open.png", "sets/barn/far/city.png",
                                  "media/music/theme.mp3", "episodes/12/episode.json", "episodes/3/cover.webp"])
def test_paths_the_server_takes(path):
    assert folder.why_not(path) is None


# ------------------------------------------------------------------------------------------------ push

def test_push_sends_only_what_the_server_lacks(keyed, world, capsys):
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 0, out
    man = folder.scan(world).manifest
    shas = {m["sha256"] for m in man.values()}
    assert len(keyed.puts) == len(shas)                    # each content once (the two puppets are the same files)
    assert "revision 1" in out and "https://tadamshow.com/ru/w/moon-cow" in out and "cover_small" in out
    assert json.loads((world / ".tadam/link.json").read_text(encoding="utf-8"))["rev"] == 1
    assert keyed.leaks == []                               # the key never went to a storage link
    # again, unchanged: nothing is uploaded, a new revision from rev 1
    keyed.puts.clear()
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 0 and keyed.puts == [] and "revision 2" in out and "0 file(s) sent" in out
    # one changed file: only it
    edit_script(world, lambda s: s["shots"][0]["camera"].append({"at": 1, "camera": "close", "on": "cow"}))
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 0 and keyed.puts == ["episodes/1/script.json"] and "revision 3" in out
    assert keyed.worlds["moon-cow"]["revs"][-1]["manifest"] == folder.scan(world).manifest


def test_push_calls_only_a_draft_world_a_draft(keyed, world, capsys):
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 0 and "draft on the site (only you see it): https://tadamshow.com/ru/w/moon-cow" in out
    # a live world (the owner adopting a published one, or a world after approval) is on the site for everyone
    keyed.worlds["moon-cow"]["status"] = "live"
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 0 and "on the site: https://tadamshow.com/ru/w/moon-cow" in out and "only you see it" not in out


def test_push_refuses_a_stale_base(keyed, world, tmp_path, capsys):
    assert run(capsys, "--world", str(world), "push")[0] == 0
    assert run(capsys, "pull", "moon-cow", "--dir", str(tmp_path / "b"))[0] == 0
    other = tmp_path / "b" / "moon-cow"
    (world / "media" / "new.png").write_bytes((world / "media" / "cup.png").read_bytes() + b"x")
    assert run(capsys, "--world", str(world), "push")[0] == 0           # rev 2 from the first folder
    keyed.puts.clear()
    code, out = run(capsys, "--world", str(other), "push")              # the second is still at rev 1
    assert code == 1 and "tadam pull" in out and "(2)" in out and keyed.puts == []


def test_push_refuses_when_the_check_finds_errors(keyed, world, capsys):
    edit_script(world, lambda s: s["shots"][0].update(say="nobody"))
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 1 and "say_unknown" in out and "nothing was sent" in out
    assert keyed.calls == []


def test_push_refuses_unmerged_server_copies(keyed, world, capsys):
    (world / "episodes/1/script.json.server").write_text("{}", encoding="utf-8")
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 1 and "not merged" in out and keyed.calls == []


def test_breaking_change_needs_confirm(keyed, world, capsys):
    keyed.breaking.add("moon-cow")
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 1 and "BREAKING" in out and "2 sent role(s)" in out and "cow-1" in out and "--confirm" in out
    assert not (world / ".tadam/link.json").exists()
    code, out = run(capsys, "--world", str(world), "push", "--confirm")
    assert code == 0 and "revision 1" in out


def test_push_refuses_a_slug_changed_after_linking(keyed, world, capsys):
    assert run(capsys, "--world", str(world), "push")[0] == 0
    p = world / "world.json"
    w = json.loads(p.read_text(encoding="utf-8"))
    w["slug"] = "other-name"
    write_json(p, w)
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 1 and "moon-cow" in out


# ------------------------------------------------------------------------------------------------ pull

def test_pull_first_time_and_three_way_merge(keyed, world, tmp_path, capsys):
    a = world
    (a / "media" / "gone.png").write_bytes(b"\x89PNG gone")
    (a / "media" / "mine.png").write_bytes(b"\x89PNG mine")
    assert run(capsys, "--world", str(a), "push")[0] == 0
    code, out = run(capsys, "pull", "moon-cow", "--dir", str(tmp_path / "b"))
    assert code == 0 and "revision 1" in out
    b = tmp_path / "b" / "moon-cow"
    assert folder.scan(b).manifest == folder.scan(a).manifest
    assert json.loads((b / ".tadam/link.json").read_text(encoding="utf-8"))["rev"] == 1

    # A (the owner, say): changes the world card, the script, removes two files; pushes rev 2
    w = json.loads((a / "world.json").read_text(encoding="utf-8"))
    w["tagline"] = {"ru": "Новый слоган"}
    write_json(a / "world.json", w)
    edit_script(a, lambda s: s["shots"][2].update(seconds=3))
    (a / "media" / "gone.png").unlink()
    (a / "media" / "mine.png").unlink()
    assert run(capsys, "--world", str(a), "push")[0] == 0
    # B, meanwhile: a new hero trait (only here), the same script changed otherwise (both), mine.png changed
    hj = json.loads((b / "heroes/cow/hero.json").read_text(encoding="utf-8"))
    hj["trait"] = {"ru": "очень упрямая"}
    write_json(b / "heroes/cow/hero.json", hj)
    edit_script(b, lambda s: s["shots"][0].update(remark={"ru": "Корова спрашивает тихо"}))
    mine_script = (b / "episodes/1/script.json").read_bytes()
    (b / "media" / "mine.png").write_bytes(b"\x89PNG changed here")

    code, out = run(capsys, "--world", str(b), "pull")
    assert code == 0, out
    # only on the server -> taken
    assert json.loads((b / "world.json").read_text(encoding="utf-8"))["tagline"] == {"ru": "Новый слоган"}
    # only here -> mine
    assert json.loads((b / "heroes/cow/hero.json").read_text(encoding="utf-8"))["trait"] == {"ru": "очень упрямая"}
    # both -> mine stays, the server's next to it
    assert (b / "episodes/1/script.json").read_bytes() == mine_script
    srv = json.loads((b / "episodes/1/script.json.server").read_text(encoding="utf-8"))
    assert srv["shots"][2]["seconds"] == 3
    assert "episodes/1/script.json.server" in out and "CHANGED IN BOTH" in out
    # removed on the server, unchanged here -> moved aside, not deleted
    assert not (b / "media/gone.png").exists()
    moved = list((b / ".tadam/removed").glob("*/media/gone.png"))
    assert len(moved) == 1 and moved[0].read_bytes() == b"\x89PNG gone" and "media/gone.png" in out
    # removed on the server, changed here -> kept
    assert (b / "media/mine.png").read_bytes() == b"\x89PNG changed here"
    assert json.loads((b / ".tadam/link.json").read_text(encoding="utf-8"))["rev"] == 2
    # a push now waits for the merge
    code, out = run(capsys, "--world", str(b), "push")
    assert code == 1 and "not merged" in out
    (b / "episodes/1/script.json.server").unlink()
    code, out = run(capsys, "--world", str(b), "push")
    assert code == 0 and "revision 3" in out


def test_merge_plan_every_case():
    m = lambda s: {"sha256": s * 64, "bytes": 1}          # noqa: E731
    base = {"same": m("a"), "srv": m("a"), "here": m("a"), "both": m("a"), "gone": m("a"), "gone_changed": m("a"),
            "i_removed": m("a")}
    local = {"same": m("a"), "srv": m("a"), "here": m("b"), "both": m("b"), "gone": m("a"), "gone_changed": m("b"),
             "new_here": m("c")}
    server = {"same": m("a"), "srv": m("c"), "here": m("a"), "both": m("d"), "i_removed": m("a"), "new_srv": m("e")}
    p = sync.merge_plan(base, local, server)
    assert p == {"take": ["new_srv", "srv"], "keep": ["here", "i_removed", "new_here"], "conflict": ["both"],
                 "remove": ["gone"], "keep_removed": ["gone_changed"]}


def test_pull_refuses_a_non_empty_folder_and_a_foreign_path(keyed, world, tmp_path, capsys):
    assert run(capsys, "--world", str(world), "push")[0] == 0
    (tmp_path / "c" / "moon-cow").mkdir(parents=True)
    (tmp_path / "c" / "moon-cow" / "x.txt").write_text("x", encoding="utf-8")
    code, out = run(capsys, "pull", "moon-cow", "--dir", str(tmp_path / "c"))
    assert code == 1 and "not empty" in out
    with pytest.raises(sync.SyncError):
        sync._inside(tmp_path, "../evil.json")


def test_pull_checks_what_it_downloads(keyed, world, tmp_path, capsys):
    assert run(capsys, "--world", str(world), "push")[0] == 0
    key = next(iter(keyed.blobs))
    keyed.blobs[key] = keyed.blobs[key] + b"tampered"
    code, out = run(capsys, "pull", "moon-cow", "--dir", str(tmp_path / "d"))
    assert code == 1 and ("does not match" in out or "larger" in out)


# ------------------------------------------------------------------------------------------------ diff

def test_script_diff_by_shots_and_steps():
    old = {"cast": {"cow": {"character": "cow"}},
           "roles": {"cow": [{"key": "cow-1", "kind": "read", "text": {"ru": "А"}, "hint": {"ru": "x"}}]},
           "shots": [{"id": "sh1", "say": "cow-1", "camera": []}, {"id": "sh2", "seconds": 2}], "film": {"set": "a"}}
    new = {"cast": {"cow": {"character": "cow"}},
           "roles": {"cow": [{"key": "cow-1", "kind": "read", "text": {"ru": "Б"}, "hint": {"ru": "x"}},
                             {"key": "cow-2", "kind": "pause"}]},
           "shots": [{"id": "sh1", "say": "cow-1", "camera": [{"at": 0, "camera": "close"}], "remark": {"ru": "r"}},
                     {"id": "sh3", "seconds": 1}], "film": {"set": "b"}}
    d = sync.script_diff(old, new)
    assert d["shots"] == {"added": ["sh3"], "removed": ["sh2"], "changed": {"sh1": ["camera", "remark"]}}
    assert d["steps"] == {"added": ["cow-2"], "removed": [], "changed": {"cow-1": ["text"]}}
    assert d["film"] == ["set"] and d["cast"] == []


def test_diff_local_against_the_server_and_revisions(keyed, world, capsys):
    assert run(capsys, "--world", str(world), "push")[0] == 0
    code, out = run(capsys, "--world", str(world), "diff")
    assert code == 0 and "no differences" in out
    edit_script(world, lambda s: (s["shots"][1]["camera"].append({"at": 1, "camera": "medium", "on": "det"}),
                                  s["roles"]["cow"].append({"key": "cow-2", "kind": "pause", "hint": {"ru": "Жди"},
                                                            "look": [{"target": "lens"}]})))
    code, out = run(capsys, "--world", str(world), "diff")
    assert code == 0 and "server rev 1" in out and "~ episodes/1/script.json" in out
    assert "~ shot sh2: camera" in out and "+ step cow-2" in out
    assert run(capsys, "--world", str(world), "push")[0] == 0
    code, out = run(capsys, "--world", str(world), "diff", "1", "2")
    assert code == 0 and "rev 1  ->  rev 2" in out and "+ step cow-2" in out
    code, out = run(capsys, "--world", str(world), "diff", "1", "--json")
    d = json.loads(out)
    assert d["episodes"]["1"]["shots"]["changed"] == {"sh2": ["camera"]}
    code, out = run(capsys, "--world", str(world), "diff", "7")
    assert code == 1 and "has not seen revision 7" in out


# ------------------------------------------------------------------------------------------------ status

STATUS = {
    "worlds": [{"id": "w1", "slug": "moon-cow", "title": {"ru": "Корова и луна"}, "status": "draft", "rev": 3,
                "lastPush": {"rev": 3, "at": "2026-11-25T12:00:00.000Z", "by": "u1", "ok": True},
                "episodes": [{"number": 1, "title": {"ru": "Пропала луна"}, "status": "script", "draft": False,
                              "submission": None,
                              "missing": [{"code": "studio_version", "message": "record the roles on the site and "
                                           "make the studio version from the current revision"}]}]}],
    "submissions": [{"id": "s1", "kind": "publish", "status": "changes", "world": "moon-cow", "episode": 1,
                     "createdAt": "2026-11-24T10:00:00.000Z"}],
    "unread": 1,
    "notifications": [{"id": "n1", "kind": "studioRemark", "text": "План sh2: камера слишком близко",
                       "at": "2026-11-25T09:30:00.000Z"}],
}


def test_status_for_a_person_and_for_claude(keyed, world, capsys):
    keyed.status_doc = STATUS
    write_json(world / ".tadam/link.json", {"url": keyed.base, "slug": "moon-cow", "rev": 2})
    code, out = run(capsys, "--world", str(world), "status")
    assert code == 0
    for want in ("world moon-cow «Корова и луна»: draft, revision 3", "check ok", "this folder is at revision 2",
                 "episode 1 «Пропала луна»: script", "studio version", "[studio_version]",
                 "s1: publish moon-cow episode 1, changes", "unread remarks and notices: 1",
                 "План sh2: камера слишком близко"):
        assert want in out, (want, out)
    code, out = run(capsys, "status", "--json")
    assert json.loads(out) == STATUS


def test_api_errors_keep_reason_and_todo(keyed):
    a = api.Api(link.current())
    with pytest.raises(api.ApiError) as e:
        a.get("/api/studio/worlds/nope/pull")
    assert e.value.status == 404
    bad = api.Api(link.Link(keyed.base, "tds_zzzz9999_" + "Q" * 24))
    with pytest.raises(api.ApiError) as e:
        bad.get("/api/studio/me")
    assert e.value.status == 401 and e.value.reason == "bad_key" and "tadam login" in str(e.value)
    assert "Q" * 24 not in str(e.value)
    with pytest.raises(api.ApiError):
        api.Api(link.Link("http://example.com", KEY))           # plain http only on this computer


def test_uploads_are_retried(monkeypatch):
    import urllib.error
    tries = []

    def opener(req, timeout):
        tries.append(req.full_url)
        if len(tries) < 3:
            raise urllib.error.URLError("blip")

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, *a):
                return b""
        return R()
    a = api.Api(link.Link("https://studio.example", KEY), opener=opener, sleep=lambda s: None)
    a.upload("https://store.example/u", b"data", {"content-type": "image/png", "Authorization": "x"})
    assert len(tries) == 3
