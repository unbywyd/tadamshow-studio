# Submitting an episode, the studio version, the owner's remarks

An episode goes public only after the project's owner approves it. The person decides when it is sent: submit
**only after they explicitly say so** («отправляй», "send it").

## Before submitting

`tadam status` lists, per episode, what still stands between it and a submission (`missing`), with codes:

| Code | What to do |
|---|---|
| `card` | fill the world's description and the bible's idea (world.json) |
| `script` | the episode has no script on the server: push it |
| `puppet` | a hero of the cast has a puppet that failed its check: draw it again, push |
| `check` | the last push has errors: `tadam check`, fix, push |
| `translation` | a text lacks one of the world's languages |
| `studio_version` | no studio version, or it is older than the current film (below) |
| `published` / `not_published` / `nothing` / `episode` | the kind does not fit (already out, not out yet, nothing waits) |

## The studio version

The owner watches a real film of the episode, made on the site from the person's own scene:

1. `tadam push`; the push prints the draft's link.
2. On the site the person records every role (QR on the phone; friends may take roles), makes the film
   («Собрать ролик») and keeps it.
3. The person presses «make studio version» on the film's page, or you run `tadam studio-version <episode>
   <videoId>` with the id they give you (from the video's page). `none` unmarks.
   A film made before the episode's film last changed is refused (`version_stale`): make it again.

Any later push that changes what is seen (shots, camera, pictures, narration) makes the film old: make and mark
a new one before submitting.

## Submit, and the remarks loop

```
tadam submit <episode> "<a word to the owner>"
```

- It reads `missing` first and refuses with the list while anything is missing; nothing is sent then.
- A published episode goes as a **revision** (`--kind` names it if needed). A revision that would make other
  people's sent roles stale is refused: make a new episode.
- While the submission is open, a push of that episode is refused: `tadam withdraw` first (`--episode <n>` or
  `--id <id>` when the world has more than one open).

`tadam status` then shows the open submissions with their **threads**: the owner's remarks, each one pointing at
a shot when it says so (`remark on sh3: the camera is too close`). When it is **returned**:

1. Read every remark to the person in plain words; agree what to change.
2. Fix it in the folder, `tadam check`, `tadam frames <n> --sheet` and look, show `tadam play`.
3. `tadam push`, make and mark the new studio version.
4. `tadam submit <episode> "<what changed>"` — the same submission reopens, the thread goes on.

`tadam reply "<text>" [--shot sh3]` answers in the thread (a question, an explanation) without resubmitting.
Approved → the episode is published (the world too, with its first episode). Rejected → it says why; it is final.

## Taking it off the site

`tadam unpublish "<reason>"` (the whole world) or `--episode <n>`: a request to the owner, always with a reason.
After approval it leaves the site; the films people made stay theirs.
