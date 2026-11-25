# The script: episodes/<n>/script.json, version 2

One document per episode. You write **names, never paths**: a hero is a cast key pointing at `heroes/<slug>`, a set
is `sets/<slug>`, music and props are file names in `media/`. Every field with its type and limits:
[script-fields.md](script-fields.md) (generated from the schema). The server ignores and refuses `film.static`,
`film.assets`, `film.files`, `shots[].scene`, `cardUrl`: never write them.

## The four parts

**cast** — `{ "<key>": { "character": "<hero slug>" } }`. The key (`cow`, `det`) is how the script names the hero;
up to 24 latin small letters, digits, `_`.

**roles** — per cast key, the **steps a person records** on the phone, in order. Each step has a stable `key`
(`cow-1`; recordings are tied to it for good — never rename a step of a published episode) and a `kind`:

| kind | what the person does | needs |
|---|---|---|
| `read` | says a line | `text`, `hint`, `look`; `maxSeconds` (how long it may take); `phrases` (below) |
| `pause` | listens silently (the reaction while another speaks) | `hint`, `look` |
| `look` | a look without words | `hint`, `look` |
| `info`, `wait_ok` | an instruction screen / "press OK when ready" | `hint` |

How to write good hints and gaze marks: [recording-steps.md](recording-steps.md).

`phrases` (1–12, default 1) says in how many breaths the line is said. A camera line `{ "phrase": 2, ... }`
waits for the 2nd one. On the site the phrases are found in the person's recording; in the kit, with nothing
recorded, the line is timed like a calm reader (0.4 s, then 2.3 words a second, then 0.25 s; a shot with a line
lasts that plus 0.4 s) and cut into `phrases` parts by its sentences (or evenly by words), 0.3 s apart.

**shots** — the film, in order. A shot is what the viewer sees between two cuts:
- `id` (`sh1`), `remark` (one short line for the viewer: «Корова спрашивает»), `about` (for you: how it is shot).
- `say`: the step key of the line spoken in this shot (a `read` step). `listen`: `{ "<cast key>": "<step key>" }` —
  the other heroes in the shot and which of their steps (usually a `pause`) shows their reaction.
- `narration`: `{ "text": {...}, "at": 0.5 }` — the narrator over this shot (voiced by the server).
- `card`: a title card (`title`, `sub`, `kicker`).
- `seconds`: the length of a shot with no line (a place, a thing, a card). A shot with a line lasts the line.
- `actors`: who stands where (1–3 heroes; none for a shot of a place or a thing): `id`, `x` (0 left … 1 right),
  `depth` (0 front … 1 far), `near` (closer than the front edge: over-the-shoulder), `height`, `at` (a named point
  of the set), `prop` (a picture from `media/` in the hero's hand).
- `focus`: `{ "on": "<cast key>", "aperture": 1.0, "back": 0.4 }` — depth of field.
- `camera`: the shot's timeline: framings from the catalogue (`{ "at": 0, "camera": "close", "on": "cow",
  "time": 3 }`) and engine lines (`{ "at": 1.2, "who": "cow", "do": "nod" }`). See
  [shots-and-camera.md](shots-and-camera.md).
- `set`: another set for this shot; `pieces`: extra set pieces for this shot only.
- Timing (rarely needed): `lead`, `trail`, `tail` seconds around a line; `gain` dB on the voice; `quiet` (no music);
  `song` (a song over the shot); `cut_listen` (which part of a listener's take shows).

**film** — `set` (the set every shot plays in), `music` (`file` in media/, `db` −12 is a good bed, `min_gap`),
`stage` (engine options every shot shares: `"faces": "board"` puts the recorded face in an oval of the painted
head — use it).

**narrator** (optional) — `{ "voice": "<a voice of the server>", "fx": "none" | "radio" }`.

## What the check wants (`tadam check`)

- every `say` / `listen` names a real step of that hero; every cast hero has steps; step keys and shot ids unique;
- every recorded step has a `hint` and `look` marks; a line fits its `maxSeconds` (a calm reader: about 2.3 words
  a second); the whole episode under 300 s;
- heroes in the picture, not on each other at one depth, at most 3, always facing us; framings from the catalogue;
- named sets, music, props exist with the exact letter case; texts in every language of the world.

## A small, complete example

```json
{
  "version": 2,
  "cast": {"cow": {"character": "cow"}, "det": {"character": "detective"}},
  "roles": {
    "cow": [
      {"key": "cow-1", "kind": "read", "text": {"ru": "Где моя луна?"},
       "hint": {"ru": "Удивлённо, будто луна пропала только что. Телефон на уровне глаз"},
       "look": [{"target": "lens"}], "maxSeconds": 5}
    ],
    "det": [
      {"key": "det-1", "kind": "read", "text": {"ru": "Сейчас найдём."},
       "hint": {"ru": "Спокойно и сонно, говори красной метке слева, как собеседнику"},
       "look": [{"target": "mark_left"}], "maxSeconds": 5},
      {"key": "det-2", "kind": "pause", "hint": {"ru": "Молча слушай, моргни, чуть кивни"},
       "look": [{"target": "lens"}]}
    ]
  },
  "shots": [
    {"id": "sh1", "remark": {"ru": "Корова спрашивает"}, "say": "cow-1", "listen": {"det": "det-2"},
     "actors": [{"id": "cow", "x": 0.3}, {"id": "det", "x": 0.72, "depth": 0.5}],
     "focus": {"on": "cow"},
     "camera": [{"at": 0, "camera": "medium", "on": "cow"}, {"at": 0.2, "camera": "close", "on": "cow", "time": 3}]},
    {"id": "sh2", "remark": {"ru": "Сыщик отвечает"}, "say": "det-1",
     "actors": [{"id": "det", "x": 0.5, "prop": "cup.png"}],
     "camera": [{"at": 0, "camera": "close", "on": "det"}]},
    {"id": "sh3", "remark": {"ru": "Двор"}, "seconds": 2,
     "actors": [{"id": "cow", "x": 0.5, "depth": 0.6}],
     "narration": {"text": {"ru": "А луна была рядом."}}}
  ],
  "film": {"set": "barn", "music": {"file": "theme.mp3", "db": -12}, "stage": {"faces": "board"}}
}
```

The detective in sh1 listens (`det-2`) while the cow speaks; in sh2 the person playing him looks at the mark on
the left, so in the film he looks to the right — where the cow would stand.
