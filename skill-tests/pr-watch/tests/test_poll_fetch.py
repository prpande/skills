import json
import subprocess
import unittest
from unittest import mock

from fakes import T0, FakeGh, comment, poll, pull, thread


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

    def test_truncation_is_reported_not_hidden(self):
        gh = FakeGh()
        pr = pull(threads=[thread("T1", [comment("c1", "reviewer-a", T0)])])
        pr["reviewThreads"]["nodes"][0]["comments"]["pageInfo"]["hasNextPage"] = True
        pr["comments"]["pageInfo"]["hasPreviousPage"] = True
        gh.prs[1411] = pr
        self.assertEqual(len(poll.fetch_pr(gh, "o", "r", 1411)["truncated"]), 2)

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
