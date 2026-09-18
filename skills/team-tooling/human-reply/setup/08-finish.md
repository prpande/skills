# Setup 8: Finish

Let the person check their own messages before they are kept, write the
profiles, and clean up.

## 1. Review the examples

Profiles are permanent and their shape examples are the person's own
messages. Print every example from every `draft/channels/<channel>.md`
in one numbered list, grouped by channel and shape. Ask the person to
name any number to strike or to replace with other wording. Apply the
answer to the draft files. A shape left with no example keeps its
skeleton.

## 2. Write

First make the `status` line of each `draft/channels/<channel>.md`
list every reason in `per_channel.<channel>.partial`, in the header format
from `human-reply/references/profile-schema.md`, adding the line when the
list is not empty. Then copy `<home>/corpus/draft/profile.md` to
`<home>/profile.md` and each `draft/channels/<channel>.md` to
`<home>/channels/<channel>.md`, replacing what was there.

## 3. Summary

Print:

- the path of every file written
- per channel: kept records, window, drop count, method, threshold, and
  calibration result
- every channel in `skipped`, with its reason
- every channel marked partial, with each reason

## 4. Clean up

1. Delete every `borrow-*` file in `<home>/corpus/` without asking.
2. When any `per_channel.<channel>.redaction` is `"model"`, delete
   `<home>/corpus/` and say it was deleted because the model did the
   redaction.
3. Otherwise ask one question: keep the collected messages, or delete
   them. Keep leaves the person's own `<channel>*.jsonl` files and deletes
   everything else in `<home>/corpus/`, including `setup.json` and
   `draft/`. Delete removes `<home>/corpus/`.

End with: `setup <channel>` rebuilds one channel, and `setup` rebuilds
all of them.
