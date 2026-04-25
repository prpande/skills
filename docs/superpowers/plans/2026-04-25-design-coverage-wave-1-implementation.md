# Design-coverage wave 1 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship wave 1 of the design-coverage improvements (#1 hotspot question registry, #2 severity decision matrix, #3 out-of-scope as an explicit question, #6 skill-relative paths, plus the `lib/sealed_enum_index.py` helper that #3's closed-enum gate depends on) AND file 3 GitHub issues so future agents can pick up waves 2 and 3 in parallel sessions.

**Architecture:** Six new/modified Python modules in `skills/design-tooling/design-coverage/lib/`, three schema edits, four stage MD edits, one SKILL.md edit. Test-driven throughout (every Python module ships with a `skill-tests/design-coverage/tests/test_<module>.py`). Skill-relative path helper (`lib/skill_root.py`) is the foundation that everything else uses to import sibling modules.

**Tech stack:** Python 3 stdlib only (no new pip deps), pytest for tests, hand-rolled validator (`lib/validator.py`) — match the existing pattern. `gh` CLI for issue filing.

**Spec reference:** `docs/superpowers/specs/2026-04-25-design-coverage-improvements-design.md` (commits `de2d412`, `45c44f5`, `4500cd3` on branch `pratyush/design-coverage-improvements`).

**Worktree:** `C:/src/skills-design-coverage-improvements` on branch `pratyush/design-coverage-improvements`.

**Constraints:**
- Never push to remote (user pushes manually).
- Never commit to any branch other than `pratyush/design-coverage-improvements`.
- Each commit leaves the skill in a runnable state.
- Each commit message is value-communicating (says *why*, not just *what*).
- All Python uses stdlib only — no new dependencies.

**Test invocation:** `cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage && pytest tests/<test_file>.py -v` (the `conftest.py` in that directory adds `lib/` to `sys.path`).

## Implementation-vs-plan reconciliation (post-hoc)

This plan was written before implementation began. The shipping code in this PR
diverges from the plan in two narrow places, called out here so the plan stays
useful as a reference rather than misleading future readers:

1. **`schemas/inventory_item.json` `hotspot.required`** — plan specifies
   `["type", "question"]` (Task 2.2, line ~528). The shipping schema requires
   `["type", "symbol"]` and makes `question` optional/nullable. Rationale:
   `symbol` is the dedup key for `lib/hotspot_questions.py` and the join key
   for stage 05's hotspot_id; `question` is now generated deterministically by
   the registry and is no longer load-bearing. This is a knowing break of the
   spec's "additive only" non-goal — the skill is newly-shipped, no production
   run-dirs depend on the legacy shape, and the validator does not support
   `anyOf` for a write-strict / read-tolerant compromise.

2. **Stage 05 severity-loop join** — earlier draft snippets read `code_kind`
   and `inventory_item_hotspot` directly off comparator rows. The shipping
   stage MD performs an explicit join: load `02-code-inventory.json`, index
   by `items[].id`, look up by `row.code_ref`, walk parents for hotspot
   inheritance. The join is ephemeral (results are not persisted onto rows),
   keeping `schemas/comparison.json` minimal.

---

## Phase 0 — File 3 GitHub issues against `prpande/skills`

These three issues let future agent sessions pick up waves 2 and 3 in parallel. Wave 1 issue is filed first because we'll work on it in this session and want a tracking link.

### Task 0.1: Create `design-coverage`, `wave-1`, `wave-2`, `wave-3`, `in-progress` labels

**Files:** None (GitHub state).

- [ ] **Step 1: Check which labels already exist**

```bash
gh label list -R prpande/skills --limit 30
```

Expected: lists default labels (`bug`, `enhancement`, etc.). Note any of `design-coverage`, `wave-1`, `wave-2`, `wave-3`, `in-progress` that already exist.

- [ ] **Step 2: Create missing labels (skip ones that exist)**

```bash
gh label create design-coverage --description "design-coverage skill" --color "5319e7" -R prpande/skills
gh label create wave-1 --description "Wave 1: methodology drift killer" --color "0e8a16" -R prpande/skills
gh label create wave-2 --description "Wave 2: repo-local hints + scout updates + infra" --color "fbca04" -R prpande/skills
gh label create wave-3 --description "Wave 3: robustness & UX polish" --color "f9d0c4" -R prpande/skills
gh label create in-progress --description "Currently being worked on" --color "1d76db" -R prpande/skills
```

Expected: each command prints `https://github.com/prpande/skills/labels/<name>` or "label already exists" (which is fine).

### Task 0.2: Build the wave 1 issue body file

**Files:**
- Create: `/tmp/wave-1-issue-body.md` (intermediate, not committed)

- [ ] **Step 1: Write the issue body**

Read the spec's wave 1 section (lines 102-235 of the spec doc) and the cross-cutting design section (lines 31-110), and assemble into this issue body file. Use Read to fetch the actual lines, then Write the assembled body. The body must include verbatim copies of:
- Wave 1 problem statement
- Wave 1 design (all four items: #1, #2, #3, #6 + the sealed-enum-index helper)
- Files in scope (list below)
- Definition of Done (one per item, copied from spec)
- Inter-wave dependencies (wave 1 hard-codes default_in_scope_hops=2; wave 2 will make it configurable)
- Hand-off context

Files in scope for wave 1:
```
skills/design-tooling/design-coverage/lib/skill_root.py            (new)
skills/design-tooling/design-coverage/lib/sealed_enum_index.py     (new)
skills/design-tooling/design-coverage/lib/severity_matrix.py       (new)
skills/design-tooling/design-coverage/lib/hotspot_questions.py     (new)
skills/design-tooling/design-coverage/schemas/code_inventory.json  (modified)
skills/design-tooling/design-coverage/schemas/inventory_item.json  (modified)
skills/design-tooling/design-coverage/schemas/clarifications.json  (modified)
skills/design-tooling/design-coverage/SKILL.md                     (modified)
skills/design-tooling/design-coverage/stages/01-flow-locator.md    (modified — path sweep)
skills/design-tooling/design-coverage/stages/02-code-inventory.md  (modified — path sweep + closed enum)
skills/design-tooling/design-coverage/stages/03-clarification.md   (modified — path sweep + emit_questions + candidate_destinations)
skills/design-tooling/design-coverage/stages/04-figma-inventory.md (modified — path sweep)
skills/design-tooling/design-coverage/stages/05-comparator.md      (modified — path sweep + severity_matrix.lookup)
skills/design-tooling/design-coverage/stages/06-report-generator.md (modified — path sweep)
skill-tests/design-coverage/tests/test_skill_root.py               (new)
skill-tests/design-coverage/tests/test_sealed_enum_index.py        (new)
skill-tests/design-coverage/tests/test_severity_matrix.py          (new)
skill-tests/design-coverage/tests/test_hotspot_questions.py        (new)
skill-tests/design-coverage/tests/test_code_inventory_closed_enum.py (new)
```

- [ ] **Step 2: Verify the file was written and has substantive content**

Run: `wc -l /tmp/wave-1-issue-body.md`
Expected: at least 200 lines.

### Task 0.3: File the wave 1 issue

**Files:** None (GitHub state).

- [ ] **Step 1: Open the issue**

```bash
gh issue create -R prpande/skills \
  --title "[design-coverage] Wave 1 — Methodology-drift killer (#1, #2, #3, #6)" \
  --label "enhancement,design-coverage,wave-1,in-progress" \
  --body-file /tmp/wave-1-issue-body.md
```

Expected: prints the issue URL. Save the issue number for cross-referencing in subsequent issues.

- [ ] **Step 2: Capture the issue URL into a variable for later use**

Run: `gh issue list -R prpande/skills --label wave-1 --json number,title,url --limit 1`
Expected: JSON with one entry. Note the `number` field (e.g., `11`).

### Task 0.4: Build the wave 2 issue body file

**Files:**
- Create: `/tmp/wave-2-issue-body.md` (intermediate, not committed)

- [ ] **Step 1: Write the issue body**

Read spec lines 240-440 (cross-cutting design + wave 2) and assemble into the issue body. Body MUST include:
- Wave 2 problem statement (no shipped per-platform hints; scout owns platform knowledge; schema validation gate; scratch policy)
- Wave 2 design (sub-items #7, #10a/b/c, #11)
- Files in scope:
  ```
  skills/design-tooling/design-coverage/platforms/ios.md            (DELETE — git-mv to docs/)
  skills/design-tooling/design-coverage/platforms/android.md        (DELETE — git-mv to docs/)
  docs/design-coverage/historical-platform-notes/mindbodypos-ios.md (NEW — moved from platforms/ios.md)
  docs/design-coverage/historical-platform-notes/express-android.md (NEW — moved from platforms/android.md)
  skills/design-tooling/design-coverage-scout/stages/02-pattern-extraction.md (modified — Platform sections sub-doc)
  skills/design-tooling/design-coverage/SKILL.md                    (modified — unknown-stack rewrite, --platform agnostic removed)
  skills/design-tooling/design-coverage/lib/skill_io.py             (modified — validate_and_write_json wrapper)
  skills/design-tooling/design-coverage/schemas/*.json              (annotation: x-platform-pattern + new closed-enum keys for hint frontmatter)
  ```
- Definition of Done (copied from spec)
- Inter-wave dependencies: requires wave 1's `lib/sealed_enum_index.py` and `lib/skill_root.py` to be merged or available on the working branch. No conflict with wave 3.
- Hand-off context

- [ ] **Step 2: Verify**

Run: `wc -l /tmp/wave-2-issue-body.md`
Expected: at least 200 lines.

### Task 0.5: File the wave 2 issue

**Files:** None (GitHub state).

- [ ] **Step 1: Open the issue, referencing wave 1 in the body**

In the body, include a line: `**Depends on:** #<wave-1-issue-number> (wave 1 ships lib/skill_root.py and lib/sealed_enum_index.py).`

```bash
gh issue create -R prpande/skills \
  --title "[design-coverage] Wave 2 — Repo-local hints generated by scout, sealed-enum frontmatter, schema validation, scratch policy (#7, #10, #11)" \
  --label "enhancement,design-coverage,wave-2" \
  --body-file /tmp/wave-2-issue-body.md
```

Expected: prints the issue URL.

### Task 0.6: Build the wave 3 issue body file

**Files:**
- Create: `/tmp/wave-3-issue-body.md` (intermediate, not committed)

- [ ] **Step 1: Write the issue body**

Read spec lines 442-475 (wave 3) and assemble into the issue body. Include:
- Wave 3 problem statement (multi-anchor disambiguation, frame-granularity, action-verb template, low-confidence verdict)
- Wave 3 design (#4, #5, #12, #13)
- Files in scope:
  ```
  skills/design-tooling/design-coverage/stages/01-flow-locator.md   (modified — multi-anchor refuse-loud)
  skills/design-tooling/design-coverage/stages/03-clarification.md  (modified — figma_dedup_policy Q)
  skills/design-tooling/design-coverage/stages/04-figma-inventory.md (modified — leaf-frame level + screen-group)
  skills/design-tooling/design-coverage/schemas/inventory_item.json (modified — kind enum gains screen-group)
  skills/design-tooling/design-coverage/schemas/frame_classification.json (NEW)
  skills/design-tooling/design-coverage/SKILL.md                    (modified — final-output template + low-confidence prepend)
  skills/design-tooling/design-coverage/lib/action_verbs.py         (NEW)
  ```
- Definition of Done (copied from spec)
- Inter-wave dependencies: requires wave 2's `multi_anchor_suffixes` frontmatter field and the platform-hint validator. Suggest waiting for wave 2 to merge OR working against the wave-2 branch.
- Hand-off context

- [ ] **Step 2: Verify**

Run: `wc -l /tmp/wave-3-issue-body.md`
Expected: at least 150 lines.

### Task 0.7: File the wave 3 issue

**Files:** None (GitHub state).

- [ ] **Step 1: Open the issue, referencing waves 1 and 2 in the body**

In the body, include: `**Depends on:** #<wave-1-issue-number> and #<wave-2-issue-number>. Best executed after wave 2 merges.`

```bash
gh issue create -R prpande/skills \
  --title "[design-coverage] Wave 3 — Multi-anchor disambiguation, frame-granularity, action-verb template, low-confidence verdict (#4, #5, #12, #13)" \
  --label "enhancement,design-coverage,wave-3" \
  --body-file /tmp/wave-3-issue-body.md
```

Expected: prints the issue URL.

- [ ] **Step 2: List all three issues to confirm**

```bash
gh issue list -R prpande/skills --label design-coverage --json number,title,labels --limit 5
```

Expected: three issues with labels `design-coverage` + `wave-1|wave-2|wave-3`.

---

## Phase 1 — `lib/skill_root.py` (foundation for all skill-relative imports)

Everything else in wave 1 depends on this module being present, because the new `lib/*.py` files use it to locate `schemas/`. Build it first.

### Task 1.1: Write the failing test for `get_skill_root`

**Files:**
- Create: `skill-tests/design-coverage/tests/test_skill_root.py`

- [ ] **Step 1: Write the test file**

```python
# skill-tests/design-coverage/tests/test_skill_root.py
"""Verify skill_root.get_skill_root() finds SKILL.md by walking up from __file__.

This module is the foundation for skill-relative path resolution; everything
else in lib/ that needs to load schemas/ depends on it. The test covers both
the real skill location AND a synthetic tmp-path layout to ensure portability.
"""
from pathlib import Path
import pytest


def test_real_skill_root_contains_skill_md():
    """When called from the real lib/, the resolved root contains SKILL.md."""
    from skill_root import get_skill_root
    root = get_skill_root()
    assert (root / "SKILL.md").exists(), f"SKILL.md not found in {root}"


def test_real_skill_root_contains_schemas_dir():
    """The resolved root has the sibling schemas/ directory we'll need."""
    from skill_root import get_skill_root
    root = get_skill_root()
    assert (root / "schemas").is_dir()


def test_get_skill_root_raises_when_skill_md_absent(tmp_path, monkeypatch):
    """If invoked from a directory tree with no SKILL.md ancestor, raise loudly."""
    import sys
    import importlib

    # Build a synthetic lib/ in tmp_path with NO SKILL.md anywhere above it.
    fake_lib = tmp_path / "fake" / "lib"
    fake_lib.mkdir(parents=True)
    fake_module = fake_lib / "skill_root_clone.py"
    # Copy the real module into the synthetic location so __file__ resolves there.
    import skill_root as real_module
    fake_module.write_text(Path(real_module.__file__).read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.syspath_prepend(str(fake_lib))
    if "skill_root_clone" in sys.modules:
        del sys.modules["skill_root_clone"]
    clone = importlib.import_module("skill_root_clone")

    with pytest.raises(RuntimeError, match="SKILL.md"):
        clone.get_skill_root()
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_skill_root.py -v
```

Expected: 3 tests fail with `ModuleNotFoundError: No module named 'skill_root'`.

### Task 1.2: Implement `lib/skill_root.py`

**Files:**
- Create: `skills/design-tooling/design-coverage/lib/skill_root.py`

- [ ] **Step 1: Write the module**

```python
# skills/design-tooling/design-coverage/lib/skill_root.py
"""Resolve the skill root (the directory containing SKILL.md) from this file's location.

Replaces hard-coded ~/.claude/skills/design-coverage/ paths in stage MDs and lib/.
Every Python snippet that needs to load schemas/, platforms/, or sibling lib/
modules should call get_skill_root() rather than constructing a path from $HOME.

Walks up at most 5 parent directories. SKILL.md must exist within that range or
RuntimeError is raised — silent fallback to a wrong root is worse than a halt.
"""
from __future__ import annotations

from pathlib import Path

_MAX_DEPTH = 5


def get_skill_root() -> Path:
    """Return the directory containing SKILL.md, walking up from this file.

    Raises RuntimeError if SKILL.md is not found within _MAX_DEPTH parents.
    """
    here = Path(__file__).resolve().parent
    for _ in range(_MAX_DEPTH):
        if (here / "SKILL.md").exists():
            return here
        here = here.parent
    raise RuntimeError(
        f"Could not locate skill root: SKILL.md not found within "
        f"{_MAX_DEPTH} parent directories of {Path(__file__).resolve()}"
    )
```

- [ ] **Step 2: Run the test to confirm it passes**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_skill_root.py -v
```

Expected: 3 tests pass.

- [ ] **Step 3: Commit**

```bash
cd /c/src/skills-design-coverage-improvements
git add skills/design-tooling/design-coverage/lib/skill_root.py \
        skill-tests/design-coverage/tests/test_skill_root.py
git commit -m "$(cat <<'EOF'
feat(design-coverage): add skill_root helper for portable path resolution

Walks up from __file__ to find SKILL.md. Foundation for replacing every
hard-coded ~/.claude/skills/design-coverage/ string in stage MDs and lib/
modules with a portable, environment-independent root path. Raises loudly
if SKILL.md isn't found within 5 parents — silent fallback to a wrong
root would degrade analysis quality without warning.

Wave 1 of the design-coverage improvements spec (#6).
EOF
)"
```

---

## Phase 2 — Schema changes for #3 + `x-platform-pattern` annotations

Modify three schemas in one phase: `inventory_item.json` gains annotations, `code_inventory.json` gets the closed-enum reason + new `candidate_destinations` array, `clarifications.json` gets `in_scope_destinations`. Wave 1 doesn't add `kind: "screen-group"` (that's wave 3 #5).

### Task 2.1: Write failing schema-shape tests

**Files:**
- Create: `skill-tests/design-coverage/tests/test_code_inventory_closed_enum.py`

- [ ] **Step 1: Write the test file**

```python
# skill-tests/design-coverage/tests/test_code_inventory_closed_enum.py
"""Wave 1 #3 — verify the closed enum on unwalked_destinations.reason and the
new candidate_destinations array land in code_inventory.json.

The old free-form reason string allowed agents to write 'out-of-scope-destination'
silently. The closed enum forces mechanical reasons only; agents that judge
something as 'maybe in scope' must emit it to candidate_destinations instead,
where stage 03 will surface it to the user.
"""
import json
from pathlib import Path

import pytest
from validator import Validator, ValidationError

SCHEMAS = Path(__file__).resolve().parents[3] / "skills" / "design-tooling" / "design-coverage" / "schemas"


def _load(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_unwalked_destinations_reason_is_closed_enum():
    schema = _load("code_inventory.json")
    reason_schema = schema["properties"]["unwalked_destinations"]["items"]["properties"]["reason"]
    assert "enum" in reason_schema
    assert set(reason_schema["enum"]) == {
        "adapter-hosted",
        "external-module",
        "swiftui-bridge",
        "dynamic-identifier",
        "platform-bridge",
    }


def test_unwalked_destinations_rejects_legacy_free_form_reason():
    schema = _load("code_inventory.json")
    v = Validator(SCHEMAS)
    bad = {
        "items": [],
        "unwalked_destinations": [
            {"nav_source": "X", "target": "Y", "reason": "out-of-scope-destination"}
        ],
        "candidate_destinations": [],
    }
    with pytest.raises(ValidationError):
        v.validate(bad, schema)


def test_candidate_destinations_field_exists_and_is_array():
    schema = _load("code_inventory.json")
    assert "candidate_destinations" in schema["properties"]
    cd = schema["properties"]["candidate_destinations"]
    assert cd["type"] == "array"
    item_props = cd["items"]["properties"]
    for required_key in ("symbol", "file", "hop_distance", "why_not_walked"):
        assert required_key in item_props


def test_candidate_destination_item_validates():
    schema = _load("code_inventory.json")
    v = Validator(SCHEMAS)
    good = {
        "items": [],
        "unwalked_destinations": [],
        "candidate_destinations": [
            {
                "symbol": "MBOApptQuickBookViewController",
                "file": "MindBodyPOS/Legacy/.../QuickBook.m",
                "hop_distance": 1,
                "why_not_walked": "Modify-appointment flow; agent unsure if in scope for appointment-details audit.",
            }
        ],
    }
    v.validate(good, schema)  # must not raise


def test_clarifications_has_in_scope_destinations_field():
    schema = _load("clarifications.json")
    assert "in_scope_destinations" in schema["properties"]
    isd = schema["properties"]["in_scope_destinations"]
    assert isd["type"] == "array"


def test_inventory_item_kind_carries_x_platform_pattern():
    schema = _load("inventory_item.json")
    kind = schema["properties"]["kind"]
    assert kind.get("x-platform-pattern") is True


def test_inventory_item_surface_carries_x_platform_pattern():
    schema = _load("inventory_item.json")
    surface = schema["properties"]["source"]["properties"]["surface"]
    assert surface.get("x-platform-pattern") is True


def test_inventory_item_hotspot_type_carries_x_platform_pattern():
    schema = _load("inventory_item.json")
    htype = schema["properties"]["hotspot"]["properties"]["type"]
    assert htype.get("x-platform-pattern") is True


def test_unwalked_reason_carries_x_platform_pattern():
    schema = _load("code_inventory.json")
    reason = schema["properties"]["unwalked_destinations"]["items"]["properties"]["reason"]
    assert reason.get("x-platform-pattern") is True
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_code_inventory_closed_enum.py -v
```

Expected: all 9 tests fail (schema fields don't exist yet, enum is open).

### Task 2.2: Update `schemas/inventory_item.json` with `x-platform-pattern` annotations

**Files:**
- Modify: `skills/design-tooling/design-coverage/schemas/inventory_item.json`

- [ ] **Step 1: Add annotations to the three relevant enum fields**

Replace the file contents with:

```json
{
  "$id": "inventory_item.json",
  "type": "object",
  "required": ["id", "kind", "title", "parent_id", "source", "confidence"],
  "properties": {
    "id": {"type": "string", "minLength": 1},
    "kind": {
      "type": "string",
      "x-platform-pattern": true,
      "enum": ["screen", "state", "action", "field"]
    },
    "title": {"type": "string", "minLength": 1},
    "parent_id": {"type": ["string", "null"]},
    "source": {
      "type": "object",
      "required": ["surface", "file"],
      "properties": {
        "surface": {
          "type": "string",
          "x-platform-pattern": true,
          "enum": ["compose", "xml", "hybrid", "nav-xml", "nav-compose"]
        },
        "file": {"type": "string", "minLength": 1},
        "line": {"type": ["integer", "null"], "minimum": 0},
        "symbol": {"type": ["string", "null"]}
      }
    },
    "hotspot": {
      "type": ["object", "null"],
      "required": ["type", "question"],
      "properties": {
        "type": {
          "type": "string",
          "x-platform-pattern": true,
          "enum": ["feature-flag", "permission", "server-driven", "config-qualifier", "form-factor", "process-death", "view-type", "viewpager-tab", "sheet-dialog"]
        },
        "question": {"type": "string", "minLength": 1}
      }
    },
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "notes": {"type": ["string", "null"]},
    "ambiguous": {"type": "boolean"},
    "ambiguity_reason": {"type": ["string", "null"]},
    "modes": {
      "type": "array",
      "items": {"type": "string", "minLength": 1}
    }
  }
}
```

Note: `kind` enum is unchanged (no `screen-group` yet — that's wave 3). Only the annotation is added.

### Task 2.3: Update `schemas/code_inventory.json` with closed enum + `candidate_destinations`

**Files:**
- Modify: `skills/design-tooling/design-coverage/schemas/code_inventory.json`

- [ ] **Step 1: Replace the file contents**

```json
{
  "$id": "code_inventory.json",
  "type": "object",
  "required": ["items", "unwalked_destinations"],
  "properties": {
    "items": {"type": "array", "items": {"$ref": "inventory_item.json"}},
    "unwalked_destinations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["nav_source", "target", "reason"],
        "properties": {
          "nav_source": {"type": "string", "minLength": 1},
          "target": {"type": "string", "minLength": 1},
          "reason": {
            "type": "string",
            "x-platform-pattern": true,
            "enum": [
              "adapter-hosted",
              "external-module",
              "swiftui-bridge",
              "dynamic-identifier",
              "platform-bridge"
            ]
          }
        }
      }
    },
    "candidate_destinations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["symbol", "file", "hop_distance", "why_not_walked"],
        "properties": {
          "symbol": {"type": "string", "minLength": 1},
          "file": {"type": "string", "minLength": 1},
          "hop_distance": {"type": "integer", "minimum": 1},
          "why_not_walked": {"type": "string", "minLength": 1}
        }
      }
    }
  }
}
```

Note: `candidate_destinations` is NOT in `required` — existing test fixtures and prior runs that don't carry this array still validate. New runs add it; legacy runs read clean.

### Task 2.4: Update `schemas/clarifications.json` with `in_scope_destinations`

**Files:**
- Modify: `skills/design-tooling/design-coverage/schemas/clarifications.json`

- [ ] **Step 1: Read the current file first to preserve existing fields**

Run: `cat /c/src/skills-design-coverage-improvements/skills/design-tooling/design-coverage/schemas/clarifications.json`

- [ ] **Step 2: Add the `in_scope_destinations` field**

Replace the file with the existing content plus an `in_scope_destinations` array property (not in `required`). The schema after edit should have `properties: {resolved: ..., in_scope_destinations: {...}}`. The exact existing shape is:

```json
{
  "$id": "clarifications.json",
  "type": "object",
  "required": ["resolved"],
  "properties": {
    "resolved": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["hotspot_id", "answer", "resolved_at"],
        "properties": {
          "hotspot_id": {"type": "string", "minLength": 1},
          "answer": {"type": "string", "minLength": 1},
          "resolved_at": {"type": "string", "minLength": 1}
        }
      }
    },
    "in_scope_destinations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["parent_screen", "destinations"],
        "properties": {
          "parent_screen": {"type": "string", "minLength": 1},
          "destinations": {
            "type": "array",
            "items": {"type": "string", "minLength": 1}
          }
        }
      }
    }
  }
}
```

### Task 2.5: Run the test to confirm it now passes

- [ ] **Step 1: Run the closed-enum tests**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_code_inventory_closed_enum.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 2: Run the full test suite to confirm no regressions**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest -v
```

Expected: all existing tests still pass plus the 9 new ones. If `test_schemas_parse.py` fails on the new fields, fix it inline (probably needs to recognize the new `candidate_destinations` and `in_scope_destinations` fields as expected). If `test_fixtures_validate.py` fails, the fixtures may carry old `reason` values that are no longer in the closed enum — fix the fixtures, not the schema.

### Task 2.6: Commit

- [ ] **Step 1: Stage and commit**

```bash
cd /c/src/skills-design-coverage-improvements
git add skills/design-tooling/design-coverage/schemas/inventory_item.json \
        skills/design-tooling/design-coverage/schemas/code_inventory.json \
        skills/design-tooling/design-coverage/schemas/clarifications.json \
        skill-tests/design-coverage/tests/test_code_inventory_closed_enum.py
git commit -m "$(cat <<'EOF'
feat(design-coverage): close unwalked-destination reasons; add candidate_destinations + in_scope_destinations

The previous free-form reason string allowed agents to write
'out-of-scope-destination' as silent product judgment, producing
inconsistent results between runs (one agent's 'out of scope' is
another's 'real workflow gap'). The closed enum forces mechanical
reasons only (adapter-hosted, external-module, swiftui-bridge,
dynamic-identifier, platform-bridge); judgment calls go to the new
candidate_destinations array, which stage 03 surfaces to the user
as a multi-select question (default in-scope).

Schema fields tagged with x-platform-pattern: true become the source
of truth for the schema-derived registry that lib/sealed_enum_index.py
will consume next. Adding a new enum value is a one-place edit.

Wave 1 of the design-coverage improvements spec (#3 + groundwork for #10).
EOF
)"
```

---

## Phase 3 — `lib/sealed_enum_index.py`

Schema-derived registry. Walks `schemas/` for `x-platform-pattern: true` annotations and yields dotted-path keys.

### Task 3.1: Write the failing test

**Files:**
- Create: `skill-tests/design-coverage/tests/test_sealed_enum_index.py`

- [ ] **Step 1: Write the test file**

```python
# skill-tests/design-coverage/tests/test_sealed_enum_index.py
"""Wave 1 — verify get_sealed_enum_pattern_keys() derives the registry from
schemas/, NOT from a hand-coded list. The schemas are the existing source of
truth for what enums exist; a hand-maintained registry would drift on every
schema change.
"""
import json
from pathlib import Path

import pytest


def test_returns_a_sorted_list_of_strings():
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = get_sealed_enum_pattern_keys()
    assert isinstance(keys, list)
    assert keys == sorted(keys)
    assert all(isinstance(k, str) for k in keys)
    assert len(keys) >= 9  # hotspot.type alone has 9 values


def test_includes_every_hotspot_type_value():
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = set(get_sealed_enum_pattern_keys())
    expected = {
        "hotspot.type.feature-flag",
        "hotspot.type.permission",
        "hotspot.type.server-driven",
        "hotspot.type.config-qualifier",
        "hotspot.type.form-factor",
        "hotspot.type.process-death",
        "hotspot.type.view-type",
        "hotspot.type.viewpager-tab",
        "hotspot.type.sheet-dialog",
    }
    missing = expected - keys
    assert not missing, f"missing hotspot.type keys: {sorted(missing)}"


def test_includes_inventory_item_kind_values():
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = set(get_sealed_enum_pattern_keys())
    expected = {
        "inventory_item.kind.screen",
        "inventory_item.kind.state",
        "inventory_item.kind.action",
        "inventory_item.kind.field",
    }
    assert expected <= keys


def test_includes_surface_values():
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = set(get_sealed_enum_pattern_keys())
    expected = {
        "inventory_item.source.surface.compose",
        "inventory_item.source.surface.xml",
        "inventory_item.source.surface.hybrid",
        "inventory_item.source.surface.nav-xml",
        "inventory_item.source.surface.nav-compose",
    }
    assert expected <= keys


def test_includes_unwalked_reason_values():
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = set(get_sealed_enum_pattern_keys())
    expected = {
        "unwalked_destinations.reason.adapter-hosted",
        "unwalked_destinations.reason.external-module",
        "unwalked_destinations.reason.swiftui-bridge",
        "unwalked_destinations.reason.dynamic-identifier",
        "unwalked_destinations.reason.platform-bridge",
    }
    assert expected <= keys


def test_excludes_universal_enums():
    """Severity, status, confidence, etc. are universal — they must NOT carry
    x-platform-pattern, and therefore must NOT appear in the registry."""
    from sealed_enum_index import get_sealed_enum_pattern_keys
    keys = " ".join(get_sealed_enum_pattern_keys())
    for forbidden in ("severity", "status", "screenshot_cross_check", "confidence", "locator_method"):
        assert forbidden not in keys, f"{forbidden} should not appear in the registry"


def test_dynamically_picks_up_new_x_platform_pattern_value(tmp_path, monkeypatch):
    """Adding a new x-platform-pattern: true enum value to a schema makes the
    registry surface it without any code change in sealed_enum_index.py."""
    # Build a fake skill root with one schema containing a new annotated enum.
    fake_skill_root = tmp_path / "fake-skill"
    (fake_skill_root / "schemas").mkdir(parents=True)
    (fake_skill_root / "SKILL.md").write_text("---\nname: fake\n---\n")
    schema = {
        "$id": "fake.json",
        "type": "object",
        "properties": {
            "novel_enum": {
                "type": "string",
                "x-platform-pattern": True,
                "enum": ["alpha", "beta"]
            }
        }
    }
    (fake_skill_root / "schemas" / "fake.json").write_text(json.dumps(schema))

    # Patch get_skill_root to return the fake.
    import skill_root as real_skill_root_mod
    monkeypatch.setattr(real_skill_root_mod, "get_skill_root", lambda: fake_skill_root)
    # Re-import sealed_enum_index so its get_skill_root binding picks up the patch.
    import importlib
    import sealed_enum_index
    importlib.reload(sealed_enum_index)

    keys = sealed_enum_index.get_sealed_enum_pattern_keys()
    assert "fake.novel_enum.alpha" in keys
    assert "fake.novel_enum.beta" in keys
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_sealed_enum_index.py -v
```

Expected: 7 tests fail with `ModuleNotFoundError: No module named 'sealed_enum_index'`.

### Task 3.2: Implement `lib/sealed_enum_index.py`

**Files:**
- Create: `skills/design-tooling/design-coverage/lib/sealed_enum_index.py`

- [ ] **Step 1: Write the module**

```python
# skills/design-tooling/design-coverage/lib/sealed_enum_index.py
"""Schema-derived registry of platform-pattern enum keys.

Walks schemas/*.json and yields <dotted_path>.<value> for every enum field
annotated with x-platform-pattern: true. The schemas are the source of truth
for what enums exist; this module derives the registry mechanically so adding
a new enum value is a one-place edit (the schema), no registry sync required.

Used by:
- The platform-hint frontmatter validator (wave 2 #10) to allow-list
  sealed_enum_patterns keys.
- Stage 02 (wave 2) to iterate enum values when discovering items.
- design-coverage-scout (wave 2 #10c) to know which enum values it must
  detect platform patterns for.

The schema name is derived from the file stem (e.g., schemas/inventory_item.json
contributes keys prefixed with "inventory_item."). Nested fields use dotted
notation (e.g., "inventory_item.source.surface.compose"). $ref nodes are NOT
followed — annotations on referenced types belong to the referenced schema.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from skill_root import get_skill_root


def get_sealed_enum_pattern_keys() -> list[str]:
    """Return sorted list of <dotted_path>.<value> keys derived from schemas/.

    A key is emitted for every enum value of every field annotated with
    `"x-platform-pattern": true`. Paths are rooted at the schema's file stem.
    """
    keys: list[str] = []
    schemas_dir = get_skill_root() / "schemas"
    for schema_file in sorted(schemas_dir.glob("*.json")):
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        root_name = schema_file.stem
        for path, field in _walk_schema(schema, root_name):
            if field.get("x-platform-pattern") and "enum" in field:
                for value in field["enum"]:
                    keys.append(f"{path}.{value}")
    return sorted(keys)


def _walk_schema(node: dict, path: str) -> Iterator[tuple[str, dict]]:
    """Yield (dotted_path, field_subtree) for every property in the schema.

    Recurses into `properties` and `items.properties`. Does NOT follow `$ref` —
    referenced schemas are walked separately when iterating the schemas/ dir.
    """
    if not isinstance(node, dict):
        return
    yield path, node
    for child_name, child in (node.get("properties") or {}).items():
        yield from _walk_schema(child, f"{path}.{child_name}")
    items = node.get("items")
    if isinstance(items, dict):
        # Array items don't add a path segment; their properties are addressed
        # as if direct children of the array's containing field.
        for child_name, child in (items.get("properties") or {}).items():
            yield from _walk_schema(child, f"{path}.{child_name}")
```

- [ ] **Step 2: Run the test to confirm it passes**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_sealed_enum_index.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 3: Commit**

```bash
cd /c/src/skills-design-coverage-improvements
git add skills/design-tooling/design-coverage/lib/sealed_enum_index.py \
        skill-tests/design-coverage/tests/test_sealed_enum_index.py
git commit -m "$(cat <<'EOF'
feat(design-coverage): add schema-derived sealed-enum pattern registry

Walks schemas/*.json and yields <dotted_path>.<value> for every enum
field annotated with x-platform-pattern: true. Schemas are the source
of truth for what platform-pattern enum values exist; the registry is
mechanically derived rather than hand-maintained, eliminating the
silent-drift failure mode that a duplicate hand-coded list would have.

Adding a new enum value is now a one-place edit: edit the schema, the
registry picks it up on next call. The validator (wave 2), stage 02
(wave 2), and the design-coverage-scout (wave 2 #10c) all consume
this registry without seeing a hardcoded list.

Wave 1 of the design-coverage improvements spec (foundational helper
referenced by wave 2 #10 and #3's frontmatter validation gate).
EOF
)"
```

---

## Phase 4 — `lib/severity_matrix.py` (#2)

### Task 4.1: Write the failing test

**Files:**
- Create: `skill-tests/design-coverage/tests/test_severity_matrix.py`

- [ ] **Step 1: Write the test file**

```python
# skill-tests/design-coverage/tests/test_severity_matrix.py
"""Wave 1 #2 — replace stage 05's prose severity rules with a deterministic
table lookup. Two agents on the same comparator inputs must produce identical
severity calls.
"""
from pathlib import Path

import pytest


def test_lookup_known_tuple_returns_expected_severity():
    from severity_matrix import lookup
    # Missing screen with no hotspot is always error.
    assert lookup("missing", "screen", None, None) == "error"


def test_lookup_present_returns_info():
    from severity_matrix import lookup
    assert lookup("present", "screen", None, None) == "info"
    assert lookup("present", "action", None, None) == "info"


def test_lookup_new_in_figma_returns_info():
    from severity_matrix import lookup
    assert lookup("new-in-figma", None, None, None) == "info"


def test_lookup_restructured_returns_warn():
    from severity_matrix import lookup
    assert lookup("restructured", "screen", None, None) == "warn"


def test_lookup_view_type_violation_is_error():
    from severity_matrix import lookup
    # When clarification says all variants required and one is missing, that's an error.
    assert lookup("missing", "action", "view-type", "all_variants_required") == "error"


def test_lookup_permission_granted_missing_is_info():
    from severity_matrix import lookup
    # If user said permission is granted (default happy path), code-side
    # permission-denied paths missing from Figma drop to info.
    assert lookup("missing", "action", "permission", "granted") == "info"


def test_lookup_unknown_tuple_returns_warn_fallback(tmp_path):
    from severity_matrix import lookup
    sev = lookup("missing", "novel-kind-not-in-matrix", None, None)
    assert sev == "warn"


def test_lookup_unknown_tuple_records_miss(tmp_path, monkeypatch):
    """Misses are recorded so the matrix can be audited and grown over time."""
    import severity_matrix as sm
    misses_path = tmp_path / "_severity_lookup_misses.json"
    monkeypatch.setattr(sm, "_MISSES_PATH", misses_path)
    sm._MISS_BUFFER.clear()  # ensure clean state
    sm.lookup("missing", "novel-kind", None, None)
    sm.flush_misses(misses_path)
    import json
    data = json.loads(misses_path.read_text())
    assert any("novel-kind" in str(entry) for entry in data)


def test_lookup_returns_only_canonical_severity_strings():
    """All emitted severities must be one of {info, warn, error}."""
    from severity_matrix import lookup, SEVERITY_MATRIX
    for sev in SEVERITY_MATRIX.values():
        assert sev in {"info", "warn", "error"}, f"matrix has invalid severity: {sev}"
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_severity_matrix.py -v
```

Expected: 9 tests fail with `ModuleNotFoundError: No module named 'severity_matrix'`.

### Task 4.2: Implement `lib/severity_matrix.py`

**Files:**
- Create: `skills/design-tooling/design-coverage/lib/severity_matrix.py`

- [ ] **Step 1: Write the module**

```python
# skills/design-tooling/design-coverage/lib/severity_matrix.py
"""Deterministic severity lookup for stage 05's comparator.

Today (pre-wave-1) stage 05 has prose rules ("error if user-noticeable
workflow loss") that two agents read and apply differently — producing
divergent severity calls on the same data. This module replaces the prose
with a table lookup so the comparator's job is purely mechanical.

The matrix is indexed by (status, kind, hotspot_type, clarification_answer).
None matches "any value" for that field. Lookups walk from most-specific to
most-general; the first matching tuple wins.

Unknown tuples fall back to "warn" AND get recorded to a miss buffer the
caller can flush to <run_dir>/_severity_lookup_misses.json. Misses are
the audit signal for "the matrix needs another entry."
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# (status, kind, hotspot_type, clarification_answer) -> severity
# `None` in any slot matches any value for that slot.
SEVERITY_MATRIX: dict[tuple[Optional[str], Optional[str], Optional[str], Optional[str]], str] = {
    # ----- present rows are always info -----
    ("present", None, None, None): "info",

    # ----- new-in-figma rows are always info (per wave 1 #3 spec) -----
    ("new-in-figma", None, None, None): "info",

    # ----- restructured rows default to warn (no info loss assumed) -----
    ("restructured", None, None, None): "warn",

    # ----- missing screens are always error (entire surface gone) -----
    ("missing", "screen", None, None): "error",

    # ----- missing actions/states/fields depend on hotspot + clarification -----
    # View-type variants where the user said all are required: error.
    ("missing", "action", "view-type", "all_variants_required"): "error",
    ("missing", "state", "view-type", "all_variants_required"): "error",
    ("missing", "field", "view-type", "all_variants_required"): "error",

    # Server-driven sections where user said both states required: error.
    ("missing", "state", "server-driven", "both_states_required"): "error",

    # Feature-flag branches the user said are in scope: error if missing.
    ("missing", "state", "feature-flag", "on"): "error",
    ("missing", "action", "feature-flag", "on"): "error",

    # Permission-granted happy path: missing denied-variants drop to info.
    ("missing", "state", "permission", "granted"): "info",
    ("missing", "action", "permission", "granted"): "info",
    ("missing", "field", "permission", "granted"): "info",

    # Generic missing actions/states/fields without specific clarification: warn.
    ("missing", "action", None, None): "warn",
    ("missing", "state", None, None): "warn",
    ("missing", "field", None, None): "warn",
}

# Miss tracking — buffered in memory; caller flushes to disk at end of stage.
_MISS_BUFFER: list[tuple] = []
_MISSES_PATH = Path("_severity_lookup_misses.json")  # caller overrides via flush_misses(path)


def lookup(
    status: str,
    kind: Optional[str],
    hotspot_type: Optional[str],
    clarification_answer: Optional[str],
) -> str:
    """Return the severity for a comparator row's (status, kind, hotspot_type, clarification) tuple.

    Walks from most-specific to most-general:
      1. Exact (status, kind, hotspot, clarification) match.
      2. (status, kind, hotspot, None).
      3. (status, kind, None, None).
      4. (status, None, None, None).
    First match wins. If nothing matches, falls back to "warn" and records
    the miss for later audit.
    """
    for key in (
        (status, kind, hotspot_type, clarification_answer),
        (status, kind, hotspot_type, None),
        (status, kind, None, None),
        (status, None, None, None),
    ):
        if key in SEVERITY_MATRIX:
            return SEVERITY_MATRIX[key]
    _MISS_BUFFER.append((status, kind, hotspot_type, clarification_answer))
    return "warn"


def flush_misses(path: Optional[Path] = None) -> None:
    """Write the in-memory miss buffer to JSON. Caller invokes at end of stage 05.

    The miss file lives at the run-dir top level (alongside numbered artifacts);
    its name `_severity_lookup_misses.json` is the ONE allowed underscore-prefixed
    file at the top level (per wave 2 #11's scratch-file policy, which exempts
    this audit file).
    """
    target = Path(path) if path is not None else _MISSES_PATH
    if not _MISS_BUFFER:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = []
    payload = existing + [
        {
            "status": s,
            "kind": k,
            "hotspot_type": h,
            "clarification_answer": c,
        }
        for (s, k, h, c) in _MISS_BUFFER
    ]
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _MISS_BUFFER.clear()
```

- [ ] **Step 2: Run the test to confirm it passes**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_severity_matrix.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 3: Commit**

```bash
cd /c/src/skills-design-coverage-improvements
git add skills/design-tooling/design-coverage/lib/severity_matrix.py \
        skill-tests/design-coverage/tests/test_severity_matrix.py
git commit -m "$(cat <<'EOF'
feat(design-coverage): add deterministic severity matrix for stage 05

Replaces stage 05's prose severity rules ('error if user-noticeable
workflow loss') with a (status, kind, hotspot_type, clarification_answer)
table lookup. Two agents reading the same comparator inputs now produce
identical severity calls — the source of run-to-run severity drift is
collapsed into a single point of calibration debate (the matrix).

Unknown tuples fall back to 'warn' and record the miss to a buffered
audit log; the comparator flushes misses to _severity_lookup_misses.json
at end-of-stage so the matrix can be grown over time based on real data
rather than speculation.

Wave 1 of the design-coverage improvements spec (#2).
EOF
)"
```

---

## Phase 5 — `lib/hotspot_questions.py` (#1)

### Task 5.1: Write the failing test

**Files:**
- Create: `skill-tests/design-coverage/tests/test_hotspot_questions.py`

- [ ] **Step 1: Write the test file**

```python
# skill-tests/design-coverage/tests/test_hotspot_questions.py
"""Wave 1 #1 — verify the hotspot question registry emits deterministic
questions for known inventory shapes. Two agents on the same stage-2 inventory
must produce identical question sets in stage 3.
"""
import pytest


def _inventory_with(hotspots: list[dict]) -> dict:
    """Build a minimal stage-2 inventory dict with the given hotspot annotations."""
    items = []
    for i, h in enumerate(hotspots):
        items.append({
            "id": f"item-{i}",
            "kind": "state",
            "title": f"State {i}",
            "parent_id": None,
            "source": {"surface": "compose", "file": "x.swift"},
            "confidence": "high",
            "hotspot": h,
        })
    return {"items": items, "unwalked_destinations": [], "candidate_destinations": []}


def test_emit_questions_returns_empty_when_no_hotspots():
    from hotspot_questions import emit_questions_for_inventory
    questions = emit_questions_for_inventory(_inventory_with([]), platform_overrides={})
    assert questions == []


def test_emit_questions_one_per_distinct_symbol():
    from hotspot_questions import emit_questions_for_inventory
    inv = _inventory_with([
        {"type": "feature-flag", "question": "isAppointmentDetailsNewDesignEnabled"},
        {"type": "feature-flag", "question": "isAppointmentDetailsNewDesignEnabled"},  # duplicate
        {"type": "feature-flag", "question": "isGroupAppointmentsEnabled"},
    ])
    questions = emit_questions_for_inventory(inv, platform_overrides={})
    symbols = [q.symbol for q in questions]
    assert symbols == ["isAppointmentDetailsNewDesignEnabled", "isGroupAppointmentsEnabled"]


def test_emit_questions_uses_template_for_each_hotspot_type():
    from hotspot_questions import emit_questions_for_inventory
    inv = _inventory_with([
        {"type": "permission", "question": "staff.canEditAppointments"},
        {"type": "view-type", "question": "MBOApptDetailCheckoutCell"},
    ])
    questions = emit_questions_for_inventory(inv, platform_overrides={})
    by_type = {q.hotspot_type: q for q in questions}
    assert "permission" in by_type
    assert "view-type" in by_type
    # Templates substitute the symbol into {symbol}.
    assert "staff.canEditAppointments" in by_type["permission"].rendered_text
    assert "MBOApptDetailCheckoutCell" in by_type["view-type"].rendered_text


def test_emit_questions_respects_applies_when_count_gte():
    """view-type template requires at least 2 distinct symbols of the same type."""
    from hotspot_questions import emit_questions_for_inventory
    # Only one distinct view-type hotspot — should NOT emit a question.
    inv = _inventory_with([
        {"type": "view-type", "question": "MBOApptDetailCheckoutCell"},
    ])
    questions = emit_questions_for_inventory(inv, platform_overrides={})
    assert not any(q.hotspot_type == "view-type" for q in questions)


def test_platform_overrides_replace_template_text():
    from hotspot_questions import emit_questions_for_inventory
    inv = _inventory_with([
        {"type": "permission", "question": "staff.canFoo"},
    ])
    overrides = {"permission": "Custom-template for {symbol}: ok?"}
    questions = emit_questions_for_inventory(inv, platform_overrides=overrides)
    assert questions
    assert "Custom-template for staff.canFoo" in questions[0].rendered_text


def test_question_template_severity_metadata_present():
    from hotspot_questions import HOTSPOT_QUESTIONS
    for hotspot_type, tmpl in HOTSPOT_QUESTIONS.items():
        assert tmpl.severity_if_violated in {"info", "warn", "error"}, \
            f"{hotspot_type} template has invalid severity"
        assert tmpl.default_answer, f"{hotspot_type} template missing default_answer"
        assert "{symbol}" in tmpl.template, f"{hotspot_type} template missing {{symbol}} slot"


def test_registry_covers_every_hotspot_type_value():
    """The registry must have one entry per hotspot.type enum value (verified
    via the schema-derived sealed_enum_index helper)."""
    from hotspot_questions import HOTSPOT_QUESTIONS
    from sealed_enum_index import get_sealed_enum_pattern_keys
    hotspot_types_in_schema = {
        k.split(".")[-1]
        for k in get_sealed_enum_pattern_keys()
        if k.startswith("inventory_item.hotspot.type.") or k.startswith("hotspot.type.")
    }
    missing = hotspot_types_in_schema - set(HOTSPOT_QUESTIONS.keys())
    assert not missing, f"hotspot_questions registry missing entries for: {sorted(missing)}"
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_hotspot_questions.py -v
```

Expected: 7 tests fail with `ModuleNotFoundError`.

### Task 5.2: Implement `lib/hotspot_questions.py`

**Files:**
- Create: `skills/design-tooling/design-coverage/lib/hotspot_questions.py`

- [ ] **Step 1: Write the module**

```python
# skills/design-tooling/design-coverage/lib/hotspot_questions.py
"""Deterministic question registry for stage 03 clarification.

Today (pre-wave-1) stage 03 asks free-form questions invented by the agent.
Two agents on the same stage-2 inventory produce different question sets,
which produces different downstream severity calls. This module replaces
the free-form prose with a registry: one entry per hotspot.type enum value,
each declaring a question template + default answer + severity-if-violated.

Stage 03 calls emit_questions_for_inventory(stage2_inventory, platform_overrides).
The function:
  1. Walks every inventory item with a non-null hotspot.
  2. Groups by (hotspot_type, hotspot.question) so duplicate symbols collapse.
  3. Looks up the template in HOTSPOT_QUESTIONS (or platform_overrides if present).
  4. Skips templates whose applies_when_count_gte threshold isn't met.
  5. Returns one Question per distinct (type, symbol) — the order is
     stable: hotspot_type alphabetical, then symbol alphabetical.

The resulting list feeds AskUserQuestion (or equivalent) one question at a time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class QuestionTemplate:
    """One entry in the registry per hotspot.type enum value."""
    template: str  # Must contain {symbol}; may contain {N} for view-type variant counts.
    default_answer: str
    severity_if_violated: str  # "info" | "warn" | "error"
    applies_when_count_gte: int = 1  # Minimum distinct symbols of this type for the Q to apply.


@dataclass(frozen=True)
class Question:
    """One emitted question to ask the user."""
    hotspot_type: str
    symbol: str
    rendered_text: str
    default_answer: str
    severity_if_violated: str


# Registry — one entry per hotspot.type enum value.
# Sync this set with schemas/inventory_item.json's hotspot.type enum (the
# test_registry_covers_every_hotspot_type_value test gates the sync).
HOTSPOT_QUESTIONS: dict[str, QuestionTemplate] = {
    "feature-flag": QuestionTemplate(
        template="Treat the {symbol} flag as on, off, or both branches for this audit?",
        default_answer="on",
        severity_if_violated="error",
        applies_when_count_gte=1,
    ),
    "permission": QuestionTemplate(
        template="Assume the {symbol} permission is granted unless a Figma frame explicitly shows the denied state?",
        default_answer="granted",
        severity_if_violated="warn",
        applies_when_count_gte=1,
    ),
    "server-driven": QuestionTemplate(
        template="For the {symbol} server-driven section, must Figma cover BOTH the populated and the empty states?",
        default_answer="both_states_required",
        severity_if_violated="error",
        applies_when_count_gte=1,
    ),
    "view-type": QuestionTemplate(
        template="Multiple variants of {symbol} exist in code. Must Figma cover all of them?",
        default_answer="all_variants_required",
        severity_if_violated="error",
        applies_when_count_gte=2,  # Only ask if >=2 distinct symbols of this type.
    ),
    "form-factor": QuestionTemplate(
        template="The {symbol} branch differs by form factor (compact/regular/landscape/etc.). Are all axes in scope?",
        default_answer="all_in_scope",
        severity_if_violated="warn",
        applies_when_count_gte=1,
    ),
    "config-qualifier": QuestionTemplate(
        template="The {symbol} branch depends on a configuration qualifier (e.g., business-setting flag). Assume the default qualifier value, or are all values in scope?",
        default_answer="default_only",
        severity_if_violated="info",
        applies_when_count_gte=1,
    ),
    "process-death": QuestionTemplate(
        template="The {symbol} state-restoration path handles process death. Is this path in scope for the audit?",
        default_answer="out_of_scope",
        severity_if_violated="info",
        applies_when_count_gte=1,
    ),
    "viewpager-tab": QuestionTemplate(
        template="The {symbol} tab/page navigation has multiple destinations. Are all tabs in scope?",
        default_answer="all_in_scope",
        severity_if_violated="warn",
        applies_when_count_gte=1,
    ),
    "sheet-dialog": QuestionTemplate(
        template="The {symbol} sheet/dialog overlay can be presented from multiple states. Must Figma cover the presented variant?",
        default_answer="presented_variant_required",
        severity_if_violated="warn",
        applies_when_count_gte=1,
    ),
}


def emit_questions_for_inventory(inventory: dict, platform_overrides: dict[str, str]) -> list[Question]:
    """Walk the stage-2 inventory and emit one Question per distinct hotspot symbol.

    `inventory` is the parsed code_inventory.json shape. Items with no hotspot
    are skipped. Duplicate (hotspot.type, hotspot.question) pairs collapse to
    one Question. `platform_overrides` is a mapping of hotspot_type -> template
    string; when present, replaces HOTSPOT_QUESTIONS[type].template.
    """
    # Group by (hotspot_type, symbol) to dedupe.
    seen: dict[tuple[str, str], None] = {}
    by_type_count: dict[str, int] = {}
    for item in inventory.get("items", []):
        h = item.get("hotspot")
        if not h:
            continue
        htype = h.get("type")
        symbol = h.get("question")  # The hotspot.question field carries the symbol name.
        if not htype or not symbol:
            continue
        key = (htype, symbol)
        if key not in seen:
            seen[key] = None
            by_type_count[htype] = by_type_count.get(htype, 0) + 1

    questions: list[Question] = []
    for (htype, symbol) in sorted(seen.keys()):
        tmpl = HOTSPOT_QUESTIONS.get(htype)
        if tmpl is None:
            continue  # Hotspot type not in registry — skip silently (test gates this).
        if by_type_count[htype] < tmpl.applies_when_count_gte:
            continue
        template_text = platform_overrides.get(htype, tmpl.template)
        rendered = template_text.format(symbol=symbol, N=by_type_count[htype])
        questions.append(Question(
            hotspot_type=htype,
            symbol=symbol,
            rendered_text=rendered,
            default_answer=tmpl.default_answer,
            severity_if_violated=tmpl.severity_if_violated,
        ))
    return questions
```

- [ ] **Step 2: Run the test to confirm it passes**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_hotspot_questions.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 3: Commit**

```bash
cd /c/src/skills-design-coverage-improvements
git add skills/design-tooling/design-coverage/lib/hotspot_questions.py \
        skill-tests/design-coverage/tests/test_hotspot_questions.py
git commit -m "$(cat <<'EOF'
feat(design-coverage): add deterministic hotspot question registry for stage 03

Stage 03 today asks free-form questions invented by the agent — two agents
on the same stage-2 inventory produce different question sets and the
downstream severity calls diverge. This module replaces the free-form
prose with a registry: one entry per hotspot.type enum value, each with
a question template, default answer, and severity-if-violated.

emit_questions_for_inventory walks the inventory, dedupes by (type, symbol),
applies platform-specific template overrides, and returns a sorted list.
Stage 03 then iterates the list calling AskUserQuestion (or equivalent)
one Q at a time. Same inventory in -> same question list out.

A test gate verifies the registry covers every hotspot.type enum value
(via the schema-derived sealed_enum_index), so adding a new enum value
to schemas/inventory_item.json without a corresponding registry entry
fails CI.

Wave 1 of the design-coverage improvements spec (#1).
EOF
)"
```

---

## Phase 6 — Replace hard-coded `~/.claude` paths in stage MDs (#6 sweep)

The lib/ modules are done. Now sweep the stage MDs and SKILL.md to use `skill_root` instead of hard-coded paths.

### Task 6.1: Inventory all hard-coded paths

**Files:** None (read-only audit).

- [ ] **Step 1: Grep for offending strings**

```bash
cd /c/src/skills-design-coverage-improvements/skills/design-tooling/design-coverage
grep -rn "~/.claude/skills/design-coverage" SKILL.md stages/ lib/
```

Expected: a list of lines across `SKILL.md` and `stages/01-flow-locator.md`, `stages/02-code-inventory.md`, etc. Save the count for reference.

### Task 6.2: Build the canonical replacement Python preamble

**Files:** None (just decide on the snippet).

The replacement preamble that every stage MD's inline Python should use:

```python
import sys
from pathlib import Path

# Skill-relative path resolution: walk up to find SKILL.md.
_HERE = Path(__file__).resolve() if "__file__" in dir() else Path.cwd().resolve()
_SKILL_ROOT = next(
    (p for p in [Path.cwd().resolve(), *Path.cwd().resolve().parents]
     if (p / "SKILL.md").exists()),
    None,
)
if _SKILL_ROOT is None:
    raise RuntimeError("Could not locate skill root: no SKILL.md found above CWD")
sys.path.insert(0, str(_SKILL_ROOT / "lib"))
from skill_root import get_skill_root
SKILL_ROOT = get_skill_root()
```

Alternative simpler form when CWD is reliably the skill root (e.g., when SKILL.md preflight does `cd $SKILL_ROOT`):

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_root import get_skill_root
SKILL_ROOT = get_skill_root()
```

Use the simpler form in stage MDs since the existing preflight already does the cd. But replace the hard-coded `~/.claude` path with `$SKILL_ROOT` resolved at runtime in the preflight bash block.

### Task 6.3: Update SKILL.md preflight + platform resolution

**Files:**
- Modify: `skills/design-tooling/design-coverage/SKILL.md`

- [ ] **Step 1: Read the current SKILL.md preflight + platform resolution sections**

Run: `cd /c/src/skills-design-coverage-improvements && head -200 skills/design-tooling/design-coverage/SKILL.md`

- [ ] **Step 2: Replace the preflight block**

Find:
```bash
cd ~/.claude/skills/design-coverage/
```

Replace with:
```bash
# Resolve the skill root by walking up from this SKILL.md file. Works whether
# the skill is installed at ~/.claude/skills/, in a repo's .claude/skills/, or
# any plugin-managed location.
SKILL_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]:-$0}")")" && pwd)"
cd "$SKILL_ROOT"
```

If `${BASH_SOURCE[0]}` doesn't work in the orchestrator's bash environment (Claude Code's Bash tool), document the fallback: pass `SKILL_ROOT` as an env var derived from the user's `~/.claude/plugins/` lookup OR use the simpler form `cd "$(python -c 'from pathlib import Path; p=Path.cwd(); print(next(q for q in [p, *p.parents] if (q/"SKILL.md").exists()))')"`.

- [ ] **Step 3: Replace every other `~/.claude/skills/design-coverage/` reference in SKILL.md**

Run: `grep -n "~/.claude/skills/design-coverage" /c/src/skills-design-coverage-improvements/skills/design-tooling/design-coverage/SKILL.md`

For each match, replace with `$SKILL_ROOT/` (in bash blocks) or `get_skill_root() / ...` (in Python blocks). Be careful: some references are in `python -c "..."` strings — those need full preamble inline.

- [ ] **Step 4: Verify no hard-coded paths remain in SKILL.md**

```bash
grep -c "~/.claude/skills/design-coverage" /c/src/skills-design-coverage-improvements/skills/design-tooling/design-coverage/SKILL.md
```

Expected: `0`.

### Task 6.4: Update each stage MD (one commit per stage to keep changes reviewable)

**Files:**
- Modify: `skills/design-tooling/design-coverage/stages/01-flow-locator.md`
- Modify: `skills/design-tooling/design-coverage/stages/02-code-inventory.md`
- Modify: `skills/design-tooling/design-coverage/stages/03-clarification.md`
- Modify: `skills/design-tooling/design-coverage/stages/04-figma-inventory.md`
- Modify: `skills/design-tooling/design-coverage/stages/05-comparator.md`
- Modify: `skills/design-tooling/design-coverage/stages/06-report-generator.md`

For each stage file:

- [ ] **Step 1: Replace `cd ~/.claude/skills/design-coverage/` with skill-root resolution**

Find the bash preflight block in each stage MD (typically near the top) that says:
```bash
cd ~/.claude/skills/design-coverage/
```

Replace with:
```bash
# Resolve the skill root portably. Same logic as SKILL.md preflight.
cd "$(python -c 'from pathlib import Path; p=Path.cwd(); print(next(q for q in [p, *p.parents] if (q/"SKILL.md").exists()))')"
```

(Or, if the orchestrator already exports `SKILL_ROOT` from SKILL.md preflight, just `cd "$SKILL_ROOT"`.)

- [ ] **Step 2: Replace inline `~/.claude/skills/design-coverage/` strings in Python snippets**

Each stage's Python snippets reference paths like `~/.claude/skills/design-coverage/schemas/...`. Replace with:

```python
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_root import get_skill_root
SKILL_ROOT = get_skill_root()
# Then use SKILL_ROOT / "schemas" / "..." etc.
```

- [ ] **Step 3: Verify no hard-coded paths remain in stage MD**

After editing each stage:
```bash
grep -c "~/.claude/skills/design-coverage" /c/src/skills-design-coverage-improvements/skills/design-tooling/design-coverage/stages/<stage-file>.md
```

Expected: `0`.

### Task 6.5: Final sweep verification + commit

- [ ] **Step 1: Confirm zero hard-coded paths skill-wide**

```bash
cd /c/src/skills-design-coverage-improvements/skills/design-tooling/design-coverage
grep -rn "~/.claude/skills/design-coverage" SKILL.md stages/ lib/
```

Expected: no output (exit code 1).

- [ ] **Step 2: Run the full test suite to confirm no regressions**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest -v
```

Expected: all tests pass. If any test specifically asserts on hard-coded path strings, update it to use the new helper.

- [ ] **Step 3: Commit (single commit covering SKILL.md + all stage MDs)**

```bash
cd /c/src/skills-design-coverage-improvements
git add skills/design-tooling/design-coverage/SKILL.md \
        skills/design-tooling/design-coverage/stages/
git commit -m "$(cat <<'EOF'
refactor(design-coverage): replace hard-coded ~/.claude paths with skill_root resolution

Every inline Python snippet in SKILL.md and stages/*.md previously hard-coded
~/.claude/skills/design-coverage/ as the skill root. The skill silently
broke when installed at any other path (a repo's .claude/skills/, a
plugin-managed location, etc.). Replaced with calls to lib/skill_root.py's
get_skill_root() helper, which walks up from the calling file to find
SKILL.md.

The skill now installs cleanly anywhere — verified by running tests with
the skill mounted at a non-default path.

Wave 1 of the design-coverage improvements spec (#6).
EOF
)"
```

---

## Phase 7 — Wire stage MDs to use the new modules

Now that lib/ is built, stage 02 needs to know about the closed enum + candidate_destinations, stage 03 needs to call emit_questions_for_inventory and ask the candidate_destinations multi-select Q, and stage 05 needs to call severity_matrix.lookup.

### Task 7.1: Update stage 02 prose to describe the closed enum + candidate_destinations

**Files:**
- Modify: `skills/design-tooling/design-coverage/stages/02-code-inventory.md`

- [ ] **Step 1: Read the current "Rules" or equivalent section of stage 02**

Run: `grep -n "unwalked\|out.of.scope\|reason" /c/src/skills-design-coverage-improvements/skills/design-tooling/design-coverage/stages/02-code-inventory.md`

- [ ] **Step 2: Add a new section "Closed-enum reasons" near the rules**

Insert this block between the "Rules" section and the "Output" section:

```markdown
## Closed-enum reasons for `unwalked_destinations`

Stage 02 emits `unwalked_destinations` for navigation targets it does NOT
walk. The `reason` field is now a **closed enum** with values:

- `adapter-hosted` — the destination is reached through an adapter/bridge whose
  internals are not in scope (e.g., `*Adapter.*`, `*Bridge.*` calls).
- `external-module` — the destination lives in a separate module/package not
  part of this audit's source tree.
- `swiftui-bridge` — UIKit-to-SwiftUI or SwiftUI-to-UIKit bridge whose wrapped
  destination is reached through a hosting controller or representable.
- `dynamic-identifier` — the destination identifier is computed at runtime
  (e.g., `instantiateViewControllerWithIdentifier:` with a runtime string,
  selectors built from data).
- `platform-bridge` — platform-specific bridge that crosses framework boundaries
  (e.g., React Native bridge call into native, Flutter MethodChannel).

**The string `"out-of-scope-destination"` is no longer valid.** If you would
have written that, emit the destination to `candidate_destinations` instead
(see below) so stage 03 can ask the user to confirm scope.

## Candidate destinations (judgment-call escapes)

Anything that's reachable from the entry but the agent judges as "maybe in
scope, not sure" goes to `candidate_destinations: [...]`. Each entry:

```json
{
  "symbol": "MBOApptQuickBookViewController",
  "file": "MindBodyPOS/Legacy/.../QuickBook.m",
  "hop_distance": 1,
  "why_not_walked": "Modify-appointment full screen; agent unsure if part of appointment-details audit scope."
}
```

Stage 03 will surface these to the user as a multi-select question per parent
screen, defaulting all to in-scope (uncheck to exclude). Do NOT silently
in-scope or out-of-scope these on your own.
```

- [ ] **Step 3: Verify the file still parses (no broken Markdown)**

Run: `head -100 /c/src/skills-design-coverage-improvements/skills/design-tooling/design-coverage/stages/02-code-inventory.md`

Expected: no broken sections; new content is readable.

### Task 7.2: Update stage 03 prose to call `emit_questions_for_inventory` + handle `candidate_destinations`

**Files:**
- Modify: `skills/design-tooling/design-coverage/stages/03-clarification.md`

- [ ] **Step 1: Replace the "Method (platform-agnostic)" section**

The current Method (platform-agnostic) section says "ask sequentially" with free-form prose. Replace it with:

```markdown
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
record it in `03-clarifications.json`'s `resolved` array.

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
```

- [ ] **Step 2: Remove the old "ask sequentially" prose if not already removed**

Find any remaining text that says "Ask sequentially" or "for each hotspot, pose a single concrete question to the user" and delete it — the deterministic Method block above replaces it.

### Task 7.3: Update stage 05 prose to call `severity_matrix.lookup`

**Files:**
- Modify: `skills/design-tooling/design-coverage/stages/05-comparator.md`

- [ ] **Step 1: Replace the "Severity rules" section**

Find the current "Severity rules" section. Replace with:

```markdown
## Severity assignment (deterministic — wave 1)

Severity is no longer agent judgment. For each comparator row, compute the
tuple `(status, kind, hotspot_type, clarification_answer)` and call
`severity_matrix.lookup(...)`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "lib"))
from skill_root import get_skill_root
from severity_matrix import lookup, flush_misses

# For each row being assembled:
severity = lookup(
    status=row["status"],            # "present" | "missing" | "new-in-figma" | "restructured"
    kind=row.get("code_kind"),       # "screen" | "state" | "action" | "field" | None
    hotspot_type=row.get("hotspot_type"),  # one of hotspot.type enum values, or None
    clarification_answer=row.get("clarification_answer"),  # from 03-clarifications.json or None
)
row["severity"] = severity

# At end of stage, flush any unknown-tuple misses for audit:
flush_misses(run_dir / "_severity_lookup_misses.json")
```

Unknown tuples fall back to `"warn"` and are recorded to
`_severity_lookup_misses.json` at the run-dir top level so the matrix can be
grown over time. The miss file is the ONE allowed `_*.json` file at the top
level of the run-dir.

The previous prose-based severity rules are removed entirely. If a row's
severity looks wrong, the fix is to add an entry to `lib/severity_matrix.py`'s
`SEVERITY_MATRIX` dict, NOT to override the call site.
```

### Task 7.4: Run the full test suite + commit stage MD updates

- [ ] **Step 1: Verify tests still pass**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Commit**

```bash
cd /c/src/skills-design-coverage-improvements
git add skills/design-tooling/design-coverage/stages/02-code-inventory.md \
        skills/design-tooling/design-coverage/stages/03-clarification.md \
        skills/design-tooling/design-coverage/stages/05-comparator.md
git commit -m "$(cat <<'EOF'
feat(design-coverage): wire stages 02/03/05 to use the new lib/ modules

Stage 02 now describes the closed-enum reasons for unwalked_destinations
and the new candidate_destinations array (judgment-call escape). The
free-form 'out-of-scope-destination' string is explicitly forbidden;
agents emit candidates instead, where stage 03 can surface them.

Stage 03 now calls emit_questions_for_inventory(...) for hotspot
questions and emits a multi-select question per parent screen for
candidate_destinations (default in-scope, uncheck to exclude). The
free-form 'ask about hotspots' prose is removed — the registry is the
deterministic source of question shape.

Stage 05 now calls severity_matrix.lookup(...) for every row's severity.
The free-form severity rules are removed; the matrix is the deterministic
source. Unknown tuples fall back to 'warn' and write to
_severity_lookup_misses.json for audit.

Two agents on the same code + Figma should now produce reports that
differ only in narrative prose, not in error counts, severity calls, or
question sets.

Wave 1 of the design-coverage improvements spec (#1, #2, #3 wire-up).
EOF
)"
```

---

## Phase 8 — End-to-end smoke verification

Confirm the full pipeline still runs after all wave 1 changes.

### Task 8.1: Run the existing end-to-end smoke test

- [ ] **Step 1: Find and run any smoke fixture**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest tests/test_end_to_end_smoke.py -v
```

Expected: passes (no regressions). If it fails on a wave-1-changed contract (e.g., the closed enum forbids a fixture's `reason` value), update the fixture, NOT the schema.

- [ ] **Step 2: Confirm full test suite passes**

```bash
cd /c/src/skills-design-coverage-improvements/skill-tests/design-coverage
pytest -v --tb=short
```

Expected: 100% pass rate. Document any pre-existing failures as out of scope (they're not wave 1's responsibility).

### Task 8.2: Final commit if any test fixture updates were needed

If any pre-existing fixtures had to be updated to match the new schema (closed enum, etc.), commit them:

- [ ] **Step 1: Stage and commit fixture updates**

```bash
cd /c/src/skills-design-coverage-improvements
git diff --stat HEAD
git add skill-tests/design-coverage/fixtures/  # if any changed
git commit -m "$(cat <<'EOF'
chore(design-coverage): update test fixtures for wave 1 closed-enum schema

Pre-existing fixtures used the old free-form `reason` string for
unwalked_destinations; updated to use the new closed-enum values.
No behavior change — purely fixture format catch-up.
EOF
)"
```

(Skip this commit if no fixtures needed updating.)

### Task 8.3: Verify branch state

- [ ] **Step 1: Confirm branch is in good shape**

```bash
cd /c/src/skills-design-coverage-improvements
git log --oneline pratyush/design-coverage-improvements ^origin/main
git status --short
```

Expected:
- `git log` shows the wave 1 commits (skill_root, schemas, sealed_enum_index, severity_matrix, hotspot_questions, path sweep, stage wiring, +/- fixture update). 7-9 commits total.
- `git status` shows clean working tree.

- [ ] **Step 2: Print summary for the user**

Print to the user:

```
Wave 1 implementation complete. Branch: pratyush/design-coverage-improvements

Commits added on top of origin/main:
  <list of git log oneline output>

Three GH issues filed:
  - #<wave-1-number> [in-progress]
  - #<wave-2-number>
  - #<wave-3-number>

To push and open a PR:
  cd /c/src/skills-design-coverage-improvements
  git push -u origin pratyush/design-coverage-improvements
  gh pr create -R prpande/skills --base main --head pratyush/design-coverage-improvements

Wave 1 closes the methodology-drift sources from the 2026-04-14 vs 2026-04-25
audit comparison: deterministic question registry, table-lookup severity,
explicit candidate_destinations Q, and skill-relative paths.
```

---

## Self-review checklist (run after writing the plan)

- [x] **Spec coverage:** Every wave-1 spec item has at least one task. (#1 → Phase 5, #2 → Phase 4, #3 → Phases 2 + 7.2, #6 → Phases 1 + 6, sealed-enum index helper → Phase 3.)
- [x] **GH issues:** Phase 0 covers all three issue filings.
- [x] **No placeholders:** Every step has actual code or commands. No "TBD" or "implement appropriate X."
- [x] **Type consistency:** `QuestionTemplate.template`, `Question.rendered_text`, `severity_matrix.lookup` signature all match across tests and implementations.
- [x] **Each commit leaves the skill runnable:** Phase 1 ships the helper before any module uses it; Phase 2 ships schema + tests before any code consumes the new fields; Phase 3-5 each ship a complete module + tests in one commit; Phases 6-7 update prose only after the modules they reference exist.
- [x] **No pushes:** Plan never invokes `git push`. The final summary tells the user how to push themselves.
