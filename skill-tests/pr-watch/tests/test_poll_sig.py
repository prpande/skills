import hashlib
import re
import unittest

from fakes import NOW, T0, T1, FakeGh, comment, pk, poll, pull, rk, thread, watch
from test_poll_ci import check
from test_poll_monitor import authored_pr, reviewed_pr

HEX12 = re.compile(r"^[0-9a-f]{12}$")


def digest(signature):
    return hashlib.sha1(signature.encode()).hexdigest()[:12]


class SigTests(unittest.TestCase):
    def tick(self, gh, view):
        return poll.tick_once(gh, view, {}, NOW)

    def test_pending_carries_the_signature_digest(self):
        gh = FakeGh()
        gh.prs[pk(1411)] = authored_pr()
        (event,) = self.tick(gh, watch({1411: "authored"}))
        self.assertEqual(event["sig"], digest("pending:c1"))

    def test_ci_red_carries_a_sig(self):
        gh = FakeGh()
        gh.prs[pk(1411)] = pull(1411)
        gh.rollup[pk(1411)] = "FAILURE"
        gh.checks[pk(1411)] = [check("Gated / Unit Tests")]
        (event,) = self.tick(gh, watch({1411: "authored"}))
        self.assertRegex(event["sig"], HEX12)

    def test_reply_carries_a_sig(self):
        gh = FakeGh()
        gh.prs[pk(1420)] = reviewed_pr(head="h1", replies=[comment("a1", "author-b", T1)])
        (event,) = self.tick(gh, watch({1420: "reviewed"}))
        self.assertEqual(event["sig"], digest("reply:a1"))

    def test_head_moved_carries_a_sig(self):
        gh = FakeGh()
        gh.prs[pk(1420)] = reviewed_pr(head="h2")
        gh.compare["h1...h2"] = ["src/B.cs"]
        (event,) = self.tick(gh, watch({1420: "reviewed"}))
        self.assertEqual(event["sig"], digest("head:h2:"))

    def test_new_comment_in_the_same_thread_changes_sig(self):
        first, second = FakeGh(), FakeGh()
        first.prs[pk(1411)] = authored_pr()
        second.prs[pk(1411)] = authored_pr(extra=[comment("c2", "reviewer-a", T1)])
        (a,) = self.tick(first, watch({1411: "authored"}))
        (b,) = self.tick(second, watch({1411: "authored"}))
        self.assertEqual(a["threads"], b["threads"])
        self.assertNotEqual(a["sig"], b["sig"])

    def test_same_state_gives_the_same_sig(self):
        sigs = []
        for _ in range(2):
            gh = FakeGh()
            gh.prs[pk(1411)] = authored_pr()
            sigs.append(self.tick(gh, watch({1411: "authored"}))[0]["sig"])
        self.assertEqual(sigs[0], sigs[1])
