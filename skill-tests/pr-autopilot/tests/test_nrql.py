import contextlib
import io
import json
import pathlib
import sys
import tempfile
import types
import unittest

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

    def run_cli(self, query=QUERY, *, env=None, which=lambda name: "newrelic-bin", exit_code=0):
        def fake_run(argv, **kwargs):
            self.calls.append(argv)
            return types.SimpleNamespace(returncode=exit_code, stdout="rows\n", stderr="")

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = nrql.main(
                ["--state", str(self.state), query],
                env={"NEW_RELIC_ACCOUNT_ID": "42"} if env is None else env,
                home=pathlib.Path(self.tmp.name),
                which=which,
                run=fake_run,
            )
        return code, out.getvalue(), err.getvalue()

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


if __name__ == "__main__":
    unittest.main()
