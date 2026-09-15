import contextlib
import io
import json
import pathlib
import tempfile
import unittest
import unittest.mock

from fakes import (ACTIONS, NOW, SELF, T0, T1, FakeGh, comment, poll, pull, review, thread,
                   watch)


def authored_pr(updated="2026-09-11T10:00:00Z", extra=()):
    return pull(1411, threads=[thread("T1", [comment("c1", "reviewer-a", T0), *extra])],
                updated=updated)


def reviewed_pr(head="h1", replies=(), updated="2026-09-11T10:00:00Z"):
    return pull(1420, author_login="author-b", head=head, updated=updated,
                threads=[thread("T9", [comment("m1", SELF, T0), *replies], path="src/B.cs")],
                reviews=[review("r1", SELF, T0, oid="h1")])


class AuthoredTickTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGh()
        self.watch = watch({1411: "authored"})
        self.poller = {}

    def tick(self, now=NOW, force=False):
        return poll.tick_once(self.gh, self.watch, self.poller, now, force=force)

    def test_first_tick_emits_pending(self):
        self.gh.prs[1411] = authored_pr()
        self.assertEqual(self.tick(), [{"pr": 1411, "role": "authored", "kind": "pending",
                                        "threads": ["T1"], "comments": [], "reviews": []}])

    def test_unchanged_pr_is_neither_fetched_nor_reported(self):
        self.gh.prs[1411] = authored_pr()
        self.tick()
        before = self.gh.thread_fetches()
        for _ in range(3):
            self.assertEqual(self.tick(), [])
        self.assertEqual(self.gh.thread_fetches(), before)

    def test_same_pending_set_is_not_emitted_twice(self):
        self.gh.prs[1411] = authored_pr()
        self.tick()
        self.gh.prs[1411] = authored_pr(updated="2026-09-11T11:00:00Z")
        self.assertEqual(self.tick(), [])

    def test_new_comment_emits_again(self):
        self.gh.prs[1411] = authored_pr()
        self.tick()
        self.gh.prs[1411] = authored_pr(updated="2026-09-11T11:00:00Z",
                                        extra=[comment("c2", "reviewer-a", T1)])
        self.assertEqual(len(self.tick()), 1)

    def test_forced_pass_re_emits_an_unhandled_set(self):
        self.gh.prs[1411] = authored_pr()
        self.tick()
        self.assertEqual(len(self.tick(force=True)), 1)

    def test_head_move_with_nothing_pending_emits_nothing(self):
        self.watch["prs"]["1411"]["settled_ids"] = ["c1"]
        self.gh.prs[1411] = authored_pr()
        self.assertEqual(self.tick(), [])
        moved = authored_pr(updated="2026-09-11T11:00:00Z")
        moved["headRefOid"] = "h3"
        self.gh.prs[1411] = moved
        self.assertEqual(self.tick(), [])

    def test_closed_pr_emits_once_and_is_no_longer_polled(self):
        pr = authored_pr()
        pr["state"] = "MERGED"
        self.gh.prs[1411] = pr
        self.assertEqual(self.tick(), [{"pr": 1411, "kind": "closed", "state": "MERGED"}])
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.poller["closed"], [1411])

    def test_a_closed_pr_removed_then_re_added_and_reopened_is_polled_again(self):
        pr = authored_pr()
        pr["state"] = "CLOSED"
        self.gh.prs[1411] = pr
        self.assertEqual([e["kind"] for e in self.tick()], ["closed"])
        entry = self.watch["prs"].pop("1411")
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.poller["closed"], [])
        self.watch["prs"]["1411"] = entry
        self.gh.prs[1411] = authored_pr()
        self.assertEqual([e["kind"] for e in self.tick()], ["pending"])

    def test_partial_heads_response_still_serves_the_prs_that_resolved(self):
        self.watch = watch({1411: "authored", 1413: "authored"})
        self.gh.prs[1411] = authored_pr()
        self.gh.prs[1413] = pull(1413, threads=[thread("T3", [comment("c9", "reviewer-a", T0)])])
        self.gh.partial_heads = {1413}
        with contextlib.redirect_stderr(io.StringIO()) as err:
            events = self.tick()
        self.assertEqual([e["pr"] for e in events], [1411])
        self.assertIn("PR #1413: null alias", err.getvalue())

    def test_fetch_error_on_one_pr_does_not_stop_the_others(self):
        self.watch = watch({1411: "authored", 1413: "authored"})
        self.gh.prs[1411] = authored_pr()
        self.gh.prs[1413] = pull(1413, threads=[thread("T3", [comment("c9", "reviewer-a", T0)])])
        self.gh.fail = {1411}
        with contextlib.redirect_stderr(io.StringIO()):
            events = self.tick()
        self.assertEqual([e["pr"] for e in events], [1413])
        self.assertNotIn("1411", self.poller["prs"])

    def test_null_alias_is_skipped_not_closed(self):
        self.gh.prs[1411] = None
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(self.tick(), [])
        self.assertIn("1411", err.getvalue())
        self.assertEqual(self.poller.get("closed", []), [])


class PushQueueTickTests(unittest.TestCase):
    def test_tick_event_on_change_then_only_after_the_retry_window(self):
        gh, poller = FakeGh(), {}
        w = watch({}, push_queue=[1413])
        self.assertEqual(poll.tick_once(gh, w, poller, NOW),
                         [{"kind": "tick", "push_queue": [1413]}])
        self.assertEqual(poll.tick_once(gh, w, poller, NOW + 60), [])
        later = NOW + poll.TICK_EVENT_RETRY_SECONDS
        self.assertEqual(len(poll.tick_once(gh, w, poller, later)), 1)

    def test_empty_queue_emits_no_tick(self):
        self.assertEqual(poll.tick_once(FakeGh(), watch({}), {}, NOW), [])


class ReviewedTickTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGh()
        self.watch = watch({1420: "reviewed"})
        self.poller = {}

    def tick(self):
        return poll.tick_once(self.gh, self.watch, self.poller, NOW)

    def test_head_move_over_a_file_i_flagged_emits_head_moved(self):
        self.gh.prs[1420] = reviewed_pr(head="h2")
        self.gh.compare["h1...h2"] = ["src/B.cs"]
        self.assertEqual(self.tick(), [{"pr": 1420, "role": "reviewed", "kind": "head-moved",
                                        "old_head": "h1", "new_head": "h2",
                                        "touches_my_findings": True, "author_replied": False}])

    def test_head_move_elsewhere_without_a_reply_is_silent(self):
        self.gh.prs[1420] = reviewed_pr(head="h2")
        self.gh.compare["h1...h2"] = ["src/Other.cs"]
        self.assertEqual(self.tick(), [])

    def test_author_reply_after_a_quiet_head_move_emits_head_moved(self):
        self.gh.prs[1420] = reviewed_pr(head="h2")
        self.gh.compare["h1...h2"] = ["src/Other.cs"]
        self.tick()
        self.gh.prs[1420] = reviewed_pr(head="h2", updated="2026-09-11T11:00:00Z",
                                        replies=[comment("a1", "author-b", T1)])
        events = self.tick()
        self.assertEqual(events[0]["kind"], "head-moved")
        self.assertTrue(events[0]["author_replied"])

    def test_author_reply_without_a_push_emits_reply(self):
        self.gh.prs[1420] = reviewed_pr(head="h1", replies=[comment("a1", "author-b", T1)])
        self.assertEqual(self.tick(), [{"pr": 1420, "role": "reviewed", "kind": "reply",
                                        "threads": ["T9"]}])

    def test_a_compare_with_no_files_list_does_not_raise(self):
        self.gh.prs[1420] = reviewed_pr(head="h2")
        self.gh.compare["h1...h2"] = None
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(self.tick(), [])
        self.assertEqual(err.getvalue(), "")

    def test_a_compare_at_the_file_cap_counts_as_touching_my_findings(self):
        self.gh.prs[1420] = reviewed_pr(head="h2")
        self.gh.compare["h1...h2"] = [f"src/F{i}.cs" for i in range(300)]
        events = self.tick()
        self.assertEqual([e["kind"] for e in events], ["head-moved"])
        self.assertTrue(events[0]["touches_my_findings"])

    def test_a_re_reviewed_head_is_the_start_of_the_compare(self):
        self.watch["prs"]["1420"]["rereviewed_head"] = "h2"
        self.gh.prs[1420] = reviewed_pr(head="h3")
        self.gh.compare["h2...h3"] = ["src/B.cs"]
        events = self.tick()
        self.assertEqual((events[0]["old_head"], events[0]["new_head"]), ("h2", "h3"))
        self.assertTrue(any(c[1] == "repos/o/r/compare/h2...h3" for c in self.gh.calls))
        self.assertFalse(any("h1...h3" in c[1] for c in self.gh.calls))

    def test_all_my_threads_resolved_with_no_later_reply_settles_once(self):
        pr = reviewed_pr(head="h2")
        pr["reviewThreads"]["nodes"][0]["isResolved"] = True
        self.gh.prs[1420] = pr
        self.gh.compare["h1...h2"] = ["src/B.cs"]
        self.assertEqual(self.tick(), [{"pr": 1420, "role": "reviewed", "kind": "settled"}])
        pr["updatedAt"] = "2026-09-11T11:00:00Z"
        self.assertEqual(self.tick(), [])

    def test_a_resolved_thread_with_a_reply_after_mine_is_not_settled(self):
        pr = reviewed_pr(head="h1", replies=[comment("a1", "author-b", T1)])
        pr["reviewThreads"]["nodes"][0]["isResolved"] = True
        self.gh.prs[1420] = pr
        self.assertEqual([e["kind"] for e in self.tick()], ["reply"])

    def test_an_escalated_reply_after_mine_on_a_resolved_thread_still_settles(self):
        pr = reviewed_pr(head="h1", replies=[comment("a1", "author-b", T1, body="thanks")])
        pr["reviewThreads"]["nodes"][0]["isResolved"] = True
        self.gh.prs[1420] = pr
        self.watch["prs"]["1420"]["escalated_ids"] = ["a1"]
        self.assertEqual(self.tick(), [{"pr": 1420, "role": "reviewed", "kind": "settled"}])

    def test_a_reviewed_pr_is_re_emitted_once_when_its_retry_time_passes(self):
        self.gh.prs[1420] = reviewed_pr(head="h1", replies=[comment("a1", "author-b", T1)])
        self.assertEqual([e["kind"] for e in self.tick()], ["reply"])
        self.watch["prs"]["1420"]["retry_after"] = NOW + 600
        self.assertEqual(poll.tick_once(self.gh, self.watch, self.poller, NOW + 60), [])
        self.assertEqual([e["kind"] for e in poll.tick_once(self.gh, self.watch, self.poller,
                                                            NOW + 600)], ["reply"])
        self.assertEqual(poll.tick_once(self.gh, self.watch, self.poller, NOW + 660), [])

    def test_one_unresolved_thread_is_not_settled(self):
        pr = reviewed_pr(head="h1")
        pr["reviewThreads"]["nodes"].append(
            thread("T10", [comment("m2", SELF, T0)], resolved=True, path="src/C.cs"))
        self.gh.prs[1420] = pr
        self.assertEqual(self.tick(), [])

    def test_pr_without_my_threads_is_ignored(self):
        self.gh.prs[1420] = pull(1420, author_login="author-b", head="h2",
                                 threads=[thread("T1", [comment("c1", "reviewer-a", T0)])])
        self.assertEqual(self.tick(), [])


class RetryAfterTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGh()
        self.gh.prs[1411] = authored_pr()
        self.gh.rollup[1411] = "FAILURE"
        self.gh.checks[1411] = [{"name": "Gated / Unit Tests", "state": "FAILURE",
                                 "bucket": "fail", "link": ACTIONS, "workflow": "App Gated",
                                 "completedAt": "2026-09-10T05:16:39Z"}]
        self.watch = watch({1411: "authored"})
        self.poller = {}
        self.assertEqual([e["kind"] for e in self.tick(NOW)], ["pending", "ci-red"])

    def tick(self, now):
        return poll.tick_once(self.gh, self.watch, self.poller, now)

    def test_a_skip_is_re_emitted_once_when_its_retry_time_passes(self):
        self.watch["prs"]["1411"]["retry_after"] = NOW + 600
        self.assertEqual(self.tick(NOW + 60), [])
        self.assertEqual([e["kind"] for e in self.tick(NOW + 600)], ["pending", "ci-red"])
        self.assertEqual(self.tick(NOW + 660), [])
        self.assertEqual(self.poller["prs"]["1411"]["retried_at"], NOW + 600)

    def test_retried_at_survives_later_writes_of_the_entry(self):
        self.watch["prs"]["1411"]["retry_after"] = NOW + 600
        self.tick(NOW + 600)
        self.gh.prs[1411] = authored_pr(updated="2026-09-11T11:00:00Z")
        self.tick(NOW + 660)
        self.assertEqual(self.poller["prs"]["1411"]["retried_at"], NOW + 600)
        self.assertEqual(self.tick(NOW + 720), [])

    def test_a_checks_error_on_the_retry_tick_retries_again_on_the_next_tick(self):
        self.watch["prs"]["1411"]["retry_after"] = NOW + 600
        self.gh.fail_checks.add(1411)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual([e["kind"] for e in self.tick(NOW + 600)], ["pending"])
        self.assertEqual(self.poller["prs"]["1411"]["retried_at"], NOW + 600)
        self.assertNotIn("ci_retried_at", self.poller["prs"]["1411"])
        self.gh.fail_checks.clear()
        self.assertEqual([e["kind"] for e in self.tick(NOW + 660)], ["ci-red"])
        self.assertEqual(self.poller["prs"]["1411"]["ci_retried_at"], NOW + 600)

    def test_a_persistent_checks_error_does_not_re_emit_the_unchanged_pending_set(self):
        self.watch["prs"]["1411"]["retry_after"] = NOW + 600
        self.gh.fail_checks.add(1411)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual([e["kind"] for e in self.tick(NOW + 600)], ["pending"])
        self.assertEqual(self.poller["prs"]["1411"]["retried_at"], NOW + 600)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.tick(NOW + 660), [])
            self.assertEqual(self.tick(NOW + 1200), [])
        self.gh.fail_checks.clear()
        self.assertEqual([e["kind"] for e in self.tick(NOW + 1800)], ["ci-red"])
        self.assertEqual(self.poller["prs"]["1411"]["ci_retried_at"], NOW + 600)

    def test_a_thread_fetch_error_on_the_retry_tick_retries_again_on_the_next_tick(self):
        self.watch["prs"]["1411"]["retry_after"] = NOW + 600
        self.gh.fail = {1411}
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual([e["kind"] for e in self.tick(NOW + 600)], ["ci-red"])
        self.assertNotIn("retried_at", self.poller["prs"]["1411"])
        self.gh.fail = set()
        self.assertEqual([e["kind"] for e in self.tick(NOW + 660)], ["pending", "ci-red"])
        self.assertEqual(self.poller["prs"]["1411"]["retried_at"], NOW + 600)

    def test_a_retry_after_that_is_not_an_integer_is_ignored(self):
        self.watch["prs"]["1411"]["retry_after"] = str(NOW + 600)
        self.assertEqual(self.tick(NOW + 600), [])

    def test_a_new_retry_time_retries_again(self):
        self.watch["prs"]["1411"]["retry_after"] = NOW + 600
        self.tick(NOW + 600)
        self.watch["prs"]["1411"]["retry_after"] = NOW + 1200
        self.assertEqual(self.tick(NOW + 900), [])
        self.assertEqual(len(self.tick(NOW + 1200)), 2)


class MonitorLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.tmp.name)
        self.gh = FakeGh()
        self.gh.prs[1411] = authored_pr()
        (self.state / "watch.json").write_text(json.dumps(watch({1411: "authored"})),
                                               encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_monitor(self, ticks, clock=NOW):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            poll.monitor(self.gh, self.state, sleep=lambda s: None,
                         clock=lambda: clock, max_ticks=ticks)
        events = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        return events, err.getvalue()

    def test_events_are_printed_and_only_the_poller_file_is_written(self):
        before = (self.state / "watch.json").read_bytes()
        events, _ = self.run_monitor(2)
        self.assertEqual([e["kind"] for e in events], ["pending"])
        self.assertEqual((self.state / "watch.json").read_bytes(), before)
        poller = json.loads((self.state / "watch-poller.json").read_text(encoding="utf-8"))
        self.assertEqual(poller["last_reconciliation"], NOW)

    def test_quiet_ticks_emit_nothing_and_fetch_no_threads(self):
        events, _ = self.run_monitor(4)
        self.assertEqual([e["kind"] for e in events], ["pending"])
        self.assertEqual(self.gh.thread_fetches(), 1)

    def test_resumed_watch_with_a_recent_reconciliation_still_forces_the_first_tick(self):
        self.run_monitor(1)
        events, _ = self.run_monitor(1, clock=NOW + 60)
        self.assertEqual([e["kind"] for e in events], ["pending"])

    def test_a_failed_heads_query_is_logged_and_the_loop_continues(self):
        self.gh.fail_heads = True
        events, err = self.run_monitor(3)
        self.assertEqual(events, [])
        self.assertEqual(err.count("heads query failed"), 3)

    def test_daily_reconciliation_reports_what_the_ticks_missed(self):
        self.run_monitor(1)
        self.gh.prs[1411] = authored_pr(extra=[comment("c2", "reviewer-a", T1)])
        events, _ = self.run_monitor(1, clock=NOW + poll.RECONCILE_SECONDS)
        self.assertEqual([e["kind"] for e in events], ["pending", "reconciled"])
        self.assertEqual(events[1]["prs"], [1411])

    def test_daily_reconciliation_stays_silent_when_nothing_actually_changed(self):
        self.run_monitor(1)
        events, _ = self.run_monitor(1, clock=NOW + poll.RECONCILE_SECONDS)
        self.assertEqual([e["kind"] for e in events], ["pending"])

    def test_daily_reconciliation_after_ci_went_green_reports_no_miss(self):
        self.gh.rollup[1411] = "FAILURE"
        self.gh.checks[1411] = [{"name": "Gated / Unit Tests", "state": "FAILURE",
                                 "bucket": "fail", "link": ACTIONS, "workflow": "App Gated",
                                 "completedAt": "2026-09-10T05:16:39Z"}]
        now = [NOW]

        def next_day(_):
            now[0] = NOW + poll.RECONCILE_SECONDS
            self.gh.rollup[1411] = "SUCCESS"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            poll.monitor(self.gh, self.state, sleep=next_day, clock=lambda: now[0], max_ticks=2)
        kinds = [json.loads(line)["kind"] for line in out.getvalue().splitlines()]
        self.assertEqual(kinds, ["pending", "ci-red", "pending"])
        poller = json.loads((self.state / "watch-poller.json").read_text(encoding="utf-8"))
        self.assertTrue(poller["prs"]["1411"]["last_ci_signature"].startswith("ci:h2:"))

    def test_events_are_printed_only_after_the_poller_file_is_saved(self):
        real = poll.write_json_atomic
        failures = []

        def write(path, data, **kwargs):
            if path.name == "watch-poller.json" and not failures:
                failures.append(path)
                raise PermissionError("watch-poller.json is open")
            return real(path, data, **kwargs)
        with unittest.mock.patch.object(poll, "write_json_atomic", write):
            events, err = self.run_monitor(1)
            self.assertEqual(events, [])
            self.assertIn("watch-poller.json is open", err)
            events, _ = self.run_monitor(2)
        self.assertEqual([e["kind"] for e in events], ["pending"])

    def test_five_failed_poller_writes_in_a_row_print_one_poller_error(self):
        real = poll.write_json_atomic
        saves = iter([False] * 6 + [True] + [False] * 5)

        def write(path, data, **kwargs):
            if path.name == "watch-poller.json" and not next(saves):
                raise PermissionError("watch-poller.json is read-only")
            return real(path, data, **kwargs)
        with unittest.mock.patch.object(poll, "write_json_atomic", write):
            events, _ = self.run_monitor(12)
        self.assertEqual([e for e in events if e["kind"] == "poller-error"],
                         [{"kind": "poller-error", "error": "watch-poller.json is read-only"}] * 2)
        kinds = [e["kind"] for e in events]
        self.assertLess(kinds.index("pending"), kinds.index("poller-error", 1))

    def test_five_failures_reading_watch_json_before_any_save_print_one_poller_error(self):
        (self.state / "watch.json").write_text("{not json", encoding="utf-8")
        events, err = self.run_monitor(5)
        self.assertEqual([e["kind"] for e in events], ["poller-error"])
        self.assertEqual(err.count("JSONDecodeError"), 5)


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        self.now += 1
        return self.now


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = pathlib.Path(self.tmp.name)
        self.heartbeat = self.state / "watch-heartbeat"
        (self.state / "watch.json").write_text(json.dumps(watch({1411: "authored"})),
                                               encoding="utf-8")
        self.clock = Clock()
        self.seen = []

    def run_monitor(self, gh, ticks=1):
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            poll.monitor(gh, self.state, sleep=lambda s: None, clock=self.clock,
                         max_ticks=ticks)
        return err.getvalue()

    def record_heartbeat(self):
        self.seen.append((int(self.heartbeat.read_text(encoding="utf-8")), self.clock.now))

    def test_the_heartbeat_is_written_before_a_gh_call_that_then_raises(self):
        fake = FakeGh()
        fake.fail_heads = True

        def gh(args):
            self.record_heartbeat()
            return fake(args)
        err = self.run_monitor(gh, ticks=2)
        self.assertIn("heads query failed", err)
        self.assertEqual(len(self.seen), 2)
        for beat, latest in self.seen:
            self.assertEqual(beat, latest)

    def test_the_heartbeat_is_written_before_a_heads_query_that_times_out(self):
        def hung(*args, **kwargs):
            self.record_heartbeat()
            raise poll.subprocess.TimeoutExpired(args[0], poll.GH_TIMEOUT_SECONDS)
        with unittest.mock.patch.object(poll.subprocess, "run", side_effect=hung):
            err = self.run_monitor(poll.run_gh)
        self.assertIn("gh timed out after 120s", err)
        self.assertEqual(len(self.seen), 1)
        self.assertEqual(self.seen[0][0], self.seen[0][1])

    def test_the_heartbeat_is_refreshed_after_the_sleep(self):
        gh = FakeGh()
        gh.prs[1411] = authored_pr()
        stamps = []

        def sleep(_):
            stamps.append(int(self.heartbeat.read_text(encoding="utf-8")))
        with contextlib.redirect_stdout(io.StringIO()):
            poll.monitor(gh, self.state, sleep=sleep, clock=self.clock, max_ticks=2)
        self.assertLess(stamps[0], int(self.heartbeat.read_text(encoding="utf-8")))

    def test_a_failed_heartbeat_write_does_not_stop_the_loop(self):
        gh = FakeGh()
        gh.prs[1411] = authored_pr()
        self.heartbeat.mkdir()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            poll.monitor(gh, self.state, sleep=lambda s: None, clock=self.clock, max_ticks=2)
        self.assertEqual([json.loads(line)["kind"] for line in out.getvalue().splitlines()],
                         ["pending"])


class AtomicWriteTests(unittest.TestCase):
    def replace_failing(self, failures):
        real = poll.os.replace
        calls = []

        def flaky(src, dst):
            calls.append(src)
            if len(calls) <= failures:
                raise PermissionError("target is open")
            real(src, dst)
        return flaky, calls

    def test_a_briefly_locked_target_is_retried(self):
        flaky, calls = self.replace_failing(2)
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(poll.os, "replace", flaky):
            target = pathlib.Path(tmp) / "watch-poller.json"
            poll.write_json_atomic(target, {"a": 1}, sleep=lambda _: None)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"a": 1})
            self.assertEqual(len(calls), 3)

    def test_a_persistently_locked_target_raises_and_leaves_no_temp_file(self):
        flaky, _ = self.replace_failing(99)
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(poll.os, "replace", flaky):
            target = pathlib.Path(tmp) / "watch-poller.json"
            with self.assertRaises(PermissionError):
                poll.write_json_atomic(target, {"a": 1}, sleep=lambda _: None)
            self.assertEqual(list(pathlib.Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
