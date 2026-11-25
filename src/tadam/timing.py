"""HOW LONG THINGS TAKE when nothing is recorded yet: the ONE place the kit estimates a line and a shot.

A line with no recording (the local player, frames, a draft film) lasts what a calm reader takes to say it; the
shot around it is cut the way the server cuts a shot around a recorded line, so a draft is as long as the film
will be, give or take the reader:

    speech  = max(words / WORDS_PER_SECOND, SHORTEST_SPEECH)
    piece   = LEAD + speech + TRAIL           the speaker's piece of the take (capped by the step's maxSeconds)
    shot    = piece + TAIL                    a shot with a line ("seconds" of the shot is not used then)

    narration shot = at + voice + NARRATION_TAIL     (voice: the narration file's length, or its speech estimate)
    any other shot = "seconds", or DEFAULT_SECONDS

LEAD, TRAIL and TAIL are the server's own defaults (apps/api services/film-logic.ts linePhrases: lead 0.4,
trail 0.25; services/film.ts timeline: tail 0.4); a shot's own "lead", "trail", "tail" win, as there.
NARRATION_TAIL is the lab's (tools/shots.py). Words are what has a letter or a digit in it.

The phrases of a line (where the mouth moves, what a camera cue { "phrase": N } waits for) are the speech cut into
the step's "phrases" parts, by its sentences where it has them, by words where it has not.
"""
from __future__ import annotations

import re

WORDS_PER_SECOND = 2.3      # a calm line, Russian or English
SHORTEST_SPEECH = 0.6       # even one word takes this long
LEAD = 0.4                  # before the words, in the speaker's piece (film-logic.ts linePhrases lead)
TRAIL = 0.25                # after them (linePhrases trail)
TAIL = 0.4                  # the shot goes on after the piece (film.ts timeline)
NARRATION_AT = 0.5          # the narrator starts this far into the shot (script schema default)
NARRATION_TAIL = 0.7        # ...and the shot goes on this long after the narration (tools/shots.py)
DEFAULT_SECONDS = 4.0       # a shot with no line, no narration and no "seconds" (film.ts timeline)
PHRASE_GAP = 0.3            # the breath between two phrases of one line


def words(text: object) -> int:
    return len([w for w in str(text or "").split() if any(c.isalnum() for c in w)])


def speech_seconds(text: object) -> float:
    """How long the words themselves take to say."""
    return max(words(text) / WORDS_PER_SECOND, SHORTEST_SPEECH)


def _num(x: object, default: float) -> float:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else default


def piece_seconds(text: object, lead: float = LEAD, trail: float = TRAIL, max_seconds: object = None) -> float:
    """The speaker's piece of the take for this line: the words with the air before and after them."""
    n = lead + speech_seconds(text) + trail
    if isinstance(max_seconds, (int, float)) and max_seconds > 0:
        n = min(n, float(max_seconds))
    return round(n, 2)


def line_shot_seconds(text: object, shot: dict | None = None, max_seconds: object = None) -> float:
    shot = shot or {}
    lead, trail = _num(shot.get("lead"), LEAD), _num(shot.get("trail"), TRAIL)
    return round(piece_seconds(text, lead, trail, max_seconds) + _num(shot.get("tail"), TAIL), 2)


def narration_shot_seconds(at: object, voice_seconds: float, shot: dict | None = None) -> float:
    shot = shot or {}
    return round(_num(at, NARRATION_AT) + voice_seconds + _num(shot.get("tail"), NARRATION_TAIL), 2)


_SENTENCE = re.compile(r"(?<=[.!?…;:])\s+|\s+[-—–]\s+")


def line_phrases(text: object, phrases: object = 1, shot: dict | None = None, max_seconds: object = None) -> list:
    """[[start, end], ...] seconds of the shot: where the words of a line with no recording are said, as many as
    the step's "phrases" (1 if it does not say), with a breath between them."""
    shot = shot or {}
    n = int(phrases) if isinstance(phrases, (int, float)) and not isinstance(phrases, bool) and phrases >= 1 else 1
    lead, trail = _num(shot.get("lead"), LEAD), _num(shot.get("trail"), TRAIL)
    piece = piece_seconds(text, lead, trail, max_seconds)
    speech = max(piece - lead - trail, 0.2)
    gaps = PHRASE_GAP * (n - 1)
    if gaps > speech * 0.5:            # a short line said in many phrases: the breaths get shorter
        gaps = speech * 0.5
    talk = speech - gaps
    gap = gaps / (n - 1) if n > 1 else 0.0
    # how much of the talking each phrase gets: by its words, sentence by sentence where the text has them
    parts = [p for p in _SENTENCE.split(str(text or "").strip()) if words(p)]
    if len(parts) == n:
        weight = [max(words(p), 1) for p in parts]
    else:
        total = max(words(text), n)
        weight = [total / n] * n
    s = sum(weight)
    out, t = [], lead
    for i, w in enumerate(weight):
        d = talk * w / s
        out.append([round(t, 2), round(t + d, 2)])
        t += d + gap
    return out
