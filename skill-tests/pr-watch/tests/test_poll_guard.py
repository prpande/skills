import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from fakes import (SELF, T0, T1, FakeGh, HomeCase, comment, moved, pk, poll, pull, review, rk, thread,
                   watch, write_session)


class GuardTests(unittest.TestCase):
    def test_own_pr_passes(self):
        gh = FakeGh()
        gh.prs[pk(1411)] = pull(1411)
        self.assertEqual(poll.main(["--assert-author", "1411", "--repo", "o/r"], gh=gh), 0)

    def test_reviewed_pr_is_refused_even_when_the_state_file_says_authored(self):
        gh = FakeGh()
        gh.prs[pk(1420)] = pull(1420, author_login="author-b")
        with tempfile.TemporaryDirectory() as tmp:
            write_session(tmp, watch({1420: "authored"}))
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = poll.main(["--assert-author", "1420", "--repo", "o/r",
                                  "--session-dir", tmp], gh=gh)
        self.assertEqual(code, 3)
        self.assertIn("push refused", err.getvalue())
        self.assertEqual([c[1] for c in gh.calls], ["repos/o/r/pulls/1420", "user"])

    def test_a_gh_failure_is_exit_one_not_a_refusal(self):
        gh = FakeGh()
        gh.prs[pk(1411)] = pull(1411)
        gh.fail_user = True
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = poll.main(["--assert-author", "1411", "--repo", "o/r"], gh=gh)
        self.assertEqual((code, err.getvalue()), (1, "pr-watch: HTTP 401: Bad credentials\n"))


class CliTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.tmp.name)
        self.gh = FakeGh()
        write_session(self.state, watch({1411: "authored", 1420: "reviewed"}))

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = poll.main([*args, "--session-dir", str(self.state)], gh=self.gh)
        return code, out.getvalue()

    def test_tails_prints_the_pending_payload(self):
        self.gh.prs[pk(1411)] = pull(threads=[thread("T1", [comment("c1", "reviewer-a", T0)])])
        code, text = self.run_main("--tails", "o/r#1411")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["threads"][0]["thread_id"], "T1")

    def test_tails_for_a_pr_not_yet_watched_reads_its_stored_progress(self):
        self.gh.prs[pk(1500)] = pull(1500, threads=[thread("T1", [comment("c1", "reviewer-a", T0)])])
        path = poll.progress_path("o", "r", 1500)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"settled_ids": ["c1"]}), encoding="utf-8")
        _, text = self.run_main("--tails", "o/r#1500")
        self.assertEqual(json.loads(text)["threads"], [])

    def test_baseline_prints_and_writes_nothing(self):
        self.gh.prs[pk(1411)] = pull(threads=[thread("T1", [comment("c1", SELF, T0)])])
        before = sorted(p.name for p in self.state.iterdir())
        _, text = self.run_main("--baseline", "o/r#1411")
        self.assertEqual(json.loads(text)["settled_ids"], ["c1"])
        self.assertEqual(sorted(p.name for p in self.state.iterdir()), before)

    def test_findings_lists_only_threads_i_took_part_in(self):
        self.gh.prs[pk(1420)] = pull(1420, author_login="author-b", head="h2",
                                 threads=[thread("T9", [comment("m1", SELF, T0)], path="src/B.cs"),
                                          thread("T8", [comment("x1", "reviewer-c", T0)])],
                                 reviews=[review("r1", SELF, T0, oid="h1")])
        moved(self.gh, "h1", "h2", ["src/B.cs"])
        _, text = self.run_main("--findings", "o/r#1420")
        payload = json.loads(text)
        self.assertEqual([t["thread_id"] for t in payload["threads"]], ["T9"])
        self.assertEqual(payload["changed_files"], ["src/B.cs"])
        self.assertEqual((payload["old_head"], payload["new_head"]), ("h1", "h2"))

    def test_findings_excludes_a_thread_i_only_replied_on(self):
        self.gh.prs[pk(1420)] = pull(1420, author_login="author-b", head="h2",
                                 threads=[thread("T9", [comment("m1", SELF, T0)], path="src/B.cs"),
                                          thread("T7", [comment("x1", "reviewer-c", T0),
                                                        comment("m2", SELF, T1)])],
                                 reviews=[review("r1", SELF, T0, oid="h1")])
        moved(self.gh, "h1", "h2", ["src/B.cs"])
        _, text = self.run_main("--findings", "o/r#1420")
        payload = json.loads(text)
        self.assertEqual([t["thread_id"] for t in payload["threads"]], ["T9"])

    def test_findings_flags_a_compare_at_the_file_cap(self):
        self.gh.prs[pk(1420)] = pull(1420, author_login="author-b", head="h2",
                                 threads=[thread("T9", [comment("m1", SELF, T0)], path="src/B.cs")],
                                 reviews=[review("r1", SELF, T0, oid="h1")])
        for count, capped in ((poll.COMPARE_FILE_CAP - 1, False), (poll.COMPARE_FILE_CAP, True)):
            with self.subTest(count=count):
                moved(self.gh, "h1", "h2", [f"src/F{i}.cs" for i in range(count)])
                _, text = self.run_main("--findings", "o/r#1420")
                self.assertIs(json.loads(text)["compare_capped"], capped)

    def test_findings_compares_from_the_re_reviewed_head(self):
        watch_state = watch({1420: "reviewed"})
        watch_state["prs"][rk(1420)]["rereviewed_head"] = "h2"
        write_session(self.state, watch_state)
        self.gh.prs[pk(1420)] = pull(1420, author_login="author-b", head="h3",
                                 threads=[thread("T9", [comment("m1", SELF, T0)], path="src/B.cs")],
                                 reviews=[review("r1", SELF, T0, oid="h1")])
        moved(self.gh, "h2", "h3", ["src/B.cs"])
        _, text = self.run_main("--findings", "o/r#1420")
        payload = json.loads(text)
        self.assertEqual((payload["old_head"], payload["changed_files"]), ("h2", ["src/B.cs"]))

    def findings(self, reviews, head="h2"):
        self.gh.prs[pk(1420)] = pull(1420, author_login="author-b", head=head,
                                 threads=[thread("T9", [comment("m1", SELF, T0)], path="src/B.cs")],
                                 reviews=reviews)
        _, text = self.run_main("--findings", "o/r#1420")
        return json.loads(text)

    def test_a_merge_from_main_leaves_the_prs_own_patch_unchanged(self):
        self.gh.compare["main...h1"] = {"src/B.cs": "@@ -2,2 +2,2 @@ class B\n ctx\n-a\n+b"}
        self.gh.compare["main...h2"] = {"src/B.cs": "@@ -40,2 +40,2 @@ class B2\n moved ctx\n-a\n+b"}
        payload = self.findings([review("r1", SELF, T0, oid="h1")])
        self.assertEqual((payload["changed_files"], payload["compare_capped"]), ([], False))

    def test_a_conflict_resolved_in_a_pr_line_changes_that_file(self):
        self.gh.compare["main...h1"] = {"src/B.cs": "@@ -2 +2 @@\n-a\n+b", "src/C.cs": "@@ -1 +1 @@\n-c\n+d"}
        self.gh.compare["main...h2"] = {"src/B.cs": "@@ -2 +2 @@\n-main\n+merged", "src/C.cs": "@@ -1 +1 @@\n-c\n+d"}
        self.assertEqual(self.findings([review("r1", SELF, T0, oid="h1")])["changed_files"], ["src/B.cs"])

    def test_a_file_without_a_patch_counts_as_changed(self):
        self.gh.compare["main...h1"] = {"img/logo.png": None, "src/B.cs": "@@ -2 +2 @@\n-a\n+b"}
        self.gh.compare["main...h2"] = {"img/logo.png": None, "src/B.cs": "@@ -2 +2 @@\n-a\n+b"}
        self.assertEqual(self.findings([review("r1", SELF, T0, oid="h1")])["changed_files"], ["img/logo.png"])

    def test_a_capped_file_list_on_the_old_side_flags_the_compare(self):
        self.gh.compare["main...h1"] = [f"src/F{i}.cs" for i in range(poll.COMPARE_FILE_CAP)]
        self.assertIs(self.findings([review("r1", SELF, T0, oid="h1")])["compare_capped"], True)

    def test_an_approval_at_an_older_commit_holds_the_re_review(self):
        approved = review("r1", SELF, T0, state="APPROVED", oid="h1")
        cases = (
            ([approved], {"approved": "h1"}),
            ([approved, review("r2", SELF, T1, oid="h2")], {"approved": "h1"}),
            ([approved, review("r2", SELF, T1, state="CHANGES_REQUESTED", oid="h2")], None),
            ([review("r1", SELF, T0, state="CHANGES_REQUESTED", oid="h1")], None),
            ([review("r1", "reviewer-c", T0, state="APPROVED", oid="h1")], None),
        )
        for reviews, hold in cases:
            with self.subTest(states=[r["state"] for r in reviews]):
                self.assertEqual(self.findings(reviews)["approval_hold"], hold)

    def test_an_approval_at_the_head_is_no_hold(self):
        self.assertIsNone(self.findings([review("r1", SELF, T0, state="APPROVED", oid="h2")])["approval_hold"])

    def test_a_dismissed_review_holds_unless_the_timeline_says_it_requested_changes(self):
        dismissed = [review("r1", SELF, T0, state="DISMISSED", oid="h1")]
        for was, hold in (("approved", {"approved": "h1"}), ("changes_requested", None)):
            with self.subTest(was=was):
                self.gh.timeline[1420] = [
                    {"event": "reviewed", "id": 77, "login": SELF, "state": "dismissed"},
                    {"event": "review_dismissed", "dismissed": {"review_id": 77, "state": was}}]
                self.assertEqual(self.findings(dismissed)["approval_hold"], hold)
        self.gh.fail_timeline.add(1420)
        self.assertEqual(self.findings(dismissed)["approval_hold"], {"approved": "h1"})

    def run_failing(self, *args):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, out = self.run_main(*args)
        return code, out, err.getvalue()

    def test_a_gh_error_is_one_stderr_line_and_exit_one(self):
        self.gh.fail = {pk(1420)}
        self.assertEqual(self.run_failing("--findings", "o/r#1420"),
                         (1, "", "pr-watch: fetch of 1420 failed\n"))

    def test_a_missing_state_file_is_one_stderr_line_and_exit_one(self):
        (self.state / "watch.json").unlink()
        code, out, err = self.run_failing("--report")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("pr-watch: ") and "watch.json" in err)
        self.assertEqual(len(err.splitlines()), 1)

    def test_a_corrupt_state_file_is_one_stderr_line_and_exit_one(self):
        (self.state / "watch.json").write_text("{not json", encoding="utf-8")
        code, out, err = self.run_failing("--checks", "o/r#1411")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("pr-watch: "))
        self.assertEqual(len(err.splitlines()), 1)

    def test_session_dir_is_required_outside_the_guard(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            poll.main(["--report"], gh=self.gh)


if __name__ == "__main__":
    unittest.main()
