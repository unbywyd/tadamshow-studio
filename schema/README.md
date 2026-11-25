# schema

JSON Schemas of the world folder, the episode script and the studio API, exported from the server's contracts
(`packages/contracts`, `npm run schemas`). Not edited by hand: a change starts in the contracts and is copied here.
`tadam` validates world.json (`world.json`), hero.json (`hero.json`) and episodes/<n>/script.json
(`script.v2.json`) against them; `tadam check --json` prints a `check-result.json` document.
