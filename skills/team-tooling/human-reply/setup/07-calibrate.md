# Setup 7: Calibrate

Build draft profiles, test them against threads the person really
answered, and fix what reads wrong. One round.

## 1. Draft profiles

Write the profiles in the formats from `human-reply/references/profile-schema.md`,
into `<home>/corpus/draft/` rather than their final place:

- `draft/channels/<channel>.md` for each channel in `channels`, from
  `<channel>.stats.json`, `<channel>.read.json`, the channel module's
  Surfaces table for the Audience and Register columns, and
  `per_channel.<channel>` in `setup.json` for the header and status lines.
  A channel with no `<channel>.read.json` gets empty Phrasebook and Shapes
  sections.
- `draft/profile.md` from `setup.json` and the reconciliation in the read
  step. Carry every voice entry of a channel not rebuilt in this run over
  from its existing profile file unchanged. Borrowed traits already in an
  existing `profile.md` stay. Each line in `"borrowed"` is added under
  Borrowed traits as `<trait> | from <borrow.name> | adopted <today> |
  told: yes`, and the header's `borrowed from` names `borrow.name`. No
  quoted colleague text goes into the profile.

When `setup <channel>` rebuilds one channel, copy the other channels'
existing files into `draft/channels/`, then apply the reconciliation's
Habits changes to them.

## 2. Draft against each held-out thread

For each channel whose `per_channel.<channel>.calibration` is not
`skipped`, and for each thread in `per_channel.<channel>.holdouts`, in
that list's order:

1. Pick the target: the person's earliest record in the thread that
   comes after a message by someone else. The context is everything in
   the thread before the target.
2. Fetch the context through one sonnet subagent, because every tool
   below returns the whole thread, target included, and a draft written
   after seeing the target proves nothing. The subagent fetches the
   thread, picks the target by the rule in step 1, and returns only the
   context messages with their authors and the target's timestamp or id;
   it never returns or quotes the target, and writes nothing to disk.
   Fetch with:
   - Slack: the thread read tool with the channel id and the thread's
     parent ts from the `thread` field.
   - GitHub: `gh api repos/<owner>/<repo>/pulls/<n>/comments` for a
     review thread, keeping the comments whose id or `in_reply_to_id` is
     the root id; `gh api repos/<owner>/<repo>/issues/<n>/comments` plus
     `gh pr view <n> --repo <owner>/<repo> --json title,body` for a
     conversation thread or review summary.
   - Notion: the comments tool with `page_id` and `discussion_id`.

   When the thread has no target, or the fetched context shows nobody but
   the person, drop the thread and say so.
3. Draft a reply to the context with the draft mode in `SKILL.md`, reading
   the profile from `<home>/corpus/draft/` instead of `<home>/`, with the
   ask "reply to the last message" and no other hint. Finish every
   channel's drafts before reading any target.
4. Read the target yourself, then show the draft and the target side by
   side, with the pool the thread came from: `pre-cutoff`, `post-cutoff`,
   `earlier`, or `backfill`.

When fewer than three of a channel's held-out threads have a target,
including when `holdouts` is empty, backfill from threads older than the
sample before giving up. Search one month at a time, going back from
`window.since`, or from the first day of the cutoff month when that is
earlier, for up to 12 months:

- Slack: the collect step's Slack search for that month in both
  `channel_types` windows, with `before:` never later than `window.since`,
  keeping only thread replies.
- GitHub: `gh search prs --commenter <login> --created <that month>`, then
  each PR's review comments with `gh api repos/<owner>/<repo>/pulls/<n>/comments`.
- Notion: the Notion search tool with `created_date_range` set to that
  month, then each page's discussions with the comments tool.

The search runs in the same subagent as step 2, which reads each
candidate thread and returns only the kept threads' context, never the
person's reply. Keep a thread when a message by someone else comes
before the person's reply, skipping threads already in `holdouts` and audiences in
`per_channel.<channel>.excluded_audiences`. Stop when the channel has
three threads with a target. Append each kept thread to
`per_channel.<channel>.holdouts` with pool `backfill`, then run steps 3
and 4 on it; its target is the person's earliest reply in the fetched
thread that comes after someone else's message. Backfilled threads are
used for calibration only and are never written to the corpus.

When no held-out or backfilled thread of a channel has a target, set
`per_channel.<channel>.calibration` to `"skipped"`, add
`"no held-out thread with a reply to calibrate against"` to
`per_channel.<channel>.partial`, tell the person, and skip sections 3 and
4 for that channel.

Otherwise, after all of a channel's threads are shown, ask: "What reads
wrong in my drafts? One sentence per thing." Wait for the answer.

## 3. Adjust

For each thing the person names:

- write a rule under `## Calibration notes` in
  `draft/channels/<channel>.md`, stated as an instruction, such as "never
  open a GitHub reply with a greeting"
- when it is about length, change the surface's budget and note the
  change in the rule; a budget never drops below the module minimum
- when it is about wording, remove or add phrasebook entries, and add a
  "never" line under `## Habits` in `draft/channels/<channel>.md` for
  anything the person never says; `profile.md`'s Banned holds only entries
  two or more channels share, placed by the read step's reconciliation
- when it is about register, amend the surface's Register cell

## 4. Re-draft once

Re-draft the channel's first remaining held-out thread, the first thread
in `per_channel.<channel>.holdouts` that section 2 did not drop, from the
adjusted draft profile, the same way as above, and show it alone. Ask one
yes or no question: "Does this read like you?" Set
`per_channel.<channel>.calibration` to `"accepted"` or `"rejected"`. There
is no second round either way.

On `rejected`, add `"calibration rejected"` to
`per_channel.<channel>.partial` and rewrite the `status` line of
`draft/channels/<channel>.md` from that list, for example
`status: partial (calibration rejected)`.

A channel whose calibration is `skipped` gets no draft and no re-draft.

Add `"calibrate"` to `done`.
