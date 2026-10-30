import unittest

from fakes import NOW, HomeCase, poll, rk, watch


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


if __name__ == "__main__":
    unittest.main()
