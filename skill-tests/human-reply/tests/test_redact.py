import contextlib
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
SKILL = REPO / "skills" / "team-tooling" / "human-reply"
sys.path.insert(0, str(SKILL / "scripts"))

import corpus  # noqa: E402
import redact  # noqa: E402

RULES = REPO / "skills" / "pr-tooling" / "pr-loop-lib" / "references" / "secret-scan-rules.md"
CHECK = SKILL / "references" / "redaction-check.md"


def scan_rule_patterns():
    """{rule number: regex} from the fenced block of secret-scan-rules.md."""
    block = re.search(r"^```\n(.*?)^```", RULES.read_text(encoding="utf-8"), re.S | re.M).group(1)
    rules, number = {}, None
    for line in block.splitlines():
        header = re.match(r"^# (\d+) ", line)
        if header:
            number = int(header.group(1))
        elif line.strip() and number is not None:
            rules[number] = line
    return rules


def check_cases():
    lines = corpus.fenced_block(CHECK.read_text(encoding="utf-8"), "redaction-check")
    return [tuple(line.split(" ==> ")) for line in lines]


class PatternCopyTests(unittest.TestCase):
    def test_patterns_match_rules_one_to_twelve_in_order(self):
        rules = scan_rule_patterns()
        self.assertEqual([rules[n] for n in range(1, 13)], [p for _, p in redact.SOURCE_PATTERNS])

    def test_the_env_rule_is_the_only_rule_not_copied(self):
        self.assertEqual(sorted(set(scan_rule_patterns()) - set(range(1, 13))), [13])


class RedactionCheckTests(unittest.TestCase):
    def test_every_case_redacts_to_its_expected_output(self):
        cases = check_cases()
        self.assertEqual(len(cases), 24)
        for given, expected in cases:
            with self.subTest(given=given):
                self.assertEqual(redact.redact(given.replace("{join}", ""))[0], expected)

    def test_every_skill_local_pattern_has_a_check_case(self):
        expected = " ".join(e for _, e in check_cases())
        for kind, _ in redact.SKILL_LOCAL_PATTERNS:
            with self.subTest(kind=kind):
                self.assertIn(f"<redacted:{kind}>", expected)

    def test_the_check_file_itself_matches_no_scan_rule(self):
        text = CHECK.read_text(encoding="utf-8")
        for number, pattern in scan_rule_patterns().items():
            with self.subTest(rule=number):
                self.assertIsNone(re.search(pattern, text, re.M))

    def test_the_check_file_itself_matches_no_skill_local_pattern(self):
        text = CHECK.read_text(encoding="utf-8")
        for index, (kind, pattern) in enumerate(redact.SKILL_LOCAL_PATTERNS):
            with self.subTest(index=index, kind=kind):
                self.assertIsNone(re.search(pattern, text))

    def test_skill_local_patterns_run_after_the_copied_rules_and_count(self):
        token = "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyz"
        self.assertEqual(redact.redact(f"Authorization: Bearer {token}"),
                         ("Authorization: Bearer <redacted:github-pat>", 1))
        self.assertEqual(redact.redact("x?p" + "wd=abc123&y=1 and Bearer " + "a" * 24),
                         ("x?pwd=<redacted:password>&y=1 and Bearer <redacted:token>", 2))

    def test_a_pem_body_is_removed_with_its_header(self):
        key = "-----BEGIN OPENSSH " + "PRIVATE KEY-----\nb3BlbnNzaC1rZXk\nAAAA\n-----END OPENSSH PRIVATE KEY-----"
        self.assertEqual(redact.redact(f"old key:\n{key}\nrotated")[0], "old key:\n<redacted:private-key>\nrotated")

    def test_clean_text_reports_zero_replacements(self):
        self.assertEqual(redact.redact("the retry policy stops at 3 attempts"), ("the retry policy stops at 3 attempts", 0))


class CliTests(unittest.TestCase):
    def test_appends_redacted_records_and_counts_touched_ones(self):
        records = [
            {"text": "use ghp_" + "0123456789abcdefghijklmnopqrstuvwxyz" + " now", "surface": "outer DM"},
            {"text": "nothing secret", "surface": "outer DM"},
        ]
        stdin = io.StringIO("".join(json.dumps(r) + "\n" for r in records))
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "slack.jsonl"
            out.write_text(json.dumps({"text": "earlier", "surface": "outer DM"}) + "\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                code = redact.main(["--out", str(out)], stdin=stdin)
            written = corpus.read_jsonl(out)
        self.assertEqual(code, 0)
        self.assertEqual([r["text"] for r in written], ["earlier", "use <redacted:github-pat> now", "nothing secret"])
        self.assertEqual(stderr.getvalue(), "redact: 1 of 2 records touched\n")


if __name__ == "__main__":
    unittest.main()
