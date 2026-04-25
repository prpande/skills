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
