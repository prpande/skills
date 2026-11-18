import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "pr-tooling" / "pr-loop-lib" / "scripts"))

import copilot_review  # noqa: E402

BODIES = json.loads((REPO / "skill-tests" / "pr-loop-lib" / "fixtures" / "copilot-reviews.json")
                    .read_text(encoding="utf-8"))


def body(name):
    return BODIES[name]["body"]


def run_cli(text):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(text)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = copilot_review.main([fh.name])
    pathlib.Path(fh.name).unlink()
    return code, out.getvalue(), err.getvalue()


class PreviouslyMissedIssues(unittest.TestCase):
    def test_each_nested_details_is_one_finding(self):
        classification, findings = copilot_review.parse(body("51-5934548755"))
        self.assertEqual(classification, "parse")
        self.assertEqual([(f["path"], f["line"]) for f in findings], [
            ("skills/pr-tooling/pr-autopilot/steps/02-preflight-review.md", 216),
            ("skills/pr-tooling/pr-autopilot/steps/03.5-pre-open-review.md", 478),
        ])
        self.assertEqual(findings[0]["title"], "Verify settled-item coverage before exempting an answer")
        self.assertEqual({f["kind"] for f in findings}, {"missed"})
        self.assertEqual({f["severity"] for f in findings}, {"medium"})

    def test_zero_width_spaces_are_stripped_from_path_and_key(self):
        _, findings = copilot_review.parse(body("46-5855681494"))
        self.assertEqual(len(findings), 4)
        for f in findings:
            self.assertNotIn("​", f["path"])
            self.assertNotIn("​", f["key"])
            self.assertEqual(f["key"], f"copilot|{f['path']}|{f['title']}")

    def test_text_holds_the_finding_not_the_markup(self):
        _, findings = copilot_review.parse(body("51-5934548755"))
        self.assertTrue(findings[1]["text"].startswith("Dispatching every extra batch"))
        self.assertNotIn("<", findings[1]["text"])

    def test_singular_heading_and_low_severity(self):
        _, findings = copilot_review.parse(body("43-5748880132"))
        self.assertEqual([(f["path"], f["line"], f["severity"]) for f in findings],
                         [("skills/pr-tooling/pr-watch/steps/01-discover.md", 41, "low")])

    def test_open_issues_beside_missed_issues_are_not_findings(self):
        _, findings = copilot_review.parse(body("45-5837534321"))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["title"], "Hold check bypassed when saved re-review head matches current head")


class SuppressedComments(unittest.TestCase):
    def test_single_item(self):
        classification, findings = copilot_review.parse(body("30-5219703484"))
        self.assertEqual(classification, "parse")
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual((f["kind"], f["severity"], f["path"], f["line"]),
                         ("suppressed", None, "skills/pr-tooling/pr-watch/steps/02-arm-monitor.md", 18))
        self.assertTrue(f["text"].startswith("Re-arming creates a new `Monitor` task"))
        self.assertNotIn("```", f["text"])
        self.assertEqual(f["key"], f"copilot|{f['path']}|{f['title']}")
        self.assertTrue(f["title"].endswith("."))

    def test_every_item_of_a_long_section(self):
        _, findings = copilot_review.parse(body("31-5221330327"))
        self.assertEqual(len(findings), 19)
        self.assertEqual(findings[-1]["path"], "skills/team-tooling/human-reply/setup/07-calibrate.md")
        self.assertFalse(any(f["text"].startswith("**Files reviewed") for f in findings))


class SkipBodies(unittest.TestCase):
    def test_verdict_only_bodies_skip(self):
        for name in ("51-5934624838", "51-5934450955", "32-5224984644"):
            with self.subTest(name=name):
                self.assertEqual(copilot_review.parse(body(name)), ("skip", []))


class Cli(unittest.TestCase):
    def test_prints_classification_and_findings(self):
        code, out, _ = run_cli(body("51-5934548755"))
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["classification"], "parse")
        self.assertEqual(len(result["findings"]), 2)

    def test_skip_body_exits_zero(self):
        code, out, _ = run_cli(body("51-5934624838"))
        self.assertEqual((code, json.loads(out)), (0, {"classification": "skip", "findings": []}))

    def test_unreadable_section_exits_two(self):
        broken = body("51-5934548755").replace("`skills/", "skills/")
        code, out, err = run_cli(broken)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("no finding", err)


if __name__ == "__main__":
    unittest.main()
