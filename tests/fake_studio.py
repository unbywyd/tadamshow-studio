"""A local stand-in for the studio server (/api/studio/*), as the contract says it behaves (the server's
services/studio/push.ts and pull.ts, packages/contracts studio.ts; the kit's schema/*.json):

  POST worlds/:slug/push/begin   {baseRev, manifest} -> the files it lacks (by fingerprint), one upload link each;
                                 baseRev must be the latest revision (older: 409 stale_base; none yet: 409 bad_base)
  PUT  <upload link>             the bytes (no key: a storage link)
  POST worlds/:slug/push/commit  {pushId, confirm?} -> every asked-for file must be there and match its fingerprint;
                                 a world marked `breaking` answers 409 breaking_change unless confirm (staff)
  GET  worlds/:slug/pull         the latest revision: manifest + a download link per file
  GET  status, GET me
  POST join/start | join/verify | join/key, GET rules, POST rules/accept   (no sign-in: join.ts, rules.ts)
  GET|POST submissions, GET submissions/:id, POST submissions/:id/withdraw | reply,
  POST worlds/:slug/episodes/:n/studio-version                              (submissions.ts)
  /api/admin/studio/submissions[/:id[/approve|return|reject|reply]]        (the owner, a staff key)

Every JSON answer is checked against the kit's schema/<answer>.json, so the fake cannot drift from the contract.
Nothing leaves 127.0.0.1.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tadam import schema
from tadam.folder import why_not

KEY = "tds_abcd1234_" + "S3cretS3cretS3cretS3cret"
NEW_KEY = "tds_newk5678_" + "N3wS3cr3tN3wS3cr3tN3wS3cr3t"      # (the key join hands out: built, not real)
STAFF_KEY = "tdm_owner123_" + "St4ffSt4ffSt4ffSt4ffSt4ff"      # (the owner's staff key for /api/admin)
EMAIL = "editor" + "@example.com"        # (a reserved example domain; built here so no address sits in the source)
MIME = {"png": "image/png", "webp": "image/webp", "jpg": "image/jpeg", "jpeg": "image/jpeg", "mp3": "audio/mpeg",
        "wav": "audio/wav", "ogg": "audio/ogg", "json": "application/json"}
WHEN = "2026-11-25T12:00:00.000Z"


class Fake:
    def __init__(self):
        self.worlds: dict[str, dict] = {}         # slug -> {id, status, revs: [{rev, manifest}]}
        self.blobs: dict[str, bytes] = {}         # "<worldId>/<sha>" -> bytes (committed)
        self.pending: dict[str, bytes] = {}       # uploaded, not committed yet
        self.sessions: dict[str, dict] = {}
        self.puts: list[str] = []                 # paths uploaded, in order
        self.leaks: list[str] = []                # a request to a storage link that carried the key
        self.breaking: set[str] = set()
        self.staff = True
        self.calls: list[tuple[str, str]] = []
        self.status_doc: dict | None = None
        self.base = ""
        self.lock = threading.Lock()
        # --- the person, the rules and join (services/studio/join.ts, rules.ts)
        self.keys: set[str] = {KEY}               # studio keys that work
        self.staff_keys: set[str] = {STAFF_KEY}   # staff keys (tdm_) of an admin
        self.rules_version = "1"
        self.accepted: str | None = "1"           # the version the person accepted (None: never)
        self.access = True
        self.banned: str | None = None            # the ban's reason: join and the key answer 403 banned
        self.codes: dict[str, str] = {}           # email -> the code "sent" to it
        self.code_tries: dict[str, int] = {}
        self.tokens: dict[str, dict] = {}         # join token -> {email, used}
        self.mails: list[str] = []                # emails a code went to
        self.accepts: list[dict] = []             # every rules/accept body that was recorded
        self.new_key = NEW_KEY
        # --- episodes, submissions, studio versions (services/studio/submissions.ts)
        self.episodes: dict[tuple[str, int], dict] = {}   # (slug, n) -> {status, missing: [...], title}
        self.subs: dict[str, dict] = {}           # id -> Submission
        self.videos: dict[str, dict] = {}         # versionId -> {slug, n, current}
        self.marked: dict[tuple[str, int], str] = {}
        self.stale_version: set[str] = set()      # submission ids whose studio version is older than the film
        self.seq = 0


def _err(code: str, message: str, status: int, **issues) -> tuple[int, dict]:
    return status, {"error": {"code": code, "message": message, **({"issues": issues} if issues else {})}}


def _check(name: str, doc: dict) -> dict:
    bad = schema.validate(name, doc)
    assert not bad, f"the fake's {name} answer breaks the contract: {bad[:3]}"
    return doc


def _req(name: str, body: object) -> tuple[int, dict] | None:
    """A request that does not fit the contract: 400 like the server's parse()."""
    bad = schema.validate(name, body)
    return _err("bad_request", f"invalid request: {bad[0][0]} {bad[0][1]}", 400) if bad else None


def _banned(fake: Fake):
    return _err("forbidden", f"this account is banned from TadamShow: {fake.banned}", 403, reason="banned",
                todo="if you think this is a mistake, reply to the ban email", why=fake.banned)


def _rules_state(fake: Fake) -> dict:
    return {"current": fake.rules_version, "accepted": fake.accepted, "acceptedAt": WHEN if fake.accepted else None,
            "outdated": bool(fake.accepted) and fake.accepted != fake.rules_version}


AGREE = {"согласен", "согласна", "i agree"}


def _agrees(typed: str) -> bool:
    t = re.sub(r"^[\"'«»“”„]+|[\"'«»“”„.!]+$", "", typed.strip()).strip()
    return re.sub(r"\s+", " ", t).lower() in AGREE


def _key_created(fake: Fake, name: str) -> dict:
    fake.keys.add(fake.new_key)
    return _check("studio-key-created.response", {
        "key": {"id": "k2", "name": name, "prefix": fake.new_key[:13], "lastUsedAt": None, "revokedAt": None,
                "createdAt": WHEN}, "secret": fake.new_key})


RULES = {
    "ru": {"rules": {"title": "Правила студии ТадамШоу", "text": "1. Только то, на что у вас есть права.\n"
                                                              "2. Чистый контент.\n3. Без спама.\nНарушение = бан."},
           "terms": {"title": "Условия для редакторов", "text": "Полные условия: права, публикация, бан. " * 20},
           "confirm": "согласен"},
    "en": {"rules": {"title": "TadamShow Studio House Rules", "text": "1. Only what you have the right to use.\n"
                                                                   "2. Clean content.\n3. No spam.\nBreaking them = a ban."},
           "terms": {"title": "Editor Terms", "text": "The full terms: rights, publication, bans. " * 20},
           "confirm": "I agree"},
}


def join_routes(fake: Fake, method: str, path: str, body: dict, auth: str | None):
    """The routes without sign-in (join/start, join/verify, join/key, rules, rules/accept)."""
    if method == "GET" and path.startswith("/api/studio/rules"):
        lang = "en" if path.endswith("lang=en") else "ru"
        r = RULES[lang]
        return 200, _check("rules.response", {"version": fake.rules_version, "lang": lang, "rules": r["rules"],
                                              "terms": r["terms"], "effectiveAt": WHEN, "confirm": r["confirm"]})
    if method != "POST":
        return None
    if path == "/api/studio/join/start":
        bad = _req("join-start.request", body)
        if bad:
            return bad
        if fake.banned:
            return _banned(fake)
        fake.codes[body["email"].lower()] = "123456"
        fake.code_tries[body["email"].lower()] = 5
        fake.mails.append(body["email"].lower())
        return 200, {"ok": True, "expiresInSec": 600}
    if path == "/api/studio/join/verify":
        bad = _req("join-verify.request", body)
        if bad:
            return bad
        email = body["email"].lower()
        if fake.banned:
            return _banned(fake)
        if email not in fake.codes:
            return _err("bad_request", "no valid code for this email: request a new one", 400)
        if body["code"] != fake.codes[email]:
            fake.code_tries[email] -= 1
            left = fake.code_tries[email]
            return _err("bad_request", f"wrong code, {left} attempts left" if left > 0 else "wrong code: request a new one", 400)
        del fake.codes[email]
        token = "tdj_" + uuid.uuid4().hex
        fake.tokens[token] = {"email": email, "used": False}
        st = _rules_state(fake)
        nxt = "off" if fake.accepted and not fake.access else "accept" if not fake.accepted or st["outdated"] else "key"
        return 200, _check("join-verify.response", {
            "token": token, "expiresAt": WHEN, "account": {"id": "u1", "email": email, "existed": True, "access": fake.access},
            "rules": st, "next": nxt})
    if path == "/api/studio/join/key":
        bad = _req("join-key.request", body)
        if bad:
            return bad
        t = fake.tokens.get(body["token"])
        if not t:
            return _err("unauthorized", "the join token is not valid", 401, reason="bad_token", todo="run tadam join")
        if fake.banned:
            return _banned(fake)
        if not fake.accepted or fake.accepted != fake.rules_version:
            return _err("forbidden", "accept the studio rules first", 403,
                        reason="rules_outdated" if fake.accepted else "rules_not_accepted", todo="accept the rules")
        if t["used"]:
            return _err("conflict", "this join token has already given a key", 409, reason="token_used", todo="run tadam login again")
        t["used"] = True
        return 201, _key_created(fake, body.get("name") or "tadam")
    if path == "/api/studio/rules/accept":
        bad = _req("rules-accept.request", body)
        if bad:
            return bad
        if not _agrees(body["typed"]):
            return _err("bad_request", "to accept the rules, type «согласен» (or «I agree»)", 400, reason="not_agreed",
                        todo="read the rules and type «согласен» / «I agree» yourself; anything else stops")
        if body["version"] != fake.rules_version:
            return _err("conflict", f"the rules changed: the current version is {fake.rules_version}", 409,
                        reason="rules_changed", todo="GET the rules again", current=fake.rules_version)
        token = body.get("token")
        if token:
            t = fake.tokens.get(token)
            if not t:
                return _err("unauthorized", "the join token is not valid", 401, reason="bad_token", todo="run tadam join again")
        elif not (auth and auth in fake.keys):
            return _err("unauthorized", "send the join token, a studio key or the site session", 401, reason="signed_out",
                        todo="run tadam join")
        if fake.banned:
            return _banned(fake)
        if token and fake.tokens[token]["used"]:
            return _err("conflict", "this join token has already given a key", 409, reason="token_used", todo="run tadam login")
        first = not fake.accepted
        fake.accepted = fake.rules_version
        if first:
            fake.access = True
        fake.accepts.append(dict(body))
        key = None
        if token and fake.access:
            fake.tokens[token]["used"] = True
            key = _key_created(fake, body.get("keyName") or "tadam")
        return 200, _check("rules-accept.response", {"version": fake.rules_version, "acceptedAt": WHEN,
                                                     "access": fake.access, "key": key})
    return None


# ------------------------------------------------------------------------------------------------ submissions

def _status(fake: Fake) -> dict:
    if fake.status_doc:
        return fake.status_doc
    slugs = sorted(set(fake.worlds) | {s for s, _ in fake.episodes})
    worlds = []
    for slug in slugs:
        w = fake.worlds.get(slug) or {"id": "w-" + slug, "status": "draft", "revs": []}
        eps = []
        for (s, n), e in sorted(fake.episodes.items()):
            if s != slug:
                continue
            open_ = _open(fake, slug, n)
            eps.append({"number": n, "title": {"ru": e.get("title", f"Серия {n}")}, "status": e["status"],
                        "draft": False, "submission": {"id": open_["id"], "kind": open_["kind"], "status": open_["status"]}
                        if open_ else None, "missing": list(e.get("missing") or [])})
        rev = w["revs"][-1]["rev"] if w["revs"] else None
        worlds.append({"id": w["id"], "slug": slug, "title": {"ru": "Корова и луна"}, "status": w["status"], "rev": rev,
                       "lastPush": {"rev": rev, "at": WHEN, "by": "u1", "ok": True} if rev else None, "episodes": eps})
    subs = [{"id": x["id"], "kind": x["kind"], "status": x["status"], "world": x["_slug"], "episode": x["_n"],
             "createdAt": x["createdAt"]} for x in fake.subs.values() if x["status"] in ("pending", "changes")]
    return {"worlds": worlds, "submissions": subs, "unread": 0, "notifications": []}


def _open(fake: Fake, slug: str, n: int | None, kind: str | None = None, statuses=("pending", "changes")) -> dict | None:
    for x in fake.subs.values():
        if x["_slug"] == slug and x["_n"] == n and x["status"] in statuses and (kind is None or x["kind"] == kind):
            return x
    return None


def _public(sub: dict) -> dict:
    return {k: v for k, v in sub.items() if not k.startswith("_")}


def _decided(sub: dict) -> dict:
    return _check("submission-decided.response", {"submission": _public(sub)})


def _brief(fake: Fake, x: dict) -> dict:
    n = x["_n"]
    e = fake.episodes.get((x["_slug"], n)) if n is not None else None
    return _check("submission-brief", {
        "id": x["id"], "kind": x["kind"], "status": x["status"],
        "world": {"id": "w-" + x["_slug"], "slug": x["_slug"], "title": {"ru": "Корова и луна"}, "status": "draft"},
        "episode": {"id": f"e{n}", "number": n, "title": {"ru": e.get("title", f"Серия {n}")}, "status": e["status"]}
        if e else None,
        "author": {"id": "u1", "email": EMAIL, "name": "Editor"}, "note": x["note"], "messages": len(x["thread"]),
        "createdAt": x["createdAt"], "updatedAt": x["updatedAt"], "decidedAt": x["decidedAt"]})


def _review(fake: Fake, x: dict, lang: str = "ru") -> dict:
    slug, n = x["_slug"], x["_n"]
    e = fake.episodes.get((slug, n)) if n is not None else None
    vid = fake.marked.get((slug, n)) if n is not None else None
    v = fake.videos.get(vid) if vid else None
    cards = {"heroes": {"cow": {"key": "cow", "characterId": "c1", "name": "Корова", "portraitUrl": None},
                        "det": {"key": "det", "characterId": "c2", "name": "Сыщик", "portraitUrl": None}},
             "items": [{"shot": "sh1", "kind": "line", "remark": "Корова спрашивает", "hero": "cow", "heroes": ["cow", "det"],
                        "text": "Где моя луна?", "hint": "Удивлённо", "title": None, "sub": None, "seconds": 2.6},
                       {"shot": "sh2", "kind": "line", "remark": "Сыщик отвечает", "hero": "det", "heroes": ["det"],
                        "text": "Сейчас найдём.", "hint": "Спокойно", "title": None, "sub": None, "seconds": 2.2},
                       {"shot": "sh3", "kind": "narration", "remark": "Двор", "hero": None, "heroes": ["cow"],
                        "text": "А луна была рядом.", "hint": None, "title": None, "sub": None, "seconds": 2.0}]}
    return _check("submission-review.response", {
        "submission": _public(x),
        "author": {"id": "u1", "email": EMAIL, "name": "Editor", "status": "active", "rulesVersion": fake.accepted},
        "studioVersion": {"id": vid, "lang": "ru", "createdAt": WHEN, "videoUrl": f"https://media.example.com/{vid}.mp4",
                          "current": bool(v and v["current"]) and x["id"] not in fake.stale_version} if v else None,
        "world": {"id": "w-" + slug, "slug": slug, "status": "draft", "title": {"ru": "Корова и луна"},
                  "tagline": {"ru": "Корова ищет луну"}, "description": {"ru": "Короткие серии о корове и сыщике."},
                  "genre": "comedy", "langs": ["ru"], "bible": {"idea": {"ru": "Сыщик и корова"}, "rules": [{"ru": "Без злобы"}]},
                  "coverUrl": None, "ownerId": "u1", "pull": f"tadam pull {slug}"},
        "episode": {"id": f"e{n}", "number": n, "status": e["status"], "title": {"ru": e.get("title", f"Серия {n}")},
                    "logline": {"ru": "Корова потеряла луну"}, "teaser": None, "coverUrl": None, "scriptRev": 1} if e else None,
        "script": {"lang": lang, "cards": cards if e else None, "live": None},
        "heroes": [{"slug": "cow", "name": {"ru": "Корова"}, "trait": {"ru": "упрямая"}, "height": 0.42, "draft": False,
                    "inEpisode": True, "portraitUrl": "https://media.example.com/cow.png", "sheetUrl": None,
                    "puppet": {"key": "cow", "passed": True, "report": None}}],
        "sets": [{"slug": "barn", "title": "Хлев", "previewUrl": None, "files": {}}],
        "media": [{"path": "media/theme.mp3", "kind": "audio", "bytes": 4096, "url": None,
                   "source": {"source": "licensed", "licence": "CC BY 4.0", "url": "https://music.example.com/theme"}},
                  {"path": "heroes/cow/puppet/portrait.png", "kind": "image", "bytes": 2048, "url": None,
                   "source": {"source": "generated", "tool": "gpt-image-2.5-flare"}}],
        "check": {"ok": True, "issues": [{"level": "warning", "where": "episodes/1/script.json#shots[0].remark.ru",
                                          "code": "borderline_word", "message": "«дурак» may be an insult: the owner will look at it"}]},
        "missing": list(e.get("missing") or []) if e else [],
        "revision": None,
        "rev": {"submitted": x["snapshot"]["rev"], "latest": x["snapshot"]["rev"]},
        "thread": list(x["thread"])})


def _msg(side: str, text: str, shot: str | None = None) -> dict:
    return {"at": WHEN, "by": "u1" if side == "author" else "u0", "side": side, "text": text, **({"shot": shot} if shot else {})}


def editor_routes(fake: Fake, method: str, path: str, body: dict):
    """/api/studio/submissions*, the studio version (signed in with a studio key, studio access on)."""
    if method == "GET" and path == "/api/studio/submissions":
        return 200, {"submissions": [_brief(fake, x) for x in sorted(fake.subs.values(), key=lambda s: s["createdAt"],
                                                                      reverse=True)]}
    m = re.match(r"^/api/studio/submissions/([A-Za-z0-9_-]+)(?:\?lang=(ru|en))?$", path)
    if method == "GET" and m:
        x = fake.subs.get(m.group(1))
        return (200, _review(fake, x, m.group(2) or "ru")) if x else _err("not_found", "no such submission", 404)
    if method != "POST":
        return None
    if path == "/api/studio/submissions":
        bad = _req("submission-create.request", body)
        if bad:
            return bad
        kind, slug, n, note = body["kind"], body["world"], body.get("episode"), body.get("note")
        if kind == "publish" and n is None:
            return _err("bad_request", "name the episode to publish", 400, reason="no_episode", todo='tadam submit <episode> "<note>"')
        if kind == "unpublish" and not note:
            return _err("bad_request", "say why it should come off the site", 400, reason="no_reason", todo='tadam unpublish "<reason>"')
        e = fake.episodes.get((slug, n)) if n is not None else None
        if n is not None and not e:
            return _err("not_found", f"no episode {n} in {slug}", 404, reason="no_episode", todo="push the episode first")
        if _open(fake, slug, n, kind, ("pending",)):
            return _err("conflict", "a submission for this is open already", 409, reason="submission_open",
                        todo="wait for the owner, or tadam withdraw", id=_open(fake, slug, n, kind, ("pending",))["id"])
        if kind != "unpublish" and e and e.get("missing"):
            return _err("conflict", "not ready to submit: " + "; ".join(x["message"] for x in e["missing"]), 409,
                        reason="not_ready", todo="see missing (tadam status)", missing=e["missing"])
        back = _open(fake, slug, n, kind, ("changes",))
        if back:                                 # a returned one is reopened: same id, the thread goes on
            back.update(status="pending", updatedAt=WHEN, note=note or back["note"])
            if note:
                back["thread"].append(_msg("author", note))
            return 201, _decided(back)
        fake.seq += 1
        sid = f"sub{fake.seq}"
        sub = {"id": sid, "kind": kind, "worldId": "w-" + slug, "episodeId": f"e{n}" if n is not None else None,
               "authorId": "u1", "status": "pending", "note": note, "thread": [], "snapshot": {"rev": 1},
               "impact": None, "decidedBy": None, "decidedAt": None, "createdAt": WHEN, "updatedAt": WHEN,
               "_slug": slug, "_n": n}
        if fake.marked.get((slug, n)):
            sub["snapshot"]["studioVersionId"] = fake.marked[(slug, n)]
        fake.subs[sid] = sub
        if kind == "publish":
            e["status"] = "review"
        return 201, _decided(sub)
    m = re.match(r"^/api/studio/submissions/([A-Za-z0-9_-]+)/(withdraw|reply)$", path)
    if m:
        x = fake.subs.get(m.group(1))
        if not x:
            return _err("not_found", "no such submission", 404)
        if m.group(2) == "withdraw":
            if x["status"] not in ("pending", "changes"):
                return _err("conflict", f"the submission is {x['status']}", 409, reason="not_open", todo="nothing to withdraw")
            x.update(status="withdrawn", updatedAt=WHEN)
            if x["kind"] == "publish":
                fake.episodes[(x["_slug"], x["_n"])]["status"] = "script"
            return 200, _decided(x)
        bad = _req("submission-message.request", body)
        if bad:
            return bad
        if x["status"] in ("withdrawn", "approved", "rejected"):
            return _err("conflict", f"the submission is {x['status']}", 409, reason="closed", todo="start a new submission")
        x["thread"].append(_msg("author", body["text"], body.get("shot")))
        return 200, _decided(x)
    m = re.match(r"^/api/studio/worlds/([a-z0-9-]+)/episodes/(\d+)/studio-version$", path)
    if m:
        bad = _req("studio-version.request", body)
        if bad:
            return bad
        slug, n = m.group(1), int(m.group(2))
        e = fake.episodes.get((slug, n))
        if not e:
            return _err("not_found", f"no episode {n} in {slug}", 404, reason="no_episode", todo="push the episode first")
        vid = body["versionId"]
        if vid is None:
            fake.marked.pop((slug, n), None)
            return 200, _check("studio-version.response", {"episode": {"id": f"e{n}", "number": n}, "version": None})
        v = fake.videos.get(vid)
        if not v or (v["slug"], v["n"]) != (slug, n):
            return _err("not_found", f'no video "{vid}" of your scene of this episode', 404, reason="no_version",
                        todo="make the video on the site from your own scene of this episode")
        if not v["current"]:
            return _err("conflict", "this video was made before the last change of the episode's film", 409,
                        reason="version_stale", todo="make the video again from the current revision, then mark it")
        fake.marked[(slug, n)] = vid
        e["missing"] = [x for x in e.get("missing") or [] if x["code"] != "studio_version"]
        return 200, _check("studio-version.response", {
            "episode": {"id": f"e{n}", "number": n},
            "version": {"id": vid, "lang": "ru", "createdAt": WHEN, "videoUrl": f"https://media.example.com/{vid}.mp4",
                        "current": True}})
    return None


def admin_routes(fake: Fake, method: str, path: str, body: dict):
    """/api/admin/studio/submissions* (a staff key of an admin)."""
    u = urllib.parse.urlsplit(path)
    q = dict(urllib.parse.parse_qsl(u.query))
    if method == "GET" and u.path == "/api/admin/studio/submissions":
        rows = [x for x in fake.subs.values() if (not q.get("status") or x["status"] == q["status"])
                and (not q.get("kind") or x["kind"] == q["kind"]) and (not q.get("world") or x["_slug"] == q["world"])]
        rows = sorted(rows, key=lambda s: s["id"])[: int(q.get("limit") or 200)]
        return 200, {"submissions": [_brief(fake, x) for x in rows]}
    m = re.match(r"^/api/admin/studio/submissions/([A-Za-z0-9_-]+)(?:/(approve|return|reject|reply))?$", u.path)
    if not m:
        return None
    x = fake.subs.get(m.group(1))
    if not x:
        return _err("not_found", "no such submission", 404)
    act = m.group(2)
    if method == "GET" and not act:
        return 200, _review(fake, x, q.get("lang", "ru"))
    if method != "POST" or not act:
        return None
    if act == "approve":
        bad = _req("submission-approve.request", body)
        if bad:
            return bad
        if x["status"] != "pending":
            return _err("conflict", f"the submission is {x['status']}, not pending", 409, reason="not_pending",
                        todo="only an open submission can be decided")
        if x["id"] in fake.stale_version and not body.get("staleVersion"):
            return _err("conflict", "the studio version is older than the episode's current film", 409,
                        reason="studio_version_stale", todo="return it, or approve with staleVersion: true")
        x.update(status="approved", decidedBy="u0", decidedAt=WHEN, updatedAt=WHEN)
        if body.get("note"):
            x["thread"].append(_msg("staff", body["note"]))
        if x["_n"] is not None:
            fake.episodes[(x["_slug"], x["_n"])]["status"] = "published" if x["kind"] != "unpublish" else "archived"
        return 200, _decided(x)
    if act == "return":
        bad = _req("submission-return.request", body)
        if bad:
            return bad
        if x["status"] != "pending":
            return _err("conflict", f"the submission is {x['status']}, not pending", 409, reason="not_pending",
                        todo="only an open submission can be decided")
        x["thread"].append(_msg("staff", body["text"]))
        for s in body.get("shots") or []:
            x["thread"].append(_msg("staff", s["text"], s["shot"]))
        x.update(status="changes", updatedAt=WHEN)
        if x["kind"] == "publish":
            fake.episodes[(x["_slug"], x["_n"])]["status"] = "script"
        return 200, _decided(x)
    if act == "reject":
        bad = _req("submission-reject.request", body)
        if bad:
            return bad
        if x["status"] not in ("pending", "changes"):
            return _err("conflict", f"the submission is {x['status']}", 409, reason="not_open",
                        todo="only an open submission can be rejected")
        x["thread"].append(_msg("staff", body["reason"]))
        x.update(status="rejected", decidedBy="u0", decidedAt=WHEN, updatedAt=WHEN)
        return 200, _decided(x)
    bad = _req("submission-message.request", body)
    if bad:
        return bad
    x["thread"].append(_msg("staff", body["text"], body.get("shot")))
    return 200, _decided(x)


def handler(fake: Fake):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status: int, body: object, raw: bytes | None = None, ctype="application/json"):
            data = raw if raw is not None else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        def _bearer(self) -> str | None:
            h = self.headers.get("Authorization") or ""
            return h[len("Bearer "):] if h.startswith("Bearer ") else None

        def _authed(self) -> bool:
            b = self._bearer()
            if b and b.startswith("tds_") and fake.banned:       # (a banned person's revoked key: 403 banned)
                self._send(*_banned(fake))
                return False
            if b not in fake.keys:
                self._send(*_err("unauthorized", "invalid or revoked studio key", 401, reason="bad_key",
                                 todo="create a new studio key in the cabinet and run tadam login again"))
                return False
            return True

        def _staff(self) -> bool:
            b = self._bearer()
            if b in fake.keys:
                self._send(*_err("unauthorized", "a studio key works only on /api/studio/*", 401))
                return False
            if b not in fake.staff_keys:
                self._send(*_err("unauthorized", "sign in first", 401))
                return False
            if not fake.staff:
                self._send(*_err("forbidden", "needs the admin role", 403))
                return False
            return True

        # ---------------------------------------------------------------- storage links
        def do_PUT(self):
            m = re.match(r"^/upload/([0-9a-f-]+)/(.+)$", self.path)
            if self.headers.get("Authorization"):
                fake.leaks.append(self.path)
            if not m:
                return self._send(404, {})
            sess = fake.sessions.get(m.group(1))
            path = m.group(2)
            if not sess or path not in sess["uploads"]:
                return self._send(403, {})
            if self.headers.get("Content-Type") != sess["types"][path]:
                return self._send(403, {})
            with fake.lock:
                fake.pending[sess["uploads"][path]] = self._body()
                fake.puts.append(path)
            self._send(200, {}, raw=b"")

        def _route(self, method: str, body: dict) -> bool:
            """join / rules, the owner's routes, submissions and the studio version: True when answered."""
            with fake.lock:
                r = join_routes(fake, method, self.path, body, self._bearer())
                if r:
                    self._send(*r)
                    return True
                if self.path.startswith("/api/admin/studio/"):
                    if self._staff():
                        r = admin_routes(fake, method, self.path, body)
                        self._send(*(r or _err("not_found", "no such studio admin route", 404)))
                    return True
                if not self._authed():
                    return True
                r = editor_routes(fake, method, self.path, body)
                if r:
                    self._send(*r)
                    return True
            return False

        def do_GET(self):
            fake.calls.append(("GET", self.path))
            if self.path.startswith("/blob/"):
                if self.headers.get("Authorization"):
                    fake.leaks.append(self.path)
                data = fake.blobs.get(self.path[len("/blob/"):])
                return self._send(200, None, raw=data, ctype="application/octet-stream") if data is not None \
                    else self._send(404, {})
            if self._route("GET", {}):
                return
            if not self._authed():
                return
            if self.path == "/api/studio/me":
                return self._send(200, _check("studio-me.response", {
                    "user": {"id": "u1", "email": EMAIL, "name": "Editor", "handle": None},
                    "via": "api", "access": fake.access, "since": WHEN, "rules": _rules_state(fake),
                    "staff": fake.staff, "limits": {"storageMb": 500, "ttsPerDay": 50, "pushesPerHour": 30},
                    "worlds": []}))
            if self.path == "/api/studio/status":
                return self._send(200, _check("status.response", _status(fake)))
            m = re.match(r"^/api/studio/worlds/([a-z0-9-]+)/pull$", self.path)
            if m:
                w = fake.worlds.get(m.group(1))
                if not w:
                    return self._send(*_err("not_found", f"no world \"{m.group(1)}\"", 404))
                if not w["revs"]:
                    return self._send(*_err("conflict", "nothing pushed yet", 409, reason="no_revision", todo="tadam push first"))
                last = w["revs"][-1]
                files = {p: f"{fake.base}/blob/{w['id']}/{x['sha256']}" for p, x in last["manifest"].items()}
                return self._send(200, _check("pull.response", {
                    "world": {"id": w["id"], "slug": m.group(1), "status": w["status"]}, "rev": last["rev"],
                    "manifest": last["manifest"], "files": files, "expiresAt": WHEN}))
            self._send(*_err("not_found", "no such studio route", 404))

        def do_POST(self):
            fake.calls.append(("POST", self.path))
            raw = self._body()
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                return self._send(*_err("bad_request", "not JSON", 400))
            m = re.match(r"^/api/studio/worlds/([a-z0-9-]+)/push/(begin|commit)$", self.path)
            if not m:
                if not self._route("POST", body):
                    self._send(*_err("not_found", "no such studio route", 404))
                return
            if not self._authed():
                return
            slug, step = m.groups()
            if fake.accepted != fake.rules_version:
                return self._send(*_err("forbidden", f"the studio rules changed (version {fake.rules_version}): accept "
                                        "them before pushing or voicing", 403, reason="rules_outdated",
                                        todo="run tadam join (it shows the new rules)", current=fake.rules_version,
                                        accepted=fake.accepted))
            with fake.lock:
                return self._send(*(begin(fake, slug, body) if step == "begin" else commit(fake, slug, body)))
    return H


def _need_base(base, latest):
    if base == latest:
        return None
    if latest is not None and (base is None or base < latest):
        return _err("conflict", f"the server has revision {latest}, the folder is from {base or 'nothing'}: pull first",
                    409, reason="stale_base", todo="run tadam pull, merge, then tadam push", serverRev=latest)
    return _err("conflict", f"there is no revision {base} of this world yet", 409, reason="bad_base",
                todo="run tadam pull to get the server's revision", serverRev=latest)


def begin(fake: Fake, slug: str, body: dict):
    assert not schema.validate("push-begin.request", body), schema.validate("push-begin.request", body)[:3]
    man = body["manifest"]
    bad = [{"path": p, "reason": why_not(p)} for p in man if why_not(p)]
    if bad:
        return _err("bad_request", f"{len(bad)} path(s) of the folder are not accepted", 400, reason="bad_paths",
                    todo="rename or remove these files", paths=bad)
    if "world.json" not in man:
        return _err("bad_request", "the folder has no world.json", 400, reason="no_world_json", todo="add world.json")
    w = fake.worlds.get(slug)
    latest = w["revs"][-1]["rev"] if w and w["revs"] else None
    if not w and body["baseRev"] is not None:
        return _err("not_found", f"no world \"{slug}\"", 404)
    no = _need_base(body["baseRev"], latest)
    if no:
        return no
    wid = w["id"] if w else "w" + uuid.uuid4().hex[:10]
    pid = str(uuid.uuid4())
    uploads, types, out, asked = {}, {}, [], set()
    for p in sorted(man):
        key = f"{wid}/{man[p]['sha256']}"
        if key in fake.blobs or key in asked:
            continue
        asked.add(key)
        uploads[p] = key
        types[p] = MIME[p.rsplit(".", 1)[-1]]
        out.append({"path": p, "url": f"{fake.base}/upload/{pid}/{p}", "headers": {"content-type": types[p]},
                    "expiresAt": WHEN})
    fake.sessions[pid] = {"slug": slug, "worldId": wid, "baseRev": body["baseRev"], "manifest": man,
                          "uploads": uploads, "types": types, "done": False}
    return 200, _check("push-begin.response", {"pushId": pid, "rev": (latest or 0) + 1, "uploads": out,
                                                "kept": len(man) - len(uploads), "expiresAt": WHEN})


def commit(fake: Fake, slug: str, body: dict):
    s = fake.sessions.get(body.get("pushId"))
    if not s or s["slug"] != slug:
        return _err("not_found", "no such push", 404)
    if s["done"]:
        return _err("conflict", "this push is already committed", 409, reason="committed", todo="start a new push")
    w = fake.worlds.get(slug)
    latest = w["revs"][-1]["rev"] if w and w["revs"] else None
    no = _need_base(s["baseRev"], latest)
    if no:
        return no
    man = s["manifest"]
    bad = []
    for p, key in s["uploads"].items():
        data = fake.pending.get(key)
        if data is None:
            bad.append({"path": p, "reason": "not uploaded"})
        elif len(data) != man[p]["bytes"] or hashlib.sha256(data).hexdigest() != man[p]["sha256"]:
            bad.append({"path": p, "reason": "its fingerprint does not match the manifest"})
    if bad:
        return _err("bad_request", f"{len(bad)} file(s) were not accepted", 400, reason="upload_missing",
                    todo="upload every file push/begin asked for, then commit", files=bad)
    if slug in fake.breaking and not (fake.staff and body.get("confirm")):
        impact = [{"episode": 1, "staleRoles": 2, "heroes": ["cow"], "steps": ["cow-1"], "reasons": ["line cow-1 text"]}]
        return _err("conflict", "a breaking change: episode 1 would make 2 sent role(s) of other people stale", 409,
                    reason="breaking_change", todo="push again with confirm: true if that is what you want", impact=impact)
    for key in s["uploads"].values():
        fake.blobs[key] = fake.pending.pop(key)
    if not w:
        w = fake.worlds[slug] = {"id": s["worldId"], "status": "draft", "revs": []}
    prev = w["revs"][-1]["manifest"] if w["revs"] else {}
    rev = (latest or 0) + 1
    w["revs"].append({"rev": rev, "manifest": man})
    s["done"] = True
    summary = {"added": sorted(p for p in man if p not in prev),
               "changed": sorted(p for p in man if p in prev and prev[p]["sha256"] != man[p]["sha256"]),
               "removed": sorted(p for p in prev if p not in man), "episodes": {}}
    eps = sorted({int(p.split("/")[1]) for p in man if p.startswith("episodes/")})
    return 200, _check("push-commit.response", {
        "rev": rev, "world": {"id": w["id"], "slug": slug, "status": w["status"]},
        "check": {"ok": True, "issues": [{"level": "warning", "where": "cover.png", "code": "cover_small",
                                          "message": "the cover is small"}]},
        "summary": summary, "editClass": None,
        "episodes": [{"number": n, "changeClass": None, "reasons": [], "impact": None, "applied": "applied"} for n in eps],
        "links": {"world": f"https://tadamshow.com/ru/w/{slug}",
                  "episodes": [{"number": n, "url": f"https://tadamshow.com/ru/w/{slug}/{n}"} for n in eps]}})


class Server:
    """with Server() as fake: ... (fake.base is the server's address)."""

    def __enter__(self) -> Fake:
        self.fake = Fake()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.fake))
        self.fake.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self.fake

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)
