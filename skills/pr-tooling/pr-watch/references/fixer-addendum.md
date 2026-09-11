# pr-watch fixer addendum

Appended after `pr-loop-lib/references/fixer-prompt.md` for every fixer
`pr-watch` dispatches. Where this addendum and the fixer prompt disagree,
this addendum wins.

## Settle it from the repository first

Before editing anything, answer these in order and cite what you found:

a. Does a shipped surface already return this? Look for the REST mapper,
   response model, or existing resolver for the same domain field. If one
   does, this PR inherits its semantics; match them.
b. Is the flagged code in this PR's diff
   (`git diff origin/{{BASE_BRANCH}}...HEAD --stat`)? Pre-existing code
   the PR only made reachable is not this PR's decision; say so rather
   than changing it.
c. When the comment says the code is unlike its siblings, count both
   sides before accepting it, and list what you counted.
d. Can the fix be made in this PR? If an upstream layer already collapsed
   the distinction the comment wants, the fix belongs to that layer and
   its shipped consumers; do not make it here.

## Allowed sources

This repository; other repositories checked out beside it, read-only
(never edit, build, or commit there); and the GitHub API through `gh`,
read-only. Nothing else: no web search, no package registry, no guessing
an API's behaviour from its name.

## Hard stops

Return `needs-human`, naming the stop in `reason`, when the fix needs any
of:

- a behaviour change on a shipped endpoint;
- a schema or contract change;
- new SQL, or a change to a repository query;
- anything the PR body names as an open question;
- no precedent found by checks a to d;
- a merge conflict with `origin/{{BASE_BRANCH}}`.

Return `needs-human` wherever the fixer prompt would have you return
`ui-deferred`. Never return `ui-deferred`.

## Verdicts

Use `fixed`, `fixed-differently`, `replied`, `not-addressing`, or
`needs-human`.

- The comment is wrong about the current code: `not-addressing`, with the
  evidence (file, line, what the code does) in `reason`.
- The code the comment refers to is gone or already changed: `replied`,
  with the current code in `reason`.
- A question the code answers: `replied`, with the answer in `reason`.
- The last comment in the thread is by the PR's author: it is the
  author's instruction. If it reads as a disposition rather than a
  request, return `replied` with no change.

## Reply text

`reply_text` is facts for the reply, not the reply: what changed or why
nothing did, the file and line, and the evidence. No greeting, no
"Addressed:" or "Not addressing:" prefix, no account of your process. The
session writes the posted reply from these facts.

Every disposition cites what settled it; never a bare "no change needed".
