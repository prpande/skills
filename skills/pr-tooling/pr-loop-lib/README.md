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
  `references/context-schema.md` defines every state key the steps
  write, including the fix-wave keys (`unit_bases` with each fixer's
  `dispatched_at` and `returned_at`, `agent_clock`, the `verify_*` keys)
  and the pre-open review keys (`context_check_answers` with
  `flipped_by` and `settled_item`, `dismissed_checks`).
- `scripts/` — `agent_wait.py` waits on background fixers and verifiers
  against their time limits (10 minutes and 3, step 04 "Time limits");
  `agent_cap_wait.py` waits for a free slot when the agent cap refuses a
  spawn (step 04 "Agent-cap wait"); `copilot_review.py` pulls the findings out of a Copilot review body
  (`references/known-bots.md`). Tests live in
  `skill-tests/pr-loop-lib/`.

## Customizing

Any step file can be edited in place. The orchestrator `SKILL.md` of each
invoking skill references files here by relative path (`pr-loop-lib/...`)
or absolute (`~/.claude/skills/pr-loop-lib/...`) — both are valid.
