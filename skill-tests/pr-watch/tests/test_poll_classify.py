import unittest

from fakes import ALLOW, SELF, author, poll


class ClassifyTests(unittest.TestCase):
    def test_allowlisted_user_account_is_a_bot(self):
        self.assertEqual(poll.classify(author("sonarqube-mbodevme"), SELF, ALLOW),
                         ("sonarqube-mbodevme", "bot"))

    def test_bot_typename_is_a_bot(self):
        self.assertEqual(
            poll.classify(author("copilot-pull-request-reviewer", "Bot"), SELF, ALLOW)[1], "bot")

    def test_bot_suffix_is_a_bot(self):
        self.assertEqual(poll.classify(author("github-actions[bot]"), SELF, ALLOW)[1], "bot")

    def test_acting_login_is_me(self):
        self.assertEqual(poll.classify(author(SELF), SELF, ALLOW), (SELF, "me"))

    def test_any_other_user_is_human(self):
        self.assertEqual(poll.classify(author("reviewer-a"), SELF, ALLOW), ("reviewer-a", "human"))

    def test_deleted_account_counts_as_a_bot(self):
        self.assertEqual(poll.classify(None, SELF, ALLOW), ("ghost", "bot"))


if __name__ == "__main__":
    unittest.main()
