import json
import re
import unittest

from fakes import ACTIONS, NOW, FakeGh, pk, poll, pull, rk, watch

GATED = "Gated / Unit Tests"


def check(name, bucket="fail"):
    return {"name": name, "state": "FAILURE" if bucket == "fail" else "SUCCESS",
            "bucket": bucket, "link": ACTIONS, "workflow": "App Gated",
            "completedAt": "2026-09-10T05:16:39Z"}


class StackedGh(FakeGh):
    def __init__(self):
        super().__init__()
        self.default = "main"
        self.rules = {}
        self.classic = {}
        self.all_checks = {}
        self.merged_base = {}
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
            return json.dumps(self.all_checks.get((owner, name, int(args[2])), []))
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
                    merged = merged and {"headRefOid": self.base_tip, **merged}
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
                      "orderBy: {field: CREATED_AT, direction: DESC}) { nodes { number url headRefOid } } }",
                      query)

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
        self.gh.merged_base[pk(1411)] = {"number": 1400, "url": "https://github.com/o/r/pull/1400"}
        events = self.tick()
        self.assertEqual(events, [{
            "pr": rk(1411), "role": "authored", "kind": "base-merged", "head": "h2",
            "base": "rung-1", "default": "main", "base_pr": 1400,
            "base_pr_url": "https://github.com/o/r/pull/1400"}])
        self.assertEqual(self.tick(), [])

    def test_no_base_merged_when_base_moved_since_merge(self):
        self.gh.all_checks[pk(1411)] = [check(GATED, "pass")]
        self.gh.merged_base[pk(1411)] = {"number": 1400, "url": "u", "headRefOid": "old"}
        self.assertNotIn("base-merged", self.kinds(self.tick()))

    def test_no_base_merged_on_default_base(self):
        self.gh.prs[pk(1411)]["baseRefName"] = "main"
        self.gh.merged_base[pk(1411)] = {"number": 1400, "url": "u"}
        self.assertNotIn("base-merged", self.kinds(self.tick()))

    def test_marks_are_dropped_when_the_pr_closes(self):
        self.gh.merged_base[pk(1411)] = {"number": 1400, "url": "u"}
        self.tick()
        self.gh.prs[pk(1411)]["state"] = "MERGED"
        self.tick()
        self.assertNotIn(rk(1411), self.poller["unchecked"])
        self.assertNotIn(rk(1411), self.poller["base_merged"])


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

    def test_checks_payload_on_default_base_has_no_missing_key(self):
        self.gh.prs[pk(1411)]["baseRefName"] = "main"
        self.assertNotIn("missing", poll.checks_payload(self.gh, "o", "r", 1411))


if __name__ == "__main__":
    unittest.main()
