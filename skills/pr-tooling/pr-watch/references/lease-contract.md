# Lease contract

This file is for code outside pr-watch that needs to know which Claude
Code session holds a pull request and whether that session's watch is
alive. The orchestrator is the first such reader. Everything here is
stable; the rest of the pr-watch state is not part of the contract.

## Where the files are

```
~/.claude/pr-watch/prs/<owner>/<repo>/<N>.json
```

One file per PR. `<owner>` and `<repo>` are lowercase in the path and
`<N>` is the PR number, so `mindbody/Mindbody.Clients#14` is
`prs/mindbody/mindbody.clients/14.json`. GitHub names ignore case; build
the path from lowercased names. The `owner` and `repo` fields inside the
file are lowercased the same way. Compare them without case. The PR's URL
carries its display casing.

The file is UTF-8 JSON, one object.

## Fields

| Field | Type | Meaning |
|---|---|---|
| `schema` | integer | `1` |
| `owner`, `repo` | string | The repository, lowercased |
| `number` | integer | The PR number |
| `role` | string | `authored` or `reviewed`, from the PR's live author when the lease was claimed |
| `holder.session_id` | string | `CLAUDE_CODE_SESSION_ID` of the holding session; the id `claude agents` lists and `--resume` takes |
| `holder.pid` | integer or null | The holder's claude process id |
| `holder.pid_started_at` | string or null | That process's creation time, ISO-8601 UTC ending `Z`. Windows reuses pids, so a pid counts only with a matching creation time. Null means the holder counts as not alive |
| `holder.poller_pid` | integer or null | The monitor's python process id; null when no monitor has ticked since the claim |
| `heartbeat` | string | ISO-8601 UTC ending `Z`. The monitor's last tick for this PR |
| `stale_after_seconds` | integer | `300`. Age after which `heartbeat` no longer shows a live monitor |
| `status` | string | `armed`, `stopped`, `released` or `closed` |
| `last_head_sha` | string or null | The PR head at the last tick |
| `pending_since` | string or null | ISO-8601 UTC. The first tick that saw work not yet handled: an unreplied thread tail, an unhandled red required check, or for a `reviewed` PR a reply on the user's threads not yet answered, or a push since the review that touches a file one of the user's findings is on or comes with an author reply. A push that does neither does not set it. Null when there is none, and on a `closed` lease |
| `last_error` | string or null | Null when the last tick was healthy. The monitor writes it on every tick, so it returns to null on the first good tick; a claim also resets it. A string on an `armed` lease means the monitor is running but could not reach GitHub for this PR. The only value today is `repo unreachable`; treat any string as a fault. `status` stays `armed` |
| `updated_at` | string | ISO-8601 UTC of the last write |

`heartbeat` is a top-level field. Read it as `lease["heartbeat"]`. A
missing or unparseable `heartbeat` counts as infinitely stale.

Right after a claim, `pending_since` and `last_error` are null and
`last_head_sha` carries over from the previous lease.

## Status

- `armed`: the holder is watching. The watch is live when
  `now - heartbeat <= stale_after_seconds`. The session is live when
  `claude agents` lists `holder.session_id`. A listed session with a
  stale heartbeat has a dead monitor: ask that session to run
  `/pr-watch <owner/repo#N ...> --yes`, naming the stale `armed` leases
  it holds. A bare `/pr-watch` would also re-arm its `stopped` PRs.
- `stopped`: the user ran `/pr-watch stop`. The holder keeps the lease.
  Do not re-arm it; report it as stopped but open.
- `released`: nobody is acting on the PR. Any session may claim it.
- `closed`: the PR merged or closed. Final. A closed lease is deleted
  after 7 days.

A holder process is alive when a process with `holder.pid` exists and
its creation time is within 2 seconds of `holder.pid_started_at`.

## Reading

- A missing file means nobody holds the PR.
- A file that does not parse as a JSON object with an object `holder`
  means nobody holds the PR.
- A file that exists but raises a sharing or permission error (a writer
  is replacing it) is neither held nor free. Retry it: the poller makes
  3 tries and the orchestrator 4, 50 ms apart. If it still fails, skip
  the file for that scan: no claim and no nudge.
- Writers replace the file atomically, so a successful read is a whole
  object.
- Never write a lease. Ask the holder's session, or let a session claim
  it.

## Writers

Only pr-watch's `poll.py` writes a lease. Two kinds of write exist and
they do not overlap for one PR:

- A claim, and a final status (`stopped`, `released`). These run in the
  session that holds, or is claiming, the PR. A claim takes the lease
  when none exists, when it is the claimant's own (a resume with a new
  pid), when it is `released` or `closed`, or when it is `armed` and the
  holder is dead: heartbeat older than `stale_after_seconds` and no
  matching process. A `stopped` lease of a dead holder is claimed only
  by a session the user pointed at that PR by name.
- A tick, from the holder's monitor. It rewrites `heartbeat`,
  `last_head_sha`, `pending_since`, `last_error` and `holder.poller_pid`
  on every `armed` lease it holds, and sets `closed` when the PR closes.
  It writes a lease only while `holder.session_id` is still its own
  session and `status` is still `armed`.

## Not part of the contract

These files sit beside the lease and may change without notice:

- `<N>.progress.json`: the PR's progress, written by the holder's
  session.
- `<N>.claim.lock`: a transient lock around a claim.
- `push.lock` in the repo directory: serialises pushes within a repo.

Do not read them for decisions and do not delete them.
