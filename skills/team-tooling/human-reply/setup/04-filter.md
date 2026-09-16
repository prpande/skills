# Setup 4: Filter

Drop the messages that read as AI-written, using the score and threshold
in `human-reply/references/ai-filter.md` and the pattern list in each channel
module's `ai-filter` block. Channels run one at a time.

## 1. First run and first read

```
<py> <skill-dir>/scripts/ai_filter.py --corpus <home>/corpus/<channel>.jsonl --module <skill-dir>/channels/<channel>.md --reference <skill-dir>/references/ai-filter.md --cutoff <cutoff> --kept <home>/corpus/<channel>.kept.jsonl
```

It prints `total`, `scanned`, `dropped`, `drop_rate`, `total_drop_rate`,
`threshold`, and up to five dropped `samples`, each with the patterns it
hit. `drop_rate` is dropped over scanned and is the rate every check below
reads; `total_drop_rate` is dropped over all records and is shown only.
Store `drop_rate` as `per_channel.<channel>.drop_rate_first`.

Show the person the drop count out of the scanned count and out of the
total, and the five samples with their hits, each sample cut to its first
300 characters.

## 2. The one adjustment

When `per_channel.<channel>.drop_rate_first` is over 0.4, say that more
than 40 percent of the scanned messages were dropped and name the two
likely causes:

- the cutoff month is wrong, and messages from before AI drafting are
  being scanned
- the person writes in this shape by default

Ask them to pick one: re-ask the cutoff, or raise the threshold by one.

When `per_channel.<channel>.drop_rate_first` is 0.4 or less, ask whether
the drops look right, and offer the same adjustment as optional: a new
threshold from 1 up to 4, or no change.

Only one adjustment per channel:

- **New cutoff.** Ask the cutoff question from the interview step again
  and store the answer as the top-level `cutoff`. The cutoff is shared,
  so the change applies to every channel. The old hold-outs were chosen
  against the old date: for this channel and for every channel already
  filtered, clear and redo them as in the collect step's hold-out first
  pass, storing each list as `per_channel.<channel>.holdouts`:

  ```
  <py> <skill-dir>/scripts/corpus.py holdout --corpus <home>/corpus/<channel>.jsonl --cutoff <new cutoff> --seed <seed> --reset
  ```

  Then redo this step from section 1 for every channel already filtered.

- **New threshold.** Lower is allowed to any value from 1. Higher is
  allowed by one point, to 4. Store `<n>` as
  `per_channel.<channel>.threshold`.

Rerun the filter command with the new `--cutoff` or `--threshold`. A
channel with no adjustment keeps threshold 3 and needs no rerun.

## 3. Second read

Read `drop_rate` from the latest run. When it is over 0.4, do not loop:
keep the filtered set, add
`"drop rate <rate> after the threshold adjustment"` to
`per_channel.<channel>.partial`, and tell the person the channel will be
marked partial for that reason.

## 4. Enough records

Count the records in `<channel>.kept.jsonl` that are not held out. Under
100, there is no profile for this channel: say the sample is too small to
measure and offer two ways on:

- widen the window: ask the window question again, then rerun the collect
  step for this channel
- move the cutoff later: ask the cutoff question again, then rerun this
  step

When the person declines both, move the channel from `channels` to
`skipped` with the reason `fewer than 100 records after the filter`.

## 5. Hold out, second pass

Skip when the channel already has three hold-out threads or the cutoff is
`never`. Otherwise:

```
<py> <skill-dir>/scripts/corpus.py holdout --corpus <home>/corpus/<channel>.jsonl --cutoff <cutoff> --seed <seed> --passed <home>/corpus/<channel>.kept.jsonl
```

Threads already held out come back with pool `earlier`. New ones come
from post-cutoff threads whose every message passed the filter, with pool
`post-cutoff`. Store the list as `per_channel.<channel>.holdouts`, then
rerun the filter command with the channel's threshold so the kept file
carries the new marks.

When a channel still has no hold-out thread, set
`per_channel.<channel>.calibration` to `"skipped"` and add
`"no thread with another participant to calibrate against"` to
`per_channel.<channel>.partial`.

The colleague sample is collected and filtered in the read step.

## Without Python

Score by reading. For each message in scope under `human-reply/references/ai-filter.md`,
check each pattern id the channel lists, skipping ids whose `exempt:`
list names the message's surface. Record dropped record ids in
`per_channel.<channel>.dropped` instead of writing a kept file; later
steps treat a dropped id as absent. The reads, the adjustment, the
100-record check, and the hold-out rules are the same.

Add `"filter"` to `done`.
