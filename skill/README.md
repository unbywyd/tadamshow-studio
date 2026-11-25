# skill

The skill for Claude Code: [SKILL.md](SKILL.md) (the work order and the rules) and [reference/](reference/) (the
world folder and sources.json, the script, shots and the camera, recording steps, puppets and sets, submitting
and the owner's remarks, changes after publishing, the house rules, and the owner's review). `reference/script-fields.md` is generated from `schema/script.v2.json` by
`python devtools/script_fields.py`; the tests check that it is current, that the JSON examples in these pages
fit the schemas and pass `tadam check`, and that every world in the kit's `examples/` passes `tadam check` with
0 errors and 0 warnings.

To use it: open Claude Code in your worlds folder and say "read <path>/skill/SKILL.md and help me make a world".
