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

The first tick is a full reconciliation, so the first events arrive within
a minute for every PR with pending work.

## After relocation

The monitor keeps delivering while the session is in a PR worktree;
nothing to do on return.

## Stream ended

The monitor ends on its own once `timeout_ms` is up, and this is the
common notification: on a 30-minute cap a watch that runs an afternoon
sees it several times. Arm it again as above. Nothing is missed in the
gap and nothing is posted about it — the first tick after re-arming is a
full reconciliation, so pending work that arrived meanwhile comes through
as its own event.

A stream that ends well before the timeout ended for a reason. Arm it
again and post "Watch monitor restarted." in each PR thread that has a
root (`pr-watch/steps/06-notify.md`), so the thread records the gap. If a
second arming also ends within a minute, stop re-arming and tell the
user, with whatever the task's output held; the watch is down until they
fix it.

## Stop

`/pr-watch stop` calls `TaskStop` on the monitor and posts the closing
reply per PR thread. The state files stay.
