# Step 02 — Arm the monitor

## Arm

If this session already has a running monitor for this watch (a resume in
the same session), do not arm a second one.

Call `Monitor` with:

- `command`: `python "<SKILL_DIR>/scripts/poll.py" --monitor --state-dir "<STATE_DIR>"`
- `timeout_ms`: `1800000`. `Monitor` clamps anything larger to its own
  cap without saying so, so a bigger number buys nothing and hides what
  the monitor will actually do; read the cap off the arming result,
  which states when the monitor expires.
- `description`: `pr-watch events for <SLUG>`

The timeout is a ceiling on one stretch of watching, not on the watch:
the monitor is armed again each time it ends, until `/pr-watch stop`.

Remember the task id in the conversation; nothing on disk records it.
Every arming returns a new one, so each re-arm below replaces the
remembered id. `/pr-watch stop` stops whatever the last arming returned;
on an id left over from an expired task it would stop nothing and leave
the live monitor running.

The first tick is a full reconciliation, so the first events arrive within
a minute for every PR with pending work.

## After relocation

The monitor keeps delivering while the session is in a PR worktree;
nothing to do on return.

## Stream ended

A monitor ends in one of two ways, and the notification says which.

An expiry notice names the deadline it reached and the number of events
it delivered ("Monitor expired after 30m with 2 events delivered"). This
is the common one: on a 30-minute cap a watch that runs an afternoon
sees it several times. Arm it again as above, keep the new task id, and
post nothing — the first tick after re-arming is a full reconciliation,
so work that arrived in the gap comes through as its own event.

Any other ending is the poller exiting or dying, and the notice carries
its exit code or its output instead. Arm it again, keep the new task id,
and post "Watch monitor restarted." in each PR thread that has a root
(`pr-watch/steps/06-notify.md`), so the thread records the gap. If the
next arming ends the same way rather than at its deadline, stop
re-arming and tell the user what the notice said; the watch is down
until they fix it.

## Stop

`/pr-watch stop` calls `TaskStop` on the monitor and posts the closing
reply per PR thread. The state files stay.
