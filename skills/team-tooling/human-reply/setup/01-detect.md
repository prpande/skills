# Setup 1: Detect

Find out what can be collected before asking the person anything.

`<skill-dir>` below is the folder holding this skill's `SKILL.md`. `<home>`
is `~/.claude/human-reply`. Setup keeps its answers and progress in
`<home>/corpus/setup.json`; every later step reads it and writes back what
it decides.

## 1. Leftovers from an interrupted run

If `<home>/corpus/` exists:

- Delete every `borrow-*.jsonl` in it without asking. A colleague sample
  never outlives the run that collected it.
- If `setup.json` exists, say which step it reached and which channels it
  covers, and ask one question: resume, or start over. Start over deletes
  `<home>/corpus/` entirely. Resume skips to the first step `setup.json`
  does not mark done; the collect step picks up from the records on disk.
- If `setup.json` does not exist but `<channel>.jsonl` files do, they are
  a sample kept by an earlier finished setup. Ask one question: collect
  fresh, which deletes them, or reuse them. Reuse marks those channels as
  collected in `setup.json` under `"reused"`; the collect step then skips
  straight to validation for them and runs the first hold-out pass with
  `--reset`.

## 2. Probe the channels

| Channel | Connected when | Collector |
|---|---|---|
| Slack | a Slack message search tool that covers DMs is listed, such as `slack_search_public_and_private` | month-windowed search from the person |
| GitHub | `gh auth status` exits 0 | `<skill-dir>/scripts/github_records.py` |
| Notion | a Notion comments tool such as `notion-get-comments` is listed | recent pages, comments per page |

Deferred tools count as listed: search for them with ToolSearch before
deciding a channel is not connected.

## 3. Probe Python

Run `python3 --version`, then `python --version` if the first fails. Keep
the first one that prints `Python 3.8` or later as the interpreter for
every script call.

If neither works, say:

- the measuring step will run inside the model instead
- that costs more tokens and produces estimates in ranges, not counts
- redaction will be done by the model and checked against a fixture first
- Python installs from https://www.python.org/downloads/

Then ask: install and rerun setup, or continue without Python. Record
`method: measured` when Python works and `method: estimated` otherwise.

## 4. Report and choose

Print one table: channel, connected or not, collector. Then ask which of
the connected channels to set up, and say in one line that setup writes
nothing unredacted itself, but the session transcript Claude Code keeps
under `~/.claude/projects/` may still hold the raw text of collected
messages. When the person invoked
`setup <channel>`, confirm that one channel instead of asking. A channel
that is not connected is recorded as skipped with the reason, and the
finish step names it.

## 5. Write the state

Write `<home>/corpus/setup.json`:

```
{
  "started": "2026-09-16",
  "done": ["detect"],
  "python": "python3",
  "method": "measured",
  "channels": ["slack", "github"],
  "skipped": {"notion": "no Notion comments tool is connected"},
  "seed": 48213,
  "per_channel": {"slack": {}, "github": {}}
}
```

`per_channel` holds one object per channel in `channels`. Later steps
write that channel's own state into it and name each key as
`per_channel.<channel>.<key>`: `redacted`, `redaction`, `holdouts`,
`github_repos_done`, `drop_rate_first`, `threshold`, `dropped`, `method`,
`calibration`, and `partial`, a list of reasons. Everything else in
`setup.json` is shared by all channels.

`python` is `null` when there is no interpreter. `seed` is any integer
from 1 to 99999; the hold-out steps use it so a resumed run picks the same
threads. When `setup <channel>` rebuilds one channel and profiles already
exist, `channels` holds that one channel only.
