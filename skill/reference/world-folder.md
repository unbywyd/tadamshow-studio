# The world folder

One folder per world (a series). Everything about the world is here; the server keeps the last pushed copy.

```
world.json                 the card and the bible (schema/world.json)
sources.json               where every picture and sound comes from (schema/sources.json; below)
cover.png                  the world's cover, vertical: cover.png, cover.jpg or cover.webp (or the file world.json
                           "cover" names); `tadam cover [episode] [--shot sh2 --at 1.5]` makes one from a frame
heroes/<slug>/hero.json    name, trait (ru/en), about (for you), height (schema/hero.json)
heroes/<slug>/puppet/      the puppet: meta.json ("name" = the hero's slug; every paid call with its usage),
                           rig.json, parts/*.png, portrait.png and sheet.png (sent: the site shows them as the hero's
                           pictures), report.json, actions.json (tadam hero check)
sets/<slug>/               kit.json (what to paint), set.json (the set as data), meta.json (the paid calls), room.png,
                           pieces, far layers
media/                     music, ambience, props held by heroes (named from the script by file name)
episodes/<n>/script.json   the script, version 2 (script.md)
episodes/<n>/episode.json  optional: title, logline, teaser (ru/en); without it the episode is «Серия <n>»
episodes/<n>/cover.png     optional
.tadam/                    the kit's own working files: scenes, cards, narration, frames, films, the check
                           pictures and logs of hero make / set make (.tadam/heroes/<slug>/puppet/check.jpg,
                           make.log; .tadam/sets/<slug>/room_raw.png), the link to the server, the merge base,
                           revisions, removed files. Never sent, never committed, never edited by hand.
```

## world.json

```json
{
  "version": 1,
  "slug": "moon-cow",
  "title": {"ru": "Корова и луна"},
  "tagline": {"ru": "Корова ищет луну"},
  "description": {"ru": "Короткие серии о корове и сонном сыщике."},
  "genre": "comedy",
  "langs": ["ru"],
  "bible": {
    "idea": {"ru": "Сыщик и корова распутывают маленькие ночные тайны"},
    "tone": {"ru": "Спокойно и смешно, без злобы"},
    "style": {"ru": "Плоская гуашь, матовые цвета", "en": "flat matte gouache, muted colours"},
    "rules": [{"ru": "Камера шутит, кукла серьёзна"}],
    "heroes": {"ru": "Корова — упрямая; сыщик — сонный"}
  }
}
```

- `slug` is the world's address on the site, unique on the whole site. It does not change after the first push
  (the push refuses a changed slug; a taken one is answered with a free suggestion).
- `langs`: every published text must exist in each language (`text_missing_lang`).
- The bible's `style.en` is what the image model gets for every puppet and set: write it in English, concrete
  (materials, colours, line, light), no artist names.

## What is sent

`tadam push` sends only files of the layout above whose names are latin letters, digits, `- _ .` with a known
type (png, webp, jpg, mp3, wav, ogg, json). Everything else stays home and push lists it (notes, check pictures,
logs, and working files an older kit left in the layout: a name starting with `_` or ending with `_raw.png`).
Empty files, names that differ only in letter case and unmerged `<file>.server` copies stop a push. JSON files are
sent with LF line endings whatever the system wrote (the manifest fingerprints exactly the bytes sent), so the
same folder gives the same revision from Windows, macOS and Linux. The kit writes pictures as compact PNGs
(lossless).

## sources.json: where every picture and sound comes from

Every png / webp / jpg / mp3 / wav / ogg that is sent needs a source (house rules 1). `tadam check` and the
server's check give `no_source` (an error, per file) or `no_sources` (no sources.json at all); a key that names
nothing is a `source_unused` warning. A key is a file, or a folder ending with `/`; the **longest key that covers
a file wins**, so a folder can say one thing and a file in it another.

```json
{
  "version": 1,
  "files": {
    "heroes/cow/puppet/": {"source": "generated", "tool": "gpt-image-2.5-flare"},
    "sets/barn/": {"source": "generated", "tool": "gpt-image-2.5-flare"},
    "sets/barn/clock.png": {"source": "own", "author": "the editor", "note": "drawn by hand"},
    "cover.png": {"source": "own"},
    "media/theme.mp3": {"source": "licensed", "licence": "CC BY 4.0", "url": "https://example.com/theme",
                        "author": "the composer"}
  }
}
```

- `own`: the person made it (optional `author`, `note`). `generated`: name the `tool` (service or model).
  `licensed`: the `licence` and a `url` (http/https) where it is stated; `author` when the licence asks credit.
- **Declare a file the moment it appears.** `tadam new world` writes an empty list; `tadam hero make` and `tadam
  set make` record their folders themselves (`--mannequin` / `--placeholder`: `own`, drawn by the kit). Anything
  else (a cover, music, a picture the person brings): ask where it comes from and write it down. Not sure the
  person may use it? Do not add the file.
- The owner sees every file with its source in the submission.

## The server link (.tadam/)

- `link.json`: the server, the world's slug and the revision this folder is at. `base.json`: that revision's
  manifest (the merge base). `revs/<n>/`: the revisions this folder pushed or pulled (for `tadam diff <n>`).
- `tadam pull` merges by file: changed only on the server → taken; only here → kept; in both → yours stays and
  the server's is written next to it as `<file>.server` (merge, then delete the copy); removed on the server →
  moved to `.tadam/removed/<time>/`.
- `tadam diff` = server → this folder; `tadam diff 3` = revision 3 → this folder; `tadam diff 3 4`.
- `tadam status` (`--json` for you): the worlds, episodes, open submissions, unread remarks of the owner and
  what is still missing before an episode can be submitted.
