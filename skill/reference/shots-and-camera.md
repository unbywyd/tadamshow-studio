# Shots and the camera

## The rules of the picture (the check enforces them)

- **Vertical 9:16.** Usually one hero in the picture, sometimes two or three — in depth, not in a row.
- **A hero always faces us.** No profile, no back; a head turns at most half way. Nobody walks sideways: a hero
  comes towards us, goes away, or walks a diagonal from a far corner, face to us. Sideways movement is the
  camera's job.
- **At most 3 heroes** in a shot; a shot of a place or a thing has none.
- **The camera jokes, the puppet is serious.** The wow comes from the framing, the push-in, the focus, the cut — the
  puppet plays it straight, no mugging.
- The person who records a role films themself with a phone held in front: everything is shot from the front
  half-sphere (below, above, left, right — never behind).

## Framings (`camera` lines)

| `camera` | shows | `on` |
|---|---|---|
| `wide` | the whole stage | — |
| `full` | the hero head to feet | a cast key |
| `medium` | the hero from the head to the thighs | a cast key |
| `close` | the face | a cast key |
| `two` | both heroes in the picture | `["a", "b"]` |
| `shake` | a jolt on top of whatever is shown (`power`, `time`) | — |

A line: `{ "at": 0.2, "camera": "close", "on": "cow", "time": 3 }` — at 0.2 s start moving to a close-up of the
cow over 3 s (a slow push-in; `time: 0` is a cut). `"roll": -6` tilts the picture (an uneasy moment); `"phrase": 2`
instead of `at` waits for the speaker's 2nd phrase. `focus` on the shot gives depth of field (`back`: how soft the
background is).

## The catalogue of shots (tried with live recordings)

| Shot | Heroes | Recording | Camera and focus |
|---|---|---|---|
| Portrait, slow push-in | 1 | into the lens | medium → close over the whole line, background soft |
| Past a face | 2 | speaker: mark → lens; near one listens | start on the near hero's face at the edge, it drifts out soft, focus on the far one; on the look into the lens a short push-in |
| From below | 1 | phone low | hero closer than usual (`near`), `roll` −6 → −3, background very soft |
| From above | 1 | phone high | `roll` +7 → +3 |
| Diagonal from the depth | 1 | into the lens | the hero walks from the far corner towards us, face to us; wide → medium, focus follows |
| Turn and whip | 2 | mark → lens; the other listens | close; after the word a whip to the other hero in 0.16 s |
| Two in depth | 2 | near: at the mark; far: listens | near sharp, far soft; after the phrase focus goes to the far one's reaction |
| Pause and hit | 1 | into the lens, 2 s silent | medium; on the first word a sharp push-in (0.12 s) and a `shake` |
| Group portrait | 3 | all listen | three facing us, wide, slow push-in |

A shot lasts its line (or its `seconds`) plus a short tail; shots are joined by straight cuts.

## Heroes in a shot

- `x`: 0 left edge … 1 right edge; `depth`: 0 the front … 1 far back (farther is smaller). Two heroes at the same
  depth must not cover each other — put one deeper.
- `near: true` (or a number): closer than the front edge, larger — over the shoulder.
- `height`: the hero's size against the picture (default: hero.json `height`, about 0.42).
- `at`: a named point of the set (set.json `points`).

## Moves (engine lines in `camera`)

Lines with `who` drive a hero: `{ "at": 1.0, "who": "cow", "do": "nod" }`. Keep them few and simple; the face
does the acting. The actions every hero is checked on (stage 1): rest, hips, think, tired, scared, serious,
victory; wave, bye, beckon, point, clap, facepalm, head_grab, heart, nod, shake_head, rub, scratch_head, shoo,
shrug, spread; angry, cry, laugh, surprised; dance_arms, dance_twist; bow, curtsy, hop, jump, squat. Others exist
(`engine/actions/*.json`) but are not guaranteed on every hero. `go` walks (always facing us), `turn` only to
`front`.

## Stage options (`film.stage` or a shot's `stage`)

`faces: "board"` (the recorded face in an oval of the painted head — the house look), `hands` (`stump` default,
`one`, `mitten`, `ball`, `none`, `drawn`), `walk: "front"`, `parallax`, `vignette` (0–1), `grade` (`day`,
`evening`, `night`, `alarm`), `closest` (how near the camera may go).

## Looking at your work

- `tadam frames <ep> --sheet` — one PNG, the middle of every shot, labelled. Open it after every change.
- `tadam frames <ep> --shot sh3 --at 1.5` — one exact frame.
- `--board-preview` — the site's look: a flat placeholder where the recorded face will show, the head grown as the
  site grows it. Use it before showing framing to the person.
- `tadam check <ep> --engine` — also plays every shot through in the engine (catches a hero talking off the
  picture, a face too small for the frame).
