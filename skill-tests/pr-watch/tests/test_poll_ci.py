import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from fakes import FakeGh, poll, pull, watch

NOW = 2_000_000_000
ACTIONS = "https://github.com/o/r/actions/runs/34439594621/job/102752575845"
AZURE = ("https://dev.azure.com/mindbody/19477e8d-94b2-4461-9dfc-2f54fa23767d"
         "/_build/results?buildId=3366211")
SONAR = "https://sonarqube.example/dashboard?id=r&pullRequest=1411"


def check(name, bucket="fail", workflow="App Gated", done="2026-09-10T05:16:39Z", link=ACTIONS):
    return {"name": name, "state": "FAILURE" if bucket == "fail" else "SUCCESS",
            "bucket": bucket, "link": link, "workflow": workflow, "completedAt": done}


def node(rollup):
    return {"number": 1411, "updatedAt": "u", "headRefOid": "h2", "state": "OPEN",
            "commits": {"nodes": [{"commit": {"statusCheckRollup": rollup}}]}}


class RollupTests(unittest.TestCase):
    def test_tick_query_asks_for_the_head_rollup(self):
        self.assertIn("commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }",
                      poll.tick_query("o", "r", [1411]))

    def test_rollup_state_reads_the_head_commit(self):
        self.assertEqual(poll.rollup_state(node({"state": "FAILURE"})), "FAILURE")

    def test_rollup_state_is_none_without_checks(self):
        self.assertIsNone(poll.rollup_state(node(None)))
        self.assertIsNone(poll.rollup_state({"number": 1411, "state": "OPEN"}))


class PlatformTests(unittest.TestCase):
    def test_actions_link(self):
        self.assertEqual(poll.check_platform(ACTIONS),
                         {"platform": "github-actions", "run_id": "34439594621",
                          "job_id": "102752575845"})

    def test_azure_link_with_a_project_guid(self):
        self.assertEqual(poll.check_platform(AZURE),
                         {"platform": "azure-pipelines", "org": "mindbody",
                          "project": "19477e8d-94b2-4461-9dfc-2f54fa23767d",
                          "build_id": "3366211"})

    def test_anything_else_is_other(self):
        self.assertEqual(poll.check_platform(SONAR), {"platform": "other"})
        self.assertEqual(poll.check_platform(None), {"platform": "other"})


class CiTickTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGh()
        self.gh.prs[1411] = pull(1411)
        self.watch = watch({1411: "authored"})
        self.poller = {}

    def tick(self, force=False):
        return poll.tick_once(self.gh, self.watch, self.poller, NOW, force=force)

    def red(self, done="2026-09-10T05:16:39Z"):
        self.gh.rollup[1411] = "FAILURE"
        self.gh.checks[1411] = [check("Gated / Unit Tests", done=done),
                                check("Gated / Audit Helm Chart", bucket="pass")]

    def test_required_failure_emits_one_ci_red(self):
        self.red()
        self.assertEqual(self.tick(), [{
            "pr": 1411, "role": "authored", "kind": "ci-red", "head": "h2",
            "checks": [{"name": "Gated / Unit Tests", "workflow": "App Gated",
                        "completed_at": "2026-09-10T05:16:39Z"}]}])

    def test_rollup_change_alone_checks_without_a_thread_fetch(self):
        self.gh.rollup[1411] = "PENDING"
        self.tick()
        fetches = self.gh.thread_fetches()
        self.red()
        self.assertEqual([e["kind"] for e in self.tick()], ["ci-red"])
        self.assertEqual(self.gh.thread_fetches(), fetches)
        self.assertEqual(self.gh.checks_calls(), 1)

    def test_only_a_non_required_failure_is_silent(self):
        self.gh.rollup[1411] = "FAILURE"
        self.gh.checks[1411] = [check("Gated / Unit Tests", bucket="pass")]
        self.assertEqual(self.tick(), [])

    def test_same_failure_is_neither_emitted_nor_rechecked(self):
        self.red()
        self.tick()
        self.assertEqual(self.tick(), [])
        self.gh.prs[1411] = pull(1411, updated="2026-09-11T11:00:00Z")
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.gh.checks_calls(), 1)

    def test_a_rerun_that_fails_again_emits_again(self):
        self.red()
        self.tick()
        self.gh.rollup[1411] = "PENDING"
        self.assertEqual(self.tick(), [])
        self.red(done="2026-09-10T06:02:11Z")
        self.assertEqual(self.tick()[0]["checks"][0]["completed_at"], "2026-09-10T06:02:11Z")

    def test_a_rerun_that_fails_the_same_way_does_not_re_emit(self):
        self.red()
        self.tick()
        self.gh.rollup[1411] = "PENDING"
        self.assertEqual(self.tick(), [])
        self.red()
        self.assertEqual(self.tick(), [])

    def test_one_name_in_two_workflows_is_two_checks(self):
        self.gh.rollup[1411] = "FAILURE"
        self.gh.checks[1411] = [check("Gated / Unit Tests", workflow="Sonarqube"),
                                check("Gated / Unit Tests")]
        self.assertEqual([c["workflow"] for c in self.tick()[0]["checks"]],
                         ["App Gated", "Sonarqube"])

    def test_reviewed_pr_is_never_checked(self):
        self.watch = watch({1411: "reviewed"})
        self.red()
        self.tick()
        self.assertEqual(self.gh.checks_calls(), 0)

    def test_no_required_checks_reads_as_none(self):
        self.gh.rollup[1411] = "FAILURE"
        self.gh.no_checks.add(1411)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(self.tick(), [])
        self.assertEqual(err.getvalue(), "")

    def test_reconciliation_re_emits_a_standing_failure(self):
        self.red()
        self.tick()
        self.assertEqual([e["kind"] for e in self.tick(force=True)], ["ci-red"])


class ChecksPayloadTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGh()
        self.gh.prs[1411] = pull(1411)
        self.gh.checks[1411] = [
            check("Gated / Unit Tests"),
            check("SonarQube Code Analysis", bucket="pass", workflow="", link=SONAR),
            check("Mindbody.Scheduling.Gated", workflow="", link=AZURE),
            check("ci/legacy", workflow="", link="https://ci.example/legacy/1"),
        ]
        self.gh.base_runs["main"] = [("Gated / Unit Tests", "failure"),
                                     ("SonarQube Code Analysis", "success")]
        self.gh.base_statuses["main"] = [("ci/legacy", "error")]

    def payload(self):
        return poll.checks_payload(self.gh, watch({1411: "authored"}), 1411)

    def test_each_check_carries_its_platform_and_base_conclusion(self):
        payload = self.payload()
        self.assertEqual((payload["pr"], payload["head"], payload["base"]), (1411, "h2", "main"))
        by_name = {c["name"]: c for c in payload["checks"]}
        self.assertEqual(by_name["Gated / Unit Tests"], {
            "name": "Gated / Unit Tests", "state": "FAILURE", "bucket": "fail",
            "link": ACTIONS, "workflow": "App Gated", "completed_at": "2026-09-10T05:16:39Z",
            "on_base": "failure", "platform": "github-actions",
            "run_id": "34439594621", "job_id": "102752575845"})
        self.assertEqual(by_name["Mindbody.Scheduling.Gated"]["build_id"], "3366211")
        self.assertIsNone(by_name["Mindbody.Scheduling.Gated"]["on_base"])
        self.assertEqual(by_name["SonarQube Code Analysis"]["platform"], "other")
        self.assertEqual(by_name["ci/legacy"]["on_base"], "error")

    def test_a_failing_base_conclusion_wins_over_a_passing_duplicate(self):
        self.gh.base_runs["main"] = [("Gated / Unit Tests", "success"),
                                     ("Gated / Unit Tests", "failure"),
                                     ("Gated / Unit Tests", "success")]
        by_name = {c["name"]: c for c in self.payload()["checks"]}
        self.assertEqual(by_name["Gated / Unit Tests"]["on_base"], "failure")

    def test_base_branch_with_a_slash_is_encoded(self):
        self.gh.prs[1411]["baseRefName"] = "release/2026"
        self.gh.base_runs["release/2026"] = [("Gated / Unit Tests", "success")]
        payload = self.payload()
        self.assertEqual(payload["base"], "release/2026")
        self.assertIn("repos/o/r/commits/release%2F2026/check-runs", [c[1] for c in self.gh.calls])
        self.assertEqual(payload["checks"][0]["on_base"], "success")

    def test_cli_prints_the_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "watch.json").write_text(
                json.dumps(watch({1411: "authored"})), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = poll.main(["--checks", "1411", "--state-dir", tmp], gh=self.gh)
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out.getvalue())["checks"]), 4)


if __name__ == "__main__":
    unittest.main()
