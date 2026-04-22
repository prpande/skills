# Stage 01 — Flow locator (platform-agnostic core)

## Inputs

- `00-run-config.json` — contains `figma_url`, `old_flow_hint` (optional), `platform`, `hint_source`.
- The current repository (CWD).
- Figma MCP access via `mcp__plugin_figma_figma__get_metadata` and `mcp__plugin_figma_figma__get_design_context`.

## Preflight: working-directory normalization

At the top of any Python snippet you run, normalize the working directory so `lib.*` imports resolve regardless of where the skill was invoked:

```bash
cd ~/.claude/skills/design-coverage/
```

Then add `Path.cwd() / "lib"` to `sys.path` before importing.

## Objective

Produce `01-flow-mapping.json` conforming to `~/.claude/skills/design-coverage/schemas/flow_mapping.json`. It must contain:
- `entry_screen` — the starting screen's code anchor
- `destinations[]` — each reachable screen with `figma_frame_id`, `figma_frame_name`, `code_anchor`, and `match_confidence`
- `unwalked[]` — Figma frames we could not match in code (and why, briefly)

## Method (platform-agnostic)

1. **Read Figma frames.** Use Figma MCP to list all frames in the target file/node. Record their `id`, `name`, and any absolute-position hints.
2. **Refuse loudly on unusable Figma.** If every frame is default-named (e.g., `Frame 1`, `Rectangle 2`, `Group 15`, `Ellipse 7`), halt stage 1 with a clear message pointing the user to rename frames before retrying. Do not attempt a best-effort match.
3. **Locate the entry screen in code** by name correspondence:
   - Strongest signal: exact class/file/component name match on the Figma entry frame's name.
   - Secondary signal: fuzzy token overlap (e.g., Figma frame "Appointment Details" matches a code anchor `AppointmentDetailsViewModel`).
   - If `old_flow_hint` is set, weigh it above fuzzy matches.
4. **Walk the navigation structure** to enumerate reachable destinations. The navigation mechanism varies by stack — see the platform-specific hints below for how it looks here.
5. **Name-only fallback.** If navigation walking is inconclusive, fall back to matching every Figma frame name against code anchors and record `match_confidence: "name-only"` on any that resolve only by name.
6. **Refuse loudly on no locatable entry.** If you cannot locate the entry screen with at least `match_confidence: "name-only"`, halt stage 1 and suggest the user rerun with `--old-flow <hint>`.

## Output

Write `01-flow-mapping.json` to the run directory. Regenerate the Markdown view with `python -m lib.renderer --render 1 <run-dir>`.

<!-- PLATFORM_HINTS -->
