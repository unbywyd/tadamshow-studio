# Frames: a drawing that lives a little

A part of a puppet or a piece of a set is normally one picture. It may instead be **several drawings shown in
turn, round and round**: a flame, a flag, steam drawn by hand, cloth that stirs, fur, a wing. Each drawing has its
own speed, so two things in one picture never tick together. Nothing is painted by `tadam strip`: it is free.

Use it for what the engine cannot move by itself. A skirt already swings as cloth, arms and legs are moved by
actions, a lamp can sway and smoke can rise by the set's `"life"` (the list of ready behaviours at the top of
`engine/life.gd`). Frames are for a change INSIDE the drawing.

## The record

The same in both places — `heroes/<hero>/puppet/rig.json` → `parts.<part>` and `sets/<set>/set.json` →
`pieces[i]`:

```json
"frames": {"count": 4, "fps": 8, "mode": "loop", "offset": 0.25}
```

| Key | What it is |
|---|---|
| `count` | 2–16 frames. Frame 1 is the drawing itself (`skirt.png`); the others lie beside it: `skirt.f2.png` … `skirt.f4.png` |
| `fps` | frames a second, 0.5–30 (default 8). Calm cloth 3–6, a flame 8–12, a wing 10–16 |
| `mode` | `loop` 1 2 3 4 1 2… (default) · `pingpong` 1 2 3 4 3 2 1… · `once` up to the last frame and stays |
| `offset` | 0–1: the share of the round it starts at, so that two drawings do not tick together |
| `order` | instead of `mode`: its own order with holds, e.g. a blink `[1, 1, 1, 1, 1, 1, 1, 2, 3, 2]` |

**Every frame is the whole canvas of the drawing, the same size in pixels as the first.** Then all frames share
the joint (a part) or the place (a piece) and nothing jumps. `tadam strip` cuts them so; do not write the record
by hand.

## How to make them

1. `tadam strip heroes/anna/puppet/parts/skirt.png --template 4` → a strip in `.tadam/strip/`: four equal cells
   in a row, the drawing in each.
2. Cells 2–4 are redrawn: by the person, or by a picture model from the strip (**paid: name the price first and
   wait for a yes**, as for every generation; declare the source in `sources.json` if it is not covered yet).
   Keep every cell's size, the outline and the place of the joint; change what is inside.
3. `tadam strip heroes/anna/puppet/parts/skirt.png <strip.png> --count 4 --fps 6 --mode pingpong` cuts the strip,
   puts the frames beside the drawing and writes the record. The drawing itself stays as it is (frame 1);
   `--replace-first` writes the strip's first cell over it (the old one is kept in `.tadam/strip/`).
4. For a part of a puppet: `tadam hero check <hero>` again (free; the rig changed). Then `tadam check`.
5. **Look**: `tadam frames 1 --shot sh3 --around 1.5` (the frames round a moment in one strip), then
   `tadam play 1` for the person. A pause and a step back land on the same frame: it is counted from the scene's
   step, not from the clock.

`tadam strip <drawing.png> --off` makes it one picture again.

A puppet made again (`tadam hero make`) or a set painted again writes its JSON anew: the record is gone and
the old frames are left lying. `tadam check` names them (`frames_unused`): cut the strip again for the new
drawing, or take them away with `--off`.

## From the script

A line of a shot (`shots[i].camera[]`, like `do`) changes the frames while the episode plays:

```json
{"at": 1.5, "who": "vis", "frames": {"chest": 2}}
{"after": "go", "of": "vis", "who": "vis", "frames": {"chest": 1}}
{"at": 0, "piece": "lamp", "frames": 0}
{"at": 3, "piece": "lamp", "frames": "again"}
```

A number is the speed: 1 as the record says, 2 twice as fast, 0.5 half, **0 stands still** on the frame of
that moment. `"again"` plays the round from its first frame (a `once` drawing plays once more: a flame that
flares, a door that slams). A hero's speed stays when it turns (the other view's drawing goes on from the same
place). `tadam check` says when the part or the piece is not frames.

## What it is not for

- **The head and the hands** cannot be frames: a recorded face and mouth go into the head, and the engine draws
  the hands. `tadam check` warns and the engine shows the first drawing.
- **The outline of a skirt** is taken from its first frame (the cloth is cut by it): redraw the folds and the
  pattern, not the silhouette.
- A part's weight and swing are measured on the first frame too.
- Many large frames are heavy on a phone: `tadam check` warns over 24 megapixels for one drawing. Fewer frames
  (3–4 with `pingpong` read as 6) or a smaller drawing.
- Frames drawn by a picture model differ a little from each other and the line "boils". On a flame or a wing that
  reads as hand animation; on calm clothes at a high `fps` it irritates: slow it down or draw fewer frames.
- The site plays frames once its engine is updated; until then it shows the first drawing, and nothing breaks.
