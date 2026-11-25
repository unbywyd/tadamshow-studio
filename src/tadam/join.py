"""BECOMING AN EDITOR from the terminal (studio-tz 3.5а; the server's http/STUDIO-API.md «Join and the rules»):

    tadam join   email -> the server sends a code -> the person types the code -> the studio's rules IN FULL ->
                 the person TYPES «согласен» / «I agree» -> a studio key, once, stored like `tadam login` stores it
    tadam login  the same for another computer (the rules are accepted already: the key comes at once); a new
                 version of the rules is shown and accepted the same way first

Everything the person answers comes from their own keyboard (tadam.keyboard): no pipes, no arguments for the
code or the agreement, nothing Claude can type. The kit checks the typed words like the server does
(«согласен», «согласна», «I agree», any case, quotes around ignored) and sends exactly what was typed; anything
else stops and nothing is accepted. The key is never printed; only a masked email is.
"""
from __future__ import annotations

import platform
import re
from dataclasses import dataclass
from typing import Callable

from tadam import __version__, link
from tadam.api import Api, ApiError

AGREE = {"согласен", "согласна", "i agree"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE = re.compile(r"^\d{6}$")
CODE_TRIES = 3

Ask = Callable[[str, str], str]          # ask(prompt, what) -> the typed line (tadam.keyboard.ask)
Out = Callable[[str], None]


class Stop(Exception):
    """The flow ends here; the message says why and what to do (exit code 1, or 2 for the person's own no)."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def agrees(typed: str) -> bool:
    """The server's typedAgrees: «согласен» / «согласна» / «I agree», any case, spaces and quotes around ignored."""
    t = re.sub(r"^[\"'«»“”„]+|[\"'«»“”„.!]+$", "", typed.strip()).strip()
    return re.sub(r"\s+", " ", t).lower() in AGREE


def client() -> str:
    return f"tadam {__version__} ({platform.system() or 'unknown'})"


def banned(e: ApiError) -> Stop | None:
    if e.reason != "banned":
        return None
    why = e.issues.get("why")
    return Stop("this account is banned from TadamShow" + (f": {why}" if why else "") +
                "\nIf you think this is a mistake, reply to the ban email.")


def show_rules(r: dict, out: Out, terms: bool = False) -> None:
    """The House Rules in full, where the full Editor Terms are, and what to type."""
    bar = "=" * 72
    out(bar)
    out(f"{r['rules'].get('title') or 'TadamShow Studio: House Rules'}  (version {r.get('version')})")
    out(bar)
    out(r["rules"].get("text", "").rstrip())
    out(bar)
    t = r.get("terms") or {}
    if terms:
        out(f"{t.get('title') or 'Editor Terms'}")
        out(bar)
        out((t.get("text") or "").rstrip())
        out(bar)
    else:
        out(f"These rules are part of the full {t.get('title') or 'Editor Terms'} ({len((t.get('text') or '').split())} "
            f"words): read them with `tadam rules --terms` (or this command with --terms); a copy of both comes in "
            f"the confirmation email.")


def accept(api: Api, r: dict, ask: Ask, out: Out, token: str | None, lang: str) -> dict:
    """Ask for the agreement and send it. With `token` (join): the answer carries the key, once."""
    word = r.get("confirm") or ("I agree" if lang == "en" else "согласен")
    out(f"To accept these rules, type «{word}» yourself and press Enter (anything else stops, nothing is accepted).")
    try:
        typed = ask(f"type «{word}»: ", "the agreement to the studio's rules")
    except (EOFError, KeyboardInterrupt):
        raise Stop("stopped: the rules are not accepted", 2) from None
    if not agrees(typed):
        raise Stop(f"not accepted («{typed[:40]}» is not «{word}»): nothing was sent. Run the command again when you "
                   f"want to accept the rules.", 2)
    body = {"version": r["version"], "typed": typed, "lang": lang, "client": client()}
    if token:
        body["token"] = token
        body["keyName"] = f"tadam ({platform.system() or 'computer'})"
    try:
        return api.post("/api/studio/rules/accept", body)
    except ApiError as e:
        b = banned(e)
        if b:
            raise b from None
        if e.reason == "rules_changed":
            raise Stop("the rules changed while you were reading them: run the command again to read the new "
                       "version") from None
        if e.reason == "access_off":
            raise Stop("studio access is switched off for this account: write to the owner of TadamShow") from None
        raise


def get_rules(api: Api, lang: str) -> dict:
    try:
        return api.get(f"/api/studio/rules?lang={'en' if lang == 'en' else 'ru'}")
    except ApiError as e:
        if e.reason == "no_rules" or e.status == 404:
            raise Stop("the studio has no rules published yet: nothing to accept; ask the owner") from None
        raise


@dataclass
class Joined:
    email: str            # masked
    stored: str | None    # where the key is (None: no key came)
    access: bool
    version: str | None   # the rules version accepted now (None: accepted before)


def email_flow(url: str, ask: Ask, out: Out, email: str | None = None, lang: str = "ru", terms: bool = False,
               opener=None, mode: str = "join") -> Joined:
    """join / login by email. `ask` reads the person's keyboard; `opener` is for tests."""
    api = Api(link.Link(url, ""), opener=opener)
    if not email:
        try:
            email = ask("your email: ", "your email")
        except (EOFError, KeyboardInterrupt):
            raise Stop("stopped", 2) from None
    email = email.strip()
    if not EMAIL.match(email):
        raise Stop(f"«{email}» is not an email address", 2)
    try:
        started = api.post("/api/studio/join/start", {"email": email})
    except ApiError as e:
        raise (banned(e) or Stop(f"no code was sent: {e}")) from None
    mins = max(1, int(started.get("expiresInSec") or 600) // 60)
    out(f"a code went to {link.mask_email(email)} (valid {mins} min; look in spam too)")
    verified = None
    for attempt in range(CODE_TRIES):
        try:
            code = ask("the 6-digit code from the email: ", "the code from your email").replace(" ", "")
        except (EOFError, KeyboardInterrupt):
            raise Stop("stopped", 2) from None
        if not CODE.match(code):
            out("the code is 6 digits")
            continue
        try:
            verified = api.post("/api/studio/join/verify", {"email": email, "code": code})
            break
        except ApiError as e:
            b = banned(e)
            if b:
                raise b from None
            if e.status == 400 and "attempts left" in e.message and attempt + 1 < CODE_TRIES:
                out(f"{e.message}: try again")
                continue
            raise Stop(f"the code was not accepted: {e}. Run `tadam {mode}` again for a new code.") from None
    if verified is None:
        raise Stop(f"no valid code: run `tadam {mode}` again for a new one")
    token, nxt = verified["token"], verified.get("next")
    acc = verified.get("account") or {}
    masked = link.mask_email(acc.get("email") or email)
    if nxt == "off":
        raise Stop(f"studio access of {masked} is switched off by the owner of TadamShow: write to them")
    version = None
    if nxt == "accept":
        rs = verified.get("rules") or {}
        if rs.get("accepted"):
            out(f"the studio's rules have a new version ({rs.get('current')}; you accepted {rs.get('accepted')}): "
                "read it and accept it to go on")
        r = get_rules(api, lang)
        show_rules(r, out, terms)
        res = accept(api, r, ask, out, token, lang)
        version = res.get("version")
        kc = res.get("key")
        if not kc:
            return Joined(masked, None, bool(res.get("access")), version)
    else:
        try:
            kc = api.post("/api/studio/join/key", {"token": token, "name": f"tadam ({platform.system() or 'computer'})"})
        except ApiError as e:
            raise (banned(e) or Stop(f"no key: {e}")) from None
    secret = (kc or {}).get("secret")
    if not isinstance(secret, str) or not link.looks_like_key(secret):
        raise Stop("the server did not send a studio key: make one in the cabinet (studio.tadamshow.com), then "
                   "`tadam login --key`")
    path = link.store(url, secret, {"id": acc.get("id")})
    return Joined(masked, str(path), True, version)


def accept_new_rules(api: Api, ask: Ask, out: Out, me: dict, lang: str = "ru", terms: bool = False) -> str:
    """A signed-in person (studio key) whose rules are outdated: show the new version, take the typed agreement.
    Returns the version accepted."""
    rs = me.get("rules") or {}
    out(f"the studio's rules have a new version ({rs.get('current')}; you accepted {rs.get('accepted') or 'none'}): "
        "pushing and voicing wait until you accept it")
    r = get_rules(api, lang)
    show_rules(r, out, terms)
    return str(accept(api, r, ask, out, None, lang).get("version"))
