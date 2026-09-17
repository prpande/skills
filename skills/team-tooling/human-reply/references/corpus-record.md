# Corpus record

Every collector writes one JSON object per line to
`~/.claude/human-reply/corpus/<channel>.jsonl`, or to
`corpus/borrow-<channel>.jsonl` for a colleague sample. Records pass
through redaction before they are written, so this skill writes nothing
unredacted to disk; the session transcript Claude Code keeps under
`~/.claude/projects/` may still hold the raw text.
`python scripts/corpus.py validate` checks a file against this shape.

## Fields

```
{"channel": "slack", "surface": "channel thread reply", "ts": "2026-03-04T10:12:00Z",
 "audience": "C0123", "thread": "C0123/1709546000.1", "others": 2,
 "text": "...", "held_out": false}
```

| Field | Type | Meaning |
|---|---|---|
| `channel` | string | `slack`, `github`, or `notion` |
| `surface` | string | exactly one surface name from the channel module's `surfaces` block, assigned by the collector using that module's Surfaces table |
| `ts` | string | when the message was sent, UTC, `YYYY-MM-DDTHH:MM:SSZ` |
| `audience` | string | the channel id, `owner/repo`, or page id; never a person's name |
| `thread` | string | an id for the conversation the message belongs to, stable across its records, so calibration can rebuild the context |
| `others` | integer | how many participants other than the person appear within the record's `thread` id; 0 when unknown. A Slack DM or group DM message outside a thread has 0, since its thread id holds only that message; a Slack thread reply, in a channel or a DM, has 1 |
| `text` | string | the message as sent, after redaction |
| `held_out` | boolean | `false` when written; set by the hold-out step, never by a collector |

No other field is allowed. A record's id, used in drop samples and the
long-message list, is `<audience>/<ts>`.

## Thread ids by channel

- Slack: `<channel id>/<thread ts>`, or `<channel id>/<ts>` for a message
  outside a thread.
- GitHub: `<owner>/<repo>#<number>` for PR bodies and issue comments,
  `<owner>/<repo>#<number>/r<review id>` for a review summary, and
  `<owner>/<repo>#<number>/c<first comment id of the thread>` for a review
  thread reply.
- Notion: `<page id>/<discussion id>`.

## Counting words

Word counts everywhere in this skill split on whitespace after replacing
each fenced block, each Slack link `<https://...>`, and each markdown
link `[text](url)` with a single word.
