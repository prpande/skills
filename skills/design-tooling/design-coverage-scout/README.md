# design-coverage-scout

Companion skill to `design-coverage` that inspects an unfamiliar UI
repository and emits a new `platforms/<name>.md` hint file.

## When to use

- `design-coverage` detected an unknown stack and the user picked "generate
  a hint" from the live prompt.
- A user wants to pre-build a hint for a new stack before running coverage.

## Invocation

```bash
/design-coverage-scout [--platform-name <name>] [--force]
```

## Output

- Draft at `<design-coverage-install>/platforms/<name>.md.draft`.
- On approval, moved to `<design-coverage-install>/platforms/<name>.md`.
- Never auto-commits. User commits and pushes to share.

## Methodology

Three-stage pipeline mirrors design-coverage's scaffolding:

1. **Stack profile** (`stages/01-stack-profile.md`)
2. **Pattern extraction** (`stages/02-pattern-extraction.md`)
3. **Hint rendering** (`stages/03-hint-rendering.md`) — interactive draft/approve

See [`hint-template.md`](./hint-template.md) for the required shape of any
hint file (scout output conforms to it automatically).

## Design & plan

- [Design](../../../docs/superpowers/specs/2026-04-22-design-coverage-platform-agnostic-design.md)
- [Implementation plan](../../../docs/superpowers/plans/2026-04-22-design-coverage-platform-agnostic.md)
