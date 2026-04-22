import json
from pathlib import Path
from typing import Any, Dict, Optional

class ValidationError(Exception):
    pass

class Validator:
    def __init__(self, schemas_dir: Path):
        self.schemas_dir = Path(schemas_dir)
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _load_ref(self, ref: str) -> Dict[str, Any]:
        if ref not in self._cache:
            target = (self.schemas_dir / ref).resolve()
            try:
                target.relative_to(self.schemas_dir.resolve())
            except ValueError:
                raise ValidationError(f"$ref {ref!r} escapes schemas dir")
            try:
                self._cache[ref] = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                raise ValidationError(f"Cannot load $ref {ref!r}: {e}")
        return self._cache[ref]

    def validate(self, data: Any, schema: Dict[str, Any], path: str = "$") -> None:
        if "$ref" in schema:
            self.validate(data, self._load_ref(schema["$ref"]), path)
            return

        t = schema.get("type")
        if t is not None:
            types = t if isinstance(t, list) else [t]
            if not any(self._type_matches(data, x) for x in types):
                raise ValidationError(f"{path}: expected type {types}, got {type(data).__name__}")

        if "enum" in schema and data not in schema["enum"]:
            raise ValidationError(f"{path}: value {data!r} not in enum {schema['enum']}")

        if isinstance(data, str):
            if "minLength" in schema and len(data) < schema["minLength"]:
                raise ValidationError(f"{path}: string shorter than minLength {schema['minLength']}")

        if isinstance(data, (int, float)) and not isinstance(data, bool):
            if "minimum" in schema and data < schema["minimum"]:
                raise ValidationError(f"{path}: value {data} below minimum {schema['minimum']}")

        if isinstance(data, list):
            if "minItems" in schema and len(data) < schema["minItems"]:
                raise ValidationError(f"{path}: array shorter than minItems {schema['minItems']}")
            item_schema = schema.get("items")
            if item_schema:
                for i, item in enumerate(data):
                    self.validate(item, item_schema, f"{path}[{i}]")

        if isinstance(data, dict):
            for req in schema.get("required", []):
                if req not in data:
                    raise ValidationError(f"{path}: missing required key '{req}'")
            props = schema.get("properties", {})
            for key, sub in props.items():
                if key in data:
                    self.validate(data[key], sub, f"{path}.{key}")

    @staticmethod
    def _type_matches(data: Any, t: str) -> bool:
        if t == "null":
            return data is None
        if t == "string":
            return isinstance(data, str)
        if t == "integer":
            return isinstance(data, int) and not isinstance(data, bool)
        if t == "number":
            return isinstance(data, (int, float)) and not isinstance(data, bool)
        if t == "boolean":
            return isinstance(data, bool)
        if t == "array":
            return isinstance(data, list)
        if t == "object":
            return isinstance(data, dict)
        return False
