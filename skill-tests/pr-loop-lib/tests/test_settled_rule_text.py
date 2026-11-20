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
    "opening words. When the code or data contradicts the fact an item's reason states, "
    "report it with a summary that starts \"Premise not shown: \" followed by the item's "
    "opening words."
)
CLAIMS_HEADER = (
    "Claims to check: each item below rests on a stated fact that no evidence was shown for, "
    "so it is not settled. Check the fact against the code and data. When they contradict it, "
    "or when an existing helper does the same job and the fact is the only reason it went "
    "unused, report it with a summary that starts \"Premise not shown: \" followed by the "
    "item's opening words, cited like any finding and ranked by what the miss costs."
)
HINT_CLAIMS = (
    " Items under \"Claims to check:\" are not settled: check each stated fact against the code "
    "and data, and when they contradict it, or an existing helper does the same job and the "
    "fact is the only reason it went unused, report it with a summary that starts "
    "\"Premise not shown: \" followed by the item's opening words."
)
HELPER_CLAUSE = (
    "an existing helper does the same job and the fact is the only reason it went unused"
)
SETTLED_ONLY = "Drift and declared but risky apply to items under \"Settled:\" only."
HINT_START = "`. Settled decisions: <path>."


def flat(text):
    return " ".join(text.split())


def hint(lines):
    return next(line for line in lines if line.strip().startswith(HINT_START))


class SettledRuleTextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.step = STEP.read_text(encoding="utf-8")
        cls.step_lines = cls.step.splitlines()
        prompt = PROMPT.read_text(encoding="utf-8")
        cls.template = re.search(r"## Prompt template\n(.*?)\n## ", prompt, re.S).group(1)

    def test_adversarial_prompt_teaches_claims_to_check(self):
        self.assertIn("Claims to check", self.template)
        self.assertIn("Premise not shown: ", self.template)

    def test_helper_clause_is_in_every_copy(self):
        claims = next(line for line in self.step_lines if line.startswith("Claims to check: each item"))
        for copy in (claims, hint(self.step_lines), self.template):
            self.assertIn(HELPER_CLAUSE, flat(copy))

    def test_prompt_never_lowers_severity_for_ruled_items(self):
        self.assertIn("never lowered because the item was ruled on", flat(self.template))

    def test_settled_file_headers_match_fixed_wording(self):
        self.assertIn(SETTLED_HEADER, self.step_lines)
        self.assertIn(CLAIMS_HEADER, self.step_lines)

    def test_settled_hint_carries_claims_rule(self):
        hints = [line for line in self.step_lines if line.strip().startswith(HINT_START)]
        self.assertEqual(len(hints), 1)
        self.assertTrue(hints[0].endswith(HINT_CLAIMS + "`"))

    def test_drift_and_risk_apply_to_settled_items_only(self):
        self.assertIn(SETTLED_ONLY, flat(self.template))

    def test_source_settles_choice_not_facts(self):
        self.assertIn(
            "source settles the choice, never the facts its reason states.",
            flat(self.step))

    def test_kept_on_purpose_line_has_evidence_tail(self):
        self.assertIn("- <statement> (<file>:<line>) Evidence: <evidence>", self.step)


if __name__ == "__main__":
    unittest.main()
