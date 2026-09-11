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
- Survive context compaction and `--resume`; the watch set and watermark
  live on disk, not in the conversation.

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

`/pr-watch [pr-number ...] [--channel <id>] [--serialize-pushes]`
`/pr-watch status`
`/pr-watch stop`

With no PR numbers, step 01 discovers the set within the current repo:

- open PRs authored by `self_login` whose head branch is checked out in a
  worktree registered by `git worktree list` for this repo, and
- open PRs in this repo on which `self_login` has posted at least one
  review-thread comment, resolved or not.

Discovery uses `gh pr list` scoped to the repo, never org-wide search, so
SAML partial results cannot silently drop a PR. The proposed set is shown
once and the user confirms; explicit numbers are added to it. A PR number
mentioned in conversation is never added silently.

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

1. Step 01 discovers and confirms the watch set, writes the state file,
   and posts nothing.
2. Step 02 arms one persistent `Monitor` running the poller in
   `--monitor` mode. No timeout. No iteration cap. No quiescence exit.
3. Each line the poller emits wakes the session with one event for one
   PR. Step 03 routes it: `authored` events go to the fix path (section
   4), `reviewed` events go to re-review (section 5).
4. The session returns to the worktree it started in after every fix.
5. If the monitor stream ends for any reason, the "stream ended"
   notification re-arms it and posts one line in the PR channel.
6. `/pr-watch stop` or session close ends the watch. Stop posts one closing
   reply per PR thread.

Everything else is quiet. A quiet event costs the poller one conditional
request; the session is not invoked.

## 3. The poller

`pr-watch/scripts/poll.py` with `threads.graphql` beside it. Grown from the
seed at `C:\src\.docs\skills\pr-watch-seed\poll.py`, parameterised by owner,
repo, watch set, state path, and bot allowlist. Deterministic: no LLM in it.

### 3.1 Modes

- `--monitor`: the interrupt source. Loops forever:
  1. `GET /notifications` with `If-None-Match: <etag>`. A 304 costs no rate
     limit and emits nothing. Sleep `X-Poll-Interval` seconds (GitHub
     returns 60 today).
  2. On 200, keep notifications whose subject URL is a PR in the watch set,
     then run the full thread fetch for those PRs only.
  3. Every 5 minutes regardless: one GraphQL call fetching `headRefOid` for
     every watched PR, because a bare push raises no notification and the
     head move is the re-review trigger.
  4. Once a day: a full fetch of every watched PR, recomputing ATTENTION
     from scratch. Emits only if it finds something the events missed.
  5. Every fetch error is caught, written to stderr, and retried on the
     next interval. The loop never exits on its own.
- `--report`: the three-section report on demand (`/pr-watch status`).
- `--reseed`: accept current state as baseline.

### 3.2 Classification

Author kinds: `me` (`login == self_login`), `bot`, `human`. Bot when any of:
`author.__typename == "Bot"`, login ends in `[bot]`, login in the
allowlist held in the state file. The allowlist ships seeded with `sonarqube-mbodevme` and
`mindbody-ado-pipelines`, both typed `User` on GitHub.

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

Bodies are not in the event line. The session reads them from the poller's
per-PR JSON dump, wrapping each in a nonce-delimited `<UNTRUSTED_COMMENT>`
block per `pr-loop-lib/references/prompt-injection-defenses.md` before any
agent sees it.

### 3.5 Watermarks

By comment id, never by timestamp. `pr-loop-lib`'s Filter A keys on
`max(created_at, updated_at) > max(last_push, last_handled)`, and
`last_push` advances when we push, so an unhandled comment made before our
push is dropped, with a rescue gated on `is_resolved == false`. Ids have no
such failure mode.

## 4. The fix path (authored PRs)

Runs per event in the PR's worktree.

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
`pr-loop-lib/steps/04-dispatch-fixers.md` when three or more touch one
area. The prompt is the library's `fixer-prompt.md` with
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

The library's verifier subagent runs on every `fixed` return unchanged.

### 4.3 Build, commit, push

Library steps 04.5 and 06 as written, with these owned by `pr-watch`'s
step file:

- Commit message: `AB#<work item>: <what changed>`. No co-author trailer,
  no session trailer. The work item comes from the PR title or body.
- Before pushing: `git merge-base --is-ancestor origin/main HEAD`; merge
  `origin/main` only when false; after a merge that moved the branch,
  re-run 04.5 at the level the merged changes warrant. Never rebase.
- Merge conflict: `git merge --abort`, leave the branch untouched, escalate
  with the conflicting paths.
- Non-fast-forward rejection: fetch, re-read the remote head, rebuild the
  fix on top. Never force.
- Push serialisation: with `--serialize-pushes` (persisted in the state
  file, so it is passed once per session), at most one PR's push per event; the others queue in the state file and
  go out on subsequent events, reported as queued. Exists because
  concurrent gated runs deadlock a shared contract database.

### 4.4 Reply and resolve

Every reply is composed through `pr-watch/references/reply-voice.md`
(section 6). No templates, no markers, no fixed prefixes. The reply
mutation's returned comment id is appended to `posted_reply_ids`.

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
says, the stop reason, and the commit sha if a partial fix exists. The
user answers by replying on the GitHub thread; that reply is the next
pending tail. Escalated ids are recorded so an item is sent once.

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
author's branch. It returns `addressed`, `partially addressed`,
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
  time.

### 6.2 What is lifted from the corpus

Traits, not phrases: comment length, sentence count, whether the code or
the ask comes first, how a file or line is cited, code-block rate,
question rate, how disagreement is phrased, how a thread is closed. His
wording and pet phrases stay out; replies post under the user's login and
a recognisable colleague's voice under it is its own tell. The corpus is
not shipped; the derived rules and a few anonymised shape examples are.

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

`<repo_root>/.pr-autopilot/watch-<session_id>.json`, separate from the
library's `pr-<N>.json` so `context-schema.md` is untouched. Written with
the library's atomic tmp+mv primitive.

```
{
  "session_id": "...",
  "self_login": "prpande",
  "channel_id": "C0C15VC8Y0Z",
  "serialize_pushes": true,
  "bot_allowlist": ["sonarqube-mbodevme", "mindbody-ado-pipelines"],
  "notifications_etag": "W/\"...\"",
  "last_reconciliation": "<ISO-8601>",
  "prs": {
    "1411": {
      "role": "authored",
      "worktree": "D:\\...\\apptdetails-s2-hydration",
      "branch": "apptdetails-s2-hydration",
      "slack_ts": "1789105505.206109",
      "seen_ids": [...],
      "posted_reply_ids": [...],
      "escalated_ids": [...],
      "handled_top_level_ids": {"<id>": "<disposition>"},
      "last_head": "..."
    }
  },
  "push_queue": [1413]
}
```

The library's `pr-<N>.lock` is acquired for the duration of a fix and
released after, per `state-protocol.md`. The library's `pr-<N>.log` is
appended to during a fix so the audit trail stays in one place.

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
  minutes.

## 10. Reuse and what is owned

Reused unchanged from `pr-loop-lib`: Filters B and C of step 03, step 04
(dispatch, clustering, verifier, policy ladder), step 04.5, step 06,
`fixer-prompt.md`, `fixer-verifier-prompt.md`, `known-bots.md`,
`prompt-injection-defenses.md`, `secret-scan-rules.md`, `state-protocol.md`
(lock primitives), `log-format.md`, `platform/github.md`.

Not used: step 01 (wait cycle), step 02 (timestamp-bounded fetch), Filter
A, step 07 (templated replies), step 08 (quiescence), steps 09 to 11.

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
7. `--monitor` emits nothing across a run of 304 responses.
8. An attempt to push on a `reviewed` PR is refused by the push guard
   even when the state file is edited to say `authored`.
9. The first event on a PR creates one Slack root; later events reply in
   that thread and never create a second root.
10. A `pr-watch` commit carries no trailers.
11. `pr-autopilot` and `pr-followup` are byte-identical before and after.

## 12. Delivery

One PR, at the user's direction, over the file-count cap. The PR body
says so.

## 13. Decisions and their reasons

| Decision | Reason |
|---|---|
| Watch lives in the working session, not a scheduled process | The session holds the effort's context; a detached fixer makes worse calls on the findings that matter |
| Interrupt source is a persistent `Monitor` on `/notifications` | Repo webhooks need admin the user lacks (`/hooks` returns 404) and a public relay; the notifications API works with the current token, honours `If-None-Match`, and returns `X-Poll-Interval` |
| Plus a 5-minute head sweep | A bare push raises no notification, and the head move is the re-review trigger |
| Parent session relocates per PR; no child process, no subagent switching | Subagents cannot write into another worktree even after `EnterWorktree(path)`; a headless child loses the conversation and hits permission prompts |
| Unit of work is the thread tail after the last posted reply id | Catches replies mid-thread from anyone, including the user; needs no marker in the body |
| Human and bot findings share one fix path | The tiers differ only in the resolve rule and the one-round rule, not in who verifies |
| Fixed hard-stop list | An agent can nearly always persuade itself the existing code settles a question |
| No markers, no templates, no trailers on anything a colleague can see | The user's requirement; automation must not be visible on the PR |
| Voice derived from a hand-reviewing colleague's traits | The user's own recent replies were AI-composed |
| Slack channel with one thread per PR | The user's requirement; channel is only about PRs in flight |
| No stop other than the user's | The user's requirement |
| Discovery per repo, not org-wide | SAML partial results return HTTP 200 with PRs silently omitted |
