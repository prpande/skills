import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
PROMPT = REPO / "skills" / "pr-tooling" / "pr-loop-lib" / "references" / "adversarial-review-prompt.md"
STEP = REPO / "skills" / "pr-tooling" / "pr-autopilot" / "steps" / "03.5-pre-open-review.md"

SETTLED_HEADER = (
    "Settled: do not argue for a different choice. When the code no longer matches an item, "
    "report that as an ordinary finding. When the code as stated can crash a client, hide an "
    "outage or failure, drop the caller's own data, or let a caller past an access check, "
    "report it with a summary that starts \"Declared but risky: \" followed by the item's "
    "opening words."
)
CLAIMS_HEADER = (
    "Claims to check: each item below rests on a stated fact that no evidence was shown for, "
    "so it is not settled. Check the fact against the code and data. When they contradict it, "
    "or when an existing helper does the same job and the fact is the only reason it went "
    "unused, report it with a summary that starts \"Premise not shown: \" followed by the "
    "item's opening words, cited like any finding and ranked by what the miss costs."
)
HINT_START = "`. Settled decisions: <path>."


def read(path):
    return path.read_text(encoding="utf-8")


def prompt_template():
    return re.search(r"## Prompt template\n(.*?)\n## ", read(PROMPT), re.S).group(1)


class SettledRuleTextTest(unittest.TestCase):
    def test_adversarial_prompt_teaches_claims_to_check(self):
        template = prompt_template()
        self.assertIn("Claims to check", template)
        self.assertIn("Premise not shown: ", template)

    def test_settled_file_headers_match_fixed_wording(self):
        lines = read(STEP).splitlines()
        self.assertIn(SETTLED_HEADER, lines)
        self.assertIn(CLAIMS_HEADER, lines)

    def test_settled_hint_carries_claims_rule(self):
        hints = [line for line in read(STEP).splitlines() if line.strip().startswith(HINT_START)]
        self.assertEqual(len(hints), 1)
        self.assertIn("Claims to check", hints[0])
        self.assertIn("Premise not shown: ", hints[0])

    def test_source_settles_choice_not_facts(self):
        self.assertIn(
            "A source settles the choice, never the facts its reason states.", read(STEP))

    def test_kept_on_purpose_line_has_evidence_tail(self):
        self.assertIn("- <statement> (<file>:<line>) Evidence: <evidence>", read(STEP))


if __name__ == "__main__":
    unittest.main()
