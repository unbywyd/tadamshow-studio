"""THE NARRATION BRIDGE, the kit's side (studio-tz 3.4 «Мост озвучки»): the local player asks the server to speak
a narration (POST /api/studio/tts: the text and the voice key → an mp3 link and its fingerprint), so nobody has
to install a TTS. The voice is the one the film will have; the server keeps the file and reuses it.

- Only with a studio key: TADAM_STUDIO_KEY or the one `tadam login` stored (and TADAM_STUDIO_URL for another
  server than the default). With no key, the narration stays subtitles and one line says so.
- Only the narration's text and the voice key are sent (and the effect, when it is not "none": it is part of the
  voice). Nothing else of the world ever leaves the computer here.
- Cached in the world's .tadam/tts/<fingerprint>.mp3 by the fingerprint of text + voice + effect, the very name the
  server gives the file (apps/api services/studio/resolve.ts ttsFingerprint); a cached narration is never asked for
  again, so it costs no limit and works offline.
- 429 (the daily or per-minute limit): a short wait is waited out once; a long one is reported with when to try
  again, and the narration stays subtitles.
- The key goes only to the studio server. The mp3 link the server answers with is fetched without it.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tadam import __version__

DEFAULT_URL = "https://api.tadamshow.com"
KEY_ENV, URL_ENV = "TADAM_STUDIO_KEY", "TADAM_STUDIO_URL"
WAIT_SHORT = 15.0           # a 429 asking to wait this long or less is waited out (once)
POLL_EVERY = 2.0            # seconds between asks about a voicing still in the queue
POLL_FOR = 180.0            # ...and how long at most
TIMEOUT = 75.0              # one request (the server waits up to 55 s for a new voicing before it answers 202)
MAX_MP3 = 20 * 1024 * 1024


class TtsError(Exception):
    """The narration could not be had; the message says why in plain words."""


class RateLimited(TtsError):
    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class Link:
    url: str      # the studio server, e.g. https://api.tadamshow.com
    key: str      # the studio key (never printed)

    def __repr__(self) -> str:          # (so a log of the link never shows the key)
        return f"Link(url={self.url!r}, key=<hidden>)"


def link_from_env(environ=None) -> Link | None:
    """TADAM_STUDIO_KEY, else the key `tadam login` stored for this server (tadam.link)."""
    from tadam import link
    got = link.current(environ)
    return Link(got.url, got.key) if got else None


def fingerprint(text: str, voice: str, fx: str = "none") -> str:
    """sha-256 (32 hex) of {text, voice, fx} as JSON.stringify writes it: the server's ttsFingerprint."""
    data = json.dumps({"text": str(text).strip(), "voice": voice, "fx": fx or "none"}, ensure_ascii=False,
                      separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:32]


def cache_file(cache_dir: Path, fp: str) -> Path:
    return Path(cache_dir) / f"{fp}.mp3"


def _safe_url(url: str) -> bool:
    u = urllib.parse.urlsplit(url)
    if u.scheme == "https" and u.hostname:
        return True
    return u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1")     # (a server on this computer)


def _error_of(body: bytes) -> tuple[str, dict]:
    try:
        e = json.loads(body.decode("utf-8")).get("error") or {}
        return str(e.get("message") or ""), e.get("issues") if isinstance(e.get("issues"), dict) else {}
    except (ValueError, AttributeError):
        return "", {}


class Client:
    """POST /api/studio/tts and GET /api/studio/tts/:jobId. `opener(request, timeout)` is urllib's urlopen
    (a test passes its own); `sleep` is time.sleep."""

    def __init__(self, link: Link, opener: Callable | None = None, sleep: Callable[[float], None] = time.sleep):
        if not _safe_url(link.url):
            raise TtsError(f"{URL_ENV} must be an https address (or http on this computer): {link.url}")
        self.link = link
        self.open = opener or urllib.request.urlopen
        self.sleep = sleep

    def _call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.link.url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.link.key}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": f"tadam/{__version__}"})
        try:
            with self.open(req, timeout=TIMEOUT) as r:
                return r.status, json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read() if e.fp is not None else b""
            msg, issues = _error_of(raw)
            if e.code == 429:
                retry = issues.get("retryAfter")
                if not isinstance(retry, (int, float)):
                    try:
                        retry = float(e.headers.get("Retry-After", "60"))
                    except (TypeError, ValueError):
                        retry = 60.0
                raise RateLimited(msg or "too many voicings", float(retry)) from None
            if e.code in (401, 403):
                raise TtsError(f"the studio key was refused ({e.code}): {msg or 'run tadam login'}") from None
            todo = issues.get("todo")
            raise TtsError(f"the server said {e.code}: {msg or 'error'}" + (f" ({todo})" if todo else "")) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise TtsError(f"the studio server cannot be reached ({getattr(e, 'reason', e)})") from None
        except ValueError:
            raise TtsError("the studio server answered something that is not JSON") from None

    def voice(self, text: str, voice: str, fx: str = "none") -> dict:
        """The server's answer once the voicing is done: {status: done, url, fingerprint, seconds, ...}."""
        body = {"text": str(text).strip(), "voice": voice}
        if fx and fx != "none":
            body["fx"] = fx
        for attempt in range(2):
            try:
                code, res = self._call("POST", "/api/studio/tts", body)
                break
            except RateLimited as e:
                if attempt == 0 and e.retry_after <= WAIT_SHORT:
                    self.sleep(e.retry_after)
                    continue
                raise
        waited = 0.0
        while res.get("status") == "pending":
            job = res.get("jobId")
            if not isinstance(job, str) or not job or waited >= POLL_FOR:
                raise TtsError("the voicing is still in the server's queue: try again in a few minutes")
            self.sleep(POLL_EVERY)
            waited += POLL_EVERY
            code, res = self._call("GET", "/api/studio/tts/" + urllib.parse.quote(job, safe=""))
        if res.get("status") != "done" or not res.get("url"):
            raise TtsError(f"the voicing failed: {res.get('error') or res.get('status') or 'no file'}")
        return res

    def download(self, url: str, out: Path) -> Path:
        """The mp3 from the link the server gave (a short-lived storage link: the key is NOT sent there)."""
        if not _safe_url(url):
            raise TtsError("the server gave a link that is not https")
        req = urllib.request.Request(url, headers={"User-Agent": f"tadam/{__version__}"})
        try:
            with self.open(req, timeout=TIMEOUT) as r:
                data = r.read(MAX_MP3 + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise TtsError(f"the narration file cannot be downloaded ({getattr(e, 'reason', e)})") from None
        if len(data) > MAX_MP3 or len(data) < 16:
            raise TtsError("the narration file is too large or empty")
        if not (data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)):
            raise TtsError("the narration file is not an mp3")
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(out)
        return out


def narration(text: str, voice: str, fx: str, cache_dir: Path, link: Link | None,
              client: Client | None = None) -> tuple[Path | None, str]:
    """(the mp3, "") or (None, why there is none). From the cache when it is there; asked for only with a link."""
    fp = fingerprint(text, voice, fx)
    f = cache_file(cache_dir, fp)
    if f.is_file() and f.stat().st_size > 0:
        return f, ""
    if link is None:
        return None, "no studio key"
    try:
        c = client or Client(link)
        res = c.voice(text, voice, fx)
        if res.get("fingerprint") not in (None, fp):
            # (the server names the file by its own fingerprint: a change of the rule on one side)
            raise TtsError("the server's fingerprint of this narration differs from the kit's: update the kit")
        return c.download(str(res["url"]), f), ""
    except RateLimited as e:
        return None, f"{e} — try again in {int(e.retry_after + 0.999)} s"
    except TtsError as e:
        return None, str(e)
