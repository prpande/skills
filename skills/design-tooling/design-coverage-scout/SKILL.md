---
name: design-coverage-scout
description: >
  Companion skill to design-coverage that inspects an unfamiliar repository
  and emits a new platforms/<name>.md hint file conforming to the shared
  template. Runs a three-stage pipeline: stack profile → pattern extraction
  → hint rendering with explicit draft/approve gating. Writes drafts only;
  never auto-commits. Use when the user says "/design-coverage-scout", runs
  design-coverage on an unknown stack and picks "generate a hint", or asks to
  "bootstrap a new platform for design-coverage".
argument-hint: "[--platform-name <name>] [--force]"
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent
---

# design-coverage-scout

Three-stage pipeline that characterizes an unfamiliar UI repo and emits a
platform hint file for design-coverage. Writes drafts only; never auto-commits.

## Preflight

```bash
cd ~/.claude/skills/design-coverage-scout/
```

## Argument parsing

- `--platform-name <name>` — override the name used in the hint frontmatter
  and filename. If omitted, derive from the detected stack (e.g., `ios`,
  `android`, `react-native`).
- `--force` — overwrite an existing `platforms/<name>.md` without draft
  gating. **Use with care** — prefer reviewing the draft.

## Run directory

Intermediate artifacts (`stack-profile.json`, `hint-draft.json`) land inside
the target repo so they're inspectable alongside the rest of its docs. The
final hint file still writes to the design-coverage install — see
`Final output` below.

```bash
# Anchor to the Git root of CWD so re-runs from subdirectories land in the
# same place. Fall back to CWD if we're not inside a Git repo.
OUTPUT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# Resolve the run-dir slug: prefer the user's --platform-name if passed,
# else fall back to the repo directory name. This slug is for operator
# organization of scout runs on disk only — the final hint filename can
# differ if stage 01 picks a more specific name.
NAME="${PLATFORM_NAME:-$(basename "$OUTPUT_DIR")}"
RUN_DIR="$OUTPUT_DIR/docs/design-coverage-scout/$(date +%Y-%m-%d)-$NAME"
mkdir -p "$RUN_DIR"
```

## Stage pipeline

1. **Stage 01 — Stack profile.** Dispatch a subagent with
   `stages/01-stack-profile.md`. Output: `<run-dir>/stack-profile.json`.
   On refuse-loud (multi-UI monorepo, no UI detected), exit with the
   refusal message.

2. **Stage 02 — Pattern extraction.** Dispatch a subagent with
   `stages/02-pattern-extraction.md`. Output: `<run-dir>/hint-draft.json`.
   If `confidence == "low"` and no patterns were harvested, exit and tell the
   user to author manually from `hint-template.md`.

3. **Stage 03 — Hint rendering.** Dispatch a subagent with
   `stages/03-hint-rendering.md`. This stage is **interactive** — it prompts
   the user to approve the draft live in the session.

## Final output

On successful rendering, print:

```
Hint written to <absolute-path>.

To share with other users:
  1. cd into the skills-repo clone that contains this file.
  2. git add <relative-path>
  3. git commit -m "design-coverage: add platforms/<name>.md (scout-generated)"
  4. git push and open a PR.
```

If the fallback path (`~/.claude/skills/design-coverage/platforms/`) was
used, additionally print:

```
NOTE: You installed via copy, not symlink. The hint file is in your local
install directory only. Copy it to your skills-repo clone to share.
```
