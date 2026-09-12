import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from fakes import SELF, T0, T1, T2, FakeGh, comment, poll, pull, thread, watch


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.tmp.name)
        self.gh = FakeGh()
        self.watch = watch({1411: "authored"})
        self.save_watch()

    def tearDown(self):
        self.tmp.cleanup()

    def save_watch(self):
        (self.state / "watch.json").write_text(json.dumps(self.watch), encoding="utf-8")

    def run_report(self, reseed=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = poll.report(self.gh, self.state, reseed=reseed)
        return code, out.getvalue()

    def seen(self):
        return json.loads((self.state / "watch-seen.json").read_text(encoding="utf-8"))

    def new_section(self, text):
        lines = text.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("NEW"))
        end = next(i for i, line in enumerate(lines) if line.startswith("STANDING"))
        return [line for line in lines[start + 1:end] if line.startswith("  PR")]

    def test_three_sections_and_no_mutation(self):
        self.gh.prs[1411] = pull(threads=[thread("T1", [comment("c1", "reviewer-a", T0)])])
        code, text = self.run_report()
        self.assertEqual(code, 0)
        for header in ("ATTENTION", "NEW", "STANDING"):
            self.assertIn(header, text)
        self.assertFalse(any("mutation" in " ".join(call) for call in self.gh.calls))

    def test_deleted_seen_id_reappears_as_exactly_that_item(self):
        self.gh.prs[1411] = pull(
            threads=[thread("T1", [comment("c1", "copilot-pull-request-reviewer", T0,
                                           typename="Bot"),
                                   comment("c2", "reviewer-a", T1)])],
            comments=[comment("i1", "sonarqube-mbodevme", T2)])
        self.run_report()
        seen = self.seen()
        seen["1411"].remove("c2")
        (self.state / "watch-seen.json").write_text(json.dumps(seen), encoding="utf-8")
        _, text = self.run_report()
        new = self.new_section(text)
        self.assertEqual(len(new), 1)
        self.assertIn("[human]", new[0])
        self.assertIn("reviewer-a", new[0])

    def test_deleted_bot_id_reappears_classified_as_bot(self):
        self.gh.prs[1411] = pull(comments=[comment("i1", "sonarqube-mbodevme", T2)])
        self.run_report()
        (self.state / "watch-seen.json").write_text(json.dumps({"1411": []}), encoding="utf-8")
        _, text = self.run_report()
        new = self.new_section(text)
        self.assertEqual(len(new), 1)
        self.assertIn("[bot]", new[0])

    def test_human_reply_on_a_resolved_thread_is_in_attention(self):
        self.watch["prs"]["1411"]["posted_reply_ids"] = ["c2"]
        self.save_watch()
        self.gh.prs[1411] = pull(threads=[thread(
            "T1", [comment("c1", "copilot-pull-request-reviewer", T0, typename="Bot"),
                   comment("c2", SELF, T1), comment("c3", "reviewer-a", T2)], resolved=True)])
        _, text = self.run_report()
        attention = text.split("NEW")[0]
        self.assertIn("[resolved]", attention)
        self.assertIn("reviewer-a (human)", attention)

    def test_quiet_report_is_one_line(self):
        self.watch["prs"]["1411"]["settled_ids"] = ["c1"]
        self.save_watch()
        self.gh.prs[1411] = pull(threads=[thread("T1", [comment("c1", SELF, T0)])])
        self.run_report()
        _, text = self.run_report()
        self.assertEqual(len(text.strip().splitlines()), 1)

    def test_reseed_accepts_everything(self):
        self.gh.prs[1411] = pull(threads=[thread("T1", [comment("c1", "reviewer-a", T0)])])
        code, text = self.run_report(reseed=True)
        self.assertEqual(code, 0)
        self.assertEqual(self.seen(), {"1411": ["c1"]})
        self.assertIn("reseeded", text)

    def test_fetch_error_leaves_the_watermark_untouched(self):
        self.gh.fail = {1411}
        code, text = self.run_report()
        self.assertEqual(code, 1)
        self.assertIn("ERROR", text)
        self.assertFalse((self.state / "watch-seen.json").exists())

    def test_a_failed_pr_does_not_hold_back_the_others(self):
        self.watch = watch({1411: "authored", 1413: "authored"})
        self.save_watch()
        self.gh.prs[1411] = pull(threads=[thread("T1", [comment("c1", "reviewer-a", T0)])])
        self.gh.prs[1413] = pull(1413, threads=[thread("T1", [comment("c9", "reviewer-a", T0)])])
        self.gh.fail = {1413}
        code, text = self.run_report()
        self.assertEqual(code, 1)
        self.assertEqual(self.seen(), {"1411": ["c1"]})


if __name__ == "__main__":
    unittest.main()
