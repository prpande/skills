# Stage 03 — Clarification (platform-agnostic core)

## Inputs

- `02-code-inventory.json` from stage 2.
- Live interactive session with the user.

## Preflight

```bash
cd ~/.claude/skills/design-coverage/
```

## Objective

Resolve hotspots — decision points whose rendered UI depends on runtime data that stage 2 cannot fully inspect statically (feature flags, permissions, server-driven content, responsive branches, user roles, etc.). Ask the human live, in-session, one question at a time. Write answers to `03-clarifications.json`.

**This stage runs in the main session. Do not hand off a file for the user to edit — ask directly.**

## Method (platform-agnostic)

1. **Identify hotspots** from the code inventory:
   - States whose entry condition depends on a flag / permission / role / server-driven response.
   - Fields whose visibility is conditional on the above.
   - Screens that branch by responsive config or device capability.
   - Lists whose item types vary by runtime data.
   - Any component annotated or named in a way that suggests runtime variance.
2. **Short-circuit on empty.** If the hotspot list is empty, write `{"resolved": []}` to `03-clarifications.json` immediately and exit. Do not enter a dialogue with no questions.
3. **Ask sequentially.** For each hotspot, pose a single concrete question to the user. Record the answer and its impact on the inventory (if any — e.g., a flag confirmation may promote a state from "speculative" to "real").

## Output

Write `03-clarifications.json` conforming to `~/.claude/skills/design-coverage/schemas/clarifications.json`. Regenerate via `python -m lib.renderer --render 3 <run-dir>`.

<!-- PLATFORM_HINTS -->
