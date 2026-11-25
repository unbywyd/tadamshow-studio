# The world folder

One folder per world (a series). Everything about the world is here; the server keeps the last pushed copy.

```
world.json                 the card and the bible (schema/world.json)
cover.png                  the world's cover, vertical
heroes/<slug>/hero.json    name, trait (ru/en), about (for you), height (schema/hero.json)
heroes/<slug>/puppet/      the puppet: meta.json, rig.json, parts/*.png, portrait.png, sheet.png, report.json,
                           actions.json (tadam hero check), check.jpg (for your eyes, never sent)
sets/<slug>/               kit.json (what to paint), set.json (the set as data), room.png, pieces, far layers
media/                     music, ambience, props held by heroes (named from the script by file name)
episodes/<n>/script.json   the script, version 2 (script.md)
episodes/<n>/episode.json  optional: title, logline, teaser (ru/en); without it the episode is «Серия <n>»
episodes/<n>/cover.png     optional
.tadam/                    the kit's own working files: scenes, cards, narration, frames, films, the link to the
                           server, the merge base, revisions, removed files. Never sent, never committed, never
                           edited by hand.
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
logs). Empty files, names that differ only in letter case and unmerged `<file>.server` copies stop a push.
Coming with the server's next step: `sources.json` at the root, saying where every picture and sound comes from
(`own`, `generated` with the tool, or `licensed` with the licence and a link) — the house rules already ask it.

## The server link (.tadam/)

- `link.json`: the server, the world's slug and the revision this folder is at. `base.json`: that revision's
  manifest (the merge base). `revs/<n>/`: the revisions this folder pushed or pulled (for `tadam diff <n>`).
- `tadam pull` merges by file: changed only on the server → taken; only here → kept; in both → yours stays and
  the server's is written next to it as `<file>.server` (merge, then delete the copy); removed on the server →
  moved to `.tadam/removed/<time>/`.
- `tadam diff` = server → this folder; `tadam diff 3` = revision 3 → this folder; `tadam diff 3 4`.
- `tadam status` (`--json` for you): the worlds, episodes, open submissions, unread remarks of the owner and
  what is still missing before an episode can be submitted.
