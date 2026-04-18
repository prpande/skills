# Merge rules

Deduplication and severity-escalation rules applied when merging
findings from multiple sources (Pass 2 adversarial preflight and any
later `/code-review` output landing in iter 1).

## Why this file exists

When both the preflight adversarial pass AND `/code-review` (running
post-open) flag the same issue, we want:
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

## Severity escalation

| Pass 2 severity | `/code-review` severity | Merged severity |
|---|---|---|
| Critical | any | Critical (no escalation needed) |
| Important | Important or Critical | Critical |
| Important | Minor | Important (no change) |
| Minor | Important or Critical | Important (escalated by one) |
| Minor | Minor | Minor |

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

- **Preflight (step 02)**: no merge needed. Only Pass 2 runs; its
  output IS the finding list.
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

The merge is deterministic given the same inputs. The LLM performs it by
reading both finding lists and applying the three-step dedup key +
severity table mechanically. No judgement calls — if the key matches,
they're the same; if it doesn't, they're different.
