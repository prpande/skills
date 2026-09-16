# Setup 5: Measure

Turn each channel's kept records into numbers. Held-out records are never
measured.

## With Python

```
<py> <skill-dir>/scripts/measure.py --corpus <home>/corpus/<channel>.kept.jsonl --module <skill-dir>/channels/<channel>.md --cutoff <cutoff> --out <home>/corpus/<channel>.stats.json
```

`stats.json` holds, per surface in the module: `records`,
`pre_cutoff_records`, `median`, `p75`, `p90`, `budget`, `label`, and
`over_budget`; then `pattern_rates` over messages longer than sixty
words, per-quarter `quarters` with the 90th percentile and the share over
150 words, and `long_message_ids`.

A surface with 30 or more pre-cutoff records has a budget from its own
90th percentile, rounded up to ten and floored at the module minimum, and
`label: measured`. Any other surface takes the module default and
`label: estimated`.

When the script exits non-zero, show its error and ask whether to
estimate this channel instead. Do not switch without the answer. On a yes,
follow the section below for this channel only and set
`per_channel.<channel>.method` to `"estimated"`.

## No pre-cutoff records

When every surface in a channel has `pre_cutoff_records` of 0, say the
budgets have nothing from before the cutoff to measure and offer to widen
the window, which reruns the collect and filter steps for the channel.
When the person declines, keep the stats as they are, where every surface
is already on its default and labelled estimated, and add
`"budgets not measured: no messages before the cutoff"` to
`per_channel.<channel>.partial`.

## Without Python

Dispatch one subagent per channel on the sonnet model. Give it:

- the channel module path and the corpus path
- the record ids to ignore: held-out records and ids in
  `per_channel.<channel>.dropped`
- the cutoff, and the word-counting rule from
  `human-reply/references/corpus-record.md`

Ask it to read a stratified sample of 300 records spread across the
surfaces in proportion to their counts, and to write
`<home>/corpus/<channel>.stats.json` with the same fields as the script,
with these differences:

- `"method": "estimated"`
- `median`, `p75`, and `p90` are ranges such as `"15-25"`
- the budget is the upper bound of the `p90` range, rounded up to ten and
  floored at the module minimum; `p90_bucket` keeps the range beside it
- every pattern rate is rounded to the nearest 0.1
- every surface row has `label: estimated`

Check the file parses as JSON before moving on.

Add `"measure"` to `done`, and print per channel a table of surface,
records, pre-cutoff records, budget, and label.
