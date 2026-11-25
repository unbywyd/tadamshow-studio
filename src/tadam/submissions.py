"""SUBMISSIONS: the editor's requests to the project's owner, and the owner's review from the terminal (studio-tz 5,
5а, 8; the server's http/STUDIO-API.md).

The editor (studio key, /api/studio/*):
    submit <episode> "<note>"     GET status first: the episode's readiness list (`missing`) must be empty, else the
                                  list is shown and nothing is sent; then POST submissions (publish, or revision for a
                                  published episode). A returned one is reopened by submitting again.
    withdraw / reply / unpublish  POST submissions/:id/withdraw | reply {text, shot?}; POST submissions {unpublish}
    studio-version <ep> <video>   POST worlds/:slug/episodes/:n/studio-version {versionId | null}
    status                        the open submissions with their threads (the owner's remarks, with their shots)

The project's owner (staff key `tdm_…`, /api/admin/studio/*, admin and above):
    review list / show / approve / return / reject / reply
approve and reject are decided by the person: the CLI asks them to type the submission's id at a real keyboard.
"""
from __future__ import annotations

import urllib.parse

from tadam.api import Api, ApiError
from tadam.link import mask_email

OPEN = ("pending", "changes")


class Refused(Exception):
    """The kit will not send it (not ready, nothing open, ambiguous); the message says what to do."""

    def __init__(self, message: str, missing: list | None = None):
        super().__init__(message)
        self.missing = missing or []


def _title(t: object) -> str:
    if isinstance(t, dict):
        return str(t.get("ru") or t.get("en") or next(iter(t.values()), ""))
    return str(t or "")


def _day(at: object) -> str:
    return str(at or "")[:16].replace("T", " ")


def missing_lines(missing: list) -> list[str]:
    return [f"  - {m.get('message')} [{m.get('code')}]" for m in missing if isinstance(m, dict)]


# ------------------------------------------------------------------------------------------------ the editor

def _world(status: dict, slug: str) -> dict:
    for w in status.get("worlds") or []:
        if w.get("slug") == slug:
            return w
    raise Refused(f"the server has no world \"{slug}\" of yours yet: `tadam push` first")


def _episode(w: dict, n: int) -> dict:
    for e in w.get("episodes") or []:
        if e.get("number") == n:
            return e
    raise Refused(f"the server has no episode {n} of {w.get('slug')}: add it here and `tadam push` first")


def readiness(api: Api, slug: str, n: int) -> tuple[dict, dict, list]:
    """(the world, the episode, what is still missing before it can be submitted) from GET status."""
    s = api.get("/api/studio/status")
    w = _world(s, slug)
    e = _episode(w, n)
    return w, e, list(e.get("missing") or [])


def submit(api: Api, slug: str, n: int, note: str | None, kind: str | None = None) -> dict:
    """The episode to the owner: refused with the readiness list when anything is missing."""
    w, e, missing = readiness(api, slug, n)
    kind = kind or ("revision" if e.get("status") == "published" else "publish")
    sub = e.get("submission") or {}
    if sub.get("status") == "pending":
        raise Refused(f"episode {n} has an open submission already ({sub.get('id')}, {sub.get('kind')}): wait for the "
                      f"owner, or `tadam withdraw --episode {n}`")
    if missing:
        raise Refused(f"episode {n} of {slug} is not ready to submit:", missing)
    body = {"kind": kind, "world": slug, "episode": n}
    if note and note.strip():
        body["note"] = note.strip()
    try:
        return api.post("/api/studio/submissions", body)
    except ApiError as err:
        if err.reason == "not_ready":
            raise Refused(f"the server says episode {n} is not ready to submit:",
                          list(err.issues.get("missing") or [])) from None
        if err.reason == "breaking_change":
            imp = err.issues.get("impact") or {}
            raise Refused(f"this revision would make {imp.get('staleRoles', '?')} sent role(s) of other people stale "
                          f"(heroes {', '.join(imp.get('heroes') or []) or '-'}): make it a new episode instead "
                          f"(`tadam new episode`)") from None
        raise


def pick_open(api: Api, slug: str, n: int | None = None, sid: str | None = None) -> dict:
    """The open submission (pending or returned) of this world: by id, by episode, or the only one."""
    s = api.get("/api/studio/status")
    subs = [x for x in s.get("submissions") or [] if x.get("world") == slug and x.get("status") in OPEN]
    if sid:
        for x in subs:
            if x.get("id") == sid:
                return x
        raise Refused(f"no open submission {sid} in {slug} (`tadam status` lists them)")
    if n is not None:
        subs = [x for x in subs if x.get("episode") == n]
    if not subs:
        raise Refused(f"no open submission in {slug}" + (f" for episode {n}" if n is not None else ""))
    if len(subs) > 1:
        raise Refused("more than one open submission: name it with --episode <n> or --id <id>:\n" + "\n".join(
            f"  {x.get('id')}: {x.get('kind')}" + (f" episode {x['episode']}" if x.get("episode") else " (the world)")
            + f", {x.get('status')}" for x in subs))
    return subs[0]


def withdraw(api: Api, sid: str) -> dict:
    return api.post(f"/api/studio/submissions/{_q(sid)}/withdraw", {})


def reply(api: Api, sid: str, text: str, shot: str | None = None, owner: bool = False) -> dict:
    body = {"text": text.strip(), **({"shot": shot} if shot else {})}
    base = "/api/admin/studio" if owner else "/api/studio"
    return api.post(f"{base}/submissions/{_q(sid)}/reply", body)


def unpublish(api: Api, slug: str, reason: str, n: int | None = None) -> dict:
    if not reason.strip():
        raise Refused('say why it should come off the site: tadam unpublish "<reason>"')
    body = {"kind": "unpublish", "world": slug, "note": reason.strip(), **({"episode": n} if n is not None else {})}
    return api.post("/api/studio/submissions", body)


def studio_version(api: Api, slug: str, n: int, version_id: str | None) -> dict:
    """Mark a video of the editor's own scene of this episode as its studio version (None: unmark)."""
    try:
        return api.post(f"/api/studio/worlds/{slug}/episodes/{n}/studio-version", {"versionId": version_id})
    except ApiError as err:
        if err.reason == "version_stale":
            raise Refused("that video was made before the episode's film last changed: make the film again on the "
                          "site from the current revision, then mark the new one") from None
        if err.reason == "no_version":
            raise Refused(f"no video {version_id} of your own scene of episode {n}: make it on the site (record the "
                          "roles, «Собрать ролик», «Оставить») and take its id from the video's page") from None
        raise


def describe_decided(d: dict) -> str:
    s = d.get("submission") or {}
    lines = [f"submission {s.get('id')}: {s.get('kind')}, {s.get('status')}"]
    if s.get("note"):
        lines.append(f"  note: {s['note']}")
    last = (s.get("thread") or [])[-1:]
    for m in last:
        lines.append("  last message: " + _message(m))
    return "\n".join(lines)


def describe_marked(d: dict) -> str:
    e, v = d.get("episode") or {}, d.get("version")
    if not v:
        return f"episode {e.get('number')}: no studio version marked"
    return (f"episode {e.get('number')}: studio version {v.get('id')} ({v.get('lang')}, made {_day(v.get('createdAt'))}"
            f", {'from the current revision' if v.get('current') else 'OLDER than the current film: make it again'})"
            + (f"\n  watch: {v['videoUrl']}" if v.get("videoUrl") else ""))


def _message(m: dict) -> str:
    who = "owner" if m.get("side") == "staff" else "author"
    return f"[{_day(m.get('at'))}] {who}" + (f" (shot {m['shot']})" if m.get("shot") else "") + f": {m.get('text')}"


def threads(api: Api, status: dict, limit: int = 10) -> list[str]:
    """The thread of every open submission (the owner's remarks first among the lines, with their shots)."""
    lines = []
    for x in [x for x in status.get("submissions") or [] if x.get("status") in OPEN][:limit]:
        try:
            r = api.get(f"/api/studio/submissions/{_q(x.get('id', ''))}")
        except ApiError as e:
            lines.append(f"  {x.get('id')}: the thread could not be read ({e})")
            continue
        sub = r.get("submission") or {}
        thread = sub.get("thread") or r.get("thread") or []
        head = f"submission {x.get('id')} ({x.get('kind')} {x.get('world')}" + \
            (f" episode {x['episode']}" if x.get("episode") else "") + f", {x.get('status')})"
        remarks = [m for m in thread if m.get("side") == "staff"]
        lines.append(head + (f": {len(remarks)} remark(s) of the owner" if remarks else ": no remarks yet"))
        if x.get("status") == "changes":
            lines.append("  RETURNED with remarks: fix them, push, mark the studio version again, then `tadam submit` "
                         "(the same submission reopens)")
        for m in remarks:
            if m.get("shot"):
                lines.append(f"  remark on {m['shot']}: {m.get('text')}")
        lines += ["  " + _message(m) for m in thread]
        missing = r.get("missing") or []
        if missing:
            lines.append("  still missing:")
            lines += ["  " + ln for ln in missing_lines(missing)]
    return lines


def _q(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


# ------------------------------------------------------------------------------------------------ the owner

ADMIN = "/api/admin/studio/submissions"


def queue(api: Api, status: str | None = "pending", kind: str | None = None, world: str | None = None,
          limit: int | None = None) -> list[dict]:
    q = {k: v for k, v in (("status", status), ("kind", kind), ("world", world),
                           ("limit", str(limit) if limit else None)) if v}
    return list(api.get(ADMIN + ("?" + urllib.parse.urlencode(q) if q else "")).get("submissions") or [])


def review(api: Api, sid: str, lang: str = "ru") -> dict:
    return api.get(f"{ADMIN}/{_q(sid)}?lang={'en' if lang == 'en' else 'ru'}")


def approve(api: Api, sid: str, note: str | None = None, confirm: bool = False, stale_version: bool = False,
            slug: str | None = None) -> dict:
    body: dict = {}
    if note and note.strip():
        body["note"] = note.strip()
    if confirm:
        body["confirm"] = True
    if stale_version:
        body["staleVersion"] = True
    if slug:
        body["slug"] = slug
    try:
        return api.post(f"{ADMIN}/{_q(sid)}/approve", body)
    except ApiError as err:
        if err.reason == "studio_version_stale":
            raise Refused("the studio version is older than the episode's current film: `tadam review return` it "
                          "(the author makes the film again), or approve with --stale-version if you watched it and "
                          "it is fine") from None
        if err.reason == "breaking_change":
            imp = err.issues.get("impact") or {}
            raise Refused(f"approving makes {imp.get('staleRoles', '?')} sent role(s) of other people stale (heroes "
                          f"{', '.join(imp.get('heroes') or []) or '-'}, steps {', '.join(imp.get('steps') or []) or '-'})"
                          ": return it, or approve with --confirm-breaking if that is what you want") from None
        raise


def return_(api: Api, sid: str, text: str, shots: list[tuple[str, str]] | None = None) -> dict:
    body: dict = {"text": text.strip()}
    if shots:
        body["shots"] = [{"shot": s, "text": t.strip()} for s, t in shots]
    return api.post(f"{ADMIN}/{_q(sid)}/return", body)


def reject(api: Api, sid: str, reason: str) -> dict:
    return api.post(f"{ADMIN}/{_q(sid)}/reject", {"reason": reason.strip()})


def describe_queue(rows: list[dict]) -> str:
    if not rows:
        return "the queue is empty"
    lines = []
    for x in rows:
        w, e, a = x.get("world") or {}, x.get("episode"), x.get("author") or {}
        lines.append(f"{x.get('id')}  {x.get('kind')} {x.get('status')}  {w.get('slug')} «{_title(w.get('title'))}»"
                     + (f" episode {e.get('number')} «{_title(e.get('title'))}»" if e else " (the whole world)")
                     + f"  by {a.get('name') or mask_email(a.get('email'))}, {_day(x.get('createdAt'))}"
                     + (f", {x['messages']} message(s)" if x.get("messages") else ""))
        if x.get("note"):
            lines.append(f"    note: {x['note']}")
    return "\n".join(lines)


def _source(src: dict | None) -> str:
    if not src:
        return "NO SOURCE"
    s = src.get("source")
    if s == "generated":
        return f"generated ({src.get('tool')})"
    if s == "licensed":
        return f"licensed ({src.get('licence')}, {src.get('url')}" + (f", by {src['author']}" if src.get("author") else "") + ")"
    return "own" + (f" ({src['author']})" if src.get("author") else "")


def _changes(label: str, fc: dict | None) -> str | None:
    fc = fc or {}
    parts = [f"{sign}{', '.join(fc.get(k) or [])}" for k, sign in (("added", "+"), ("changed", "~"), ("removed", "-"))
             if fc.get(k)]
    return f"  {label}: " + "  ".join(parts) if parts else None


def _cards(cards: dict | None, indent: str = "  ") -> list[str]:
    if not cards:
        return [indent + "(no script)"]
    names = {k: (h.get("name") or k) for k, h in (cards.get("heroes") or {}).items()}
    out, shot = [], None
    for it in cards.get("items") or []:
        if it.get("shot") != shot:
            shot = it.get("shot")
            out.append(f"{indent}{shot} ({it.get('seconds', 0):g} s) {it.get('remark') or ''}".rstrip())
        k = it.get("kind")
        if k == "line":
            out.append(f"{indent}  {names.get(it.get('hero'), it.get('hero'))}: «{it.get('text')}»"
                       + (f"  (hint: {it['hint']})" if it.get("hint") else ""))
        elif k == "narration":
            out.append(f"{indent}  narration: «{it.get('text')}»")
        elif k == "card":
            out.append(f"{indent}  title card: {it.get('title') or ''}" + (f" / {it['sub']}" if it.get("sub") else ""))
        else:
            who = ", ".join(names.get(h, h) for h in it.get("heroes") or [])
            out.append(f"{indent}  scene" + (f": {who}" if who else "") + (f" — {it['text']}" if it.get("text") else ""))
    return out


def describe_review(r: dict) -> str:
    """The review screen in the terminal, top to bottom like the admin's (studio-tz 8.2)."""
    s, a = r.get("submission") or {}, r.get("author") or {}
    w, e = r.get("world") or {}, r.get("episode")
    L = [f"SUBMISSION {s.get('id')}: {s.get('kind')}, {s.get('status')} (since {_day(s.get('createdAt'))})"
         + (f" by {a.get('name') or mask_email(a.get('email'))}" if a else "")
         + (f", accepted the rules v{a['rulesVersion']}" if a.get("rulesVersion") else "")]
    if s.get("note"):
        L.append(f"  note: {s['note']}")
    v = r.get("studioVersion")
    L.append("STUDIO VIDEO (watch it first):")
    if v:
        L.append(f"  {v.get('videoUrl') or '(no file link)'}")
        L.append(f"  made {_day(v.get('createdAt'))}, {v.get('lang')}, "
                 + ("from the current revision" if v.get("current") else "OLDER than the current film"))
    else:
        L.append("  none marked")
    L.append(f"WORLD {w.get('slug')} «{_title(w.get('title'))}» ({w.get('status')}, {', '.join(w.get('langs') or [])}"
             + (f", {w['genre']}" if w.get("genre") else "") + ")")
    if w.get("tagline"):
        L.append(f"  tagline: {_title(w['tagline'])}")
    if w.get("description"):
        L.append(f"  about: {_title(w['description'])}")
    for k, val in (w.get("bible") or {}).items():
        if isinstance(val, list):
            for x in val:
                L.append(f"  bible {k}: {_title(x)}")
        elif val:
            L.append(f"  bible {k}: {_title(val)}")
    L.append(f"  to change it yourself: {w.get('pull')}  (then push and approve)")
    if e:
        L.append(f"EPISODE {e.get('number')} «{_title(e.get('title'))}» ({e.get('status')}, script revision "
                 f"{e.get('scriptRev') or '-'})")
        for k in ("logline", "teaser"):
            if e.get(k):
                L.append(f"  {k}: {_title(e[k])}")
    heroes = r.get("heroes") or []
    if heroes:
        L.append("HEROES:")
        for h in heroes:
            p = h.get("puppet") or {}
            L.append(f"  {h.get('slug')} «{_title(h.get('name'))}»" + (f" — {_title(h['trait'])}" if h.get("trait") else "")
                     + f"; puppet {'passed' if p.get('passed') else 'NOT passed' if p else 'missing'}"
                     + ("; in this episode" if h.get("inEpisode") else "") + ("; NEW (draft)" if h.get("draft") else ""))
            for k in ("portraitUrl", "sheetUrl"):
                if h.get(k):
                    L.append(f"    {k[:-3]}: {h[k]}")
    sc = r.get("script") or {}
    L.append(f"SCRIPT ({sc.get('lang')}) by shots:")
    L += _cards(sc.get("cards"), "  ")
    if sc.get("live"):
        L.append("  the LIVE script (what viewers see now):")
        L += _cards(sc["live"], "    ")
    sets = r.get("sets") or []
    if sets:
        L.append("SETS: " + "; ".join(f"{x.get('slug')} «{x.get('title')}»" + (f" {x['previewUrl']}" if x.get("previewUrl") else "")
                                      for x in sets))
    media = r.get("media") or []
    if media:
        L.append(f"PICTURES AND SOUNDS ({len(media)}), where they come from:")
        for m in media[:60]:
            L.append(f"  {m.get('path')} ({m.get('kind')}, {max(1, int(m.get('bytes') or 0) // 1024)} KB): {_source(m.get('source'))}")
        if len(media) > 60:
            L.append(f"  and {len(media) - 60} more")
    ck = r.get("check")
    if ck is not None:
        iss = ck.get("issues") or []
        ne = sum(i.get("level") == "error" for i in iss)
        L.append(f"CHECK of the last push: {'ok' if ck.get('ok') else 'FAILED'}, {ne} error(s), {len(iss) - ne} other")
        for i in [i for i in iss if i.get("level") != "info"][:20]:
            L.append(f"  {i.get('level')} {i.get('where')}: {i.get('message')} [{i.get('code')}]")
    if r.get("missing"):
        L.append("MISSING before publication:")
        L += missing_lines(r["missing"])
    rv = r.get("revision")
    if rv:
        L.append(f"REVISION: class {rv.get('changeClass') or '-'}" + (f" ({'; '.join(rv['reasons'])})" if rv.get("reasons") else ""))
        imp = rv.get("impact")
        if imp:
            L.append(f"  impact: {imp.get('staleRoles')} sent role(s) of other people go stale; heroes "
                     f"{', '.join(imp.get('heroes') or []) or '-'}; steps {', '.join(imp.get('steps') or []) or '-'}")
        for lab in ("shots", "steps", "files"):
            ln = _changes(lab, rv.get(lab))
            if ln:
                L.append(ln)
        if rv.get("held"):
            L.append("  held until approval: " + ", ".join(rv["held"]))
    rev = r.get("rev") or {}
    L.append(f"REVISION submitted {rev.get('submitted')}, the server's latest {rev.get('latest')}"
             + ("  (pushed since: check the studio video still matches)" if rev.get("latest") and rev.get("latest") != rev.get("submitted") else ""))
    thread = r.get("thread") or s.get("thread") or []
    L.append("THREAD:" if thread else "THREAD: no messages")
    L += ["  " + _message(m) for m in thread]
    L.append(f"decide: tadam review approve {s.get('id')} | return {s.get('id')} \"<remarks>\" [--shot sh3 \"<remark>\"] | "
             f"reject {s.get('id')} \"<reason>\"")
    return "\n".join(L)
