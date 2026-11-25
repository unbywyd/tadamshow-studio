# engine

The TadamShow puppet engine (Godot 4.7, GL Compatibility). No builds here; `engine/.godot/` is Godot's cache and is
never committed.

- `stage.tscn` (the main scene): plays a scene written as data. `godot --path engine res://stage.tscn --
  --scene=<folder with scene.json>`; `--check` plays it through unseen and prints one `CHECK {json}` line. The
  header of `stage.gd` lists every key a scene may have. Pictures and sounds a scene names may be absolute paths
  (the kit writes its scenes into a world's `.tadam/` with absolute paths).
- `player.tscn`: the kit's local player (`tadam play / frames / film`): the shots of an episode one after
  another, with title cards and subtitles over them. `-- --playlist=<file.json>`; the playlist is written by
  `tadam` into a folder of its own for every run (never into this folder). `--font=<ttf>` gives bubbles and
  subtitles the kit's own font; `--board-preview` draws the site's look before a face is recorded.
- `viewer.tscn`: one hero and every action on buttons: `-- --hero=<name> --puppets=<world>/heroes`.
- `web_boot.tscn`: the boot scene of the web build.
- `actions/` the action library, `items/` the instruments (drawn by code: `devtools/draw_instruments.py`),
  `sounds/` the sounds (synthesized: `devtools/make_sfx.py`, `devtools/make_foley.py`).
