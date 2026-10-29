import unittest

from fakes import NOW, FakeGh, pk, poll, pull, rk, watch

APPROVED_BEHIND = {"mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND",
                   "reviewDecision": "APPROVED"}


class MergeBlockerTests(unittest.TestCase):
    def node(self, rollup="SUCCESS", **fields):
        return {"commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": rollup}}}]},
                **fields}

    def test_conflicting(self):
        self.assertEqual(poll.merge_blocker(self.node(mergeable="CONFLICTING")), "conflicting")

    def test_unknown_while_github_computes(self):
        self.assertEqual(poll.merge_blocker(self.node(mergeable="UNKNOWN")), "unknown")
        self.assertEqual(poll.merge_blocker(self.node()), "unknown")

    def test_behind_counts_only_when_approved_and_green(self):
        self.assertEqual(poll.merge_blocker(self.node(**APPROVED_BEHIND)), "behind-ready")
        self.assertIsNone(poll.merge_blocker(
            self.node(**dict(APPROVED_BEHIND, reviewDecision="REVIEW_REQUIRED"))))
        self.assertIsNone(poll.merge_blocker(self.node(rollup="PENDING", **APPROVED_BEHIND)))

    def test_clean_and_blocked_are_not_reported(self):
        self.assertIsNone(poll.merge_blocker(self.node(mergeable="MERGEABLE",
                                                       mergeStateStatus="CLEAN")))
        self.assertIsNone(poll.merge_blocker(self.node(mergeable="MERGEABLE",
                                                       mergeStateStatus="BLOCKED")))


class MergeabilityTickTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGh()
        self.view = watch({1411: "authored"})
        self.gh.prs[pk(1411)] = pull(1411)
        self.gh.rollup[pk(1411)] = "SUCCESS"
        self.gh.checks[pk(1411)] = [{"name": "build", "bucket": "pass"}]
        self.poller = {}
        self.now = NOW

    def tick(self, force=False):
        self.now += 60
        return [e for e in poll.tick_once(self.gh, self.view, self.poller, self.now, force=force)
                if e["kind"] in ("conflicting", "behind-ready")]

    def test_tick_query_asks_for_mergeability(self):
        query = poll.tick_query({("o", "r"): [1411]})[0]
        for field in ("baseRefName", "mergeable", "mergeStateStatus", "reviewDecision"):
            self.assertIn(field, query)

    def test_conflict_is_raised_once_per_head_without_the_pr_changing(self):
        self.assertEqual(self.tick(), [])
        self.gh.merge[pk(1411)] = {"mergeable": "CONFLICTING"}
        self.assertEqual(self.tick(), [{"pr": rk(1411), "role": "authored",
                                        "kind": "conflicting", "head": "h2", "base": "main"}])
        self.assertEqual(self.tick(), [])
        self.gh.prs[pk(1411)]["headRefOid"] = "h3"
        self.assertEqual([e["head"] for e in self.tick()], ["h3"])

    def test_unknown_keeps_the_mark(self):
        self.gh.merge[pk(1411)] = {"mergeable": "CONFLICTING"}
        self.tick()
        self.gh.merge[pk(1411)] = {"mergeable": "UNKNOWN"}
        self.assertEqual(self.tick(), [])
        self.gh.merge[pk(1411)] = {"mergeable": "CONFLICTING"}
        self.assertEqual(self.tick(), [])

    def test_a_cleared_conflict_that_returns_is_raised_again(self):
        self.gh.merge[pk(1411)] = {"mergeable": "CONFLICTING"}
        self.tick()
        self.gh.merge[pk(1411)] = {"mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"}
        self.tick()
        self.gh.merge[pk(1411)] = {"mergeable": "CONFLICTING"}
        self.assertEqual(len(self.tick()), 1)

    def test_a_forced_pass_raises_it_again(self):
        self.gh.merge[pk(1411)] = {"mergeable": "CONFLICTING"}
        self.tick()
        self.assertEqual(len(self.tick(force=True)), 1)

    def test_approved_green_and_behind_is_raised(self):
        self.gh.merge[pk(1411)] = dict(APPROVED_BEHIND)
        self.assertEqual(self.tick(), [{"pr": rk(1411), "role": "authored",
                                        "kind": "behind-ready", "head": "h2", "base": "main"}])
        self.assertEqual(self.tick(), [])

    def test_behind_without_approval_or_green_checks_is_quiet(self):
        self.gh.merge[pk(1411)] = dict(APPROVED_BEHIND, reviewDecision="REVIEW_REQUIRED")
        self.assertEqual(self.tick(), [])
        self.gh.merge[pk(1411)] = dict(APPROVED_BEHIND)
        self.gh.rollup[pk(1411)] = "PENDING"
        self.assertEqual(self.tick(), [])

    def test_reviewed_pr_is_never_reported(self):
        self.view = watch({1411: "reviewed"})
        self.gh.merge[pk(1411)] = {"mergeable": "CONFLICTING"}
        self.assertEqual(self.tick(), [])

    def test_a_closed_pr_drops_its_mark(self):
        self.gh.merge[pk(1411)] = {"mergeable": "CONFLICTING"}
        self.tick()
        self.gh.prs[pk(1411)]["state"] = "MERGED"
        self.tick()
        self.assertNotIn(rk(1411), self.poller["merge"])


if __name__ == "__main__":
    unittest.main()
