---
name: android
detect:
  - "**/build.gradle"
  - "**/build.gradle.kts"
  - "**/AndroidManifest.xml"
description: Android (Compose + Fragment/XML + hybrid ComposeView) hint. Ported from Express-Android #5190.
confidence: high
---

## 01 Flow locator

Android apps mix three navigation stacks: classic Fragment-based nav-graphs
(XML), Compose Navigation (`NavHost { composable("route") { ... } }`), and
plain Activity launches. Walk them in this order.

**Pass 1 — nav-graph match (preferred).** This is the strongest signal.

- Glob every `res/navigation/*.xml` under the app module's `res/` dirs. Each
  `<fragment>` / `<dialog>` / `<activity>` node carries an `android:name`
  pointing at the destination class — record `{id, label, class, source_file}`
  for every destination.
- Grep Kotlin for Compose-Nav routes:
  - `NavHost\s*\(` — the host.
  - `composable\s*\(` — route destinations. Resolve the route argument even
    when it comes from a sealed-class constant (e.g.,
    `composable(Screen.AppointmentDetails.route)` — follow the constant to
    its declaration).
  - `navigation\s*\(\s*route\s*=` — nested nav graphs.
- Tokenize the Figma top-frame names and any `--old-flow` hint; score each
  destination by distinct token overlap. Populate `destinations[]` with the
  top matches and a `score` per mapping. Set `match_confidence: "high"` on
  any destination whose tokens overlap >=2 frame tokens.

**Pass 2 — name-search fallback.** Run only if Pass 1 produced no match
above the medium threshold.

- Tokenize Figma frame names + hint.
- Grep against `class\s+\w+\s*:\s*(Fragment|BottomSheetDialogFragment|DialogFragment|AppCompatActivity|FragmentActivity)`,
  `@Composable\s+fun\s+\w+`, and `res/layout/*.xml` filenames under the app
  module.
- Rank by distinct-anchor count (how many independent signals — class name,
  composable, layout filename — agree on the same destination).
- Set `match_confidence: "name-only"` on any destination that resolved only
  via this pass.

**Confidence tagging.**

- `high` — Pass 1 (nav-graph) produced the match.
- `medium` — Pass 2 with >=2 distinct anchors agreeing.
- `name-only` / `low` — Pass 2 with <2 anchors. Continue but surface
  prominently in the final report.

**Refuse-loud conditions.** Halt stage 1 (set `locator_method: "refused"`,
populate `refused_reason`, leave `destinations: []`) if any of:

- Every Figma frame name matches `^(Frame|Rectangle|Group|Ellipse)\s+\d+$`
  — reason: `"Figma frames are all default-named; rename frames or pass
  --old-flow"`.
- Neither pass resolves the entry screen above the medium threshold —
  reason: describe what you searched and what you found (nav XML files
  scanned, `composable(...)` routes seen, classes matched).
- A `NavHost` is present but its route graph references sealed-class
  constants that cannot be resolved to literal strings — reason: name the
  unresolvable constants and suggest the user pass `--old-flow` with the
  concrete starting route.

## 02 Code inventory

Android has three surface kinds and one hybrid — the inventory must cover
all four. Use the same **Discovery -> Focused-reads -> Cross-linking**
phases; the concrete patterns are below.

### Surfaces (what to grep for)

- **Pure Compose screens.** Anchor: `@Composable\s+fun\s+\w+Screen\b` and
  any Composable invoked directly from a Compose-Nav `composable(...)` lambda.
  Set `source.surface: "compose"`.
- **Fragment + XML layout screens.** Anchor:
  `class\s+\w+\s*:\s*(Fragment|BottomSheetDialogFragment|DialogFragment)`.
  These pair with `setContentView(R.layout.<name>)`, `onCreateView` inflating
  `R.layout.<name>`, or a ViewBinding class named `<Name>Binding`. Set
  `source.surface: "xml"`.
- **Activity screens.** Anchor:
  `class\s+\w+\s*:\s*(AppCompatActivity|FragmentActivity|ComponentActivity)`.
  Inherit the same XML / Compose / hybrid detection as Fragments.
- **Hybrid ComposeView hosts.** Anchor: `\bComposeView\b` or `setContent\s*{`
  inside a Fragment / Activity body. These are two rows — the host (Fragment
  or Activity, surface `xml` or `compose`) AND the inner Composable (surface
  `compose`). Cross-link them with `parent_id` and set the host's
  `source.surface: "hybrid"`. When emitting the two rows, tag them with a
  `hybrid-host:<layout-or-class-id>` marker in `notes` so stage 2c's
  cross-link pass can pair them.

### State containers

- **ViewModel.** Grep `class\s+\w+ViewModel\b` or `:\s*ViewModel\(`. Record
  each ViewModel as a state row parented to its owning screen.
- **StateFlow / SharedFlow.** Grep `MutableStateFlow`, `asStateFlow()`,
  `StateFlow<`, `SharedFlow<`. Each distinct flow field is a candidate state.
- **LiveData.** Grep `MutableLiveData`, `LiveData<`. Older screens still use
  this; treat identically to StateFlow.
- **SavedStateHandle.** Grep `SavedStateHandle` and `savedStateHandle.get(`.
  Rows backed by `SavedStateHandle` survive process-death — tag with
  `hotspot: {"type": "process-death", "question": "Does this row's post-restore appearance match the Figma?"}`.
- **sealed class UiState / State.** Grep
  `sealed\s+(class|interface)\s+\w*(UiState|State)\b`. Enumerate the
  subclasses (`Loading`, `Error`, `Content`, `Empty`, ...) as distinct
  state rows.

### Actions

- **Compose click handlers.** Grep `\.clickable\s*{`, `onClick\s*=\s*{`,
  `onValueChange\s*=`, `\.combinedClickable\b`, `detectDragGestures`,
  `detectTapGestures`.
- **XML click handlers.** Grep `setOnClickListener\s*{`, `setOnLongClickListener`,
  `android:onClick="`. Pair with the view id that owns the listener.
- **Swipe / refresh.** Grep `SwipeRefreshLayout`, `SwipeToDismiss`,
  `pullToRefresh`.
- **Form submits.** Grep `setOnEditorActionListener`, `onSubmit\s*=`,
  `KeyboardActions\(`.
- **Nav triggers.** Grep `navController\.navigate\(`, `findNavController\(\)\.navigate`,
  `navigate\(route\s*=`. Record the destination each action reaches.

### Fields

- **Compose text/image.** Grep `Text\(`, `Image\(`, `Icon\(`, `AsyncImage\(`,
  `Coil`, `Glide`. Record the string / resource / state each reads.
- **XML fields.** Grep in layout XML for `<TextView`, `<ImageView`, `<Button`,
  `<EditText`, `<Switch`, `<CheckBox`. Record each `android:id` and the
  `android:text` / `android:src` it renders.
- **RecyclerView rows.** Grep `class\s+\w+ViewHolder\b`, `onBindViewHolder`,
  `getItemViewType`. A single RecyclerView with multiple view types yields
  multiple field rows — tag each with
  `hotspot: {"type": "view-type", "question": "Which view-type variant does the Figma frame represent?"}`.
- **Compose content blocks.** The body of any `@Composable` is a container
  of fields; emit one row per semantically distinct UI element rendered from
  state (not per Composable call — `Row { Text(); Text() }` is two fields,
  one Row).

### Hotspots (tag during discovery)

Set `hotspot` on any row whose anchor implies a runtime branch stage 3 will
need to resolve. `hotspot` is an object `{"type": "<enum>", "question": "<prompt>"}` per `inventory_item.json`; the `type` values below are the full accepted enum (`feature-flag`, `permission`, `server-driven`, `config-qualifier`, `form-factor`, `process-death`, `view-type`, `viewpager-tab`, `sheet-dialog`).

- `feature-flag` — match `FeatureFlags`, `Flags\.`, `isEnabled\(`, `FlagKey`,
  or whatever pattern the host repo actually uses. Discover the repo's own
  helper names by grepping at stage start; do not hard-code. Example emission: `{"type": "feature-flag", "question": "Is flag X on/off for the flows you care about?"}`.
- `permission` — `checkSelfPermission`, `registerForActivityResult\(.*RequestPermission`. Example: `{"type": "permission", "question": "Assume permission X is granted — is there a denied-branch design?"}`.
- `server-driven` — fields populated from `Retrofit` / `OkHttp` responses,
  list adapters backed by paged network data. Example: `{"type": "server-driven", "question": "What variants of response field X does the backend actually return today?"}`.
- `config-qualifier` — branches that read `Configuration.uiMode`, resources
  under `values-night/`, `values-ldrtl/`, `values-sw600dp/`. Example: `{"type": "config-qualifier", "question": "Which qualifier is in scope for the Figma frame?"}`.
- `form-factor` — `resources.configuration.smallestScreenWidthDp`,
  `isTablet()` helpers. Example: `{"type": "form-factor", "question": "Phone or tablet layout?"}`.
- `process-death` — state backed by `SavedStateHandle`.
- `view-type` — RecyclerView with multiple `getItemViewType` branches.
- `viewpager-tab` — `ViewPager2` + `FragmentStateAdapter` where tabs are
  data-driven.
- `sheet-dialog` — `BottomSheetDialog`, `DialogFragment`, `showSheet`,
  `show(supportFragmentManager`, with multiple state variants.

### Cross-linking

- Every nav destination (from stage 1) must resolve to a screen row. If it
  does not, append an entry to `unwalked_destinations`:
  `{ "nav_source": "<nav xml filename>", "target": "<short class name>",
  "reason": "class not found" }`. Never silently drop.
- Hybrid ComposeView hosts: set the host's `source.surface: "hybrid"`; make
  the inner Composable row's `parent_id` point to the host Fragment / Activity.
- Orphaned rows (`parent_id` set but parent missing from `items`) must
  survive to the renderer — do not delete.
- If no target-flow class or Composable can be opened at all, refuse with
  a structured error in the inventory.

## 03 Clarification

Hotspot topics to ask about when present in the inventory:

- **Feature flags** — name each flag pattern found (e.g., `FeatureFlags.NEW_BOOKING_FLOW`);
  for each flagged branch, confirm the current default in the environment
  the design targets (prod / staging / rollout percentage).
- **Runtime permissions** — camera, mic, location (fine/coarse), notifications,
  contacts, storage; confirm the permission-denied and never-ask-again paths
  are covered in the Figma.
- **Server-driven content** — list items, screen content, or field values
  populated from network responses; confirm the expected response shape and
  which variants the design covers (empty, single, many, error).
- **Config qualifiers** — `values-night/` (dark mode), RTL (`values-ldrtl/`),
  `sw600dp/` (tablets), density qualifiers (`hdpi` / `xhdpi` / `xxhdpi`);
  confirm which qualifiers the design explicitly covers.
- **Phone / tablet branches** — if the code branches on
  `smallestScreenWidthDp` or uses `sw600dp` resources, confirm both layouts
  are in the Figma file.
- **Process-death restore** — `SavedStateHandle` survives process death;
  confirm the design's restore state (what renders after the OS kills and
  resumes the process) matches the post-restore code path.
- **RecyclerView view types** — for each adapter with multiple
  `getItemViewType` branches, list the viewTypes and confirm the design
  covers every one.
- **ViewPager2 tabs** — when tabs come from `FragmentStateAdapter` with a
  data-driven item count, confirm which tabs the Figma covers and whether
  dynamic tab counts are in scope.
- **BottomSheet / Dialog state variants** — collapsed vs expanded,
  loading vs loaded vs error vs empty; confirm the design covers each
  state of every sheet and dialog in the flow.
