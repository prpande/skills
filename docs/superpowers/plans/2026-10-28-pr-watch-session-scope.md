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
- [ ] **Step 3:** Implement `pw_paths.py` per the Interfaces block. Reuse `poll.NAME` by importing it (no copy).
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `Add pr-watch keys and state paths`.

### Task 3: Lease module

**Files:**
- Create: `skills/pr-tooling/pr-watch/scripts/lease.py`
- Test: `skill-tests/pr-watch/tests/test_lease.py`

**Interfaces:**
- Consumes: Task 2 paths; `poll.write_json_atomic`, `poll.read_json`.
- Produces:
  - `process_started_at(pid: int) -> float | None`: epoch creation time via `ctypes` (`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetProcessTimes`); `None` when the process does not exist or access fails; non-Windows: `None`.
  - `holder_alive(holder: dict, started_at=process_started_at) -> bool`: true when `started_at(holder["pid"])` is within 2 s of `parse_iso(holder["pid_started_at"])`.
  - `read_lease(owner, repo, n) -> dict | None` (None when missing or unparseable).
  - `claim(owner, repo, n, *, role, holder, explicit, now, started_at=process_started_at) -> tuple[bool, str]`: holder = `{session_id, pid, pid_started_at, poller_pid}`. Returns `(True, "claimed")` / `(True, "reclaimed")` or `(False, reason)`. Rules exactly as the spec's "Claim rules". Writes `status: armed`, fresh `heartbeat`, `stale_after_seconds: 300`, `pending_since: null`, `last_error: null`, keeps `last_head_sha` from an old lease. Holds the claim lock for the read-check-write; a lock file under 60 s old returns `(False, "busy: another claim in progress")`.
  - `set_status(owner, repo, n, status, session_id, now) -> bool`: writes `status` only when `holder.session_id == session_id`; false otherwise.
  - `tick_write(owner, repo, n, *, session_id, now, head, pending_since, last_error, poller_pid, status="armed") -> bool`: rewrites heartbeat-side fields; returns false and writes nothing when the lease's holder is a different session (lost lease).
  - `prune_closed(now) -> int`: deletes `closed` leases (and their progress files) whose `updated_at` is over 7 days old.
  - `armed_peers(owner, repo, exclude_n) -> list[int]`: PR numbers in that repo dir with `status: armed`, any holder, excluding `exclude_n`.
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
- Modify: `skill-tests/pr-watch/tests/fakes.py` (`watch()` builder, `FakeGh` heads query)
- Modify: every `skill-tests/pr-watch/tests/test_poll_*.py` that builds a watch or asserts `"pr": <int>`
- Test: `skill-tests/pr-watch/tests/test_poll_multirepo.py`

**Interfaces:**
- Consumes: Tasks 2 and 3.
- Produces:
  - `load_view(session_dir: Path) -> dict`: reads `watch.json` and each PR's progress file (session-local copy under `<session_dir>/progress/` when `dry_run`), returns `{self_login, bot_allowlist, ado_orgs, push_queue, session_id, claude_pid, prs: {key: {**progress, **entry, "owner", "repo", "number"}}}`. A missing progress file reads as the starting values of step 01 §4 for the role.
  - `tick_query(groups: dict[tuple[str, str], list[int]]) -> tuple[str, dict[str, tuple[str, str]]]`: one query, alias `r<i>` per repo, `p<N>` per PR inside; returns the query and alias → (owner, repo).
  - `tick_once(gh, view, poller, now, force=False) -> list[dict]`: as today, keyed by `owner/repo#N`; events carry `"pr": "<key>"`. A null repo alias warns once per repo and skips only that repo's PRs. Poller `prs` entries gain `review_pending: bool` and `ci_pending: bool` and `pending_since: int|None` (set when either first becomes true, cleared when both false).
  - `monitor(gh, session_dir, sleep, clock, max_ticks=None, write_lease=lease.tick_write) -> int`: after each saved tick, writes every non-closed PR's lease (`status` from the entry: `armed`, or `released` once then never again; `closed` when closed), records `poller_pid` and `claude_pid` in `watch-poller.json`, prunes closed leases once per reconciliation, and returns 0 when no PR in the set is both open and `armed`.
  - CLI: `--session-dir` replaces `--state-dir`; `--baseline/--tails/--findings/--checks` take a ref string; `--report/--reseed` cover the whole set.

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
def test_monitor_exits_when_nothing_armed_and_open(self):  # returns 0 after closed event; lease status closed
def test_released_written_once_then_left(self):
def test_lost_lease_pr_is_reported(self):  # tick_write False -> stderr "lease for o/a#1 is held by another session" and an event {"pr": key, "kind": "lease-lost"}
```

- [ ] **Step 2:** Run the new file. Expected: FAIL.
- [ ] **Step 3:** Change `fakes.watch()` to write a session dir + progress files and return the dir; teach `FakeGh` to answer the aliased multi-repo heads query (`r<i>: repository(owner: "o", name: "a") { p1: ... }`) with `null_repos`. Update existing tests' expected `"pr"` values to keys.
- [ ] **Step 4:** Implement the poll.py changes per the Interfaces block. Evaluate functions take owner/repo from the PR entry, not the view.
- [ ] **Step 5:** Run `python -m unittest discover -s skill-tests/pr-watch/tests -v`. Expected: all PASS (old and new).
- [ ] **Step 6:** Commit `Poll every repo in a session's watch in one query and write leases`.

The `lease-lost` event is new; Task 9 routes it (stop handling that PR, post one line, drop it from `watch.json`).

### Task 5: Claim, status and peers CLI

**Files:**
- Modify: `skills/pr-tooling/pr-watch/scripts/poll.py` (`main`, `run_mode`)
- Test: `skill-tests/pr-watch/tests/test_poll_lease_cli.py`

**Interfaces:**
- Produces CLI modes (all print one line or JSON, exit 0 on success, 1 with a `pr-watch:` stderr line on failure):
  - `--claim <ref> --session-dir <dir> --role authored|reviewed [--explicit]`: holder from `watch.json` (`session_id`, `claude_pid`) and `process_started_at(claude_pid)`. Prints `claimed`/`reclaimed`; on refusal exits 1 with the reason.
  - `--lease-status <ref> --session-dir <dir> --status stopped|released`.
  - `--repo-peers <ref>`: prints JSON list of armed peer keys in the same repo.

- [ ] **Step 1:** Tests: claim then reclaim with the same session; refusal exit code 1 and stderr naming the holder; `--lease-status` by a non-holder exits 1; `--repo-peers` lists another session's armed PR and not a closed one.
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

- [ ] **Step 1:** Tests: each of the five evidence kinds adopts; a `pr-link` alone does not; a PR authored by someone else is dropped; a closed PR is dropped; a `git -C D:/x push` with `gitBranch` = `main` but command naming `feat-1` adopts `feat-1`; missing transcript → `discover` returns `[]` and `--discover` prints `[]` with stderr `pr-watch: no transcript for session <id>` and exits 0.
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

- [ ] **Step 1:** Tests with injected `procs`: owned (ancestor chain python → bash → `claude.exe.old.1730.4242` = `claude_pid`); foreign (other claude pid); stale (no process, heartbeat 301 s); live-unknown (no process, heartbeat 100 s); `import_progress` keeps `settled_ids`/`posted_reply_ids`/`slack_ts`, lowercases keys, never overwrites an existing progress file, and the old files end renamed/deleted.
- [ ] **Step 2:** Run; expected FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the suite; expected PASS.
- [ ] **Step 5:** Commit `Detect and import old per-repo watches`.

### Task 8: State references and SKILL.md

**Files:**
- Create: `skills/pr-tooling/pr-watch/references/lease-contract.md` (the spec's lease table, status meanings, liveness rule, writers, lowercase paths, `<N>.progress.json` and lock as non-contract; addressed to an outside reader)
- Modify: `skills/pr-tooling/pr-watch/references/watch-state-schema.md` (session files and progress file per the spec's "State"; the per-PR table moves under `<N>.progress.json` unchanged; `watch.json` loses `owner`/`repo`, gains `claude_pid` and per-PR `status`; `push_queue` holds keys)
- Modify: `skills/pr-tooling/pr-watch/SKILL.md` (description, argument-hint, invocation table from the spec incl. `--yes` and `release`, Paths table: `PW_HOME`, `SESSION_DIR`, `POLL`; drop `MAIN`/`STATE_DIR`/`SLUG`; events list adds `lease-lost`; hard rule: progress files are written only by the lease holder)

- [ ] **Step 1:** Write the three files.
- [ ] **Step 2:** Run `python scripts/validate.py`. Expected: exit 0.
- [ ] **Step 3:** Commit `Document session-scoped pr-watch state and the lease contract`.

### Task 9: Step files

**Files:**
- Modify: `skills/pr-tooling/pr-watch/steps/01-discover.md` (rewrite §1–§7: fixed values `SESSION_DIR` from `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`; resume from `SESSION_DIR/watch.json`; bare discovery via `POLL --discover`; explicit refs via `parse_ref` rules; clone resolution per spec; old-format handling via `--migrate-scan`/`--migrate-import` with TaskStop or tree kill for `owned`; `POLL --claim` per PR with excluded list; `--yes` skips §6's question; adding refs to a running watch arms no second monitor; under `--dry-run` no `--claim`, no migration, progress copies under `SESSION_DIR/progress/`)
- Modify: `steps/02-arm-monitor.md` (`--session-dir`; description `pr-watch events for this session`; exit 0 of the monitor when nothing is armed is a normal end: do not re-arm until a PR joins; old-format guard in "Stream ended")
- Modify: `steps/03-route-event.md` (key events; `pr` without `/` → migration via step 01 `--yes`; `lease-lost` route; `closed` drops the key from `watch.json`)
- Modify: `steps/04-fix-path.md` (every "write `watch.json`" for a per-PR field → write the PR's progress file via `state_put.py`; `--repo` from the key; §6 and §8 pending-check scan covers this session's same-repo authored PRs plus `POLL --repo-peers <key>`; §2 relocation per Task 1 outcome: A = launch-repo PRs keep `EnterWorktree(path)`, other repos `ExitWorktree(keep)` + absolute paths + `git -C`, return with `EnterWorktree(path: origin_worktree)`; B = other-repo fixers return a unified diff applied with `git -C <worktree> apply`)
- Modify: `steps/05-rereview.md`, `steps/06-notify.md`, `steps/07-ci.md` (progress-file writes, keys, `--repo` from key; 06 posts one line when a PR joins a running watch)
- Modify: `skills/pr-tooling/pr-watch/references/fixer-addendum.md`, `known-bots-overlay.md` (key and path mentions only)

- [ ] **Step 1:** Edit 01 and 02. Run `python scripts/validate.py`; expected exit 0. Commit `Arm pr-watch per session with leases`.
- [ ] **Step 2:** Edit 03, 04, 05, 06, 07 and the two references. `git grep -n "STATE_DIR\|SLUG\|<MAIN>/.pr-autopilot/watch\|--state-dir" skills/pr-tooling/pr-watch` must print only the migration lines in 01, 02 and 03. Run the validator; expected exit 0. Commit `Route session-scoped events through the fix, re-review and CI paths`.

### Task 10: Auto-join from pr-autopilot and pr-followup

**Files:**
- Modify: `skills/pr-tooling/pr-autopilot/SKILL.md` (Execution, after step 9 of Phase 5)
- Modify: `skills/pr-tooling/pr-followup/SKILL.md` (Execution step 6)

**Interfaces:**
- Consumes: `~/.claude/pr-watch/sessions/<CLAUDE_CODE_SESSION_ID>/watch.json` and `watch-heartbeat`.

- [ ] **Step 1:** Add one numbered step to each: when `<PW_HOME>/sessions/<session id>/watch.json` exists, any entry has `status` `armed`, and the heartbeat is under 300 s old, invoke the `pr-watch` skill with `owner/repo#N --yes` for this PR; otherwise do nothing. Under `--dry-run`, do nothing.
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
- [ ] **Step 6:** Auto-join: run `pr-autopilot` for a new PR in the test session with the watch running. Expected: the PR appears in `watch.json` and gets a lease.
- [ ] **Step 7:** Migration: arm the old skill version (`git -C <main> show origin/main:...` copy in a scratch skill dir) on a sandbox PR, then arm the new one in the same session. Expected: old poller gone, `watch.json.migrated` present, progress imported.
- [ ] **Step 8:** Close and delete every sandbox PR and branch the tests opened; record results here.

### Task 13: Final checks

- [ ] **Step 1:** `python scripts/validate.py` → exit 0.
- [ ] **Step 2:** `python -m unittest discover -s skill-tests/pr-watch/tests -v` → all pass.
- [ ] **Step 3:** Walk every comment line the diff adds to `.py` files; delete any that fail the global comment rule.
- [ ] **Step 4:** Message `[OrchDev]PrAuto` and `[OrchDev]Main` with the PR link and any contract change since the design.
