import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from fakes import (NOW, SELF, T0, T1, FakeGh, HomeCase, claim_leases, comment, lease, pk, poll,
                   pull, pw_paths, review, thread, watch, write_session)

A1 = "o/a#1"
B2 = "p/b#2"
B1 = "p/b#1"


def pending_pr(number, head="h2", updated="2026-09-11T10:00:00Z", extra=()):
    return pull(number, head=head, updated=updated,
                threads=[thread("T1", [comment("c1", "reviewer-a", T0), *extra])])


def two_repos(gh):
    gh.prs[pk(1, "o", "a")] = pending_pr(1)
    gh.prs[pk(2, "p", "b")] = pending_pr(2)
    return watch({A1: "authored", B2: "authored"})


class MultiRepoTickTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGh()
        self.poller = {}

    def tick(self, view, now=NOW, force=False):
        return poll.tick_once(self.gh, view, self.poller, now, force=force)

    def test_one_request_covers_two_repos(self):
        events = self.tick(two_repos(self.gh))
        self.assertEqual(self.gh.heads_requests(), 1)
        self.assertEqual({e["pr"] for e in events}, {A1, B2})

    def test_unreachable_repo_does_not_block_the_other(self):
        view = two_repos(self.gh)
        self.gh.null_repos.add(("p", "b"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            events = self.tick(view)
        self.assertEqual([e["pr"] for e in events], [A1])
        self.assertEqual(self.poller["errors"], {B2: "repo unreachable"})
        self.assertEqual(err.getvalue().count("p/b"), 1)

    def test_a_malformed_payload_fails_only_its_own_pr(self):
        view = two_repos(self.gh)
        self.gh.prs[pk(2, "p", "b")]["reviewThreads"] = None
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            events = self.tick(view)
        self.assertEqual([e["pr"] for e in events], [A1])
        self.assertEqual(self.poller["errors"], {B2: "check failed"})
        self.assertIn("PR p/b#2: TypeError", err.getvalue())
        self.assertNotIn(B2, self.poller["prs"])

    def test_a_pr_with_unreadable_progress_is_not_queried(self):
        view = two_repos(self.gh)
        view["prs"][B2]["load_fault"] = "progress unreadable"
        events = self.tick(view)
        self.assertEqual([e["pr"] for e in events], [A1])
        self.assertEqual(self.poller["errors"], {B2: "progress unreadable"})
        self.assertFalse(any('"b"' in c[3] for c in self.gh.calls if c[:2] == ["api", "graphql"]))

    def test_same_number_in_two_repos(self):
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1, head="ha")
        self.gh.prs[pk(1, "p", "b")] = pending_pr(1, head="hb")
        view = watch({A1: "authored", B1: "authored"})
        self.tick(view)
        self.assertEqual(self.poller["heads"], {A1: "ha", B1: "hb"})
        self.assertEqual({k: v["last_head"] for k, v in self.poller["prs"].items()},
                         {A1: "ha", B1: "hb"})

    def test_pending_since_set_then_cleared(self):
        view = watch({1: "authored"}, owner="o", repo="a")
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.tick(view)
        self.assertEqual(self.poller["prs"][A1]["pending_since"], NOW)
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1, updated="2026-09-11T11:00:00Z",
                                                  extra=[comment("c2", "reviewer-a", T1)])
        self.tick(view, now=NOW + 30)
        self.assertEqual(self.poller["prs"][A1]["pending_since"], NOW)
        view["prs"][A1]["settled_ids"] = ["c1", "c2"]
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1, updated="2026-09-11T12:00:00Z")
        self.tick(view, now=NOW + 60)
        entry = self.poller["prs"][A1]
        self.assertEqual((entry["review_pending"], entry["pending_since"]), (False, None))

    def test_pending_stays_set_when_the_same_set_is_not_emitted_again(self):
        view = watch({1: "authored"}, owner="o", repo="a")
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.tick(view)
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1, updated="2026-09-11T11:00:00Z")
        self.assertEqual(self.tick(view, now=NOW + 60), [])
        self.assertTrue(self.poller["prs"][A1]["review_pending"])

    def test_changed_progress_alone_re_evaluates_and_clears_pending(self):
        view = watch({1: "authored"}, owner="o", repo="a")
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.tick(view)
        self.assertEqual(self.poller["prs"][A1]["pending_since"], NOW)
        view["prs"][A1]["settled_ids"] = ["c1"]
        self.tick(view, now=NOW + 60)
        entry = self.poller["prs"][A1]
        self.assertEqual((entry["review_pending"], entry["pending_since"]), (False, None))

    def reviewed_push(self, changed):
        view = watch({2: "reviewed"}, owner="o", repo="a")
        self.gh.prs[pk(2, "o", "a")] = pull(
            2, author_login="author-b", head="h2",
            threads=[thread("T9", [comment("m1", SELF, T0)], path="src/B.cs")],
            reviews=[review("r1", SELF, T0, oid="h1")])
        self.gh.compare["h1...h2"] = changed
        self.tick(view)
        return self.poller["prs"]["o/a#2"]["review_pending"]

    def test_reviewed_push_touching_a_thread_is_pending(self):
        self.assertTrue(self.reviewed_push(["src/B.cs"]))

    def test_reviewed_push_touching_no_thread_is_not_pending(self):
        self.assertFalse(self.reviewed_push(["src/Z.cs"]))

    def test_pending_flags_from_live_data(self):
        view = watch({1: "authored", 2: "reviewed"}, owner="o", repo="a")
        self.gh.prs[pk(1, "o", "a")] = pull(1)
        self.gh.prs[pk(2, "o", "a")] = pull(
            2, author_login="author-b", head="h1",
            threads=[thread("T9", [comment("m1", SELF, T0)], resolved=True)],
            reviews=[review("r1", SELF, T0, oid="h1")])
        self.gh.rollup[pk(1, "o", "a")] = "SUCCESS"
        self.poller["prs"] = {A1: {"last_ci_signature": "ci:h2:old|x|2026", "ci_pending": True}}
        self.tick(view)
        self.assertEqual(self.poller["prs"][A1]["ci_pending"], False)
        reviewed = self.poller["prs"]["o/a#2"]
        self.assertEqual((reviewed["review_pending"], reviewed["ci_pending"]), (False, False))
        self.assertEqual(reviewed["last_signature"], "settled")

    def test_red_check_is_ci_pending_until_it_is_handled(self):
        view = watch({1: "authored"}, owner="o", repo="a")
        key = pk(1, "o", "a")
        self.gh.prs[key] = pull(1)
        self.gh.rollup[key] = "FAILURE"
        self.gh.checks[key] = [{"name": "Unit", "state": "FAILURE", "bucket": "fail",
                                "link": "", "workflow": "W", "completedAt": "t1"}]
        self.tick(view)
        self.assertTrue(self.poller["prs"][A1]["ci_pending"])
        view["prs"][A1]["ci_handled"] = ["h2|W|Unit|t1"]
        self.tick(view, now=NOW + 60)
        entry = self.poller["prs"][A1]
        self.assertEqual((entry["ci_pending"], entry["pending_since"]), (False, None))


class RunGhTests(unittest.TestCase):
    def test_run_gh_hides_window_on_windows(self):
        done = mock.Mock(returncode=0, stdout="{}", stderr="")
        with mock.patch.object(os, "name", "nt"), \
                mock.patch.object(poll.subprocess, "CREATE_NO_WINDOW", 134217728, create=True), \
                mock.patch.object(poll.subprocess, "run", return_value=done) as run:
            poll.run_gh(["api", "user"])
        self.assertEqual(run.call_args.kwargs["creationflags"], 134217728)


class LoadViewTests(HomeCase):
    def session(self, dry_run=False):
        directory = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        (directory / "watch.json").write_text(json.dumps({
            "session_id": "s-1", "self_login": SELF, "dry_run": dry_run,
            "prs": {A1: {"role": "authored", "status": "armed"},
                    B2: {"role": "reviewed", "status": "armed"}}}), encoding="utf-8")
        return directory

    def test_a_missing_progress_file_reads_as_the_starting_values_for_the_role(self):
        view = poll.load_view(self.session())
        authored, reviewed = view["prs"][A1], view["prs"][B2]
        self.assertEqual((authored["ci_handled"], authored["ci_fix_pushes"], authored["queued_head"]),
                         ([], 0, None))
        self.assertEqual((reviewed["finding_verdicts"], reviewed["rereviewed_head"]), ({}, None))
        self.assertNotIn("ci_handled", reviewed)
        self.assertEqual((authored["owner"], authored["repo"], authored["number"]), ("o", "a", 1))

    def test_dry_run_reads_progress_from_the_session_directory(self):
        directory = self.session(dry_run=True)
        local = directory / "progress" / "o" / "a" / "1.progress.json"
        local.parent.mkdir(parents=True)
        local.write_text(json.dumps({"settled_ids": ["x"]}), encoding="utf-8")
        shared = pw_paths.progress_path("o", "a", 1)
        shared.parent.mkdir(parents=True)
        shared.write_text(json.dumps({"settled_ids": ["shared"]}), encoding="utf-8")
        view = poll.load_view(directory)
        self.assertEqual(view["prs"][A1]["settled_ids"], ["x"])
        shared.unlink()
        directory2 = self.session(dry_run=False)
        self.assertEqual(poll.load_view(directory2)["prs"][A1]["settled_ids"], [])

    def test_a_malformed_entry_is_skipped_and_the_rest_load(self):
        directory = self.session()
        watch_file = directory / "watch.json"
        data = json.loads(watch_file.read_text(encoding="utf-8"))
        data["prs"]["not a ref"] = {"role": "authored", "status": "armed"}
        data["prs"]["o/a#7"] = "armed"
        watch_file.write_text(json.dumps(data), encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            view = poll.load_view(directory)
        self.assertEqual(sorted(view["prs"]), [A1, B2])
        self.assertEqual(err.getvalue().count("skipped"), 2)

    def test_an_unreadable_progress_file_marks_the_pr(self):
        directory = self.session()
        shared = pw_paths.progress_path("o", "a", 1)
        shared.parent.mkdir(parents=True)
        shared.write_text("{not json", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            view = poll.load_view(directory)
        self.assertEqual(view["prs"][A1]["load_fault"], "progress unreadable")
        self.assertEqual(view["prs"][A1]["settled_ids"], [])
        self.assertIsNone(view["prs"][B2]["load_fault"])


class MonitorCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.state = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.gh = FakeGh()

    def start(self, view, claim=True, session_id="s-1"):
        write_session(self.state, view)
        if claim:
            claim_leases(view, session_id=session_id)

    def run_monitor(self, ticks=1, clock=NOW, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = poll.monitor(self.gh, self.state, sleep=lambda s: None,
                                clock=lambda: clock, max_ticks=ticks, **kwargs)
        events = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        return events, err.getvalue(), code

    def lease(self, n=1, owner="o", repo="a"):
        return lease.read_lease(owner, repo, n)

    def lease_bytes(self, n=1, owner="o", repo="a"):
        return pw_paths.lease_path(owner, repo, n).read_bytes()


class MonitorLeaseTests(MonitorCase):
    def test_monitor_writes_lease_each_tick(self):
        view = two_repos(self.gh)
        self.start(view)
        self.run_monitor(1)
        for n, owner, repo, head in ((1, "o", "a", "h2"), (2, "p", "b", "h2")):
            held = self.lease(n, owner, repo)
            self.assertEqual(held["heartbeat"], pw_paths.iso_utc(NOW))
            self.assertEqual(held["last_head_sha"], head)
            self.assertEqual(held["pending_since"], pw_paths.iso_utc(NOW))
            self.assertEqual((held["status"], held["last_error"]), ("armed", None))
            self.assertEqual(held["holder"]["poller_pid"], os.getpid())
        self.run_monitor(1, clock=NOW + 60)
        self.assertEqual(self.lease()["heartbeat"], pw_paths.iso_utc(NOW + 60))
        self.assertEqual(self.lease()["pending_since"], pw_paths.iso_utc(NOW))

    def test_monitor_records_its_pids_for_the_ancestry_check(self):
        view = watch({A1: "authored"})
        view["claude_pid"] = 4242
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view)
        self.run_monitor(1, started_at=lambda pid: NOW - 100, holder_alive=lambda h, s=None: True)
        recorded = json.loads((self.state / "watch-poller.json").read_text(encoding="utf-8"))
        self.assertEqual((recorded["poller_pid"], recorded["claude_pid"]), (os.getpid(), 4242))
        self.assertEqual(recorded["claude_started_at"], pw_paths.iso_utc(NOW - 100))

    def test_monitor_exits_idle_when_nothing_armed(self):
        view = watch({A1: "authored"})
        merged = pending_pr(1)
        merged["state"] = "MERGED"
        self.gh.prs[pk(1, "o", "a")] = merged
        self.start(view)
        events, _, code = self.run_monitor(5)
        self.assertEqual(code, 0)
        self.assertEqual([e["kind"] for e in events], ["closed", "idle"])
        self.assertEqual(self.lease()["status"], "closed")

    def test_a_closing_write_that_finds_the_lease_busy_is_retried(self):
        view = watch({A1: "authored"})
        merged = pending_pr(1)
        merged["state"] = "MERGED"
        self.gh.prs[pk(1, "o", "a")] = merged
        self.start(view)
        calls = []

        def busy_once(*args, **kwargs):
            calls.append(kwargs["status"])
            if len(calls) == 1:
                return "busy"
            return lease.tick_write(*args, **kwargs)

        events, _, code = self.run_monitor(3, write_lease=busy_once)
        self.assertEqual(calls, ["closed", "closed"])
        self.assertEqual(code, 0)
        self.assertEqual([e["kind"] for e in events], ["closed", "idle"])
        self.assertEqual(self.lease()["status"], "closed")

    def test_closed_pr_counts_as_not_armed(self):
        view = watch({A1: "authored", B2: "authored"})
        view["prs"][B2]["status"] = "stopped"
        merged = pending_pr(1)
        merged["state"] = "CLOSED"
        self.gh.prs[pk(1, "o", "a")] = merged
        self.gh.prs[pk(2, "p", "b")] = pending_pr(2)
        self.start(view)
        events, _, _ = self.run_monitor(5)
        self.assertEqual([e["kind"] for e in events], ["closed", "idle"])
        self.assertEqual(self.lease()["status"], "closed")
        self.assertEqual(self.lease(2, "p", "b")["heartbeat"], pw_paths.iso_utc(NOW))

    def test_a_closed_pr_does_not_end_the_watch_while_another_is_open(self):
        view = two_repos(self.gh)
        self.gh.prs[pk(1, "o", "a")]["state"] = "MERGED"
        self.start(view)
        events, _, _ = self.run_monitor(2)
        self.assertEqual([(e["kind"], e["pr"]) for e in events if "pr" in e],
                         [("closed", A1), ("pending", B2)])
        self.assertNotIn("idle", [e["kind"] for e in events])

    def test_released_entry_is_not_ticked(self):
        view = two_repos(self.gh)
        view["prs"][A1]["status"] = "released"
        self.start(view)
        before = self.lease_bytes()
        events, _, _ = self.run_monitor(1)
        self.assertEqual([e["pr"] for e in events], [B2])
        self.assertEqual(self.lease_bytes(), before)
        self.assertFalse(any('pullRequest(number: 1)' in c[3] for c in self.gh.calls
                             if c[:2] == ["api", "graphql"] and '"a"' in c[3]))

    def test_tick_never_rearms_a_released_lease(self):
        view = watch({A1: "authored"})
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view)
        lease.set_status("o", "a", 1, "released", "s-1", NOW)
        before = self.lease_bytes()
        events, err, _ = self.run_monitor(2, clock=NOW + 60)
        self.assertEqual(self.lease_bytes(), before)
        self.assertEqual(events, [{"kind": "idle"}])
        self.assertEqual(err, "")

    def test_inactive_pr_is_dropped_from_ticks(self):
        view = two_repos(self.gh)
        self.start(view)
        lease.set_status("o", "a", 1, "released", "s-1", NOW)
        events, _, _ = self.run_monitor(3)
        self.assertEqual([e["pr"] for e in events if e["kind"] == "pending"], [B2])
        later = [c[3] for c in self.gh.calls if c[:2] == ["api", "graphql"]
                 and 'repository(owner: "' in c[3]][1:]
        self.assertTrue(later)
        self.assertFalse(any("pullRequest(number: 1)" in q and '"a"' in q for q in later))

    def test_unreadable_lease_after_a_loss_still_prints_the_tick(self):
        view = watch({A1: "authored"})
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view)
        with mock.patch.object(lease, "read_with_retry", side_effect=PermissionError("locked")):
            events, _, _ = self.run_monitor(1, write_lease=lambda *a, **k: "lost")
        self.assertIn({"pr": A1, "kind": "lease-lost", "holder": None}, events)

    def test_claude_pid_is_read_from_watch_json_only(self):
        view = watch({A1: "authored"})
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view)

        def never(pid):
            raise AssertionError("the environment must not name the claude process")
        with mock.patch.dict(os.environ, {"CLAUDE_PID": "4242"}):
            events, _, code = self.run_monitor(1, started_at=never)
        self.assertEqual((code, [e["kind"] for e in events]), (0, ["pending"]))

    def test_monitor_exits_before_any_write_when_claude_was_gone_at_start_on_windows(self):
        view = watch({A1: "authored"})
        view["claude_pid"] = 4242
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view)
        before = self.lease_bytes()
        with mock.patch.object(poll, "IS_WINDOWS", True):
            events, _, code = self.run_monitor(2, clock=NOW + 500, started_at=lambda pid: None)
        self.assertEqual((code, events), (3, []))
        self.assertEqual(self.lease_bytes(), before)
        self.assertFalse((self.state / "watch-heartbeat").exists())

    def test_the_start_time_check_is_skipped_off_windows(self):
        view = watch({A1: "authored"})
        view["claude_pid"] = 4242
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view)
        with mock.patch.object(poll, "IS_WINDOWS", False):
            events, _, code = self.run_monitor(1, started_at=lambda pid: None)
        self.assertEqual((code, [e["kind"] for e in events]), (0, ["pending"]))

    def test_lost_lease_pr_is_reported_once(self):
        view = two_repos(self.gh)
        write_session(self.state, view)
        claim_leases(watch({A1: "authored"}), session_id="s-2")
        claim_leases(watch({B2: "authored"}), session_id="s-1")
        before = self.lease_bytes()
        events, err, _ = self.run_monitor(3)
        lost = [e for e in events if e["kind"] == "lease-lost"]
        self.assertEqual(lost, [{"pr": A1, "kind": "lease-lost", "holder": "s-2"}])
        self.assertEqual(err.count("lease for o/a#1 is held by another session"), 1)
        self.assertEqual([e["pr"] for e in events if e["kind"] == "pending"], [B2])
        self.assertEqual(self.lease_bytes(), before)

    def test_a_lost_pr_leaves_the_tick_queue_and_its_loss_prints_first(self):
        view = two_repos(self.gh)
        view["push_queue"] = [A1, B2]
        write_session(self.state, view)
        claim_leases(watch({A1: "authored"}), session_id="s-2")
        claim_leases(watch({B2: "authored"}), session_id="s-1")
        events, _, _ = self.run_monitor(1)
        kinds = [e["kind"] for e in events]
        self.assertLess(kinds.index("lease-lost"), kinds.index("tick"))
        self.assertEqual([e["push_queue"] for e in events if e["kind"] == "tick"], [[B2]])

    def test_released_lease_is_silent(self):
        view = watch({A1: "authored"})
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view)
        lease.set_status("o", "a", 1, "released", "s-1", NOW)
        events, err, _ = self.run_monitor(1)
        self.assertNotIn("lease-lost", [e["kind"] for e in events])
        self.assertEqual(err, "")

    def test_a_missing_lease_warns_once_and_events_still_flow(self):
        view = watch({A1: "authored"})
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view, claim=False)
        events, err, _ = self.run_monitor(3)
        self.assertEqual(err.count("no lease file for o/a#1"), 1)
        self.assertEqual([e["kind"] for e in events], ["pending"])

    def test_unreachable_repo_gets_last_error(self):
        view = two_repos(self.gh)
        self.start(view)
        lease.tick_write("p", "b", 2, session_id="s-1", now=NOW - 500, head="old",
                         pending_since=None, last_error=None, poller_pid=1)
        self.gh.null_repos.add(("p", "b"))
        _, _, _ = self.run_monitor(1)
        held = self.lease(2, "p", "b")
        self.assertEqual(held["heartbeat"], pw_paths.iso_utc(NOW))
        self.assertEqual((held["last_head_sha"], held["last_error"]), ("old", "repo unreachable"))
        self.gh.null_repos.clear()
        self.run_monitor(1, clock=NOW + 60)
        held = self.lease(2, "p", "b")
        self.assertEqual((held["last_head_sha"], held["last_error"]), ("h2", None))

    def test_a_failed_pr_check_gets_last_error_and_the_watch_keeps_running(self):
        view = two_repos(self.gh)
        self.start(view)
        self.gh.fail.add(("p", "b", 2))
        events, err, code = self.run_monitor(1)
        self.assertEqual(([e["pr"] for e in events], code), ([A1], 0))
        self.assertEqual(self.lease(2, "p", "b")["last_error"], "check failed")
        self.assertIsNone(self.lease()["last_error"])
        self.gh.fail.clear()
        self.run_monitor(1, clock=NOW + 60)
        self.assertIsNone(self.lease(2, "p", "b")["last_error"])

    def test_an_unreadable_progress_file_keeps_the_lease_armed_with_an_error(self):
        view = watch({A1: "authored"})
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view)
        pw_paths.progress_path("o", "a", 1).write_text("{not json", encoding="utf-8")
        events, err, _ = self.run_monitor(2)
        self.assertEqual(events, [])
        held = self.lease()
        self.assertEqual((held["status"], held["last_error"]), ("armed", "progress unreadable"))
        self.assertIn("progress file unreadable", err)

    def test_monitor_exits_when_claude_is_gone(self):
        view = watch({A1: "authored"})
        view["claude_pid"] = 4242
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view)
        answers = iter([True, False])
        events, _, code = self.run_monitor(
            5, clock=NOW + 500, started_at=lambda pid: NOW - 100,
            holder_alive=lambda holder, started_at=None: next(answers))
        self.assertEqual(code, 3)
        self.assertEqual([e["kind"] for e in events], ["pending"])
        self.assertEqual(self.lease()["heartbeat"], pw_paths.iso_utc(NOW + 500))
        before = self.lease_bytes()
        events, _, code = self.run_monitor(
            5, clock=NOW + 900, started_at=lambda pid: NOW - 100,
            holder_alive=lambda holder, started_at=None: False)
        self.assertEqual((code, events), (3, []))
        self.assertEqual(self.lease_bytes(), before)

    def test_dry_run_monitor_writes_no_lease(self):
        view = watch({A1: "authored"}, dry_run=True)
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view, claim=False)
        claim_leases(watch({A1: "authored"}), session_id="s-2")
        before = self.lease_bytes()
        events, err, _ = self.run_monitor(2)
        self.assertEqual([e["kind"] for e in events], ["pending"])
        self.assertEqual(self.lease_bytes(), before)
        self.assertEqual(err, "")

    def test_dry_run_monitor_creates_no_lease_files(self):
        view = watch({A1: "authored"}, dry_run=True)
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view, claim=False)
        self.run_monitor(1)
        self.assertFalse(pw_paths.lease_path("o", "a", 1).exists())

    def stale_closed_lease(self):
        stale = {"schema": 1, "owner": "o", "repo": "a", "number": 9, "role": "authored",
                 "holder": {"session_id": "s-9"}, "heartbeat": pw_paths.iso_utc(NOW - 10**7),
                 "stale_after_seconds": 300, "status": "closed", "last_head_sha": None,
                 "pending_since": None, "last_error": None,
                 "updated_at": pw_paths.iso_utc(NOW - 10**7)}
        path = pw_paths.lease_path("o", "a", 9)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stale), encoding="utf-8")
        return path

    def test_reconciliation_prunes_old_closed_leases(self):
        view = watch({A1: "authored"})
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view)
        old = self.stale_closed_lease()
        self.run_monitor(1)
        self.assertFalse(old.exists())

    def test_dry_run_prunes_nothing(self):
        view = watch({A1: "authored"}, dry_run=True)
        self.gh.prs[pk(1, "o", "a")] = pending_pr(1)
        self.start(view, claim=False)
        old = self.stale_closed_lease()
        self.run_monitor(1)
        self.assertTrue(old.exists())


if __name__ == "__main__":
    unittest.main()
