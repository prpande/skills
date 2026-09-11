import base64
import contextlib
import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from fakes import FakeGh, poll

ACTIONS = "https://github.com/o/r/actions/runs/34439594621/job/102752575845"
AZURE = ("https://dev.azure.com/mindbody/19477e8d-94b2-4461-9dfc-2f54fa23767d"
         "/_build/results?buildId=3366211")
BUILD = ("https://dev.azure.com/mindbody/19477e8d-94b2-4461-9dfc-2f54fa23767d"
         "/_apis/build/builds/3366211")
SONAR = "https://sonarqube.example/dashboard?id=r&pullRequest=1411"
PAT = "pat-value-for-tests"


class Opener:
    def __init__(self, body="{}", error=None):
        self.body, self.error, self.requests = body, error, []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return io.BytesIO(self.body.encode("utf-8"))


class FakeAdo:
    def __init__(self, records, logs=None):
        self.records, self.logs, self.calls = records, logs or {}, []

    def __call__(self, url, method="GET", body=None):
        self.calls.append((method, url, body))
        if "/timeline?" in url:
            return json.dumps({"records": self.records})
        if "/logs/" in url:
            return self.logs[int(url.split("/logs/")[1].split("?")[0])]
        if "/stages/" in url:
            return ""
        raise AssertionError(url)


def record(kind, result, name, log_id=None, identifier=None):
    return {"type": kind, "result": result, "name": name, "identifier": identifier,
            "log": {"id": log_id} if log_id is not None else None}


class AdoRequestTests(unittest.TestCase):
    def test_header_is_basic_auth_of_the_pat(self):
        opener = Opener(body="ok")
        with mock.patch.dict(os.environ, {"AZURE_DEVOPS_EXT_PAT": PAT}):
            self.assertEqual(poll.ado_request(f"{BUILD}/timeline?api-version=7.1",
                                              opener=opener), "ok")
        expected = "Basic " + base64.b64encode(f":{PAT}".encode("ascii")).decode("ascii")
        self.assertEqual(opener.requests[0].get_header("Authorization"), expected)
        self.assertEqual(opener.requests[0].get_method(), "GET")

    def test_missing_pat_raises_before_any_request(self):
        opener = Opener()
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(poll.GhError):
                poll.ado_request(f"{BUILD}/timeline?api-version=7.1", opener=opener)
        self.assertEqual(opener.requests, [])

    def test_http_error_message_carries_the_status_and_not_the_pat(self):
        error = urllib.error.HTTPError(f"{BUILD}/timeline", 401, "Unauthorized", {}, None)
        with mock.patch.dict(os.environ, {"AZURE_DEVOPS_EXT_PAT": PAT}):
            with self.assertRaises(poll.GhError) as caught:
                poll.ado_request(f"{BUILD}/timeline?api-version=7.1", opener=Opener(error=error))
        self.assertIn("401", str(caught.exception))
        self.assertNotIn(PAT, str(caught.exception))


class CiLogTests(unittest.TestCase):
    def test_actions_log_keeps_the_last_5000_lines(self):
        gh = FakeGh()
        gh.job_logs["102752575845"] = "\n".join(f"line {i}" for i in range(6000))
        lines = poll.ci_log(gh, "o/r", ACTIONS).splitlines()
        self.assertEqual((len(lines), lines[0], lines[-1]), (5000, "line 1000", "line 5999"))
        self.assertIn(["run", "view", "--job", "102752575845", "--repo", "o/r", "--log-failed"],
                      gh.calls)

    def test_azure_log_joins_the_failed_task_logs(self):
        ado = FakeAdo([record("Stage", "failed", "Gated", identifier="gated"),
                       record("Task", "failed", "Run tests", log_id=7),
                       record("Task", "succeeded", "Restore", log_id=3)],
                      logs={7: "Failed ShouldBook [42 ms]", 3: "restored"})
        text = poll.ci_log(FakeGh(), "o/r", AZURE, ado=ado)
        self.assertIn("== Run tests ==", text)
        self.assertIn("Failed ShouldBook", text)
        self.assertNotIn("restored", text)
        self.assertEqual(ado.calls[0], ("GET", f"{BUILD}/timeline?api-version=7.1", None))

    def test_other_platform_has_no_log_source(self):
        with self.assertRaises(poll.GhError):
            poll.ci_log(FakeGh(), "o/r", SONAR)


class CiRerunTests(unittest.TestCase):
    def test_actions_reruns_the_failed_jobs_of_the_run(self):
        gh = FakeGh()
        self.assertEqual(poll.ci_rerun(gh, "o/r", ACTIONS), ["run 34439594621"])
        self.assertIn(["run", "rerun", "34439594621", "--failed", "--repo", "o/r"], gh.calls)

    def test_azure_retries_each_failed_stage_by_identifier(self):
        ado = FakeAdo([record("Stage", "failed", "Gated", identifier="gated"),
                       record("Stage", "succeeded", "Build", identifier="build")])
        self.assertEqual(poll.ci_rerun(FakeGh(), "o/r", AZURE, ado=ado), ["stage gated"])
        self.assertEqual(ado.calls[-1], (
            "PATCH", f"{BUILD}/stages/gated?api-version=7.1-preview.1",
            {"state": "retry", "forceRetryAllJobs": False}))


class CliTests(unittest.TestCase):
    def test_ci_log_needs_repo_and_prints_the_log(self):
        gh = FakeGh()
        gh.job_logs["102752575845"] = "error CS1002: ; expected"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            poll.main(["--ci-log", ACTIONS], gh=gh)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = poll.main(["--ci-log", ACTIONS, "--repo", "o/r"], gh=gh)
        self.assertEqual((code, out.getvalue().strip()), (0, "error CS1002: ; expected"))

    def test_a_failure_is_one_line_on_stderr(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = poll.main(["--ci-rerun", SONAR, "--repo", "o/r"], gh=FakeGh())
        self.assertEqual(code, 1)
        self.assertIn("no CI source", err.getvalue())


if __name__ == "__main__":
    unittest.main()
