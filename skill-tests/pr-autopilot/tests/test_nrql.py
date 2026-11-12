import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "pr-tooling" / "pr-autopilot" / "scripts"))

import nrql  # noqa: E402

QUERY = "SELECT count(*) FROM Transaction SINCE 7 days ago"


class NrqlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = pathlib.Path(self.tmp.name) / "run" / "nrql.json"
        self.calls = []

    def run_cli(
        self,
        query=QUERY,
        *,
        env=None,
        which=lambda name: "newrelic-bin",
        exit_code=0,
        run=None,
        lock_wait=0.2,
    ):
        def fake_run(argv, **kwargs):
            self.calls.append(argv)
            self.run_kwargs = kwargs
            return types.SimpleNamespace(returncode=exit_code, stdout="rows\n", stderr="")

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = nrql.main(
                ["--state", str(self.state), query],
                env={"NEW_RELIC_ACCOUNT_ID": "42"} if env is None else env,
                home=pathlib.Path(self.tmp.name),
                which=which,
                run=run or fake_run,
                lock_wait=lock_wait,
            )
        return code, out.getvalue(), err.getvalue()

    def saved_queries(self):
        return json.loads(self.state.read_text(encoding="utf-8"))["queries"]

    def lock_path(self):
        return nrql.lock_path(self.state)

    def test_runs_the_query_and_counts_it(self):
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(out, "rows\n")
        self.assertEqual(
            self.calls,
            [["newrelic-bin", "nrql", "query", "--accountId", "42", "--query", QUERY]],
        )
        saved = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(saved["queries"], [{"query": QUERY, "exit": 0}])

    def test_query_after_the_cap_is_refused_and_not_run(self):
        for _ in range(nrql.MAX_QUERIES):
            self.assertEqual(self.run_cli()[0], 0)
        code, _, err = self.run_cli()
        self.assertEqual(code, nrql.EXIT_CAP)
        self.assertIn("6 of 6", err)
        self.assertEqual(len(self.calls), nrql.MAX_QUERIES)

    def test_reset_starts_a_new_count(self):
        for _ in range(nrql.MAX_QUERIES):
            self.run_cli()
        self.assertEqual(nrql.main(["--state", str(self.state), "--reset"]), 0)
        self.assertEqual(self.run_cli()[0], 0)
        saved = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["queries"]), 1)

    def test_failed_query_still_counts(self):
        self.assertEqual(self.run_cli(exit_code=1)[0], 1)
        saved = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(saved["queries"], [{"query": QUERY, "exit": 1}])

    def test_rejected_queries_do_not_run_or_count(self):
        rejected = [
            "DROP TABLE Transaction SINCE 1 day ago",
            "SELECT count(*) FROM Transaction",
            "SELECT count(*) FROM Transaction SINCE 1 day ago FACET name TIMESERIES",
            "SELECT count(*) FROM Transaction SINCE 1 day ago LIMIT 21",
            "SELECT count(*) FROM Transaction SINCE 1 day ago LIMIT MAX",
            "SELECT 1 FROM A SINCE 1 day ago; SELECT 2 FROM B SINCE 1 day ago",
        ]
        for query in rejected:
            with self.subTest(query=query):
                self.assertEqual(self.run_cli(query)[0], nrql.EXIT_REJECTED)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.state.exists())

    def test_accepted_query_shapes(self):
        accepted = [
            "FROM Transaction SELECT count(*) SINCE 7 days ago LIMIT 20",
            "select count(*) from Transaction since 7 days ago facet name limit 5",
        ]
        for query in accepted:
            with self.subTest(query=query):
                self.assertIsNone(nrql.check_query(query))

    def test_unreadable_state_file_refuses_instead_of_resetting_the_count(self):
        self.state.parent.mkdir(parents=True)
        self.state.write_text("[]", encoding="utf-8")
        self.assertEqual(self.run_cli()[0], nrql.EXIT_CAP)
        self.assertEqual(self.calls, [])

    def test_no_cli_or_account_is_unavailable_and_not_counted(self):
        self.assertEqual(self.run_cli(which=lambda name: None)[0], nrql.EXIT_UNAVAILABLE)
        self.assertEqual(self.run_cli(env={})[0], nrql.EXIT_UNAVAILABLE)
        self.assertFalse(self.state.exists())

    def test_account_id_comes_from_the_default_profile_only(self):
        folder = pathlib.Path(self.tmp.name) / ".newrelic"
        folder.mkdir()
        (folder / "default-profile.json").write_text('"work"', encoding="utf-8")
        (folder / "credentials.json").write_text(
            json.dumps({
                "other": {"accountID": 1, "apiKey": "other-key"},
                "work": {"accountID": 77, "apiKey": "work-key"},
            }),
            encoding="utf-8",
        )
        code, out, err = self.run_cli(env={})
        self.assertEqual(code, 0)
        self.assertEqual(self.calls[0][3:5], ["--accountId", "77"])
        self.assertNotIn("key", out + err)

    def test_cli_gets_no_stdin_and_a_timeout(self):
        self.run_cli()
        self.assertIs(self.run_kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(self.run_kwargs["timeout"], nrql.QUERY_TIMEOUT_SECONDS)

    def test_save_state_retries_a_permission_error(self):
        real_replace = os.replace
        attempts = []

        def flaky(src, dst):
            attempts.append(src)
            if len(attempts) < 3:
                raise PermissionError("held")
            return real_replace(src, dst)

        with mock.patch.object(nrql.os, "replace", flaky), mock.patch.object(nrql.time, "sleep"):
            nrql.save_state(self.state, {"queries": []})
        self.assertEqual(len(attempts), 3)
        self.assertEqual(self.saved_queries(), [])
        self.assertEqual([p.name for p in self.state.parent.iterdir()], ["nrql.json"])

    def test_missing_query_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                nrql.main(["--state", str(self.state)])
        self.assertEqual(raised.exception.code, 2)

    def test_reset_with_a_query_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                nrql.main(["--state", str(self.state), "--reset", QUERY])
        self.assertEqual(raised.exception.code, 2)

    def test_reset_is_hidden_from_help(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            nrql.main(["--help"])
        self.assertNotIn("--reset", out.getvalue())

    def test_use_utf8_output_survives_non_ascii_cli_output(self):
        raw_out, raw_err = io.BytesIO(), io.BytesIO()
        fake_out = io.TextIOWrapper(raw_out, encoding="cp1252")
        fake_err = io.TextIOWrapper(raw_err, encoding="cp1252")
        with mock.patch.object(sys, "stdout", fake_out), mock.patch.object(sys, "stderr", fake_err):
            nrql.use_utf8_output()
            sys.stdout.write("caf\u00e9 \u2192 \u4e2d")
            sys.stderr.write("\u2192")
            sys.stdout.flush()
            sys.stderr.flush()
        self.assertEqual(raw_out.getvalue().decode("utf-8"), "caf\u00e9 \u2192 \u4e2d")
        self.assertEqual(raw_err.getvalue().decode("utf-8"), "\u2192")

    def test_run_oserror_removes_the_entry_and_is_unavailable(self):
        def broken(argv, **kwargs):
            raise OSError("cannot execute")

        code, _, err = self.run_cli(run=broken)
        self.assertEqual(code, nrql.EXIT_UNAVAILABLE)
        self.assertIn("query not run", err)
        self.assertEqual(self.saved_queries(), [])

    def test_timeout_stays_counted(self):
        def slow(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 120)

        code, _, err = self.run_cli(run=slow)
        self.assertEqual(code, 1)
        self.assertIn("timed out", err)
        self.assertEqual(self.saved_queries(), [{"query": QUERY, "exit": "timeout"}])

    def test_cli_with_a_script_suffix_is_unavailable(self):
        for found in ("C:/bin/newrelic.JS", "C:/bin/newrelic.cmd", "C:/bin/newrelic.bat"):
            with self.subTest(found=found):
                code, _, _ = self.run_cli(which=lambda name: found)
                self.assertEqual(code, nrql.EXIT_UNAVAILABLE)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.state.exists())

    def test_cli_with_an_exe_suffix_runs(self):
        self.assertEqual(self.run_cli(which=lambda name: "C:/bin/newrelic.EXE")[0], 0)

    def test_state_path_that_is_a_directory_is_refused(self):
        self.state.mkdir(parents=True)
        code, _, err = self.run_cli()
        self.assertEqual(code, nrql.EXIT_CAP)
        self.assertIn("state file unusable", err)
        self.assertEqual(self.calls, [])

    def test_reset_on_a_directory_state_path_is_refused(self):
        self.state.mkdir(parents=True)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(nrql.main(["--state", str(self.state), "--reset"]), nrql.EXIT_CAP)

    def test_fresh_lock_blocks_the_query(self):
        self.state.parent.mkdir(parents=True)
        self.lock_path().write_text("", encoding="utf-8")
        code, _, err = self.run_cli(lock_wait=0.1)
        self.assertEqual(code, nrql.EXIT_CAP)
        self.assertIn("busy", err)
        self.assertEqual(self.calls, [])
        self.assertTrue(self.lock_path().exists())

    def test_reset_clears_a_lock_left_by_a_dead_run(self):
        self.state.parent.mkdir(parents=True)
        self.lock_path().write_text("", encoding="utf-8")
        self.assertEqual(nrql.main(["--state", str(self.state), "--reset"]), 0)
        self.assertEqual(self.run_cli()[0], 0)
        self.assertFalse(self.lock_path().exists())

    def test_overlapping_calls_never_pass_the_cap(self):
        ran = []

        def slow_run(argv, **kwargs):
            ran.append(1)
            time.sleep(0.05)
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        def call():
            nrql.main(
                ["--state", str(self.state), QUERY],
                env={"NEW_RELIC_ACCOUNT_ID": "42"},
                home=pathlib.Path(self.tmp.name),
                which=lambda name: "newrelic-bin",
                run=slow_run,
                lock_wait=10,
            )

        threads = [threading.Thread(target=call) for _ in range(nrql.MAX_QUERIES + 4)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(len(ran), nrql.MAX_QUERIES)
        self.assertEqual([q["exit"] for q in self.saved_queries()], [0] * nrql.MAX_QUERIES)

    def test_failed_save_leaves_no_temp_file(self):
        self.state.mkdir(parents=True)
        with contextlib.redirect_stderr(io.StringIO()):
            nrql.main(["--state", str(self.state), "--reset"])
        self.assertEqual([p.name for p in self.state.parent.iterdir()], [self.state.name])

    def test_lock_is_not_held_while_the_cli_runs(self):
        seen = []

        def probe(argv, **kwargs):
            seen.append(self.lock_path().exists())
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        self.run_cli(run=probe)
        self.assertEqual(seen, [False])

    def test_failed_second_save_warns_and_keeps_the_exit_code(self):
        real_save = nrql.save_state
        saves = []

        def save(path, state):
            saves.append(1)
            if len(saves) > 1:
                raise OSError("disk full")
            real_save(path, state)

        with mock.patch.object(nrql, "save_state", save):
            code, out, err = self.run_cli(exit_code=3)
        self.assertEqual(code, 3)
        self.assertEqual(out, "rows\n")
        self.assertIn("warning", err)

    def test_string_literals_do_not_satisfy_or_trip_checks(self):
        rejected = [
            "SELECT count(*) FROM T WHERE a = 'SINCE 1 day ago'",
            "SELECT count(*) FROM T SINCE 1 day ago FACET b",
            "SELECT * FROM T SINCE 1 day ago",
            "SELECT * FROM T WHERE (a = 1) SINCE 1 day ago",
            "SELECT * FROM T SINCE 1 day ago WHERE a = 'LIMIT 5'",
            "SELECT count(*) FROM T SINCE 1 day ago LIMIT 0x5",
            "SELECT count(*) FROM T SINCE 1 day ago LIMIT \u0663",
            "SELECT count(*) FROM T SINCE 1 day ago LIMIT 5 LIMIT 99",
        ]
        accepted = [
            "SELECT count(*) FROM T SINCE 1 day ago WHERE a = 'x;y'",
            "SELECT count(*) FROM T SINCE 1 day ago WHERE a = 'it''s; x'",
            "SELECT count(*) FROM T SINCE 1 day ago WHERE a = 'it\\'s; x'",
            "SELECT count(*) FROM T SINCE 1 day ago WHERE a = 'TIMESERIES' FACET b LIMIT 5",
            "SELECT count(*) FROM T SINCE 1 day ago WHERE a = 'LIMIT 99'",
            "SELECT * FROM T SINCE 1 day ago LIMIT 5",
            "FROM T SELECT count(*) SINCE 1 day ago LIMIT 5)",
        ]
        for query in rejected:
            with self.subTest(query=query):
                self.assertIsNotNone(nrql.check_query(query))
        for query in accepted:
            with self.subTest(query=query):
                self.assertIsNone(nrql.check_query(query))


if __name__ == "__main__":
    unittest.main()
