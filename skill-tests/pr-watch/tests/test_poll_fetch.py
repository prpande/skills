import json
import subprocess
import unittest
from unittest import mock

from fakes import SELF, T0, T1, T2, T3, FakeGh, comment, poll, pull, review, thread


class RunGhTests(unittest.TestCase):
    def test_a_hung_gh_is_a_gh_error_naming_the_command(self):
        hung = subprocess.TimeoutExpired(["gh", "api", "graphql"], 120)
        with mock.patch.object(poll.subprocess, "run", side_effect=hung) as run:
            with self.assertRaises(poll.GhError) as caught:
                poll.run_gh(["api", "graphql", "-f", "query=q"])
        self.assertEqual(str(caught.exception), "gh timed out after 120s: gh api graphql")
        self.assertEqual(run.call_args.kwargs["timeout"], 120)

    def test_a_failed_call_keeps_its_stdout(self):
        done = subprocess.CompletedProcess(["gh"], 1, stdout='{"data": {}}', stderr="GraphQL: x")
        with mock.patch.object(poll.subprocess, "run", return_value=done):
            with self.assertRaises(poll.GhError) as caught:
                poll.run_gh(["api", "graphql"])
        self.assertEqual((str(caught.exception), caught.exception.stdout),
                         ("GraphQL: x", '{"data": {}}'))


class GraphqlTests(unittest.TestCase):
    def test_ints_are_typed_fields_and_none_is_omitted(self):
        calls = []
        poll.graphql(lambda a: calls.append(a) or '{"data": {}}', "q",
                     {"n": 5, "owner": "o", "after": None})
        self.assertEqual(calls[0], ["api", "graphql", "-f", "query=q", "-F", "n=5",
                                    "-f", "owner=o"])

    def test_errors_raise(self):
        body = json.dumps({"errors": [{"message": "bad"}], "data": None})
        with self.assertRaises(poll.GhError):
            poll.graphql(lambda a: body, "q", {})

    def test_partial_data_is_accepted_when_allowed(self):
        body = json.dumps({"errors": [{"message": "one alias failed"}],
                           "data": {"repository": {"p1": None}}})
        self.assertEqual(poll.graphql(lambda a: body, "q", {}, allow_partial=True),
                         {"repository": {"p1": None}})

    @staticmethod
    def failing(stdout):
        def gh(args):
            raise poll.GhError("GraphQL: one alias failed", stdout=stdout)
        return gh

    def test_partial_data_on_a_failed_exit_is_accepted_when_allowed(self):
        body = json.dumps({"errors": [{"message": "one alias failed"}],
                           "data": {"repository": {"p1": {"number": 1}, "p2": None}}})
        self.assertEqual(poll.graphql(self.failing(body), "q", {}, allow_partial=True),
                         {"repository": {"p1": {"number": 1}, "p2": None}})

    def test_a_failed_exit_without_data_still_raises(self):
        for stdout in (None, "", "not json", json.dumps({"errors": [], "data": None})):
            with self.subTest(stdout=stdout), self.assertRaises(poll.GhError):
                poll.graphql(self.failing(stdout), "q", {}, allow_partial=True)

    def test_a_failed_exit_raises_when_partial_is_not_allowed(self):
        body = json.dumps({"errors": [{"message": "x"}], "data": {"repository": {}}})
        with self.assertRaises(poll.GhError):
            poll.graphql(self.failing(body), "q", {})


class FetchTests(unittest.TestCase):
    def test_fetch_follows_thread_pages(self):
        gh = FakeGh()
        first = pull(threads=[thread("T1", [comment("c1", "reviewer-a", T0)])])
        first["reviewThreads"]["pageInfo"] = {"hasNextPage": True, "endCursor": "1"}
        second = pull(threads=[thread("T2", [comment("c2", "reviewer-a", T0)])])
        gh.pages[1411] = [first, second]
        pr = poll.fetch_pr(gh, "o", "r", 1411)
        self.assertEqual([t["id"] for t in pr["reviewThreads"]["nodes"]], ["T1", "T2"])
        self.assertEqual(gh.thread_fetches(), 2)

    def test_a_thread_with_a_second_comment_page_yields_every_comment_in_order(self):
        gh = FakeGh()
        pr = pull(threads=[thread("T1", [comment("c1", "reviewer-a", T0),
                                         comment("c2", "reviewer-a", T1)])])
        pr["reviewThreads"]["nodes"][0]["comments"]["pageInfo"] = {"hasNextPage": True,
                                                                    "endCursor": "k2"}
        gh.prs[1411] = pr
        gh.thread_comment_pages[("T1", "k2")] = {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [comment("c3", "reviewer-a", T2), comment("c4", "reviewer-a", T3)]}
        fetched = poll.fetch_pr(gh, "o", "r", 1411)
        self.assertEqual([c["id"] for c in fetched["reviewThreads"]["nodes"][0]["comments"]["nodes"]],
                         ["c1", "c2", "c3", "c4"])
        self.assertNotIn("truncated", fetched)

    def test_earlier_issue_comment_and_review_pages_are_read_oldest_first(self):
        gh = FakeGh()
        pr = pull(comments=[comment("i3", "reviewer-a", T2)],
                  reviews=[review("r3", "reviewer-a", T2, body="x")])
        pr["comments"]["pageInfo"] = {"hasPreviousPage": True, "startCursor": "i3"}
        pr["reviews"]["pageInfo"] = {"hasPreviousPage": True, "startCursor": "r3"}
        gh.prs[1411] = pr
        gh.earlier[(1411, "comments", "i3")] = {
            "pageInfo": {"hasPreviousPage": True, "startCursor": "i2"},
            "nodes": [comment("i2", "reviewer-a", T1)]}
        gh.earlier[(1411, "comments", "i2")] = {
            "pageInfo": {"hasPreviousPage": False, "startCursor": "i1"},
            "nodes": [comment("i1", "reviewer-a", T0)]}
        gh.earlier[(1411, "reviews", "r3")] = {
            "pageInfo": {"hasPreviousPage": False, "startCursor": "r1"},
            "nodes": [review("r1", SELF, T0), review("r2", "reviewer-a", T1, body="y")]}
        fetched = poll.fetch_pr(gh, "o", "r", 1411)
        self.assertEqual([c["id"] for c in fetched["comments"]["nodes"]], ["i1", "i2", "i3"])
        self.assertEqual([r["id"] for r in fetched["reviews"]["nodes"]], ["r1", "r2", "r3"])
        payload = poll.tails_payload(fetched, {}, SELF, [])
        self.assertEqual([r["id"] for r in payload["top_level"]], ["i1", "i2", "i3", "r2", "r3"])
        self.assertNotIn("truncated", payload)

    def test_missing_pr_raises(self):
        gh = FakeGh()
        gh.prs[1411] = None
        with self.assertRaises(poll.GhError):
            poll.fetch_pr(gh, "o", "r", 1411)


class TickQueryTests(unittest.TestCase):
    def test_every_pr_gets_an_alias_and_no_threads(self):
        query = poll.tick_query("mindbody", "Mindbody.Scheduling", [1411, 1413])
        self.assertIn("p1411: pullRequest(number: 1411)", query)
        self.assertIn("p1413: pullRequest(number: 1413)", query)
        self.assertNotIn("reviewThreads", query)

    def test_unsafe_names_are_refused(self):
        with self.assertRaises(ValueError):
            poll.tick_query('o") { x', "r", [1])


if __name__ == "__main__":
    unittest.main()
