"""WHAT THE PICTURES COST: the image model's prices per token, in ONE place, and the cost of the pictures a paid
command painted, worked out from the usage fields the API answers with (input and output tokens, text and image).

The kit paints at quality "medium" by default (`--quality low | medium | high` on `tadam hero make` and
`tadam set make`). OpenAI prices images PER TOKEN, not per picture, so a picture's price depends on its size, its
quality and the pictures sent with it. What was actually paid at medium (November 2026, gpt-image-2.5-flare,
1024x1536):

    a portrait          about $0.011
    a pattern sheet     about $0.038   (the pattern and the portrait go with it as input pictures)
    a hero              about $0.05    (portrait + sheet; each repainted sheet, at most 2, about $0.04 more)
    a set               about $0.04-0.1 (a room and one picture per piece)
    at "high"           several times more: one high picture was about $0.25

The per-token prices below reproduce those bills (they were fitted to them; OpenAI's price list is per token and may
change: update the numbers and the date here, and nowhere else). A cost the kit prints is an ESTIMATE from them.
"""
from __future__ import annotations

PRICES_DATE = "2026-11"
MODEL = "gpt-image-2.5-flare"
# US dollars per 1 million tokens
USD_PER_MILLION = {
    "text_in": 5.0,         # the prompt
    "image_in": 8.0,        # pictures sent with it (the pattern, the portrait, a style picture)
    "image_out": 30.0,      # the picture painted (a text output, rare, is counted at this rate too: an upper bound)
}
OBSERVED = {"portrait": 0.011, "sheet": 0.038, "hero": 0.05, "set": (0.04, 0.1), "high_picture": 0.25}
DEFAULT_QUALITY = "medium"


def _num(x: object) -> int:
    return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else 0


def tokens(usage: object) -> dict | None:
    """{text_in, image_in, image_out} of one call's usage (the API's usage object as a dict), or None."""
    if not isinstance(usage, dict):
        return None
    ind = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    outd = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
    tin, iin = _num(ind.get("text_tokens")), _num(ind.get("image_tokens"))
    if not (tin or iin):
        tin = _num(usage.get("input_tokens"))
    out = _num(outd.get("image_tokens")) + _num(outd.get("text_tokens")) or _num(usage.get("output_tokens"))
    return {"text_in": tin, "image_in": iin, "image_out": out}


def cost(usage: object) -> float | None:
    """US dollars of one call, from its usage; None when the API gave no usage."""
    t = tokens(usage)
    if t is None:
        return None
    return sum(t[k] * USD_PER_MILLION[k] for k in t) / 1_000_000


def summary(calls: list) -> dict:
    """{pictures, tokens_in, tokens_out, usd (None when no call reported its usage), unknown (calls without usage)}."""
    out = {"pictures": 0, "tokens_in": 0, "tokens_out": 0, "usd": None, "unknown": 0}
    for c in calls or []:
        if not isinstance(c, dict):
            continue
        out["pictures"] += 1
        t = tokens(c.get("usage"))
        if t is None:
            out["unknown"] += 1
            continue
        out["tokens_in"] += t["text_in"] + t["image_in"]
        out["tokens_out"] += t["image_out"]
        out["usd"] = (out["usd"] or 0.0) + cost(c.get("usage"))
    return out


def describe(calls: list, quality: str | None = None) -> str:
    """One line for the person: what was painted and what it cost (an estimate from the usage)."""
    s = summary(calls)
    q = f" at {quality} quality" if quality else ""
    line = f"painted {s['pictures']} picture(s){q}"
    if s["usd"] is not None:
        line += (f": {s['tokens_in']:,} input + {s['tokens_out']:,} output tokens = about ${s['usd']:.3f} "
                 f"(per-token prices of {PRICES_DATE} in tadam/prices.py; they may change)")
    if s["unknown"]:
        line += f"; the API reported no usage for {s['unknown']} of them (no cost worked out)"
    return line
