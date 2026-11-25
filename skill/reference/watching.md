# Watching together: the pause, "here", and the fix

The person watches the episode in the window and stops it where something is wrong. They do not edit anything
by hand: they say it in words («тут больше времени», «не та поза», «замени жест»), and you edit the script.
The window tells you exactly where they stopped and what was on the screen.

## Start the window

```
tadam play 1                       # in the background: it runs until the person closes it
tadam play 1 --shot sh3 --at 1.5 --paused   # open right at a moment, stopped
```

Run it in the background (it stays open), and tell the person the keys:

| Key | What it does |
|---|---|
| Space | pause / play (at the end: from the start) |
| ← / → | one frame back / on |
| Shift + ← / → | one second back / on (across shots) |
| ↑ / ↓, Home | the shot before / the next shot, this shot's start |
| L | this shot round and round |
| S | speed 1× → 0.5× → 0.25× |
| M | a mark without stopping (several places in one viewing) |
| B | the action library on the hero of the moment, opened on what it plays now |
| H | hide the notes over the picture |
| Esc, Q | close |

On a pause the window shows over the picture: the shot and second, the frame, the line being said, what every
hero is doing (the library's action names: `shrug 2/3` is phase 2 of 3; «в позе think» is the last pose left by
an action that is over), and the script lines at work.

## "Here": ask the window first, never guess

When the person says «вот тут», «здесь», «в этом месте», "here", "this":

1. `tadam play where` — the shot and second, the path of the picture (`.tadam/player/pause.png`: the frame
   exactly as on the screen, without the notes), who is heard, what every hero plays, and the shot's script
   lines with their numbers: `episodes/1/script.json → shots[4].camera[n]`, each `at_work`, `holds` (its pose is
   still there), `done`, `next` or `waits`. `--json` gives the same as data.
2. **Open the picture** and look at it before you answer.
3. More context when you need it: `tadam frames 1 --shot sh5 --around 1.5 --frames 6` — frames round the moment
   in one strip (the motion, not one pose; the moment itself framed in red); `tadam frames 1 --shot sh5 --at 1.5`
   — the frame at full size.
4. Say back what you see and what you will change, in one sentence («sh5, 1.5 s: Пяткина в позе think —
   заменю на shrug в строке camera[2]»), then edit `episodes/<n>/script.json`.
5. `tadam check <episode>`. The open window notices the change, reads the episode again and stands **on the
   same shot and second, paused**: the person sees the fix at once and presses Space.

Marks: `where` lists them (shot, second, picture, lines at work). Go through them one by one with the person.

If `where` says the window is closed, that is where it was last; if it says the script changed after that
pause, the line numbers are of the script as it was then — read the shot again before editing.

## Picking a gesture

B opens the action library (a window of its own) on the hero of the moment. The person presses actions to see
them on that hero; the last one pressed is written down, and `tadam play where` shows it as `picked last in the
action library: wave (помахать)`. When they say «замени на этот», take that name.

## What the window does not do

It does not move heroes, change timing by mouse or save anything into the script: it only shows and tells
where it stands. Every change is yours, in the script, by the person's words.
