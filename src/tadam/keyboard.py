"""THE PERSON'S OWN KEYBOARD: what only a person may type — the agreement to the studio's rules («согласен» /
"I agree"), the code from their email, the id of a submission the owner approves or rejects.

Like `skey fill`, these answers are never taken from a pipe, a file, an argument or the environment:
  - the command refuses when stdin or stdout is not a terminal (Claude's shell, a script, `echo согласен | tadam`);
  - it refuses inside a Claude Code session (CLAUDECODE is set there): the person runs it in their own terminal;
  - the answer is read from the terminal device itself (POSIX /dev/tty, Windows the console through msvcrt), not
    from sys.stdin, so text piped into the command cannot stand in for it.
The skill forbids Claude to type any of it; this makes the honest path the only easy one. (A program that fakes a
whole terminal could still type into it; that is a deliberate act against the rules the person accepted.)
"""
from __future__ import annotations

import os
import sys


class NoKeyboard(Exception):
    """There is no person at a real keyboard here."""


def why_not() -> str | None:
    """None when a person can type here, else why not."""
    if (os.environ.get("CLAUDECODE") or "").strip():
        return "this runs inside a Claude Code session"
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return "this is not a terminal (the input or the output goes through a pipe)"
    except (AttributeError, ValueError, OSError):
        return "this is not a terminal"
    return None


def real() -> bool:
    return why_not() is None


def require(what: str) -> None:
    """Raise NoKeyboard with plain words when nobody can type `what` here."""
    why = why_not()
    if why:
        raise NoKeyboard(f"{what} is typed by the person at a real keyboard, and {why}. Open your own terminal "
                         f"window and run the command there yourself. Nothing can be piped or passed in for it.")


def _ask_posix(prompt: str) -> str:
    with open("/dev/tty", "r+", encoding="utf-8", errors="replace") as tty:
        tty.write(prompt)
        tty.flush()
        line = tty.readline()
    if not line:
        raise EOFError
    return line.rstrip("\r\n")


def _ask_windows(prompt: str) -> str:
    import msvcrt
    sys.stdout.write(prompt)
    sys.stdout.flush()
    chars: list[str] = []
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            msvcrt.putwch("\r")
            msvcrt.putwch("\n")
            return "".join(chars)
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch == "\x1a":
            raise EOFError
        if ch in ("\x00", "\xe0"):          # an arrow or a function key: two codes, both ignored
            msvcrt.getwch()
            continue
        if ch == "\x08":
            if chars:
                chars.pop()
                for c in "\x08 \x08":
                    msvcrt.putwch(c)
            continue
        if ch < " ":
            continue
        chars.append(ch)
        msvcrt.putwch(ch)


def ask(prompt: str, what: str = "the answer") -> str:
    """One line typed by the person (shown as typed). Raises NoKeyboard without a real keyboard, EOFError /
    KeyboardInterrupt when they stop."""
    require(what)
    return (_ask_windows if os.name == "nt" else _ask_posix)(prompt).strip()
