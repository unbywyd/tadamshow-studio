# schema

JSON Schemas of the world folder, the episode script and the studio API, exported from the server's contracts
(`packages/contracts`, `pnpm --filter @tadamshow/contracts schemas`). Not edited by hand: a change starts in the
contracts and is copied here with `python devtools/refresh_schemas.py <a checkout of the server, or its
packages/contracts>` (it also removes the schemas the contracts dropped and rewrites
skill/reference/script-fields.md).
`tadam` validates world.json (`world.json`), hero.json (`hero.json`) and episodes/<n>/script.json
(`script.v2.json`) and sources.json (`sources.json`) against them, applies the word list `bad-words.json` the way
the server does (tadam.words), and `tadam check --json` prints a `check-result.json` document. The fake server of
the tests checks every answer against the `*.response.json` / `submission*.json` schemas.
