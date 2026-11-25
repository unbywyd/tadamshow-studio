# skill

The skill for Claude Code: [SKILL.md](SKILL.md) (the work order and the rules) and [reference/](reference/) (the
world folder, the script, shots and the camera, recording steps, puppets and sets, changes after publishing, the
house rules). `reference/script-fields.md` is generated from `schema/script.v2.json` by
`python devtools/script_fields.py`; the tests check that it is current and that every example here passes the
schemas and `tadam check`.

To use it: open Claude Code in your worlds folder and say "read <path>/skill/SKILL.md and help me make a world".
