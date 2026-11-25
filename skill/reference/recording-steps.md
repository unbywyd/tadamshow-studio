# Recording steps: what a person does on the phone

Real people play the roles: each opens the episode on the site, scans a QR code and records their hero's steps
with the phone's front camera. The site shows each step's `hint`, the gaze marks and a timer. Their face then shows
in the oval of the painted head. Write every step for a stranger holding a phone, not for an actor.

## A good step

```json
{"key": "det-1", "kind": "read",
 "text": {"ru": "Сейчас найдём."},
 "hint": {"ru": "Спокойно и сонно, будто тебя разбудили. Говори красной метке слева, как собеседнику"},
 "look": [{"target": "mark_left"}],
 "phone": "eye",
 "maxSeconds": 5}
```

- **`hint`**: one or two short sentences: the feeling (how, not what), where to look, what to do with the face. In
  the person's words, second person, no film jargon. Bad: «Реплика 3, средний план». Good: «Удивлённо, брови вверх,
  смотри прямо в камеру».
- **`text`**: what is said, short — one breath. A line is one recording; split long speeches into several steps
  and several shots.
- **`maxSeconds`**: the time the person gets; a calm reader says about 2.3 words a second, so give the words / 2.3
  plus a second or two. `tadam check` says when a line does not fit.
- **`phrases`**: how many phrases the line has (pauses inside it) when the camera should react to the 2nd, 3rd…
- **`phone`**: `eye` (default), `low` (phone at the waist, looking down into it: the hero looms), `high` (phone
  above the head, looking up: the hero is small, lost).

## Gaze marks (`look`)

| target | the person | in the film |
|---|---|---|
| `lens` | looks straight into the camera | speaks to the viewer: portraits, push-ins, the hit after a pause |
| `mark_left` | talks to a red mark on the LEFT of the screen | looks to the RIGHT (the recording is not mirrored) |
| `mark_right` | talks to a mark on the right | looks to the left |
| `mark_up` / `mark_down` | looks above / below | looks up / down |
| `point` | a point `x`, `y` (0–1 of the screen) | an exact direction |

Several marks in time: `[{"target": "mark_left"}, {"target": "lens", "atSec": 2.5}]` — talks to the partner, then
on the word at 2.5 s throws a look into the camera. `holdSec` keeps a mark that long.

**The mark rule**: a mark on the left of the phone screen = the hero looks right in the film. So place the partner
in the shot on the side the recording looks to: a hero at `x: 0.3` talking to one at `x: 0.7` records
`mark_left`.

## Listening

Every hero who is in a shot but does not speak needs a **listening** step (`kind: "pause"`): «Молча слушай,
моргни, чуть кивни» with `look` at the speaker's side or into the lens. One listening step per hero is usually
enough; name it in each shot's `listen`.

## How many steps

One `read` per line plus one `pause` for listening, per hero. Every step costs the person time: keep an episode
to what one person can record in a few minutes. Step keys never change once people recorded them (a changed line
of a published episode is a breaking change: [after-publishing.md](after-publishing.md)).
