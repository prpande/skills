# Setup 7: Calibrate

Build draft profiles, test them against threads the person really
answered, and fix what reads wrong. One round.

## 1. Draft profiles

Write the profiles in the formats from `human-reply/references/profile-schema.md`,
into `<home>/corpus/draft/` rather than their final place:

- `draft/channels/<channel>.md` for each channel in `channels`, from
  `<channel>.stats.json`, `<channel>.read.json`, the channel module's
  Surfaces table for the Audience and Register columns, and the channel's
  entries in `setup.json` for the header and status lines.
- `draft/profile.md` from `setup.json` and the reconciliation in the read
  step. Carry every voice entry of a channel not rebuilt in this run over
  from its existing profile file unchanged. Borrowed traits already in an
  existing `profile.md` stay, and the lines in `"borrowed"` are added with
  today's date.

When `setup <channel>` rebuilds one channel, copy the other channels'
existing files into `draft/channels/`, then apply the reconciliation's
Habits changes to them.

## 2. Draft against each held-out thread

For each channel whose `"calibration"` is not `skipped`, and for each
thread in its `"holdouts"`:

1. Pick the target: the person's earliest record in the thread that
   comes after a message by someone else. The context is everything in
   the thread before the target.
2. Fetch the context:
   - Slack: the thread read tool with the channel id and the thread's
     parent ts from the `thread` field.
   - GitHub: `gh api repos/<owner>/<repo>/pulls/<n>/comments` for a
     review thread, keeping the comments whose id or `in_reply_to_id` is
     the root id; `gh api repos/<owner>/<repo>/issues/<n>/comments` plus
     `gh pr view <n> --repo <owner>/<repo> --json title,body` for a
     conversation thread or review summary.
   - Notion: the comments tool with `page_id` and `discussion_id`.

   When the fetched context shows nobody but the person, drop the thread
   and say so.
3. Draft a reply to the context with the draft mode in `SKILL.md`, reading
   the profile from `<home>/corpus/draft/` instead of `<home>/`, with the
   ask "reply to the last message" and no other hint. Do not look at the
   target first.
4. Show the draft and the target side by side, with the pool the thread
   came from: `pre-cutoff`, `post-cutoff`, or `earlier`.

After all of a channel's threads are shown, ask: "What reads wrong in my
drafts? One sentence per thing." Wait for the answer.

## 3. Adjust

For each thing the person names:

- write a rule under `## Calibration notes` in
  `draft/channels/<channel>.md`, stated as an instruction, such as "never
  open a GitHub reply with a greeting"
- when it is about length, change the surface's budget and note the
  change in the rule; a budget never drops below the module minimum
- when it is about wording, remove or add phrasebook entries, and add a
  line under Banned for anything the person never says
- when it is about register, amend the surface's Register cell

## 4. Re-draft once

Re-draft the channel's first remaining held-out thread from the adjusted
draft profile, the same way as above, and show it alone. Ask one yes or
no question: "Does this read like you?" Store `"calibration": "accepted"`
or `"calibration": "rejected"` for the channel. There is no second round
either way; a rejected channel is named in the finish summary.

A channel with `"calibration": "skipped"` gets no draft and no re-draft.

Add `"calibrate"` to `done`.
