# Backend production lenses — a governing tier for `deep-review`

**Date:** 2026-07-28
**Status:** Approved design (pre-implementation)
**Location:** `skills/pr-tooling/deep-review/` (+ one `pr-autopilot` step edit)

## Purpose

`deep-review` grades a diff against `references/lens-register.md`. The register
already carries 45 backend-relevant lenses across six packs (`data-access`,
`wire-contracts`, `http`, `graphql`, `runtime`, `authz`), so the review is not
generic — but those packs encode *repository-layer idioms*: which layer owns the
SQL, how parameters are bound, how ids are typed. The failure classes that
actually take backend services down in production are absent: transaction
boundaries, lost updates, idempotency under retry, dual writes, tenant scoping,
cache races, migrations under rolling deploy, and resource bounds.

This design adds 35 such lenses as a new tier that **fires on every backend
diff and cannot be suppressed by a repo convention**, plus a review angle that
can trace write paths beyond the diff to evaluate them.

## Decisions

Four decisions were settled during brainstorming; the rest of this document
follows from them.

1. **Authority: a third tier, not another fallback pack.** The new lenses sit
   between the universal lenses and repo conventions. A repo rule may *narrow*
   a finding but may not suppress it. Rationale: a repo whose docs never mention
   tenant scoping is exactly the repo that needs the lens fired at it. Adding
   them as ordinary scoped packs — suppressible by any adjacent house rule —
   reproduces the problem this work exists to fix.
2. **Detection: a new review angle, not lenses alone.** Several lenses cannot be
   judged from a diff hunk (does an outbox exist? what does the caller do on
   timeout? how does this repo normally scope queries?). Angle 13 is licensed to
   trace beyond the diff.
3. **Scope: six groups, 35 lenses.** An operability group (probes, correlation
   ids) was considered and cut — its findings land on platform teams, not on the
   PR author. Its one author-actionable rule survives as `TEN6`.
4. **Effort: angle 13 runs at `standard` and `max`** on backend diffs, taking
   `standard` from six finders to seven. `max` runs all 13 angles. `quick`'s
   inline pass grades against the tier without an extra agent.

## Precedence model

`references/lens-register.md` currently states three rules. They are replaced by
four:

1. **Universal lenses (`U`) always apply.**
2. **Backend production lenses always fire on a backend diff.** A repo rule may
   *narrow* a finding — swap the prescribed remedy, name the repo's own helper —
   but may not suppress the flag. The boundary is one test: a repo rule changes
   what you prescribe, never whether you report. Where a repo convention
   conflicts with a lens's remedy, report the defect and prescribe the repo's
   remedy.
3. **Repo-defined conventions govern** everything below this line, and outrank
   scoped packs.
4. **Scoped packs are fallback suggestions** — apply only when the diff touches
   the pack's trigger AND the repo has no rule of its own on that subject.

Rules 1, 3 and 4 are today's behaviour, restated. Rule 2 is new.

### Backend-diff trigger

Mechanical, not a judgment call. The diff is a backend diff when it touches any
of: SQL or ORM bindings or repository-layer code; an HTTP endpoint or route; a
GraphQL schema, resolver, or loader; a message/event handler; a schema migration
file; or cache access. This is the union of the existing `data-access`, `http`,
`graphql`, and `runtime` triggers, so Phase 0 reuses detection it already does.

## The lenses

Full text lives in a new `references/backend-lenses.md`, in the register's
existing voice: **id — imperative rule**, then the failure mechanism. Lenses
that would otherwise generate noise carry a `Not a finding when:` guard —
without these, "cannot be suppressed" becomes a noise generator.

`EXP6` and `EXP7` are posture lenses: the defect is the absence of something
that lives nowhere near the diff. They are admissible only when the diff creates
or widens the exposure, and they anchor to the diff line that creates it.

### TX — transactions and consistency

- **TX1 — No network I/O inside an open transaction.** An HTTP call, queue
  publish, cache write, or distributed-lock acquisition between begin and commit
  holds row locks for the duration of a dependency's latency or outage. Move it
  outside the boundary, or record the intent in the same transaction (TX4) and
  act after commit.
  *Not a finding when:* the call targets the same database connection the
  transaction owns.
- **TX2 — Read-modify-write carries a concurrency token.** Load, mutate in
  memory, save — without a rowversion, ETag, or `WHERE version = @seen` — loses
  the second writer's update: both requests read the same state, both pass
  validation, one write disappears with no error. Wrapping the pair in a
  transaction does not fix this; at the default isolation level both readers
  still see the initial state.
  *Not a finding when:* the path is append-only, single-writer by construction,
  or the update is a relative statement the database serialises (`SET n = n + 1`).
- **TX3 — The service owns the transaction boundary.** A repository that opens
  its own transaction cannot compose into a larger unit of work; an endpoint
  that opens one puts a business decision in the wrong layer (U18).
- **TX4 — A dual write is an outbox or a documented inconsistency.** A database
  write plus a message publish, cache write, or third-party call in one method
  has no atomicity — the second can fail after the first commits, and the event
  is lost with no trace. Record the intent in the same transaction and dispatch
  after commit, or state at the seam why the inconsistency is tolerable (U12).
  Where an outbox exists, the dispatcher reads only committed rows and the table
  has a bounded retention path; an unbounded outbox degrades the whole database.
- **TX5 — Locking and isolation assumptions are explicit in code.** Code that
  depends on repeatable reads, `SELECT ... FOR UPDATE`, or a specific isolation
  level states it at the call site rather than inheriting a default that differs
  between local, CI, and production.

### IDM — idempotency and delivery semantics

- **IDM1 — Retryable writes are idempotent by key or by constraint.** A client
  that retries on timeout must not produce a second effect: guard with a
  caller-supplied idempotency key whose stored result is replayed, or with a
  natural unique constraint the second attempt violates harmlessly.
  *Not a finding when:* the operation is naturally idempotent (full-state PUT,
  delete), or no retry path can reach it.
- **IDM2 — Message handlers are idempotent.** At-least-once is the default
  contract of every broker; redelivery follows any consumer crash, visibility
  timeout, rebalance, or lost acknowledgement. Deduplicate on the message id or
  express the effect as an upsert. A handler that inserts, increments, or calls
  a payment API without a guard double-processes.
- **IDM3 — Retry policy only wraps idempotent operations.** Retries around a
  non-idempotent call convert a single transient failure into duplicated side
  effects. Check what the operation does, not just whether the exception looks
  transient.
- **IDM4 — Retries are bounded, backed off, and jittered.** Immediate unbounded
  retry across every instance is a retry storm: a hundred instances retrying
  five times turns a hundred requests into five hundred against a dependency
  that is already failing, preventing recovery. Check W6 first — the base client
  may already retry.
- **IDM5 — Every consumer has a retry ceiling and a dead-letter destination with
  a named owner.** A message that throws forever is requeued at the head and
  stops the partition; a dead-letter queue nobody owns is a silent data-loss
  queue. Replay is scoped by failure cause and code version, never "send
  everything back".
- **IDM6 — Background work carries its own context.** Queue workers, timers, and
  fire-and-forget tasks do not inherit request context: tenant, correlation id,
  and authorization scope are serialised into the payload and re-established by
  the handler, never read from ambient state.

### TEN — tenancy and scoping

- **TEN1 — Every query is scoped by a tenant derived from the authenticated
  principal, not from a request body, route parameter, or header the caller
  controls.** A single missing scope predicate is the entire cross-tenant leak
  class, and it produces correct-looking results in every single-tenant test.
  *Not a finding when:* the repo enforces scoping globally (row-level security
  with a verified session variable, an ORM global filter) and the diff does not
  bypass it.
- **TEN2 — Every cache key carries the tenant/scope component.** A key of
  `user:{id}` in a shared cache serves one tenant's row to another. This is a
  security finding, not a hygiene note. Combine with R3.
- **TEN3 — Tenant context is passed explicitly across async boundaries.**
  Ambient or async-local context does not survive into background tasks, timers,
  thread-pool work, or pooled connections. Pass it as a parameter and assert its
  presence at the boundary.
- **TEN4 — Not-found and forbidden are indistinguishable for out-of-scope ids.**
  Returning 404 for a nonexistent id and 403 for another tenant's id lets a
  caller enumerate what exists elsewhere.
- **TEN5 — Session-scoped connection state is reset on release.** Anything set
  on a pooled connection (`SET app.tenant_id`, RLS session variables, temp
  tables, session settings) leaks to the next borrower. Set it inside the scope
  that uses it and reset it deterministically.
- **TEN6 — Secrets and personal data never land in logs, cache values, or error
  responses.** Tokens, connection strings, and personal fields must not be
  logged at any level, cached in a payload that outlives its authorization, or
  echoed in an error body. Combine with R5's payload-size limits.

### CA — cache correctness

Extends `R1`–`R3`, which cover invalidate-don't-re-save, TTLs as greppable
constants, and case normalisation.

- **CA1 — The cache-aside write race is closed, or the staleness window is
  stated.** A read that misses, reads the database, and writes the cache can
  land a value that predates a concurrent commit — the entry is then wrong until
  TTL. Invalidate both before and after the database write, or document at the
  seam the staleness the design accepts (U12).
- **CA2 — Hot-key regeneration is single-flighted and TTLs are jittered.** When
  a hot key expires, every concurrent request regenerates it against the
  database at once. Serialise regeneration (single-flight, or serve stale while
  revalidating) and spread TTLs so keys do not expire in lockstep.
- **CA3 — Cached payloads are version-prefixed.** Adding, renaming, or retyping
  a field in a cached type makes entries written by the old build deserialise
  into a wrong or default-filled object on the new one — during every rolling
  deploy. Bump a version component in the key when the cached shape changes.
- **CA4 — Negative results are cached deliberately.** An uncached miss on a hot
  absent key amplifies straight to the database; a cached miss needs a shorter
  TTL than a hit and an invalidation when the entity is created. Pick one and
  say which.
- **CA5 — In-process caches are size-bounded and hand out immutable values.** An
  unbounded dictionary is a memory leak with a slow fuse; returning a shared
  mutable instance lets one caller's mutation reach every other caller.
- **CA6 — A cache is never the system of record for an authorization
  decision.** Cached permissions, roles, or entitlements keep revoked access
  alive for the TTL. Bound it explicitly and invalidate on change; combine with
  R6 — an upstream error must not resolve to "allowed".

### MIG — schema change under rolling deploy

- **MIG1 — Schema change is expand/contract across releases.** Dropping a
  column, renaming one, or adding `NOT NULL` in the same release that changes
  the code breaks every old instance still serving traffic during the rollout.
  Expand, migrate, then contract in a later release.
  *Not a finding when:* the table has no existing readers or writers.
- **MIG2 — Migration connections set a lock timeout.** DDL waiting on an
  exclusive lock queues behind a long-running query — and every subsequent query
  queues behind the DDL, turning a schema change into a full-table stall. A
  short lock timeout plus a statement timeout makes it fail fast and retry.
- **MIG3 — Backfills are batched and resumable.** A single `UPDATE` across a
  large table is a lock, a transaction-log event, and a replication-lag spike.
  Batch by key range, commit per batch, and make a re-run resume.
- **MIG4 — Index creation on a live table is online/concurrent.** The default
  form locks the table for the build. Pair with I2 — the index ships with the
  query that needs it.

### EXP — exposure and resource bounds

- **EXP1 — Pagination ordering is total.** `ORDER BY created_at` with duplicate
  values breaks ties non-deterministically, so rows are skipped and repeated
  across pages. Every paginated ordering ends in a unique column.
- **EXP2 — Keyset/cursor pagination once the set can grow.** Offset pagination
  scans and discards every skipped row, so deep pages get progressively more
  expensive, and concurrent inserts shift the window. Cursor pagination needs
  the stable sort key EXP1 requires.
  *Not a finding when:* the result set is bounded small by construction.
- **EXP3 — The server clamps client-supplied page size.** A `limit` the caller
  sets with no server-side maximum is an unbounded query with extra steps.
- **EXP4 — Request bodies, arrays, and uploads are size-bounded.** An unbounded
  collection parameter is a memory and database amplifier from one request.
- **EXP5 — Every outbound call has an explicit timeout.** A dependency that
  hangs rather than fails holds a request thread and a pooled connection until
  something else gives up; pool exhaustion then converts one slow dependency
  into a whole-service outage.
- **EXP6 — GraphQL depth and complexity limits exist, and the new field is
  costed.** Nesting multiplies: ten levels at ten items each is ten billion
  resolutions from one request. A new field or edge that widens the graph must
  fit the configured budget. *Posture — admissible only when the diff creates or
  widens the exposure.*
- **EXP7 — GraphQL errors are masked in production.** An unhandled resolver
  exception surfaced verbatim leaks internal messages, stack frames, and SQL to
  any caller. *Posture — admissible only when the diff adds a path that can
  surface a raw exception.*
- **EXP8 — Inbound binding is allowlisted.** Binding a request payload straight
  onto a domain entity or row model lets a caller set fields the API never meant
  to expose — status, role, owner, price. Map explicitly, field by field.

### Severity defaults

`TEN1`, `TEN2`, `TEN6`, and `EXP8` are security findings: **blocker unless
refuted.** Every other lens takes its severity from the concrete failure
scenario, as today.

## File-by-file changes

Eight files.

1. **`references/backend-lenses.md`** (new) — the tier: header stating the
   firing rule and pointing back at the register's precedence section, the
   mechanical trigger, the six groups, the severity defaults.
2. **`references/lens-register.md`** — Precedence section replaced with the
   four-rule model. A Tier-2 section lists the six prefixes and points at the
   new file. The opening line ("distilled from real review rounds — not a style
   guide") is amended: the tier is distilled from postmortems and OWASP, not
   from this register's own review history, and the document should say so.
   Maintenance gains the admission rule below.
3. **`SKILL.md`** — angle 13 added to the catalog; effort table updated
   (`standard` = 6 finders + angle 13 on backend diffs, `max` = all 13, `quick`
   grades against the tier inline); Phase 0 gains a step recording whether the
   diff is backend; the file list at the top gains the new reference.
4. **`references/agent-briefs.md`** — an angle-13 finder brief. It differs from
   the standard finder brief in three ways: an explicit read-only licence to
   read beyond the diff; the posture-admissibility rule; and the anchoring rule
   — **a posture finding anchors to the diff line that creates the exposure,
   never to the missing config**, which keeps it inside the existing JSON schema
   and inside U8. Model stays sonnet.
5. **`pr-autopilot/steps/02-preflight-review.md`** — step 3 resolves
   `backend-lenses.md` alongside the register, independently missing-tolerant
   (log `backend_lenses_missing`, substitute empty, continue); includes the tier
   when the diff is backend; the precedence preamble in 3a is updated to state
   the narrow-not-suppress rule.
6. **`pr-loop-lib/references/adversarial-review-prompt.md`** — Pass D's
   instruction hardcodes the precedence summary, so it carries the
   narrow-not-suppress wording and maps the tier's security lenses onto Pass D's
   own severity schema.
7. **This spec.**
8. **The implementation plan.**

## Maintenance guardrail

The register's Maintenance section gains a tier-2 admission rule: **a new
backend production lens requires either a real incident or review round, or a
named external source *plus* a stated false-positive guard.** Without it, a tier
that cannot be suppressed becomes a best-practices dumping ground, and reviewers
learn to skip its findings — which costs more than never having added it.

## Non-goals

- Stack-specific tells stay in the `dotnet`/`N` pack. Tier-2 text names
  mechanisms (`rowversion`, `SELECT ... FOR UPDATE`), not one stack's APIs.
- The report format, the finding JSON schema, and the verdict rubric are
  unchanged.
- `quick`'s agent count is unchanged.
- No per-repo register staging; that mechanism already exists and is untouched.

## Risks

- **False positives on lenses that need repo-wide context.** `TEN1` in a repo
  with global scoping, `MIG1` on a new table, `IDM1` on an internal endpoint.
  Mitigated by the `Not a finding when:` guards and by the existing verifier
  pass, which refutes on quoted evidence.
- **Angle 13 wandering.** A tracer licensed to leave the diff can produce
  findings about untouched code. Mitigated by the anchoring rule and by U8,
  which the verifier already enforces.
- **`standard` cost.** One extra sonnet finder on backend diffs. Accepted.

## Verification

- `python scripts/validate.py` passes (repo skill validator).
- The register's Tier-2 pointer resolves to the new file; the tier is reachable
  from `lens-register.md` alone, since that is the path `pr-autopilot` resolves.
- A dry read of `02-preflight-review.md` confirms the degrade path still works
  with the new file absent.
- Dogfood: run `/deep-review` at `standard` against a backend diff and confirm
  angle 13 dispatches and cites tier ids.
