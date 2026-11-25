# TadamShow Studio

Tools for making puppet-theatre cartoons for [TadamShow](https://tadamshow.com): the puppet engine, the
`tadam` command and (soon) a skill for Claude Code. You keep a **world folder** on your disk; Claude writes
the script, makes the puppets and the sets, looks at the frames itself and shows you the scene in a local
player. When it is ready, one command sends it to TadamShow for review.

> Status: early. Working: `tadam doctor`, `new`, `hero make`, `set make`, `check` and the engine. Coming: the
> local player and frames (`play`, `frames`, `film`), sending to TadamShow (`login`, `push`, ...), the skill.

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
   commit; a secret manager is best.
5. A **studio key** from your TadamShow studio page — later, only to send your work (`tadam login`).

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

## Commands

```bash
tadam new world my-world --title "Моя рубрика"   # a world folder (world.json with the bible)
cd my-world
tadam new hero cow --name "Корова"                # heroes/cow/hero.json
tadam hero make cow "a calm brown cow in a raincoat"   # paints the puppet with YOUR key, cuts it, checks it
tadam new set barn                                # sets/barn/kit.json: describe the room and the furniture
tadam set make barn                               # paints the set with YOUR key, writes set.json
tadam new episode 1 --cast cow=cow                # episodes/1/script.json (script version 2)
tadam check 1                                     # what is wrong, in plain words; exit 1 on errors; --json
```

`hero make --mannequin` and `set make --placeholder` draw free stand-ins by code (a wooden mannequin, a plain
room) to block out scenes before anything is painted. `tadam check --engine` also plays every shot through in
the engine, unseen. A world folder:

```
world.json   cover.png   heroes/<slug>/hero.json + puppet/   sets/<slug>/   media/   episodes/<n>/script.json
.tadam/      the kit's working files (engine scenes, caches): never committed, never sent
```

## Layout

```
tadam/      the library and the `tadam` command (src/tadam)
engine/     the puppet engine (Godot 4.7): engine/stage.tscn plays a scene, engine/viewer.tscn shows a hero
schema/     JSON Schemas of the script and the world folder (exported from the server, not edited by hand)
devtools/   the code that drew the engine's instruments and synthesized its sounds
skill/      the skill for Claude Code — coming
examples/   a small sample world — coming
```

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
