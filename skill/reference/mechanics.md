# Mechanics: actions and the workshop

An **action** is a movement as data: `engine/actions/<id>.json` (the core library, 86 of them) or
`actions/<id>.json` in the world folder (this world's own). It does not belong to a hero: every number is in the
hero's own measures (arm and leg lengths, degrees, seconds), so the same file moves a tall hero and a short one.
A world's action plays on every hero of the world; it may not take a core name (`action_name_taken`).

## The commands

| Command | What it does |
|---|---|
| `tadam action list` | every action by group; `[world]` marks this world's own |
| `tadam action show <id>` | the action in words, phase by phase (`--json`: the file) |
| `tadam action new <id> --title "…"` | a world action from a template, to write its phases |
| `tadam action check <id> [--proof] [--heroes a,b]` | the engine plays it on the world's heroes (and on the **proof bodies**: plain, tall, short, heavy, big head, four skirts) and measures it; exit 1 on a fault. A world action's result: `actions/<id>.check.json` |
| `tadam action sheet <id> [--proof] [--frames 12]` | a storyboard PNG: a row per hero, frames through the action. **Your eyes: open it and look** |
| `tadam workshop [hero]` | the workshop window for the person (start it in the background) |
| `tadam workshop pose [--fix]` | the pose of the moment in the open window (`--fix`: keep it in the list, «вот эту зафиксируй») |
| `tadam action from-poses <id> --title "…"` | a draft action from the poses fixed in the window |

All of it is free: no paid call is made.

## The format (engine/motion.gd, its header, is the full truth)

```json
{ "id": "wave_big", "title": "помахать широко", "group": "gesture", "params": { "side": "right" },
  "phases": [
    { "time": 0.35, "arm_r": { "at": [0.44, -0.68], "look": "palm" }, "head": 6 },
    { "time": 1.6, "loop": true, "arm_r": { "wrist": { "base": 0, "amp": 30, "rate": 2.0 } } },
    { "name": "return", "time": 0.45, "arm_r": "rest", "head": "rest" } ] }
```

- Channels: `legs` (`drop`, `shift`, `foot_l` / `foot_r` `[out, up]`, `walk`, `seat`, `jump`), `body` (`lean`,
  `chest`), `head` (a tilt in degrees), `arm_l` / `arm_r` / `arms` (`at: [out, down]` arm lengths from the
  shoulder, or `{"to": "chest" | "face" | "hip" | …}`; `look`: palm / fist / back / edge / point / fist_side (a fist from the thumb, as round a handle: what a
  hand holds a thing with) / fist_palm / thumb / shake (an open hand edge on, thumb up) / pinch; `wrist`;
  `elbow`: down / up / out / in; `aim`; `contact: true` to touch the body; `shoulder`: raised in arm lengths,
  0.1–0.15 is a shrug). The head: a tilt, or `{"tilt": 7, "drop": 0.12}` (drawn into the collar; − stretched up).
- **Two ways to say an arm.** A FREE gesture (a wave, a shrug, a wind-up): its ANGLES, `"arm_r": {"raise": 140,
  "elbow": 35}` — raise: 0 hanging, 90 out level, 180 straight up, < 0 across the body; elbow (a number): 0
  straight, + the forearm turns on the way the arm rises, − in toward the body. What is written is what is drawn,
  within 2°, the same on every body: the engine guesses nothing, and its laws do not move that hand (so a hand
  written into the belly IS in the belly: the check says so). A hand that must TOUCH something: a place,
  `"at": {"to": "hip"}` (or `[out, down]`); there the engine picks the elbow, or the action says it
  (`"elbow": "out"`). Write angles by default; a place only for a touch, a thing, a partner.
- **Legs in angles**: `"legs": {"hip": 8, "knee": 0, "drop": 0.9}` (or `hip_l` / `knee_r`...): hip 0 down, + out;
  knee − bends it out. Legs said so are FREE (a body lying, falling, a leg kicked up): nothing holds the body but
  the floor — whatever part is lowest lies ON it, the body is lifted. `"legs": "rest"` (or a foot's place) plants
  them again; sit the body up straight with the legs under it first, then plant (see `fall`, `get_up`).
- Any number may swing: `{ "base": 0, "amp": 24, "rate": 2.0 }`. A phase: `time` (s), `ease` (inout / out / in /
  linear), `loop: true` (lasts the call's `duration`). Write it for the RIGHT side: the engine mirrors it.
- The last phase named `return` brings back what the action moved. Only words, numbers and lists: never a path
  or a link (the schema refuses them).

## The laws (the engine keeps them whatever the file says)

A joint bends only its own way; a hand goes round the shoulder, never into the body (unless `contact`), never
under the floor; a standing foot does not slide; the puppet is flat, so a hand is always in front of the head
and the body. Do not fight a law in the file: when the table reports a fault, change the pose or the time.

## Working with the person: poses by hand, transitions by you

The person feels movement; you write it down. The order:

(Poses kept in the window say their arms in angles, read from the hero as the person left it: the draft action
plays back exactly that, on any body.)

1. Start `tadam workshop` in the background. On the «Позы» tab the person drags dots on the hero (hands, feet,
   pelvis, neck for the lean, head) and presses «Фикс» (F) for each pose, or says «вот эту зафиксируй» and you run
   `tadam workshop pose --fix`. Three or four poses are enough.
2. `tadam action from-poses <id> --title "…"`: a phase a pose, only what changed, times by the length of the way.
3. Refine the file yourself: the ease of each way in (`out` for a snap, `in` for a slow start), a hold where the
   pose should stay (`loop`), a swing where it lives (`wrist`, `head`), the return. A way in is never shorter
   than a puppet's arm needs: about 1.6 arm lengths a second.
4. `tadam action sheet <id> --proof` and open the PNG; `tadam action check <id> --proof` until it passes.
5. The window reads the changed file by itself: the person watches it (slow 0.25×, pause, a step, «по кругу»,
   the trail) and says what to change in words, or moves a pose and fixes it again.
6. Use it in a script like any action: `"do": "<id>"`. `tadam check` warns while its check is missing or stale.
   For now a world's action plays in the kit only (`tadam play`, `frames`, the workshop): `tadam push` keeps
   `actions/` on this computer and says so, and the site plays the script without it until it learns world
   actions. Tell the person before a script relies on one.

**A pose for two** (a handshake, a hug): the row «Пара» puts two heroes side by side. The person drags each one
along the floor by the ⇆ under its feet, or uses the «Расстояние» slider, to set how far apart they stand. «Правлю
позу» picks whose dots are shown, and one «Фикс» keeps both poses: in `poses.json` each entry has `pose` (left) and
`partner` (right), both as they stand, so `arm_r` is the hand on the screen's right. «Сохранить» writes two files.
`<id>` is the left hero's half, with `"pair": {"gap", "view": "front", "partner": "<id>_b"}` and the gap measured
from where they stood. `<id>_b` is the right hero's half, `partner_only`, written MIRRORED because the stage plays
the partner with `side: left`. Refine both files the same way as above, and keep `<id>_b` mirrored.

What the window shows is written to `.tadam/workshop/state.json` (hero, action, the pose in these measures):
read it when the person says «вот это поправь». Be honest: you judge motion by the table and the storyboard; the
person judges the feel. Walks and runs are not poses: they are the `gait` of a walk (step, lift, sway, arm swing).

## Never

Edit `engine/actions/` (the core library is the owner's: `tadam workshop --core` in the kit's own clone only);
name a world action like a core one; tune an action to one hero — it must pass on the proof bodies.
