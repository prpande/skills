import contextlib
import io
import json
import pathlib
import tempfile
import unittest
import unittest.mock

from fakes import NOW, FakeGh, HomeCase, claim_leases, pk, poll, rk, watch, write_session
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


if __name__ == "__main__":
    unittest.main()
