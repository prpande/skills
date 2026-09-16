# Setup 6: Read

Readers turn a channel's messages into shapes, a phrasebook, and habits.
Numbers come from the measure step; readers never count words.

## 1. The sample

Readers read `<home>/corpus/<channel>.kept.jsonl` and skip every
held-out record. Without Python there is no kept file: readers read
`<home>/corpus/<channel>.jsonl` and skip every held-out record and every
id in `per_channel.<channel>.dropped`. The sample is fixed so three
readers see the same messages:

- every record over sixty words, newest first, up to 300
- 200 records of sixty words or fewer, taken round-robin across the
  surfaces in the module's surface order: the newest untaken record of
  each surface in turn, skipping a surface that has run out, until 200
  are taken or every surface has run out

## 2. Three readers per channel

Dispatch three subagents on the sonnet model for each channel, in
parallel. Each gets this prompt with the slots filled:

````
Read the messages one person wrote on <channel>, from <corpus path>.
Skip records whose held_out is true and these ids (<audience>/<ts>): <dropped ids or "none">.
Read this sample: every record over sixty words, newest first, up to 300;
then 200 records of sixty words or fewer, round-robin across surfaces in
this order, taking the newest untaken record of each surface in turn and
skipping a surface that has run out, until 200 are taken or all run out:
<surface names from the module>.
Count words by splitting on whitespace after replacing each fenced block
and each link with one word.

The platform's shape skeletons are in <module path> under Shapes. Use
them as a starting vocabulary, not a limit.

Return only a JSON object in the reader return format from
<skill-dir>/references/profile-schema.md. Rules:
- Every example is a message from the sample, copied exactly except that
  every person's name becomes <name> and every team or squad name becomes
  <team>. Placeholders like <redacted:kind> stay as they are.
- Give two examples for a shape on a surface with 30 or more records, one
  otherwise. Surface record counts: <surface: records, from stats.json>.
- Phrasebook phrases are literal text the person wrote, three to eight
  words, grouped by role.
- Write nothing to disk.
````

## 3. Check each return

A return fails when it is not valid JSON in the reader return format, or
when any surface with 30 or more records has fewer than two examples
across all its shapes, a surface with no shape included. Re-run a failed
reader once with a fresh subagent. When the second attempt fails too,
drop that reader and add `"reader returned off-schema twice"` to
`per_channel.<channel>.partial`. With one reader left, there is nothing
to vote on: use its return as is.

With no reader left, skip section 4 for the channel and write no
`<channel>.read.json`, so the channel gets no shapes, phrasebook, or
voice entries. Add `"no reader returned a valid read"` to
`per_channel.<channel>.partial` and tell the person.

## 4. Merge within a channel

- **Shapes, disagreement, typing habits, sign-offs, banned.** Keep an
  entry two or more readers returned. Two shapes are the same when they
  are on the same surface and their skeletons have the same slots in the
  same order. Merge their examples, drop repeats, and keep two, or one on
  a surface under 30 records.
- **Phrasebook.** No vote. Count each candidate phrase's records in the
  channel corpus, case-insensitively, ignoring held-out records:

  ```
  grep -v '"held_out": true' <home>/corpus/<channel>.kept.jsonl | grep -ciF "<phrase>"
  ```

  Without Python, count in `<home>/corpus/<channel>.jsonl` instead,
  leaving out held-out records and ids in `per_channel.<channel>.dropped`.
  Keep the phrase when the count is 2 or more, with that count.

Write the merged result to `<home>/corpus/<channel>.read.json` in the
reader return format, with a `count` on each phrasebook entry.

## 5. Reconcile across channels

Voice entries are the hedges from the phrasebook, typing habits,
disagreement, sign-offs, and banned. Build a map from each entry to the
channels that returned it:

1. Start from the existing profile files, when there are any. An entry in
   `<home>/profile.md` carries its channels at the end of its line. An
   entry under `## Habits` in `<home>/channels/<channel>.md` belongs to
   that channel.
2. Remove every entry of the channels read in this run, then add their
   entries from each `<channel>.read.json`.
3. An entry with two or more channels goes into `profile.md`, with its
   channels listed. An entry with one channel goes under that channel's
   `## Habits`.

This also demotes: an entry in `profile.md` that a rebuilt channel no
longer returns drops to the Habits of the channels that still have it.
With one channel set up in total, `profile.md` voice sections stay empty
and every entry is a Habit.

Two entries are the same when they describe the same habit, even in
different words; keep the wording of the first.

## 6. Colleague traits

Skip unless `borrow` is set. The colleague sample is collected, filtered,
read, and deleted in this section, so no borrow file outlives it.

1. Run the collect step's collector for `borrow.channel` with the
   colleague as author, redacting as the collect step does, into
   `<home>/corpus/borrow-<channel>.jsonl`:
   - Slack: `from:<@author id>`, with `channel_types` set to
     `public_channel,private_channel` only.
   - GitHub: `github_records.py` with `--login <colleague login>`.
   - Notion: comments whose author is the colleague's user id.

   Cap at 300 with `normalize --cap 300`, then run `corpus.py validate`
   on the file. Borrow records are never held out and never measured.
2. Filter it:

   ```
   <py> <skill-dir>/scripts/ai_filter.py --corpus <home>/corpus/borrow-<channel>.jsonl --module <skill-dir>/channels/<channel>.md --reference <skill-dir>/references/ai-filter.md --cutoff never --borrow --kept <home>/corpus/borrow-<channel>.kept.jsonl
   ```

   Report the drop count. No adjustment is offered on a colleague sample.
   Without Python, score every colleague message over sixty words by
   reading, as the filter step describes, and leave the dropped ones out
   of the reader's path by writing the rest to the kept file.
3. Dispatch one sonnet subagent on
   `<home>/corpus/borrow-<channel>.kept.jsonl`:

````
Read the messages in <path>. Return only a JSON list of five to ten
traits of how this person writes, each one line that someone else could
follow, such as "opens replies with the verdict, no greeting" or "uses >
quote-reply for multi-part answers". Do not quote any message. Write
nothing to disk.
````

Show the traits numbered and ask which to adopt. Store the adopted lines
as `"borrowed"` in `setup.json`. Delete
`<home>/corpus/borrow-<channel>.jsonl` and its kept file as soon as the
answer is in.

Add `"read"` to `done`.
