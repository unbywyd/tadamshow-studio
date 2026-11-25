# Puppets and sets

## A hero's puppet

A puppet is a flat jointed figure: 15 painted pieces (head, chest, pelvis, upper arms, forearms, hands, thighs,
shins, feet) pinned at the joints. The engine moves it; nothing is animated by hand.

```
tadam new hero cow --name "Корова"                       heroes/cow/hero.json: name, trait, about, height
tadam hero make cow "a calm brown cow in a yellow raincoat, big round eyes" [--rig humanoid-a-skirt-knee]
tadam hero make cow "..." --mannequin                    free: the wooden mannequin, to block out scenes
tadam hero check cow                                     every action on the hero, in the engine (free; ~30 s,
                                                         a hero in a skirt 1–2 min: run it in the background)
```

`hero make` (PRICE FIRST, see SKILL.md; medium quality by default, about $0.05 a hero): paints a full-body
portrait, then the pattern sheet (every piece apart, on the pattern), cuts the sheet, builds the skeleton and
audits the assembled puppet; a failed sheet is repainted from the same portrait (up to 3 attempts). Then it runs
`tadam hero check`. It prints the pictures painted and their cost (from the API's usage); `puppet/meta.json`
keeps every call with its usage, and its `"name"` is the hero's slug (the server keys puppets by it: two heroes
with one name are a `tadam check` error, `puppet_name_twice`).

- **The description**: what the hero looks like, concrete — body, clothes, colours, one or two memorable details
  (a hat, horns, ears: the hero is recognised by the silhouette of its head). No famous characters, no real
  people. The look of the whole world comes from the bible's `style` (`--style` overrides it).
- **Patterns** (`--rig`): `humanoid-a` (trousers), `humanoid-a-skirt-short|knee|calf|floor` (a skirt or a coat of
  that length). The side and back views (`humanoid-a-side…`, `humanoid-a-back…`) exist but heroes face us anyway.
- **Look at `.tadam/heroes/<slug>/puppet/check.jpg`** (the sheet cut into pieces, joints marked, four poses; with
  `_sheet_check.jpg`, `_poses.jpg` and `make.log` it is a working file: in `.tadam/`, never sent). The audit's
  verdict is `report.json` (`passed`). `portrait.png` and `sheet.png` stay in the puppet folder and are sent: the
  site shows them as the hero's pictures, and a repaint starts from the portrait. Re-cutting a puppet from its
  sheet is free and gives the same parts: `python -m tadam.puppet.cut_skin heroes/<slug>/puppet` (then `tadam
  hero check <slug>`).
- **The face board**: `hero make` also writes `parts.head.board` into `rig.json` — the oval of the painted head
  where the recorded face will show on the site (found from the drawing: under the hat or hair, over the painted
  face, snug — a little of the brow and cheeks is cut, as a hole in a board). Check it with
  `tadam frames <ep> --board-preview` on a close shot. A head drawn so that the oval lands wrong is drawn again
  (a clearer face, a less tall hat), not adjusted by hand.
- **The action table** (`tadam hero check`, written to `puppet/actions.json`): every action of the engine played on
  this hero, both sides, measured (an elbow on the wrong side, a sliding foot, a hand inside the body, under the
  floor, a missed target, a jerk, the face covered, not back at rest). The hero must pass all 33 **stage-1**
  actions; the rest are reported only. **A failing hero is drawn again — never tuned, never fitted.** `tadam check`
  reports a hero whose table is missing, stale (the puppet changed since) or failing.

## A set

A set is a room in parts: an empty room picture, far layers, and every piece of furniture as its own picture on
a transparent background. When a film is made the set is only data (`set.json`): no AI at film time.

```
tadam new set barn          sets/barn/kit.json (what to paint) + set.json
tadam set make barn         PRICE FIRST: one picture for the room, one per piece (medium: $0.04–0.1 a set)
tadam set make barn --placeholder        free: a plain room and flat shapes, to block out scenes
tadam set make barn --only desk          repaint one part;  --layout-only: lay out set.json again, no painting
```

kit.json:

```json
{
  "name": "Хлев",
  "floor": 0.87,
  "ground": {"far": 0.675, "far_scale": 0.55, "tilt": 0.7},
  "room": {"prompt": "an empty wooden barn, front view, vertical 9:16, floor in the lower part, a small window"},
  "far": [],
  "props": [
    {"id": "crate", "prompt": "an old wooden crate", "x": 0.2, "base": 0.8, "width": 0.25},
    {"id": "lamp", "prompt": "a small oil lamp", "x": 0.2, "on": "crate", "surface": 0.1, "width": 0.08}
  ]
}
```

- The room is EMPTY (furniture comes as pieces), seen from the front, its floor in the lower part.
- **A window**: ask the model for the window glass "filled with flat pure magenta #FF00FF" (the template's room
  prompt says so). `set make` keys that magenta out (with its pink fringe), so the glass becomes see-through.
  Behind it the engine shows the set's **far layers** (`far`: `{"id", "image", "scale", "rect"}`): **your own
  pictures** in the set's folder (a street, a sky, a garden), each at its own depth so it slides and blurs with the
  camera. The kit does not paint far layers: bring them (and give each a source in sources.json); without one the
  window shows the engine's plain light backdrop.
- `set make` prints the pictures painted and their cost and keeps them with their usage in `sets/<slug>/meta.json`;
  the model's raw room (before the keying) is a working file in `.tadam/sets/<slug>/`.
- A piece (`id`, `prompt`, `x`, `width` required): `x` (0–1 across), `base` (where it stands, 0 top … 1 bottom),
  `width` (share of the picture); `on`: stands on another piece's top (`surface`: how far down that piece its top is).
- Keep 2–5 pieces; leave the middle free for the heroes.
- `set.json` may also have `points` (named places: `{"door": {"x": 0.8, "y": 0.9}}`) that shots use with `at`.

## Media

`media/` holds music (`theme.mp3`), ambience and props a hero holds (`cup.png`, transparent). Only what you have
the right to use: own, generated by you, or licensed for this use (house rules). Music is not generated by the kit.
