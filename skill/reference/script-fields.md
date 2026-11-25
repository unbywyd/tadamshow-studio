# script.json version 2: every field

Generated from `schema/script.v2.json` (the server's contract) by `devtools/script_fields.py`: do not edit by hand.
What the fields mean and which ones matter: [script.md](script.md). `*` = required.

| Field | Type | Values and limits |
|---|---|---|
| `$schema` | string | length <= 300 |
| `version` * | 2 |  |
| `cast` * | map of object | keys `^[a-z][a-z0-9_]{0,23}$` |
| `cast.<key>.character` * | string | length >= 1; length <= 80; pattern `^[a-z0-9]+(?:-[a-z0-9]+)*$` |
| `narrator` | object |  |
| `narrator.engine` | string | `silero` / `piper`; default `"silero"` |
| `narrator.voice` | string | length <= 40; default `"eduard"` |
| `narrator.fx` | string | `none` / `radio`; default `"none"` |
| `roles` * | map of list of object | keys `^[a-z][a-z0-9_]{0,23}$` |
| `roles.<key>` | list of object | items >= 1 |
| `roles.<key>[].key` * | string | pattern `^[a-z0-9][a-z0-9_-]{0,47}$` |
| `roles.<key>[].kind` * | string | `info` / `read` / `wait_ok` / `look` / `pause` |
| `roles.<key>[].text` | object |  |
| `roles.<key>[].text.ru` * | string | length >= 1; length <= 500 |
| `roles.<key>[].text.en` | string | length <= 500 |
| `roles.<key>[].hint` | object |  |
| `roles.<key>[].hint.ru` * | string | length >= 1; length <= 1000 |
| `roles.<key>[].hint.en` | string | length <= 1000 |
| `roles.<key>[].look` | list of object | default `[]` |
| `roles.<key>[].look[].target` * | string | `lens` / `mark_left` / `mark_right` / `mark_up` / `mark_down` / `point` |
| `roles.<key>[].look[].x` | number | >= 0; <= 1 |
| `roles.<key>[].look[].y` | number | >= 0; <= 1 |
| `roles.<key>[].look[].atSec` | number | >= 0 |
| `roles.<key>[].look[].holdSec` | number | >= 0 |
| `roles.<key>[].phone` | string | `eye` / `low` / `high` |
| `roles.<key>[].maxSeconds` | number | > 0; <= 120 |
| `roles.<key>[].phrases` | integer | >= 1; <= 12 |
| `shots` * | list of object | items >= 1; items <= 120 |
| `shots[].id` * | string | pattern `^[a-z0-9_-]{1,24}$` |
| `shots[].remark` * | object |  |
| `shots[].remark.ru` * | string | length >= 1; length <= 300 |
| `shots[].remark.en` | string | length <= 300 |
| `shots[].about` | string | length <= 1500 |
| `shots[].say` | string | pattern `^[a-z0-9][a-z0-9_-]{0,47}$` |
| `shots[].listen` | map of string | keys `^[a-z][a-z0-9_]{0,23}$` |
| `shots[].listen.<key>` | string | pattern `^[a-z0-9][a-z0-9_-]{0,47}$` |
| `shots[].narration` | object |  |
| `shots[].narration.text` * | object |  |
| `shots[].narration.text.ru` * | string | length >= 1; length <= 800 |
| `shots[].narration.text.en` | string | length <= 800 |
| `shots[].narration.at` | number | >= 0; default `0.5` |
| `shots[].narration.db` | number | default `0` |
| `shots[].card` | object |  |
| `shots[].card.title` * | object |  |
| `shots[].card.title.ru` * | string | length >= 1; length <= 120 |
| `shots[].card.title.en` | string | length <= 120 |
| `shots[].card.sub` | object |  |
| `shots[].card.sub.ru` * | string | length >= 1; length <= 120 |
| `shots[].card.sub.en` | string | length <= 120 |
| `shots[].card.kicker` | object |  |
| `shots[].card.kicker.ru` * | string | length >= 1; length <= 80 |
| `shots[].card.kicker.en` | string | length <= 80 |
| `shots[].card.from` | number | >= 0 |
| `shots[].card.to` | number | >= 0 |
| `shots[].card.top` | number | >= 0; <= 1 |
| `shots[].seconds` | number | > 0; <= 120 |
| `shots[].set` | string | length >= 1; length <= 80; pattern `^[a-z0-9]+(?:-[a-z0-9]+)*$` |
| `shots[].actors` | list of object | items <= 3 |
| `shots[].actors[].id` * | string | pattern `^[a-z][a-z0-9_]{0,23}$` |
| `shots[].actors[].x` * | number | >= -0.5; <= 1.5 |
| `shots[].actors[].y` | number | >= -0.5; <= 1.5 |
| `shots[].actors[].depth` | number | >= 0; <= 1 |
| `shots[].actors[].near` | boolean or number |  |
| `shots[].actors[].at` | string | pattern `^[a-z][a-z0-9_]{0,31}$` |
| `shots[].actors[].height` | number | >= 0.05; <= 1.5 |
| `shots[].actors[].prop` | string | length <= 200; pattern `^(?:[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}\/){0,3}[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$` |
| `shots[].focus` | object |  |
| `shots[].focus.on` * | string | length <= 40 |
| `shots[].focus.aperture` | number | >= 0; <= 4 |
| `shots[].focus.back` | number | >= 0; <= 1 |
| `shots[].camera` | list of object | items <= 40 |
| `shots[].camera[].at` | number | >= 0 |
| `shots[].camera[].phrase` | integer | >= 1; <= 40 |
| `shots[].camera[].camera` | string | length <= 40 |
| `shots[].camera[].on` | string or list of string |  |
| `shots[].camera[].time` | number | >= 0 |
| `shots[].stage` | map of string or number or boolean | keys `^[a-z][a-z0-9_]{0,31}$` |
| `shots[].stage.<key>` | string or number or boolean |  |
| `shots[].pieces` | list of object | items <= 20 |
| `shots[].pieces[].id` * | string | pattern `^[a-z0-9_-]{1,32}$` |
| `shots[].pieces[].image` * | string | length <= 200; pattern `^(?:[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}\/){0,3}[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$` |
| `shots[].pieces[].rect` * | list | items >= 4; items <= 4 |
| `shots[].pieces[].base` | number | >= -1; <= 2 |
| `shots[].pieces[].bias` | number | >= -1; <= 1 |
| `shots[].pieces[].front` | boolean |  |
| `shots[].lead` | number | >= 0; <= 10 |
| `shots[].trail` | number | >= 0; <= 10 |
| `shots[].tail` | number | >= 0; <= 10 |
| `shots[].gain` | number | >= -24; <= 24 |
| `shots[].quiet` | boolean |  |
| `shots[].song` | object |  |
| `shots[].song.file` * | string | length <= 200; pattern `^(?:[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}\/){0,3}[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$` |
| `shots[].song.db` | number | >= -60; <= 12 |
| `shots[].song.from` | number |  |
| `shots[].song.fade_in` | number | >= 0; <= 10 |
| `shots[].song.fade_out` | number | >= 0; <= 10 |
| `shots[].cut_listen` | map of list | keys `^[a-z][a-z0-9_]{0,23}$` |
| `shots[].cut_listen.<key>` | list | items >= 2; items <= 2 |
| `shots[].scene` | (set by the server) | leave it out |
| `shots[].cardUrl` | (set by the server) | leave it out |
| `film` * | object |  |
| `film.fps` | integer | >= 12; <= 60 |
| `film.width` | integer | >= 240; <= 2160 |
| `film.height` | integer | >= 240; <= 3840 |
| `film.set` * | string | length >= 1; length <= 80; pattern `^[a-z0-9]+(?:-[a-z0-9]+)*$` |
| `film.music` | object |  |
| `film.music.file` * | string | length <= 200; pattern `^(?:[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}\/){0,3}[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$` |
| `film.music.db` | number | >= -60; <= 12 |
| `film.music.start` | number | >= 0 |
| `film.music.min_gap` | number | >= 0; <= 10 |
| `film.music.ambience` | object |  |
| `film.music.ambience.file` * | string | length <= 200; pattern `^(?:[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}\/){0,3}[A-Za-z0-9_-][A-Za-z0-9_.-]{0,99}$` |
| `film.music.ambience.db` | number | >= -60; <= 12 |
| `film.stage` | map of string or number or boolean | keys `^[a-z][a-z0-9_]{0,31}$` |
| `film.stage.<key>` | string or number or boolean |  |
| `film.static` | (set by the server) | leave it out |
| `film.assets` | (set by the server) | leave it out |
| `film.files` | (set by the server) | leave it out |
