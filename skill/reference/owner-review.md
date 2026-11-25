# The owner's review (the project's owner only)

Only for the owner of TadamShow (staff admin and above). An editor never needs this page; if the person is not
the owner, these commands answer that a staff key is needed — do not look for a way around it.

The queue lives on the server's owner side (`/api/admin/studio/*`), where a studio key does not work: the owner
stores their **staff key** once, typed hidden at their own keyboard — `tadam login --staff` (or keeps it in
`TADAM_STAFF_KEY`, e.g. `skey run --only TADAM_STAFF_KEY -- tadam review list`). Never ask for it in the chat.

```
tadam review list [--all | --status changes] [--kind publish] [--of <slug>]   the queue, oldest first
tadam review show <id> [--lang en] [--json]                                   one submission, top to bottom
tadam review return <id> "<remarks>" [--shot sh3 "<remark>"]...               back to the author with remarks
tadam review reply <id> "<text>" [--shot sh3]                                 a message in the thread
tadam review approve <id> [--note "..."] [--stale-version] [--confirm-breaking] [--slug new-address]
tadam review reject <id> "<reason>"
```

`review show` prints what the admin's review screen shows: the studio video's link (watch it first), the world's
card and bible, the episode, the heroes (puppet passed or not, new ones), the script **by shots** (lines with
their heroes and hints, narration, title cards), the sets, every picture and sound **with its source**, the
server's check, what is missing, for a revision its class, reasons and impact (how many sent roles of other
people go stale), the revisions, and the thread.

How to help the owner:

1. `review list`, then `review show <id>`; tell the owner in plain words what the episode is, what the check and
   the sources say, anything that looks off (a file without a source, a borderline word, an old studio video).
2. Remarks: write them with the owner, each one tied to its shot when it is about one
   (`--shot sh4 "the camera is too close"`), and `review return` them. Returning needs no confirmation.
3. A small thing the owner would rather fix than return: `tadam pull <slug>` (the command is in `review show`),
   change it, `tadam check`, `tadam push`; the author is told and their next push needs a pull. If the change is
   visible in the film, the studio version must be made again before approving.
4. **approve** and **reject** are the owner's own decisions: the command asks the owner to type the submission's
   id at their own keyboard and refuses without one. Never type it, never pipe it, never run them on the
   owner's behalf. `--stale-version` (the video is older than the film) and `--confirm-breaking` (other people's
   sent roles go stale) only after the owner said yes to exactly that; `--slug` only on a world's first
   publication.
