# Platform hint template

Every `platforms/<name>.md` file inside `design-coverage/` must conform to the
shape below. The main skill's hint-injection logic and the repo's structural
validator both enforce this contract.

## Required frontmatter

```yaml
---
name: <short-lowercase-platform-name>          # Required. Lowercase, hyphen-separated.
detect:                                         # Required. At least one glob.
  - "<glob>"                                    #   e.g. "**/*.xcodeproj", "Package.swift"
description: <one-line summary>                 # Required.
confidence: high | medium | low                 # Required.
---
```

**`detect` globs.** The main skill matches each glob against the current
working directory. If ANY glob matches, the platform is considered detected.
If multiple hints detect, the orchestrator refuses and asks the user to pass
`--platform <name>` to disambiguate.

**`confidence: low` or `medium`** signals the hint was auto-generated and may
miss platform-specific patterns. Scout emits `confidence: medium` by default;
a human curator should review and promote to `high` after validation.

## Required sections

### `## 01 Flow locator`

Platform-specific guidance for stage 1 of design-coverage. Explain:
- The platform's navigation mechanism (nav graph, router config, stack-based,
  coordinator-based, etc.).
- How the entry screen of a flow is typically named/declared.
- Refuse-loud conditions specific to this stack (e.g., storyboard-only flows
  with no code anchors).

### `## 02 Code inventory`

Platform-specific guidance for stage 2:
- How screens are declared (framework-specific class/decorator/component
  patterns).
- How state is held (state containers, hooks, observables, etc.).
- How actions are attached (event handlers, closures, decorators).
- How fields are rendered (text views, bindings, JSX, etc.).
- How hybrid hosts are detected and represented (if the platform has any —
  e.g., UIHostingController on iOS, ComposeView on Android).

### `## 03 Clarification`

A list of hotspot topics stage 3 should ask the human about. Each item should
be one line describing what to look for and what to confirm (feature flags,
permission gates, server-driven content, responsive branches, etc.).

## Optional sections

### `## Unresolved questions`

If `confidence < high`, scout emits this section with bullet-list items the
hint author was unsure about. A human curator resolves these and removes the
section before promoting confidence.

## Style

- **Imperative voice.** "Grep for X," "Check Y," not "The developer should
  look at X."
- **Concrete patterns, not abstract advice.** "Grep for `@Composable` fun
  declarations" beats "look for composable components."
- **Link to code.** Reference the actual tokens the stack uses, not
  paraphrased equivalents.
- **Keep each section focused.** If it grows past ~100 lines, split into
  clearly labeled sub-sections.
