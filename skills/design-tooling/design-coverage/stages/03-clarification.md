# Stage 03 — Clarification (platform-agnostic core)

## Inputs

- `02-code-inventory.json` from stage 2.
- Live interactive session with the user.

## Preflight

```bash
# Resolve the skill root portably: walk up from CWD to find SKILL.md.
cd "$(python -c 'from pathlib import Path; p=Path.cwd(); print(next(q for q in [p, *p.parents] if (q/"SKILL.md").exists()))')"
```

## Objective

Resolve hotspots — decision points whose rendered UI depends on runtime data that stage 2 cannot fully inspect statically (feature flags, permissions, server-driven content, responsive branches, user roles, etc.). Ask the human live, in-session, one question at a time. Write answers to `03-clarifications.json`.

**This stage runs in the main session. Do not hand off a file for the user to edit — ask directly.**

## Method (deterministic — wave 1)

Stage 03 emits exactly two kinds of questions, both from deterministic sources:

### A. Hotspot questions (one per distinct hotspot symbol)

Call `emit_questions_for_inventory(stage2_inventory, platform_overrides)` from
`lib/hotspot_questions.py`. The function returns a list of Question objects;
ask each one via the live AskUserQuestion interface (never via file handoff).

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_root import get_skill_root
from hotspot_questions import emit_questions_for_inventory
from skill_io import read_json

run_dir = Path(...)  # set by orchestrator
SKILL_ROOT = get_skill_root()
inventory = read_json(run_dir / "02-code-inventory.json")
# platform_overrides come from the platform hint's `hotspot_question_overrides`
# frontmatter field (wave 2 #10); for wave 1, default to {}.
platform_overrides: dict[str, str] = {}
questions = emit_questions_for_inventory(inventory, platform_overrides)
```

For each Question, present the rendered_text, capture the user's answer, and
record it in `03-clarifications.json`'s `resolved` array. For each Question,
format `hotspot_id` as `f"{hotspot_type}:{symbol}"` when persisting to
`resolved[]` — stage 05 joins on this exact string.

### B. Candidate-destination scope (one multi-select per parent screen)

Read `02-code-inventory.json`'s `candidate_destinations` field. Group by
`parent_screen` (the symbol that's the navigation source). For each group,
emit ONE multi-select question:

> "Reachable from `<parent_screen>` in N hops:
>  - `<candidate_1.symbol>` (`<file>`)
>  - `<candidate_2.symbol>` (`<file>`)
>  - ...
> All checked by default. Uncheck any to exclude from this audit."

Persist the user's selections in `03-clarifications.json`'s
`in_scope_destinations` array:

```json
"in_scope_destinations": [
  {
    "parent_screen": "MBOApptDetailViewController",
    "destinations": ["MBOApptQuickBookViewController", "MBOClientProfileViewController"]
  }
]
```

Stage 05 reads this list to know which candidates to flag as `missing` if
Figma has no counterpart.

### Short-circuit on empty

If both `emit_questions_for_inventory` returns `[]` AND `candidate_destinations`
is empty, write `{"resolved": [], "in_scope_destinations": []}` to
`03-clarifications.json` immediately and exit. Do not enter a dialogue.

## Output

Write `03-clarifications.json` to the run dir conforming to the skill's `schemas/clarifications.json`, then regenerate the Markdown view:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_io import atomic_write_json
from renderer import render_clarifications

atomic_write_json(run_dir / "03-clarifications.json", clarifications)
(run_dir / "03-clarifications.md").write_text(render_clarifications(clarifications))
```

<!-- PLATFORM_HINTS -->
