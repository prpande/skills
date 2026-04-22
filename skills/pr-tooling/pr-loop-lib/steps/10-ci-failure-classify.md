# Loop step 10 — CI failure classify

Runs only when step 09 reports one or more red checks. Classifies each and
routes to auto-fix or surface-to-user.

## Classification table

For each red check, determine class. Name-match regexes are declared in a
fenced code block below (one per class) so markdown-table escaping does not
alter the meaning of `|` alternation. Regex flavor: Python `re` (also
compatible with `grep -E` / ripgrep).

```
# Lint/format — check name matches any of:
lint|format|style|prettier|eslint|dotnet-format

# Compile/build
build|compile

# Real test failure
test|spec|unit|integration
```

| Class | Detection | Handling |
|---|---|---|
| Lint/format | Check name matches the lint/format regex above; log shows rule violations | Run the formatter locally (e.g., `dotnet format`, `npm run lint -- --fix`, `cargo fmt`), commit as "fix: apply formatter", push, re-enter loop |
| Compile/build | Check name matches the compile/build regex above; log contains compiler errors | Dispatch a fixer subagent with the error output and the head commit diff; apply fix, commit, push, re-enter |
| Real test failure | Check name matches the test regex above; failing test passed on the base branch (determine via `git log -1 --format=%H origin/<base>` and running the test locally if possible) | Dispatch a fixer with the failing test output; apply fix, commit, push, re-enter |
| Pre-existing main-fail | Same check currently red on `origin/<base>` | Surface to user via final report; do NOT loop |
| Flake | Check was green on a previous run of the same HEAD SHA with no intervening code change; OR test path is listed in a repo-maintained known-flaky file | `gh run rerun <run-id>`; if still red, reclassify as real test failure |

## Log retrieval

GitHub:
```bash
gh run view <run-id> --log-failed
```

AzDO:
```bash
az pipelines runs show --id <run-id> --output json
# Then fetch logs via the URL in the response
```

Feed the log output (truncated to last 5000 lines if larger) to the fixer
subagent as the "feedback body" in the fixer-prompt template.

## Outer cap

`context.ci_reentry_count` is incremented each time step 10 decides to
re-enter the loop. When it reaches 3, do NOT re-enter again; proceed to
step 11 with `context.termination_reason = "ci-reentry-cap"`.

## Routing

- Every red check is Lint/format, Compile, or Real test, and after fixes
  there is at least one code change staged → commit, push, re-enter
  loop step 01 (wait cycle).
- One or more red checks are Pre-existing main-fail → skip them, surface
  in final report, treat remaining fixable ones as above. If there are no
  fixable remaining → proceed to step 11 with
  `context.termination_reason = "ci-pre-existing-failures"`.
- All red checks are Flake and reruns succeed → re-enter step 09 (do not
  count against the outer cap; flake-reruns are not fixes).
- Cap reached → step 11 with `context.termination_reason = "ci-reentry-cap"`.
- One or more red checks **cannot be classified** (name matches none of
  the lint/compile/test regexes, is not flake, and is not pre-existing
  main-fail) → step 11 with `context.termination_reason = "ci-red"`.
  This distinguishes a genuine "CI is red and we don't know how to
  move it forward" exit from the cap exit. The per-check detail in the
  final report identifies which checks were unclassifiable so the
  operator can investigate.
