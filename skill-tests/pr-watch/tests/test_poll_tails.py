import unittest

from fakes import ALLOW, SELF, comment, poll, pull, review, thread

T0 = "2026-09-10T09:00:00Z"
T1 = "2026-09-10T10:00:00Z"
T2 = "2026-09-10T11:00:00Z"
T3 = "2026-09-10T12:00:00Z"
RECORD_KEYS = {"id", "surface", "author", "author_type", "created_at", "updated_at",
               "path", "line", "body", "thread_id", "is_resolved"}


def entry(**fields):
    base = {"posted_reply_ids": [], "settled_ids": [], "handled_top_level_ids": {}}
    base.update(fields)
    return base


def tail_ids(threads):
    return [[c["id"] for c in tail] for _, tail in threads]


class PendingTests(unittest.TestCase):
    def test_tail_starts_after_the_last_posted_reply(self):
        t = thread("T1", [comment("c1", "reviewer-a", T0), comment("c2", SELF, T1),
                          comment("c3", "reviewer-a", T2)])
        threads, _ = poll.pending(pull(threads=[t]), entry(posted_reply_ids=["c2"]), SELF, ALLOW)
        self.assertEqual(tail_ids(threads), [["c3"]])

    def test_hand_typed_reply_is_pending_until_its_id_is_recorded(self):
        t = thread("T1", [comment("c1", "copilot-pull-request-reviewer", T0, typename="Bot"),
                          comment("c2", SELF, T1)])
        threads, _ = poll.pending(pull(threads=[t]), entry(), SELF, ALLOW)
        self.assertEqual(tail_ids(threads), [["c1", "c2"]])
        threads, _ = poll.pending(pull(threads=[t]), entry(posted_reply_ids=["c2"]), SELF, ALLOW)
        self.assertEqual(threads, [])

    def test_settled_id_closes_a_tail(self):
        t = thread("T1", [comment("c1", "sonarqube-mbodevme", T0)])
        threads, _ = poll.pending(pull(threads=[t]), entry(settled_ids=["c1"]), SELF, ALLOW)
        self.assertEqual(threads, [])

    def test_resolved_thread_is_read_like_an_open_one(self):
        t = thread("T1", [comment("c1", "reviewer-a", T0), comment("c2", SELF, T1),
                          comment("c3", "reviewer-a", T2)], resolved=True)
        threads, _ = poll.pending(pull(threads=[t]), entry(posted_reply_ids=["c2"]), SELF, ALLOW)
        self.assertEqual(tail_ids(threads), [["c3"]])

    def test_top_level_item_by_me_is_never_pending(self):
        _, top = poll.pending(pull(comments=[comment("i1", SELF, T0, body="ptal")]),
                              entry(), SELF, ALLOW)
        self.assertEqual(top, [])

    def test_review_without_a_body_is_not_an_item(self):
        _, top = poll.pending(pull(reviews=[review("r1", "reviewer-a", T0, body="")]),
                              entry(), SELF, ALLOW)
        self.assertEqual(top, [])

    def test_handled_top_level_item_is_not_pending(self):
        pr = pull(comments=[comment("i1", "reviewer-a", T0)],
                  reviews=[review("r1", "reviewer-a", T1, state="CHANGES_REQUESTED",
                                  body="fix it")])
        _, top = poll.pending(pr, entry(handled_top_level_ids={"i1": "fixed"}), SELF, ALLOW)
        self.assertEqual([(s, i["id"]) for s, i in top], [("review", "r1")])


class BaselineTests(unittest.TestCase):
    def test_thread_whose_last_comment_is_mine_is_settled(self):
        t = thread("T1", [comment("c1", "reviewer-a", T0), comment("c2", SELF, T1)])
        self.assertEqual(poll.baseline(pull(threads=[t]), SELF, ALLOW)["settled_ids"], ["c2"])

    def test_resolved_thread_ending_in_a_bot_is_settled(self):
        t = thread("T1", [comment("c1", "copilot-pull-request-reviewer", T0, typename="Bot")],
                   resolved=True)
        self.assertEqual(poll.baseline(pull(threads=[t]), SELF, ALLOW)["settled_ids"], ["c1"])

    def test_resolved_thread_ending_in_a_human_stays_pending(self):
        t = thread("T1", [comment("c1", "reviewer-a", T0), comment("c2", SELF, T1),
                          comment("c3", "reviewer-a", T2)], resolved=True)
        self.assertEqual(poll.baseline(pull(threads=[t]), SELF, ALLOW)["settled_ids"], [])

    def test_open_thread_ending_in_a_bot_stays_pending(self):
        t = thread("T1", [comment("c1", "copilot-pull-request-reviewer", T0, typename="Bot")])
        self.assertEqual(poll.baseline(pull(threads=[t]), SELF, ALLOW)["settled_ids"], [])

    def test_top_level_items_older_than_my_newest_activity_are_baselined(self):
        pr = pull(comments=[comment("h1", "reviewer-a", T0), comment("h2", "reviewer-a", T2),
                            comment("b1", "sonarqube-mbodevme", T3)],
                  reviews=[review("r1", SELF, T1, body="")])
        self.assertEqual(poll.baseline(pr, SELF, ALLOW)["handled_top_level_ids"],
                         {"h1": "baseline", "b1": "baseline"})

    def test_without_activity_of_mine_only_bots_are_baselined(self):
        pr = pull(comments=[comment("h1", "reviewer-a", T0),
                            comment("b1", "sonarqube-mbodevme", T1)])
        self.assertEqual(poll.baseline(pr, SELF, ALLOW)["handled_top_level_ids"],
                         {"b1": "baseline"})

    def test_item_at_the_same_second_as_my_activity_stays_pending(self):
        pr = pull(comments=[comment("i1", "reviewer-a", T1)],
                  reviews=[review("r1", SELF, T1, body="")])
        self.assertEqual(poll.baseline(pr, SELF, ALLOW)["handled_top_level_ids"], {})


class PayloadTests(unittest.TestCase):
    def test_records_carry_exactly_the_comment_record_fields(self):
        t = thread("T1", [comment("c1", "reviewer-a", T0)])
        pr = pull(threads=[t], comments=[comment("i1", "reviewer-a", T1)])
        payload = poll.tails_payload(pr, entry(), SELF, ALLOW)
        self.assertEqual(set(payload["threads"][0]["tail"][0]), RECORD_KEYS)
        self.assertEqual(set(payload["top_level"][0]), RECORD_KEYS)
        self.assertEqual(payload["threads"][0]["tail"][0]["surface"], "inline")
        self.assertEqual(payload["top_level"][0]["surface"], "issue")

    def test_allowlisted_author_is_reported_with_bot_type(self):
        t = thread("T1", [comment("c1", "mindbody-ado-pipelines", T0)])
        payload = poll.tails_payload(pull(threads=[t]), entry(), SELF, ALLOW)
        self.assertEqual(payload["threads"][0]["tail"][0]["author_type"], "Bot")

    def test_human_answering_a_watch_reply_is_flagged(self):
        t = thread("T1", [comment("c1", "reviewer-a", T0), comment("c2", SELF, T1),
                          comment("c3", "reviewer-a", T2)])
        payload = poll.tails_payload(pull(threads=[t]), entry(posted_reply_ids=["c2"]),
                                     SELF, ALLOW)
        self.assertTrue(payload["threads"][0]["follows_watch_reply"])
        self.assertEqual(payload["threads"][0]["tail_kinds"], ["human"])

    def test_tail_after_a_settled_id_does_not_follow_a_watch_reply(self):
        t = thread("T1", [comment("c1", SELF, T0), comment("c2", "reviewer-a", T1)])
        payload = poll.tails_payload(pull(threads=[t]), entry(settled_ids=["c1"]), SELF, ALLOW)
        self.assertFalse(payload["threads"][0]["follows_watch_reply"])


if __name__ == "__main__":
    unittest.main()
