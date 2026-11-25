"""The OpenAI image API (the official `openai` SDK).

The key comes from ONE place: the environment variable OPENAI_API_KEY (the editor's own key; a secret manager such
as skey can put it there for one command). There is no fallback to any file. The value is never printed, logged or
written anywhere: it goes straight into the SDK client.

Every generator of the kit calls `call()`. Tests replace the client with `set_client()`: nothing in the test suite
ever reaches the network.
"""
from __future__ import annotations

import base64
import contextlib
import inspect
import os
import time
from pathlib import Path
from typing import Any, Callable, Sequence

DEFAULT_MODEL = "gpt-image-2.5-flare"


class GenerationError(RuntimeError):
    """A generation could not be made: no key, or the API said no. The message never contains the key."""


def key() -> str:
    v = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not v or not v.isascii() or any(c.isspace() for c in v):
        raise GenerationError("no usable OPENAI_API_KEY in the environment: set your own OpenAI key there "
                              "(https://platform.openai.com/api-keys); `tadam doctor` checks it")
    return v


def _real_client() -> Any:
    from openai import OpenAI
    return OpenAI(api_key=key(), timeout=300, max_retries=2)


_factory: Callable[[], Any] = _real_client


def set_client(factory: Callable[[], Any] | None) -> Callable[[], Any]:
    """Replace how the client is made (tests). None puts the real one back. Returns the previous factory."""
    global _factory
    old = _factory
    _factory = factory or _real_client
    return old


def _split(fn: Callable, fields: dict) -> dict:
    """Arguments the SDK method knows go by name, the rest in extra_body (a newer API field an older SDK lacks)."""
    try:
        names = set(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        return dict(fields)
    known = {k: v for k, v in fields.items() if k in names}
    extra = {k: v for k, v in fields.items() if k not in names}
    if extra:
        known["extra_body"] = extra
    return known


def call(endpoint: str, fields: dict, images: Sequence[Path | str] | None = None) -> tuple[bytes, dict | None, float]:
    """One image: (png bytes, usage, seconds). endpoint is "generations" or "edits" (with reference images)."""
    key()                                       # no key: a clear error before anything is made or sent
    client = _factory()
    t0 = time.time()
    try:
        if images:
            with contextlib.ExitStack() as st:
                files = [st.enter_context(open(Path(p), "rb")) for p in images]
                fn = client.images.edit
                r = fn(image=files, **_split(fn, fields))
        else:
            fn = client.images.generate
            r = fn(**_split(fn, fields))
    except GenerationError:
        raise
    except Exception as e:                      # the SDK's errors carry the status and the API's words, not the key
        raise GenerationError(f"OpenAI images/{endpoint}: {e.__class__.__name__}: {str(e)[:500]}") from None
    try:
        png = base64.b64decode(r.data[0].b64_json)
    except (AttributeError, IndexError, TypeError, ValueError) as e:
        raise GenerationError(f"OpenAI images/{endpoint}: unexpected answer ({e.__class__.__name__})") from None
    usage = getattr(r, "usage", None)
    if usage is not None and hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    return png, usage, round(time.time() - t0, 1)
