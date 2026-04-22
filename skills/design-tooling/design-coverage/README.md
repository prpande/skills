# design-coverage

A platform-agnostic Claude Code skill that compares an existing in-code UI flow
against a new Figma design and produces an auditable, confidence-tagged
discrepancy report.

## Quick start

```bash
# Install (from the skills repo root)
ln -s "$PWD/skills/design-tooling/design-coverage" "$HOME/.claude/skills/design-coverage"
# Restart Claude Code session.

# Run from inside a target repo worktree:
/design-coverage <figma-url>
```

## Arguments

- `<figma-url>` — required, e.g. `https://figma.com/design/<fileKey>/...?node-id=<nodeId>`
- `--old-flow <hint>` — optional string to disambiguate flow detection
- `--platform <name>` — one of `ios`, `android`, `agnostic` (or any other
  platform hint installed under `platforms/`)
- `--output-dir <path>` — override default artifact location

## Platform hints

Day-one hints shipped under `platforms/`:
- `ios.md` — ported from MindBodyPOS #5349
- `android.md` — ported from Express-Android #5190

For unknown stacks, run `design-coverage-scout` to generate a new hint, or
pass `--platform agnostic` to run without platform-specific guidance.

## Artifacts

Runs land at `<target-repo>/docs/design-coverage/<YYYY-MM-DD>-<flow-slug>/`:

- `00-run-config.json` + 01…06 stage artifacts (JSON source of truth)
- Regenerated Markdown views with `DO-NOT-EDIT` banners and sha256 headers

## Design & plan

- [Design](../../../docs/superpowers/specs/2026-04-22-design-coverage-platform-agnostic-design.md)
- [Implementation plan](../../../docs/superpowers/plans/2026-04-22-design-coverage-platform-agnostic.md)
