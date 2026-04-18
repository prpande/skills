# pr-loop-lib

**This is an include library, not a skill.** Deliberately has no `SKILL.md`,
so Claude Code does not register it as an invocable skill.

Both `pr-autopilot` and `pr-followup` reach into this folder by path to
share the PR-comment loop logic. Editing a step file here changes both
skills symmetrically.

## Layout

- `steps/` — the comment/CI loop phases, numbered in execution order.
- `platform/` — one file per target platform (`github.md`, `azdo.md`).
- `references/` — cross-cutting content: bot signatures, fixer prompt,
  prompt-injection defenses, secret-scan rules, PR-template fallback.

## Customizing

Any step file can be edited in place. The orchestrator `SKILL.md` of each
invoking skill references files here by relative path (`pr-loop-lib/...`)
or absolute (`~/.claude/skills/pr-loop-lib/...`) — both are valid.
