# Merge rules

Deduplication and severity-escalation rules applied when merging
findings from multiple sources (pr-autopilot's pre-open lens agents,
`/code-review`, and review comments landing in iter 1).

## Why this file exists

When both a lens agent AND `/code-review` flag the same issue, we
want:
1. One consolidated finding in the user's view, not two.
2. Escalated severity signal (two independent reviewers converging
   is high confidence).

## Deduplication key

Two findings are "the same" when ALL of:
1. Same file path (exact match).
2. Line-range overlap — their `line` values are within 3 lines of each
   other. (3 is a tolerance for slight line-shift between pre-push
   diff and post-push diff.)
3. Same category. Categories are pulled from each finding's `category`
   field. A finding without a category defaults to `other` and never
   matches any other finding's category.

When all three match, the findings are considered the same issue.

### Triage override — normalized-lead hash (β)

Triage (`pr-loop-lib/steps/03-triage.md` Filter B.5) CANNOT use the
category-based key above because `CommentRecord` (the shape of triage
actionable items) has no `category` field. Under β Section 3, triage
dedups against preflight findings using a **normalized-lead-paragraph
SHA-1 hash**:

1. Strip fenced code blocks (` ``` … ``` `) and HTML tags from the
   candidate body.
2. Take the lead paragraph (everything up to the first blank line).
3. Lowercase and collapse whitespace to single spaces.
4. Truncate to 200 characters.
5. SHA-1; compare the hex digest (`description_hash`).

Path match is retained when both sides carry a path (exact match;
missing path on either side is "don't restrict by path"). The
preflight side stores the hash at
`context.preflight_passes.merged[].description_hash`; step 02 computes
it using the same five-step normalization so the two sides stay in
lock-step. See `pr-loop-lib/steps/03-triage.md` Filter B.5 Stage 2
for the receiving-side pipeline, and
`pr-autopilot/steps/02-preflight-review.md` "Per-finding
description_hash" for the emitting-side pipeline.

This override is authoritative for triage *and* for pr-autopilot
step 03.5's `/code-review` dedup. The category-based key above
remains the correct key when both sources carry `category` (e.g.,
merging two adversarial-prompt outputs).

**Note.** An earlier revision of this section described a looser
`line within 3 lines` + "normalized description equality"
(whitespace-trimmed + lowercased). β replaced that with the
hash-based scheme above — equality on a normalized-lead hash is
deterministic and tolerates bodies that bundle summary + snippet +
table (the common non-`/code-review` bot shape). If you see a
pointer to "Triage override" expecting the older equality form,
it's now this hash scheme.

## Lens-agent fold

pr-autopilot step 02 runs one lens agent per pack, each with the
Universal lenses, so two agents can report one defect. Before anything
else reads the list:

This fold is the only one applied to the lens agents' findings of one
run; the category key under "Deduplication key" is not applied on top.

1. Two lens findings match when they name the same file, their lines
   are within 3 of each other (or both are null), they describe the
   same failure, and one of these holds: they cite the same lens id,
   they share a `category`, or one carries a `check_id`. Never fold on
   file and line alone, or on a shared lens id alone: two lenses can hit
   one line, and one lens can flag two fields on adjacent lines.
2. Findings that match directly or through a chain of matches form one
   group, even when two members of the chain are more than 3 lines
   apart. Each group yields one entry in `merged`.
3. Keep the member with the lowest id. Give it the highest severity in
   the group (no escalation: the agents are not independent reviewers
   of the Universal lenses), `declared_risk: true` if any member has
   it, the `settled_item` and `check_id` of whichever member carries
   one, and every other member's id in `duplicate_ids[]`. Append to its
   description every lens id a member's description cites that it
   lacks, and each member's recommendation that differs from its own.

## Severity escalation

Severity strings match the adversarial-review-prompt's JSON output:
always lowercase `critical`/`important`/`minor`.

| Lens severity | `/code-review` severity | Merged severity |
|---|---|---|
| `critical` | any | `critical` (no escalation needed) |
| `important` | `important` or `critical` | `critical` |
| `important` | `minor` | `important` (no change) |
| `minor` | `important` or `critical` | `important` (escalated by one) |
| `minor` | `minor` | `minor` |

Single-source findings (only one pass flagged them) retain their
original severity.

## Preserved metadata on merged findings

```json
{
  "severity": "<escalated or original>",
  "file": "<shared>",
  "line": "<min of the two>",
  "description": "<adversarial's description, longer/more specific usually>",
  "recommendation": "<merged: adversarial's first, /code-review's appended>",
  "category": "<shared>",
  "sources": ["preflight-pass2", "code-review"],
  "original_severities": {
    "preflight-pass2": "important",
    "code-review": "minor"
  }
}
```

The `sources` array tells the user which passes flagged the issue.
`original_severities` is diagnostic — shows what each source said
before escalation.

## When to invoke the merge

- **Pre-open (pr-autopilot step 03.5)**: the lens agents and
  `/code-review` run together. Step 02 first folds the lens agents'
  own lists into one ("Lens-agent fold" above), and step 03.5
  D then merges that list with `/code-review`'s and with step 01.5's
  skipped points before one fix round. A merged finding is declared but
  risky when any of its sources marked it so. `/code-review` findings carry no `category`, so
  two findings are the same only when they name the same file and either
  their `description_hash` values are equal or their lines are within 3
  of each other and both describe the same failure.
- **Iter 1 of the comment loop**: when triage extracts `/code-review`'s
  comment findings (via the known-bot exemption rule), compare each
  against `context.preflight_passes.merged` (from preflight). For
  matches per the dedup key, mark the `/code-review` finding as
  already-addressed-in-preflight (skip dispatch) and append a note to
  the user's preflight PR body section. Non-matching `/code-review`
  findings dispatch normally.
- **Post-iter-1**: the merge is complete; later iterations don't
  re-merge.

Concretely, iter 1's step 03 (triage) runs the merge as a sub-step
between Filter B and Filter C. The filter chain becomes:

```
A (new-since-push) → B (actionability / known-bots) → B.5 (dedup against
preflight_passes.merged) → C (prompt-injection refusal)
```

## Determinism

The file, line-window, lens-id, category, hash and severity tests are
mechanical: given the same inputs they give the same result. Whether two
findings "describe the same failure" (the Lens-agent fold and the
pre-open merge with `/code-review`) is a judgement the LLM makes by
reading both descriptions; every other step of the merge applies the
rules above as written.
