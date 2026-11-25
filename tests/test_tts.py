"""The narration bridge's client (tadam.tts) against a fake studio server on this computer: what is sent (only the
text and the voice key), the key only to the studio server, the cache by fingerprint, waiting in the queue, the
limits (429), no key, no server."""
from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tadam import episode, tts
from tadam.world import World, read_json, write_json

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 64
KEY = "test-studio-key-not-real"


class Fake:
    """A studio server: POST /api/studio/tts, GET /api/studio/tts/<job>, GET /files/<fp>.mp3 (the 'storage')."""

    def __init__(self):
        self.calls = []                 # (method, path, headers, body)
        self.answers = []               # what POST answers, in turn: (code, body); then "done"
        self.pending_polls = 0
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json", headers=None):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                fake.calls.append(("POST", self.path, dict(self.headers), body))
                if fake.answers:
                    code, b, *h = fake.answers.pop(0)
                    return self._send(code, b, headers=h[0] if h else None)
                return self._send(200, fake.done(body))

            def do_GET(self):
                fake.calls.append(("GET", self.path, dict(self.headers), None))
                if self.path.startswith("/files/"):
                    return self._send(200, MP3, "audio/mpeg")
                if self.path.startswith("/api/studio/tts/"):
                    if fake.pending_polls > 0:
                        fake.pending_polls -= 1
                        return self._send(200, fake.pending())
                    return self._send(200, fake.done(fake.last_body))
                return self._send(404, {"error": {"code": "not_found", "message": "no"}})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.last_body = {}
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def done(self, body):
        fp = tts.fingerprint(body["text"], body["voice"], body.get("fx", "none"))
        return {"status": "done", "fingerprint": fp, "cached": False, "url": f"{self.url}/files/{fp}.mp3",
                "expiresAt": "2026-11-25T12:00:00.000Z", "jobId": None, "seconds": 2.1, "error": None}

    def pending(self):
        return {"status": "pending", "fingerprint": "0" * 32, "cached": False, "url": None, "expiresAt": None,
                "jobId": "job-1", "seconds": None, "error": None}

    def close(self):
        self.srv.shutdown()


@pytest.fixture
def fake():
    f = Fake()
    yield f
    f.close()


def link(f):
    return tts.Link(f.url, KEY)


def test_fingerprint_is_the_servers():
    # JSON.stringify({text: text.trim(), voice, fx}) through sha-256, first 32 hex: values computed by Node
    assert tts.fingerprint('А луна была рядом. "Да"\n', "eduard") == "109e258b971623362d27581e473dace6"
    assert tts.fingerprint("Hello", "eduard", "radio") == "8fd665fd387645ea2b98040bd66a4859"
    assert tts.fingerprint("Hello", "eduard", "") == tts.fingerprint(" Hello ", "eduard", "none")


def test_voiced_once_then_from_the_cache(fake, tmp_path):
    f, why = tts.narration("Однажды ночью.", "eduard", "none", tmp_path, link(fake), tts.Client(link(fake)))
    assert why == "" and f == tmp_path / f"{tts.fingerprint('Однажды ночью.', 'eduard')}.mp3"
    assert f.read_bytes() == MP3
    post, get = fake.calls
    # only the text and the voice key go out; the key goes to the studio server only, not to the storage link
    assert post[0] == "POST" and post[1] == "/api/studio/tts" and post[3] == {"text": "Однажды ночью.", "voice": "eduard"}
    assert post[2]["Authorization"] == f"Bearer {KEY}"
    assert get[1].startswith("/files/") and "Authorization" not in get[2]
    # again: from the cache, nothing asked (no limit spent, works offline)
    fake.calls.clear()
    f2, _ = tts.narration("Однажды ночью.", "eduard", "none", tmp_path, None)
    assert f2 == f and fake.calls == []


def test_the_effect_is_sent_only_when_there_is_one(fake, tmp_path):
    tts.narration("Раз.", "eduard", "radio", tmp_path, link(fake), tts.Client(link(fake)))
    assert fake.calls[0][3] == {"text": "Раз.", "voice": "eduard", "fx": "radio"}


def test_waiting_in_the_queue(fake, tmp_path):
    fake.answers = [(202, fake.pending())]
    fake.pending_polls = 2
    fake.last_body = {"text": "Два.", "voice": "eduard"}
    slept = []
    c = tts.Client(link(fake), sleep=slept.append)
    f, why = tts.narration("Два.", "eduard", "none", tmp_path, link(fake), c)
    assert why == "" and f.is_file()
    assert [m for m, p, *_ in fake.calls] == ["POST", "GET", "GET", "GET", "GET"]
    assert fake.calls[1][1] == "/api/studio/tts/job-1" and fake.calls[1][2]["Authorization"] == f"Bearer {KEY}"
    assert slept == [tts.POLL_EVERY] * 3


def test_a_short_limit_is_waited_out_once(fake, tmp_path):
    err = {"error": {"code": "too_many_requests", "message": "11 voicings in the last minute",
                     "issues": {"reason": "tts_per_minute", "todo": "wait 7 s", "retryAfter": 7}}}
    fake.answers = [(429, err)]
    slept = []
    f, why = tts.narration("Три.", "eduard", "none", tmp_path, link(fake), tts.Client(link(fake), sleep=slept.append))
    assert why == "" and f.is_file() and slept == [7]


def test_a_long_limit_is_reported(fake, tmp_path):
    err = {"error": {"code": "too_many_requests", "message": "20 voicings today: at most 20",
                     "issues": {"reason": "tts_per_day", "todo": "try again in 5 h", "retryAfter": 18000}}}
    fake.answers = [(429, err)]
    slept = []
    f, why = tts.narration("Четыре.", "eduard", "none", tmp_path, link(fake), tts.Client(link(fake), sleep=slept.append))
    assert f is None and "at most 20" in why and "try again in 18000 s" in why and slept == []
    assert not list(tmp_path.iterdir())
    # no retryAfter in the body: the Retry-After header
    fake.answers = [(429, {"error": {"code": "too_many_requests", "message": "slow down"}}, {"Retry-After": "120"})]
    _, why = tts.narration("Пять.", "eduard", "none", tmp_path, link(fake), tts.Client(link(fake)))
    assert "try again in 120 s" in why


def test_refusals_in_plain_words(fake, tmp_path):
    fake.answers = [(401, {"error": {"code": "unauthorized", "message": "a staff API key does not work here"}})]
    _, why = tts.narration("Шесть.", "eduard", "none", tmp_path, link(fake), tts.Client(link(fake)))
    assert "studio key was refused (401)" in why
    fake.answers = [(400, {"error": {"code": "bad_request", "message": 'no voice "x" on the server',
                                     "issues": {"todo": "use one of: eduard"}}})]
    _, why = tts.narration("Шесть.", "x", "none", tmp_path, link(fake), tts.Client(link(fake)))
    assert 'no voice "x"' in why and "use one of: eduard" in why
    fake.answers = [(200, {"status": "failed", "fingerprint": "0" * 32, "url": None, "error": "TTS crashed"})]
    _, why = tts.narration("Семь.", "eduard", "none", tmp_path, link(fake), tts.Client(link(fake)))
    assert "TTS crashed" in why


def test_a_different_fingerprint_is_not_taken(fake, tmp_path):
    fake.answers = [(200, {**fake.done({"text": "Восемь.", "voice": "eduard"}), "fingerprint": "f" * 32})]
    f, why = tts.narration("Восемь.", "eduard", "none", tmp_path, link(fake), tts.Client(link(fake)))
    assert f is None and "fingerprint" in why


def test_no_key_and_no_server(tmp_path):
    assert tts.narration("Девять.", "eduard", "none", tmp_path, None) == (None, "no studio key")
    assert tts.link_from_env({}) is None
    lk = tts.link_from_env({tts.KEY_ENV: " zq-secret-zq ", tts.URL_ENV: "https://example.test/"})
    assert lk == tts.Link("https://example.test", "zq-secret-zq") and "zq-secret" not in repr(lk)
    assert tts.link_from_env({tts.KEY_ENV: "k"}).url == tts.DEFAULT_URL
    # a closed port: offline
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    lk = tts.Link(f"http://127.0.0.1:{port}", KEY)
    f, why = tts.narration("Девять.", "eduard", "none", tmp_path, lk)
    assert f is None and "cannot be reached" in why
    # the key never goes over plain http to another computer
    with pytest.raises(tts.TtsError, match="https"):
        tts.Client(tts.Link("http://example.test", KEY))


def test_the_episode_uses_the_bridge(world, fake, monkeypatch):
    """With a studio key the narration is voiced (and mixed); its shot lasts as long as the voice."""
    monkeypatch.setattr(episode.mix, "duration", lambda p: 2.5 if str(p).endswith(".mp3") else None)
    w = World(world)
    ep = episode.build(w, "1", link=link(fake), client=tts.Client(link(fake)))
    n = ep.shots[2].narration
    assert n["file"] and n["seconds"] == 2.5 and not ep.shots[2].subs
    assert ep.shots[2].seconds == 2.0          # (the shot says "seconds": 2 itself)
    s, _ = read_json(w.episode_dir("1") / "script.json")
    del s["shots"][2]["seconds"]
    write_json(w.episode_dir("1") / "script.json", s)
    ep = episode.build(w, "1", link=None)      # (from the cache now: no key needed)
    assert ep.shots[2].seconds == round(0.5 + 2.5 + 0.7, 2) and not ep.notes
    snd = episode.sounds(ep)[2]
    assert snd.narrator["file"] == n["file"] and snd.narrator["at"] == 0.5
    # --no-voice: subtitles, nothing asked
    fake.calls.clear()
    ep = episode.build(w, "1", link=link(fake), voice=False)
    assert ep.shots[2].subs[0]["kind"] == "narration" and fake.calls == []
