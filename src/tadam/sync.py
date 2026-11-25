"""THE WORLD FOLDER AND THE SERVER: `tadam push`, `tadam pull`, `tadam diff` (studio-tz 3.4, 5, 5а).

What the folder keeps about the server, in .tadam/ (never sent, never committed):
    .tadam/link.json            {url, slug, worldId, rev}: which world on which server, and its revision here
    .tadam/base.json            {rev, manifest}: the manifest of the revision last pulled or pushed (the merge base)
    .tadam/revs/<rev>/          that revision's manifest and its JSON files (world, heroes, sets, scripts), so
                                `tadam diff <rev>` can show shots and steps of revisions this folder has seen
    .tadam/removed/<time>/      local files a pull took away because the server removed them (nothing is lost)

push: the local check first (no push with errors) -> the manifest -> begin (the server answers which files it
lacks, with one-time upload links) -> only those files are uploaded (in parallel, retried) -> commit (the server's
own check, the change classes, the links) -> the new revision is saved here. Always "from a revision": a newer one on
the server answers 409 stale_base, and the push says to pull first.

pull: the first time, the world into a new folder; afterwards a THREE-WAY MERGE BY FILE against the base:
    changed only on the server            -> the server's file is taken
    changed only here                     -> mine stays
    changed in both places                -> mine stays, the server's is written next to it as <file>.server
    removed on the server, unchanged here -> moved to .tadam/removed/<time>/ (and said so)
    removed on the server, changed here   -> mine stays (and said so)
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from tadam import folder
from tadam.api import Api, ApiError
from tadam.world import World, WorldError, read_json, write_json

PARALLEL = 6
MAX_FILE = 200 * 1024 * 1024
SNAP_MAX = 2 * 1024 * 1024        # JSON files kept per revision for `tadam diff` (they are small)


class SyncError(Exception):
    """A push or pull that cannot go on; the message says what to do."""


# ------------------------------------------------------------------------------------------------ .tadam/ state

def _state(root: Path) -> Path:
    return Path(root) / ".tadam"


def read_link(root: Path) -> dict:
    data, _ = read_json(_state(root) / "link.json")
    return data if isinstance(data, dict) else {}


def read_base(root: Path) -> dict[str, dict]:
    data, _ = read_json(_state(root) / "base.json")
    m = data.get("manifest") if isinstance(data, dict) else None
    return m if isinstance(m, dict) else {}


def _save(root: Path, url: str, slug: str, world_id: str | None, rev: int, manifest: dict, files: dict[str, bytes]):
    """The revision now shared by this folder and the server: link, base, and the snapshot for `tadam diff`."""
    st = _state(root)
    write_json(st / "link.json", {"url": url, "slug": slug, "worldId": world_id, "rev": rev,
                                  "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    write_json(st / "base.json", {"rev": rev, "manifest": manifest})
    snap = st / "revs" / str(rev)
    if snap.exists():
        shutil.rmtree(snap)
    write_json(snap / "manifest.json", manifest)
    for p, data in files.items():
        f = snap / "files" / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)


def _local_jsons(root: Path, manifest: dict) -> dict[str, bytes]:
    return {p: (Path(root) / p).read_bytes() for p, m in manifest.items() if p.endswith(".json") and m["bytes"] <= SNAP_MAX}


def world_slug(root: Path) -> str:
    data, err = read_json(Path(root) / "world.json")
    slug = data.get("slug") if isinstance(data, dict) else None
    if not isinstance(slug, str) or not folder.SLUG.match(slug):
        raise SyncError("world.json has no valid slug (lowercase latin letters, digits and dashes): fix it, "
                        "then `tadam check`")
    return slug


def _linked(root: Path, api: Api, slug: str) -> dict:
    lk = read_link(root)
    if lk and lk.get("url") and lk["url"] != api.link.url:
        raise SyncError(f"this folder belongs to {lk['url']}, not {api.link.url}: set TADAM_STUDIO_URL to it, or "
                        f"pull the world from {api.link.url} into a new folder")
    if lk and lk.get("slug") and lk["slug"] != slug:
        raise SyncError(f"world.json says slug \"{slug}\" but this folder is the server's \"{lk['slug']}\": "
                        f"put the slug back (a world's address does not change after the first push)")
    return lk


# ------------------------------------------------------------------------------------------------ push

@dataclass
class Pushed:
    response: dict
    uploaded: list[str]
    kept: int
    local_only: list[tuple[str, str]]
    warnings: list = field(default_factory=list)


def _refuse_scan(sc: folder.Scan) -> None:
    if sc.server_copies:
        raise SyncError("files from the last pull are not merged yet: " + ", ".join(sc.server_copies[:8])
                        + " — merge each into its file, delete the .server copy, then push")
    if sc.case_clashes:
        raise SyncError("files whose names differ only in letter case: " + ", ".join(sc.case_clashes[:8]))
    if sc.empty:
        raise SyncError("empty files (the server refuses them): " + ", ".join(sc.empty[:8]))
    if len(sc.manifest) > folder.MAX_FILES:
        raise SyncError(f"{len(sc.manifest)} files: at most {folder.MAX_FILES} in a world")
    if "world.json" not in sc.manifest:
        raise SyncError("no world.json")


def push(root: Path, api: Api, confirm: bool = False, log=print) -> Pushed:
    from tadam import check, issues
    root = Path(root)
    slug = world_slug(root)
    lk = _linked(root, api, slug)
    found = check.check_world(root)
    errors = [i for i in found if i.level == "error"]
    if errors:
        raise SyncError("`tadam check` found errors; nothing was sent:\n" + issues.format_text(errors))
    sc = folder.scan(root)
    _refuse_scan(sc)
    base_rev = lk.get("rev") if isinstance(lk.get("rev"), int) else None
    try:
        begin = api.post(f"/api/studio/worlds/{slug}/push/begin", {"baseRev": base_rev, "manifest": sc.manifest})
    except ApiError as e:
        raise _push_error(e, slug) from None
    ups = begin.get("uploads") or []
    for u in ups:
        if u.get("path") not in sc.manifest:
            raise SyncError(f"the server asked for a file this folder did not offer: {u.get('path')!r}")
    log(f"sending {len(ups)} file(s) of {len(sc.manifest)} (the server has the other {begin.get('kept', 0)}) ...")

    def send(u: dict) -> str:
        p = u["path"]
        data = (root / p).read_bytes()
        if hashlib.sha256(data).hexdigest() != sc.manifest[p]["sha256"]:
            raise SyncError(f"{p} changed while it was being sent: push again")
        api.upload(u["url"], data, u.get("headers") or {})
        return p

    if ups:
        with ThreadPoolExecutor(PARALLEL) as pool:
            done = list(pool.map(send, ups))
    else:
        done = []
    body = {"pushId": begin["pushId"]}
    if confirm:
        body["confirm"] = True
    try:
        res = api.post(f"/api/studio/worlds/{slug}/push/commit", body)
    except ApiError as e:
        raise _push_error(e, slug) from None
    w = res.get("world") or {}
    _save(root, api.link.url, slug, w.get("id"), int(res["rev"]), sc.manifest, _local_jsons(root, sc.manifest))
    return Pushed(res, done, int(begin.get("kept") or 0), sc.local_only,
                  [i for i in found if i.level == "warning"])


def _push_error(e: ApiError, slug: str) -> SyncError:
    if e.reason == "stale_base":
        srv = e.issues.get("serverRev")
        return SyncError(f"the server has a newer revision of {slug}" + (f" ({srv})" if srv else "")
                         + ": run `tadam pull` first, merge, then `tadam push`")
    if e.reason == "bad_base":
        return SyncError(f"{e.message}: run `tadam pull` to get the server's revision")
    if e.reason == "breaking_change":
        lines = ["a BREAKING change (class C): it makes other people's sent roles stale, so it was not applied."]
        for x in e.issues.get("impact") or []:
            lines.append(f"  episode {x.get('episode')}: {x.get('staleRoles')} sent role(s) of other people go stale;"
                         f" heroes {', '.join(x.get('heroes') or []) or '-'}; steps {', '.join(x.get('steps') or []) or '-'}")
            for r in x.get("reasons") or []:
                lines.append(f"    - {r}")
        lines.append(f"what to do: {e.todo}" if e.todo else "")
        if "confirm" in e.todo:
            lines.append("to accept it: `tadam push --confirm` — only after the person said yes to exactly this")
        return SyncError("\n".join(x for x in lines if x))
    if e.reason == "slug_taken":
        return SyncError(f"{e.message} — {e.todo}")
    if e.status == 401:
        return SyncError(f"{e}: run `tadam login` with a valid studio key")
    if e.reason == "rules_outdated" or (e.status == 403 and "rules" in e.message):
        return SyncError(f"{e}: the studio's rules changed; the person reads and accepts them again, themself, in a "
                         f"terminal: `tadam login` (or `tadam login --key`)")
    paths = e.issues.get("paths") or e.issues.get("files")
    extra = ""
    if isinstance(paths, list) and paths:
        extra = "\n" + "\n".join(f"  {p.get('path', p) if isinstance(p, dict) else p}"
                                 + (f": {p.get('reason')}" if isinstance(p, dict) and p.get("reason") else "")
                                 for p in paths[:20])
    return SyncError(f"the server refused the push: {e}{extra}")


def describe_push(p: Pushed) -> str:
    r = p.response
    lines = [f"pushed {r.get('world', {}).get('slug')}: revision {r.get('rev')} "
             f"({len(p.uploaded)} file(s) sent, {p.kept} already there)"]
    s = r.get("summary") or {}
    lines.append(f"files: +{len(s.get('added') or [])} ~{len(s.get('changed') or [])} -{len(s.get('removed') or [])}")
    for n, e in sorted((s.get("episodes") or {}).items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
        sh, stp = e.get("shots") or {}, e.get("steps") or {}
        parts = [f"{k} {', '.join(v)}" for k, v in (("shots added", sh.get("added")), ("shots changed", sh.get("changed")),
                                                     ("shots removed", sh.get("removed")), ("steps added", stp.get("added")),
                                                     ("steps changed", stp.get("changed")), ("steps removed", stp.get("removed"))) if v]
        if parts:
            lines.append(f"episode {n}: " + "; ".join(parts))
    for e in r.get("episodes") or []:
        cls = e.get("changeClass")
        line = f"episode {e.get('number')}: {e.get('applied')}" + (f", class {cls}" if cls else "")
        if e.get("reasons"):
            line += " (" + "; ".join(e["reasons"][:6]) + ")"
        imp = e.get("impact")
        if imp:
            line += f"; {imp.get('staleRoles', 0)} sent role(s) of others go stale"
        lines.append(line)
    if r.get("editClass"):
        lines.append(f"change class over the published episodes: {r['editClass']}")
    ck = r.get("check") or {}
    iss = ck.get("issues") or []
    lines.append(f"server check: {'ok' if ck.get('ok') else 'ERRORS'}" + (f", {len(iss)} finding(s)" if iss else ""))
    mark = {"error": "ERROR", "warning": "warn ", "info": "info "}
    for i in iss[:30]:
        lines.append(f"  {mark.get(i.get('level'), '?')} {i.get('where')}: {i.get('message')} [{i.get('code')}]")
    links = r.get("links") or {}
    if links.get("world"):
        lines.append(f"draft on the site (only you see it): {links['world']}")
    for e in links.get("episodes") or []:
        lines.append(f"  episode {e.get('number')}: {e.get('url')}")
    if p.local_only:
        shown = [x for x, _ in p.local_only if not _boring(x)]
        lines.append(f"{len(p.local_only)} file(s) stay on this computer (not part of the world format)"
                     + (": " + ", ".join(shown[:8]) + (" ..." if len(shown) > 8 else "") if shown else ""))
    return "\n".join(lines)


def _boring(p: str) -> bool:
    """The kit's own by-products next to a puppet or a set (check pictures, logs): not worth listing."""
    n = p.rsplit("/", 1)[-1]
    return n.endswith((".jpg", ".log")) and "/puppet/" in p or n.startswith("_") or n == "make.log"


# ------------------------------------------------------------------------------------------------ pull

@dataclass
class Pulled:
    root: Path
    rev: int
    first: bool
    taken: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)                # changed only here
    conflicts: list[str] = field(default_factory=list)           # both: <file>.server written
    removed: list[str] = field(default_factory=list)             # moved to .tadam/removed/<time>/
    kept_removed: list[str] = field(default_factory=list)        # the server removed it, mine changed: kept
    moved_to: Path | None = None


def _inside(root: Path, rel: str) -> Path:
    if folder.why_not(rel):
        raise SyncError(f"the server sent a path this kit does not take: {rel!r}")
    p = (root / rel).resolve()
    if root.resolve() not in p.parents:
        raise SyncError(f"the server sent a path outside the folder: {rel!r}")
    return p


def _fetch(api: Api, url: str, m: dict, rel: str) -> bytes:
    data = api.download(url, int(m["bytes"]))
    if len(data) != int(m["bytes"]) or hashlib.sha256(data).hexdigest() != m["sha256"]:
        raise SyncError(f"{rel}: the downloaded file does not match the server's manifest: pull again")
    return data


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def merge_plan(base: dict, local: dict, server: dict) -> dict[str, list[str]]:
    """The three-way decision for every path (pure: tests call it). Keys: take, keep, conflict, remove, keep_removed."""
    plan: dict[str, list[str]] = {"take": [], "keep": [], "conflict": [], "remove": [], "keep_removed": []}
    sha = lambda m, p: (m.get(p) or {}).get("sha256")      # noqa: E731
    for p in sorted(set(base) | set(local) | set(server)):
        b, l, s = sha(base, p), sha(local, p), sha(server, p)
        if l == s:
            continue
        if s is not None:
            if l == b:
                plan["take"].append(p)              # changed (or new) only on the server
            elif s == b:
                plan["keep"].append(p)              # changed (or removed) only here
            else:
                plan["conflict"].append(p)          # both
        else:                                       # the server has no such file
            if b is None:
                plan["keep"].append(p)              # new here
            elif l == b:
                plan["remove"].append(p)            # removed on the server, unchanged here
            else:
                plan["keep_removed"].append(p)      # removed on the server, changed here
    return plan


def pull(api: Api, slug: str | None, root: Path | None, into: Path | None = None, log=print) -> Pulled:
    """root: an existing world folder (merge); else the world `slug` goes into `into`/<slug> (a new folder)."""
    if root is not None:
        root = Path(root)
        own = world_slug(root)
        if slug and slug != own:
            raise SyncError(f"this folder is the world \"{own}\", not \"{slug}\": to fetch \"{slug}\" run "
                            f"`tadam pull {slug}` outside any world folder (or with --dir)")
        slug = own
        _linked(root, api, slug)
    if not slug:
        raise SyncError("which world? `tadam pull <slug>` (or run it inside a world folder)")
    try:
        res = api.get(f"/api/studio/worlds/{slug}/pull")
    except ApiError as e:
        if e.status == 404:
            raise SyncError(f"no world \"{slug}\" that you may pull") from None
        if e.reason == "no_revision":
            raise SyncError(f"nothing has been pushed to {slug} yet") from None
        raise SyncError(f"the server refused the pull: {e}") from None
    server = res.get("manifest") or {}
    links = res.get("files") or {}
    rev = int(res["rev"])
    wid = (res.get("world") or {}).get("id")
    if root is None:
        dest = Path(into or Path.cwd()) / slug
        if dest.exists() and any(dest.iterdir()):
            raise SyncError(f"{dest} exists and is not empty: pull into another folder (--dir), or run `tadam pull` "
                            f"inside it if it is this world")
        dest.mkdir(parents=True, exist_ok=True)
        out = Pulled(dest, rev, True)
        jobs = [(p, m) for p, m in sorted(server.items())]
        for p, _ in jobs:
            _inside(dest, p)
        got = _download_all(api, links, jobs)
        for p, data in got.items():
            _write(_inside(dest, p), data)
            out.taken.append(p)
        _save(dest, api.link.url, slug, wid, rev, server, {p: d for p, d in got.items() if p.endswith(".json")})
        return out

    local = folder.scan(root).manifest
    base = read_base(root)
    plan = merge_plan(base, local, server)
    out = Pulled(root, rev, False)
    for p in server:
        _inside(root, p)
    want = [(p, server[p]) for p in plan["take"] + plan["conflict"]]
    # the server's JSON files that differ from mine: fetched too, for the revision's snapshot (`tadam diff`)
    want += [(p, server[p]) for p in plan["keep"] if p in server and p.endswith(".json")]
    got = _download_all(api, links, want)
    for p in plan["take"]:
        _write(_inside(root, p), got[p])
        out.taken.append(p)
    for p in plan["conflict"]:
        target = _inside(root, p)
        _write(target.with_name(target.name + ".server"), got[p])
        out.conflicts.append(p)
    out.kept = list(plan["keep"])
    out.kept_removed = plan["keep_removed"]
    if plan["remove"]:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bin_ = _state(root) / "removed" / stamp
        for p in plan["remove"]:
            src = root / p
            dst = bin_ / p
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            out.removed.append(p)
        out.moved_to = bin_
    snap = {}
    for p, m in server.items():
        if not p.endswith(".json") or m["bytes"] > SNAP_MAX:
            continue
        if p in got:
            snap[p] = got[p]
        elif (root / p).is_file() and local.get(p, {}).get("sha256") == m["sha256"]:
            snap[p] = (root / p).read_bytes()
    _save(root, api.link.url, slug, wid, rev, server, snap)
    return out


def _download_all(api: Api, links: dict, jobs: list[tuple[str, dict]]) -> dict[str, bytes]:
    for p, _ in jobs:
        if p not in links:
            raise SyncError(f"the server gave no download link for {p}")

    def one(job):
        p, m = job
        return p, _fetch(api, links[p], m, p)
    if not jobs:
        return {}
    with ThreadPoolExecutor(PARALLEL) as pool:
        return dict(pool.map(one, jobs))


def describe_pull(r: Pulled) -> str:
    if r.first:
        return f"pulled revision {r.rev} into {r.root} ({len(r.taken)} files)"
    lines = [f"merged revision {r.rev} of the server into this folder"]
    if r.taken:
        lines.append(f"taken from the server ({len(r.taken)}): " + ", ".join(r.taken[:20]) + (" ..." if len(r.taken) > 20 else ""))
    if r.kept:
        lines.append(f"kept mine, changed only here ({len(r.kept)}): " + ", ".join(r.kept[:20]))
    if r.conflicts:
        lines.append(f"CHANGED IN BOTH PLACES ({len(r.conflicts)}): mine stays, the server's is next to it:")
        lines += [f"  {p}  <->  {p}.server" for p in r.conflicts]
        lines.append("merge each pair into the file, delete the .server copy, `tadam check`, then push")
    if r.removed:
        lines.append(f"removed on the server, so moved out of the folder ({len(r.removed)}): " + ", ".join(r.removed)
                     + f"\n  (they are in {r.moved_to}; nothing is lost)")
    if r.kept_removed:
        lines.append("removed on the server but changed here, kept: " + ", ".join(r.kept_removed))
    if len(lines) == 1:
        lines.append("nothing to change: the folder already had everything")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ diff

def _load_side(root: Path, rev: str | None, api: Api | None) -> tuple:
    """(label, manifest, read(path) -> object|None) of one side of a diff: 'local', a revision kept here, or 'server'."""
    root = Path(root)
    if rev == "local":
        man = folder.scan(root).manifest

        def read_local(p):
            data, _ = read_json(root / p)
            return data
        return "this folder", man, read_local
    if rev == "server":
        if api is None:
            raise SyncError("no studio key: `tadam login` (or `tadam diff <rev>` with a revision kept here)")
        try:
            res = api.get(f"/api/studio/worlds/{world_slug(root)}/pull")
        except ApiError as e:
            raise SyncError(f"the server refused: {e}") from None
        man, links = res.get("manifest") or {}, res.get("files") or {}
        cache: dict[str, object] = {}

        def read_server(p):
            if p not in cache:
                m = man.get(p)
                cache[p] = json.loads(_fetch(api, links[p], m, p).decode("utf-8")) if m and p in links else None
            return cache[p]
        return f"server rev {res.get('rev')}", man, read_server
    snap = _state(root) / "revs" / str(rev)
    man, _ = read_json(snap / "manifest.json")
    if not isinstance(man, dict):
        have = sorted((int(d.name) for d in (_state(root) / "revs").glob("*") if d.name.isdigit()), reverse=True) \
            if (_state(root) / "revs").is_dir() else []
        raise SyncError(f"this folder has not seen revision {rev} (it keeps the revisions it pushed or pulled: "
                        f"{', '.join(map(str, have)) or 'none yet'}); the server answers only its latest")

    def read_snap(p):
        data, _ = read_json(snap / "files" / p)
        return data
    return f"rev {rev}", man, read_snap


def _fields(a: object, b: object) -> list[str]:
    if not isinstance(a, dict) or not isinstance(b, dict):
        return ["(whole)"]
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def _keyed(items: list, key: str) -> dict:
    return {x[key]: x for x in items if isinstance(x, dict) and isinstance(x.get(key), str)}


def script_diff(old: object, new: object) -> dict:
    """Shots by id and steps by key: added / removed / changed (with the fields that changed). Pure."""
    o = old if isinstance(old, dict) else {}
    n = new if isinstance(new, dict) else {}
    out: dict = {}
    os_, ns = _keyed(o.get("shots") or [], "id"), _keyed(n.get("shots") or [], "id")
    out["shots"] = {"added": [k for k in ns if k not in os_], "removed": [k for k in os_ if k not in ns],
                    "changed": {k: _fields(os_[k], ns[k]) for k in ns if k in os_ and os_[k] != ns[k]}}
    old_order, new_order = [k for k in os_ if k in ns], [k for k in ns if k in os_]
    if old_order != new_order:
        out["shots"]["order"] = True

    def steps(s):
        res = {}
        for hero, lst in (s.get("roles") or {}).items():
            for st in lst if isinstance(lst, list) else []:
                if isinstance(st, dict) and isinstance(st.get("key"), str):
                    res[st["key"]] = {**st, "_hero": hero}
        return res
    ost, nst = steps(o), steps(n)
    out["steps"] = {"added": [k for k in nst if k not in ost], "removed": [k for k in ost if k not in nst],
                    "changed": {k: _fields(ost[k], nst[k]) for k in nst if k in ost and ost[k] != nst[k]}}
    out["cast"] = _fields(o.get("cast") or {}, n.get("cast") or {}) if o.get("cast") != n.get("cast") else []
    out["film"] = _fields(o.get("film") or {}, n.get("film") or {}) if o.get("film") != n.get("film") else []
    other = sorted(k for k in set(o) | set(n) if k not in ("shots", "roles", "cast", "film") and o.get(k) != n.get(k))
    out["other"] = other
    return out


def diff(root: Path, a: str, b: str, api: Api | None) -> dict:
    """What changed from side `a` to side `b` ('server', 'local' or a revision number)."""
    la, ma, ra = _load_side(root, a, api)
    lb, mb, rb = _load_side(root, b, api)
    files = {"added": sorted(p for p in mb if p not in ma), "removed": sorted(p for p in ma if p not in mb),
             "changed": sorted(p for p in mb if p in ma and ma[p]["sha256"] != mb[p]["sha256"])}
    scripts = {}
    for p in sorted(set(files["changed"]) | set(files["added"]) | set(files["removed"])):
        if p.startswith("episodes/") and p.endswith("/script.json"):
            sd = script_diff(ra(p) if p in ma else None, rb(p) if p in mb else None)
            scripts[p.split("/")[1]] = sd
    return {"from": la, "to": lb, "files": files, "episodes": scripts}


def describe_diff(d: dict) -> str:
    f = d["files"]
    lines = [f"{d['from']}  ->  {d['to']}"]
    if not any(f.values()):
        lines.append("no differences")
        return "\n".join(lines)
    for k, mark in (("added", "+"), ("changed", "~"), ("removed", "-")):
        for p in f[k]:
            lines.append(f"  {mark} {p}")
    for n, sd in sorted(d["episodes"].items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        lines.append(f"episode {n}, script:")
        for what in ("shots", "steps"):
            x = sd[what]
            for k in x["added"]:
                lines.append(f"  + {what[:-1]} {k}")
            for k in x["removed"]:
                lines.append(f"  - {what[:-1]} {k}")
            for k, flds in x["changed"].items():
                lines.append(f"  ~ {what[:-1]} {k}: {', '.join(f for f in flds if f != '_hero')}")
            if x.get("order"):
                lines.append("  ~ the order of the shots")
        if sd["cast"]:
            lines.append(f"  ~ cast: {', '.join(sd['cast'])}")
        if sd["film"]:
            lines.append(f"  ~ film: {', '.join(sd['film'])}")
        if sd["other"]:
            lines.append(f"  ~ {', '.join(sd['other'])}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ status

def _title(t: object) -> str:
    if isinstance(t, dict):
        return str(t.get("ru") or t.get("en") or next(iter(t.values()), ""))
    return str(t or "")


def describe_status(s: dict, here: dict | None = None) -> str:
    """GET /api/studio/status for a person. `here`: this folder's link.json (its slug and revision), when in one."""
    lines = []
    worlds = s.get("worlds") or []
    if not worlds:
        lines.append("no worlds on the server yet: make one here and `tadam push`")
    for w in worlds:
        lp = w.get("lastPush") or {}
        check = {True: "check ok", False: "check found errors", None: "not checked"}.get(lp.get("ok"))
        lines.append(f"world {w.get('slug')} «{_title(w.get('title'))}»: {w.get('status')}, revision {w.get('rev') or '-'}"
                     + (f" (last push {lp.get('at', '')[:16].replace('T', ' ')}, {check})" if lp else ""))
        if here and here.get("slug") == w.get("slug") and w.get("rev") and here.get("rev") != w.get("rev"):
            lines.append(f"  this folder is at revision {here.get('rev')}, the server at {w.get('rev')}: `tadam pull`")
        for e in w.get("episodes") or []:
            sub = e.get("submission")
            line = f"  episode {e.get('number')} «{_title(e.get('title'))}»: {e.get('status')}"
            if e.get("draft"):
                line += ", a pushed revision waits for approval"
            if sub:
                line += f"; submission {sub.get('kind')} {sub.get('status')}"
            lines.append(line)
            miss = e.get("missing") or []
            if miss:
                lines.append("    before it can be submitted:")
                lines += [f"      - {m.get('message')} [{m.get('code')}]" for m in miss]
    subs = s.get("submissions") or []
    if subs:
        lines.append("open submissions:")
        lines += [f"  {x.get('id')}: {x.get('kind')} {x.get('world')}" + (f" episode {x['episode']}" if x.get("episode") else "")
                  + f", {x.get('status')} since {str(x.get('createdAt', ''))[:10]}" for x in subs]
    unread = int(s.get("unread") or 0)
    lines.append(f"unread remarks and notices: {unread}")
    for n in s.get("notifications") or []:
        lines.append(f"  [{str(n.get('at', ''))[:16].replace('T', ' ')}] {n.get('text')}")
    return "\n".join(lines)


def find_root(start: str | None) -> Path | None:
    from tadam.world import find_world
    try:
        return find_world(start)
    except WorldError:
        return None


__all__ = ["push", "pull", "diff", "merge_plan", "script_diff", "describe_push", "describe_pull", "describe_diff",
           "describe_status", "SyncError", "World"]
