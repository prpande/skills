import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from fakes import SELF, T0, T1, FakeGh, comment, poll, pull, review, thread, watch


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

    def test_a_gh_failure_is_exit_one_not_a_refusal(self):
        gh = FakeGh()
        gh.prs[1411] = pull(1411)
        gh.fail_user = True
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = poll.main(["--assert-author", "1411", "--repo", "o/r"], gh=gh)
        self.assertEqual((code, err.getvalue()), (1, "pr-watch: HTTP 401: Bad credentials\n"))


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

    def test_findings_excludes_a_thread_i_only_replied_on(self):
        self.gh.prs[1420] = pull(1420, author_login="author-b", head="h2",
                                 threads=[thread("T9", [comment("m1", SELF, T0)], path="src/B.cs"),
                                          thread("T7", [comment("x1", "reviewer-c", T0),
                                                        comment("m2", SELF, T1)])],
                                 reviews=[review("r1", SELF, T0, oid="h1")])
        self.gh.compare["h1...h2"] = ["src/B.cs"]
        _, text = self.run_main("--findings", "1420")
        payload = json.loads(text)
        self.assertEqual([t["thread_id"] for t in payload["threads"]], ["T9"])

    def test_findings_flags_a_compare_at_the_file_cap(self):
        self.gh.prs[1420] = pull(1420, author_login="author-b", head="h2",
                                 threads=[thread("T9", [comment("m1", SELF, T0)], path="src/B.cs")],
                                 reviews=[review("r1", SELF, T0, oid="h1")])
        for count, capped in ((poll.COMPARE_FILE_CAP - 1, False), (poll.COMPARE_FILE_CAP, True)):
            with self.subTest(count=count):
                self.gh.compare["h1...h2"] = [f"src/F{i}.cs" for i in range(count)]
                _, text = self.run_main("--findings", "1420")
                self.assertIs(json.loads(text)["compare_capped"], capped)

    def test_findings_compares_from_the_re_reviewed_head(self):
        watch_state = watch({1420: "reviewed"})
        watch_state["prs"]["1420"]["rereviewed_head"] = "h2"
        (self.state / "watch.json").write_text(json.dumps(watch_state), encoding="utf-8")
        self.gh.prs[1420] = pull(1420, author_login="author-b", head="h3",
                                 threads=[thread("T9", [comment("m1", SELF, T0)], path="src/B.cs")],
                                 reviews=[review("r1", SELF, T0, oid="h1")])
        self.gh.compare["h2...h3"] = ["src/B.cs"]
        _, text = self.run_main("--findings", "1420")
        payload = json.loads(text)
        self.assertEqual((payload["old_head"], payload["changed_files"]), ("h2", ["src/B.cs"]))

    def run_failing(self, *args):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, out = self.run_main(*args)
        return code, out, err.getvalue()

    def test_a_gh_error_is_one_stderr_line_and_exit_one(self):
        self.gh.fail = {1420}
        self.assertEqual(self.run_failing("--findings", "1420"),
                         (1, "", "pr-watch: fetch of 1420 failed\n"))

    def test_a_missing_state_file_is_one_stderr_line_and_exit_one(self):
        (self.state / "watch.json").unlink()
        code, out, err = self.run_failing("--report")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("pr-watch: ") and "watch.json" in err)
        self.assertEqual(len(err.splitlines()), 1)

    def test_a_corrupt_state_file_is_one_stderr_line_and_exit_one(self):
        (self.state / "watch.json").write_text("{not json", encoding="utf-8")
        code, out, err = self.run_failing("--checks", "1411")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("pr-watch: "))
        self.assertEqual(len(err.splitlines()), 1)

    def test_state_dir_is_required_outside_the_guard(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            poll.main(["--report"], gh=self.gh)


if __name__ == "__main__":
    unittest.main()
