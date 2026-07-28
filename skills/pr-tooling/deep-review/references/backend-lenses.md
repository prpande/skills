# Backend production lenses

The governing tier referenced by precedence rule 2 of `references/lens-register.md`.
Each lens is a failure class that has taken backend services down in production —
distilled from postmortems and published API-security guidance rather than from
this register's own review rounds, and admitted under the rule in the register's
Maintenance section.

**This tier is not suppressible.** A repo rule may *narrow* a finding — swap the
prescribed remedy, name the repo's own helper, restrict which paths it covers —
but may not remove the flag. Where a repo convention conflicts with a lens's
remedy, report the defect and prescribe the repo's remedy. The `Not a finding
when:` guards below are the only suppression rules, and they always apply.

## Trigger

The tier fires on a **backend diff**: the diff touches SQL or ORM bindings or
repository-layer code, an HTTP endpoint or route, a GraphQL schema/resolver/loader,
a message or event handler, a schema migration file, or cache access. This is the
union of the `data-access`, `http`, `graphql`, and `runtime` triggers in the
register, so no new detection is needed.

## Severity defaults

`TEN1`, `TEN2`, `TEN6`, and `EXP8` are security findings: **blocker unless
refuted.** Every other lens takes its severity from the concrete failure scenario.

## Posture lenses

`EXP6` and `EXP7` are posture lenses — the defect is the absence of something that
lives nowhere near the diff. They are admissible only when the diff creates or
widens the exposure, and they anchor to the diff line that creates it, never to
the missing configuration. A pre-existing exposure the diff does not widen is not
a finding (U8).

## TX — transactions and consistency

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

## IDM — idempotency and delivery semantics

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

## TEN — tenancy and scoping

- **TEN1 — Every query is scoped by a tenant derived from the authenticated
  principal** — not from a request body, route parameter, or header the caller
  controls. A single missing scope predicate is the entire cross-tenant leak
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

## CA — cache correctness

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

## MIG — schema change under rolling deploy

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

## EXP — exposure and resource bounds

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
