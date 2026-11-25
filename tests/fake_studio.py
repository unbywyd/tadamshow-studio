"""A local stand-in for the studio server (/api/studio/*), as the contract says it behaves (the server's
services/studio/push.ts and pull.ts, packages/contracts studio.ts; the kit's schema/*.json):

  POST worlds/:slug/push/begin   {baseRev, manifest} -> the files it lacks (by fingerprint), one upload link each;
                                 baseRev must be the latest revision (older: 409 stale_base; none yet: 409 bad_base)
  PUT  <upload link>             the bytes (no key: a storage link)
  POST worlds/:slug/push/commit  {pushId, confirm?} -> every asked-for file must be there and match its fingerprint;
                                 a world marked `breaking` answers 409 breaking_change unless confirm (staff)
  GET  worlds/:slug/pull         the latest revision: manifest + a download link per file
  GET  status, GET me

Every JSON answer is checked against the kit's schema/<answer>.json, so the fake cannot drift from the contract.
Nothing leaves 127.0.0.1.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tadam import schema
from tadam.folder import why_not

KEY = "tds_abcd1234_" + "S3cretS3cretS3cretS3cret"
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


def _err(code: str, message: str, status: int, **issues) -> tuple[int, dict]:
    return status, {"error": {"code": code, "message": message, **({"issues": issues} if issues else {})}}


def _check(name: str, doc: dict) -> dict:
    bad = schema.validate(name, doc)
    assert not bad, f"the fake's {name} answer breaks the contract: {bad[:3]}"
    return doc


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

        def _authed(self) -> bool:
            if self.headers.get("Authorization") != f"Bearer {KEY}":
                self._send(*_err("unauthorized", "invalid or revoked studio key", 401, reason="bad_key",
                                 todo="create a new studio key in the cabinet and run tadam login again"))
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

        def do_GET(self):
            fake.calls.append(("GET", self.path))
            if self.path.startswith("/blob/"):
                if self.headers.get("Authorization"):
                    fake.leaks.append(self.path)
                data = fake.blobs.get(self.path[len("/blob/"):])
                return self._send(200, None, raw=data, ctype="application/octet-stream") if data is not None \
                    else self._send(404, {})
            if not self._authed():
                return
            if self.path == "/api/studio/me":
                return self._send(200, _check("studio-me.response", {
                    "user": {"id": "u1", "email": EMAIL, "name": "Editor", "handle": None},
                    "via": "api", "access": True, "since": WHEN, "request": "granted", "about": None,
                    "staff": fake.staff, "limits": {"storageMb": 500, "ttsPerDay": 50, "pushesPerHour": 30},
                    "worlds": []}))
            if self.path == "/api/studio/status":
                return self._send(200, _check("status.response", fake.status_doc or {
                    "worlds": [], "submissions": [], "unread": 0, "notifications": []}))
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
            if not self._authed():
                return
            body = json.loads(self._body() or b"{}")
            m = re.match(r"^/api/studio/worlds/([a-z0-9-]+)/push/(begin|commit)$", self.path)
            if not m:
                return self._send(*_err("not_found", "no such studio route", 404))
            slug, step = m.groups()
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
