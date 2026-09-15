import base64
import contextlib
import http.server
import io
import json
import os
import pathlib
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

from fakes import ACTIONS, AZURE, SONAR, FakeGh, poll, watch

BUILD = ("https://dev.azure.com/mindbody/19477e8d-94b2-4461-9dfc-2f54fa23767d"
         "/_apis/build/builds/3366211")
PAT = "pat-value-for-tests"
ORGS = ["mindbody"]
OTHER_ORG = AZURE.replace("/mindbody/", "/attacker-org/")


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


def record(kind, result, name, log_id=None, identifier=None, finished=True):
    return {"type": kind, "result": result, "name": name, "identifier": identifier,
            "finishTime": "2026-09-10T05:16:39Z" if finished else None,
            "log": {"id": log_id} if log_id is not None else None}


class FailedRecordsTests(unittest.TestCase):
    @staticmethod
    def names(records, kind="Task"):
        return [r["name"] for r in poll.failed_records({"records": records}, kind)]

    def test_failed_records_are_returned_ahead_of_canceled_ones(self):
        self.assertEqual(self.names([record("Task", "canceled", "timed out"),
                                     record("Task", "failed", "Run tests")]), ["Run tests"])

    def test_without_a_failure_finished_canceled_records_are_returned(self):
        self.assertEqual(self.names([record("Task", "canceled", "timed out"),
                                     record("Task", "canceled", "never ran", finished=False),
                                     record("Stage", "canceled", "Gated"),
                                     record("Task", "succeeded", "Restore")]), ["timed out"])

    def test_a_timed_out_stage_is_retried(self):
        ado = FakeAdo([record("Stage", "canceled", "Gated", identifier="gated")])
        self.assertEqual(poll.ci_rerun(FakeGh(), "o/r", AZURE, ORGS, ado=ado), ["stage gated"])


class AdoOrgTests(unittest.TestCase):
    def test_an_allowed_org_is_matched_without_case(self):
        ado = FakeAdo([record("Task", "failed", "Run tests", log_id=7)], logs={7: "boom"})
        self.assertIn("boom", poll.ci_log(FakeGh(), "o/r", AZURE, ["MindBody"], ado=ado))

    def test_another_org_raises_before_any_request(self):
        opener = Opener()
        with mock.patch.object(poll, "_NO_REDIRECT_OPENER", opener), \
                mock.patch.dict(os.environ, {"AZURE_DEVOPS_EXT_PAT": PAT}):
            for run in (poll.ci_log, poll.ci_rerun):
                with self.subTest(mode=run.__name__), self.assertRaises(poll.GhError) as caught:
                    run(FakeGh(), "o/r", OTHER_ORG, ORGS)
                self.assertEqual(str(caught.exception),
                                 "Azure DevOps org attacker-org is not in ado_orgs")
        self.assertEqual(opener.requests, [])


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

    def test_the_default_opener_refuses_a_redirect_without_following_it(self):
        hits = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.end_headers()

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/from"
            with mock.patch.dict(os.environ, {"AZURE_DEVOPS_EXT_PAT": PAT}):
                with self.assertRaises(poll.GhError) as caught:
                    poll.ado_request(url)
            self.assertIn("302", str(caught.exception))
            self.assertNotIn(PAT, str(caught.exception))
            self.assertNotIn("/elsewhere", hits)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


class CiLogTests(unittest.TestCase):
    def test_actions_log_keeps_the_last_lines_when_no_marker_is_found(self):
        gh = FakeGh()
        gh.job_logs["102752575845"] = "\n".join(f"line {i}" for i in range(6000))
        lines = poll.ci_log(gh, "o/r", ACTIONS, ORGS).splitlines()
        self.assertEqual((len(lines), lines[0], lines[-1]), (2000, "line 4000", "line 5999"))
        self.assertIn(["api", "repos/o/r/actions/jobs/102752575845/logs"], gh.calls)

    def test_actions_log_with_one_marker_is_one_window_around_it(self):
        gh = FakeGh()
        raw = [f"line {i}" for i in range(6000)]
        raw[800] = "##[error] the real failure is here"
        gh.job_logs["102752575845"] = "\n".join(raw)
        lines = poll.ci_log(gh, "o/r", ACTIONS, ORGS).splitlines()
        self.assertLessEqual(len(lines), 2000)
        self.assertIn("##[error] the real failure is here", lines)
        self.assertEqual(lines, raw[int(lines[0].split()[1]):int(lines[-1].split()[1]) + 1])

    def test_actions_log_keeps_the_first_and_the_last_marker(self):
        raw = [f"line {i}" for i in range(6000)]
        raw[100] = "##[error] a continue-on-error step failed"
        raw[5800] = "error CS1002: ; expected"
        lines = poll.failure_window("\n".join(raw)).splitlines()
        self.assertIn(raw[100], lines)
        self.assertIn(raw[5800], lines)
        self.assertIn("... 3821 lines omitted ...", lines)
        self.assertEqual(len(lines), 2001)
        self.assertEqual((lines[0], lines[999], lines[1001], lines[-1]),
                         ("line 0", "line 999", "line 4821", "line 5820"))

    def test_markers_whose_windows_overlap_are_one_window(self):
        raw = [f"line {i}" for i in range(6000)]
        raw[3000] = "##[error] first"
        raw[3600] = "##[error] last"
        lines = poll.failure_window("\n".join(raw)).splitlines()
        self.assertFalse(any("omitted" in line for line in lines))
        self.assertEqual((lines[0], lines[-1]), ("line 2621", "line 3749"))

    def test_azure_log_joins_the_failed_task_logs(self):
        ado = FakeAdo([record("Stage", "failed", "Gated", identifier="gated"),
                       record("Task", "failed", "Run tests", log_id=7),
                       record("Task", "succeeded", "Restore", log_id=3)],
                      logs={7: "Failed ShouldBook [42 ms]", 3: "restored"})
        text = poll.ci_log(FakeGh(), "o/r", AZURE, ORGS, ado=ado)
        self.assertIn("== Run tests ==", text)
        self.assertIn("Failed ShouldBook", text)
        self.assertNotIn("restored", text)
        self.assertEqual(ado.calls[0], ("GET", f"{BUILD}/timeline?api-version=7.1", None))

    def test_other_platform_has_no_log_source(self):
        with self.assertRaises(poll.GhError):
            poll.ci_log(FakeGh(), "o/r", SONAR, ORGS)

    def test_azure_build_with_no_failed_task_raises(self):
        ado = FakeAdo([record("Task", "succeeded", "Restore", log_id=3)], logs={3: "restored"})
        with self.assertRaises(poll.GhError):
            poll.ci_log(FakeGh(), "o/r", AZURE, ORGS, ado=ado)


class CiRerunTests(unittest.TestCase):
    def test_actions_reruns_the_failed_jobs_of_the_run(self):
        gh = FakeGh()
        self.assertEqual(poll.ci_rerun(gh, "o/r", ACTIONS, ORGS), ["run 34439594621"])
        self.assertIn(["run", "rerun", "34439594621", "--failed", "--repo", "o/r"], gh.calls)

    def test_azure_retries_each_failed_stage_by_identifier(self):
        ado = FakeAdo([record("Stage", "failed", "Gated", identifier="gated"),
                       record("Stage", "succeeded", "Build", identifier="build")])
        self.assertEqual(poll.ci_rerun(FakeGh(), "o/r", AZURE, ORGS, ado=ado), ["stage gated"])
        self.assertEqual(ado.calls[-1], (
            "PATCH", f"{BUILD}/stages/gated?api-version=7.1-preview.1",
            {"state": "retry", "forceRetryAllJobs": False}))

    def test_azure_build_with_no_failed_stage_raises_without_patching(self):
        ado = FakeAdo([record("Stage", "succeeded", "Build", identifier="build")])
        with self.assertRaises(poll.GhError):
            poll.ci_rerun(FakeGh(), "o/r", AZURE, ORGS, ado=ado)
        self.assertFalse(any(call[0] == "PATCH" for call in ado.calls))


class CliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = tmp.name
        (pathlib.Path(tmp.name) / "watch.json").write_text(
            json.dumps(watch({1411: "authored"})), encoding="utf-8")

    def ci(self, *args, gh=None):
        return poll.main([*args, "--repo", "o/r", "--state-dir", self.state], gh=gh or FakeGh())

    def test_ci_log_needs_repo_and_state_dir_and_prints_the_log(self):
        gh = FakeGh()
        gh.job_logs["102752575845"] = "error CS1002: ; expected"
        for partial in (["--repo", "o/r"], ["--state-dir", self.state], []):
            with self.subTest(partial=partial), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit):
                poll.main(["--ci-log", ACTIONS, *partial], gh=gh)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.ci("--ci-log", ACTIONS, gh=gh)
        self.assertEqual((code, out.getvalue().strip()), (0, "error CS1002: ; expected"))

    def test_a_failure_is_one_line_on_stderr(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = self.ci("--ci-rerun", SONAR)
        self.assertEqual(code, 1)
        self.assertIn("no CI source", err.getvalue())

    def test_an_org_outside_ado_orgs_exits_one_without_a_request(self):
        opener = Opener()
        err = io.StringIO()
        with mock.patch.object(poll, "_NO_REDIRECT_OPENER", opener), \
                mock.patch.dict(os.environ, {"AZURE_DEVOPS_EXT_PAT": PAT}), \
                contextlib.redirect_stderr(err):
            code = self.ci("--ci-rerun", OTHER_ORG)
        self.assertEqual((code, err.getvalue()),
                         (1, "pr-watch: Azure DevOps org attacker-org is not in ado_orgs\n"))
        self.assertEqual(opener.requests, [])

    def test_an_org_in_ado_orgs_reaches_azure_devops(self):
        timeline = json.dumps({"records": [record("Task", "failed", "Run tests", log_id=7)]})
        opener = Opener(body=timeline)
        with mock.patch.object(poll, "_NO_REDIRECT_OPENER", opener), \
                mock.patch.dict(os.environ, {"AZURE_DEVOPS_EXT_PAT": PAT}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.ci("--ci-log", AZURE), 0)
        self.assertEqual([r.full_url for r in opener.requests],
                         [f"{BUILD}/timeline?api-version=7.1", f"{BUILD}/logs/7?api-version=7.1"])

    def run_against_local_ado(self, handler_cls):
        server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), thread.join(timeout=5), server.server_close()))
        with mock.patch.object(poll, "ADO_BUILD", f"http://127.0.0.1:{server.server_port}/build"), \
             mock.patch.dict(os.environ, {"AZURE_DEVOPS_EXT_PAT": PAT}):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = self.ci("--ci-log", AZURE)
        return code, err.getvalue()

    def test_a_redirect_from_ado_exits_one_stderr_line(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "/elsewhere")
                self.end_headers()

            def log_message(self, *a):
                pass

        code, err = self.run_against_local_ado(Handler)
        self.assertEqual(code, 1)
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertNotIn(PAT, err)

    def test_a_non_json_ado_body_exits_one_stderr_line(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"<html>sign in</html>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        code, err = self.run_against_local_ado(Handler)
        self.assertEqual(code, 1)
        self.assertEqual(len(err.strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
