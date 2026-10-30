import contextlib
import io
import json
import pathlib
import tempfile
import unittest
import unittest.mock

from fakes import (NOW, T1, FakeGh, HomeCase, claim_leases, comment, lease, pk, poll, pull,
                   pw_paths, rk, thread, watch, write_session)
from test_poll_monitor import authored_pr


def fresh_poller():
    return {"closed": [], "heads": {}, "prs": {}, "errors": {}}


def returning(result, seen=None):
    def write_lease(owner, repo, number, **kwargs):
        if seen is not None:
            seen.append(kwargs)
        return result
    return write_lease


class WriteSessionLeasesTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.view = watch({1: "authored"})
        self.armed = self.view["prs"]
        self.poller = fresh_poller()

    def write(self, write_lease, now=NOW, closed_before=frozenset(), **kwargs):
        return poll.write_session_leases(self.view, self.armed, self.poller, set(closed_before),
                                         now, write_lease=write_lease, **kwargs)

    def test_lease_lost_raised_once_across_calls(self):
        lost = returning("lost")
        silenced1, ev1, _ = self.write(lost)
        _, ev2, _ = self.write(lost, now=NOW + 60)
        self.assertEqual([e["kind"] for e in ev1], ["lease-lost"])
        self.assertEqual(ev2, [])
        self.assertEqual(silenced1, {rk(1)})
        self.assertEqual(self.poller["lease_dropped"], [rk(1)])

    def test_inactive_drops_without_an_event(self):
        silenced, events, _ = self.write(returning("inactive"))
        self.assertEqual((silenced, events), ({rk(1)}, []))
        self.assertEqual(self.poller["lease_dropped"], [rk(1)])

    def test_dropped_pr_is_not_written_again(self):
        seen = []
        self.write(returning("lost", seen))
        self.write(returning("lost", seen), now=NOW + 60)
        self.assertEqual(len(seen), 1)

    def test_missing_warns_once_and_is_persisted(self):
        missing = returning("missing")
        self.write(missing)
        self.write(missing, now=NOW + 60)
        self.assertEqual(self.poller["lease_warned"], [rk(1)])

    def test_closing_pr_with_busy_lease_is_unclosed(self):
        self.poller["closed"] = [rk(1)]
        silenced, events, unclosed = self.write(returning("busy"))
        self.assertEqual((silenced, events, unclosed), ({rk(1)}, [], {rk(1)}))

    def test_closed_before_is_skipped(self):
        seen = []
        silenced, events, unclosed = self.write(returning("lost", seen), closed_before={rk(1)})
        self.assertEqual((silenced, events, unclosed, seen), (set(), [], set(), []))

    def test_central_flag_reaches_write_lease(self):
        seen = []
        self.write(returning("ok", seen), central=True)
        self.assertTrue(seen[0]["central"])

    def test_default_does_not_pass_central(self):
        seen = []
        self.write(returning("ok", seen))
        self.assertNotIn("central", seen[0])

    def test_prunes_both_lists_to_the_armed_keys(self):
        self.poller["lease_dropped"] = [rk(1), rk(7)]
        self.poller["lease_warned"] = [rk(1), rk(9)]
        self.write(returning("ok"))
        self.assertEqual(self.poller["lease_dropped"], [rk(1)])
        self.assertEqual(self.poller["lease_warned"], [rk(1)])

    def test_a_dropped_pr_that_is_no_longer_armed_is_retried_when_rearmed(self):
        self.poller["lease_dropped"] = [rk(1)]
        self.armed = {}
        self.write(returning("ok"))
        self.armed = self.view["prs"]
        seen = []
        self.write(returning("ok", seen))
        self.assertEqual(len(seen), 1)

    def test_lease_lost_raised_once_across_a_json_round_trip(self):
        lost = returning("lost")
        _, ev1, _ = self.write(lost)
        self.poller = json.loads(json.dumps(self.poller))
        _, ev2, _ = self.write(lost, now=NOW + 60)
        self.assertEqual(len(ev1), 1)
        self.assertEqual(ev2, [])


class MonitorLeaseStateTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = pathlib.Path(self.tmp.name)
        self.gh = FakeGh()
        self.gh.prs[pk(1411)] = authored_pr()
        view = watch({1411: "authored"})
        write_session(self.state, view)
        claim_leases(view)

    def run_monitor(self, write_lease, ticks=1):
        saves = []
        real = poll.write_json_atomic

        def counting(path, data, **kwargs):
            if path.name == "watch-poller.json":
                saves.append(path)
            return real(path, data, **kwargs)
        with unittest.mock.patch.object(poll, "write_json_atomic", counting),                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            poll.monitor(self.gh, self.state, sleep=lambda s: None, clock=lambda: NOW,
                         max_ticks=ticks, write_lease=write_lease)
        return len(saves)

    def test_a_restarted_monitor_retries_a_pr_the_earlier_one_dropped(self):
        (self.state / "watch-poller.json").write_text(
            json.dumps({"lease_dropped": [rk(1411)], "lease_warned": [rk(1411)]}),
            encoding="utf-8")
        seen = []
        self.run_monitor(returning("ok", seen))
        self.assertEqual(len(seen), 1)

    def test_a_pr_dropped_during_a_run_is_not_retried_by_the_same_monitor(self):
        seen = []
        self.run_monitor(returning("lost", seen), ticks=3)
        self.assertEqual(len(seen), 1)

    def test_the_poller_is_saved_again_only_when_the_lease_lists_change(self):
        self.assertEqual(self.run_monitor(returning("ok")), 1)
        self.assertEqual(self.run_monitor(returning("inactive")), 2)

    def test_a_new_missing_warning_saves_again(self):
        self.assertEqual(self.run_monitor(returning("missing")), 2)


def pending_check(name="build"):
    return {"name": name, "state": "PENDING", "bucket": "pending", "link": "", "workflow": "CI",
            "completedAt": None}


class TickAllTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.root = pw_paths.sessions_root()
        self.gh = FakeGh()
        self.gh.prs[pk(1411)] = authored_pr()
        self.leases = []

    def session(self, sid="s-1", prs=None, central=True, push_queue=(), status=None,
                progress=None, **top):
        view = watch(prs or {1411: "authored"}, push_queue=push_queue)
        view["session_id"] = sid
        if central:
            view["watcher"] = "central"
        view.update(top)
        for key, value in (status or {}).items():
            view["prs"][key]["status"] = value
        for key, fields in (progress or {}).items():
            view["prs"][key].update(fields)
        claim_leases(view, session_id=sid)
        return write_session(self.root / sid, view)

    def recording(self, owner, repo, number, **kwargs):
        self.leases.append((pw_paths.pr_key(owner, repo, number), kwargs))
        return "ok"

    def tick(self, now=NOW, **kwargs):
        kwargs.setdefault("write_lease", self.recording)
        with contextlib.redirect_stderr(io.StringIO()):
            return poll.tick_all(self.gh, self.root, now, **kwargs)

    def spool(self, sid="s-1", name="events.jsonl"):
        path = self.root / sid / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def kinds(self, sid="s-1", name="events.jsonl"):
        return [e["kind"] for e in self.spool(sid, name)]

    def test_skips_non_central_sessions(self):
        self.session(central=False)
        stats = self.tick()
        self.assertEqual((self.spool(), self.leases, stats["sessions"]), ([], [], 0))
        self.assertFalse((self.root / "s-1" / "watch-poller.json").exists())

    def test_central_session_spools_pending_event(self):
        self.session()
        stats = self.tick()
        self.assertEqual(self.spool(), [{"session": "s-1", "pr": rk(1411), "role": "authored",
                                         "kind": "pending", "threads": ["T1"], "comments": [],
                                         "reviews": []}])
        self.assertEqual((stats["sessions"], stats["events"]), (1, 1))

    def test_first_tick_is_forced_then_not(self):
        self.session()
        self.tick()
        self.tick(now=NOW + 300)
        self.assertEqual(len(self.spool()), 1)
        self.tick(now=NOW + poll.RECONCILE_SECONDS)
        self.assertEqual(self.kinds(), ["pending", "pending"])

    def test_reconciled_not_spooled(self):
        self.session()
        self.tick()
        self.gh.prs[pk(1411)] = authored_pr(extra=[comment("c2", "reviewer-a", T1)])
        self.tick(now=NOW + 300)
        self.tick(now=NOW + poll.RECONCILE_SECONDS)
        self.assertEqual(self.kinds(), ["pending", "pending"])

    def test_idle_not_emitted_and_no_claude_pid_exit(self):
        self.session(claude_pid=2_000_000_000)
        merged = authored_pr()
        merged["state"] = "MERGED"
        self.gh.prs[pk(1411)] = merged
        stats = self.tick()
        self.assertEqual(self.kinds(), ["closed"])
        self.assertEqual(stats["sessions"], 1)

    def test_lease_written_central(self):
        self.session()
        self.tick()
        self.assertEqual([(key, kw["central"], kw["status"]) for key, kw in self.leases],
                         [(rk(1411), True, "armed")])

    def test_spool_written_before_poller_saved(self):
        self.session()
        real = poll.write_json_atomic

        def failing(path, data, **kwargs):
            if path.name == "watch-poller.json":
                raise OSError("disk full")
            return real(path, data, **kwargs)
        with unittest.mock.patch.object(poll, "write_json_atomic", failing):
            stats = self.tick()
        first = self.spool()
        self.assertEqual([e["kind"] for e in first], ["pending"])
        self.assertEqual(stats["errors"], 1)
        self.tick(now=NOW + 300)
        self.assertEqual(self.spool(), first * 2)

    def test_deadline_skips_remaining_sessions(self):
        self.gh.prs[pk(1412)] = pull(1412, threads=[thread("T2", [comment("c9", "reviewer-a",
                                                                          T1)])])
        self.session("s-1")
        self.session("s-2", prs={1412: "authored"})
        clock = [0.0]

        def slow_lease(owner, repo, number, **kwargs):
            clock[0] = 181.0
            return self.recording(owner, repo, number, **kwargs)
        stats = self.tick(clock=lambda: clock[0], write_lease=slow_lease)
        self.assertEqual(stats["skipped_after_deadline"], 1)
        self.assertEqual(stats["sessions"], 1)
        self.assertEqual(self.spool("s-2"), [])
        self.assertFalse((self.root / "s-2" / "watch-poller.json").exists())
        self.assertEqual([key for key, _ in self.leases], [rk(1411)])

    def queued_session(self, queued_at):
        for n in (2, 3):
            self.gh.prs[pk(n)] = pull(n)
        self.gh.checks[pk(3)] = [pending_check()]
        self.session(prs={2: "authored", 3: "authored"}, push_queue=[rk(2)],
                     progress={rk(2): {"queued_at": queued_at}})

    def test_tick_raised_only_when_peers_green(self):
        self.queued_session(NOW - 60)
        self.tick()
        self.assertNotIn("tick", self.kinds())
        self.gh.checks[pk(3)] = []
        self.tick(now=NOW + 300)
        self.assertEqual([e for e in self.spool() if e["kind"] == "tick"],
                         [{"session": "s-1", "kind": "tick", "push_queue": [rk(2)]}])

    def test_tick_raised_after_an_hour_queued(self):
        self.queued_session(NOW - 3601)
        self.tick()
        self.assertIn("tick", self.kinds())

    def test_dry_run_ticks_stopped_and_monitor_watches(self):
        self.gh.prs[pk(1412)] = pull(1412, threads=[thread("T2", [comment("c9", "reviewer-a",
                                                                          T1)])])
        directory = self.session(central=False, prs={1411: "authored", 1412: "authored"},
                                 status={rk(1412): "stopped"})
        live_poller = {"last_reconciliation": NOW, "prs": {}, "closed": [rk(1411), rk(1412)]}
        (directory / "watch-poller.json").write_text(json.dumps(live_poller), encoding="utf-8")
        stats = self.tick(dry_run=True)
        self.assertEqual(sorted(e["pr"] for e in self.spool(name="events.dry-run.jsonl")),
                         [rk(1411), rk(1412)])
        self.assertTrue((directory / "watch-poller.dry-run.json").exists())
        self.assertFalse((directory / "events.jsonl").exists())
        self.assertEqual(json.loads((directory / "watch-poller.json").read_text(encoding="utf-8")),
                         live_poller)
        self.assertEqual(self.leases, [])
        self.assertEqual(stats["sessions"], 1)

    def test_dry_run_never_writes_a_lease_or_prunes(self):
        self.session()
        with unittest.mock.patch.object(poll.lease, "prune_closed") as prune:
            self.tick(dry_run=True)
        self.assertEqual((self.leases, prune.call_count), ([], 0))

    def test_heads_query_batched_across_sessions(self):
        self.gh.prs[pk(1412)] = pull(1412, threads=[thread("T2", [comment("c9", "reviewer-a",
                                                                          T1)])])
        self.session("s-1")
        self.session("s-2", prs={1412: "authored"})
        stats = self.tick()
        self.assertEqual(self.gh.heads_requests(), 1)
        self.assertEqual((self.kinds("s-1"), self.kinds("s-2")), (["pending"], ["pending"]))
        self.assertEqual(stats["gh_calls"], len(self.gh.calls))

    def test_unreadable_session_files_are_counted_and_others_still_tick(self):
        (self.root / "s-0").mkdir(parents=True)
        (self.root / "s-0" / "watch.json").write_text("{not json", encoding="utf-8")
        (self.root / "s-00").mkdir()
        self.session("s-2")
        stats = self.tick()
        self.assertEqual(stats["errors"], 1)
        self.assertEqual(self.kinds("s-2"), ["pending"])

    def test_a_session_dir_without_watch_json_is_skipped_silently(self):
        (self.root / "s-0").mkdir(parents=True)
        stats = self.tick()
        self.assertEqual((stats["errors"], stats["sessions"]), (0, 0))

    def test_a_corrupt_poller_is_ticked_from_empty_state(self):
        for body in ("[", "[]"):
            with self.subTest(body=body):
                directory = self.session()
                (directory / "events.jsonl").unlink(missing_ok=True)
                (directory / "watch-poller.json").write_text(body, encoding="utf-8")
                self.leases = []
                stats = self.tick()
                self.assertEqual(stats["errors"], 1)
                self.assertEqual(self.kinds(), ["pending"])
                self.assertEqual([(key, kw["central"]) for key, kw in self.leases],
                                 [(rk(1411), True)])
                saved = json.loads((directory / "watch-poller.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["last_reconciliation"], NOW)

    def test_a_torn_spool_tail_stays_on_its_own_line(self):
        directory = self.session()
        (directory / "events.jsonl").write_text('{"session": "s-1", "ki', encoding="utf-8")
        self.tick()
        lines = (directory / "events.jsonl").read_text(encoding="utf-8").split("\n")
        self.assertEqual(lines[0], '{"session": "s-1", "ki')
        self.assertEqual(json.loads(lines[1])["kind"], "pending")
        self.assertEqual(lines[2:], [""])

    def test_a_pr_reopened_while_armed_is_rechecked_on_the_daily_pass(self):
        self.session()
        merged = authored_pr()
        merged["state"] = "MERGED"
        self.gh.prs[pk(1411)] = merged
        self.tick()
        self.gh.prs[pk(1411)] = authored_pr(updated="2026-09-11T11:00:00Z")
        self.tick(now=NOW + 300)
        self.assertEqual(self.kinds(), ["closed"])
        self.tick(now=NOW + poll.RECONCILE_SECONDS)
        self.assertEqual(self.kinds(), ["closed", "pending"])

    def test_a_closed_event_lost_to_a_kill_is_spooled_by_the_next_run(self):
        self.session()
        merged = authored_pr()
        merged["state"] = "MERGED"
        self.gh.prs[pk(1411)] = merged
        real = poll.append_spool

        def killed(path, session_id, events):
            raise KeyboardInterrupt
        with unittest.mock.patch.object(poll, "append_spool", killed):
            with self.assertRaises(KeyboardInterrupt):
                self.tick(write_lease=lease.tick_write)
        self.assertEqual(lease.read_lease("o", "r", 1411)["status"], "closed")
        self.assertEqual(self.kinds(), [])
        self.tick(now=NOW + 300, write_lease=lease.tick_write)
        self.assertEqual(self.kinds(), ["closed"])

    def test_a_reopened_pr_whose_lease_went_closed_is_dropped_not_rewritten(self):
        self.session()
        merged = authored_pr()
        merged["state"] = "MERGED"
        self.gh.prs[pk(1411)] = merged
        self.tick(write_lease=lease.tick_write)
        self.gh.prs[pk(1411)] = authored_pr(updated="2026-09-11T11:00:00Z")
        self.tick(now=NOW + poll.RECONCILE_SECONDS, write_lease=lease.tick_write)
        self.assertEqual(self.kinds(), ["closed"])
        self.assertEqual(lease.read_lease("o", "r", 1411)["status"], "closed")
        saved = json.loads((self.root / "s-1" / "watch-poller.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["lease_dropped"], [rk(1411)])

    def test_central_leases_carry_no_poller_pid(self):
        self.session()
        self.tick()
        self.assertIsNone(self.leases[0][1]["poller_pid"])

    def test_the_session_ticked_longest_ago_goes_first_after_a_deadline_skip(self):
        self.gh.prs[pk(1412)] = pull(1412, threads=[thread("T2", [comment("c9", "reviewer-a",
                                                                          T1)])])
        self.session("s-1")
        self.session("s-2", prs={1412: "authored"})
        clock = [0.0]

        def slow_lease(owner, repo, number, **kwargs):
            clock[0] = 181.0
            return self.recording(owner, repo, number, **kwargs)
        self.tick(clock=lambda: clock[0], write_lease=slow_lease)
        self.assertEqual((self.kinds("s-1"), self.kinds("s-2")), (["pending"], []))
        clock[0] = 0.0
        self.tick(now=NOW + 300, clock=lambda: clock[0], write_lease=slow_lease)
        self.assertEqual((self.kinds("s-1"), self.kinds("s-2")), (["pending"], ["pending"]))

    def test_a_missing_sessions_root_is_an_empty_run(self):
        stats = self.tick()
        self.assertEqual(stats, {"sessions": 0, "events": 0, "gh_calls": 0,
                                 "skipped_after_deadline": 0, "errors": 0})

    def test_lease_lost_spools_once_and_silences_the_pr(self):
        self.session()

        def lost(owner, repo, number, **kwargs):
            return "lost"
        self.tick(write_lease=lost)
        self.tick(now=NOW + 300, write_lease=lost)
        self.assertEqual(self.kinds(), ["lease-lost"])

    def test_a_rearmed_pr_is_written_again_after_a_run_with_nothing_armed(self):
        directory = self.session()
        (directory / "watch-poller.json").write_text(
            json.dumps({"lease_dropped": [rk(1411)], "lease_warned": [rk(1411)]}),
            encoding="utf-8")
        watch_path = directory / "watch.json"
        armed = json.loads(watch_path.read_text(encoding="utf-8"))
        released = json.loads(json.dumps(armed))
        released["prs"][rk(1411)]["status"] = "released"
        watch_path.write_text(json.dumps(released), encoding="utf-8")
        self.tick()
        watch_path.write_text(json.dumps(armed), encoding="utf-8")
        self.tick(now=NOW + 300)
        self.assertEqual([key for key, _ in self.leases], [rk(1411)])

    def test_poller_error_spooled_once_after_five_failed_runs(self):
        self.session()
        self.gh.fail_heads = True
        for i in range(poll.POLLER_ERROR_AFTER + 1):
            self.tick(now=NOW + 300 * i)
        self.assertEqual(self.kinds(), ["poller-error"])
        self.assertIn("heads query failed", self.spool()[0]["error"])
        self.gh.fail_heads = False
        self.tick(now=NOW + 3000)
        self.assertEqual(self.kinds(), ["poller-error", "pending"])


class TickAllCliTests(HomeCase):
    def test_tick_all_prints_stats_and_writes_a_central_lease(self):
        gh = FakeGh()
        gh.prs[pk(1411)] = authored_pr()
        view = dict(watch({1411: "authored"}), watcher="central")
        claim_leases(view)
        write_session(pw_paths.sessions_root() / "s-1", view)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = poll.main(["--tick-all"], gh=gh)
        self.assertEqual(code, 0)
        stats = json.loads(out.getvalue())
        self.assertEqual((stats["sessions"], stats["events"]), (1, 1))
        held = lease.read_lease("o", "r", 1411)
        self.assertEqual((held["watcher"], held["stale_after_seconds"]), ("central", 900))

    def test_dry_run_needs_tick_all(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            poll.main(["--monitor", "--dry-run", "--session-dir", "x"])
        self.assertIn("--dry-run needs --tick-all", err.getvalue())


if __name__ == "__main__":
    unittest.main()
