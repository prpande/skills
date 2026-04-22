"""Defang harvested section content before substituting into a hint draft.

Stage 02 of scout harvests snippets from the target repo. If a snippet
contains `---` on a line by itself, it terminates the hint's frontmatter
block when substituted. If it contains a `## 0N …` heading, the hint
validator finds a duplicate section header. This module renders those
structural chars inert without losing the content.
"""
import re

_HR_LINE = re.compile(r"^\s*---\s*$")
_STAGE_HEADER = re.compile(r"^##\s+0[1-3]\s")


def sanitize_section(text: str) -> str:
    """Neutralize content that would corrupt the enclosing hint file.

    - Lines that are exactly `---` become `— — —` (U+2014 em-dashes) —
      visually similar, but no longer matched by the YAML frontmatter
      terminator.
    - Lines starting with `## 0N ` (N in 1..3) are indented by two
      spaces so they render as inline content rather than a duplicate
      stage-section heading.
    """
    out = []
    for line in text.splitlines():
        if _HR_LINE.match(line):
            out.append("— — —")
        elif _STAGE_HEADER.match(line):
            out.append("  " + line)
        else:
            out.append(line)
    return "\n".join(out)
