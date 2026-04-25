"""Tests that <!-- PLATFORM_HINTS --> substitution extracts the right section."""
from __future__ import annotations
import textwrap


def inject_hint(core_prompt: str, hint_text: str, platform: str, stage_num: str) -> str:
    """Replica of the injection logic from SKILL.md."""
    section_map = {
        "01": "## 01 Flow locator",
        "02": "## 02 Code inventory",
        "03": "## 03 Clarification",
    }
    header = section_map[stage_num]
    lines = hint_text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == header)
    end = next(
        (i for i in range(start + 1, len(lines))
         if lines[i].startswith("## ") and lines[i].strip() != header),
        len(lines),
    )
    hint_section = "\n".join(lines[start + 1:end]).strip("\n")
    injected = f"\n## Platform-specific hints ({platform})\n\n{hint_section}\n"
    return core_prompt.replace("<!-- PLATFORM_HINTS -->", injected)


HINT_FIXTURE = textwrap.dedent("""\
    ---
    name: ios
    detect: ["**/*.xcodeproj"]
    description: iOS.
    confidence: high
    ---

    ## 01 Flow locator
    iOS flow content.

    ## 02 Code inventory
    iOS inventory content.

    ## 03 Clarification
    iOS clarification content.
""")


def test_injects_stage_01() -> None:
    core = "Body before.\n\n<!-- PLATFORM_HINTS -->\n"
    out = inject_hint(core, HINT_FIXTURE, "ios", "01")
    assert "iOS flow content" in out
    assert "iOS inventory content" not in out
    assert "## Platform-specific hints (ios)" in out


def test_injects_stage_02() -> None:
    core = "Body.\n<!-- PLATFORM_HINTS -->\n"
    out = inject_hint(core, HINT_FIXTURE, "ios", "02")
    assert "iOS inventory content" in out
    assert "iOS flow content" not in out


def test_injects_stage_03() -> None:
    core = "Body.\n<!-- PLATFORM_HINTS -->\n"
    out = inject_hint(core, HINT_FIXTURE, "ios", "03")
    assert "iOS clarification content" in out
    assert "iOS flow content" not in out
    assert "iOS inventory content" not in out


