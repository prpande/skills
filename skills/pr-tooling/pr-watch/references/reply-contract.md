# Reply contract

Every reply `pr-watch` posts on GitHub follows this contract. The replies
post under the user's login and must read as the user typing them by
hand. The contract says what a reply carries and what it must never say.
The wording comes from the user's voice profile when one is usable, and
is written plainly otherwise.

## Shapes

- **Fixed.** Carries the short sha and what changed. Must not restate the
  comment or explain why it was right.
  A dry run commits nothing, so a reply it writes to the dry-run file
  carries `<no sha: dry run>` in the sha's place and satisfies the audit
  with it.
- **Refuted.** Carries the evidence: file, line, what the code does. Must
  not argue or hedge; the evidence does the disagreeing.
- **Superseded.** Carries what the code says now and the commit that
  changed it.
- **Answered and left open.** Carries what is pending and why. Must not
  promise a date or future work.
- **Re-review verdict.** One line per finding: the verdict in plain words,
  then the evidence.
- **Closing a thread as author.** One line, or nothing.

A file is cited by its repo-relative path in plain text, or by a GitHub
link to the line range at a commit. Line numbers go in the link, not in
the prose.

## Never

No greeting, no thanks-opener, no "Addressed:" or "Not addressing:" or
any prefix, no restating the comment, no summary of what was checked, no
"Great catch", no promise of future work, no mention of tools, agents,
automation, or a process. No phrase lifted from any colleague. No
@-mention of a bot account.

## Writing a reply

1. **Check the profile.** Use the user's voice only when all of these
   hold:
   - `~/.claude/skills/human-reply/SKILL.md` exists
   - `~/.claude/human-reply/channels/github.md` exists
   - the lines of that file before its first `##` heading contain neither
     `partial` nor `estimated`
   - in its Surfaces table, the row for the surface being written is not
     labelled `estimated`: `review thread reply` for a thread reply,
     `issue comment` for a top-level reply

   When any of them fails, skip to step 4.
2. **Draft.** Invoke the `human-reply` skill with `draft`, channel
   `github`, the surface, and an ask that names the shape and lists what
   the shape must carry, with the facts filled in (the sha, the evidence
   link, the pending reason). Take the text inside its fenced block and
   nothing else.
3. **Audit.** Run the audit below on that text. When it passes, the reply
   is that text. When it fails, invoke `human-reply` once more with the
   same ask plus each failing item stated as content to add or remove,
   such as "include the short sha 3f9c2e1" or "remove the opening
   thanks". When the second draft also fails, go to step 4 and post the
   Slack "voice fallback" line from `pr-watch/steps/06-notify.md`.
4. **Plain reply.** Write the reply yourself in one to four plain
   sentences that carry what the shape requires and break nothing under
   Never, then run the audit below.

Under `dry_run`, the same steps run; only the posting is replaced.

## Audit before posting

Each line must answer yes.

1. Does the reply fit exactly one shape above and carry what that shape
   requires (sha, evidence, pending reason), counting the dry-run
   placeholder as the sha?
2. Is the evidence a path, a line-range link, or a sha (or the dry-run
   placeholder), not a paragraph?
3. Is nothing from the comment being answered repeated?
4. Is it free of everything under Never?
5. Nothing that says or implies the reply was generated, checked by a
   tool, or part of a process?
