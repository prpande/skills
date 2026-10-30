# Step 02 — Arm the monitor

A central watch (`--central`) never arms a Monitor; step 01 section 9
ends there for it.

## Arm

Run `POLL --monitor-alive --session-dir <SESSION_DIR>`. When it prints
`alive`, do not arm a second one. It reads the running processes, so it
holds after the task id is lost to compaction.

Call `Monitor` with:

- `command`: `python "<SKILL_DIR>/scripts/poll.py" --monitor --session-dir "<SESSION_DIR>"`
- `timeout_ms`: `1800000`. `Monitor` clamps anything larger to its own
  cap without saying so, so a bigger number buys nothing and hides what
  the monitor will actually do; read the cap off the arming result,
  which states when the monitor expires.
- `description`: `pr-watch events for this session`

The timeout is a ceiling on one stretch of watching, not on the watch:
the monitor is armed again each time it ends, until no PR in the watch
is still armed. Each PR leaves when it closes or merges, is released,
or is stopped; the next PR to join arms it again.

Remember the task id in the conversation; nothing on disk records it.
Every arming returns a new one, so each re-arm below replaces the
remembered id. `/pr-watch stop` stops whatever the last arming returned;
on an id left over from an expired task it would stop nothing, and the
live monitor then ends on its own once no entry is `armed`. Whether a monitor runs is always decided by
`POLL --monitor-alive`, never by the remembered id.

The first tick is a full reconciliation, so the first events arrive within
a minute for every PR with pending work.

## After relocation

The monitor keeps delivering while the session is in a PR worktree;
nothing to do on return.

## Stream ended

A monitor ends in one of three ways, and the notification says which.

After an `idle` event (`pr-watch/steps/03-route-event.md`) the stream
ends because no PR in the watch is still `armed`. This is a planned end:
do not arm again and post no "Watch monitor restarted." line. The next PR
to join starts a new monitor.

A monitor this session ended on purpose (step 01 section 4 ending an old
poller, step 01 section 9's central switch, `/pr-watch stop`, or a
`release` that leaves no `armed` PR) is not armed again and posts nothing.
So is any ending in a session whose `watch.json` has `"watcher": "central"`:
arm nothing and post nothing.

An expiry notice names the deadline it reached and the number of events
it delivered ("Monitor expired after 30m with 2 events delivered"). This
is the common one: on a 30-minute cap a watch that runs an afternoon
sees it several times. Arm it again as above, keep the new task id, and
post nothing — the first tick after re-arming is a full reconciliation,
so work that arrived in the gap comes through as its own event.

Any other ending is the poller exiting or dying, and the notice carries
its exit code or its output instead. Arm it again, keep the new task id,
and post "Watch monitor restarted." in each PR thread whose progress file
has a `slack_ts` (`pr-watch/steps/06-notify.md`), so the thread records the gap. If the
next arming ends the same way rather than at its deadline, stop
re-arming and tell the user what the notice said; the watch is down
until they fix it.

## Stop

Under `dry_run` the watch holds no leases, so `stop` and `release` skip
every `POLL --lease-status` call below.

`/pr-watch stop` writes `watch.json` first: `stopped_at` is the current
epoch seconds and every `armed` entry's `status` becomes `stopped`; a
`released`, `closed`, or `lost` entry is left as it is. Then it runs
`POLL --lease-status <owner/repo#N> --status stopped --session-dir
<SESSION_DIR>` for each entry it changed, calls `TaskStop` on the monitor when its
task id is known, and posts the closing reply per PR thread. With the
entries `stopped` the monitor sees no `armed` PR and exits, so a lost task
id still ends it. The state files stay.

`/pr-watch release owner/repo#N` writes the entry's `status` as
`released` in `watch.json` first, then runs
`POLL --lease-status <owner/repo#N> --status released --session-dir
<SESSION_DIR>`, skipping the second step for a `lost` entry. Another
session may then claim the PR.

A `POLL --lease-status` call in `stop` or `release` that exits non-zero
is run once more. If it fails again, tell the user which PR's lease
still reads `armed` and print its stderr line: with the monitor gone
the heartbeat goes stale, and an orchestrator would then nudge this
session to re-arm that PR.
