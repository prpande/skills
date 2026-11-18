import json
import re
import unittest

from unittest import mock

from fakes import NOW, FakeGh, pk, poll, pull, rk, watch
from test_poll_ci import check
from test_poll_review_ready import handled_view, ready_pr

GATED = "Gated / Unit Tests"


class StackedGh(FakeGh):
    def __init__(self):
        super().__init__()
        self.default = "main"
        self.rules = {}
        self.classic = {}
        self.all_checks = {}
        self.merged_base = {}
        self.retargets = {}
        self.base_tip = "tip1"

    def __call__(self, args):
        if args[:1] == ["api"] and "/rules/branches/" in args[1]:
            self.calls.append(list(args))
            return "".join(f"{name}\n" for name in self.rules.get("/".join(args[1].split("/")[1:3]), []))
        if args[:1] == ["api"] and args[1].endswith("/protection/required_status_checks"):
            self.calls.append(list(args))
            contexts = self.classic.get("/".join(args[1].split("/")[1:3]))
            if contexts is None:
                raise poll.GhError("gh: Not Found (HTTP 404)")
            return "".join(f"{name}\n" for name in contexts)
        if args[:2] == ["pr", "checks"] and "--required" not in args:
            self.calls.append(list(args))
            owner, name = args[args.index("--repo") + 1].lower().split("/")
            key = (owner, name, int(args[2]))
            if key in self.fail_checks:
                raise poll.GhError("HTTP 502: checks unavailable")
            if key in self.no_checks:
                raise poll.GhError("no checks reported on the 'rung-1' branch")
            return json.dumps(self.all_checks.get(key, []))
        if args[:1] == ["api"] and "/pulls/" in args[1] and any(".base.ref" in a for a in args):
            self.calls.append(list(args))
            owner, name = args[1].split("/")[1:3]
            p = self.prs[(owner.lower(), name.lower(), int(args[1].rsplit("/", 1)[1]))]
            return f"{p['baseRefName']} {p['headRefOid']} {self.default}\n"
        out = super().__call__(args)
        if args[:2] == ["api", "graphql"] and 'repository(owner: "' in args[3]:
            data = json.loads(out)["data"]
            for alias, nodes in data.items():
                owner, name = re.search(rf'{alias}: repository\(owner: "([^"]+)", name: "([^"]+)"',
                                        args[3]).groups()
                for node in (nodes or {}).values():
                    if node is None:
                        continue
                    node["baseRepository"] = {"defaultBranchRef": {"name": self.default}}
                    merged = self.merged_base.get((owner.lower(), name.lower(), node["number"]))
                    merged = merged and {"headRefOid": self.base_tip, "baseRefName": self.default,
                                         **merged}
                    node["timelineItems"] = {"totalCount": self.retargets.get(
                        (owner.lower(), name.lower(), node["number"]), 0)}
                    node["baseRef"] = {"target": {"oid": self.base_tip},
                                       "associatedPullRequests": {"nodes": [merged] if merged else []}}
            return json.dumps({"data": data})
        return out


class StackedBase(unittest.TestCase):
    def setUp(self):
        self.gh = StackedGh()
        self.gh.prs[pk(1411)] = pull(1411)
        self.gh.prs[pk(1411)]["baseRefName"] = "rung-1"
        self.gh.rollup[pk(1411)] = "SUCCESS"
        self.gh.rules["o/r"] = [GATED]
        self.gh.all_checks[pk(1411)] = [check("Wiz", "pass")]
        self.watch = watch({1411: "authored"})
        self.poller = {}

    def tick(self, force=False):
        return poll.tick_once(self.gh, self.watch, self.poller, NOW, force=force)

    def kinds(self, events):
        return [e["kind"] for e in events]


class QueryAndNameTests(unittest.TestCase):
    def test_tick_query_asks_for_default_branch_and_merged_base(self):
        query = poll.tick_query({("o", "r"): [1411]})[0]
        self.assertIn("baseRepository { defaultBranchRef { name } }", query)
        self.assertIn("baseRef { target { oid } associatedPullRequests(states: MERGED, first: 1, "
                      "orderBy: {field: CREATED_AT, direction: DESC}) { nodes { number baseRefName headRefOid } } }",
                      query)
        self.assertIn("timelineItems(itemTypes: [BASE_REF_CHANGED_EVENT, "
                      "AUTOMATIC_BASE_CHANGE_SUCCEEDED_EVENT], first: 0) { totalCount }", query)

    def test_default_required_names_unions_ruleset_and_classic(self):
        gh = StackedGh()
        gh.rules["o/r"] = ["A", "B"]
        gh.classic["o/r"] = ["B", "C"]
        self.assertEqual(poll.default_required_names(gh, "o/r", "main"), ["A", "B", "C"])
        gh.classic["o/r"] = None
        self.assertEqual(poll.default_required_names(gh, "o/r", "main"), ["A", "B"])

    def test_default_required_names_quotes_the_branch(self):
        gh = StackedGh()
        poll.default_required_names(gh, "o/r", "release/1")
        self.assertTrue(all("release%2F1" in c[1] for c in gh.calls))

    def test_forbidden_protection_call_counts_as_no_names(self):
        gh = StackedGh()
        gh.rules["o/r"] = ["A"]

        def forbidden(args):
            if args[1].endswith("/protection/required_status_checks"):
                raise poll.GhError("gh: Must have admin rights to Repository. (HTTP 403)")
            return gh(args)
        self.assertEqual(poll.default_required_names(forbidden, "o/r", "main"), ["A"])

    def test_forbidden_rules_call_raises(self):
        def forbidden(args):
            if "/rules/branches/" in args[1]:
                raise poll.GhError("gh: Resource protected by SAML enforcement (HTTP 403)")
            return ""
        with self.assertRaises(poll.GhError):
            poll.default_required_names(forbidden, "o/r", "main")

    def test_other_errors_raise(self):
        def boom(args):
            raise poll.GhError("HTTP 502")
        with self.assertRaises(poll.GhError):
            poll.default_required_names(boom, "o/r", "main")

    def failing(self, endpoint, message):
        gh = StackedGh()
        gh.rules["o/r"] = ["A"]
        gh.classic["o/r"] = ["B"]

        def call(args):
            if endpoint in args[1]:
                raise poll.GhError(message)
            return gh(args)
        return call

    def test_missing_rules_endpoint_is_tolerated_by_each_marker(self):
        for message in ("gh: Gone (HTTP 404)", "gh: Not Found"):
            with self.subTest(message):
                call = self.failing("/rules/branches/", message)
                self.assertEqual(poll.default_required_names(call, "o/r", "main"), ["B"])

    def test_missing_protection_is_tolerated_by_each_marker(self):
        for message in ("gh: Gone (HTTP 404)", "gh: Forbidden (HTTP 403)", "gh: Not Found",
                        "gh: Must have admin rights to Repository."):
            with self.subTest(message):
                call = self.failing("/protection/", message)
                self.assertEqual(poll.default_required_names(call, "o/r", "main"), ["A"])

    def test_a_bare_status_number_inside_other_text_is_not_a_missing_marker(self):
        for endpoint, message in (("/rules/branches/", "gh: run 5404 failed"),
                                  ("/protection/", "gh: run 5403 failed")):
            with self.subTest(endpoint):
                with self.assertRaises(poll.GhError):
                    poll.default_required_names(self.failing(endpoint, message), "o/r", "main")

    def test_memo_answers_the_second_lookup_for_the_same_repo_and_branch(self):
        gh = StackedGh()
        gh.rules["o/r"] = ["A"]
        memo = {}
        self.assertEqual(poll.default_required_names(gh, "o/r", "main", memo), ["A"])
        calls = len(gh.calls)
        self.assertEqual(poll.default_required_names(gh, "o/r", "main", memo), ["A"])
        self.assertEqual(len(gh.calls), calls)
        poll.default_required_names(gh, "o/r", "release", memo)
        self.assertGreater(len(gh.calls), calls)

    def test_no_required_names_skips_the_checks_lookup(self):
        gh = StackedGh()
        gh.all_checks[pk(1411)] = [check(GATED, "pass")]
        self.assertEqual(poll.stacked_checks(gh, "o/r", 1411, "main"), ([], []))
        self.assertEqual(gh.checks_calls(), 0)


class StackedTickTests(StackedBase):
    def test_stacked_rung_with_gated_checks_missing_is_unchecked(self):
        events = self.tick()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], {
            "pr": rk(1411), "role": "authored", "kind": "ci-unchecked", "head": "h2",
            "base": "rung-1", "default": "main", "missing": [GATED]})

    def test_unchecked_raised_once_per_head_rollup_and_missing(self):
        self.tick()
        self.assertNotIn("ci-unchecked", self.kinds(self.tick()))

    def test_no_unchecked_while_rollup_pending(self):
        self.gh.rollup[pk(1411)] = "PENDING"
        self.assertNotIn("ci-unchecked", self.kinds(self.tick()))

    def test_unchecked_suppressed_once_session_recorded_it(self):
        self.watch["prs"][rk(1411)]["ci_handled"] = ["h2|ci-unchecked"]
        self.assertNotIn("ci-unchecked", self.kinds(self.tick(force=True)))

    def test_forced_pass_ignores_the_mark(self):
        self.tick()
        self.assertIn("ci-unchecked", self.kinds(self.tick(force=True)))

    def test_stacked_red_required_check_raises_ci_red(self):
        self.gh.rollup[pk(1411)] = "FAILURE"
        self.gh.all_checks[pk(1411)] = [check(GATED), check("Wiz", "pass")]
        events = self.tick()
        self.assertEqual(self.kinds(events), ["ci-red"])
        self.assertEqual([c["name"] for c in events[0]["checks"]], [GATED])

    def test_default_base_makes_no_rules_call(self):
        self.gh.prs[pk(1411)]["baseRefName"] = "main"
        self.assertEqual(self.tick(), [])
        self.assertFalse([c for c in self.gh.calls if any("/rules/branches/" in a for a in c)])

    def test_retargeted_rung_still_checked(self):
        self.assertIn("ci-unchecked", self.kinds(self.tick()))
        self.gh.prs[pk(1411)]["baseRefName"] = "main"
        self.gh.rollup[pk(1411)] = "FAILURE"
        events = [e for e in self.tick() if e["kind"] == "ci-unchecked"]
        self.assertEqual([e["base"] for e in events], ["main"])

    def test_base_merged_raised_once(self):
        self.gh.all_checks[pk(1411)] = [check(GATED, "pass")]
        self.gh.merged_base[pk(1411)] = {"number": 1400}
        events = self.tick()
        self.assertEqual(events, [{
            "pr": rk(1411), "role": "authored", "kind": "base-merged", "head": "h2",
            "base": "rung-1", "default": "main", "base_pr": 1400}])
        self.assertEqual(self.tick(), [])

    def test_no_base_merged_when_base_moved_since_merge(self):
        self.gh.all_checks[pk(1411)] = [check(GATED, "pass")]
        self.gh.merged_base[pk(1411)] = {"number": 1400, "headRefOid": "old"}
        self.assertNotIn("base-merged", self.kinds(self.tick()))

    def test_no_base_merged_on_default_base(self):
        self.gh.prs[pk(1411)]["baseRefName"] = "main"
        self.gh.merged_base[pk(1411)] = {"number": 1400}
        self.assertNotIn("base-merged", self.kinds(self.tick()))

    def test_no_base_merged_when_the_merged_pr_targeted_another_branch(self):
        self.gh.merged_base[pk(1411)] = {"number": 1400, "baseRefName": "rung-0"}
        self.assertNotIn("base-merged", self.kinds(self.tick()))

    def test_merged_base_pr_skips_null_nodes(self):
        node = {"baseRepository": {"defaultBranchRef": {"name": "main"}},
                "baseRef": {"target": {"oid": "t"}, "associatedPullRequests": {"nodes": [None]}}}
        self.assertIsNone(poll.merged_base_pr(node))

    def test_marks_are_dropped_when_the_pr_closes(self):
        self.gh.merged_base[pk(1411)] = {"number": 1400}
        self.tick()
        self.gh.prs[pk(1411)]["state"] = "MERGED"
        self.tick()
        self.assertNotIn(rk(1411), self.poller["unchecked"])
        self.assertNotIn(rk(1411), self.poller["base_merged"])

    def test_reviewed_role_gets_no_base_merged_and_no_stacked_mark(self):
        self.watch = watch({1411: "reviewed"})
        self.gh.merged_base[pk(1411)] = {"number": 1400}
        self.assertEqual(self.tick(), [])
        self.assertNotIn("stacked", self.poller["prs"][rk(1411)])

    def test_authored_stacked_pr_stores_the_stacked_mark(self):
        self.tick()
        self.assertTrue(self.poller["prs"][rk(1411)]["stacked"])

    def test_a_base_merged_fault_does_not_stop_the_other_prs(self):
        self.gh.prs[pk(1412)] = pull(1412)
        self.gh.prs[pk(1412)]["baseRefName"] = "rung-1"
        self.gh.rollup[pk(1412)] = "SUCCESS"
        self.gh.all_checks[pk(1412)] = [check(GATED, "pass")]
        self.gh.all_checks[pk(1411)] = [check(GATED, "pass")]
        self.gh.merged_base[pk(1411)] = self.gh.merged_base[pk(1412)] = {"number": 1400}
        self.watch = watch({1411: "authored", 1412: "authored"})
        real = poll.check_base_merged

        def faulty(view, poller, key, node, events):
            if key == rk(1411):
                raise poll.GhError("boom")
            return real(view, poller, key, node, events)
        with mock.patch.object(poll, "check_base_merged", faulty):
            events = self.tick()
        self.assertEqual([(e["pr"], e["kind"]) for e in events], [(rk(1412), "base-merged")])

    def test_retargeted_pr_on_the_default_branch_counts_as_stacked(self):
        self.gh.prs[pk(1411)]["baseRefName"] = "main"
        self.assertEqual(self.tick(), [])
        self.gh.retargets[pk(1411)] = 1
        self.assertEqual(self.kinds(self.tick(force=True)), ["ci-unchecked"])

    def test_names_are_looked_up_once_per_repo_and_branch_per_tick(self):
        for n in (1412, 1413):
            self.gh.prs[pk(n)] = pull(n)
            self.gh.prs[pk(n)]["baseRefName"] = "rung-1"
            self.gh.rollup[pk(n)] = "SUCCESS"
        self.watch = watch({1411: "authored", 1412: "authored", 1413: "authored"})
        self.assertEqual(self.kinds(self.tick()), ["ci-unchecked"] * 3)
        for endpoint in ("/rules/branches/", "/protection/required_status_checks"):
            self.assertEqual(sum(1 for c in self.gh.calls if endpoint in c[1] and c[0] == "api"), 1)
        self.gh.calls.clear()
        self.tick(force=True)
        self.assertEqual(sum(1 for c in self.gh.calls if "/rules/branches/" in c[1]), 1)

    def test_no_required_names_means_no_checks_lookup_and_no_event(self):
        self.gh.rules["o/r"] = []
        self.gh.rollup[pk(1411)] = "FAILURE"
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.gh.checks_calls(), 0)

    def test_expected_rollup_is_deferred_without_a_lookup(self):
        self.gh.rollup[pk(1411)] = "EXPECTED"
        self.assertEqual(self.tick(), [])
        self.assertFalse([c for c in self.gh.calls if "/rules/branches/" in c[1]])

    def test_unchecked_mark_suppresses_a_repeat_on_a_failing_rollup(self):
        self.gh.rollup[pk(1411)] = "FAILURE"
        self.assertEqual(self.kinds(self.tick()), ["ci-unchecked"])
        self.assertEqual(self.tick(), [])

    def test_missing_checks_report_counts_as_unchecked(self):
        self.gh.no_checks.add(pk(1411))
        events = self.tick()
        self.assertEqual([(e["kind"], e["missing"]) for e in events], [("ci-unchecked", [GATED])])

    def test_a_check_fault_is_retried_on_the_next_tick(self):
        self.gh.rollup[pk(1411)] = "PENDING"
        self.tick()
        self.gh.rollup[pk(1411)] = "SUCCESS"
        self.gh.fail_checks.add(pk(1411))
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.poller["errors"], {rk(1411): "check failed"})
        self.assertEqual(self.poller["prs"][rk(1411)]["last_rollup"], poll.CI_FAULT_ROLLUP)
        self.gh.fail_checks.clear()
        self.assertEqual(self.kinds(self.tick()), ["ci-unchecked"])

    def test_a_check_fault_on_a_new_head_with_the_same_rollup_is_retried(self):
        self.assertEqual(self.kinds(self.tick()), ["ci-unchecked"])
        self.gh.prs[pk(1411)]["headRefOid"] = "head2"
        self.gh.fail_checks.add(pk(1411))
        self.assertEqual(self.tick(), [])
        self.gh.fail_checks.clear()
        self.assertEqual(self.kinds(self.tick()), ["ci-unchecked"])

    def test_a_pending_rollup_on_a_retry_pass_does_not_spend_the_retry(self):
        self.watch["prs"][rk(1411)]["retry_after"] = NOW - 10
        self.gh.rollup[pk(1411)] = "PENDING"
        self.assertEqual(self.tick(), [])
        self.assertNotIn("ci_retried_at", self.poller["prs"][rk(1411)])
        self.gh.rollup[pk(1411)] = "SUCCESS"
        self.assertEqual(self.kinds(self.tick()), ["ci-unchecked"])
        self.assertEqual(self.poller["prs"][rk(1411)]["ci_retried_at"], NOW - 10)

    def test_a_retry_pass_raises_the_unchecked_event_again_once(self):
        self.assertEqual(self.kinds(self.tick()), ["ci-unchecked"])
        self.assertEqual(self.tick(), [])
        self.watch["prs"][rk(1411)]["retry_after"] = NOW - 10
        self.assertEqual(self.kinds(self.tick()), ["ci-unchecked"])
        self.assertEqual(self.tick(), [])

    def test_stacked_pr_with_a_missing_required_check_is_not_review_ready(self):
        self.gh.prs[pk(1411)] = ready_pr()
        self.gh.prs[pk(1411)]["baseRefName"] = "rung-1"
        self.watch = handled_view()
        self.assertEqual(self.kinds(self.tick()), ["ci-unchecked"])
        self.assertEqual(sum(1 for c in self.gh.calls if "/rules/branches/" in c[1]), 1)
        self.gh.all_checks[pk(1411)] = [check(GATED, "pass")]
        self.assertEqual(self.kinds(self.tick(force=True)), ["review-ready"])


class ChecksPayloadTests(StackedBase):
    def test_checks_payload_for_stacked_pr_filters_to_default_required(self):
        self.gh.all_checks[pk(1411)] = [check(GATED, "pass"), check("Wiz", "pass")]
        payload = poll.checks_payload(self.gh, "o", "r", 1411)
        self.assertEqual([c["name"] for c in payload["checks"]], [GATED])
        self.assertEqual(payload["missing"], [])
        self.gh.all_checks[pk(1411)] = [check("Wiz", "pass")]
        payload = poll.checks_payload(self.gh, "o", "r", 1411)
        self.assertEqual(payload["checks"], [])
        self.assertEqual(payload["missing"], [GATED])

    def test_checks_payload_reads_the_default_branch_from_the_pull_request(self):
        poll.checks_payload(self.gh, "o", "r", 1411)
        jq = next(a for c in self.gh.calls if ".base.ref" in " ".join(c) for a in c if ".base.ref" in a)
        self.assertIn(".base.repo.default_branch", jq)

    def test_checks_payload_on_default_base_has_no_missing_key(self):
        self.gh.prs[pk(1411)]["baseRefName"] = "main"
        self.assertNotIn("missing", poll.checks_payload(self.gh, "o", "r", 1411))


if __name__ == "__main__":
    unittest.main()
