import contextlib
import io
import json
import pathlib
import tempfile
import unittest
import unittest.mock

from fakes import NOW, SELF, T0, T1, FakeGh, comment, poll, pull, review, thread, watch


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

    def test_pr_without_my_threads_is_ignored(self):
        self.gh.prs[1420] = pull(1420, author_login="author-b", head="h2",
                                 threads=[thread("T1", [comment("c1", "reviewer-a", T0)])])
        self.assertEqual(self.tick(), [])


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
