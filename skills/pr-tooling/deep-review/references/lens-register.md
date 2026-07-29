# Review lens register

The canonical rule set consumed by `deep-review` (all effort levels) and by
`pr-autopilot`'s preflight review. Each lens in *this file* is a repeatable
mistake class distilled from real review rounds — not a style guide. The
governing backend tier in `references/backend-lenses.md` is distilled instead
from production postmortems and published API-security guidance, and is held to
the admission rule in Maintenance.

## Precedence

1. **Universal lenses (`U`) always apply.**
2. **Backend production lenses always fire on a backend diff.** The tier in
   `references/backend-lenses.md` is not suppressible: a repo rule may *narrow*
   a finding — swap the prescribed remedy, name the repo's own helper — but may
   not remove the flag. The boundary is one test: a repo rule changes what you
   prescribe, never whether you report. Where a repo convention conflicts with a
   lens's remedy, report the defect and prescribe the repo's remedy. A lens whose
   subject does not exist in the system under review is inapplicable rather than
   suppressed — see the tier's header.
3. **Repo-defined conventions govern** everything below this line. Before
   applying any scoped pack, read the target repo's own rule sources:
   `CLAUDE.md` / `AGENTS.md` / `ARCHITECTURE.md`, any repo review skill or
   runbook under `.claude/skills/`, and per-directory convention docs. Where a
   repo rule and a scoped lens conflict, the repo rule wins — apply it and stay
   silent about the suppressed lens.
4. **Scoped packs are fallback suggestions.** Apply a pack only when the diff
   touches its trigger AND the repo has no rule of its own on that subject.

Findings cite lenses by id (`Lens U3`, `Lens TEN1`). A lens hit is a *candidate*
— verify context before reporting; quoted strings, test doubles, and generated
code false-positive.

## Backend production tier

`references/backend-lenses.md` holds the governing tier described in precedence
rule 2 — six groups, firing on a backend diff: the diff touches SQL or ORM
bindings or repository-layer code, an HTTP endpoint or route, a GraphQL
schema/resolver/loader, a message or event handler, a schema migration file, or
cache access.

| Prefix | Subject |
|---|---|
| `TX` | transaction boundaries and consistency |
| `IDM` | idempotency and delivery semantics |
| `TEN` | tenancy and scoping |
| `CA` | cache correctness |
| `MIG` | schema change under rolling deploy |
| `EXP` | exposure and resource bounds |

## Universal — always apply

- **U1 — Same-subject census before any new file.** This is a mechanical
  enumeration with a required output, not a judgment call. For every file the
  diff adds, run the whole search list and report what each returned — *even
  when the answer is "nothing exists"*, because a silent census is
  indistinguishable from one that never ran:
  1. the basename, unqualified, across the tree;
  2. `class <Name>` / `interface I<Name>` in every namespace or module;
  3. `<Subject>Tests` and any other test type naming the same subject;
  4. the concept the file owns, however it is spelled elsewhere (the entity,
     the table, the endpoint) — for a type fronting a collaborator, grep who
     else already injects that collaborator (`D1` for the repository case;
     report it under one id, not both).

  A same-named type in a different namespace/module compiles fine — that is
  exactly the trap. Extend the existing one, even if it lives in a legacy
  folder.
- **U2 — Shared logic goes on the existing owner.** When two flows need one
  rule, host it on the type that already owns the concept. Never mint a
  one-method extension/util class as a "shared home". Check dependency
  direction before proposing where it lives.
- **U3 — Constants live with the decision owner.** A constant belongs to the
  code that *acts on* the value, not to an exception/DTO that merely
  mentions it.
- **U4 — Reuse shared infrastructure.** Locking, error mapping, validation
  catalogs, pagination/batching helpers: grep for an existing shared seam
  before writing a bespoke variant.
- **U5 — Naming census per new public name.** Grep how the repo already names
  the concept and cite the concrete exemplar; align to the majority
  convention rather than inventing a parallel one. "Consistent with existing
  code" is a standing acceptance bar.
- **U6 — Name for the domain concept, and defensively.** If a parameter or
  member name invites misuse, rename at the definition — not with
  per-consumer aliases. A member is named after what it represents; an
  aggregation's name must match what it aggregates.
- **U7 — Comment minimalism.** Comments exist only for constraints the code
  cannot show (locking/transaction semantics, schema traps, contract pins,
  deliberate deviations). No narration, no restating the code, no
  reviewer-directed notes, and no provenance — external line citations, CI
  run ids, planning-doc references belong in commit messages. Applies to
  tests with full force: the test name carries intent. Stale comments
  referencing removed code and ticketless TODOs are findings.
- **U8 — Pre-existing defects don't ride feature PRs.** Unrelated fixes and
  cleanups go in a standalone PR. Exception: a tiny, clearly-labeled fix
  that unblocks this PR's own CI.
- **U9 — Split/stacked PRs: say where the fix landed.** A reviewer reads only
  the PR they were asked to review. When a fix lives in another PR or
  branch, reply on the original thread with the pointer immediately.
- **U10 — Loop-await is an N+1.** Any loop awaiting a per-item I/O call
  (repository, HTTP, cache) is a candidate for a set/range read.
- **U11 — Signature width.** More than four positional parameters → a request
  object/record.
- **U12 — Document deliberate omissions at the seam.** A knowingly-absent
  cancellation token, a deliberate no-op branch, an intentionally-skipped
  guard: one comment line at the definition saying it is deliberate,
  otherwise it reads as an oversight and draws a review thread.
- **U13 — PR scope discipline.** No reformatting of unrelated lines, no
  IDE-driven reshuffles, no "while I was here" cleanups mixed into a feature
  or carve-out PR. In a behavior-neutral PR, opportunistic fixes touch only
  lines the PR already rewrites.
- **U14 — Delete what the change made dead.** Tightening a type or contract
  must remove the now-dead guards, overflow checks, and bridging casts that
  existed only for the old shape.
- **U15 — Error-surface semantics are team decisions.** New status codes,
  error formats, or headers are not introduced unilaterally — check the
  repo's decision log or raise with the team first.
- **U16 — Magic values get named constants** owned by the acting code (a
  shared constant only when multiple owners genuinely exist).
- **U17 — Fix at the right depth.** A special case layered on shared
  infrastructure is a bandaid; prefer generalizing the underlying mechanism.
  Nested call-in-call chains and boolean/flag parameters spreading through a
  core method are the smell.
- **U18 — Entry points stay thin.** In a layered codebase, endpoints,
  resolvers, and other entry points map the request, call the domain
  service, and map the response. Business decisions ("load setting X, pass
  flag if true") belong inside the domain service; orchestration across
  multiple data sources belongs in a service, not in a data component
  wrapping another.
- **U19 — Two-state semantics are an enum, not a bool.** If explaining what
  true and false each mean takes a paragraph, model it as an enum — and
  never name a bool after its storage quirk. Escalate once the bool would
  reach a domain or API contract.
- **U20 — Every new construct earns its existence.** Most lenses ask whether
  something is built correctly. This one asks whether it should be there at
  all, because a construct that is present, correct and unnecessary is
  invisible to every other lens. For each type, interface, provider, wrapper,
  extension class, attribute or constant the diff adds, count its production
  call sites (`grep` the name, excluding its own declaration and its own
  tests) and answer one question in the finding: **what breaks if this is
  deleted and its body inlined at those call sites?** Report when any holds:
  - **one caller.** A type with a single production consumer is that
    consumer's private detail. In a shared location (`Domain/`, `Common/`,
    `Shared/`) the bar is two *distinct calling types* — an extraction with
    one consumer is speculative. This is the deliberate counterweight to U2:
    U2 pulls shared logic onto an existing owner, U20 pushes back when there
    is nothing yet to share.
  - **pass-through.** Every member forwards to one collaborator and adds no
    logic, no mapping, and no policy.
  - **unobserved observability.** A metric, log attribute or trace field with
    no alert, dashboard, or runbook named in the diff or findable in the repo.
    Telemetry nobody watches is not a signal, and its cost is real. When the
    alerting layer is not in the working tree at all — it lives in a vendor
    console, a wiki, or another repository — say so and state what would
    confirm coverage, rather than asserting the telemetry is unwatched.
  - **dead on arrival.** Introduced with no reachable caller and no test
    exercising it.

  *Not a finding when:* the construct implements a published interface or
  framework contract, or a second consumer arrives in a named, in-flight
  change — say which.

## Pack: tests — trigger: any test file in the diff

- **T1 — Assert at the highest seam that observes the behavior.** Default to
  the repo's highest-level test style (behavioral/spec through the real
  entry point, mocking only true externals). If a higher-level test
  exercises the code, a lower-level duplicate adds nothing — pick one and
  delete the other.
- **T2 — No proxy tests.** A test that mocks X and asserts X was called pins
  the mock, not behavior, and becomes merge friction on every signature
  change. Justified only for complex logic unreachable from a higher seam.
  Needing a coverage-exclusion attribute on members a test never exercises
  is the tell that the mock sits at the wrong level — mock lower instead.
- **T3 — Data-layer behavior needs the real engine.** Repository/SQL behavior
  is verified by contract/integration tests against a live database, never
  by mocked unit tests. Keep them lean: cover the SQL shapes, not every
  parameter combination.
- **T4 — No coverage-filler tests.** Don't write a test whose only purpose is
  a coverage gate; raise the exclusion question with the lead instead.
- **T5 — Mirror the nearest existing test pattern.** Use the established base
  class/fixture for the test type; re-rolling plumbing the base owns is a
  finding. Add to the existing test class for a component — a second
  parallel class for the same subject is a smell.
- **T6 — Wiring-proof per net-new input.** Every new filter/field/parameter
  needs a test proving the value actually reaches the query/service — a
  hardcoded value must fail it.
- **T7 — Strong negative controls.** Assert the expected value, not merely
  "not the old value"; untouched-record checks compare full snapshots, not
  one field.
- **T8 — Parameterize near-identical tests, and count the cost of the tier.**
  Two tests differing only in one input belong in one parameterized case. In a
  slow tier (contract, integration, E2E, browser) the case count is itself a
  design fact — every added case is a recurring tax on CI feedback time, and on
  the whole team wherever that tier also runs on a local build. Count the cases the
  diff adds to a slow tier, and report when two differ only in seed data and
  could share one seeded row, or when a case duplicates coverage a faster tier
  already provides.
- **T9 — No shape-only tests.** Don't assert that a member/attribute merely
  exists when a behavioral test already fails on contract change.
- **T10 — Never depend on machine-local time, zone, or culture.** Pin a fixed
  timezone, clock, and culture; "passes locally, fails in CI" is the symptom.
- **T11 — Test names track behavior.** Follow the repo's naming shape
  (Given/When/Then or equivalent) and update the name whenever the pinned
  behavior changes — a stale display name misdocuments the suite.
- **T12 — Reflection in a test means the wrong layer.** If a test needs
  reflection to observe behavior, mock at a different (usually lower) level
  instead of prying the object open.
- **T13 — Side-effecting E2E tests are a stability risk.** A test that
  creates real external resources blocks every subsequent run when cleanup
  fails; make cleanup bulletproof, provide a skip mechanism, or push the
  validation down to a test tier without real side effects.
- **T14 — Exercise real collaborators when it's cheap.** Prefer a real
  parser/mapper/context over mocking its interface so the real path gets
  coverage — and don't add test complexity for a theoretical concern with
  no observed failure.

## Pack: wire-contracts — trigger: public API surface, shared client packages, serialized DTOs

- **W1 — Breaking-change check on every contract touch.** Paths, response
  fields, enum members, exception→status mappings, client package
  properties, parameter order: always call out the compat impact explicitly.
  Changing which exception a method throws is a contract change if the
  mapping differs.
- **W2 — No defaults baked into shared client packages.** Properties nullable
  with no default; the consuming edge resolves defaults. A baked-in default
  locks every consumer forever.
- **W3 — Never insert a parameter before an existing trailing
  token/options parameter.** Positional callers rebind silently. Append
  after it, or add an overload.
- **W4 — Verify the serializer honors the attribute.** Mixed serializer
  stacks ignore the wrong attribute family silently; confirm which
  serializer the project actually uses before copying nearby patterns.
- **W5 — Don't emit wire surface the consumer stack ignores.** Verify actual
  client behavior before adding headers/fields.
- **W6 — Don't stack resilience layers.** Check what the base client already
  does; a second retry policy multiplies attempts against the upstream.
- **W7 — One home per contract.** Add fields by updating the shared contract
  package, not by introducing a local wrapper/request model beside it.
- **W8 — Typed error codes.** Exceptions surfaced across the wire carry a
  strongly-typed code (enum), never free text; each distinct failure gets
  its own accurate code.
- **W9 — Tighten shared-DTO nullability only after a full census.** Declare
  a field non-nullable only when it is truly populated for *every* type the
  shared DTO represents; otherwise keep it nullable and document which
  types populate it. Loosening later is a breaking change.

## Pack: http — trigger: endpoints, routes, request/response handling

- **H1 — 204 for intentionally empty responses.** A 200 with an empty body
  confuses clients about whether more data might come.
- **H2 — POST for actions, PATCH for partial state.** An endpoint that
  executes business logic (sign-in, mark-arrived) is `POST
  /resource/{id}/action`; PATCH implies "merge this partial state".
- **H3 — No custom `X-`-prefixed headers.** RFC 6648 deprecates the prefix;
  prefer standard names (`Correlation-Id`, `Idempotency-Key`) so the
  mechanism stays reusable across endpoints.
- **H4 — Cross-field rules live in the request validator.** "A or B must be
  set" belongs in the validation layer so the client gets a 400 naming the
  property — not a bare service-thrown error with no detail.

## Pack: data-access — trigger: SQL, ORM bindings, repository-layer code

- **D1 — One repository owns one table, and one front door owns the
  repository.** Cross-table writes go through the owning repository,
  orchestrated by a service. A second repository/provider writing a table
  another one owns is an architecture finding that needs explicit sign-off,
  not a local convenience. The same rule applies one layer up: before adding a
  provider, service or facade over a repository, `grep` for who already
  injects that repository's interface — if a front door exists, the new method
  belongs on it. Two providers over one repository is the same defect wearing
  a different hat, and it is usually argued for on grounds that do not survive
  ("it must run in the transaction", "it stays out of the shared surface") —
  check whether the existing owner already takes the same connection or scope
  before accepting either.
- **D2 — Data-access statements live only in the data layer.** No SQL in
  providers/services/endpoints; move it down and call the method.
- **D3 — Ownership check per statement.** Which module/domain owns that
  table? Cross-domain access goes behind a contract interface, never
  directly from the wrong data project.
- **D4 — Parameter hygiene.** Build explicit parameter objects; never pass a
  whole domain object as the ORM parameter bag; don't bind parameters a
  branch never references.
- **D5 — Bound everything that can grow.** Unbounded queries need a hard
  LIMIT; paging loops need a max-pages safety; IN/batch parameter counts are
  bounded via a shared batching constant.
- **D6 — Zero rows affected on a must-exist write → not-found.** Return the
  affected count and throw at the service, or throw from the repository —
  never silent success.
- **D7 — Cancellation reaches the command.** Propagate the token to the data
  command; where partial completion would corrupt state, explicitly pass a
  none-token to the completion leg and document it (U12).
- **D8 — Id-type census.** Type new model ids the way the same column/concept
  is typed on existing models. A narrowing cast next to a parameter bind is
  the tell that the field is mistyped.
- **D9 — Never derive business dates from the DB server clock.** The server's
  zone is not the tenant's; pass caller-computed date/time parameters.
- **D10 — Trigger/audit-owned columns are not written manually.** If a
  trigger or framework owns a column, manual SET clauses fight it.
- **D11 — Transactions don't span databases/tenants** that may live on
  different servers — the transaction silently degrades. Flag any ambient
  transaction whose enlisted connections can cross that boundary.
- **D12 — Storage quirks stop at the row model.** Convert legacy/storage
  shapes (option-packed booleans, sentinel values, reused columns) to a
  meaningful domain type at the row→domain boundary; never surface the raw
  storage shape upward.
- **D13 — Guarded transaction seams over silent fallbacks.** When the
  codebase offers both a fail-fast "requires active transaction" execution
  seam and a silently-auto-connecting one, writes **that must be
  transactional** use the guarded form. Read this together with `TX6`, which
  is its counterpart: D13 governs statements that genuinely degrade outside a
  transaction, and TX6 governs everything else. Applying D13 to a plain write
  is the over-constraint TX6 exists to catch.
- **D14 — Read paths use the read-only connection seam** where the codebase
  offers one; pre-marking reads makes an eventual replica rollout
  transparent.
- **D15 — Exact match over wildcard search.** Wildcard-capable filters are
  expensive and, once exposed in a public API, removing them is a breaking
  change — decide deliberately up front.
- **D16 — Typed enums on row records.** When the ORM can map them, model
  coded columns as enums rather than raw strings/ints so the repository
  boundary validates incoming values.
- **D17 — One scan, not several.** Collapse multiple parallel seeks/scans of
  the same large table into a single read (set-based join/union) instead of
  issuing separate scans and post-filtering.

## Pack: dotnet — trigger: C# code

- **N1 — Inject a clock.** Domain code never calls the static system clock;
  use the repo's clock abstraction so tests can pin time.
- **N2 — Tenant-local vs UTC.** Time-of-day business comparisons ("is it
  today?", "was it late?") use the tenant-local time source, not UTC.
- **N3 — Strong date/time types.** Model what the column stores: date-only as
  a date type, time-of-day as a time type — never a full datetime carrying a
  meaningless half.
- **N4 — `required` on correctness-gating value-type fields.** A non-required
  bool/time/date on a request record silently defaults; when the field
  toggles a guard, an omitting caller compiles and disables it.
- **N5 — Invariant culture for machine-comparable strings.** Lock names,
  cache keys, anything compared byte-wise across machines: format through
  the invariant culture explicitly.
- **N6 — Exceptions live where both sides can reference them.** A type thrown
  across a layer boundary belongs in a layer both sides reference.
- **N7 — Broad catch never swallows external failures.** Catching the base
  exception type to continue with defaults converts outages into silent bad
  data; fail loudly.
- **N8 — Don't fight cancellation.** Catching a cancellation exception so a
  step can "still complete" is wrong; propagate it.
- **N9 — API-surfaced exceptions inherit the designated base.** When the
  repo enforces a base exception type (often via a structural test), fix
  the new exception to comply — never add an exclusion to the enforcement
  test.
- **N10 — `dynamic` and reflection need justification.** Both are review
  red flags in production code; the burden is on the author to show why a
  strongly-typed alternative isn't viable.

## Pack: runtime — trigger: caching, logging/telemetry, resilience code

- **R1 — Invalidate, don't re-save.** On entity save, delete the cache entry
  and let the next read repopulate via the canonical load path; re-saving a
  merged projection through a different mapping plants stale entries.
- **R2 — Cache policy as greppable constants.** TTLs live in code, consistent
  across environments — config overrides hide the real value and hide
  TTL-dependent bugs on lower environments.
- **R3 — Normalize case-insensitive key components.** A cache key built from
  a case-insensitive identifier gets lowercased, or one entity yields two
  entries.
- **R4 — Debug logs don't merge.** They're dead code where debug is disabled
  and noise where it isn't; promote the data to a telemetry attribute if
  it's needed in production. Hot-path info-level logs become spam at volume.
- **R5 — Telemetry hygiene.** Attribute/metric names centralized in one
  constants home; no payload dumps (value-size limits); log on error.
- **R6 — Fail loudly on permission/config fetch errors.** Returning
  "false/off for everything" on an upstream error disguises an outage as a
  policy decision — especially dangerous in authorization paths.

## Pack: authz — trigger: endpoints, resolvers, loaders, permission checks

- **A1 — New entry points carry their siblings' checks.** Enumerate the
  authorization calls sibling endpoints/loaders make and match them; a
  missing tenant/business-context assertion on one new path is a security
  gap, not a style issue.
- **A2 — Authorize caller-supplied scope ids.** Batch/loader paths that
  accept ids from the caller authorize each id (IDOR); prefer sourcing scope
  from an already-authorized parent.
- **A3 — Widening token acceptance requires a per-resource audit.** Opening a
  service-token-only surface to user tokens means auditing resource-level
  checks that never existed on that path.

## Pack: graphql — trigger: schema, resolvers, data loaders

- **G1 — Dedicated graph models/enums.** Domain types and enums don't leak
  into the schema; schema attributes don't leak into domain types.
- **G2 — Resolver arguments grouped in an input type** with required fields
  non-nullable; arrays over enumerated positional fields — input objects can
  grow compatibly, loose scalars can't.
- **G3 — Truncation must surface.** Batch loaders bound their batch size,
  state their multi-tenant behavior explicitly, and never silently drop
  trailing pages — throw or bubble the has-more signal.
- **G4 — Resolve expensive relations only when selected.** Inspect the
  selection set before joining to expensive tables.
- **G5 — References resolve through batch loaders** with explicitly declared
  entity keys — composite where the identity needs it — so sibling types and
  other subgraphs reuse the loader.
- **G6 — One generic mutation-error shape.** A shared error response type
  (implementing each response union) plus a single exception→presentation
  mapper, instead of a per-endpoint failure type that multiplies classes.

## Pack: flags — trigger: feature-flag reads, flag key definitions

- **FF1 — Flag keys through the shared provider abstraction.** Never
  duplicate key constants into another file as a "temporary" bridge — the
  copies drift.
- **FF2 — Removing an enum-backed flag value shifts the stored mapping.**
  The value configured in the flag-management system must be updated in
  lockstep with the code change, or existing targeting silently changes
  meaning.

## Pack: infra — trigger: pipelines, IaC, event wiring, package manifests

- **I1 — Deploy-order events.** A live subscription must never point at a
  not-yet-deployed consumer; split the subscription into a follow-up PR
  that merges after the consumer is live everywhere.
- **I2 — Indexes ship with their query.** No speculative indexes; add the
  index in the PR that introduces the query needing it.
- **I3 — Alert destinations are real.** Never leave a new alert on the no-op
  default route; wire the owning team's channels and incident policy.
- **I4 — Know which files overwrite each other.** Where two deploy artifacts
  can each rewrite a shared section, keep the section duplicated in sync per
  the repo's stated rule — don't "deduplicate" it.
- **I5 — Vulnerable transitive dependencies get pinned directly** at the
  patched version, and the upstream package that pulls them in is checked
  for its own update at the same time.

## Maintenance

- New repeatable mistake class from a review round → if the target repo has
  its own register/runbook, append there as part of that review (that copy
  governs future reviews of that repo).
- If the lesson generalizes, add it here — in a deliberate update session,
  scoped to the right pack, stripped of repo-private names and provenance.
- A lens proven wrong gets deleted, not annotated.
- A new **backend production lens** requires either a real incident or review
  round, or a named external source *plus* a stated `Not a finding when:` guard.
  Without that bar a tier nobody can suppress becomes a best-practices dump, and
  reviewers learn to skip its findings.
