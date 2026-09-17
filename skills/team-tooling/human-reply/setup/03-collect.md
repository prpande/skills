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
`<redacted:private-key>`, and every match of the other
`SOURCE_PATTERNS` becomes `<redacted:kind>` with the kind named beside the
pattern. Then apply `SKILL_LOCAL_PATTERNS` in order: a `pwd=` URL value,
a `Cookie:` or `Set-Cookie:` header value, a session or tracking cookie
value, and a Bearer token of 20 or more characters. Each keeps the text
before the value and replaces only the value, as in `pwd=<redacted:password>`,
and skips a value that is already a placeholder. Before the first
record of the run is written, redact every case in
`human-reply/references/redaction-check.md` and compare with its expected output. On
any miss, stop setup and say Python is required to collect. On a pass,
append records with the shell and set `per_channel.<channel>.redaction`
to `"model"`; the finish step reads it.

## 2. Resume point

For Slack and Notion, when `<home>/corpus/<channel>.jsonl` already has
records, resume the pass named in `per_channel.<channel>.pass` (section
3). In the `pre` pass, or when the cutoff is `never`, run:

```
<py> <skill-dir>/scripts/corpus.py oldest --corpus <home>/corpus/<channel>.jsonl
```

and continue collecting backwards from that date instead of from where
the pass starts. In the `post` pass, add `--from-month <cutoff>` so
pre-cutoff records are ignored; when it prints `none`, start the `post`
pass from `window.until`. Duplicates are removed later by `normalize`.
Without Python, read the oldest `ts` from the file, counting only records
from the cutoff month on in the `post` pass.

GitHub resumes by repo instead: skip every repo already in
`per_channel.github.github_repos_done`.

On every run of this step, first or later, each collector skips the
audiences in `per_channel.<channel>.excluded_audiences` (section 7).

## 3. Slack

Get the person's own Slack user id from the search tool's description or
from the user search tool.

With the cutoff `never`, collect in one pass from `window.until` back to
`window.since`. With a cutoff month, collect in two passes, so the cap
fills first with pre-cutoff messages, the ones budgets are measured from:

1. `pre`: from the last day of the month before the cutoff back to
   `window.since`.
2. `post`, only when `pre` ended below the cap: from `window.until` back
   to the first day of the cutoff month.

Both passes stay inside the window; a pass with no day in the window is
skipped. Store `per_channel.slack.pass` as `pre` or `post` when a pass
starts.

Within a pass, search one calendar month at a time, newest month first,
and run two windows per month: one with `channel_types` set to
`public_channel,private_channel`, one with `im,mpim`. The newest month
ends where the pass starts and the oldest month begins where it ends.

Each month gets a quota, so the sample covers the whole pass instead of
its newest months: the room left under the cap when the pass starts
(1500 for `pre`, 1500 minus the records kept for `post`), divided by the
months in the pass, rounded up. Store it as `per_channel.slack.quota`.
The channels window runs first and stops at half the quota, rounded up;
the DM window stops at the quota minus the records the channels window
took. Count only records built, not skipped messages.

Each call:

- `query`: `from:<@USER_ID> after:<last day of the previous month> before:<first day of the next month>`

  The angle brackets are literal `<` and `>` characters. An HTML-entity
  form such as `&lt;@USER_ID&gt;` returns "No results found" with no
  error.

- `sort`: `timestamp`, `sort_dir`: `desc`, `limit`: 20, `include_context`: false
- `cursor`: the cursor from the previous page, empty on the first page

A window ends when it reaches its share of the quota, when no cursor
comes back, or when a page is short and the page before it was short too. An empty page after a full one does not end
the window; ask for the next page. The search stops at 20 pages. When a
window reaches page 20, start a new window with the same `after:` and
`before:` set to the day after the oldest message captured so far; the
one-day overlap is removed by `normalize`.

Build one record per message. Skip a message in the person's own
self-DM (the DM whose other member is the person), and skip a message
whose text is empty after trimming, such as an attachment with no text.

| Field | Value |
|---|---|
| `surface` | a 1:1 DM whose other member's id is in `inner_circle`: `inner-circle DM`; any other 1:1 DM: `outer DM`; a group DM: `group DM`; a channel message with a thread timestamp different from its own: `channel thread reply`; any other channel message: `channel new post` at 120 words or fewer, `write-up` over 120 |
| `ts` | the message timestamp converted to UTC `YYYY-MM-DDTHH:MM:SSZ` |
| `audience` | the channel or DM id |
| `thread` | `<channel id>/<thread ts>`, or `<channel id>/<ts>` outside a thread |
| `others` | the participants other than the person within the record's `thread` id: a DM or group DM message outside a thread: 0, since its thread id holds only that message; a thread reply: 1; a top-level channel post: 1 when it shows replies, 0 otherwise; a thread reply inside a DM or group DM: 1 |
| `text` | the message text as returned |

Pipe each page's records through redaction before asking for the next
page. After each month, run the command below. When it trims to the cap,
it keeps the newest records of every month in turn, so no month is
dropped whole:

```
<py> <skill-dir>/scripts/corpus.py normalize --corpus <home>/corpus/slack.jsonl --cap 1500 --cutoff <cutoff>
```

Then check the month's coverage. When both windows returned no messages
and the month is not before the person's first Slack message, check the
query text against the form above and run the month once more. A month
still empty after that goes into `per_channel.slack.empty_months` as
`YYYY-MM`.

End the pass when its oldest month is done. A resumed pass reuses the
stored quota.

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
After the last repo, run `normalize` with `--cap 1500 --cutoff <cutoff>`.

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
4. For each comment the person wrote inside the current pass's dates,
   build a record: `audience` is the page id, `thread` is
   `<page id>/<discussion id>`, `others` is the number of other authors
   in the discussion.
5. Pipe each page's records through redaction, then run
   `normalize --cap 500 --cutoff <cutoff>`. End the pass when it reports
   500 kept, or when the pages run out.

Notion uses the same passes and dates as Slack (section 3) and stores
`per_channel.notion.pass`. The `post` pass, run only when `pre` ended
below 500, walks the page list again and keeps only comments from the
cutoff month on.

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

## 7. Automated posts

An automation that posts under the person's name would teach the profile
its status lines as the person's habits. For each channel in `channels`:

```
<py> <skill-dir>/scripts/corpus.py templated --corpus <home>/corpus/<channel>.jsonl
```

Each printed line is an audience with at least ten records where half or
more open with the same three words. When no channel prints a line, skip
to section 8. Otherwise show every flagged audience in one list, with its
channel name (Slack channel, repo, or page title), `records`, and
`prefix`, and ask one question: "Which of these are automated posts to
leave out? You can also name other channels." Wait for the answer.

Resolve any channel the person names that was not flagged to its id.
For each channel with audiences to leave out, run:

```
<py> <skill-dir>/scripts/corpus.py drop --corpus <home>/corpus/<channel>.jsonl --audience <id> --audience <id>
```

and add the ids to `per_channel.<channel>.excluded_audiences`.

Without Python, apply the same rule by reading each file and remove the
chosen audiences' records with the shell.

## 8. Hold out, first pass

For each channel in `channels`:

```
<py> <skill-dir>/scripts/corpus.py holdout --corpus <home>/corpus/<channel>.jsonl --cutoff <cutoff> --seed <seed>
```

This marks up to three pre-cutoff threads, or threads from the whole
window when the cutoff is `never`, with a record whose `others` is 1 or
more. A DM message outside a Slack thread has `others` 0 and never
qualifies. Store the printed list as `per_channel.<channel>.holdouts`.
The filter step runs the second pass when a channel got fewer than three.

Without Python, pick the threads at random under the same rule and set
`held_out` to `true` on every record of each chosen thread.

Add `"collect"` to `done`, and print per channel: records kept, date of
the oldest record, records touched by redaction, hold-out threads marked,
excluded audiences, and for Slack every month in
`per_channel.slack.empty_months`, named as a possible gap in the sample.
