# pr-watch design

Third entry point on `pr-loop-lib`. A standing supervisor that lives inside
the working session, watches a set of pull requests, fixes and replies on the
ones the user authored, re-reviews the ones the user reviewed, and reports to
a Slack channel. It never exits on its own.

`pr-autopilot` publishes a PR and drives it to green. `pr-followup` re-enters
that loop on demand. `pr-watch` is armed once per session and reacts to
GitHub activity until the user stops it or the session closes.

## 1. Goals and non-goals

Goals:

- Address review activity on the user's PRs quickly and with as little
  intervention from the user as possible, including human reviewers'
  findings.
- Re-review PRs the user has reviewed when their authors push, and post the
  verdicts on the user's own threads.
- Never let anything reach a colleague that reads as automation.
- Never commit to, push to, or resolve threads on a PR the user did not
  author.
- Survive context compaction and `--resume`. The watch set and watermarks
  live on disk, keyed to the repo, and step 01 re-arms from them when a
  session starts in a repo that has a saved watch.

Non-goals:

- Reacting to red CI (library steps 09 and 10 are not wired; a later
  revision can add them).
- Running while no session is attached. The watch is a property of the
  working session because that session holds the effort's context: the
  plan, the decisions, and the reasons behind them. A detached fixer
  would make worse calls on exactly the findings that matter.
- Approving or requesting changes on a reviewed PR. Review state stays the
  user's call.
- Posting anywhere on Slack other than the configured channel.

## 2. Shape

### 2.1 Invocation

`/pr-watch [pr-number ...] [--channel <id>] [--parallel-pushes] [--dry-run]`
`/pr-watch status`
`/pr-watch stop`

With no PR numbers, step 01 discovers the set within the current repo:

- open PRs authored by `self_login` whose head branch is checked out in a
  worktree registered by `git worktree list` for this repo, and
- open PRs in this repo on which `self_login` has posted at least one
  review-thread comment, resolved or not.

Discovery uses `gh pr list` scoped to the repo, never org-wide search, so
SAML partial results cannot silently drop a PR. The proposed set is shown
once and the user confirms. The confirmation also lists authored PRs that
were excluded for having no worktree, so an omission is visible. Explicit
numbers are added to the set; an explicit authored PR with no worktree
gets one created at `<repo_root>/.claude/worktrees/<branch>` before it is
recorded. A PR number mentioned in conversation is never added silently.

If the repo already holds a watch state file (section 8), step 01 offers
to resume it, merged with whatever discovery finds. This is how the watch
survives `--resume` and a new session in the same repo.

`--dry-run` runs every path up to its first mutation and writes what it
would have committed, pushed, replied, or resolved to the scratchpad
instead. It is the acceptance harness for the fix path and re-review.

`--channel` defaults to `C0C15VC8Y0Z` (`#prpande-prs`). Passing a channel
id is the authorisation the skill needs to post there.

### 2.2 Roles

Each PR in the set carries a role, computed at discovery and recomputed on
every event from `pullRequest.author.login == self_login`:

| Role | Allowed mutations |
|---|---|
| `authored` | commit, push, reply, resolve, all on the PR's head branch |
| `reviewed` | reply on the user's own threads; resolve the user's own threads when judged addressed |

Worktree presence never decides the role. A `reviewed` entry never carries
a worktree path.

### 2.3 Lifecycle

1. Step 01 discovers and confirms the watch set (or resumes a saved one),
   writes the state file, records the worktree the session started in as
   the origin, initialises the library's `pr-<N>.json` for every
   `authored` PR (section 8), and posts nothing.
2. Step 02 arms one persistent `Monitor` running the poller in
   `--monitor` mode. No timeout. No iteration cap. No quiescence exit.
3. Each line the poller emits is one event for one PR. Step 03 takes
   events strictly one at a time: a line that arrives while a fix is in
   flight waits until that fix has returned the session to the origin
   worktree. Step 03 routes each event: `authored` events go to the fix
   path (section 4), `reviewed` events go to re-review (section 5).
4. The session returns to the origin worktree after every fix. The origin
   and the state file path are read from the state file, never recomputed
   from the current directory, because relocation changes what
   `git rev-parse --show-toplevel` returns.
5. If the monitor stream ends for any reason, the "stream ended"
   notification re-arms it and posts one line in the PR channel.
6. `/pr-watch stop` ends the watch and posts one closing reply per PR
   thread. Session close ends the running watch but leaves the state file,
   so the next session in the repo can resume it.

Everything else is quiet. A quiet event costs the poller one conditional
request; the session is not invoked.

## 3. The poller

`pr-watch/scripts/poll.py` with `threads.graphql` beside it. New code that
keeps the seed poller's fetch query, its classification rules, and its
id-watermark idea, and adds the monitor loop, the two state files, the
event lines, and the modes below. The seed's ATTENTION rule (newest
comment from a non-bot, non-self account) is replaced by the pending-tail
rule in 3.3. Parameterised by owner, repo, watch set, state paths, and bot
allowlist. Deterministic: no LLM in it.

### 3.1 Modes

- `--monitor`: the interrupt source. Loops forever on a 60-second tick:
  1. One GraphQL request with one alias per watched PR, fetching only
     `updatedAt`, `headRefOid`, and `state`. Cost is about one point
     against the 5,000-per-hour GraphQL budget, so the tick can run all
     day. `updatedAt` moves on every comment, review, reply, and push,
     including the user's own, and does not depend on read state; this
     is why the poller does not use `/notifications`, which omits the
     user's own activity and anything already opened in the browser.
  2. For each PR whose `updatedAt` or `headRefOid` changed since the last
     tick: the full thread fetch for that PR only, then the pending-tail
     computation (3.3), then zero or one event line. A full fetch of ten
     PRs costs roughly 500 points, which is why it runs only on change.
  3. Same tick: if `push_queue` in the session's state file is non-empty,
     emit one `tick` event so the session can drain one queued push
     without waiting for GitHub activity.
  4. Once a day: a full fetch of every watched PR, recomputing pending
     tails from scratch. Emits only for what the ticks missed, and
     writes one `reconciled` event naming what it found so a divergence
     is visible.
  5. Every fetch error is caught, written to stderr, and retried on the
     next tick. The loop never exits on its own. A PR that reaches
     `MERGED` or `CLOSED` emits one `closed` event and leaves the set.
- `--report`: the three-section report on demand (`/pr-watch status`). The
  sections are ATTENTION, NEW, and STANDING.
- `--reseed`: accept current state as baseline.

### 3.2 Classification

Author kinds: `me` (`login == self_login`), `bot`, `human`. Bot when any of:
`author.__typename == "Bot"`, login ends in `[bot]`, login in the
allowlist held in the state file. The allowlist ships seeded with
`sonarqube-mbodevme`, `mindbody-ado-pipelines`, and `mergewatch-playlist`,
all typed `User` on GitHub.

The library's Filter B decides a bot comment's disposition from
`known-bots.md` by exact login, and treats an unknown bot as actionable.
The allowlisted logins have no row there, so `pr-watch` ships
`pr-watch/references/known-bots-overlay.md` with one Skip row per allowlisted
login (their comments are status lines, never findings) and concatenates
it after the library table when Filter B runs. The library file is not
edited.

### 3.3 Pending tails

The unit of work is a thread. A thread's tail is every comment after the
last one whose id is in the state file's `posted_reply_ids`. A thread is
pending when its tail is non-empty. Every comment in the tail is in scope
whoever wrote it: a bot opening the thread, a teammate replying, the user
typing a reply by hand. A `me` comment whose id is not in
`posted_reply_ids` is one the user typed and is pending work.

Consequences accepted by design:

- A hand-typed comment by the user on their own PR is an instruction to
  the fix path. The escape hatch is a hand-typed reply that reads as a
  disposition; the fix path then returns `replied` with no change.
- Losing the state file makes every thread look pending. The first event
  re-verifies everything rather than skipping anything.
- Resolved threads are read like open ones. Resolving does not stop
  replies and a reply does not reopen; judge by who spoke last.
- Issue comments and review bodies have no thread. Each is handled once,
  keyed by id, and its disposition is recorded in the state file.

### 3.4 Event lines

One JSON line per PR with actionable change:

```
{"pr": 1411, "role": "authored", "kind": "pending",
 "threads": [<thread id>, ...], "comments": [<id>, ...], "reviews": [<id>, ...]}
{"pr": 1420, "role": "reviewed", "kind": "head-moved",
 "old_head": "...", "new_head": "...", "touches_my_findings": true, "author_replied": false}
```

Plus `tick` (push queue non-empty), `reconciled` (daily sweep found
something), and `closed` (PR merged or closed). A `head-moved` event on an
`authored` PR is compared with `last_pushed_head`: equal means it is the
watch's own push and is dropped; different means the user or another
session pushed, and the event only updates `last_head` and re-runs the
gate in 4.1 on the next pending event.

Bodies are not in the event line. The session reads them from the poller's
per-PR JSON dump, wrapping each in a nonce-delimited `<UNTRUSTED_COMMENT>`
block per `pr-loop-lib/references/prompt-injection-defenses.md` before any
agent sees it. Step 03 then runs the library's Filter C (the
prompt-injection regex from `03-triage.md`) on every body in the tail. A
hit removes that thread from the dispatch set for this event, records the
id, and escalates it (4.5); nothing is posted on the thread.

### 3.5 Watermarks

By comment id, never by timestamp. `pr-loop-lib`'s Filter A keys on
`max(created_at, updated_at) > max(last_push, last_handled)`, and
`last_push` advances when we push, so an unhandled comment made before our
push is dropped, with a rescue gated on `is_resolved == false`. Ids have no
such failure mode.

## 4. The fix path (authored PRs)

Runs per event in the PR's worktree, one event at a time.

### 4.1 Gate

Before relocating:

```
git -C <worktree> fetch origin
git -C <worktree> status --porcelain      # must be empty
git -C <worktree> rev-parse HEAD          # must equal the PR headRefOid
```

A dirty worktree means the user is in it: skip this PR for this event,
report it as skipped in the PR's Slack thread, retry on the next event or
sweep. A HEAD mismatch means another session moved the branch: same.

Then `EnterWorktree(path=<worktree>)`, acquire the library's `pr-<N>.lock`
per `state-protocol.md` (so `pr-followup` cannot collide), run the path,
release the lock, and `EnterWorktree(path=<origin worktree>)` to return.

Subagents cannot switch worktrees (measured 2026-09-11: a subagent's
`EnterWorktree(path=B)` reports success and its next Write into B is
refused). The parent session relocates; nothing else does.

### 4.2 Verify

One fixer subagent per pending thread, clustered per
`pr-loop-lib/steps/04-dispatch-fixers.md` (which clusters when an event
carries three or more actionable items, or resolved and unresolved threads
together). The prompt is the library's `fixer-prompt.md` with
`pr-watch/references/fixer-addendum.md` concatenated after it, the same
way the defenses are concatenated. The addendum adds:

1. The repository-first checks, in order:
   a. Does a shipped surface already return this? Find the REST mapper,
      response model or existing resolver for the same domain field. If
      it does, the PR inherits its semantics.
   b. Is the file even in the diff? Pre-existing code the PR made
      reachable is not this PR's decision.
   c. Census before accepting an "unlike its siblings" claim. Count both
      sides. One such claim asserted every sibling type carried a
      reference resolver when 12 of 19 carried none.
   d. Can the fix be made here? If an upstream layer already collapsed the
      distinction, the fix changes that layer's shipped consumers.
2. Allowed sources for the answer: this repo, other clones under the
   configured roots (read-only), and the GitHub API. Nothing else.
3. The hard-stop list. Return `needs-human` naming the stop when the fix
   needs any of:
   - a behaviour change on a shipped endpoint,
   - a schema or contract change,
   - new SQL or a repository query change,
   - anything the PR body names as an open question,
   - no precedent found by checks a to d,
   - a merge conflict with `origin/main`.
   Also `needs-human` when the tail is a human disagreeing with or
   questioning a reply `pr-watch` posted (one automatic round per human
   exchange; never a second automatic reply).
4. Record the disposition either way. A finding resolved from the repo
   cites what resolved it, never a bare "no change".
5. The verdict set is `fixed`, `refuted`, `superseded`, `needs-human`. The
   library's `ui-deferred` verdict is removed: nothing consumes it here,
   and the library's "Deferred for user review" template must never reach
   a thread. Anything the library would have deferred returns
   `needs-human` with the reason.

The library's verifier subagent runs on every `fixed` return unchanged.

### 4.3 Build, commit, push

Library step 04.5 as written. Step 06 is not reused: it hardcodes the
commit message `Address PR review feedback (#N)`, and this skill's
`pr-watch/steps/04-fix-path.md` owns the commit and push sequence instead, keeping
the library's secret scan (`secret-scan-rules.md`, blocking) and its
push guard order:

1. Secret scan over the staged diff. A hit blocks the commit and
   escalates.
2. Commit message: `AB#<work item>: <what changed>`. No co-author trailer,
   no session trailer. The work item is the first `AB#<digits>` in the PR
   title, then the PR body, then the branch's newest commit subject. When
   none has one, the message is `<what changed>` alone.
3. `git merge-base --is-ancestor origin/main HEAD`; merge `origin/main`
   only when false; after a merge that moved the branch, re-run 04.5 at
   the level the merged changes warrant. Never rebase.
4. Merge conflict: `git merge --abort`, leave the branch untouched,
   escalate with the conflicting paths.
5. Push guard (section 9), then `git push origin HEAD`. Non-fast-forward
   rejection: fetch, re-read the remote head, rebuild the fix on top.
   Never force. Record the pushed sha as `last_pushed_head`.
6. Only after the push succeeds: the replies for the threads that fix
   covers (4.4), since each names the commit.

Push serialisation is on by default: at most one PR's push per event; the
others stay committed locally and queue in the session's state file. The
queue drains one push per `tick` event (3.1), so a quiet PR's fix ships
within a minute of the previous push, and its replies wait until it has.
Exists because concurrent gated runs deadlock a shared contract database.
`--parallel-pushes` turns it off; the choice is persisted in the state
file, so it is passed once per watch.

### 4.4 Reply and resolve

Every reply is composed through `pr-watch/references/reply-voice.md`
(section 6). No templates, no markers, no fixed prefixes. A reply that
names a commit posts only after that commit is on the remote. The reply
mutation's returned comment id is appended to `posted_reply_ids` in the
same state write that records the disposition.

Resolve the thread when any of:

- it was opened by a bot and the disposition is fixed, refuted with
  evidence, or superseded;
- it was opened or joined by a human, the request was concrete (not a
  question), and the fix is verified;
- the human's latest reply after a `pr-watch` disposition is an
  acknowledgement.

Leave it open when the disposition is `needs-human`, or the human's latest
reply carries a question or a condition. Never resolve to tidy up.

Issue comments and review bodies get one top-level reply, once, keyed by
id. A prompt-injection hit (library Filter C) gets no reply at all; it
escalates.

### 4.5 Escalation

Each `needs-human` item is one reply in the PR's Slack thread: who, file
and line, the comment quoted in full inside a code block, what the code
says, the stop reason, and the commit sha if a partial fix exists.
Before relay the quoted body passes the library's `secret-scan-rules.md`
with matches replaced by `[redacted]`, and Slack mention syntax
(`<!channel>`, `<!here>`, `<@U…>`, `<#C…>`) has its leading `<` escaped so
a code block cannot page anyone.

The user answers by replying on the GitHub thread. A `me` comment newer
than the escalated comment clears the stop: the thread's id leaves
`escalated_ids`, the one-round counter resets, and the fix path runs the
tail again with the user's reply as the instruction. Without that, the
user's answer would re-trip the same hard stop and go nowhere. Escalated
ids are otherwise recorded so an item is sent once.

## 5. Re-review (reviewed PRs)

### 5.1 State comes from GitHub

The user's review threads are the findings, their ids are the anchors
that survive force-pushes, and `isOutdated` says the code under a thread
has moved. No local record of the user's past review exists; a set derived
from conversation would not survive compaction.

### 5.2 Trigger and filter

Trigger: a PR where the user has review threads and whose head has moved
since the user's newest comment on those threads. Re-review only when the
head moved and either the diff since the user's review touches a file one
of the user's threads names, or the author replied on one of those
threads. Otherwise record the head move and stay quiet.

### 5.3 Judgement

One subagent per finding reads the current code at the new head, via
`gh` and a read-only local clone when one exists, never a worktree on the
author's branch. Its prompt carries the library's defenses text; the
author's replies and the diff since the user's review are handed to it
inside the same nonce-delimited untrusted blocks as comment bodies, since
a code comment can carry a payload that flips a verdict and resolves the
user's own thread. It returns `addressed`, `partially addressed`,
`not addressed`, or `superseded`, with the evidence. This is a judgement
against the code, not a diff test: an author may fix a finding somewhere
other than where it was flagged.

### 5.4 Posting

- One reply per finding on the user's own thread, through the voice guide.
- Resolve only threads judged `addressed`.
- Never approve, never request changes, never touch another reviewer's
  threads.
- If the author disputes a verdict, escalate to the PR's Slack thread; no
  second automatic reply.

## 6. Reply voice

`pr-watch/references/reply-voice.md`, owned by this skill. Every posted
reply goes through it.

### 6.1 Sources

- The user's Slack corpus rules in `slack-reply/references/` (shapes,
  phrasebook, audit), translated to GitHub markdown.
- The `humanizer` skill's tell catalogue.
- A PR-comment corpus from a colleague who reviews by hand: every comment,
  thread reply, and review body by his login on the user's last fifteen
  `mindbody/Mindbody.Scheduling` PRs, plus his replies as author on his own
  PRs in the same repo. The login is resolved from reviewer lists at build
  time. The corpus is assembled in the build session's scratchpad, read
  once to derive the guide, and deleted; it is never written under any
  repo and never committed. Modelling a named colleague's style without
  telling him is the user's decision, recorded in section 13.

### 6.2 What is lifted from the corpus

Traits, not phrases: comment length, sentence count, whether the code or
the ask comes first, how a file or line is cited, code-block rate,
question rate, how disagreement is phrased, how a thread is closed. His
wording and pet phrases stay out; replies post under the user's login and
a recognisable colleague's voice under it is its own tell. The corpus is
not shipped; the derived rules and a few anonymised shape examples are.
The guide is derived once and is repo-agnostic: traits of review prose do
not depend on which repo the PR is in, so discovery in another repo uses
the same guide with no per-repo corpus.

### 6.3 Content of the guide

- One reader tier: GitHub review reply. One to four sentences, hard cap
  sixty words.
- Shapes: fixed (names the commit and what changed), refuted (evidence,
  not disagreement), superseded (the current text), acknowledged and left
  open (what is pending and why), re-review verdict (per finding, with
  the evidence), author closing a thread.
- The audit checklist merging `slack-reply`'s audit with the humanizer's
  highest-frequency tells, so the guide stands alone.
- Final step: invoke `humanizer` when installed; it may not add words.

## 7. Slack channel

Channel `C0C15VC8Y0Z`, one thread per PR, all replies in-thread.

- First event on a PR posts the root: number, title, link, one standing
  line. Its `ts` is recorded in the state file.
- Every later notification is a reply in that thread: escalations, pushed
  fixes (commit and what changed), a posted re-review, a skipped PR
  (dirty worktree), a merge conflict, a monitor re-arm, the closing line
  on stop.
- Nothing posts when nothing happened.
- The MCP cannot edit a posted message; the root stays as posted. The
  MCP appends a "Sent using @Claude" footer to agent messages; acceptable
  in a channel only the user reads.

## 8. State

Two files under `<repo_root>/.pr-autopilot/`, keyed to the repo rather
than the session so a new session resumes settled threads instead of
replaying them. Both are written with the library's atomic tmp+mv
primitive, and each has exactly one writer.

`watch.json`, written only by the session:

```
{
  "self_login": "prpande",
  "channel_id": "C0C15VC8Y0Z",
  "origin_worktree": "D:\\src\\Mindbody.Scheduling",
  "serialize_pushes": true,
  "bot_allowlist": ["sonarqube-mbodevme", "mindbody-ado-pipelines",
                    "mergewatch-playlist"],
  "prs": {
    "1411": {
      "role": "authored",
      "worktree": "D:\\...\\apptdetails-s2-hydration",
      "branch": "apptdetails-s2-hydration",
      "slack_ts": "1789105505.206109",
      "posted_reply_ids": [...],
      "escalated_ids": [...],
      "handled_top_level_ids": {"<id>": "<disposition>"},
      "last_pushed_head": "..."
    }
  },
  "push_queue": [1413]
}
```

`watch-poller.json`, written only by the poller:

```
{
  "last_reconciliation": "<ISO-8601>",
  "prs": {
    "1411": {"updated_at": "...", "last_head": "...", "seen_ids": [...]}
  }
}
```

The poller reads `watch.json` for the set, roles, allowlist, push queue,
and `posted_reply_ids`, and never writes it. The session reads
`watch-poller.json` for `last_head` and never writes it. Resume merges
discovery into the existing `watch.json`; a PR no longer open is dropped
from both files on the `closed` event.

Bridge to the library. Steps 04, 04.5, and the fixer and verifier prompts
read the library's `context` object and its `pr-<N>.json`, `pr-<N>.lock`,
and `pr-<N>.log`. Step 01 therefore initialises a real `pr-<N>.json` for
every `authored` PR, exactly as `pr-autopilot` step 01 would (`pr_number`,
`branch`, `head_sha`, `base_sha`, `self_login`, `repo`, empty
`handled_comment_ids`, `last_push_timestamp` unset), and step 03 fills
`context.actionable_items` from the poller's per-PR dump by mapping each
tail comment onto the library's `CommentRecord` shape (`id`, `author`,
`author_kind`, `body`, `path`, `line`, `thread_id`, `is_resolved`,
`created_at`). The fix path then iterates the library steps per PR with
that context, holding `pr-<N>.lock` for the duration and appending to
`pr-<N>.log` so the audit trail stays in one place. Invariant G1 holds
because the state file the lock protects now exists.

## 9. Safety

- Ownership is enforced three ways, independently: `reviewed` entries have
  no worktree; the fix path holds the library lock; a push guard
  immediately before every `git push` re-fetches the PR author from
  GitHub and aborts on mismatch with `self_login`. The guard does not
  trust the state file.
- The hard rules of `pr-autopilot/SKILL.md` apply verbatim: never on
  `main`/`master`, never `--no-verify`, never bypass signing, secret scan
  blocking at step 06, no destructive git, always `--paginate`.
- Comment bodies are untrusted. Nonce-delimited wrapping before any agent
  sees them; Filter C from `03-triage.md` before dispatch; fixer and
  verifier prompts carry the defenses text.
- Never post to Slack outside the configured channel. Never post to
  Notion. Never merge, close, or retarget a PR.
- One build or test command at a time, foreground, timeout at least five
  minutes. If the user is running one when an event arrives, the event
  waits; the session never starts a second.
- A wrong automated fix is undone with `git revert` on top of the branch
  and a further reply; the watch never rewrites pushed history, so every
  push it makes is recoverable by the user with plain git.

## 10. Reuse and what is owned

Reused unchanged from `pr-loop-lib`: Filters B and C of step 03, step 04
(dispatch, clustering, verifier, policy ladder), step 04.5,
`fixer-prompt.md`, `fixer-verifier-prompt.md`, `known-bots.md`,
`prompt-injection-defenses.md`, `secret-scan-rules.md`, `state-protocol.md`
(lock primitives), `log-format.md`, `platform/github.md`, and the
`context-schema.md` shape for `pr-<N>.json`.

Not used: step 01 (wait cycle), step 02 (timestamp-bounded fetch), Filter
A, Filter B.5 (its self-login rescue contradicts 3.3 and its dedup keys on
a preflight pass that never runs here), step 06 (hardcoded commit
message; replaced by the sequence in 4.3), step 07 (templated replies),
step 08 (quiescence), steps 09 to 11.

Owned by `pr-watch`:

```
skills/pr-tooling/pr-watch/
  SKILL.md
  steps/01-discover.md
  steps/02-arm-monitor.md
  steps/03-route-event.md
  steps/04-fix-path.md
  steps/05-rereview.md
  steps/06-notify.md
  references/fixer-addendum.md
  references/known-bots-overlay.md
  references/reply-voice.md
  references/watch-state-schema.md
  scripts/poll.py
  scripts/threads.graphql
  scripts/test_poll.py
```

`git diff` on the PR must show no change under `pr-autopilot/`,
`pr-followup/`, or `pr-loop-lib/`.

## 11. Acceptance

1. `python scripts/validate.py` passes from the repo root.
2. `poll.py --report` against a set of real open PRs produces the
   three-section report (ATTENTION, NEW, STANDING) and performs no
   mutation.
3. Deleting a known comment id from `seen_ids` makes exactly that item
   reappear as NEW on the next run, correctly classified.
4. A human comment on a resolved thread appears under ATTENTION.
5. A login in the allowlist typed `User` is classified as a bot.
6. A `me` reply whose id is not in `posted_reply_ids` makes its thread
   pending; adding the id closes the tail.
7. `--monitor` emits nothing across a run of ticks where no watched PR's
   `updatedAt` or `headRefOid` changed, and performs no thread fetch.
8. An attempt to push on a `reviewed` PR is refused by the push guard
   even when the state file is edited to say `authored`.
9. The first event on a PR creates one Slack root; later events reply in
   that thread and never create a second root.
10. A `pr-watch` commit carries no trailers.
11. `pr-autopilot` and `pr-followup` are byte-identical before and after.
12. `--dry-run` against a real authored PR with a pending bot thread runs
    the gate, the fixer, the verifier, and the commit sequence, and leaves
    the branch, the remote, and the thread untouched, with the would-be
    commit, reply, and resolve decision written to the scratchpad.
13. `--dry-run` against a real reviewed PR whose head moved over a file
    one of the user's threads names produces one verdict per finding with
    evidence, and posts nothing.
14. A user reply under an escalated thread makes that thread pending
    again and the fix path runs one more round on it.
15. The `Monitor` armed in step 02 is still delivering events after the
    session has relocated with `EnterWorktree` and returned. This is an
    untested assumption; if it fails, step 02 re-arms after every return
    and the spec is amended before the build continues.
16. A bot comment from an allowlisted login (a quality-gate status line)
    receives no reply and appears in no event.

## 12. Delivery

One PR, at the user's direction, over the file-count cap. The PR body
says so.

## 13. Decisions and their reasons

| Decision | Reason |
|---|---|
| Watch lives in the working session, not a scheduled process | The session holds the effort's context; a detached fixer makes worse calls on the findings that matter |
| Interrupt source is a persistent `Monitor` polling `updatedAt` and `headRefOid` over GraphQL every 60 s | Repo webhooks need admin the user lacks (`/hooks` returns 404) and a public relay; `/notifications` omits the user's own comments and anything already read, and `gh api` surfaces its 304 as an error; one aliased GraphQL request costs about one point and catches comments, replies, and pushes alike |
| State keyed to the repo, two files with one writer each | A session-keyed file replays settled threads in the next session; two writers on one tmp+mv file lose each other's fields |
| Push serialisation on by default | The shared contract database deadlock it exists for is a known failure, not a hypothetical |
| Parent session relocates per PR; no child process, no subagent switching | Subagents cannot write into another worktree even after `EnterWorktree(path)`; a headless child loses the conversation and hits permission prompts |
| Unit of work is the thread tail after the last posted reply id | Catches replies mid-thread from anyone, including the user; needs no marker in the body |
| Human and bot findings share one fix path | The tiers differ only in the resolve rule and the one-round rule, not in who verifies |
| Fixed hard-stop list | An agent can nearly always persuade itself the existing code settles a question |
| No markers, no templates, no trailers on anything a colleague can see | The user's requirement; automation must not be visible on the PR |
| Voice derived from a hand-reviewing colleague's traits | The user's own recent replies were AI-composed |
| The colleague is not told his comments seed the guide | The user's decision; traits only are lifted, the corpus never leaves the build scratchpad, and no phrase of his is reproduced |
| Slack channel with one thread per PR | The user's requirement; channel is only about PRs in flight |
| No stop other than the user's | The user's requirement |
| Discovery per repo, not org-wide | SAML partial results return HTTP 200 with PRs silently omitted |
