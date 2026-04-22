# skills

User-level Claude Code skills maintained by @prpande.

## Skills

| Skill | Purpose |
|---|---|
| [`pr-autopilot`](./pr-autopilot/SKILL.md) | Autonomously publish a PR and drive it through the reviewer-bot feedback loop until CI is green. |
| [`pr-followup`](./pr-followup/SKILL.md) | Re-enter the same comment loop later when human or late bot comments arrive. |

## Supporting library

[`pr-loop-lib/`](./pr-loop-lib/README.md) — shared per-step markdown
library imported by both skills. Not a skill itself (no `SKILL.md`).

## Prompts

Standalone prompts you can paste into a Claude conversation — no install step.

| Prompt | Purpose |
|---|---|
| [`attention-status-page`](./prompts/attention-status-page.md) | Build a live "What needs your attention" HTML artifact that pulls from your connected tools (Slack, Notion, Asana, Linear, Jira, email) and groups items by work item. |

## Design docs

- [2026-04-17 pr-autopilot skill design](./docs/superpowers/specs/2026-04-17-pr-autopilot-skill-design.md)
- [2026-04-17 pr-autopilot skill implementation plan](./docs/superpowers/plans/2026-04-17-pr-autopilot-skill-implementation.md)

## Installation

Symlink (or copy) each skill folder into `~/.claude/skills/`:

```bash
ln -s "$PWD/pr-autopilot"  "$HOME/.claude/skills/pr-autopilot"
ln -s "$PWD/pr-followup"   "$HOME/.claude/skills/pr-followup"
ln -s "$PWD/pr-loop-lib"   "$HOME/.claude/skills/pr-loop-lib"
```

On Windows with Git Bash, use `cmd //c mklink /D` or copy:

```bash
cp -r pr-autopilot   "$HOME/.claude/skills/pr-autopilot"
cp -r pr-followup    "$HOME/.claude/skills/pr-followup"
cp -r pr-loop-lib    "$HOME/.claude/skills/pr-loop-lib"
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
