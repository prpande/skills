import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from fakes import SELF, FakeGh, comment, poll, pull, review, thread, watch

T0 = "2026-09-10T09:00:00Z"


class GuardTests(unittest.TestCase):
    def test_own_pr_passes(self):
        gh = FakeGh()
        gh.prs[1411] = pull(1411)
        self.assertEqual(poll.main(["--assert-author", "1411", "--repo", "o/r"], gh=gh), 0)

    def test_reviewed_pr_is_refused_even_when_the_state_file_says_authored(self):
        gh = FakeGh()
        gh.prs[1420] = pull(1420, author_login="author-b")
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "watch.json").write_text(
                json.dumps(watch({1420: "authored"})), encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = poll.main(["--assert-author", "1420", "--repo", "o/r",
                                  "--state-dir", tmp], gh=gh)
        self.assertEqual(code, 3)
        self.assertIn("push refused", err.getvalue())
        self.assertEqual([c[1] for c in gh.calls], ["repos/o/r/pulls/1420", "user"])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.tmp.name)
        self.gh = FakeGh()
        (self.state / "watch.json").write_text(
            json.dumps(watch({1411: "authored", 1420: "reviewed"})), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = poll.main([*args, "--state-dir", str(self.state)], gh=self.gh)
        return code, out.getvalue()

    def test_tails_prints_the_pending_payload(self):
        self.gh.prs[1411] = pull(threads=[thread("T1", [comment("c1", "reviewer-a", T0)])])
        code, text = self.run_main("--tails", "1411")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["threads"][0]["thread_id"], "T1")

    def test_baseline_prints_and_writes_nothing(self):
        self.gh.prs[1411] = pull(threads=[thread("T1", [comment("c1", SELF, T0)])])
        before = sorted(p.name for p in self.state.iterdir())
        _, text = self.run_main("--baseline", "1411")
        self.assertEqual(json.loads(text)["settled_ids"], ["c1"])
        self.assertEqual(sorted(p.name for p in self.state.iterdir()), before)

    def test_findings_lists_only_threads_i_took_part_in(self):
        self.gh.prs[1420] = pull(1420, author_login="author-b", head="h2",
                                 threads=[thread("T9", [comment("m1", SELF, T0)], path="src/B.cs"),
                                          thread("T8", [comment("x1", "reviewer-c", T0)])],
                                 reviews=[review("r1", SELF, T0, oid="h1")])
        self.gh.compare["h1...h2"] = ["src/B.cs"]
        _, text = self.run_main("--findings", "1420")
        payload = json.loads(text)
        self.assertEqual([t["thread_id"] for t in payload["threads"]], ["T9"])
        self.assertEqual(payload["changed_files"], ["src/B.cs"])
        self.assertEqual((payload["old_head"], payload["new_head"]), ("h1", "h2"))

    def test_state_dir_is_required_outside_the_guard(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            poll.main(["--report"], gh=self.gh)


if __name__ == "__main__":
    unittest.main()
