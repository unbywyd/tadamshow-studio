"""Submissions (submit, the studio version, reply, withdraw, unpublish, the threads in status) and the owner's review
from the terminal (list, show, approve / reject with the typed id, return with shot remarks) against the local fake
server (tests/fake_studio.py: every answer checked against schema/)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fake_studio import EMAIL, KEY, STAFF_KEY, Server
from tadam import cli, keyboard, link

NOT_READY = [{"code": "studio_version", "message": "record the roles on the site and make the studio version from "
                                                   "the current revision"},
             {"code": "puppet", "message": "the puppet of cow did not pass its check"}]


@pytest.fixture
def fake(monkeypatch):
    with Server() as f:
        monkeypatch.setenv(link.URL_ENV, f.base)
        monkeypatch.setenv(link.KEY_ENV, KEY)
        f.episodes[("moon-cow", 1)] = {"status": "script", "title": "Пропала луна", "missing": [dict(NOT_READY[0])]}
        f.videos["v1"] = {"slug": "moon-cow", "n": 1, "current": True}
        f.videos["v0"] = {"slug": "moon-cow", "n": 1, "current": False}
        yield f


@pytest.fixture
def owner(fake, monkeypatch):
    monkeypatch.setenv(link.STAFF_ENV, STAFF_KEY)
    return fake


@pytest.fixture
def person(monkeypatch):
    answers: list[str] = []

    def typed(prompt: str) -> str:
        if not answers:
            raise EOFError
        return answers.pop(0)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setattr(keyboard, "why_not", lambda: None)
    monkeypatch.setattr(keyboard, "_ask_windows", typed)
    monkeypatch.setattr(keyboard, "_ask_posix", typed)
    return SimpleNamespace(answers=answers)


def run(capsys, *argv) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def posts(fake, part: str) -> list[str]:
    return [p for m, p in fake.calls if m == "POST" and part in p]


def submitted(fake, world, capsys, note="первая серия"):
    """The episode made ready (studio version marked) and submitted: the submission's id."""
    assert run(capsys, "--world", str(world), "studio-version", "1", "v1")[0] == 0
    code, out = run(capsys, "--world", str(world), "submit", "1", note)
    assert code == 0, out
    return next(iter(fake.subs))


# ------------------------------------------------------------------------------------------------ the editor

def test_submit_is_refused_with_the_list_when_not_ready(fake, world, capsys):
    fake.episodes[("moon-cow", 1)]["missing"] = [dict(x) for x in NOT_READY]
    code, out = run(capsys, "--world", str(world), "submit", "1", "посмотрите")
    assert code == 1 and "not ready to submit" in out
    for m in NOT_READY:
        assert m["message"] in out and f"[{m['code']}]" in out
    assert not posts(fake, "/api/studio/submissions") and not fake.subs


def test_studio_version_marks_unmarks_and_refuses(fake, world, capsys):
    code, out = run(capsys, "--world", str(world), "studio-version", "1", "v1")
    assert code == 0 and "studio version v1" in out and "from the current revision" in out and "watch: https://" in out
    assert fake.marked[("moon-cow", 1)] == "v1" and not fake.episodes[("moon-cow", 1)]["missing"]
    code, out = run(capsys, "--world", str(world), "studio-version", "1", "v0")
    assert code == 1 and "made before the episode's film last changed" in out
    code, out = run(capsys, "--world", str(world), "studio-version", "1", "nope")
    assert code == 1 and "no video nope" in out
    code, out = run(capsys, "--world", str(world), "studio-version", "1", "none")
    assert code == 0 and "no studio version marked" in out and ("moon-cow", 1) not in fake.marked


def test_submit_is_accepted_when_ready(fake, world, capsys):
    sid = submitted(fake, world, capsys)
    s = fake.subs[sid]
    assert s["kind"] == "publish" and s["status"] == "pending" and s["note"] == "первая серия"
    assert s["snapshot"]["studioVersionId"] == "v1" and fake.episodes[("moon-cow", 1)]["status"] == "review"
    code, out = run(capsys, "--world", str(world), "submit", "1")
    assert code == 1 and "open submission already" in out and len(fake.subs) == 1


def test_a_published_episode_goes_as_a_revision(fake, world, capsys):
    fake.episodes[("moon-cow", 1)].update(status="published", missing=[])
    code, out = run(capsys, "--world", str(world), "submit", "1", "новая музыка")
    assert code == 0, out
    assert next(iter(fake.subs.values()))["kind"] == "revision"


def test_reply_withdraw_unpublish(fake, world, capsys):
    sid = submitted(fake, world, capsys)
    code, out = run(capsys, "--world", str(world), "reply", "Поправил камеру", "--shot", "sh2")
    assert code == 0 and f"submission {sid}: publish, pending" in out
    assert fake.subs[sid]["thread"][-1] == {"at": fake.subs[sid]["thread"][-1]["at"], "by": "u1", "side": "author",
                                            "text": "Поправил камеру", "shot": "sh2"}
    code, out = run(capsys, "--world", str(world), "withdraw")
    assert code == 0 and "withdrawn" in out and fake.subs[sid]["status"] == "withdrawn"
    assert fake.episodes[("moon-cow", 1)]["status"] == "script"
    code, out = run(capsys, "--world", str(world), "withdraw")
    assert code == 1 and "no open submission" in out
    code, out = run(capsys, "--world", str(world), "unpublish", "  ")
    assert code == 1 and "say why" in out
    code, out = run(capsys, "--world", str(world), "unpublish", "Больше не снимаем", "--episode", "1")
    assert code == 0 and "unpublish, pending" in out
    u = [x for x in fake.subs.values() if x["kind"] == "unpublish"][0]
    assert u["note"] == "Больше не снимаем" and u["_n"] == 1


def test_status_shows_the_thread_and_the_remarks_with_their_shots(owner, world, capsys):
    sid = submitted(owner, world, capsys)
    code, out = run(capsys, "review", "return", sid, "Почти готово", "--shot", "sh3", "камера слишком близко")
    assert code == 0, out
    code, out = run(capsys, "--world", str(world), "status")
    assert code == 0, out
    for want in (f"submission {sid} (publish moon-cow episode 1, changes): 2 remark(s) of the owner", "RETURNED",
                 "remark on sh3: камера слишком близко", "owner: Почти готово", "owner (shot sh3): камера слишком близко"):
        assert want in out, (want, out)
    # resubmitting reopens the same submission, the thread goes on
    code, out = run(capsys, "--world", str(world), "submit", "1", "Отодвинул камеру")
    assert code == 0, out
    assert list(owner.subs) == [sid] and owner.subs[sid]["status"] == "pending"
    assert owner.subs[sid]["thread"][-1]["text"] == "Отодвинул камеру"


# ------------------------------------------------------------------------------------------------ the owner

def test_review_needs_the_staff_key(fake, world, capsys):
    code, out = run(capsys, "review", "list")
    assert code == 1 and "staff key" in out and "tadam login --staff" in out


def test_a_studio_key_is_no_staff_key(fake, monkeypatch, capsys):
    monkeypatch.setenv(link.STAFF_ENV, KEY)
    code, out = run(capsys, "review", "list")
    assert code == 1 and "only on /api/studio" in out


def test_login_staff_stores_the_staff_key(fake, monkeypatch, capsys):
    monkeypatch.setenv(link.STAFF_ENV, STAFF_KEY)
    code, out = run(capsys, "login", "--staff")
    assert code == 0 and STAFF_KEY not in out
    run(capsys, "login")                                     # the studio key next to it: both kept
    monkeypatch.delenv(link.STAFF_ENV)
    assert link.staff().key == STAFF_KEY and link.current().key == KEY
    assert run(capsys, "review", "list")[0] == 0
    assert run(capsys, "logout", "--staff")[0] == 0 and link.staff() is None and link.current().key == KEY


def test_review_list_and_show(owner, world, capsys):
    sid = submitted(owner, world, capsys)
    code, out = run(capsys, "review", "list")
    assert code == 0 and sid in out and "publish pending" in out and "moon-cow «Корова и луна»" in out
    assert "episode 1 «Пропала луна»" in out and "note: первая серия" in out and EMAIL not in out
    code, out = run(capsys, "review", "show", sid)
    assert code == 0, out
    for want in ("STUDIO VIDEO (watch it first):", "https://media.example.com/v1.mp4", "from the current revision",
                 "WORLD moon-cow «Корова и луна» (draft, ru, comedy)", "bible idea: Сыщик и корова",
                 "bible rules: Без злобы", "tadam pull moon-cow", "EPISODE 1 «Пропала луна»",
                 "logline: Корова потеряла луну", "HEROES:", "cow «Корова» — упрямая; puppet passed; in this episode",
                 "SCRIPT (ru) by shots:", "sh1 (2.6 s) Корова спрашивает", "Корова: «Где моя луна?»  (hint: Удивлённо)",
                 "narration: «А луна была рядом.»", "SETS: barn «Хлев»", "media/theme.mp3 (audio, 4 KB): licensed (CC BY 4.0",
                 "generated (gpt-image-2.5-flare)", "CHECK of the last push: ok", "borderline_word",
                 "THREAD: no messages", f"tadam review approve {sid}"):
        assert want in out, (want, out)
    assert EMAIL not in out
    assert run(capsys, "review", "list", "--status", "approved")[1].strip() == "the queue is empty"


def test_approve_needs_the_typed_id(owner, world, person, capsys):
    sid = submitted(owner, world, capsys)
    person.answers += [sid[:-1]]                             # a wrong id: nothing is sent
    code, out = run(capsys, "review", "approve", sid)
    assert code == 2 and "not approved" in out and owner.subs[sid]["status"] == "pending"
    assert not posts(owner, "/approve")
    person.answers += [sid]
    code, out = run(capsys, "review", "approve", sid, "--note", "Отлично")
    assert code == 0 and f"submission {sid}: publish, approved" in out
    assert owner.subs[sid]["status"] == "approved" and owner.episodes[("moon-cow", 1)]["status"] == "published"


def test_approve_and_reject_refuse_without_a_keyboard(owner, world, capsys):
    sid = submitted(owner, world, capsys)
    for argv in (("review", "approve", sid), ("review", "reject", sid, "нет")):
        code, out = run(capsys, *argv)
        assert code == 2 and "real keyboard" in out
    assert owner.subs[sid]["status"] == "pending" and not posts(owner, "/approve") and not posts(owner, "/reject")


def test_approve_a_stale_studio_version(owner, world, person, capsys):
    sid = submitted(owner, world, capsys)
    owner.stale_version.add(sid)
    person.answers += [sid]
    code, out = run(capsys, "review", "approve", sid)
    assert code == 1 and "--stale-version" in out and owner.subs[sid]["status"] == "pending"
    person.answers += [sid]
    code, out = run(capsys, "review", "approve", sid, "--stale-version")
    assert code == 0 and owner.subs[sid]["status"] == "approved"


def test_return_with_shot_remarks_needs_no_confirmation(owner, world, capsys):
    sid = submitted(owner, world, capsys)
    code, out = run(capsys, "review", "return", sid, "Две правки", "--shot", "sh3", "камера близко",
                    "--shot", "sh1", "громче")
    assert code == 0 and "changes" in out
    t = owner.subs[sid]["thread"]
    assert [(m["side"], m.get("shot"), m["text"]) for m in t] == [
        ("staff", None, "Две правки"), ("staff", "sh3", "камера близко"), ("staff", "sh1", "громче")]
    code, out = run(capsys, "review", "return", sid, "ещё")              # only a pending one is returned
    assert code == 1 and "not pending" in out
    code, out = run(capsys, "review", "reply", sid, "жду", "--shot", "sh1")
    assert code == 0 and owner.subs[sid]["thread"][-1]["shot"] == "sh1"


def test_reject_needs_the_typed_id(owner, world, person, capsys):
    sid = submitted(owner, world, capsys)
    person.answers += ["yes"]
    code, out = run(capsys, "review", "reject", sid, "Чужая музыка")
    assert code == 2 and "not rejected" in out and owner.subs[sid]["status"] == "pending"
    person.answers += [sid]
    code, out = run(capsys, "review", "reject", sid, "Чужая музыка")
    assert code == 0 and "rejected" in out and owner.subs[sid]["status"] == "rejected"
    assert owner.subs[sid]["thread"][-1]["text"] == "Чужая музыка"
