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
2. **The bible**: `tadam new world <slug> --dir <a folder for worlds>` — the person's worlds live OUTSIDE the
   kit's repository (only the kit's own sample, `examples/sock-bureau`, lives in it: read it, play it, never
   build in it). Fill `world.json` (title, tagline, description, genre, bible: idea, tone, style, rules,
   heroes) and show it to the person in plain words.
3. **Heroes**: `tadam new hero <slug>`, fill `hero.json`. To block out scenes first: `tadam hero make <slug> "…"
   --mannequin` (free). The real puppet: `tadam hero make <slug> "<look>"` — **name the price first** (see
   below) and wait for a yes. Its action check takes ~30 s (a hero in a skirt 1–2 min: say so). Read the table:
   a hero that fails a stage-1 action is **drawn again, never tuned**. Look at
   `.tadam/heroes/<slug>/puppet/check.jpg` yourself (check pictures and logs stay in `.tadam/`, never sent).
4. **The set**: `tadam new set <slug>`, describe the room and the pieces in `kit.json`, then `tadam set make
   <slug>` (price first) or `--placeholder` (free). A drawing that should live a little (a flame, a flag, cloth,
   a wing) becomes frames shown in turn: `tadam strip`, see [frames](reference/frames.md).
   **Every picture and sound has its source in `sources.json`** at the world root, declared the moment the file
   appears: `own` (the person made it), `generated` + `tool`, `licensed` + `licence` + `url`. `hero make`,
   `set make` and `tadam cover` (the cover from a frame, free) write their own entries; you add the rest
   (media, anything the person brings — ask where it comes from; no source, no file). `tadam check` errors on
   any file without one.
5. **The script**: `tadam new episode 1 --cast key=hero`, then write `episodes/1/script.json`.
6. **After EVERY change**: `tadam check [episode]` (fix every error) and `tadam frames <episode> --sheet`, then
   **open the sheet PNG and look at it** — heroes in the picture, not on each other, facing us, the framing
   right. Use `--board-preview` to see where the recorded face will be. Fix and look again.
7. **Show the person**: `tadam play <episode>` **in the background** (a window with sound; `--shot sh3 --at 1.5`).
   They pause it (Space) and say «вот тут»: run `tadam play where`, open its picture, fix THAT line by their
   words; the open window re-reads it by itself. Details: [watching together](reference/watching.md).
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

Paid generation runs on the **person's own OpenAI key**, at **medium quality by default** (`--quality`). Before
`hero make` or `set make` (without `--mannequin` / `--placeholder`) say how many pictures it paints and what that
costs, and wait for a yes. OpenAI prices per token, not per picture; what was paid at medium (Nov 2026,
`gpt-image-2.5-flare`):

- `hero make`: portrait ≈ $0.011 + pattern sheet ≈ $0.038 ≈ **$0.05**; each repainted sheet (at most 2) ≈ $0.04.
- `set make`: 1 room + 1 picture per piece ≈ **$0.04–0.1** a set.
- `--quality high` costs several times more (one high picture was about $0.25). Prices may change.
- Every paid command prints the pictures it painted and their cost from the API's usage (`tadam/prices.py`);
  tell the person what it actually cost.

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
