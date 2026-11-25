# TadamShow Studio

Tools for making puppet-theatre cartoons for [TadamShow](https://tadamshow.com): the puppet engine, the
`tadam` command and a skill for Claude Code. You keep a **world folder** on your disk; Claude writes
the script, makes the puppets and the sets, looks at the frames itself and shows you the scene in a local
player. When it is ready, one command sends it to TadamShow for review.

> Status: early. Working: `tadam doctor`, `new`, `hero make` / `hero check`, `set make`, `check`, the local player
> and frames (`play`, `frames`, `film`, `cover`), the engine, the link to TadamShow (`join`, `login`, `push`, `pull`,
> `diff`, `status`), submissions (`submit`, `studio-version`, `reply`, `withdraw`, `unpublish`), the owner's
> `review`, and the skill.

Русская версия: [README.ru.md](README.ru.md).

## Licence in one paragraph

This is **source-available** software under the [PolyForm Noncommercial License 1.0.0](LICENSE), not open
source. It is free for personal, hobby, educational and research use. Making cartoons, videos or products
with it for commercial purposes needs a commercial licence. **Making worlds and episodes for TadamShow is
allowed** (see [NOTICE](NOTICE)). The content of worlds and the TadamShow name and logo are not covered by
the licence. For a commercial licence, open an issue titled "Commercial licence".

## Install in 5 minutes

You need:

1. **Python 3.11+** — https://www.python.org/downloads/
2. **Godot 4.7** (the standard build, not .NET) — https://godotengine.org/download/
   Put it on your `PATH` (as `godot`, `godot4` or `godot_console`) or set `TADAM_GODOT` to its full path.
3. **ffmpeg** with `ffprobe` — https://ffmpeg.org/download.html
4. **Your own OpenAI API key** in the environment variable `OPENAI_API_KEY` — https://platform.openai.com/api-keys
   It pays for the pictures of your puppets and sets. Nothing paid comes from us. Keep it out of files you
   commit; a secret manager is best (it can pass the key to one command: `skey run --only OPENAI_API_KEY --
   tadam hero make …`).
5. A **studio key** (`tds_…`) — to send your work and to hear the narration in the local player. Run
   **`tadam join`** yourself in a terminal: your email, the code from the letter, the studio's rules in full, and
   you type «согласен» / "I agree"; the key comes back once and is kept in your own config folder (never shown).
   On another computer: `tadam login` (the same email and code), or `tadam login --key` with a key from the
   cabinet, or `TADAM_STUDIO_KEY`. Without a key the narration is shown as subtitles. Never paste it into a
   chat.

Then:

```bash
git clone https://github.com/unbywyd/tadamshow-studio.git
cd tadamshow-studio
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS / Linux: source .venv/bin/activate
pip install -e .
tadam doctor
```

`tadam doctor` checks Python, Godot, ffmpeg, the OpenAI key (only that it is set; the value is never
printed) and a writable temp folder, and says what is missing and where to get it. Exit code 1 means
something required is missing.

## What it costs

Only painting costs money (your OpenAI key); everything else is free. The kit paints at **medium quality by
default** (`--quality low | medium | high` on `hero make` and `set make`; `--help` shows the defaults). OpenAI
prices pictures per token, not per picture; what was actually paid at medium (November 2026):

| what | pictures | about |
|---|---|---|
| a hero (`hero make`) | portrait + pattern sheet (+1 per repainted sheet, at most 2) | $0.011 + $0.038 ≈ **$0.05** |
| a set (`set make`) | 1 room + 1 per piece | **$0.04–0.1** |
| at `high` | | several times more (one high picture was about $0.25) |

Every paid command prints the pictures it painted and their cost, worked out from the token usage the API
answers with (the per-token prices, with their date, are in `src/tadam/prices.py`; they may change), and keeps
the usage in `meta.json` (the puppet's, or `sets/<slug>/meta.json`).

## Start in 5 minutes

Claude asks about your idea, writes the bible, makes the heroes and the set (naming the price before anything
paid), writes the script, looks at the frames itself and plays the episode for you. When you like it, it pushes
the world; you record the roles on the site and say when to send it.

1. Install (above) and run `tadam doctor` until it is happy.
2. `tadam join` in your own terminal (or skip it for now: everything but sending works without it).
3. Open Claude Code in this repository (or anywhere, giving the full path of `skill/SKILL.md`) and tell Claude:
   **"read skill/SKILL.md and help me make a world"**

## Commands

```bash
tadam new world my-world --title "Моя рубрика"   # a world folder (world.json with the bible)
cd my-world
tadam new hero cow --name "Корова"                # heroes/cow/hero.json
tadam hero make cow "a calm brown cow in a raincoat"   # paints the puppet with YOUR key, cuts it, checks it
tadam new set barn                                # sets/barn/kit.json: describe the room and the furniture
tadam set make barn                               # paints the set with YOUR key, writes set.json
tadam new episode 1 --cast cow=cow                # episodes/1/script.json (script version 2)
tadam check 1                                     # what is wrong, in plain words, and the episode's length;
                                                  # exit 1 on errors; --json; --verbose adds the info notes
tadam frames 1 --sheet                            # one PNG: the middle of every shot, labelled (Claude looks at it)
tadam frames 1 --shot sh3 --at 1.5                # one frame of one shot; --json prints the paths as JSON
tadam frames 1 --shot sh3 --around 1.5            # six frames round that moment in one strip: the motion
tadam play 1 [--shot sh3 --at 1.5 --paused]       # a window plays the episode with its sound; Space pauses, arrows
                                                  # step, M marks, B opens the action library, Esc closes;
                                                  # it plays changes to the world at once
tadam play where                                  # where the window stopped: shot, second, picture, what every
                                                  # hero plays, the script lines at work (skill: watching.md)
tadam film 1                                      # a draft MP4 (picture, narration, music, subtitles)
tadam hero check cow                              # every action of the engine on the hero (hero make runs it;
                                                  # ~30 s, a hero in a skirt 1-2 min)
tadam cover [1] [--shot sh2 --at 1.5]             # the world's cover from a frame (free), no subtitles

tadam join                                        # become an editor: email, code, the rules, YOU type «согласен»
tadam login [--key]                               # this computer: email + code (or an existing key, typed hidden)
tadam rules [--terms]                             # read the studio's rules
tadam push                                        # check, then send only what changed; prints the revision
tadam pull [slug]                                 # the server's revision: merged into this folder, or a new one
tadam diff [rev [rev]]                            # what changed, by files and by shots and steps
tadam status [--json]                             # worlds, episodes, submissions, remarks, what is missing
tadam studio-version 1 <videoId>                  # the film you made on the site is the episode's studio version
tadam submit 1 "a note"                           # to the owner (refused with the list while anything is missing)
tadam reply "text" [--shot sh3]  |  tadam withdraw  |  tadam unpublish "reason" [--episode 1]
tadam review list | show <id> | approve <id> | return <id> "..." [--shot sh3 "..."] | reject <id> "..."
                                                  # the project's owner only (staff key: tadam login --staff)
```

Every picture and sound of a world has its source in `sources.json` at the world's root (`own`, `generated`
with the tool, `licensed` with the licence and a link; a folder key ending with `/` covers its files):
`tadam check` errors on a file without one, and on swearing in any text (borderline words are warnings), the
same rules the server applies.

`hero make --mannequin` and `set make --placeholder` draw free stand-ins by code (a wooden mannequin, a plain
room) to block out scenes before anything is painted. `tadam check --engine` also plays every shot through in
the engine, unseen.

Nothing is recorded locally: heroes keep their painted heads, their mouths move while they say a line, and the
line shows as a subtitle with the hero's name. A line with no recording lasts what a calm reader takes to say it
(`tadam.timing`: lead 0.4 s + words / 2.3 a second + trail 0.25 s, then 0.4 s of the shot after it).
`--board-preview` draws what the site will show once a face is recorded (a placeholder in the head's face oval,
the head as large as the site makes it), so the framing matches; `hero make` finds that oval from the drawing. The narration is voiced by the TadamShow server
(`POST /api/studio/tts`: only the text and the voice key are sent) and kept in `.tadam/tts/`; `--no-voice` keeps
it as subtitles. On Linux without a screen, frames and films run under `xvfb-run`. A world folder:

```
world.json   sources.json   cover.png|jpg|webp   heroes/<slug>/hero.json + puppet/   sets/<slug>/   media/   episodes/<n>/
.tadam/      the kit's working files (engine scenes, cards, narration, frames, films, the check pictures and logs
             of hero make / set make): never committed, never sent
```

The kit writes every JSON file with LF line endings and fingerprints a puppet by its rig's content, so a
checkout that changes line endings changes nothing; `tadam push` sends JSON with LF on every system. Pictures are
kept as compact PNGs (lossless: invisible pixels cleaned, deflated hard).

## Layout

```
tadam/      the library and the `tadam` command (src/tadam)
engine/     the puppet engine (Godot 4.7): engine/stage.tscn plays a scene, engine/viewer.tscn shows a hero
schema/     JSON Schemas of the script, the world folder and the studio API, and the word list (exported from
            the server: python devtools/refresh_schemas.py <contracts>; never edited by hand)
devtools/   the code that drew the engine's instruments and synthesized its sounds; the schema refresh
skill/      the skill for Claude Code: SKILL.md and reference/ (the folder, the script, shots, recording, puppets)
examples/   a small sample world: examples/sock-bureau (two heroes, one set, one 40-second episode). It lives
            in the kit's repository to be read and played; your own worlds go in a folder outside it. The tests run
            `tadam check` on every example (0 errors, 0 warnings)
```

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
