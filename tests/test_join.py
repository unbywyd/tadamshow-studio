"""tadam join / login by email, the rules and the typed agreement, a new version of the rules, a ban — against the
local fake server (tests/fake_studio.py: every answer checked against schema/). The person at the keyboard is
played by `person`: what it types is read where a real terminal is read (tadam.keyboard), never from stdin."""
from __future__ import annotations

import io
import sys
from types import SimpleNamespace

import pytest

from fake_studio import EMAIL, KEY, NEW_KEY, Server
from tadam import cli, join, keyboard, link


@pytest.fixture
def fake(monkeypatch):
    with Server() as f:
        monkeypatch.setenv(link.URL_ENV, f.base)
        yield f


@pytest.fixture
def newcomer(fake):
    """Someone who never accepted the rules and has no studio access yet."""
    fake.accepted, fake.access, fake.keys = None, False, set()
    return fake


@pytest.fixture
def person(monkeypatch):
    """A person at a real keyboard who types `answers`, one per question."""
    answers: list[str] = []
    prompts: list[str] = []

    def typed(prompt: str) -> str:
        prompts.append(prompt)
        if not answers:
            raise EOFError
        return answers.pop(0)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setattr(keyboard, "why_not", lambda: None)
    monkeypatch.setattr(keyboard, "_ask_windows", typed)
    monkeypatch.setattr(keyboard, "_ask_posix", typed)
    return SimpleNamespace(answers=answers, prompts=prompts)


def run(capsys, *argv) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def stored() -> str:
    f = link.config_dir() / link.FILE
    return f.read_text(encoding="utf-8") if f.exists() else ""


@pytest.mark.parametrize("lang,word", [("ru", "согласен"), ("ru", "Согласна"), ("en", "I agree"), ("ru", "«согласен»")])
def test_join_happy_path(newcomer, person, capsys, lang, word):
    person.answers += [EMAIL, "123456", word]
    code, out = run(capsys, "join", "--lang", lang)
    assert code == 0, out
    rules = "Нарушение = бан." if lang == "ru" else "Breaking them = a ban."
    assert rules in out and ("Правила студии" in out or "House Rules" in out)       # the rules, in full
    assert "tadam rules --terms" in out                                                # where the full terms are
    assert "«согласен»" in out if lang == "ru" else "«I agree»" in out
    assert link.mask_email(EMAIL) in out and EMAIL not in out
    assert NEW_KEY not in out and "N3wS3cr3t" not in out                              # the key is never shown
    lk = link.current()
    assert lk is not None and lk.key == NEW_KEY and NEW_KEY in stored()               # stored like tadam login
    assert newcomer.access and newcomer.accepted == "1"
    (acc,) = newcomer.accepts
    assert acc["typed"] == word and acc["version"] == "1" and acc["token"].startswith("tdj_")
    assert acc["client"].startswith("tadam ") and acc["lang"] == lang
    assert person.prompts[0].startswith("your email") and "code" in person.prompts[1]


def test_join_takes_the_email_as_an_argument(newcomer, person, capsys):
    person.answers += ["123456", "согласен"]
    code, out = run(capsys, "join", EMAIL)
    assert code == 0, out
    assert newcomer.mails == [EMAIL]


def test_wrong_code_is_asked_again_then_given_up(newcomer, person, capsys):
    person.answers += [EMAIL, "000000", "12 34 56", "согласен"]
    code, out = run(capsys, "join")
    assert code == 0, out
    assert "wrong code, 4 attempts left" in out
    # three wrong codes: nothing accepted, nothing stored
    link.forget(link.server_url())
    newcomer.accepted, newcomer.accepts = None, []
    person.answers[:] = [EMAIL, "111111", "222222", "333333"]
    code, out = run(capsys, "join")
    assert code == 1 and "tadam join` again" in out
    assert not newcomer.accepts and not stored()
    person.answers[:] = [EMAIL, "abc", "1", "12345"]                  # never 6 digits: never sent
    code, out = run(capsys, "join")
    assert code == 1 and "the code is 6 digits" in out


def test_the_agreement_is_refused_without_a_terminal(newcomer, monkeypatch, capsys):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(EMAIL + "\n123456\nсогласен\n"))      # piped in: not a person
    code, out = run(capsys, "join", EMAIL)
    assert code == 2 and "real keyboard" in out and "Nothing can be piped" in out
    assert not newcomer.mails and not newcomer.accepts and not stored()


def test_the_agreement_is_refused_inside_claude_code(newcomer, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    assert "Claude Code" in (keyboard.why_not() or "")
    code, out = run(capsys, "join", EMAIL)
    assert code == 2 and "Claude Code session" in out and not newcomer.mails


def test_keyboard_refuses_pipes():
    # (pytest's own stdin is not a terminal)
    assert keyboard.why_not() is not None
    with pytest.raises(keyboard.NoKeyboard):
        keyboard.ask("type: ", "the agreement")


@pytest.mark.parametrize("word", ["да", "ok", "yes", "", "согласен?", "not agree"])
def test_a_wrong_word_accepts_nothing(newcomer, person, capsys, word):
    person.answers += [EMAIL, "123456", word]
    code, out = run(capsys, "join")
    assert code == 2 and "not accepted" in out and "nothing was sent" in out
    assert not newcomer.accepts and not newcomer.access and not stored()


def test_agrees_is_the_servers_rule():
    for ok in ("согласен", " СОГЛАСНА ", "«согласен»", '"I agree".', "i  agree"):
        assert join.agrees(ok), ok
    for no in ("согласен!!1", "agree", "я согласен", "соглашаюсь", "y"):
        assert not join.agrees(no), no


def test_login_by_email_when_the_rules_are_accepted(fake, person, capsys):
    person.answers += [EMAIL, "123456"]
    code, out = run(capsys, "login")
    assert code == 0, out
    assert "signed in as " + link.mask_email(EMAIL) in out
    assert "Нарушение" not in out and not fake.accepts                 # no rules asked: accepted already
    assert link.current().key == NEW_KEY


def test_rules_outdated_at_login_by_email(fake, person, capsys):
    fake.rules_version = "2"                                            # accepted "1"
    person.answers += [EMAIL, "123456", "согласен"]
    code, out = run(capsys, "login")
    assert code == 0, out
    assert "new version (2; you accepted 1)" in out and "Нарушение = бан." in out
    assert fake.accepted == "2" and fake.accepts[-1]["token"]
    assert link.current().key == NEW_KEY


def test_rules_outdated_at_login_with_a_key(fake, person, monkeypatch, capsys):
    fake.rules_version = "2"
    fake.staff = False
    monkeypatch.setenv(link.KEY_ENV, KEY)
    person.answers += ["I agree"]
    code, out = run(capsys, "login", "--key")
    assert code == 0, out
    assert "new version (2; you accepted 1)" in out and "Нарушение = бан." in out
    assert "accepted the studio's rules, version 2" in out
    assert fake.accepted == "2" and "token" not in fake.accepts[-1]     # recorded with the key, no new key


def test_rules_outdated_without_a_terminal_only_says_so(fake, monkeypatch, capsys):
    fake.rules_version = "2"
    fake.staff = False
    monkeypatch.setenv(link.KEY_ENV, KEY)
    code, out = run(capsys, "login")
    assert code == 0 and "tadam login --key` yourself in a terminal" in out
    assert fake.accepted == "1" and not fake.accepts


def test_the_owner_side_is_not_asked_for_new_rules_at_login(fake, person, monkeypatch, capsys):
    # staff admin+ are not asked by the server (rules.ts needRules): login must not tell them pushing waits
    fake.rules_version = "2"
    monkeypatch.setenv(link.KEY_ENV, KEY)
    code, out = run(capsys, "login", "--key")
    assert code == 0, out
    assert "not asked to accept" in out and "pushing and voicing wait" not in out
    assert not person.prompts and fake.accepted == "1" and not fake.accepts


def test_push_says_the_rules_changed(fake, monkeypatch, capsys, world):
    fake.rules_version = "2"
    monkeypatch.setenv(link.KEY_ENV, KEY)
    code, out = run(capsys, "--world", str(world), "push")
    assert code == 1 and "rules changed" in out


def test_a_banned_person_sees_the_reason(fake, person, monkeypatch, capsys):
    fake.banned = "spam and other people's music"
    person.answers += [EMAIL]
    code, out = run(capsys, "join")
    assert code == 1 and "banned from TadamShow: spam and other people's music" in out
    assert not fake.mails and not stored()
    monkeypatch.setenv(link.KEY_ENV, KEY)                     # the revoked key answers 403 banned with the reason
    code, out = run(capsys, "status")
    assert code == 1 and "banned from TadamShow: spam and other people's music" in out
    code, out = run(capsys, "login")
    assert code == 1 and "banned" in out and "spam" in out


def test_access_switched_off(fake, person, capsys):
    fake.access = False
    person.answers += [EMAIL, "123456"]
    code, out = run(capsys, "login")
    assert code == 1 and "switched off" in out and not stored()


def test_rules_can_be_read_without_signing_in(fake, capsys):
    code, out = run(capsys, "rules", "--lang", "en", "--terms")
    assert code == 0 and "Breaking them = a ban." in out and "The full terms" in out and "tadam join" in out
