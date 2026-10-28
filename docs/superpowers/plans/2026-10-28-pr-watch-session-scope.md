# pr-watch session scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `pr-watch` from one watch per repo into one watch per Claude Code session across repos, with a per-PR lease the orchestrator can read.

**Architecture:** State moves to `~/.claude/pr-watch/`: a session directory (set, poller files, heartbeat) and per-PR files (progress written by the holder session, lease written only by `poll.py`). The poller queries every repo in one aliased GraphQL request and writes each PR's lease on every tick. Step files take `owner/repo#N` keys and read and write per-PR progress files instead of `watch.json` entries.

**Tech Stack:** Python 3 standard library only (`ctypes` for Windows process times); `unittest`; markdown step files; `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-10-28-pr-watch-session-scope-design.md` (read it with this plan). Original design: `docs/superpowers/specs/2026-09-11-pr-watch-design.md`.

## Global Constraints

- Python standard library only. Tests use `unittest`, run from the repo root: `python -m unittest discover -s skill-tests/pr-watch/tests -v`. `pytest` is not installed.
- Root `~/.claude/pr-watch/`; tests override it with env `PR_WATCH_HOME`.
- Session id = env `CLAUDE_CODE_SESSION_ID`; claude pid = env `CLAUDE_PID`.
- `owner` and `repo` lowercased in every path and key; key form `owner/repo#N`.
- Lease: `schema` 1, `stale_after_seconds` 300, times ISO-8601 UTC ending `Z`, status one of `armed`, `stopped`, `released`, `closed`.
- Only `poll.py` writes a lease, via `write_json_atomic`. Claim lock `<N>.claim.lock`, stale after 60 s. Closed leases pruned after 7 days.
- A lease file that exists but raises an `OSError` other than `FileNotFoundError` is unreadable, not unheld (claim refuses "lease unreadable"). A tick writes only a lease still held by this session and still `armed`; it never moves a lease out of `stopped`, `released` or `closed`.
- Push lock `prs/<owner>/<repo>/push.lock`, exclusive create, stale after 300 s.
- Every subprocess the scripts start on Windows passes `creationflags=subprocess.CREATE_NO_WINDOW` (0 elsewhere).
- No marker, template, prefix or trailer on anything posted to GitHub; commits carry no `Co-Authored-By` trailer (praty's rule).
- Live tests touch only `prpande/prism-sandbox` and `prpande/prism-sandbox-2`, never Mindbody repos.
- Step files are agent instructions: keep the existing voice; run `python scripts/validate.py` after every step-file task.

## Review Focus

1. A holder whose claude.exe was renamed by auto-update (`claude.exe.old.<ms>.<pid>`) is still live: liveness uses pid + creation time, never the image name. Test in Task 3.
2. Two sessions claiming one PR at once: a fresh claim lock makes the second claim fail with "busy", a lock older than 60 s is removed. Test in Task 3.
3. A half-written or garbage lease file reads as "nobody holds it" and a claim overwrites it. Test in Task 3.
4. One repo in the set becoming unreachable (renamed, no access) must not stop ticks for the other repos. Test in Task 4.
5. A session whose transcript cannot be found (deleted, project folder moved) gets an empty bare discovery with a clear stderr line, not a crash. Test in Task 6.

---

### Task 1: Spike: cross-repo edits after leaving the worktree

Throwaway. Decides which branch of the spec's "Editing files in another repo" Task 9 writes. Run it in this session, from the plan's worktree.

**Files:** none committed. Record the result in this plan file under the task.

- [ ] **Step 1:** Make a scratch git repo outside this repo: `git init <scratchpad>/xrepo` with one committed file, and `git -C <scratchpad>/xrepo worktree add <scratchpad>/xrepo/.claude/worktrees/b -b b`.
- [ ] **Step 2:** From inside this worktree, try `Write` to `<scratchpad>/xrepo/.claude/worktrees/b/probe1.txt`. Expected: refused (the lock), confirming the problem.
- [ ] **Step 3:** `ExitWorktree` with `action: keep`. Then `Write` and `Edit` to `.../b/probe2.txt`. Record whether they succeed.
- [ ] **Step 4:** Dispatch one `general-purpose` subagent (model haiku) told to `Write` `.../b/probe3.txt` with absolute path. Record the result.
- [ ] **Step 5:** `EnterWorktree` with `path` = this plan's worktree. Expected: back in it; `git rev-parse --show-toplevel` shows it.
- [ ] **Step 6:** Record outcome A (steps 3-5 all succeed: Task 9 uses exit/absolute paths/re-enter) or B (any fails: Task 9 uses the patch fallback). Delete the scratch repo.

**Result (28 Oct 2026): outcome C.** Run with the probe repo at `D:\src\prpande\pw-xrepo-probe` (the scratchpad is exempt from the lock, so a probe there proves nothing). Step 2's Write into the other repo's worktree succeeded while still isolated; Edit too; a haiku subagent's Write and Edit there succeeded; a Write into this repo's shared checkout was refused ("Edit the worktree copy of this file instead of the shared-checkout path"). No ExitWorktree needed. Task 9: other-repo PRs skip relocation and use absolute paths plus `git -C`; launch-repo PRs keep `EnterWorktree(path)`.

### Task 2: Keys and paths module

**Files:**
- Create: `skills/pr-tooling/pr-watch/scripts/pw_paths.py`
- Test: `skill-tests/pr-watch/tests/test_pw_paths.py`

**Interfaces:**
- Produces:
  - `home() -> pathlib.Path` (env `PR_WATCH_HOME` else `~/.claude/pr-watch`)
  - `parse_ref(ref: str, default_repo: str | None = None) -> tuple[str, str, int]`: accepts `owner/repo#N`, a PR URL `https://github.com/owner/repo/pull/N`, or bare `N` (needs `default_repo` `owner/repo`); returns lowercased owner, repo; raises `ValueError` on anything else or names failing `poll.NAME`.
  - `pr_key(owner: str, repo: str, n: int) -> str` → `owner/repo#N` lowercased.
  - `session_dir(session_id: str) -> Path`, `pr_dir(owner, repo) -> Path`, `lease_path(owner, repo, n) -> Path` (`<N>.json`), `progress_path(owner, repo, n) -> Path` (`<N>.progress.json`), `claim_lock_path(owner, repo, n) -> Path`.
  - `iso_utc(epoch: float) -> str` (`2026-10-28T07:35:00Z`), `parse_iso(s: str) -> float`.

- [ ] **Step 1: Write the failing tests**

```python
def test_ref_forms_lowercase(self):
    self.assertEqual(pw_paths.parse_ref("Mindbody/Mindbody.Clients#14"), ("mindbody", "mindbody.clients", 14))
    self.assertEqual(pw_paths.parse_ref("https://github.com/prpande/prism-sandbox/pull/3"), ("prpande", "prism-sandbox", 3))
    self.assertEqual(pw_paths.parse_ref("7", default_repo="PrPande/Skills"), ("prpande", "skills", 7))
def test_bad_refs_raise(self):
    for bad in ("7", "o/r#x", "o r/x#1", "o/r", "../x/y#1"):
        with self.assertRaises(ValueError): pw_paths.parse_ref(bad)
def test_case_variants_share_one_lease_path(self):
    self.assertEqual(pw_paths.lease_path("Mindbody", "Mindbody.Clients", 14), pw_paths.lease_path("mindbody", "mindbody.clients", 14))
def test_paths_under_home(self):  # with PR_WATCH_HOME set to a temp dir
    self.assertEqual(pw_paths.progress_path("o", "r", 5), tmp / "prs" / "o" / "r" / "5.progress.json")
def test_iso_round_trip(self):
    self.assertEqual(pw_paths.iso_utc(2_000_000_000), "2033-05-18T03:33:20Z")
    self.assertEqual(pw_paths.parse_iso("2033-05-18T03:33:20Z"), 2_000_000_000)
```

- [ ] **Step 2:** Run `python -m unittest discover -s skill-tests/pr-watch/tests -p test_pw_paths.py -v`. Expected: FAIL (`No module named 'pw_paths'`). Add `pw_paths` import beside `poll` in `fakes.py`.
- [ ] **Step 3:** Implement `pw_paths.py` per the Interfaces block. (Built: `NAME` moved into `pw_paths.py`; `poll.py` re-imports it. See ledger ruling 5.)
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `Add pr-watch keys and state paths`.

### Task 3: Lease module

**Files:**
- Create: `skills/pr-tooling/pr-watch/scripts/lease.py`, `skills/pr-tooling/pr-watch/scripts/pw_io.py` (`read_json`, `write_json_atomic` moved out of `poll.py`, which re-imports them)
- Test: `skill-tests/pr-watch/tests/test_lease.py`

**Interfaces:**
- Consumes: Task 2 paths; `pw_io.write_json_atomic`, `pw_io.read_json`. Module graph: `pw_io` ← `pw_paths` ← `lease` ← `poll`.
- Produces:
  - `process_started_at(pid: int) -> float | None`: epoch creation time via `ctypes` (`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetProcessTimes`); `None` when the process does not exist or access fails; non-Windows: `None`.
  - `holder_alive(holder: dict, started_at=process_started_at) -> bool`: true when `started_at(holder["pid"])` is within 2 s of `parse_iso(holder["pid_started_at"])`.
  - `read_lease(owner, repo, n) -> dict | None` (None when missing or unparseable).
  - `claim(owner, repo, n, *, role, holder, explicit, now, started_at=process_started_at) -> tuple[bool, str]`: holder = `{session_id, pid, pid_started_at, poller_pid}`. Returns `(True, "claimed")` / `(True, "reclaimed")` or `(False, reason)`. Rules exactly as the spec's "Claim rules". Writes `status: armed`, fresh `heartbeat`, `stale_after_seconds: 300`, `pending_since: null`, `last_error: null`, keeps `last_head_sha` from an old lease. Holds the claim lock for the read-check-write; a lock file under 60 s old returns `(False, "busy: another claim in progress")`.
  - `set_status(owner, repo, n, status, session_id, now) -> bool`: writes `status` only when `holder.session_id == session_id`; false otherwise.
  - `tick_write(owner, repo, n, *, session_id, now, head, pending_since, last_error, poller_pid, status="armed") -> bool`: rewrites heartbeat-side fields; returns false and writes nothing when the lease's holder is a different session (lost lease).
  - `prune_closed(now) -> int`: deletes `closed` leases (and their progress files) whose `updated_at` is over 7 days old.
  - `armed_peers(owner, repo, exclude_n) -> list[int]`: PR numbers in that repo dir with `status: armed` and `role: authored`, any holder, excluding `exclude_n`.
  - `holder_label(session_id, agents=list_agents) -> str`: `[Tag]Name` from `claude agents --json` (`name` for that `sessionId`), else the id. `list_agents()` runs `claude agents --json` with `CREATE_NO_WINDOW`, returns `[]` on any failure.

- [ ] **Step 1: Write the failing tests** (all with a temp `PR_WATCH_HOME`, injected `started_at`, fixed `now`)

```python
def test_claim_fresh_writes_contract_fields(self):
    ok, why = lease.claim("o", "r", 1, role="authored", holder=H1, explicit=False, now=NOW, started_at=alive(H1))
    self.assertEqual((ok, why), (True, "claimed"))
    l = lease.read_lease("o", "r", 1)
    self.assertEqual({k: l[k] for k in ("schema","owner","repo","number","role","status","stale_after_seconds","pending_since","last_error")},
                     {"schema":1,"owner":"o","repo":"r","number":1,"role":"authored","status":"armed","stale_after_seconds":300,"pending_since":None,"last_error":None})
    self.assertEqual(l["heartbeat"], pw_paths.iso_utc(NOW))
def test_same_session_new_pid_reclaims_even_with_fresh_heartbeat(self): ...  # (True, "reclaimed")
def test_live_other_session_refused_with_label(self):  # reason contains "[Tag]Name" and "heartbeat 30s ago"
def test_dead_holder_with_stale_heartbeat_taken(self):  # heartbeat NOW-301, started_at -> None
def test_dead_holder_with_fresh_heartbeat_refused(self):  # NOW-100
def test_alive_pid_with_different_start_time_counts_dead(self):  # pid reused
def test_renamed_exe_holder_still_live(self):  # started_at matches; no image-name check anywhere
def test_released_and_closed_claimable(self):
def test_stopped_dead_holder_needs_explicit(self):  # explicit=False refused, True claimed
def test_garbage_lease_is_unheld(self):  # file "{\"sch" -> read_lease None, claim True
def test_fresh_claim_lock_is_busy_stale_is_removed(self):  # mtime NOW-10 busy; NOW-61 claimed
def test_tick_write_refuses_lost_lease(self):
def test_set_status_only_by_holder(self):
def test_prune_closed_after_seven_days(self):  # 7d+1s pruned, 7d-1s kept, armed never
def test_armed_peers_spans_sessions_excludes_self(self):
```

- [ ] **Step 2:** Run `python -m unittest discover -s skill-tests/pr-watch/tests -p test_lease.py -v`. Expected: FAIL (no module).
- [ ] **Step 3:** Implement `lease.py`. Lock = `os.open(path, O_CREAT|O_EXCL|O_WRONLY)`; age from `os.stat().st_mtime` against `now`; always removed in `finally`.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `Add pr-watch per-PR lease`.

### Task 4: Multi-repo poller and per-PR progress

**Files:**
- Modify: `skills/pr-tooling/pr-watch/scripts/poll.py` (`tick_query`, `tick_once`, `monitor`, `evaluate_ci`, `evaluate_reviewed`, `checks_payload`, `findings_payload`, `report`, `main`, `run_mode`)
- Modify: `skill-tests/pr-watch/tests/fakes.py` (`watch()` builder, `FakeGh` heads query; `FakeGh` keys prs, pages, rollup and failures by `(owner, repo, number)`)
- Modify: `skills/pr-tooling/pr-watch/scripts/lease.py` and `skill-tests/pr-watch/tests/test_lease.py` (`tick_write` result, Step 0)
- Modify: every `skill-tests/pr-watch/tests/test_poll_*.py` that builds a watch or asserts `"pr": <int>`
- Test: `skill-tests/pr-watch/tests/test_poll_multirepo.py`

**Interfaces:**
- Consumes: Tasks 2 and 3.
- Produces:
  - `load_view(session_dir: Path) -> dict`: reads `watch.json` and each PR's progress file (session-local copy under `<session_dir>/progress/` when `dry_run`), returns `{self_login, bot_allowlist, ado_orgs, push_queue, session_id, claude_pid, prs: {key: {**progress, **entry, "owner", "repo", "number"}}}`. A missing progress file reads as the starting values of step 01 §4 for the role.
  - `tick_query(groups: dict[tuple[str, str], list[int]]) -> tuple[str, dict[str, tuple[str, str]]]`: one query, alias `r<i>` per repo, `p<N>` per PR inside; returns the query and alias → (owner, repo).
  - `lease.tick_write(...)` (amended, Step 0) returns `"written"`, `"lost"` (another session holds it), `"inactive"` (held here but status not `armed`) or `"missing"` (no lease file). It writes only on `"written"`: holder is this session AND stored status is `armed`. `status="closed"` is allowed only from `armed`.
  - `tick_once(gh, view, poller, now, force=False) -> list[dict]`: as today, keyed by `owner/repo#N`; events carry `"pr": "<key>"`. A null repo alias warns once per repo and skips only that repo's PRs; those PRs are returned in `poller["unreachable"]` so the monitor can write `last_error`. Poller `prs` entries gain `review_pending: bool`, `ci_pending: bool` and `pending_since: int|None` (set when either first becomes true, cleared when both false). Both are recomputed every tick from live data, never from stored signatures: authored `review_pending` = `pending()` returned any thread tail or top-level item this tick; authored `ci_pending` = rollup in `FAILED_ROLLUP` with at least one red required check not yet in `ci_handled`; reviewed `review_pending` = the PR head differs from `rereviewed_head` or an unanswered reply exists, and the settled state is false; reviewed `ci_pending` is always false.
  - `run_gh` (and every other `subprocess.run` in `poll.py`) passes `creationflags=CREATE_NO_WINDOW` on Windows (ledger ruling 3).
  - `monitor(gh, session_dir, sleep, clock, max_ticks=None, write_lease=lease.tick_write) -> int`: re-reads `watch.json` every tick and ticks only entries that are `armed` and not in `poller["closed"]`. After each saved tick, writes each ticked PR's lease through `write_lease`, with `status: closed` in the same tick the closed event is emitted. On `"lost"` emits `lease-lost` once and drops the PR; on `"inactive"` drops it silently; on `"missing"` warns on stderr once. For a PR in `poller["unreachable"]` it writes the lease with a fresh heartbeat, `last_head_sha` unchanged and `last_error: "repo unreachable"`, cleared on the next good tick. Records `poller_pid`, `claude_pid` and `claude_started_at` (from `lease.process_started_at` at start) in `watch-poller.json`; prunes closed leases once per reconciliation. Each tick first checks the claude process is still the one recorded (pid + start time, `lease.holder_alive`); when it is gone the monitor writes nothing more and returns 3 without printing `idle`, so the leases go stale and another session can take over. When `dry_run` is true the monitor writes no leases, emits no `lease-lost` and prunes nothing. When no entry is still `armed` and open (after writing the final statuses), prints `{"kind": "idle"}` and returns 0.
  - CLI: `--session-dir` replaces `--state-dir`; `--baseline/--tails/--findings/--checks` take a ref string; `--report/--reseed` cover the whole set (the spec's Poller section says the same after this review).

- [ ] **Step 0: Amend `lease.tick_write`** to the four-way result above. Tests in `test_lease.py`: a lease this session holds with status `released`, `stopped` or `closed` returns `"inactive"` and the file is byte-identical afterwards; another session's lease returns `"lost"`; no file returns `"missing"`; `status="closed"` over an armed lease of this session writes. Update existing `tick_write` tests that assert `True`/`False`. Run `test_lease.py`; expected PASS.

- [ ] **Step 1: Write the failing tests** in `test_poll_multirepo.py`

```python
def test_one_request_covers_two_repos(self):
    events = tick(view({"o/a#1": "authored", "p/b#2": "authored"}))
    self.assertEqual(self.gh.heads_requests(), 1)
    self.assertEqual({e["pr"] for e in events}, {"o/a#1", "p/b#2"})
def test_unreachable_repo_does_not_block_the_other(self):
    self.gh.null_repos.add(("p", "b"))
    self.assertEqual([e["pr"] for e in tick(...)], ["o/a#1"])
def test_pending_since_set_then_cleared(self): ...
def test_monitor_writes_lease_each_tick(self):  # heartbeat == iso_utc(clock()), last_head_sha, pending_since
def test_monitor_exits_idle_when_nothing_armed(self):  # after closed event: lease status closed, last stdout line {"kind": "idle"}, returns 0
def test_released_entry_is_not_ticked(self):  # entry status released in watch.json -> no lease write, no event for it
def test_tick_never_rearms_a_released_lease(self):  # lease file already released, entry still armed in a stale view -> lease unchanged
def test_lost_lease_pr_is_reported_once(self):  # lease held by another session -> one event {"pr": key, "kind": "lease-lost", "holder": <session id>}, stderr "lease for o/a#1 is held by another session", no further ticks for it
def test_released_lease_is_silent(self):  # lease released by this session, entry still armed in watch.json -> no lease-lost, no write
def test_same_number_in_two_repos(self):  # o/a#1 and p/b#1 with different heads -> each event carries its own key and head
def test_unreachable_repo_gets_last_error(self):  # null alias for p/b -> p/b#2 lease heartbeat fresh, last_error "repo unreachable"; next good tick clears it
def test_monitor_exits_when_claude_is_gone(self):  # injected holder_alive False -> returns 3, no idle line, lease heartbeat not advanced
def test_dry_run_monitor_writes_no_lease(self):  # dry_run true -> no lease files created, no lease-lost
def test_closed_pr_counts_as_not_armed(self):  # closed event this tick with entry still armed in watch.json -> lease closed, idle printed
def test_pending_flags_from_live_data(self):  # green CI with an old last_ci_signature -> ci_pending False; reviewed PR settled -> review_pending False
def test_run_gh_hides_window_on_windows(self):  # os.name patched to nt -> subprocess.run called with creationflags CREATE_NO_WINDOW
```

- [ ] **Step 2:** Run the new file. Expected: FAIL.
- [ ] **Step 3:** Change `fakes.watch()` to write a session dir + progress files and return the dir; teach `FakeGh` to answer the aliased multi-repo heads query (`r<i>: repository(owner: "o", name: "a") { p1: ... }`) with `null_repos`. Update existing tests' expected `"pr"` values to keys.
- [ ] **Step 4:** Implement the poll.py changes per the Interfaces block. Evaluate functions take owner/repo from the PR entry, not the view.
- [ ] **Step 5:** Run `python -m unittest discover -s skill-tests/pr-watch/tests -v`. Expected: all PASS (old and new).
- [ ] **Step 6:** Commit `Poll every repo in a session's watch in one query and write leases`.

The `lease-lost` and `idle` events are new; Task 9 routes them (`lease-lost`: mark the entry `lost` in `watch.json`, post one line; `idle`: a planned end, no re-arm).

### Task 5: Claim, status and peers CLI

**Files:**
- Modify: `skills/pr-tooling/pr-watch/scripts/poll.py` (`main`, `run_mode`)
- Modify: `skills/pr-tooling/pr-watch/scripts/lease.py` (`taken-over` result; `_take_lock` gains a `stale_seconds` parameter, default 60; push-lock functions write the session id into the lock file)
- Test: `skill-tests/pr-watch/tests/test_poll_lease_cli.py`, `skill-tests/pr-watch/tests/test_lease.py`

`taken-over` is returned only for the `_decide` branches that take another session's `armed` lease whose holder is dead, or its `stopped` lease by explicit ref. Taking a `released` or `closed` lease, or a missing one, stays `claimed`, so the existing `test_lease.py` cases keep their expected values.

**Interfaces:**
- Produces CLI modes (all print one line or JSON, exit 0 on success, 1 with a `pr-watch:` stderr line on failure):
  - `--claim <ref> --session-dir <dir> --role authored|reviewed [--explicit]`: holder from `watch.json` (`session_id`, `claude_pid`) and `process_started_at(claude_pid)`. Prints `claimed`, `reclaimed`, or `taken-over` (the previous lease named another session); on refusal exits 1 with the reason. `lease.claim` gains the `taken-over` result for that case.
  - `--lease-status <ref> --session-dir <dir> --status stopped|released`.
  - `--repo-peers <ref>`: prints JSON list of armed peer keys in the same repo.
  - `--push-lock take|release <ref> --session-dir <dir>`: `take` prints `taken` or exits 1 with `busy`; `release` removes the lock only when this session took it (the lock file holds the session id). Backed by new `lease.take_push_lock(owner, repo, session_id, now) -> bool` and `lease.release_push_lock(owner, repo, session_id) -> None`, reusing the claim-lock helper with a 300 s stale threshold.

- [ ] **Step 1:** Tests: claim then reclaim with the same session; claim of another session's dead lease prints `taken-over`; refusal exit code 1 and stderr naming the holder; `--lease-status` by a non-holder exits 1; `--repo-peers` lists another session's armed PR and not a closed one; push lock taken by session A makes B's `take` exit 1 `busy`, B's `release` leaves A's lock, a 301 s old lock is taken.
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement as thin wrappers over `lease.py`.
- [ ] **Step 4:** Run the whole suite; expected PASS.
- [ ] **Step 5:** Commit `Add lease claim, status and peers modes`.

### Task 6: Bare-arm discovery from the transcript

**Files:**
- Create: `skills/pr-tooling/pr-watch/scripts/discover.py`
- Modify: `poll.py` (`--discover --session-id <id>` mode calls it)
- Test: `skill-tests/pr-watch/tests/test_discover.py` (fixture transcripts written as JSONL in the test)

**Interfaces:**
- Produces:
  - `find_transcript(session_id, projects=Path.home()/".claude"/"projects") -> Path | None` (glob `*/<id>.jsonl`, newest mtime).
  - `evidence(records: Iterable[dict], origin_of: Callable[[str], str | None]) -> dict`: returns `{"branches": {(owner, repo, branch): [kinds]}, "urls": {pr_url: [kinds]}, "hints": set[pr_url]}`. Kinds: `commit-on-branch`, `push-on-branch` (tool call in a record whose `cwd` maps to owner/repo via `origin_of` and whose `gitBranch` is the branch), `push-names-branch` (push command naming the branch, repo from `git -C <path>` or `cwd`), `push-output` (tool result matching `^\s*[0-9a-f]+\.\.[0-9a-f]+\s+(\S+) -> \1$`), `pr-create` (a `gh pr create` result containing the URL). `pr-link` records only add to `hints`.
  - `discover(gh, session_id, self_login, origin_of) -> list[dict]`: resolves branch evidence to PRs with `gh pr list --repo <o/r> --head <branch> --author <self> --state open --json number,url,headRefName`, URL evidence with `gh pr view <url> --json number,author,state,headRefName,url`; keeps open PRs authored by `self_login`; returns `[{"ref", "url", "branch", "evidence": [kinds]}]`. Hints with no evidence are dropped.
  - `origin_of(path) -> str | None`: `git -C <path> remote get-url origin` parsed to `owner/repo` lowercased, cached; None on failure.
  - `clone_candidates(session_id, owner, repo, origin_of, projects=...) -> list[str]`: distinct `cwd` values and `git -C <path>` paths (from Bash/PowerShell calls) in the session's transcript (falling back, in the CLI, to `holder_clone`: the `worktree` the PR's lease holder recorded in its `watch.json`, when its origin matches) whose `origin_of` equals `owner/repo`, newest first, each mapped to its repo top level (`git -C <cwd> rev-parse --show-toplevel`). CLI `--find-clone <ref> --session-id <id>` prints the first or exits 1 with `pr-watch: no local clone of owner/repo known to this session`. Step 01 calls it for both bare and explicit refs after checking the current directory.

- [ ] **Step 1:** Tests: each of the five evidence kinds adopts; a `pr-link` alone does not; a PR authored by someone else is dropped; a closed PR is dropped; a `git -C D:/x push` with `gitBranch` = `main` but command naming `feat-1` adopts `feat-1`; missing transcript → `discover` returns `[]` and `--discover` prints `[]` with stderr `pr-watch: no transcript for session <id>` and exits 0; `clone_candidates` returns a matching transcript cwd's top level and skips cwds of other repos; `--find-clone` exits 1 with the "no local clone" line when none match.
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement. Tool calls are `assistant` records' `message.content[]` items of `type: tool_use` with `name` `Bash` or `PowerShell` and `input.command`; results are later `user` records' `tool_result` items matched by `tool_use_id`.
- [ ] **Step 4:** Run; expected PASS.
- [ ] **Step 5:** Commit `Discover a session's own PRs from its transcript`.

### Task 7: Old-format watch detection and import

**Files:**
- Create: `skills/pr-tooling/pr-watch/scripts/migrate.py`
- Modify: `poll.py` (`--migrate-scan <main checkout> --session-dir <dir>` and `--migrate-import <main checkout> --session-dir <dir>`)
- Test: `skill-tests/pr-watch/tests/test_migrate.py`

**Interfaces:**
- Produces:
  - `list_processes() -> list[dict]`: `{pid, ppid, name, cmdline}` from `Get-CimInstance Win32_Process | Select ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json` via `powershell -NoProfile` with `CREATE_NO_WINDOW`.
  - `old_monitor(main: Path, procs) -> dict | None`: the python process whose command line contains `poll.py`, `--monitor` and `--state-dir` pointing at `<main>\.pr-autopilot` (case-insensitive, either slash).
  - `claude_ancestor(pid, procs) -> int | None`: first ancestor whose `name` matches `^claude\.exe` (so `claude.exe.old.<ms>.<pid>` matches).
  - `scan(main, claude_pid, procs, now) -> dict`: `{"state": "none"|"owned"|"foreign"|"stale"|"live-unknown", "monitor_pid", "owner_pid", "heartbeat_age", "prs": [keys]}`. `live-unknown` = no monitor process but heartbeat under 300 s.
  - `import_progress(main, session_dir) -> list[str]`: copies each old PR entry's progress fields to the new progress path (skips a key whose progress file already exists), renames `watch.json` → `watch.json.migrated`, deletes `watch-heartbeat` and `watch-poller.json`; returns the imported keys.
  - `identity_ok(claude_pid, my_pid, procs, env) -> str | None`: None when fine; a reason when `CLAUDE_CODE_CHILD_SESSION` is set in `env` or `claude_pid` is not an ancestor of `my_pid`.
  - `leftover_monitors(session_dir, claude_pid, procs) -> list[int]`: pids of `poll.py --monitor --session-dir <session_dir>` processes whose claude ancestor is not `claude_pid` (a resumed session's old poller).
  - `monitor_alive(session_dir, claude_pid, procs, now) -> bool`: true when a `poll.py --monitor --session-dir <session_dir>` process whose claude ancestor is `claude_pid` exists and `watch-heartbeat` is under 300 s old. This is how step 01/02 knows the monitor runs after compaction has dropped the task id. CLI `--monitor-alive --session-dir <dir>` prints `alive` or `down`.
  - CLI: `--check-identity` (exit 1 with the reason on stdout-free stderr line) and `--end-leftover-monitors --session-dir <dir>` (ends each pid's tree with `taskkill /T /F`, `CREATE_NO_WINDOW`; prints the pids).

- [ ] **Step 1:** Tests with injected `procs`: owned (ancestor chain python → bash → `claude.exe.old.1730.4242` = `claude_pid`); foreign (other claude pid); stale (no process, heartbeat 301 s); live-unknown (no process, heartbeat 100 s); `import_progress` keeps `settled_ids`/`posted_reply_ids`/`slack_ts`, lowercases keys, never overwrites an existing progress file, and the old files end renamed/deleted; `identity_ok` refuses a child-session env and a non-ancestor pid; `leftover_monitors` returns an old poller under a dead claude and not the one under `claude_pid`; `monitor_alive` is true for a same-ancestor poller with a fresh heartbeat and false for a stale heartbeat or no process.
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the suite; expected PASS.
- [ ] **Step 5:** Commit `Detect and import old per-repo watches`.

### Task 8: State references and SKILL.md

**Files:**
- Create: `skills/pr-tooling/pr-watch/references/lease-contract.md` (the spec's lease table, status meanings, liveness rule, writers, lowercase paths, `<N>.progress.json` and lock as non-contract; addressed to an outside reader)
- Modify: `skills/pr-tooling/pr-watch/references/watch-state-schema.md` (session files and progress file per the spec's "State"; the per-PR table moves under `<N>.progress.json` unchanged; `watch.json` loses `owner`/`repo`, gains `claude_pid` and per-PR `status`; `push_queue` holds keys)
- Modify: `skills/pr-tooling/pr-watch/SKILL.md` (description, argument-hint, invocation table from the spec incl. `--yes` and `release`, Paths table: `PW_HOME`, `SESSION_DIR`, `POLL`; drop `MAIN`/`STATE_DIR`/`SLUG`; events list adds `lease-lost` and `idle`; hard rule: progress files are written only by the lease holder)

- [ ] **Step 1:** Write the three files.
- [ ] **Step 2:** Run `python scripts/validate.py`. Expected: exit 0.
- [ ] **Step 3:** Commit `Document session-scoped pr-watch state and the lease contract`.

### Task 9: Step files

**Files:**
- Modify: `skills/pr-tooling/pr-watch/steps/01-discover.md` (rewrite §1–§7: fixed values `SESSION_DIR` from `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`; `POLL --check-identity` first, stop on failure; resume from `SESSION_DIR/watch.json`, then `POLL --end-leftover-monitors`; bare discovery via `POLL --discover`; explicit refs via `parse_ref` rules; clone resolution per spec through `POLL --find-clone` when the current directory does not match; old-format handling via `--migrate-scan`/`--migrate-import` with TaskStop or tree kill for `owned`, exclusion line for `foreign` and `live-unknown`; `POLL --claim` per PR with excluded list, one retry on "lease unreadable", and for `taken-over` add the PR to `push_queue` when its progress has `queued_head` or a non-empty `ci_rerun_queued`; `--yes` skips §6's question; any arm clears `stopped_at`; after writing the new entries, `POLL --monitor-alive` decides: `alive` arms no second monitor, `down` arms one per step 02 (covers a monitor that went `idle` while the join was being written, and a task id lost to compaction); under `--dry-run` no `--claim`, no migration, progress copies under `SESSION_DIR/progress/`)
- Modify: `steps/02-arm-monitor.md` (`--session-dir`; description `pr-watch events for this session`; "stream ended" after an `idle` event is a planned end: no re-arm, no "monitor died" line)
- Modify: `steps/03-route-event.md` (key events; `lease-lost` → entry `lost`, one Slack line; `idle` → re-read `watch.json`; when any entry is `armed`, arm a new monitor per step 02, else nothing; a monitor exit code 3 (its claude process gone) is never seen by a live session and needs no route; `closed` sets the entry `closed`; `stop` writes `watch.json` (`stopped_at`, entries `stopped`) before `--lease-status`, `release` writes the entry `released` before `--lease-status released`)
- Modify: `steps/04-fix-path.md` (every "write `watch.json`" for a per-PR field → write the PR's progress file via `state_put.py`; `--repo` from the key; §6 and §8 pending-check scan runs under `POLL --push-lock take` and covers this session's same-repo authored PRs plus `POLL --repo-peers <key>`; `busy` queues like a running check; release the lock once the pushed head shows a check run or 120 s after the push; §2 per outcome C: launch-repo PRs keep `EnterWorktree(path)`; other-repo PRs skip relocation, edit with absolute paths, every git command `git -C <worktree>` incl. §5, §6, §10 and the drain; the fixer brief for an other-repo PR names the worktree root and says to use Read/Grep/Glob on it rather than its git helpers)
- Modify: `steps/05-rereview.md`, `steps/06-notify.md`, `steps/07-ci.md` (progress-file writes, keys, `--repo` from key; 06 posts one line when a PR joins a running watch)
- Modify: `skills/pr-tooling/pr-watch/references/fixer-addendum.md`, `known-bots-overlay.md` (key and path mentions; the addendum says "the repository at `<worktree>`", not "this repository")
- Modify: `skills/pr-tooling/pr-loop-lib/references/fixer-prompt.md`, `references/fixer-verifier-prompt.md`, `steps/04-dispatch-fixers.md`, `steps/04.5-local-verify.md` (the worktree root is an explicit input: prompts name it instead of "this repository"; the `files_changed` check resolves paths against it; local verify runs build/test with it as working directory. When the caller passes no root, behaviour is today's: the cwd)

- [ ] **Step 1:** Edit 01 and 02. Run `python scripts/validate.py`; expected exit 0. Commit `Arm pr-watch per session with leases`.
- [ ] **Step 2:** Edit 03, 04, 05, 06, 07, the two references and the four pr-loop-lib files. `git grep -n "STATE_DIR\|SLUG\|<MAIN>/.pr-autopilot/watch\|--state-dir" skills/pr-tooling/pr-watch` must print only the migration lines in 01. Run the validator; expected exit 0. Commit `Route session-scoped events through the fix, re-review and CI paths`.

### Task 10: Auto-join from pr-autopilot and pr-followup

**Files:**
- Modify: `skills/pr-tooling/pr-autopilot/SKILL.md` (Execution, after step 9 of Phase 5)
- Modify: `skills/pr-tooling/pr-followup/SKILL.md` (Execution step 6)

**Interfaces:**
- Consumes: `~/.claude/pr-watch/sessions/<CLAUDE_CODE_SESSION_ID>/watch.json`.

- [ ] **Step 1:** Add one numbered step to each: when `<PW_HOME>/sessions/<session id>/watch.json` exists, its `dry_run` is false and its `stopped_at` is null, invoke the `pr-watch` skill with `owner/repo#N --yes` for this PR; otherwise do nothing. No heartbeat test: an idle watch (every PR closed) still takes the new PR. Under the calling skill's own `--dry-run`, do nothing.
- [ ] **Step 2:** Run `python scripts/validate.py`; expected exit 0.
- [ ] **Step 3:** Commit `Join a running pr-watch when autopilot or followup finishes`.

### Task 11: Supersede notes in the original design

**Files:** Modify `docs/superpowers/specs/2026-09-11-pr-watch-design.md` §13 rows "State keyed to the repo, two files with one writer each" and "Discovery per repo, not org-wide", and §8's opening sentence: each gets one sentence pointing at `2026-10-28-pr-watch-session-scope-design.md`.

- [ ] **Step 1:** Edit. **Step 2:** Commit `Point the original pr-watch design at the session-scope change`.

### Task 12: Live tests on sandbox repos

**Files:** none committed except the result log appended to this plan under the task.

- [ ] **Step 1:** Create `prpande/prism-sandbox-2` (public) with `README.md`, `calc.py`, and `.github/workflows/check.yml` running `python -c "import calc"` on `pull_request`; clone it beside the local `prism-sandbox` clone. Open PR S2-1 (branch `pw-live-1`) there and PR S1-1 in `prism-sandbox` from a branch this session pushes.
- [ ] **Step 2:** Multi-repo: `/pr-watch prpande/prism-sandbox#<S1-1> prpande/prism-sandbox-2#<S2-1> --yes`. Expected: no question; one monitor; both lease files `armed` with fresh heartbeats; a review comment on each PR from a login other than `prpande` (a workflow step posting as `github-actions[bot]`, added to the sandbox workflows for this) is fixed, pushed and replied on, including the PR outside the launch repo.
- [ ] **Step 3:** Second session: launch a session in `prism-sandbox` and run `/pr-watch prpande/prism-sandbox#<S1-1> --yes`. Expected: excluded with a line naming this session's `[Tag]Name`.
- [ ] **Step 4:** Resume: end this test session, `claude --resume <id>`, run `/pr-watch`. Expected: `reclaimed`, no replay of handled threads.
- [ ] **Step 5:** Takeover: kill the holder session, wait 301 s, arm from another session. Expected: claimed; progress (settled ids, Slack thread) carried.
- [ ] **Step 6:** Auto-join: run `pr-autopilot` for a new PR in the test session with the watch running. Expected: the PR appears in `watch.json` and gets a lease. Then close every watched PR, wait for the `idle` event, and run `pr-autopilot` for one more PR. Expected: a new monitor starts and the PR is `armed`.
- [ ] **Step 6b:** Cross-repo fix: on the `prism-sandbox-2` PR (not the launch repo), a review comment needing a code change is fixed by a pr-fixer with no relocation, local verify runs in that worktree, the commit lands on that PR's branch, and nothing changes in the launch repo's checkout.
- [ ] **Step 7:** Migration: arm the old skill version (`git -C <main> show origin/main:...` copy in a scratch skill dir) on a sandbox PR, then arm the new one in the same session. Expected: old poller gone, `watch.json.migrated` present, progress imported.
- [ ] **Step 8:** Close and delete every sandbox PR and branch the tests opened; record results here.

### Task 13: Final checks

- [ ] **Step 1:** `python scripts/validate.py` → exit 0.
- [ ] **Step 2:** `python -m unittest discover -s skill-tests/pr-watch/tests -v` → all pass.
- [ ] **Step 3:** Walk every comment line the diff adds to `.py` files; delete any that fail the global comment rule.
- [ ] **Step 3b:** Confirm no old-format watch is running: no process whose command line holds `poll.py`, `--monitor` and `--state-dir`. If one is found, tell praty before the merge; the step files carry no guard for it.
- [ ] **Step 4:** Message `[OrchDev]PrAuto` and `[OrchDev]Main` with the PR link and any contract change since the design.
