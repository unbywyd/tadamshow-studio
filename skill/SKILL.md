---
name: tadamshow-studio
description: Make a world (a series) and its episodes for TadamShow with the `tadam` kit — puppet-theatre cartoons in which real people later record the roles on their phones. Use when the person wants to make, change or send a TadamShow world, hero (puppet), set or episode script, look at frames, play an episode, push or pull a world folder, or check its status on the server. Triggers include tadam, TadamShow, ТадамШоу, рубрика, серия, кукла, декорация, сценарий, world folder, script.json, push, pull.
---

# TadamShow Studio

You work in a **world folder** on the person's disk with the `tadam` command. The folder is the only truth: you
edit files there, the server keeps the last pushed copy, the owner approves what goes public. The person is the
**editor**; you do the hands-on work and show them the result. Answer in the person's language.

## Before anything

1. `tadam doctor` — fix what it says is missing (Python, Godot 4.7, ffmpeg, OPENAI_API_KEY).
2. Read the references you need, once per session: [world folder](reference/world-folder.md),
   [script](reference/script.md), [shots and camera](reference/shots-and-camera.md),
   [recording steps](reference/recording-steps.md), [puppets and sets](reference/puppets-and-sets.md),
   [after publishing](reference/after-publishing.md), [house rules](reference/house-rules.md).

## The work order

1. **Ask about the idea** before writing anything: what the series is about, who the heroes are, the tone, the
   look, the language(s), how long an episode is (30–90 s is good). A few questions at a time.
2. **The bible**: `tadam new world <slug> --dir <a folder for worlds>` (outside the kit's repository, so the
   world is never committed with it), then fill `world.json` (title, tagline, description, genre, bible:
   idea, tone, style, rules, heroes). Show it to the person in plain words.
3. **Heroes**: `tadam new hero <slug>`, fill `hero.json`. To block out scenes first: `tadam hero make <slug> "…"
   --mannequin` (free). The real puppet: `tadam hero make <slug> "<look>"` — **name the price first** (see
   below) and wait for a yes. After it, read the action table it prints: a hero that fails a stage-1 action is
   **drawn again, never tuned**. Look at `heroes/<slug>/puppet/check.jpg` yourself.
4. **The set**: `tadam new set <slug>`, describe the room and the pieces in `kit.json`, then `tadam set make
   <slug>` (price first) or `--placeholder` (free).
5. **The script**: `tadam new episode 1 --cast key=hero`, then write `episodes/1/script.json`.
6. **After EVERY change**: `tadam check [episode]` (fix every error) and `tadam frames <episode> --sheet`, then
   **open the sheet PNG and look at it** — heroes in the picture, not on each other, facing us, the framing
   right. Use `--board-preview` to see where the recorded face will be. Fix and look again.
7. **Show the person**: `tadam play <episode>` (a window with sound; `--shot sh3` to start there). Change what
   they ask, by their words, then check and look again.
8. **Send**: `tadam login` once (the person types the key; never in chat), then `tadam push`. Read its answer:
   the revision, the server's check, the change class, the draft links. A 409 "pull first" → `tadam pull`, merge
   every `<file>.server` into its file, delete the copy, check, push again.
9. **Remind the person** to open the draft on the site (the link from push), record every role through the QR
   code (alone or with friends), make the film and press «make studio version». `tadam status` says what is
   still missing.
10. **Submit only after the person explicitly says to send it** («отправляй», "send it"). (`tadam submit` comes
    with the next kit update; until then the person submits on the site.)

## Money

Paid generation runs on the **person's own OpenAI key**. Before `hero make` or `set make` (without `--mannequin` /
`--placeholder`) say how many pictures it paints and roughly what that costs, and wait for a yes:

- `hero make`: 2 pictures (portrait 1024×1536 + pattern sheet 1024×1536), +1 per repainted sheet (at most 2
  more). At `--quality medium` that is about $0.06–0.07 a picture with gpt-image-1 prices: **≈ $0.13, at most
  ≈ $0.26**. `high` costs about 4× more, `low` about 4× less.
- `set make`: 1 room (1024×1536) + 1 per piece (1024×1024, ≈ $0.04 at medium): a room with 5 pieces ≈ $0.27.
- These are estimates from OpenAI's published per-picture prices; the kit's default model may be priced
  differently — say so, and point to the person's OpenAI pricing page.

## Never

- Never type «согласен» / "I agree" or accept any rules for the person, and never run `tadam join` for them: the
  agreement is theirs, typed at their own keyboard.
- Never bypass a check or a refusal: no editing `.tadam/`, no hand-made requests to the API, no `--confirm` on a
  push unless the person said yes to exactly that breaking change. A failing hero is redrawn, not tuned.
- Never ask for, print, or write a key: `OPENAI_API_KEY` and `TADAM_STUDIO_KEY` live in the environment (suggest
  `skey`: `skey run --only OPENAI_API_KEY -- tadam hero make …`) or in `tadam login`'s store. Never put a key in a
  file of the world folder.
- Never use other people's music, pictures, characters, voices or real people (house rules). Never delete the
  person's files to make a check pass; `tadam pull` moves files aside, it does not delete them.
