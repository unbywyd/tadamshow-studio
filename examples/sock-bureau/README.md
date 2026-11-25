# Бюро пропавших носков / The Lost Sock Bureau

A small, complete world made with this kit: the bible, two painted heroes, one painted set and one short
episode (10 shots, about 40 s, Russian with English translations).

**The idea.** Somewhere there is an office where every sock lost in the wash ends up. A polite archivist takes
complaints; the socks never come back, but each one leaves a story. In episode 1 «Левый ушёл» ("The Left One
Left") Citizen Pyatkina comes for her left sock and learns it has left her for a right one.

## What it shows

| File | What to look at |
|---|---|
| `world.json` | a filled card and bible in two languages; `bible.style.en` is the line every picture was painted with |
| `heroes/archivist`, `heroes/visitor` | two puppets from `tadam hero make` (trousers and a knee-length coat: `--rig humanoid-a-skirt-knee`), both pass all 33 stage-1 actions; `puppet/meta.json` keeps what painting them cost (about $0.05 each at medium) |
| `sets/bureau` | `kit.json` (an empty room + three pieces, one standing on another) and what `tadam set make` painted from it |
| `episodes/1/script.json` | a title card (sh1) and an end card with narration (sh10); narration over a wide shot (sh2); listening steps; gaze marks that change during a line (`mark_down` → `lens`); shots from the catalogue: two in depth (sh3), portrait push-in (sh5), past a face (sh7), pause and hit (sh9) |
| `sources.json` | where every file comes from |

## Play it

From the kit's folder, with the kit installed (`pip install -e .`, `tadam doctor`):

```bash
cd examples/sock-bureau
tadam check 1                       # 0 errors, 0 warnings (the kit's tests check it too)
tadam hero check visitor            # free: every action on the hero (~1 min: she wears a coat, a skirt rig)
tadam frames 1 --sheet              # .tadam/frames/1/sheet.png
tadam frames 1 --sheet --board-preview
tadam play 1                        # a window with sound; Esc closes it
tadam film 1                        # .tadam/films/1.mp4
```

Nothing here needs an OpenAI key: the pictures are already painted. Without a studio key the narration shows as
subtitles. The kit's working files go to `.tadam/` (git-ignored). The check picture of a puppet (the sheet cut
into pieces, four poses) is one of them: re-cut a puppet from its sheet for free to see it,
`python -m tadam.puppet.cut_skin heroes/archivist/puppet` -> `.tadam/heroes/archivist/puppet/check.jpg`.

This world lives in the kit's repository as a sample to read and play. Make your own worlds in a folder outside
the repository (`tadam new world <slug> --dir <your worlds folder>`).

## Licence

The content of this example (texts, pictures, the world and its heroes) is under the same terms as the kit:
the [PolyForm Noncommercial License 1.0.0](../../LICENSE), with the [NOTICE](../../NOTICE). The pictures were
generated for this example with the kit's own `tadam hero make` / `tadam set make` (see `sources.json`).
