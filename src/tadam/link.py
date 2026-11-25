"""THE STUDIO KEY and the server it belongs to (`tadam login` / `tadam logout`).

- The server: https://api.tadamshow.com, or TADAM_STUDIO_URL (a test server, the owner's dev server).
- The key (`tds_…`, made in the cabinet or by `tadam join`): TADAM_STUDIO_KEY when it is set (e.g. by
  `skey run --only TADAM_STUDIO_KEY -- tadam push`), else the one `tadam login` stored for this server.
- Stored in the person's own config folder, never inside a world folder (a world folder is pushed and may be shared):
      Windows  %APPDATA%\\tadam\\credentials.json
      macOS    ~/Library/Application Support/tadam/credentials.json
      Linux    $XDG_CONFIG_HOME/tadam/credentials.json (~/.config/tadam/...)
  (TADAM_CONFIG_DIR moves it, for tests). On macOS and Linux the file is readable by its owner only (0600) and its
  folder 0700. `tadam logout` removes the key.
- The key is never printed, never logged, never written anywhere else; it goes only to the studio server.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_URL = "https://api.tadamshow.com"
KEY_ENV, URL_ENV, CONFIG_ENV = "TADAM_STUDIO_KEY", "TADAM_STUDIO_URL", "TADAM_CONFIG_DIR"
FILE = "credentials.json"


@dataclass(frozen=True)
class Link:
    url: str      # the studio server, e.g. https://api.tadamshow.com
    key: str      # the studio key (never printed)
    source: str = "env"    # env | stored

    def __repr__(self) -> str:          # (so a log of the link never shows the key)
        return f"Link(url={self.url!r}, key=<hidden>, source={self.source!r})"

    __str__ = __repr__


def config_dir(environ=None, platform: str | None = None) -> Path:
    env = os.environ if environ is None else environ
    forced = (env.get(CONFIG_ENV) or os.environ.get(CONFIG_ENV) or "").strip()
    if forced:
        return Path(forced).expanduser()
    plat = platform or sys.platform
    home = Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
    if plat.startswith("win"):
        base = env.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Roaming") / "tadam"
    if plat == "darwin":
        return home / "Library" / "Application Support" / "tadam"
    xdg = (env.get("XDG_CONFIG_HOME") or "").strip()
    return (Path(xdg) if xdg else home / ".config") / "tadam"


def server_url(environ=None) -> str:
    env = os.environ if environ is None else environ
    return ((env.get(URL_ENV) or "").strip() or DEFAULT_URL).rstrip("/")


def _read(environ=None) -> dict:
    f = config_dir(environ) / FILE
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def stored_key(url: str, environ=None) -> str | None:
    s = (_read(environ).get("servers") or {}).get(url) or {}
    k = s.get("key") if isinstance(s, dict) else None
    return k.strip() if isinstance(k, str) and k.strip() else None


def current(environ=None) -> Link | None:
    """The key to use now: TADAM_STUDIO_KEY, else the stored one for this server; None when there is neither."""
    env = os.environ if environ is None else environ
    url = server_url(env)
    key = (env.get(KEY_ENV) or "").strip()
    if key:
        return Link(url, key, "env")
    k = stored_key(url, env)
    return Link(url, k, "stored") if k else None


def _write_private(path: Path, text: str) -> None:
    """Write a file only its owner can read (POSIX 0600; on Windows the user's own profile folder)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
    tmp = path.with_name(path.name + ".part")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    if os.name == "posix":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def store(url: str, key: str, who: dict | None = None, environ=None) -> Path:
    """Keep the key for this server (replacing the one before)."""
    data = _read(environ)
    servers = data.get("servers") if isinstance(data.get("servers"), dict) else {}
    servers[url] = {"key": key, **({"user": who} if who else {})}
    data = {"version": 1, "servers": servers}
    f = config_dir(environ) / FILE
    _write_private(f, json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    return f


def forget(url: str, environ=None) -> bool:
    """Remove the stored key of this server. True when there was one."""
    data = _read(environ)
    servers = data.get("servers") if isinstance(data.get("servers"), dict) else {}
    had = servers.pop(url, None) is not None
    f = config_dir(environ) / FILE
    if not servers:
        f.unlink(missing_ok=True)
    elif had:
        _write_private(f, json.dumps({"version": 1, "servers": servers}, ensure_ascii=False, indent=1) + "\n")
    return had


def mask_email(email: object) -> str:
    """a***@example.com: enough to recognise one's own account, not the address itself."""
    if not isinstance(email, str) or "@" not in email:
        return "?"
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


KEY_SHAPE = re.compile(r"^tds_[a-z0-9]{8}_[A-Za-z0-9_-]{20,200}$")     # the server's studio key (services/auth.ts)


def looks_like_key(key: str) -> bool:
    return bool(KEY_SHAPE.match(key.strip()))
