---
name: ios
detect:
  - "**/*.xcodeproj"
  - "**/*.xcworkspace"
  - "Package.swift"
description: iOS (UIKit + SwiftUI + ObjC) hint. Ported from MindBodyPOS #5349.
confidence: high
---

## 01 Flow locator

Search the iOS source tree (typically `Sources/`, `App/`, or the product-named
root such as `MindBodyPOS/`). Skip `Pods/`, `Carthage/`, `DerivedData/`,
`.build/`, `fastlane/`, and any `*.generated.swift` output.

**Entry-screen matching — name correspondence in priority order.**

1. Exact class-name match against the Figma entry frame. Grep for
   `class <Name>ViewController`, `class <Name>ViewModel`,
   `class <Name>Coordinator`, `struct <Name>View:\s*View`, and
   `struct <Name>Screen:\s*View`. `*Coordinator` and `*FlowController`
   classes are the strongest anchor for multi-screen flows — prefer them
   over a single `ViewController` when both exist.
2. Storyboard ID match. Grep `*.storyboard` and `*.xib` for
   `storyboardIdentifier="<Name>"` or `customClass="<Name>ViewController"`.
   If the hit is storyboard-only with no corresponding `.swift` class, drop
   to step 3 — do not anchor the flow on a storyboard file alone.
3. Fuzzy token overlap. Split the Figma name on camel-case / spaces and
   match against file basenames (`AppointmentDetails` matches
   `AppointmentDetailsViewModel.swift`). Weight class names above file
   names.
4. When `old_flow_hint` is set, weigh the hint above fuzzy matches but
   below exact class-name matches — an exact hit on the Figma name is
   still the best signal.

**Navigation walking — iOS idioms to follow.**

- **UIKit imperative pushes/presents.** Grep the entry screen and its
  coordinator for:
  - `navigationController?.pushViewController(`
  - `.present(`, `.presentModal(`, `showDetailViewController(`
  - `performSegue(withIdentifier:`
  - `self.show(`, `self.showDetailViewController(`

  The argument to each is the next destination. Resolve it to a class and
  recurse.
- **Coordinator destinations.** If the flow uses a coordinator, find the
  destination enum (commonly `enum Destination`, `enum Route`, or
  `enum <Flow>Step`) and enumerate every case. Each case is a reachable
  screen. Follow `navigate(to:)` / `route(to:)` / `start(_:)` dispatch
  methods to the concrete view controller factory.
- **Storyboard segues.** Open the `.storyboard` XML for the entry scene,
  enumerate every `<segue>` element, and resolve each `destination=` UUID
  to its scene's `customClass`. Manual segues (`performSegue`) also count —
  grep for their identifiers.
- **SwiftUI navigation.** Grep for:
  - `NavigationLink(destination:`, `NavigationLink(value:`
  - `NavigationStack { ... .navigationDestination(for:`
  - `.sheet(isPresented:`, `.sheet(item:`
  - `.fullScreenCover(`
  - `.popover(`
  - `TabView { ... }` (each tab is a destination)

  `navigationDestination(for: Route.self)` paired with an enum is the
  SwiftUI equivalent of the coordinator pattern — enumerate the enum
  cases.
- **Hybrid hosts.** `UIHostingController(rootView: <SwiftUIView>)` embeds
  SwiftUI inside UIKit. Treat both the hosting controller and the
  SwiftUI root as one logical screen — record the hosting controller as
  the code anchor and note the SwiftUI view in the evidence.
  Conversely, `UIViewControllerRepresentable` embeds UIKit inside
  SwiftUI; follow it to the wrapped VC.

**Refuse-loud conditions specific to iOS.**

- **Storyboard-only flow with no code anchors.** If every scene in the
  target storyboard has `customClass=""` or inherits straight from
  `UIViewController` with no Swift subclass, halt stage 1 — there is
  nothing to inventory. Tell the user to provide `--old-flow <hint>`
  pointing at a code anchor (a view model, a presenter, a coordinator),
  or to rename Figma frames to match existing symbol names.
- **Generated-only code.** If the only matches are inside
  `*.generated.swift`, `R.generated.swift` (R.swift), or
  `*+Generated.swift`, halt — generated files are outputs, not sources
  of truth.

## 02 Code inventory

**Screen declarations — discovery grep patterns.**

- `class\s+\w+\s*:\s*(UIViewController|UITableViewController|UICollectionViewController|UIPageViewController|UISplitViewController|UINavigationController|UITabBarController)`
- `struct\s+\w+\s*:\s*View\b` (SwiftUI)
- `class\s+\w+Coordinator\b`, `class\s+\w+FlowController\b`,
  `class\s+\w+Router\b`
- `class\s+\w+Presenter\b`, `class\s+\w+ViewModel\b` (record alongside
  the VC / View they drive, not as separate screens)
- Objective-C: `@interface\s+\w+\s*:\s*UIViewController`

Every match is a candidate screen. Merge UIKit+SwiftUI hybrid hosts: a
`UIHostingController` whose `rootView` is a SwiftUI `struct ... : View`
is one logical screen with two files — record the hosting controller as
the primary and cite both.

**State containers — where render modes live.**

- UIKit view-model properties exposed through bindings:
  - `@Published var <name>` (Combine)
  - `var <name>: AnyPublisher<_, _>`
  - `let <name> = CurrentValueSubject<_, _>(...)`
  - `let <name> = BehaviorRelay<_>(...)` (RxSwift)
  - `@Observable class` / `@ObservationTracked` (Observation framework)
- SwiftUI local and shared state:
  - `@State`, `@Binding`
  - `@StateObject`, `@ObservedObject`, `@EnvironmentObject`
  - `@Environment(\.<keypath>)`
  - `@FocusState`, `@SceneStorage`, `@AppStorage`
- Enumerated render modes — scan the VC / View body for branches:
  - `if viewModel.isLoading { ... }` → state `"Loading"`
  - `if let error = viewModel.error { ... }` → state `"Error"`
  - `if items.isEmpty { ... }` → state `"Empty"`
  - `switch state { case .loading: ...; case .loaded(let x): ...; case .error: ... }`
    → one state per enum case
  - `if !staff.canEditAppointments { ... }` → state
    `"Permission-denied"`, record `metadata.permissions`
  - `if featureFlag.isEnabled(.newX) { ... } else { ... }` → record both
    branches as distinct states AND a `feature-flag` hotspot

**Actions — user-triggered events.**

- `@IBAction func <name>(_ sender:` — Interface Builder hooks
- `<button>.addTarget(self, action: #selector(<name>), for:` — target-action
- `UITapGestureRecognizer`, `UIPanGestureRecognizer`,
  `UISwipeGestureRecognizer` — gesture recognizers
- `Button(action: { ... })` and `Button("Title") { ... }` — SwiftUI
- `.onTapGesture { ... }`, `.onLongPressGesture { ... }`, `.onSubmit { ... }`
- `NavigationLink(destination: ...) { Label(...) }` — navigation + action
- `.swipeActions { Button(...) { ... } }` — List row swipes
- `.toolbar { ToolbarItem(...) { Button(...) } }` — nav-bar / toolbar actions

Follow each action's closure or selector to the handler to learn the
destination; feed that back into navigation walking in stage 1 scope.

**Fields — data rendered to the user.**

- UIKit assignments: `<outlet>.text =`, `<outlet>.attributedText =`,
  `<outlet>.image =`, `<outlet>.tintColor =`, `<outlet>.isHidden =`
- `@IBOutlet weak var <name>:` declarations — each outlet is a field
  candidate; record the one where `.text` / `.image` is set from model
  data.
- SwiftUI body content: `Text(<expr>)`, `Image(<expr>)`,
  `Label(<title>, systemImage:)`, `AsyncImage(url:)`, `SecureField(...)`,
  `TextField(..., text: $...)`, `Toggle(..., isOn: $...)`
- Table/collection data sources:
  - UIKit: `tableView(_:cellForRowAt:)`, `collectionView(_:cellForItemAt:)`,
    and any `configure(with:)` or `setup(model:)` cell method — enumerate
    every field set on the cell (`cell.titleLabel.text = model.name`,
    etc.)
  - Diffable data sources: `UICollectionViewDiffableDataSource`,
    `UITableViewDiffableDataSource` — the cell-provider closure is the
    equivalent of `cellForRow`.
  - SwiftUI: `List(items) { item in Row(item) }`, `ForEach(items) { ... }`
    — follow the row view's body.

**Hybrid hosts — recognize and merge.**

- `UIHostingController(rootView: SomeSwiftUIView())` — UIKit shell
  around SwiftUI. Cite both `*.swift` files on the single screen item.
- `UIViewControllerRepresentable` / `UIViewRepresentable` — SwiftUI
  shell around UIKit. Follow `makeUIViewController(context:)` to the
  wrapped VC; merge as above.
- XIB-backed VCs: `init(nibName:bundle:)` with a matching `.xib` —
  the XIB's outlets are the field roster; cross-link `@IBOutlet`
  declarations against it.

**Hotspots to record alongside inventory items.**

Each emission must match the shared `inventory_item.json` schema — a
non-null `hotspot` is an object `{"type": "<enum>", "symbol": "<identifier>"}`.
The `symbol` is the concrete identifier that distinguishes this hotspot
from siblings of the same type — the flag name, permission name, cell
class name, etc. Stage 03's question registry uses `symbol` as the
dedup key and substitutes it into the canonical prompt template. You
MAY add an optional `"question": "..."` field to suggest prompt text,
but the registry is the source of truth — it will be ignored unless a
platform override hooks it in. Use these mappings from iOS patterns to
the schema's `hotspot.type` enum:

- `feature-flag` — any branch keyed on `FeatureFlagType`,
  `FeatureFlagManager`, `ImplementationSwitch`, `RemoteConfig`,
  or `LaunchDarkly`. Emit `{"type": "feature-flag", "symbol": "<flagName>"}`
  (e.g., `"isAppointmentDetailsNewDesignEnabled"`).
- `permission` — `if staff.can*`, `if user.hasRole(`,
  `AVCaptureDevice.authorizationStatus(`, `CLLocationManager` auth,
  `UNUserNotificationCenter` requests, `PHPhotoLibrary` requests.
  Emit `{"type": "permission", "symbol": "<permissionName>"}`
  (e.g., `"staff.canEditAppointments"`, `"camera"`).
- `server-driven` — `for item in response.items`,
  `UICollectionViewCompositionalLayout` with dynamic section provider,
  any cell type chosen by a runtime `switch` on a server enum.
  Emit `{"type": "server-driven", "symbol": "<sectionOrFieldName>"}`.
- `view-type` — `tableView.dequeueReusableCell` with an identifier
  chosen at runtime, or a cell-provider closure that branches on item
  type; also `UIHostingController` or `UIViewControllerRepresentable`
  variants whose wrapped view is chosen at runtime; also any
  `switch` / `if-else` on a status or state enum (e.g., appointment
  status Booked/Confirmed/Arrived/…) that renders a different UI
  per case — treat each case as a candidate state row whose presence
  in Figma stage 5 can verify.
  Emit `{"type": "view-type", "symbol": "<cellClassOrEnumCase>"}`
  (e.g., `"MBOApptDetailCheckoutCell"`).
- `form-factor` — compact vs regular `horizontalSizeClass`, iPhone vs
  iPad layout branches, `UIDevice.current.userInterfaceIdiom`.
  Emit `{"type": "form-factor", "symbol": "<branchName>"}`.

The schema's enum also accepts `config-qualifier`, `process-death`,
`viewpager-tab`, `sheet-dialog`; only `process-death` has a clear iOS
analogue (state-restoration flows via `NSUserActivity` / `restorationID`
/ `SceneDelegate.stateRestorationActivity`). Emit those when the iOS
pattern cleanly matches; otherwise prefer the five above.

## 03 Clarification

Hotspot topics to ask about when present in the inventory:

- **Feature flags** — search for `FeatureFlagType`, `FeatureFlagManager`,
  `ImplementationSwitch`, `RemoteConfig`, `LaunchDarkly`; for each flagged
  branch, confirm which variant the current default is and which the
  Figma represents.
- **Server-driven content** — lists or sections populated from a network
  payload (`response.actions`, `response.items`, `response.sections`);
  confirm the expected shape and which variants are in scope.
- **Permission gates** — push (`UNUserNotificationCenter`), camera
  (`AVCaptureDevice`), microphone, location (`CLLocationManager`),
  photo-library (`PHPhotoLibrary`), contacts, calendar, HealthKit; for
  each, confirm the permission-denied path has a design or is explicitly
  out of scope.
- **Staff / role permissions** — `staff.canEditAppointments`,
  `user.hasRole(.manager)`, and similar role checks. Batch these when
  multiple gates differ only by which permission they check — ask one
  blanket question ("assume all listed staff permissions are granted
  unless you say otherwise — any exceptions?").
- **Device / size-class branches** — compact vs regular
  `horizontalSizeClass`, iPhone vs iPad layout branches,
  `UIDevice.current.userInterfaceIdiom`, landscape vs portrait,
  Dynamic Type size; confirm intended behaviors on each axis.
- **Appearance / theme branches** — `colorScheme == .dark`,
  `traitCollection.userInterfaceStyle`; confirm dark mode is in scope
  and which Figma frame represents it. When dark mode IS in scope,
  emit inventory items with `modes: ["light", "dark"]` (one row per
  logical item, not one per appearance) — stage 5 will verify each
  mode on the same row instead of counting them as two separate
  rows. When dark mode is explicitly out of scope, emit
  `modes: ["light"]` so the comparator can skip dark-mode figma
  frames with `status: "new-in-figma"` severity `info` automatically.
- **A/B test hooks** — if present; confirm which variant the Figma
  represents and whether the other variant also needs a coverage pass.
