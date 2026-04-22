# Scout Stage 01 — Stack profile

## Inputs

- The current repository (CWD).

## Objective

Emit `<run-dir>/stack-profile.json` characterizing the UI stack of this repo.
The downstream stage-2 prompt uses it to decide which patterns to harvest.

## Method

1. **Identify the primary language(s).** File-extension tallies — `.swift`,
   `.kt`, `.java`, `.tsx/.ts/.jsx/.js`, `.dart`, `.vue`. If it's a monorepo
   with multiple UI trees, REFUSE LOUDLY and list the candidates; ask the user
   to scope to one sub-tree and re-run.
2. **Identify the build system.** Presence of `Package.swift`,
   `build.gradle(.kts)`, `package.json`, `pubspec.yaml`, `Podfile`,
   `*.xcodeproj`, `*.xcworkspace`.
3. **Identify the UI framework.**
   - iOS: UIKit (UIViewController) vs SwiftUI (`: View`) vs mixed.
   - Android: Jetpack Compose (`@Composable`) vs Fragment/XML vs hybrid (ComposeView).
   - Web: React / Vue / Angular / Svelte; SSR vs CSR; meta-framework (Next, Nuxt, SvelteKit).
   - Cross-platform: React Native (`@react-navigation`), Flutter (MaterialApp),
     Compose Multiplatform.
4. **Identify the navigation style.**
   - Graph-based (Android nav graph, TanStack Router).
   - Router-config (React Router, Vue Router).
   - Stack-based imperative (UIKit).
   - Declarative (SwiftUI NavigationStack, Compose Navigation).
   - Coordinator pattern.
5. **Identify the state-container convention.**
   - ViewModel + observable (Android, SwiftUI `@ObservableObject`).
   - Store pattern (Redux, Pinia, Zustand).
   - Hooks (React `useState`/`useContext`).
   - BLoC (Flutter).
6. **Identify hybrid-host patterns** if any exist (UIHostingController,
   ComposeView, React-in-Angular bridges).

## Refuse conditions

- **Multi-UI monorepo** — refuse, list candidate sub-trees, ask user to re-run
  inside one of them.
- **No UI detected at all** — refuse, point user at
  `~/.claude/skills/design-coverage-scout/hint-template.md` for manual authoring.

## Output

Write `<run-dir>/stack-profile.json`:

```jsonc
{
  "primary_language": "kotlin",
  "build_system": "gradle",
  "ui_framework": "compose + fragment/xml",
  "navigation_style": "nav-graph + compose-nav",
  "state_container": "viewmodel + stateflow",
  "hybrid_hosts": true,
  "confidence": "high"
}
```

Set `confidence` on the profile itself based on coverage of the six probes
above: `high` if all six produced a confident answer, `medium` if one or two
were guesses, `low` otherwise.
