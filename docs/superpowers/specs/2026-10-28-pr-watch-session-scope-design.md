# pr-watch session scope: design

Status: draft for praty's review, 28 Oct 2026. Changes the shipped
`pr-watch` (`skills/pr-tooling/pr-watch/`, original design
`2026-09-11-pr-watch-design.md`) from one watch per repo to one watch per
Claude Code session, across repos. The orchestrator
(`D:\src\prpande\orchestrator`) arms and supervises it; its PR-automation
design reads the lease contract defined here.

## 🎯 Intent

praty meant pr-watch to look after the PRs a session is working on,
wherever they live. A SoapMig session has PRs in
`mindbody/Mindbody.Clients`, `mindbody/Staffmgmt.Service` and
`mindbody/Mindbody.BizApp.Bff` at once. The shipped skill cannot do that:
its state sits in one repo's main checkout, its poller queries one repo,
a second session in the same repo is refused by the repo-wide heartbeat,
and arming always ends in a confirm question.

The orchestrator will arm pr-watch in worker sessions unattended, route
every piece of work for a PR to the session that holds it, and resume that
session by id when it is offline. pr-watch has to make "which session holds
this PR, and is its watch alive" answerable from a file.

## ✅ Goals

- One watch per session, covering PRs in any number of repos, with one
  poller and one GraphQL query per tick.
- At most one session holds a PR at a time (a per-PR lease). A session
  that wants a held PR is told which session holds it.
- A PR's progress (settled threads, posted replies, push caps, Slack
  thread) survives a handover to another session, so nothing is replayed
  or re-baselined.
- A PR this session opens or follows up after arming joins the running
  watch on its own.
- `--yes` arms with no confirm, for unattended use.
- A documented lease contract the orchestrator reads from stdlib Python.
- Watches armed in the old per-repo format are migrated on re-arm, never
  run beside the new one.

## 🚫 Non-goals

- Changing what the watch does on an event: the fix path, CI handling,
  re-review, reply voice, Slack threads and hard rules are unchanged
  except where a step names a repo or a state path.
- Any orchestrator code. The orchestrator only reads the lease files.
- Org-wide PR search for discovery (SAML partial results stay a reason to
  avoid it).

## ⚠️ Anti-goals

- Two watchers acting on one PR: two new-format sessions, or a new-format
  and an old-format watch.
- A bare `/pr-watch` grabbing PRs the session only looked at. A
  coordinating session views many of praty's PRs.
- A deadlock where a session refuses its own PR because it lost track of
  its own monitor (compaction drops the task id).
- `/pr-watch stop` being undone by the orchestrator within minutes.

## 🧱 Decided with praty (28 Oct 2026)

1. **State split in two.** Per session: the PR set and everything about
   the watch itself. Per PR: the progress fields plus the lease. A session
   that takes a PR over continues its history.
2. **The PR set is `owner/repo#N` entries from any repo.**
3. **One poller per session** covers every repo in the set.
4. **A per-PR lease** replaces the per-repo heartbeat block.
5. **`--yes`** arms without the "Watch these PRs?" confirm.
6. **The `reviewed` role stays, explicit-only.** A bare `/pr-watch` never
   adopts a reviewed PR. The orchestrator's `[Review]<Repo><N>` session
   does a first review and then arms `/pr-watch owner/repo#N --yes`, so
   it holds the lease and gets later re-review asks. All work for a PR
   goes to its lease holder; no separate re-review session exists.
7. **New PRs join automatically.** When `pr-autopilot` or `pr-followup`
   finishes in a session whose watch is running, its PR joins that watch.
8. **No routine stop.** praty does not plan to call `/pr-watch stop`. A
   watch on a PR ends when the PR merges or closes. `stop` and a new
   `release` stay as escape hatches.

Settled with the orchestrator sessions (`[OrchDev]Main`,
`[OrchDev]PrAuto`), same day: the lease fields, liveness rule, status
values, resume-by-id with immediate self-reclaim, takeover only as a
fallback, migration by process ancestry, and the bare-arm evidence rule.

## 🗂️ State

Root: `~/.claude/pr-watch/` (`PW_HOME`). Nothing lives in a repo's main
checkout any more, except the library files below.

```
~/.claude/pr-watch/
  sessions/<session-id>/
    watch.json            session; written only by the session
    watch-poller.json     poller; written only by POLL --monitor
    watch-heartbeat       poller; bare epoch integer, as today
    watch-seen.json       POLL --report / --reseed
  prs/<owner>/<repo>/
    <N>.json              the lease; written only by poll.py (rules below)
    <N>.progress.json     the PR's progress; written only by the lease holder's session
    <N>.claim.lock        transient; exclusive-create lock around a claim
```

`<session-id>` is `CLAUDE_CODE_SESSION_ID` (verified by `[OrchDev]PrAuto`
to equal `sessionId` from `claude agents --json`). `--resume` keeps it.

`owner` and `repo` are lowercased everywhere they form a path or a key
(`prs/mindbody/mindbody.clients/14.json`, `mindbody/mindbody.clients#14`).
GitHub names ignore case; without this, a ref typed by hand and one read
from a remote could yield two lease files for one PR. The lease's
`owner`/`repo` fields hold the same lowercased names; readers compare
them case-insensitively, and the PR URL carries the display casing.

The library files stay where they are:
`<worktree>/.pr-autopilot/pr-<N>.json`, `.lock`, `.log`, shared with
`pr-followup` and keyed by the PR's worktree.

### `watch.json` (session)

The fields that describe the watch, not a PR: `session_id`,
`claude_pid`, `self_login`, `channel_id`, `origin_worktree`,
`serialize_pushes`, `bot_allowlist`, `ado_orgs`, `dry_run`,
`stopped_at`, `push_queue`, and `prs`: an object keyed by `owner/repo#N`,
each value `{role, worktree?, branch, title, url, status}` where `status`
is `armed`, `stopped`, `released`, `closed` or `lost` (another session
claimed the lease; this session no longer acts on the PR). `stopped_at` is
set by `/pr-watch stop` and cleared by any arm. `owner`/`repo` at the top
level go away.

`push_queue` holds `owner/repo#N` keys. Serialisation is per repo and
across sessions: the shared contract database it guards is per repo, and
under the old design every watched PR in a repo was serialised against
every other. The "other PRs' checks still running" test therefore covers
every PR with an `armed` lease under `prs/<owner>/<repo>/`, whichever
session holds it, and never PRs in other repos.

Two sessions can both find nothing running and push at once, so the scan
and the push run under `prs/<owner>/<repo>/push.lock` (exclusive create,
same handling as the claim lock). The lock is held from the scan until
the pushed head has a check run registered, or 120 s after the push,
whichever comes first; a lock older than 300 s is stale. A session that
finds the lock held treats the repo as busy and queues, as it does for a
running check.

### `<N>.progress.json` (per PR)

Every per-PR field `watch-state-schema.md` lists today
(`posted_reply_ids`, `settled_ids`, `escalated_ids`,
`handled_top_level_ids`, `slack_ts`, the CI and fix-push counters,
`finding_verdicts`, `rereviewed_head`, `retry_after`, `skip_reason`,
queue fields, and the rest), unchanged in meaning. Written only by the
session that holds the lease, through `state_put.py` as today. The
poller reads it.

A `--dry-run` watch takes no leases and keeps its progress copies in its
session directory, so a rehearsal never touches the shared files.

### `<N>.json`: the lease

The contract the orchestrator reads. Defined in
`references/lease-contract.md` (new), which the orchestrator cites:

| Field | Meaning |
|---|---|
| `schema` | `1` |
| `owner`, `repo`, `number` | the PR |
| `role` | `authored` \| `reviewed` (from the live PR author) |
| `holder.session_id` | `CLAUDE_CODE_SESSION_ID` of the holder |
| `holder.pid` | the holder's claude process id (`CLAUDE_PID`) |
| `holder.pid_started_at` | that process's creation time, ISO-8601 UTC; Windows reuses pids |
| `holder.poller_pid` | the monitor's python pid, or null when no monitor runs |
| `heartbeat` | ISO-8601 UTC with `Z`; the monitor's last tick |
| `stale_after_seconds` | `300` |
| `status` | `armed` \| `stopped` \| `released` \| `closed` |
| `last_head_sha` | head at the last tick |
| `pending_since` | ISO-8601 UTC: the first tick that saw work not yet handled (an unreplied thread tail, an unhandled red required check, or for `reviewed` a push past praty's review); null when none |
| `last_error` | short string or null; set by the monitor, `status` stays `armed` |
| `updated_at` | ISO-8601 UTC of this write |

Status meanings for a reader:

- `armed`: the holder is watching. The watch is live when
  `now - heartbeat <= stale_after_seconds`. The session is live when
  `claude agents` lists `holder.session_id`. Listed but stale means the
  monitor is down: nudge the session to run `/pr-watch`.
- `stopped`: praty ran `/pr-watch stop`. The holder keeps the lease; the
  orchestrator does not re-arm it and lists it as stopped-but-open.
- `released`: nobody is acting; anyone may claim it.
- `closed`: the PR merged or closed. Final. Files older than 7 days are
  pruned by any monitor's daily reconciliation.

A missing or unparseable lease file means nobody holds the PR.

**Writers.** Only `poll.py` writes a lease, always atomically
(`write_json_atomic`: temp file in the same directory, replace with
Windows retry). Two kinds of write, which never overlap for one PR:

- **Claim and final status** (`POLL --claim`, `POLL --lease-status`):
  run by step 01 before the monitor starts, by `stop` after the monitor
  is stopped, and by `release` after it updates `watch.json`. A claim
  holds `<N>.claim.lock` (exclusive create; a lock older than 60 s is
  stale and removed) for its read-check-write.
- **Ticks** (`POLL --monitor`): rewrites the lease of every `armed` PR in
  the session's `prs` on each tick: heartbeat, `last_head_sha`,
  `pending_since`, `last_error`. Each write first re-reads the lease and
  writes only when `holder.session_id` is still this session and the
  status is still `armed`. A tick never moves a lease out of `stopped`,
  `released` or `closed`; only a claim does. A PR that closes gets
  `status: closed`.
- **Lost lease.** When the re-read shows another session holds the PR,
  the monitor writes nothing for it, emits `{"kind":"lease-lost","pr":
  ...,"holder":...}` once, and drops it from its ticks. Step 03 marks the
  PR `lost` in `watch.json` and posts one line to its Slack thread.

`release` and `stop` write `watch.json` first and the lease second, so a
tick that read the old `watch.json` cannot re-arm a lease it no longer
owns: the tick sees a non-`armed` status and skips it.

### Claim rules

`POLL --claim <owner/repo#N> --session-dir <dir>` takes the lease when:

- no lease file exists, or it does not parse; or
- `holder.session_id` is this session (a resume: same id, new pid). It
  is reclaimed at once, whatever the heartbeat says; or
- `status` is `released` or `closed`; or
- `status` is `armed` and the holder is dead: the heartbeat is older than
  `stale_after_seconds` and no process with `holder.pid` and a matching
  creation time exists.

A `stopped` lease held by another, dead session is claimable only when
the PR was named explicitly in this invocation. Otherwise the claim
fails, exits non-zero, and prints one line naming the holder session
(`[Tag]Name` from `claude agents --json` when it can be read, else the
id) and the heartbeat age. Step 01 lists the PR as excluded with that
line and carries on with the others.

A lease file that exists but cannot be read (a transient sharing error
while another process replaces it) is not "missing": the claim refuses
with "lease unreadable" and step 01 retries it once.

**Self-reclaim.** A resumed session can find its old monitor still
running: the poller outlives its claude process. Before claiming, step 01
ends every `poll.py --monitor --session-dir <this session's dir>` process
whose claude ancestor is not this session's `CLAUDE_PID`, so one session
never has two pollers.

**Takeover.** When a claim takes a PR from another session, queued work in
the progress file (`queued_head`, `ci_rerun_queued`) moves to the new
holder: step 01 adds the PR to this session's `push_queue` and the next
drain handles it, so a fix committed but not pushed by the dead session
is not stranded.

**Inherited identity.** A process started by a session's tools inherits
`CLAUDE_CODE_SESSION_ID` and `CLAUDE_PID`, and so would a `claude`
launched from one. Step 01 refuses to arm when `CLAUDE_PID` is missing or
is not the nearest `claude.exe*` ancestor of the arming process.
`CLAUDE_CODE_CHILD_SESSION` is no signal: it was set to `1` in the tool
processes of a normal, transcript-saving session started by the
orchestrator (measured 28 Oct 2026).

## 🔎 Arming

### Invocation

| Command | Meaning now |
|---|---|
| `/pr-watch` | this session's own open PRs in any repo (rule below); never reviewed PRs |
| `/pr-watch owner/repo#N ...` | those PRs; role from the live author |
| `/pr-watch N ...` | a bare number is a PR in the current directory's repo |
| `--yes` | skip the "Watch these PRs?" confirm |
| `--channel`, `--parallel-pushes`, `--dry-run` | unchanged |
| `/pr-watch status` | every PR in this session's watch, across repos |
| `/pr-watch stop` | stop this session's monitor; its leases become `stopped` |
| `/pr-watch release owner/repo#N` | drop one PR; its lease becomes `released` |

The orchestrator's seeding message is `/pr-watch owner/repo#N [...] --yes`.
Re-running `/pr-watch` with new refs in a session that already watches
adds them to the running watch without a second monitor.

### Bare `/pr-watch`: the evidence rule

A PR joins a bare arm only when both hold:

1. its live author is `self_login`; and
2. this session's transcript shows it wrote to the PR's head branch:
   - a `git commit` or `git push` tool call in a record whose `cwd` is in
     that repo and whose `gitBranch` equals the PR's `headRefName`; or
   - a `git push` / `git -C <path> push` call (not `--dry-run`) whose
     command names the head branch, or whose output carries a push line
     for it: `<sha>..<sha>  <headRefName> -> <headRefName>`, a forced
     update, or `[new branch]`; or
   - a `gh pr create` call whose output carries the PR's URL.

`pr-link` records are hints for which PRs to check, never evidence: they
appear for PRs a session only viewed and are missing from most sessions
that did create PRs.

The transcript is found by globbing
`~/.claude/projects/*/<session-id>.jsonl` (EnterWorktree moves the
project folder, so the path is never cached). Each candidate is checked
with `gh pr view <url> --json author,state,headRefName,...`; no org-wide
search.

### Finding a local clone

An `authored` PR needs a worktree. For a PR whose head branch already has
a worktree, that path is used. Otherwise the clone is resolved in order:
the current directory's repo when its `origin` matches; a `cwd` from this
session's transcript inside a clone whose `origin` matches. A PR with no
known clone is excluded with "no local clone of owner/repo known to this
session". No filesystem-wide search.

### Old-format watches

Step 01 checks `<MAIN>/.pr-autopilot/watch.json` for every repo in the
new set. When one exists and lists a PR being armed:

1. Find the old monitor: a `python ... poll.py --monitor --state-dir
   "<MAIN>\.pr-autopilot"` process (Win32_Process command line). The old
   format never stored the poller's pid.
2. Walk its `ParentProcessId` chain to the first process whose image
   name matches `claude.exe*`. Auto-update renames running binaries to
   `claude.exe.old.<ms>.<pid>`, so an exact match misses them.
3. That pid is this session's `CLAUDE_PID`: this session owns the old
   watch, whether or not it still remembers the task id. Stop it
   (`TaskStop` when the id is known, else end the poller's process tree
   by pid), then migrate.
4. A different claude pid: another session owns it. Map the pid to a
   session through `claude agents --json` (it exposes `pid`) and refuse
   the PR: "old-format watch in owner/repo held by [Tag]Name, heartbeat
   Ns ago; re-arm /pr-watch in that session". Unnamed when the walk or
   the lookup fails.
5. No old monitor process and a heartbeat older than 300 s: stale;
   migrate.
6. No old monitor process and a heartbeat 300 s old or newer: the poller
   died moments ago or is restarting. Exclude the PR with "old-format
   watch in owner/repo ticked Ns ago; retry after it goes stale" and arm
   the rest.

Migrate means: copy each old PR entry's progress fields into
`<N>.progress.json` (nothing re-baselined), claim the lease, rename the
old `watch.json` to `watch.json.migrated`, and delete `watch-heartbeat`
and `watch-poller.json`. PRs in the old file that are not in the new set
are migrated too when this session owns the old watch, so none is left
unwatched.

No old-format watch is running (praty, 28 Oct 2026), so the steps carry
no guard for a session whose old poller is still running when the new
step files land. Re-arming is the only migration path. Before merging,
check that no old-format watch is running.

## ✏️ Editing files in another repo

The fix path (step 04 section 2) moves the session into the PR's
worktree with `EnterWorktree(path)` and back to `origin_worktree`
afterwards. That switch only works between worktrees of the launch
repo, or of a repo nested inside the launch directory, so it cannot
reach a `Staffmgmt.Service` worktree from a session launched in
`Mindbody.Clients`.

It does not need to. Measured 28 Oct 2026 from a session isolated in a
worktree of this repo: the worktree lock refuses writes only into the
launch repo's own shared checkout. Write and Edit into a worktree of
another repo succeeded with no relocation, and so did a subagent's Write
and Edit there. `git -C <path>` commands against the other repo ran
normally.

So for a PR whose repo is not the launch repo, step 04 skips the
relocation: the session and its fixers edit with absolute paths, and
every git command uses `git -C <worktree>`. A PR in the launch repo keeps
today's `EnterWorktree(path)` path unchanged.

Without the relocation the cwd is the wrong repo, so every part of the
fix path that assumes the cwd takes the worktree root explicitly:

- Step 04's own git commands (sections 5, 6 and 10 and the drain) use
  `git -C <worktree>`.
- `pr-loop-lib`'s fixer and verifier prompts name the worktree root
  instead of "this repository", and its `files_changed` check resolves
  paths against that root.
- `pr-loop-lib` step 04.5 (local verify) runs its build and test
  commands with the worktree as their working directory.
- The `pr-fixer` agent definition is unchanged. Its git helpers are
  allow-listed only in their bare form, so they would read the launch
  repo; the brief for an other-repo PR tells the fixer to use Read, Grep
  and Glob on the worktree path instead.

## 🔁 Poller

`POLL --monitor --session-dir <dir>` replaces `--state-dir`.

- One GraphQL request per tick, one alias per repo and one per PR inside
  it: `r0: repository(owner:, name:) { p14: pullRequest(number: 14) {...} }`.
  Owner and repo are validated against the existing `NAME` pattern before
  they are inlined, as today.
- Events carry `"pr": "owner/repo#N"` instead of a bare number. Every
  step that reads `pr` or passes `--repo` takes the repo from the key.
- Each tick also writes the leases (above). `pending_since` is set the
  first tick a PR has a non-empty pending set or an unhandled red
  required check (authored) or a head past the review (reviewed), and
  cleared the first tick it is empty.
- The monitor exits cleanly when no PR in `watch.json` is still
  `armed`: it writes the final lease statuses, prints `{"kind":"idle"}`
  and exits 0. Step 02 treats "stream ended" after `idle` as a planned
  exit: no re-arm and no "monitor died" line. The next PR to join starts
  a new monitor.
- `lease-lost` (above) is a new event kind; step 03 routes it. On
  `idle`, step 03 re-reads `watch.json` and starts a new monitor when a
  PR joined while the old one was exiting.
- The monitor exits without `idle`, and writes nothing more, when its
  claude process is gone (pid plus creation time). An orphaned poller
  would otherwise keep a dead session's heartbeat fresh forever and
  block takeover.
- A PR in a repo the query cannot reach keeps a fresh heartbeat with
  `last_error: "repo unreachable"`, so the orchestrator does not nudge a
  session that a re-arm cannot help.
- A `--dry-run` monitor writes no leases.
- Whether the monitor runs is read from disk (`watch-poller.json`
  `poller_pid` alive under this session's claude pid, and a heartbeat
  under 300 s), not from a task id compaction may have dropped.
- `watch-poller.json` records `poller_pid` and `claude_pid` for the
  ancestry check.
- The per-PR modes (`--baseline`, `--tails`, `--findings`, `--checks`)
  take `owner/repo#N`, and `--report` covers the whole set; `--assert-author`, `--ci-log` and
  `--ci-rerun` keep `--repo` but step files fill it from the key.

## 🔗 Auto-join from pr-autopilot and pr-followup

At the end of a `pr-autopilot` run (after the final CI gate) and of a
`pr-followup` run, the skill checks
`~/.claude/pr-watch/sessions/<CLAUDE_CODE_SESSION_ID>/watch.json`. When
it exists, `dry_run` is false and `stopped_at` is null, the skill invokes
`/pr-watch owner/repo#N --yes`. The PR joins the watch, its Slack thread
notes it, and nothing is asked; when the monitor had gone idle because
every earlier PR closed, the arm starts a new one. The heartbeat is not
part of the test: a watch whose PRs all merged is idle, not gone, and
praty expects the next PR to join it. With no `watch.json`, or a watch
praty stopped, nothing happens.

## 🧪 Testing

- Unit tests in `skill-tests/pr-watch/tests/` for: the multi-repo tick
  query and alias mapping; `owner/repo#N` events; lease claim (fresh,
  self-reclaim with a new pid, released, dead holder, live holder refused,
  stopped needing an explicit ref, claim-lock contention, unreadable
  lease refused, self-reclaim ending a live old poller, takeover
  re-queueing queued work, inherited identity refused); lease writes on
  ticks including `pending_since` set and clear, a tick skipping a lease
  another session now holds (`lease-lost` once) and one already
  `released`; the push lock; monitor exit with `idle` when nothing is
  armed; transcript evidence (each of the four forms, pr-link alone
  rejected); migration (owned, foreign, stale, fresh-without-monitor)
  with ancestry faked.
- Live tests against `prpande/prism-sandbox` and a new public
  `prpande/prism-sandbox-2` (praty approved creating it, test-only; a few
  files and one GitHub Actions check), never Mindbody PRs:
  multi-repo watch in one session, a second session refused with the
  holder named, a resume reclaiming its own lease, takeover after the
  holder dies, auto-join from a pr-autopilot run, migration of an
  old-format watch.
- `python scripts/validate.py` and the existing pr-watch tests pass.

## 🔧 Left to the builder

- Module layout inside `poll.py` (or a new `lease.py` beside it), CLI
  flag names beyond those named here, and how step files are reworded.
- The exact transcript parsing (record shapes for tool calls and results).
- How `status` renders a multi-repo watch.
- Updating `2026-09-11-pr-watch-design.md` decisions that this supersedes
  ("State keyed to the repo", "Discovery per repo") with a pointer here.

## 🧭 Calls made without praty (check these)

- Cross-repo fixes use absolute paths and `git -C` with no relocation
  (measured: the worktree lock covers only the launch repo's checkout).
- Push serialisation spans sessions within a repo (read from leases).
- `owner`/`repo` are lowercased in every path and key.
- Progress lives in `<N>.progress.json` beside the lease, not inside it,
  so the lease keeps a single writer (`poll.py`) and the progress file a
  single writer (the holder session).
- A dry run takes no leases and keeps progress in its session directory.
- The monitor exits when nothing in the set is still armed and open,
  with an `idle` event so step 02 does not read it as a crash.
- Auto-join keys on `watch.json` existing and not stopped, not on a fresh
  heartbeat.
- Each tick re-reads the lease and never writes one another session
  holds or one that is no longer `armed`.
- Pushes in one repo are serialised across sessions by a `push.lock`.
- A claim that takes a PR from another session re-queues its queued fix
  or CI rerun; a self-reclaim ends the session's own leftover poller.
- Arming refuses when the session identity was inherited.
- The fixer agent definition stays as is; other-repo briefs steer it to
  Read, Grep and Glob.
- Closed lease files are pruned after 7 days.
- A `stopped` lease of a dead session is claimable only by explicit ref.
- An authored PR with no local clone known to the session is excluded,
  not cloned.
