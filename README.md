# skills

User-level Claude Code skills maintained by @prpande.

## Skills

| Skill | Purpose |
|---|---|
| [`pr-autopilot`](./skills/pr-tooling/pr-autopilot/SKILL.md) | Autonomously publish a PR and drive it through the reviewer-bot feedback loop until CI is green. |
| [`pr-followup`](./skills/pr-tooling/pr-followup/SKILL.md) | Re-enter the same comment loop later when human or late bot comments arrive. |
| [`deep-review`](./skills/pr-tooling/deep-review/SKILL.md) | Multi-angle adversarial code review of a PR, branch, or local changes, graded against a curated lens register; also the register's canonical home (consumed by `pr-autopilot` preflight when installed). |
| [`design-coverage`](./skills/design-tooling/design-coverage/SKILL.md) | Compare an existing in-code UI flow against a new Figma design and produce an auditable discrepancy report. |
| [`design-coverage-scout`](./skills/design-tooling/design-coverage-scout/SKILL.md) | Companion skill that inspects an unfamiliar repo and emits a new `platforms/<name>.md` hint file for `design-coverage`. |
| [`api-e2e`](./skills/api-tooling/api-e2e/SKILL.md) | Interview-driven, fresh-context staging E2E validation of a backend API PR or deployed endpoint: repo-head-derived expectations, build fingerprinting, risk-tiered matrix, four-way failure triage, redacted durable report. |
| [`squad-learnings`](./skills/team-tooling/squad-learnings/SKILL.md) | Per-machine ledger of engineering learnings, captured as they happen; `install` wires proactive capture into the user's global CLAUDE.md, `review` compiles a quarter-half readout. Works on a bare Claude Code install. |
| [`contribution-log`](./skills/career-tooling/contribution-log/SKILL.md) | Local-first record of what the user delivered, captured at milestone moments; window-based `review` (week/month/cycle/quarter/year) with opt-in GitHub/ADO/Notion/Slack enrichment, and a `promo` mode for annual-review and promotion packages. |

## Supporting library

[`pr-loop-lib/`](./skills/pr-tooling/pr-loop-lib/README.md) — shared per-step markdown
library imported by both skills. Not a skill itself (no `SKILL.md`).

## Prompts

Standalone prompts you can paste into a Claude conversation — no install step.

| Prompt | Purpose |
|---|---|
| [`attention-status-page`](./prompts/attention-status-page.md) | Build a live "What needs your attention" HTML artifact that pulls from your connected tools (Slack, Notion, Asana, Linear, Jira, email) and groups items by work item. |

## Design docs

- [2026-04-17 pr-autopilot skill design](./docs/superpowers/specs/2026-04-17-pr-autopilot-skill-design.md)
- [2026-04-17 pr-autopilot skill implementation plan](./docs/superpowers/plans/2026-04-17-pr-autopilot-skill-implementation.md)
- [2026-04-22 design-coverage platform-agnostic design](./docs/superpowers/specs/2026-04-22-design-coverage-platform-agnostic-design.md)
- [2026-04-22 design-coverage platform-agnostic implementation plan](./docs/superpowers/plans/2026-04-22-design-coverage-platform-agnostic.md)

## Installation

Symlink (or copy) each skill folder into `~/.claude/skills/`:

```bash
ln -s "$PWD/skills/pr-tooling/pr-autopilot"              "$HOME/.claude/skills/pr-autopilot"
ln -s "$PWD/skills/pr-tooling/pr-followup"               "$HOME/.claude/skills/pr-followup"
ln -s "$PWD/skills/pr-tooling/deep-review"               "$HOME/.claude/skills/deep-review"
ln -s "$PWD/skills/pr-tooling/pr-loop-lib"               "$HOME/.claude/skills/pr-loop-lib"
ln -s "$PWD/skills/design-tooling/design-coverage"       "$HOME/.claude/skills/design-coverage"
ln -s "$PWD/skills/design-tooling/design-coverage-scout" "$HOME/.claude/skills/design-coverage-scout"
ln -s "$PWD/skills/api-tooling/api-e2e"                  "$HOME/.claude/skills/api-e2e"
ln -s "$PWD/skills/team-tooling/squad-learnings"         "$HOME/.claude/skills/squad-learnings"
ln -s "$PWD/skills/career-tooling/contribution-log"      "$HOME/.claude/skills/contribution-log"
```

On Windows with Git Bash, use `cmd //c mklink /D` or copy:

```bash
cp -r skills/pr-tooling/pr-autopilot              "$HOME/.claude/skills/pr-autopilot"
cp -r skills/pr-tooling/pr-followup               "$HOME/.claude/skills/pr-followup"
cp -r skills/pr-tooling/deep-review               "$HOME/.claude/skills/deep-review"
cp -r skills/pr-tooling/pr-loop-lib               "$HOME/.claude/skills/pr-loop-lib"
cp -r skills/design-tooling/design-coverage       "$HOME/.claude/skills/design-coverage"
cp -r skills/design-tooling/design-coverage-scout "$HOME/.claude/skills/design-coverage-scout"
cp -r skills/api-tooling/api-e2e                  "$HOME/.claude/skills/api-e2e"
cp -r skills/team-tooling/squad-learnings         "$HOME/.claude/skills/squad-learnings"
cp -r skills/career-tooling/contribution-log      "$HOME/.claude/skills/contribution-log"
```

After installation, restart your Claude Code session. The skills appear in
`/<list>` under `pr-autopilot` and `pr-followup`.

## Validation

Run the structural validator before committing changes:

```bash
python scripts/validate.py
```

Exits 0 with `OK` on success; non-zero with per-file diagnostics on
failure.

## Smoke test

1. In any GitHub repo, make a trivial change on a feature branch.
2. Run `/pr-autopilot 2` (cap at 2 iterations for a quick test).
3. Verify: PR opens, template filled, first wait cycle begins.
4. Wait for at least one reviewer-bot cycle (10 min), observe that comments
   are addressed in the next iteration.
5. Observe the final report.
