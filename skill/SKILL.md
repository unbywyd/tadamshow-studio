---
name: tadamshow-studio
description: Make a world (a series) and its episodes for TadamShow with the `tadam` kit — puppet-theatre cartoons in which real people later record the roles on their phones. Use when the person wants to make, change or send a TadamShow world, hero (puppet), set or episode script, look at frames, play an episode, push or pull a world folder, submit an episode, answer the owner's remarks, or check its status on the server; and when the project's owner reviews submissions. Triggers include tadam, TadamShow, ТадамШоу, рубрика, серия, кукла, декорация, сценарий, world folder, script.json, sources.json, push, pull, submit, заявка, замечания, review.
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
   [submitting](reference/submitting.md), [after publishing](reference/after-publishing.md),
   [house rules](reference/house-rules.md); the project's owner also [owner review](reference/owner-review.md).
3. Not an editor yet? The person runs **`tadam join` themself**, in their own terminal window (it asks the
   email, the code from the letter, shows the rules and they type «согласен» / "I agree"). Another computer:
   `tadam login` the same way. Tell them the command; never run it for them.

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
   **Every picture and sound has its source in `sources.json`** at the world root, declared the moment the file
   appears: `own` (the person made it), `generated` + `tool`, `licensed` + `licence` + `url`. `hero make` and
   `set make` write their own entries; you add the rest (cover, media, anything the person brings — ask where
   it comes from; no source, no file). `tadam check` errors on any file without one.
5. **The script**: `tadam new episode 1 --cast key=hero`, then write `episodes/1/script.json`.
6. **After EVERY change**: `tadam check [episode]` (fix every error) and `tadam frames <episode> --sheet`, then
   **open the sheet PNG and look at it** — heroes in the picture, not on each other, facing us, the framing
   right. Use `--board-preview` to see where the recorded face will be. Fix and look again.
7. **Show the person**: `tadam play <episode>` (a window with sound; `--shot sh3` to start there). Change what
   they ask, by their words, then check and look again.
8. **Send**: signed in once (`tadam join` / `tadam login`, by the person), then `tadam push`. Read its answer:
   the revision, the server's check, the change class, the draft links. A 409 "pull first" → `tadam pull`, merge
   every `<file>.server` into its file, delete the copy, check, push again.
9. **Remind the person** to open the draft on the site (the link from push), record every role through the QR
   code (alone or with friends), make the film and press «make studio version» (or `tadam studio-version
   <episode> <videoId>`).
   `tadam status` says what is still missing.
10. **Submit only after the person explicitly says to send it** («отправляй», "send it"): `tadam submit
    <episode> "<note>"` (it refuses with the list while anything is missing). Then `tadam status` shows the
    owner's answer: remarks point at shots (`remark on sh3: …`) — fix them, check, push, mark the new film,
    `tadam submit` again (the same submission reopens); `tadam reply "<text>"` answers in the thread. Details:
    [submitting](reference/submitting.md).

## Money

Paid generation runs on the **person's own OpenAI key**. Before `hero make` or `set make` (without `--mannequin` /
`--placeholder`) say how many pictures it paints and roughly what that costs, and wait for a yes:

- `hero make`: 2 pictures (portrait + pattern sheet, 1024×1536), +1 per repainted sheet (at most 2 more):
  2–4 pictures.
- `set make`: 1 room (1024×1536) + 1 picture per piece (1024×1024).
- The kit's default model is `gpt-image-2.5-flare`. For a rough figure: one high-quality picture cost about
  **$0.25** in November 2026 (so a hero ≈ $0.5, at most ≈ $1; a room with 5 pieces ≈ $1.5); medium and low are
  cheaper. Prices change: check https://openai.com/api/pricing before the first generation, give the person the
  estimate in pictures and dollars, and wait for a yes.

## Never

- Never type «согласен» / "I agree" or accept any rules for the person, and never run `tadam join` or `tadam
  login` for them: the agreement is theirs, typed at their own keyboard. Never type a submission id into
  `tadam review approve` / `reject`: that confirmation is the owner's own.
- Never bypass a check or a refusal: no editing `.tadam/`, no hand-made requests to the API, no `--confirm` on a
  push unless the person said yes to exactly that breaking change. A failing hero is redrawn, not tuned.
- Never ask for, print, or write a key: `OPENAI_API_KEY` and `TADAM_STUDIO_KEY` live in the environment (suggest
  `skey`: `skey run --only OPENAI_API_KEY -- tadam hero make …`) or in `tadam login`'s store. Never put a key in a
  file of the world folder.
- Never use other people's music, pictures, characters, voices or real people (house rules). Never delete the
  person's files to make a check pass; `tadam pull` moves files aside, it does not delete them.
