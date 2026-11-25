# The life of a world, and changes after publishing

```
world:    draft ──(its first episode approved)──▶ live ──(unpublishing approved)──▶ hidden
episode:  script ──submit──▶ review ──approve──▶ published ──(unpublishing approved)──▶ archived
                     ▲            │
                     └── returned with remarks / rejected (always with a text)
```

1. `tadam push` — the world and its episodes become a **draft** on the server, seen only by its editor.
2. On the site the editor records every role (QR on the phone), makes the film and presses «make studio version».
3. Submission (after the person says «send it»: `tadam submit`, see [submitting](submitting.md)): the owner
   watches the studio version and approves or returns it with remarks (`tadam status` shows them; a remark can
   point at a shot: «sh4: the camera is too close»).
4. A world goes for approval only together with its first episode.

An episode can be submitted when: the card and the bible are filled; every hero of the episode has a puppet that
passed its check; the script has no errors; the studio version is made from the CURRENT revision; texts exist in
every language of the world; every picture and sound has its source (sources.json). `tadam status` lists what
is missing. While a submission is open, pushing that episode is refused: `tadam withdraw` first.

A published episode's later push is sent as a **revision** (`tadam submit <n>` picks the kind); taking an episode
or the whole world off the site is `tadam unpublish "<reason>" [--episode <n>]`, also approved by the owner.

## Changes after publishing: the classes

Every push of a published episode is classed by the server, comparing it with what viewers see:

| Class | What | How it goes out |
|---|---|---|
| **A** texts | world title, tagline, description; hero name and trait; episode title, logline, teaser; `remark` and `hint`; a new translation | at once (the owner can roll it back) |
| **B** revision | narration text and voice, title cards, music, camera and placing, pictures of puppets and sets, covers | a revision request; recorded roles and finished films stay as they are |
| **C** breaking | adding, removing or rewording a line; the number of phrases; anything that changes the recording steps or how roles are cut | refused when it would make other people's sent roles stale: make a NEW episode instead |

A line's text is class C, not A: the people who recorded it said the old words. So: once an episode is published,
never change `text`, `kind`, `phrases`, `say`/`listen` of recorded steps, and never rename step keys. Want a
different line? A new episode.

The push answer names the class per episode, the reasons and the impact (`staleRoles`: how many sent roles of
other people go stale). Show it to the person in plain words.

## Working with the project's owner

The owner of TadamShow may pull any world (`tadam pull <slug>`), change it and push it back; the author is told.
Your next push is then refused («pull first»): `tadam pull`, merge every `<file>.server` copy into its file (keep
both sides' intent; ask the person when they conflict), delete the copy, `tadam check`, `tadam diff` to see the
result, push. Only the owner may push a breaking change with `--confirm`, and only after saying yes to exactly
the impact shown.
