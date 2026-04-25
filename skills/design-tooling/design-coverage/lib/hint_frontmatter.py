"""Hint-frontmatter parser and validator.

Wave 2 #10a — adds four optional fields to platform hint files:
- multi_anchor_suffixes: list[str]                 (consumed by wave 3 #4)
- default_in_scope_hops: int (default 2)           (consumed by stage 02)
- hotspot_question_overrides: dict[str, str]       (consumed by stage 03)
- sealed_enum_patterns: dict[str, {grep, description?}]
                                                   (consumed by stage 02 + scout)

`sealed_enum_patterns` keys MUST be in the schema-derived registry returned
by `sealed_enum_index.get_sealed_enum_pattern_keys()`. Unknown keys are
rejected at load time so a typo in a repo-local hint can't silently widen
the registry.
"""
from __future__ import annotations

import re
from typing import Any


_FRONTMATTER_RE = re.compile(
    r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|\Z)", re.DOTALL
)


def _yaml_unescape(s: str) -> str:
    """Reverse the escaping emitted by render_draft._yaml_str.

    Intentionally narrow: only handles the two escape sequences that
    _yaml_str produces (nothing more, nothing less):
      \\  →  \
      \"  →  "
    Processed character-by-character so mixed sequences (e.g. \\\")
    are decoded correctly.
    """
    result: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == "\\":
                result.append("\\")
                i += 2
            elif nxt == '"':
                result.append('"')
                i += 2
            else:
                result.append(s[i])
                i += 1
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def parse_hint_frontmatter(text: str) -> dict[str, Any]:
    """Parse the frontmatter block from a hint .md file into a dict."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm: dict[str, Any] = {}
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line[0].isspace():
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "" or value == "|":
            block_items: list[str] = []
            j = i + 1
            while j < len(lines) and (lines[j].startswith("  -") or
                                       lines[j].lstrip().startswith("- ")):
                item = lines[j].lstrip()[2:].strip().strip('"').strip("'")
                block_items.append(item)
                j += 1
            if block_items:
                fm[key] = block_items
                i = j
                continue
            if j < len(lines) and lines[j].startswith("  ") and ":" in lines[j]:
                fm[key], i = _parse_nested_mapping(lines, i + 1)
                continue
            fm[key] = ""
            i += 1
            continue
        if value == "{}":
            fm[key] = {}
        elif value.lstrip("-").isdigit():
            fm[key] = int(value)
        elif value in ("true", "false"):
            fm[key] = value == "true"
        else:
            raw = value.strip('"').strip("'")
            fm[key] = _yaml_unescape(raw)
        i += 1
    return fm


def _parse_nested_mapping(lines: list[str], start: int) -> tuple[dict[str, Any], int]:
    """Parse a mapping rooted at column 2.

    Handles two shapes:
    - Two-level nested dict (sealed_enum_patterns): outer keys end with `:`,
      inner keys are at indent 4, list items at indent 6.
    - Flat {str: str} dict (hotspot_question_overrides): key-value pairs at
      indent 2 that do NOT end with `:`.
    """
    out: dict[str, Any] = {}
    i = start
    cur_key: str | None = None
    cur_val: dict[str, Any] | None = None
    cur_subkey: str | None = None
    while i < len(lines):
        line = lines[i]
        if line == "" or line.lstrip().startswith("#"):
            i += 1
            continue
        if not line.startswith("  "):
            break
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent == 2:
            if stripped.endswith(":"):
                # Start of a new outer key for two-level nested dict.
                cur_key = stripped[:-1]
                cur_val = {}
                out[cur_key] = cur_val
                cur_subkey = None
            elif ":" in stripped:
                # Flat key: value entry (e.g., hotspot_question_overrides).
                flat_key, _, flat_val = stripped.partition(":")
                raw_fk = flat_key.strip().strip('"').strip("'")
                raw_fv = flat_val.strip().strip('"').strip("'")
                out[_yaml_unescape(raw_fk)] = _yaml_unescape(raw_fv)
            i += 1
            continue
        if indent == 4 and ":" in stripped:
            sub_key, _, sub_val = stripped.partition(":")
            sub_key = sub_key.strip()
            sub_val = sub_val.strip()
            cur_subkey = sub_key
            if sub_val == "":
                if cur_val is not None:
                    # Only 'grep' is a known list field; all other empty
                    # sub-values (e.g. description:) are scalar → None.
                    cur_val[sub_key] = [] if sub_key == "grep" else None
            else:
                if cur_val is not None:
                    if sub_val == "null":
                        cur_val[sub_key] = None
                    else:
                        cur_val[sub_key] = _yaml_unescape(
                            sub_val.strip('"').strip("'")
                        )
            i += 1
            continue
        if indent == 6 and stripped.startswith("- ") and cur_subkey and cur_val is not None:
            if isinstance(cur_val.get(cur_subkey), list):
                # Unescape YAML double-backslash back to single backslash so
                # callers can use the value directly as a Python regex pattern.
                raw = stripped[2:].strip().strip('"').strip("'")
                cur_val[cur_subkey].append(raw.replace("\\\\", "\\"))
            i += 1
            continue
        i += 1
    return out, i


def validate_hint_frontmatter(
    fm: dict[str, Any],
    sealed_keys: list[str],
) -> list[str]:
    """Return a list of error strings; empty list means valid."""
    errors: list[str] = []
    for required in ("name", "detect", "description", "confidence"):
        if required not in fm:
            errors.append(f"frontmatter missing required key: {required}")
    if "confidence" in fm and fm["confidence"] not in {"high", "medium", "low"}:
        errors.append(
            f"frontmatter 'confidence' must be high/medium/low, got "
            f"{fm['confidence']!r}"
        )
    if "detect" in fm:
        if not isinstance(fm["detect"], list) or not fm["detect"]:
            errors.append("frontmatter 'detect' must list at least one glob entry")
        elif any(not isinstance(g, str) or not g for g in fm["detect"]):
            errors.append(
                "frontmatter 'detect' items must be non-empty strings"
            )

    if "multi_anchor_suffixes" in fm:
        if not isinstance(fm["multi_anchor_suffixes"], list):
            errors.append("frontmatter 'multi_anchor_suffixes' must be a list of strings")
        elif any(not isinstance(s, str) or not s for s in fm["multi_anchor_suffixes"]):
            errors.append(
                "frontmatter 'multi_anchor_suffixes' items must be non-empty strings"
            )
    if "default_in_scope_hops" in fm:
        v = fm["default_in_scope_hops"]
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            errors.append(
                f"frontmatter 'default_in_scope_hops' must be a non-negative "
                f"integer, got {v!r}"
            )
    if "hotspot_question_overrides" in fm:
        if not isinstance(fm["hotspot_question_overrides"], dict):
            errors.append(
                "frontmatter 'hotspot_question_overrides' must be a mapping"
            )
        elif any(
            not isinstance(v, str)
            for v in fm["hotspot_question_overrides"].values()
        ):
            errors.append(
                "frontmatter 'hotspot_question_overrides' values must be strings"
            )

    sep = fm.get("sealed_enum_patterns")
    if sep is not None:
        if not isinstance(sep, dict):
            errors.append("frontmatter 'sealed_enum_patterns' must be a mapping")
        else:
            allowed = set(sealed_keys)
            for key, body in sep.items():
                if key not in allowed:
                    errors.append(
                        f"frontmatter 'sealed_enum_patterns' has unknown key "
                        f"{key!r} (not in schema-derived registry)"
                    )
                if not isinstance(body, dict):
                    errors.append(
                        f"frontmatter 'sealed_enum_patterns.{key}' must be a "
                        f"mapping with 'grep' (list) and optional 'description'"
                    )
                    continue
                if "grep" not in body:
                    errors.append(
                        f"frontmatter 'sealed_enum_patterns.{key}' missing "
                        f"required 'grep' list"
                    )
                elif not isinstance(body["grep"], list) or not body["grep"]:
                    errors.append(
                        f"frontmatter 'sealed_enum_patterns.{key}.grep' must "
                        f"be a non-empty list of regex strings"
                    )
    return errors
