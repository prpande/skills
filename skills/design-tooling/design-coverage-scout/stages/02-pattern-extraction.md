# Scout Stage 02 — Pattern extraction

## Inputs

- `<run-dir>/stack-profile.json` from stage 1.
- The current repository.

## Objective

For each of the three required hint sections (`01 Flow locator`,
`02 Code inventory`, `03 Clarification`), harvest concrete patterns from this
repo that will be rendered into `platforms/<name>.md` in stage 3. Write
`<run-dir>/hint-draft.json` conforming to
`~/.claude/skills/design-coverage-scout/schemas/hint_draft.json`.

## Durability rule (applies to every section below)

Hint files live in the shared skills repo and are re-used across many runs
against the same stack, months apart. **Describe patterns, not instance
counts.** Do not embed point-in-time tallies like "329 UIViewController hits
across 143 files" or "175 `@Published` hits repo-wide" — these drift as the
repo evolves and turn a hint file stale.

Concretely:

- **Allowed**: ripgrep-ready patterns (`class .*ViewController`,
  `@Composable fun <PascalCase>Screen`), concrete class names that are
  structurally load-bearing (e.g., a base protocol like `Coordinator` at a
  specific path), representative examples ("e.g., `SettingsCoordinator`,
  `MoreCoordinator`").
- **Not allowed**: numeric hit counts, file-count tallies, "X hits repo-wide",
  "N files match" — even approximate. If you need to convey scale, use
  qualitative words ("dominant", "common", "rare") instead.

When in doubt, ask: "would this sentence still be accurate a year from now?"
If a number would be wrong by then, cut the number.

## Method

### For the `flow_locator` section

- Find 1–2 concrete examples of how flows are declared (the file glob, the
  class/decorator name, the route-constant pattern).
- Identify the navigation walker approach (how destinations are listed from a
  starting point).
- Note any refuse-loud conditions specific to this stack.

### For the `code_inventory` section

- Identify the screen-declaration glob (e.g., `class .*Fragment` OR
  `@Composable fun <PascalCase>Screen`).
- Identify the state-container glob (e.g., `class .*ViewModel`).
- Identify the action pattern (e.g., `.clickable { ... }`, `@IBAction`).
- Identify the field-rendering pattern (e.g., `Text(`, `TextView`).
- Identify hybrid-host pattern if one exists.

### For the `clarification` section

- Grep for feature-flag usage pattern name(s).
- Grep for permission-check patterns (`checkSelfPermission`,
  `AVCaptureDevice.authorizationStatus`).
- Grep for server-driven-content markers (network-layer references from UI
  code).
- Grep for responsive/config-branch patterns (`values-night/`, size-class
  checks, media queries).
- Grep for A/B-test hooks.
- Compile a list of topics to ask the human about (what the
  `03 Clarification` section will list).

## Sealed-enum pattern extraction (wave 2)

After harvesting the three prose sections above, walk
`get_sealed_enum_pattern_keys()` from the design-coverage skill's
`lib/sealed_enum_index.py` and produce a `sealed_enum_patterns` map for
the draft. The registry is **schema-derived**, not hand-coded: adding a
new `x-platform-pattern: true` enum value to a design-coverage schema
surfaces here automatically on the next run.

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "design-coverage" / "lib"))
# In symlink-installed setups the line above resolves; if not, walk to the
# paired skill via the realpath of this scout module's neighbor.
from sealed_enum_index import get_sealed_enum_pattern_keys

keys = get_sealed_enum_pattern_keys()  # e.g., ["inventory_item.kind.action", ...]
```

For each key, look up the matching Platform section below for inductive
bias, run discovery against the consuming repo, and emit candidate
`grep:` patterns into the draft under `sealed_enum_patterns.<key>`.

**Coverage threshold.** The draft must populate `sealed_enum_patterns`
for **≥ 80%** of the keys returned by `get_sealed_enum_pattern_keys()`.
Below that, set `confidence: "low"` AND emit an `unresolved_questions`
entry per missing key explaining why no pattern was found. Do not skip
silently — a hint that lacks coverage for half the registry will silently
produce empty inventory rows downstream.

### Platform sections — platform-truth heuristics

These sections encode the conventions that transcend any specific app on
each platform. Use them as the **starting bias** for the discovery walk;
combine with this-codebase-specific symbol scanning (e.g., grep for the
heuristic, then promote the actual class names you find into the draft's
grep list).

#### iOS

- **`inventory_item.kind.screen`**: `class \w+ ?: ?UI(View|TableView|CollectionView|Page|Split|Tab|Navigation)Controller`, `struct \w+ ?: ?View\b`, `class \w+Coordinator\b`, `class \w+FlowController\b`, `class \w+Router\b`. Storyboard / XIB anchors: `customClass="<name>"` in `*.storyboard` / `*.xib`.
- **`inventory_item.kind.action`**: `@IBAction`, `addTarget\(self, action: #selector\(`, `Button\(action:`, `\.onTapGesture`, `\.onLongPressGesture`, `\.swipeActions`, `performSegue\(withIdentifier:`.
- **`inventory_item.kind.field`**: `\.text ?=`, `\.attributedText ?=`, `\.image ?=`, `Text\(`, `Label\(`, `AsyncImage\(`, `SecureField\(`, `TextField\(`, `Toggle\(`.
- **`inventory_item.kind.state`**: `@Published var`, `CurrentValueSubject<`, `BehaviorRelay<`, `@State\b`, `@StateObject\b`, `@ObservedObject\b`, `@EnvironmentObject\b`, `enum .*State\b` switch arms.
- **`inventory_item.source.surface.compose`**: `struct \w+ ?: ?View\b` (SwiftUI is the iOS analogue of Compose for surface tagging).
- **`inventory_item.source.surface.xml`**: `\.storyboard\b`, `\.xib\b`.
- **`inventory_item.source.surface.hybrid`**: `UIHostingController\(rootView:`, `UIViewControllerRepresentable`, `UIViewRepresentable`.
- **`inventory_item.source.surface.nav-xml`**: storyboard `<segue>` graphs.
- **`inventory_item.source.surface.nav-compose`**: `NavigationStack \{`, `NavigationLink\(`, `\.navigationDestination\(for:`.
- **`inventory_item.hotspot.type.feature-flag`**: `FeatureFlagType\.`, `FeatureFlagManager\.`, `ImplementationSwitch\.`, `RemoteConfig\.`, `LaunchDarkly\.`.
- **`inventory_item.hotspot.type.permission`**: `staff\.can[A-Z]`, `user\.hasRole\(`, `AVCaptureDevice\.authorizationStatus`, `CLLocationManager`, `UNUserNotificationCenter`, `PHPhotoLibrary`.
- **`inventory_item.hotspot.type.server-driven`**: `response\.items`, `response\.sections`, `JSONDecoder\(\)\.decode`.
- **`inventory_item.hotspot.type.view-type`**: `dequeueReusableCell.*withReuseIdentifier`, runtime `switch ... \.status\b`.
- **`inventory_item.hotspot.type.form-factor`**: `UIDevice\.current\.userInterfaceIdiom`, `horizontalSizeClass`, `traitCollection\.userInterfaceStyle`.
- **`inventory_item.hotspot.type.process-death`**: `NSUserActivity`, `restorationID`, `stateRestorationActivity`.
- **`inventory_item.hotspot.type.sheet-dialog`**: `UIAlertController`, `\.sheet\(isPresented:`, `\.fullScreenCover\(`, `\.popover\(`.
- **`inventory_item.hotspot.type.config-qualifier`** / **`inventory_item.hotspot.type.viewpager-tab`**: typically n/a on iOS — record an `unresolved_questions` entry rather than inventing patterns.
- **`code_inventory.unwalked_destinations.reason.platform-bridge`**: `UIHostingController\(rootView:`, `UIViewControllerRepresentable`.
- **`code_inventory.unwalked_destinations.reason.adapter-hosted`**: `Adapter\.\w+\(`, `Bridge\.\w+\(`.
- **`code_inventory.unwalked_destinations.reason.dynamic-identifier`**: `instantiate.*WithIdentifier:`, `Selector\("`.
- **`code_inventory.unwalked_destinations.reason.swiftui-bridge`**: `UIHostingController`, `UIViewControllerRepresentable`, `UIViewRepresentable`.
- **`code_inventory.unwalked_destinations.reason.external-module`**: `import` from a Pod/SPM module declared in `Podfile` / `Package.swift`.
- **`code_inventory.unwalked_destinations.reason.unresolved-class`**: anchors that didn't resolve to any walked file.

#### Android

- **`inventory_item.kind.screen`**: `class \w+ ?: ?Fragment\b`, `class \w+ ?: ?BottomSheetDialogFragment\b`, `class \w+ ?: ?DialogFragment\b`, `class \w+ ?: ?(AppCompat|Fragment|Component)Activity\b`, `@Composable\s+fun\s+\w+Screen\b`.
- **`inventory_item.kind.action`**: `\.clickable\s*\{`, `onClick\s*=\s*\{`, `\.combinedClickable\b`, `setOnClickListener`, `setOnLongClickListener`, `android:onClick="`, `KeyboardActions\(`.
- **`inventory_item.kind.field`**: `Text\(`, `Image\(`, `Icon\(`, `AsyncImage\(`, `<TextView`, `<ImageView`, `<EditText`, `<Switch`, `<CheckBox`.
- **`inventory_item.kind.state`**: `MutableStateFlow`, `StateFlow<`, `MutableLiveData`, `LiveData<`, `SavedStateHandle`, `sealed (class|interface) \w*(UiState|State)\b`.
- **`inventory_item.source.surface.compose`**: `@Composable\s+fun\s+\w+`.
- **`inventory_item.source.surface.xml`**: `R\.layout\.`, `setContentView\(R\.layout\.`, `<Name>Binding\b`.
- **`inventory_item.source.surface.hybrid`**: `\bComposeView\b`, `setContent\s*\{`.
- **`inventory_item.source.surface.nav-xml`**: `res/navigation/.*\.xml`.
- **`inventory_item.source.surface.nav-compose`**: `NavHost\s*\(`, `composable\s*\(`, `navigation\s*\(\s*route\s*=`.
- **`inventory_item.hotspot.type.feature-flag`**: `FeatureFlags\.`, `Flags\.`, `isEnabled\(`, `FlagKey`.
- **`inventory_item.hotspot.type.permission`**: `checkSelfPermission`, `registerForActivityResult\(.*RequestPermission`, `android\.permission\.[A-Z_]+`.
- **`inventory_item.hotspot.type.server-driven`**: Retrofit / OkHttp response decoding into UI state, paged adapters.
- **`inventory_item.hotspot.type.config-qualifier`**: `Configuration\.uiMode`, resources under `values-night/`, `values-ldrtl/`, `values-sw\d+dp/`.
- **`inventory_item.hotspot.type.form-factor`**: `resources\.configuration\.smallestScreenWidthDp`, `isTablet\(\)`.
- **`inventory_item.hotspot.type.process-death`**: `SavedStateHandle\b`, `savedStateHandle\.get\(`.
- **`inventory_item.hotspot.type.view-type`**: RecyclerView `getItemViewType` branches, `ViewHolder` subclasses.
- **`inventory_item.hotspot.type.viewpager-tab`**: `ViewPager2 \+ FragmentStateAdapter` data-driven tab counts.
- **`inventory_item.hotspot.type.sheet-dialog`**: `BottomSheetDialog`, `DialogFragment`, `showSheet`, `show\(supportFragmentManager`.
- **`code_inventory.unwalked_destinations.reason.platform-bridge`**: React Native bridge calls into native, Flutter MethodChannel.
- **`code_inventory.unwalked_destinations.reason.adapter-hosted`**: `*Adapter\.` / `*Bridge\.` calls whose internals are out of scope.
- **`code_inventory.unwalked_destinations.reason.dynamic-identifier`**: Fragment instantiations from runtime strings.
- **`code_inventory.unwalked_destinations.reason.swiftui-bridge`**: typically n/a on Android — record a `null` value or skip.
- **`code_inventory.unwalked_destinations.reason.external-module`**: nav-graph `<fragment android:name="<external.module.Class>"`.
- **`code_inventory.unwalked_destinations.reason.unresolved-class`**: nav-graph `android:name=` referencing a class not in the walked source tree.

#### Adding a new platform section

Add a `#### <Platform Name>` heading to the list above and enumerate
each enum-key heuristic. The format is intentionally identical across
platforms so a new platform section is mechanical: the keys list is fixed
by `get_sealed_enum_pattern_keys()`; the values are this-platform's
inductive bias for what to grep for. Once the section lands, scout
runs against repos on that platform produce drafts on the same
≥ 80% coverage contract as iOS / Android.

If a key has no analogue on the new platform (e.g., `viewpager-tab` on
iOS), document that explicitly (`typically n/a on <platform>`) rather
than omitting the line — silence reads as "scout didn't think about
this", and the next contributor has to redo the analysis.

## Confidence rules

- All three sections harvested ≥ 1 concrete pattern → `confidence: "high"`.
- Some sections empty → `confidence: "medium"` AND add items to
  `unresolved_questions`.
- No section harvested anything → stop, tell the user to author the hint
  manually from `hint-template.md`.

## Output

Write `<run-dir>/hint-draft.json` conforming to the schema. Each
`sections.flow_locator`, `sections.code_inventory`, `sections.clarification`
is a prose string written in hint-file style — imperative voice, concrete
patterns, links to actual tokens in the repo. If any section is below
confidence, populate `unresolved_questions` with specific asks for the curator.
