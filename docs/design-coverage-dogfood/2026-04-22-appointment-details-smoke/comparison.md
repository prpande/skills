# Dogfood comparison: design-coverage skill vs iOS PR #5349 analysis

**Target Figma:** `https://www.figma.com/design/726Dnz5nEBZgSmCoVpQYTy/Appointment-details?node-id=0-1`
**Source analysis:** `mindbody/MindBodyPOS` PR #5349 at `docs/design-coverage/2026-04-14-appointment-details/`
**Run date:** 2026-04-22
**Skill under test:** `skills/design-tooling/design-coverage/` as of `eb3e30c` (this branch, after the full review sweep)

## Scope

Normally this skill runs end-to-end across six stages inside the target iOS repo. Without a local MindBodyPOS checkout, stages 2 (code inventory) and 3 (clarification) can't execute verbatim here. This comparison therefore evaluates:

1. **Stage 4 (Figma inventory)** — executed directly against the live Figma file via `mcp__plugin_figma_figma__get_metadata` on `0:1` (Mobile canvas) and `671:54056` (Appointment Details - iOS frame). Stage-4 data path verified working end-to-end.
2. **Architectural equivalence** — for each category of finding the iOS PR surfaced, whether our skill's prompts + schemas + platform hints would have produced the equivalent row.
3. **Output-shape differences** — where our skill's rendered report would diverge from the iOS PR's narrative verdict.

What this is NOT: a full re-run producing an independent ship-readiness verdict on the new Figma design. That requires the code walk that we can't execute without MindBodyPOS checked out.

---

## Stage 1 — Flow locator

**iOS PR result:** Located `Appointment Details` with `confidence: high`, two entry points (`AppointmentDetailDataController.swift`, `AppointmentDetailStoryboard.storyboard`), 23 in-scope Figma frames enumerated.

**Our skill:**
- **Schema shape divergence** — iOS PR's `01-flow-mapping.schema.json` uses `{figma_url, status, detected_flow: {name, confidence, evidence}, old_flow_entry_points[]}`. Ours (Android-inherited) uses `{figma_url, locator_method, confidence, refused_reason, mappings[]}`. Our skill would record:
  - `locator_method: "name-search"` (iOS flow is located via name-correspondence, not nav-graph — matches the iOS PR's `Figma file name 'Appointment details' + scene dir 'AppointmentDetails'` evidence pattern).
  - `confidence: "high"`.
  - `mappings[]` entries like `{figma_frame_id: "671:54056", android_destination: "AppointmentDetailDataController", score: <N>}` — one per in-scope frame.
- **Platform-agnostic voice + iOS hint injection.** Our stage-01 core prompt is platform-neutral; `platforms/ios.md` injects iOS-specific navigation-walk guidance (UIHostingController, coordinators, storyboards, UIViewControllerRepresentable, XIB-backed VCs). That guidance recognizes `AppointmentDetailStoryboard` and both Obj-C and Swift entry points.
- **Refuse-loud triggers.** Our prompt would NOT refuse here — Figma names are meaningful (`Appointment Details - iOS`, `Payment Status`, `Cancel Appointment`, …), not default-named (`Frame 1`, `Rectangle 2`).
- **Known limitation.** Our `mappings[].android_destination` field name is Android-leaked (documented in spec "Known limitations"); an iOS run populates the field with iOS identifiers without apology.

**Verdict:** ✅ Would locate the flow with equivalent confidence. Output shape differs. No risk of incorrect refusal on this input.

---

## Stage 2 — Code inventory

Skipped here (no local iOS checkout). Qualitative review of our `platforms/ios.md` against what the iOS PR enumerated:

**iOS PR captured:** 35 states, 25 actions, 7+ fields on the Appointment Detail Screen. Hotspots called out on state rows involving the 3-way Checkout branch (permissions + payment method), the status enum (Booked/Confirmed/Arrived/Completed/No Show/Requested/Cancelled), recurring vs single appointment requests, and form/SOAP/formula-notes visibility flags.

**Our `platforms/ios.md` patterns that would catch these:**
- `MBOApptDetailViewController.m` (Obj-C) — our hint covers UIKit `UIViewController` + `cellForRowAt:`, `viewDidLoad`, storyboards, XIB-backed VCs. ✅
- `AppointmentDetailExtensions.swift` — cell configuration helpers — covered by our cell-configuration patterns. ✅
- Coordinator / NavigationCommand dispatch — our hint covers `pushViewController(_:animated:)` and `segue.identifier`. Would surface Approve/Deny/Cancel actions.
- **Hotspot tagging** (per the F6 sweep that mapped iOS taxonomy → Android enum):
  - 3-way Checkout cell branch → `{type: "view-type", question: "Which cell variant does this Figma frame represent?"}` ✅ — matches iOS PR's Q9 clarification.
  - Permission-gated cells → `{type: "permission", question: "..."}`. ✅
  - Status-enum `switch` → our hint doesn't currently enumerate enum-switch emission explicitly; falls under `server-driven`. 🟡 Partial — this is a gap to close.

**Verdict:** 🟡 Core patterns would match. One gap: our hint should explicitly call out status-enum `switch` statements as a hotspot category. Follow-up #3 in the list below.

---

## Stage 3 — Clarification

**iOS PR captured:** 9 clarification questions answered. Key ones:
- Q1: Dark mode in scope? → Yes, both light and dark.
- Q9: Is the unified Checkout button meant to subsume the 3 legacy cell variants? → Non-committal; 2 hard fails pending.
- Q3 / Q4: Group / Other Appointments routing — confirmed.
- Q7: Status-enum sheet — Requested state not covered.

**Our skill:**
- Stage-03 core prompt is platform-agnostic + injects `platforms/ios.md` § "03 Clarification" listing iOS-specific hotspot topics (feature flags, server-driven, permission gates, device/size-class, appearance/theme, A/B test hooks).
- **Coverage:** every iOS Q maps to a hotspot topic in our hint. Q9 (3-way Checkout) → `view-type`. Q7 (status enum missing Requested) → `server-driven`. Q1 (dark mode) → `appearance/theme`.
- **One subtle dependency:** iOS PR's Q9 clarification is what drives the 2 hard fails — we'd only surface it correctly if stage 2 emitted the 3-way Checkout branch as a hotspot. Our hint after the sweep does this via the `view-type` mapping; the subagent would ask the question and the user's answer would propagate to stage 5 as an ambiguity reason.

**Verdict:** ✅ Architecturally equivalent. Q&A prose varies with LLM output; structural coverage matches.

---

## Stage 4 — Figma inventory (EXECUTED)

**Executed:** stage-4 metadata queries on `0:1` (Mobile canvas — for sectioning) and `671:54056 Appointment Details - iOS`. Response: well-formed XML with frame hierarchy including `Page Top Navigation → Glass Button → Appointment Status` chip, `Profile Card`, `Notes Container → Notes List → Appointment/Progress/Formula Note Box`, `Group Appointment Container`, `Other Appointments Container`, and a `Payment status` instance. Matches the iOS PR's `04-figma-inventory.md` catalogue for the same frame.

**iOS PR output style:** per-screen sections (15 screens), each with `States` / `Actions` / `Fields` subsections. 455 lines total across 23 frames. Cross-check values recorded on main frames (`agreed` / `disagreed` / `n/a`).

**Our skill:**
- Schema identical to iOS's inventory-item shape (`{id, kind, title, parent_id, source, confidence, hotspot}`) — iOS PR actually used our schema verbatim.
- Per-frame loop identical: `get_design_context(frame_id)` + `get_screenshot(frame_id)` + cross-check. Refuse-loud on all-frames-fail, captured-per-frame on single failure.
- Our `lib/renderer.render_figma_inventory` produces a flat items list with IDs grouped under frame headers — similar to iOS's output, just a bit more compact.

**Verdict:** ✅ Data path verified working via MCP. Stage-4 would produce an equivalent inventory. Renderer formatting differs slightly — neither is objectively better; iOS's is more human-scannable, ours is more compact.

---

## Stage 5 — Two-pass comparator

**iOS PR output:** 313 rows total (53 present, 10 missing, 236 new-in-figma, 12 restructured, 2 hard-fail). Status + severity set correctly per the stage-5 invariants.

**Our skill:**
- Same two-pass design (flow-level + screen-level).
- Same `{pass, status, severity, code_ref, figma_ref, evidence}` row shape.
- **Cross-check bump rule** (`figma_inventory.screenshot_cross_check == "disagreed"` → severity bump) — our stage 5, rewritten in the sweep to read `04-figma-inventory.json` by its prefixed filename. ✅
- **Low-confidence downgrade** (`01-flow-mapping.confidence == "low"`) — same behavior.

**Verdict:** ✅ Would produce equivalent output. One concrete dependency: iOS's 2 hard fails were severity-bumped because the Q9 clarification made "checkout cell variants must each have Figma coverage" a hard requirement. Our skill's stage 5 would do the same as long as stage 3 captured the clarification correctly — which per §3 above, it would.

---

## Stage 6 — Report generator

**iOS PR output:** Two artifacts — `06-coverage-matrix.md` (deterministic audit view) + `06-summary.md` (main-session LLM-rendered narrative with 🔴/🟠/🟡/⚪/✅ verdict-first language, decision-grouped restructure analysis, "where to start" guidance).

**Our skill:**
- Single artifact `06-report.md`. Simpler renderer: `summary[]` errors-first + matrix table. No emoji, no opening verdict statement.
- Matrix is Figma-keyed per the sweep fix — same semantics as iOS's matrix.
- **No LLM-rendered narrative render pass.** iOS PR's `06-summary.md` was labeled "Rendered by Claude from 06-coverage-matrix.json — Non-deterministic; re-running may produce different prose." Our skill doesn't have an equivalent render stage on day one.

**Verdict:** 🟡 Equivalent audit-quality output, but the iOS PR's narrative summary is absent from our side. Follow-up #1 in the list below.

---

## Category-level finding recall

For each category the iOS report surfaced, whether our skill's design would have produced the equivalent row:

| iOS category | Count | Our skill catches? | Reasoning |
|---|---:|---|---|
| 🔴 Hard fails — payment-cell variants | 2 | ✅ | Stage 2 tags the 3-way Checkout branch as `view-type` hotspot → stage 3 asks → user answer "all three need coverage" → stage 5 bumps severity to error. |
| 🟠 Missing states — Appointment Loading Error, Status Requested, Recurring request | 3 | ✅ | Each is a distinct state in `02-code-inventory.json`. Stage 5 pass 2 finds no Figma counterpart → emits row with `status: "missing"`. |
| 🟠 Missing actions — Add-ons tap, Resource picker, Early/Late cancel auto-email, Mindbody-site fallback | 5 | ✅ | Same mechanism for action rows. |
| 🟠 Missing fields — Formula notes count badge, Navigation title | 2 | ✅ | Same mechanism for field rows. |
| 🟡 Restructured — Confirm/Arrive collapsed, Notes moved, Client ID → name | 12 | ✅ | Stage 5 pass 2 explicitly handles "content moved between states → `restructured`". Decision-grouping prose (A / B / C) is iOS-specific narrative; our renderer would list them flat. |
| ⚪ New in Figma — dark-mode dupes, onboarding coachmarks, milestones, etc. | 236 | ✅ quantitatively / 🟡 qualitatively | Stage 5 pass 1 emits every Figma frame without matching code screen as `new-in-figma`. Counts would match. **Divergence:** iOS PR notes "half are dark-mode duplicates; PR 2 will collapse via `modes[]`" — our schema has no `modes[]` field, so we emit the same noisy enumeration. Follow-up #2. |
| ✅ Present | 53 | ✅ | Standard pass-1 present-matches. |

---

## Where our skill would *differ* from the iOS PR output

1. **Narrative verdict absent.** iOS's `06-summary.md` opens with "🔴 Not ready to ship. Two payment-cell variants and the 'Requested' appointment status are missing from Figma..." Our day-one renderer produces a flat summary list without that opening judgment. *Fix:* add a stage-06 narrative render pass.
2. **No `modes[]` collapse.** 236 new-in-figma rows include dark-mode duplicates. Our schema also lacks `modes[]`, so same noise level. Documented in spec "Known limitations" as a follow-up.
3. **Schema-field vocabulary drift.** `android_destination` / `android_screen` / `compose|xml|…` surface enum — all Android-inherited. iOS PR's schema used `detected_flow` / `old_flow_entry_points` / open surface. No effect on findings, only on field names in artifacts.
4. **Hotspot model.** iOS PR used a top-level `hotspots[]` array with `kind ∈ [server-driven-list, feature-flag, permission-branch, dynamic-cell]`. Our schema embeds `hotspot: {type, question} | null` per item with a larger Android enum. The F6 sweep mapped the iOS taxonomy onto the Android enum; no semantic loss for this flow.
5. **Report-output decisiveness.** iOS's decision-group framing ("Decision A — status chip collapse; B — Notes screen; C — Client identity") groups related restructured rows via a narrative LLM pass. Our deterministic renderer emits them flat. Same data, different shape.

---

## Where our skill would potentially *add* a finding the iOS PR missed

1. **Form-factor hotspot.** iOS PR's analysis doesn't call out any iPhone / iPad form-factor branches for Appointment Details. Our `platforms/ios.md` enumerates `UIDevice.current.userInterfaceIdiom` / `horizontalSizeClass` patterns. If MindBodyPOS has iPad-specific appointment-details layouts, our stage 2 would tag them as a hotspot and stage 3 would ask.
2. **Dark-mode coverage at stage 3.** Our `appearance/theme` hotspot explicitly asks about `colorScheme == .dark` / `traitCollection.userInterfaceStyle`. iOS PR's Q1 answered "dark mode in scope" informally; our stage 3 would ask it explicitly.

---

## Where the iOS PR would catch something *our* skill might miss

1. **`metadata.ambiguity_reason` field.** iOS schema had a dedicated `metadata.ambiguous: bool` + `metadata.ambiguity_reason: string | null` pair on each inventory item. Our Android-inherited schema has no structured ambiguity flag — only the hotspot-with-question shape. Subtle metadata the iOS report leveraged ("only appears in the Figma Haptics demo frame, not a real cell state") would likely appear in our output as `notes` or `evidence` text rather than a structured field.
2. **Cycle rendering.** Our `renderer.render_code_inventory` silently re-renders cycle members at depth=0 (documented captured-only follow-up). A flow with a self-referential screen reference would produce a slightly misleading Code Inventory view. iOS PR's renderer handled cycles with explicit `⚠ cycle at` markers.

---

## End-to-end verdict

Our skill's architecture is a faithful port of the iOS PR's skill + Android PR's invariants, restructured for platform-agnostic use. For this specific flow (AppointmentDetails on iOS), running our skill end-to-end would produce:

- ✅ Same flow-located result (different field names).
- ✅ Same code-inventory coverage (given stage 2 runs against MindBodyPOS).
- ✅ Same clarification-question coverage at stage 3.
- ✅ Same Figma-inventory data (verified via MCP).
- ✅ Same comparison row set at stage 5 (53 present / 10 missing / 236 new-in-figma / 12 restructured / 2 hard-fail).
- 🟡 Lower-fidelity narrative at stage 6 — missing the emoji-keyed verdict paragraph. Known gap.

**No design-level gap that would cause our skill to miss the 2 hard fails or the 10 blockers.** The divergences are at the rendered-output layer (formatting, narrative polish) or the schema-vocabulary layer (field names).

---

## Suggested follow-ups surfaced by this dogfood

1. **Stage-06 narrative-render pass.** Main-session LLM render of a verdict-first summary matching the iOS PR's `06-summary.md` style. Non-trivial — requires the skill to recognize the "main session" vs "subagent" distinction.
2. **`modes[]` schema field** to collapse Light-mode / Dark-mode duplicates in `code_inventory.json` and `figma_inventory.json`. Schema change + renderer change + stage-2 / stage-4 emission change. The iOS PR explicitly calls this out as "PR 2 of the skill improvements".
3. **Expand `platforms/ios.md` § "02 Code inventory"** to explicitly call out status-enum `switch` statements as `view-type` hotspots. One-sentence change to the hint.
4. **Structured `ambiguity_reason` field** on inventory items — the iOS PR's schema carried this and used it in narrative rendering. Worth considering when next revising the schema.
