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

# Module-level (not name-level) import so monkeypatching `skill_root.get_skill_root`
# in tests is picked up live without `importlib.reload(sealed_enum_index)`. A `from
# skill_root import get_skill_root` form would copy the reference at import time;
# after monkeypatch reverts, the local copy stays bound to the test lambda for the
# rest of the session and any subsequent test using this module reads fake schemas.
import skill_root


def get_sealed_enum_pattern_keys() -> list[str]:
    """Return sorted list of <dotted_path>.<value> keys derived from schemas/.

    A key is emitted for every enum value of every field annotated with
    `"x-platform-pattern": true`. Paths are rooted at the schema's file stem.
    """
    keys: list[str] = []
    schemas_dir = skill_root.get_skill_root() / "schemas"
    for schema_file in sorted(schemas_dir.glob("*.json")):
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        root_name = schema_file.stem
        for path, field in _walk_schema(schema, root_name):
            if field.get("x-platform-pattern") and "enum" in field:
                for value in field["enum"]:
                    keys.append(f"{path}.{value}")
    return sorted(keys)


_MAX_WALK_DEPTH = 20  # safety bound; current schemas nest <8 deep


def _walk_schema(node: dict, path: str, _depth: int = 0) -> Iterator[tuple[str, dict]]:
    """Yield (dotted_path, field_subtree) for every property in the schema.

    Recurses into `properties` and `items.properties`. Does NOT follow `$ref` —
    referenced schemas are walked separately when iterating the schemas/ dir.
    Bounded at `_MAX_WALK_DEPTH` so an accidentally cyclic or pathologically
    deep schema can't stack-overflow at registry-build time.
    """
    if not isinstance(node, dict) or _depth > _MAX_WALK_DEPTH:
        return
    yield path, node
    for child_name, child in (node.get("properties") or {}).items():
        yield from _walk_schema(child, f"{path}.{child_name}", _depth + 1)
    items = node.get("items")
    if isinstance(items, dict):
        # Array items don't add a path segment; their properties are addressed
        # as if direct children of the array's containing field.
        for child_name, child in (items.get("properties") or {}).items():
            yield from _walk_schema(child, f"{path}.{child_name}", _depth + 1)
    # Tuple-typed items (JSON-Schema's `items: [<sub>, <sub>]` form) are not
    # used anywhere under schemas/ today. If a future schema introduces one,
    # extend this branch — silently skipping would drop platform-pattern
    # annotations on the tuple members.
