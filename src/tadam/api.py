"""The studio API client (/api/studio/*, docs: the server's contracts, schema/*.json): JSON calls with the studio key,
and the file transfers to and from the short-lived storage links the server hands out (sent WITHOUT the key).

Errors come back as ApiError with the server's code, message and, for studio errors, `reason` and `todo` (what to
do: "run tadam pull first"). Only https addresses are used (http only for a server on this computer).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from tadam import __version__
from tadam.link import KEY_ENV, URL_ENV, Link

TIMEOUT = 120.0
TRIES = 3                  # a file transfer is tried this many times (network blips, a 5xx of the storage)
BACKOFF = 1.5


class ApiError(Exception):
    """The server said no (or could not be reached). `status` 0 = no answer."""

    def __init__(self, status: int, code: str, message: str, issues: object = None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.issues = issues if isinstance(issues, dict) else {}
        self.reason = str(self.issues.get("reason") or "")
        self.todo = str(self.issues.get("todo") or "")

    def __str__(self) -> str:
        return self.message + (f" ({self.todo})" if self.todo else "")


def safe_url(url: str) -> bool:
    u = urllib.parse.urlsplit(url)
    if u.scheme == "https" and u.hostname:
        return True
    return u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1")     # (a server on this computer)


def no_key() -> ApiError:
    return ApiError(0, "no_key", f"no studio key: run `tadam login` (or set {KEY_ENV})")


class Api:
    """`opener(request, timeout)` is urllib's urlopen (a test passes its own); `sleep` is time.sleep."""

    def __init__(self, link: Link, opener: Callable | None = None, sleep: Callable[[float], None] = time.sleep):
        if not safe_url(link.url):
            raise ApiError(0, "bad_url", f"{URL_ENV} must be an https address (or http on this computer): {link.url}")
        self.link = link
        self.open = opener or urllib.request.urlopen
        self.sleep = sleep

    # ------------------------------------------------------------------ JSON with the key
    def call(self, method: str, path: str, body: dict | None = None, timeout: float = TIMEOUT) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": f"tadam/{__version__}"}
        if self.link.key:                    # (join, verify and the rules are asked without a key)
            headers["Authorization"] = f"Bearer {self.link.key}"
        req = urllib.request.Request(self.link.url + path, data=data, method=method, headers=headers)
        try:
            with self.open(req, timeout=timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raw = e.read() if e.fp is not None else b""
            try:
                err = json.loads(raw.decode("utf-8")).get("error") or {}
            except (ValueError, AttributeError):
                err = {}
            msg = str(err.get("message") or f"HTTP {e.code}")
            if e.code == 401 and self.link.key:
                msg = f"the studio key was refused: {msg}"
            raise ApiError(e.code, str(err.get("code") or "error"), msg, err.get("issues")) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ApiError(0, "unreachable", f"the studio server cannot be reached ({getattr(e, 'reason', e)})") from None
        try:
            out = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            raise ApiError(0, "not_json", "the studio server answered something that is not JSON") from None
        if not isinstance(out, dict):
            raise ApiError(0, "not_json", "the studio server answered something that is not an object")
        return out

    def get(self, path: str) -> dict:
        return self.call("GET", path)

    def post(self, path: str, body: dict) -> dict:
        return self.call("POST", path, body)

    # ------------------------------------------------------------------ storage links (no key)
    def _transfer(self, req: urllib.request.Request, what: str, limit: int | None = None) -> bytes:
        last = ""
        for attempt in range(TRIES):
            try:
                with self.open(req, timeout=TIMEOUT) as r:
                    return r.read() if limit is None else r.read(limit + 1)
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}"
                if e.code < 500 and e.code not in (408, 429):
                    break                       # (a refused link does not get better by asking again)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = str(getattr(e, "reason", e))
            if attempt + 1 < TRIES:
                self.sleep(BACKOFF * (attempt + 1))
        raise ApiError(0, "transfer", f"{what}: {last}")

    def upload(self, url: str, data: bytes, headers: dict) -> None:
        if not safe_url(url):
            raise ApiError(0, "bad_url", "the server gave an upload link that is not https")
        h = {str(k): str(v) for k, v in (headers or {}).items() if str(k).lower() != "authorization"}
        req = urllib.request.Request(url, data=data, method="PUT", headers=h)
        self._transfer(req, "upload failed")

    def download(self, url: str, limit: int) -> bytes:
        if not safe_url(url):
            raise ApiError(0, "bad_url", "the server gave a download link that is not https")
        req = urllib.request.Request(url, headers={"User-Agent": f"tadam/{__version__}"})
        data = self._transfer(req, "download failed", limit)
        if len(data) > limit:
            raise ApiError(0, "too_large", "a downloaded file is larger than the manifest says")
        return data
