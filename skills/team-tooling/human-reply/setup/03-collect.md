# Setup 3: Collect

Write each chosen channel's messages to `<home>/corpus/<channel>.jsonl`,
one record per line in the shape from `human-reply/references/corpus-record.md`, then
mark hold-out threads. Channels run one at a time, in the order listed in
`setup.json`.

Every path passed to a script is absolute: resolve `<home>` and
`<skill-dir>` once and use the resolved paths. `<py>` is the interpreter
stored in `setup.json`.

A channel listed under `"reused"` in `setup.json` skips sections 1 to 5
and starts at section 6, and its first hold-out pass adds `--reset`.

## 1. Redaction comes first

This skill writes nothing unredacted to disk, not even a temp file.
The session transcript Claude Code keeps under `~/.claude/projects/` may
still hold the raw text the collection tools return.

With Python, records reach disk only through `redact.py`, which reads
JSONL on stdin and appends to `--out`. Pipe a batch in with a quoted
heredoc from Bash:

```
<py> <skill-dir>/scripts/redact.py --out <home>/corpus/slack.jsonl <<'RECORDS'
{"channel": "slack", "surface": "outer DM", ...}
RECORDS
```

or with a single-quoted here-string from PowerShell:

```
@'
{"channel": "slack", "surface": "outer DM", ...}
'@ | <py> <skill-dir>/scripts/redact.py --out <home>/corpus/slack.jsonl
```

Keep the `redact: N of M records touched` line from each batch and add
the touched counts up in `per_channel.<channel>.redacted`.

Without Python, redact by hand using the patterns in
`scripts/redact.py`: a whole private-key block becomes
`<redacted:private-key>`, and every match of the other patterns becomes
`<redacted:kind>` with the kind named beside the pattern. Before the first
record of the run is written, redact every case in
`human-reply/references/redaction-check.md` and compare with its expected output. On
any miss, stop setup and say Python is required to collect. On a pass,
append records with the shell and set `per_channel.<channel>.redaction`
to `"model"`; the finish step reads it.

## 2. Resume point

For Slack and Notion, when `<home>/corpus/<channel>.jsonl` already has
records, run:

```
<py> <skill-dir>/scripts/corpus.py oldest --corpus <home>/corpus/<channel>.jsonl
```

and continue collecting backwards from that date instead of from
`window.until`. Duplicates are removed later by `normalize`. Without
Python, read the oldest `ts` from the file.

GitHub resumes by repo instead: skip every repo already in
`per_channel.github.github_repos_done`.

## 3. Slack

Get the person's own Slack user id from the search tool's description or
from the user search tool.

Search one calendar month at a time, newest month first, and run two
windows per month: one with `channel_types` set to
`public_channel,private_channel`, one with `im,mpim`. The newest month
ends at `window.until` and the oldest starts at `window.since`. Each call:

- `query`: `from:<@USER_ID> after:<last day of the previous month> before:<first day of the next month>`
- `sort`: `timestamp`, `sort_dir`: `desc`, `limit`: 20, `include_context`: false
- `cursor`: the cursor from the previous page, empty on the first page

A window ends when no cursor comes back, or when a page is short and the
page before it was short too. An empty page after a full one does not end
the window; ask for the next page. The search stops at 20 pages. When a
window reaches page 20, start a new window with the same `after:` and
`before:` set to the day after the oldest message captured so far; the
one-day overlap is removed by `normalize`.

Build one record per message:

| Field | Value |
|---|---|
| `surface` | a 1:1 DM whose other member's id is in `inner_circle`: `inner-circle DM`; any other 1:1 DM: `outer DM`; a group DM: `group DM`; a channel message with a thread timestamp different from its own: `channel thread reply`; any other channel message: `channel new post` at 120 words or fewer, `write-up` over 120 |
| `ts` | the message timestamp converted to UTC `YYYY-MM-DDTHH:MM:SSZ` |
| `audience` | the channel or DM id |
| `thread` | `<channel id>/<thread ts>`, or `<channel id>/<ts>` outside a thread |
| `others` | 1 for a 1:1 DM; the member count minus one for a group DM, or 2 when unknown; 1 for a thread reply; 1 for a top-level post that shows replies, 0 otherwise |
| `text` | the message text as returned |

Pipe each page's records through redaction before asking for the next
page. After each month, run:

```
<py> <skill-dir>/scripts/corpus.py normalize --corpus <home>/corpus/slack.jsonl --cap 1500
```

Stop when it reports 1500 kept or the month is before `window.since`.

## 4. GitHub

```
gh api user --jq .login
<py> <skill-dir>/scripts/github_records.py repos --login <login> --since <window.since>
```

For each repo it prints, collect and redact in one pipe, then add the repo
to `per_channel.github.github_repos_done` so a resumed run skips it:

```
<py> <skill-dir>/scripts/github_records.py records --repo <owner/name> --login <login> --since <window.since> --until <window.until> | <py> <skill-dir>/scripts/redact.py --out <home>/corpus/github.jsonl
```

A repo that fails with a 403 or 404 is skipped and named in the summary.
After the last repo, run `normalize` with `--cap 1500`.

Without Python, call the same `gh search` and `gh api` endpoints that
`scripts/github_records.py` calls and build the same records by hand.

## 5. Notion

1. Fetch `{"id": "self"}` with the Notion fetch tool to get the person's
   user id.
2. List pages: the recent pages tool with `limit` 200 and its cursor, plus
   the Notion search tool with `filters.created_by_user_ids` set to the
   person and `filters.created_date_range.start_date` set to
   `window.since`. Drop repeats.
3. For each page, call the comments tool twice: once with `page_id` only,
   which returns page-level discussions, and once with
   `include_all_blocks: true` and `include_resolved: true`. A discussion
   in the first answer is a `page comment` discussion; one only in the
   second is an `inline comment` discussion.
4. For each comment the person wrote inside the window, build a record:
   `audience` is the page id, `thread` is `<page id>/<discussion id>`,
   `others` is the number of other authors in the discussion.
5. Pipe each page's records through redaction. Stop at 500 records after
   `normalize --cap 500`, or when the pages run out.

Tell the person that Notion comments are reached page by page, so the
sample covers only pages they visited or created recently.

## 6. Validate

For each channel file:

```
<py> <skill-dir>/scripts/corpus.py validate --corpus <home>/corpus/<channel>.jsonl --module <skill-dir>/channels/<channel>.md
```

A record that fails is fixed by rebuilding it from the source, never by
editing the redacted text. Without Python, check every field against
`human-reply/references/corpus-record.md`.

## 7. Hold out, first pass

For each channel in `channels`:

```
<py> <skill-dir>/scripts/corpus.py holdout --corpus <home>/corpus/<channel>.jsonl --cutoff <cutoff> --seed <seed>
```

This marks up to three pre-cutoff threads, or threads from the whole
window when the cutoff is `never`, where someone other than the person
took part. Store the printed list as `per_channel.<channel>.holdouts`. The
filter step runs the second pass when a channel got fewer than three.

Without Python, pick the threads at random under the same rule and set
`held_out` to `true` on every record of each chosen thread.

Add `"collect"` to `done`, and print per channel: records kept, date of
the oldest record, records touched by redaction, and hold-out threads
marked.
