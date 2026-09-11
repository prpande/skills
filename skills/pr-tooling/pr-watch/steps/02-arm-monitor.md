# Step 02 — Arm the monitor

## Arm

If this session already has a running monitor for this watch (a resume in
the same session), do not arm a second one.

Call `Monitor` with:

- `command`: `python "<SKILL_DIR>/scripts/poll.py" --monitor --state-dir "<STATE_DIR>"`
- `persistent`: `true`
- `timeout_ms`: `3600000` (ignored when persistent)
- `description`: `pr-watch events for <SLUG>`

Remember the task id in the conversation; nothing on disk records it.

The first tick is a full reconciliation, so the first events arrive within
a minute for every PR with pending work.

## After relocation

The monitor keeps delivering while the session is in a PR worktree;
nothing to do on return.

## Stream ended

If a notification says the monitor stream ended, arm it again as above and
post "Watch monitor restarted." in each PR thread that has a root
(`pr-watch/steps/06-notify.md`).

## Stop

`/pr-watch stop` calls `TaskStop` on the monitor and posts the closing
reply per PR thread. The state files stay.
