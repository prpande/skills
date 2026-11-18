import contextlib
import io
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "pr-tooling" / "pr-loop-lib" / "scripts"))

import copilot_review  # noqa: E402

BODIES = json.loads((REPO / "skill-tests" / "pr-loop-lib" / "fixtures" / "copilot-reviews.json")
                    .read_text(encoding="utf-8"))


def body(name):
    return BODIES[name]["body"]


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = copilot_review.main(argv)
    return code, out.getvalue(), err.getvalue()


def run_cli(text):
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "body.md"
        path.write_text(text, encoding="utf-8")
        return run_main([str(path)])


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
            self.assertNotIn("\u200b", f["path"])
            self.assertNotIn("\u200b", f["key"])
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
        self.assertFalse(any("Files reviewed" in f["text"] for f in findings))

    def test_keys_and_titles_of_chosen_items_are_exact(self):
        _, findings = copilot_review.parse(body("31-5221330327"))
        first = findings[0]
        self.assertEqual(first["title"], "This plan still instructs the implementation to use the deleted `reply-voice.md`.")
        self.assertEqual(
            first["key"],
            "copilot|docs/superpowers/plans/2026-09-11-pr-watch.md|"
            "This plan still instructs the implementation to use the deleted `reply-voice.md`.")
        by_line = {(f["path"], f["line"]): f for f in findings}
        corpus = by_line[("skills/team-tooling/human-reply/scripts/corpus.py", 136)]
        self.assertEqual(
            corpus["title"],
            "On the second hold-out pass, `setup/04-filter.md` supplies `--passed` and says only "
            "post-cutoff threads should fill missing slots.")
        layout = by_line[("docs/superpowers/specs/2026-09-16-human-reply-design.md", 82)]
        self.assertEqual(
            layout["title"],
            "The documented `scripts/` layout omits `corpus.py`, `ai_filter.py`, and `github_records.py`, "
            "even though setup invokes all three and they are part of this PR's runtime.")
        self.assertEqual(layout["key"], f"copilot|{layout['path']}|{layout['title']}")

    def test_body_with_both_sections_returns_suppressed_then_missed(self):
        combined = body("30-5219703484") + "\n" + body("46-5855681494")
        classification, findings = copilot_review.parse(combined)
        self.assertEqual(classification, "parse")
        self.assertEqual([f["kind"] for f in findings], ["suppressed"] + ["missed"] * 4)
        code, out, _ = run_cli(combined)
        self.assertEqual((code, len(json.loads(out)["findings"])), (0, 5))


class TitleNormalization(unittest.TestCase):
    def test_abbreviations_and_numbers_do_not_end_the_title(self):
        for text, title in [
            ("Use a guard, e.g. a lock, before writing. Then retry.", "Use a guard, e.g. a lock, before writing."),
            ("Prefer A vs. B in the loop. More.", "Prefer A vs. B in the loop."),
            ("Step 1. is wrong. More.", "Step 1. is wrong."),
        ]:
            with self.subTest(text=text):
                self.assertEqual(copilot_review._first_sentence(text), title)

    def test_dash_bullet_is_stripped_and_inline_fence_is_kept(self):
        text = body("30-5219703484").replace(
            "* Re-arming creates", "- Nested fences like ```js break the parser. Re-arming creates", 1)
        _, findings = copilot_review.parse(text)
        self.assertTrue(findings[0]["text"].startswith("Nested fences like ```js break"))
        self.assertEqual(findings[0]["title"], "Nested fences like ```js break the parser.")

    def test_angle_words_in_a_missed_title_are_kept(self):
        text = body("51-5934548755").replace(
            "Verify settled-item coverage", "Compare `git diff <base_sha>` output and verify settled-item coverage", 1)
        _, findings = copilot_review.parse(text)
        self.assertIn("`git diff <base_sha>`", findings[0]["title"])


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
        self.assertIn("not every finding", err)


class CliInputs(unittest.TestCase):
    def test_dash_reads_the_body_from_stdin(self):
        stdin = types.SimpleNamespace(buffer=io.BytesIO(body("51-5934548755").encode("utf-8")))
        with mock.patch.object(sys, "stdin", stdin):
            code, out, _ = run_main(["-"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["findings"]), 2)

    def test_wrong_argument_count_prints_usage_and_exits_64(self):
        for argv in ([], ["a.md", "b.md"]):
            with self.subTest(argv=argv):
                code, out, err = run_main(argv)
                self.assertEqual((code, out), (64, ""))
                self.assertEqual(err.strip(), copilot_review.USAGE)

    def test_missing_file_exits_64(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_main([str(pathlib.Path(tmp) / "absent.md")])
        self.assertEqual((code, out), (64, ""))
        self.assertIn("cannot read the body", err)

    def test_file_bytes_that_are_not_text_decode_with_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "body.md"
            path.write_bytes(b"\xff\x00bad")
            code, out, _ = run_main([str(path)])
        self.assertEqual((code, json.loads(out)["classification"]), (0, "skip"))

    def test_utf16_and_bom_bodies_parse_like_utf8(self):
        text = body("51-5934548755")
        expected = json.loads(run_cli(text)[1])
        for encoding in ("utf-16", "utf-8-sig"):
            with self.subTest(encoding=encoding):
                with tempfile.TemporaryDirectory() as tmp:
                    path = pathlib.Path(tmp) / "body.md"
                    path.write_bytes(text.encode(encoding))
                    code, out, _ = run_main([str(path)])
                self.assertEqual((code, json.loads(out)), (0, expected))

    def test_crlf_body_parses_like_lf_from_file_and_stdin(self):
        text = body("51-5934548755")
        expected = json.loads(run_cli(text)[1])
        crlf = text.replace("\n", "\r\n")
        self.assertEqual(json.loads(run_cli(crlf)[1]), expected)
        stdin = types.SimpleNamespace(buffer=io.BytesIO(crlf.encode("utf-8")))
        with mock.patch.object(sys, "stdin", stdin):
            code, out, _ = run_main(["-"])
        self.assertEqual((code, json.loads(out)), (0, expected))


class QuotedMarkupInsideFindings(unittest.TestCase):
    def test_label_line_in_a_fenced_quote_does_not_end_the_suppressed_section(self):
        text = body("31-5221330327")
        fence = text.index("```\n") + 4
        quoted = text[:fence] + "- **Note:** see reply-voice.md\n" + text[fence:]
        code, out, _ = run_cli(quoted)
        self.assertEqual((code, len(json.loads(out)["findings"])), (0, 19))

    def test_closing_details_in_a_fenced_quote_does_not_end_the_suppressed_section(self):
        text = body("31-5221330327")
        fence = text.index("```\n") + 4
        quoted = text[:fence] + "</details>\n" + text[fence:]
        code, out, _ = run_cli(quoted)
        self.assertEqual((code, len(json.loads(out)["findings"])), (0, 19))

    def test_closing_details_in_a_tilde_fenced_quote_does_not_end_the_suppressed_section(self):
        text = body("31-5221330327")
        opener = text.index("```\n")
        closer = text.index("```\n", opener + 4)
        tilde = (text[:opener] + "~~~\n</details>\n" + text[opener + 4:closer]
                 + "~~~\n" + text[closer + 4:])
        code, out, _ = run_cli(tilde)
        self.assertEqual((code, len(json.loads(out)["findings"])), (0, 19))

    def test_backtick_fence_is_not_closed_by_tildes(self):
        masked = copilot_review._mask("```\n~~~\n</details>\n~~~\n```\nafter\n")
        self.assertNotIn("details", masked)
        self.assertIn("after", masked)

    def test_details_tags_in_inline_code_do_not_split_missed_items(self):
        text = body("46-5855681494").replace(
            "These triggers omit", "The `</details>` and `<details>` tags are quoted. These triggers omit", 1)
        _, findings = copilot_review.parse(text)
        self.assertEqual(len(findings), 4)
        self.assertIn("`</details>`", findings[0]["text"])

    def test_item_heading_in_a_fenced_quote_is_not_an_item(self):
        text = body("30-5219703484").replace(
            "```\nthe monitor", "```\n**fake/file.md:9**\nthe monitor", 1)
        code, out, _ = run_cli(text)
        self.assertEqual((code, len(json.loads(out)["findings"])), (0, 1))


class PartialReads(unittest.TestCase):
    def test_one_unreadable_missed_item_exits_two(self):
        text = body("46-5855681494").replace("`skills/", "skills/", 1)
        code, out, err = run_cli(text)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("not every finding", err)

    def test_suppressed_range_heading_is_read(self):
        text = body("30-5219703484").replace("02-arm-monitor.md:18**", "02-arm-monitor.md:18-20**")
        _, findings = copilot_review.parse(text)
        self.assertEqual([f["line"] for f in findings], [18])

    def test_unreadable_suppressed_heading_exits_two(self):
        text = body("30-5219703484").replace("02-arm-monitor.md:18**", "02-arm-monitor.md**")
        code, out, _ = run_cli(text)
        self.assertEqual((code, out), (2, ""))

    def test_heading_count_that_differs_from_items_read_exits_two(self):
        text = body("31-5221330327").replace("Suppressed comments (19)", "Suppressed comments (20)")
        self.assertEqual(run_cli(text)[0], 2)


class SectionMarkupVariants(unittest.TestCase):
    def test_variants_the_parse_row_matches_are_read_or_exit_two(self):
        missed = body("51-5934548755")
        variants = [
            missed.replace("</strong></summary>", "</strong> </summary>", 1),
            missed.replace("<summary><strong>", "<summary>\n<strong>", 1),
            body("30-5219703484").replace("### Suppressed", "#### Suppressed"),
            body("30-5219703484").replace("### Suppressed", "  ### Suppressed"),
        ]
        for i, text in enumerate(variants):
            with self.subTest(variant=i):
                code, out, _ = run_cli(text)
                self.assertTrue(code == 2 or json.loads(out)["classification"] == "parse")

    def test_heading_with_unmatched_markup_exits_two(self):
        text = body("30-5219703484").replace("### Suppressed comments (1)", "Note: ### Suppressed comments (1)")
        self.assertEqual(run_cli(text)[0], 2)


if __name__ == "__main__":
    unittest.main()
