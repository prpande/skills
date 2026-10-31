import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from fakes import ALLOW, SELF, T0, T1, T2, T3, comment, poll, pull, review, thread

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

    def test_tail_of_only_my_own_comments_is_not_pending(self):
        t = thread("T1", [comment("c1", "reviewer-a", T0), comment("c2", SELF, T1),
                          comment("c3", SELF, T2)])
        threads, _ = poll.pending(pull(threads=[t]), entry(posted_reply_ids=["c2"]), SELF, ALLOW)
        self.assertEqual(threads, [])

    def test_my_comment_after_someone_elses_keeps_the_thread_pending(self):
        t = thread("T1", [comment("c1", SELF, T0), comment("c2", "reviewer-a", T1),
                          comment("c3", SELF, T2)])
        threads, _ = poll.pending(pull(threads=[t]), entry(), SELF, ALLOW)
        self.assertEqual(tail_ids(threads), [["c1", "c2", "c3"]])

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

    def test_bot_review_on_the_current_head_stays_pending(self):
        pr = pull(head="h2", reviews=[review("r1", "copilot-pull-request-reviewer", T1,
                                             body="findings", oid="h2", typename="Bot")])
        self.assertEqual(poll.baseline(pr, SELF, ALLOW)["handled_top_level_ids"], {})

    def test_bot_review_on_an_older_head_is_baselined(self):
        pr = pull(head="h2", reviews=[review("r1", "copilot-pull-request-reviewer", T1,
                                             body="findings", oid="h1", typename="Bot")])
        self.assertEqual(poll.baseline(pr, SELF, ALLOW)["handled_top_level_ids"],
                         {"r1": "baseline"})

    def test_bot_issue_comment_is_baselined_on_any_head(self):
        pr = pull(head="h2", comments=[comment("b1", "sonarqube-mbodevme", T1)])
        self.assertEqual(poll.baseline(pr, SELF, ALLOW)["handled_top_level_ids"],
                         {"b1": "baseline"})

    def test_bot_review_on_the_current_head_predating_my_activity_is_baselined(self):
        pr = pull(head="h2",
                  reviews=[review("r1", "copilot-pull-request-reviewer", T0,
                                  body="findings", oid="h2", typename="Bot"),
                           review("r2", SELF, T1, body="")])
        self.assertEqual(poll.baseline(pr, SELF, ALLOW)["handled_top_level_ids"],
                         {"r1": "baseline"})


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


SLACK_TS = "1793292267.630379"
SLACK_REPLY = {"ts": SLACK_TS, "author": "U07ENJD06T0", "body": "please rename it"}


class SlackTests(unittest.TestCase):
    def payload(self, replies, **fields):
        return poll.tails_payload(pull(), entry(**fields), SELF, ALLOW, slack=replies,
                                  slack_human="U07ENJD06T0")

    def test_slack_replies_become_top_level_records(self):
        rec = self.payload([SLACK_REPLY])["top_level"][0]
        self.assertEqual(set(rec), RECORD_KEYS)
        self.assertEqual(rec["id"], f"slack:{SLACK_TS}")
        self.assertEqual(rec["surface"], "slack")
        self.assertEqual(rec["author"], "U07ENJD06T0")
        self.assertEqual(rec["author_type"], "User")
        self.assertEqual(rec["body"], "please rename it")
        self.assertEqual(rec["created_at"], "2026-10-29T16:44:27Z")

    def test_handled_slack_reply_skipped(self):
        payload = self.payload([SLACK_REPLY], handled_top_level_ids={f"slack:{SLACK_TS}": "fixed"})
        self.assertEqual(payload["top_level"], [])

    def test_slack_records_follow_github_ones(self):
        pr = pull(comments=[comment("i1", "reviewer-a", T0)])
        payload = poll.tails_payload(pr, entry(), SELF, ALLOW, slack=[SLACK_REPLY],
                                     slack_human="U07ENJD06T0")
        self.assertEqual([r["id"] for r in payload["top_level"]], ["i1", f"slack:{SLACK_TS}"])

    def test_author_type_is_user_for_the_human_and_bot_for_others(self):
        bot = {"ts": "1793292300.000100", "author": "UBOT0001", "body": "nit"}
        types = [r["author_type"] for r in self.payload([SLACK_REPLY, bot])["top_level"]]
        self.assertEqual(types, ["User", "Bot"])

    def test_no_slack_input_changes_nothing(self):
        self.assertEqual(self.payload(None)["top_level"], [])


class SlackFilterTests(unittest.TestCase):
    def keep(self, replies, since="1793292267.000000"):
        return [r["ts"] for r in poll.slack_replies_to_handle(
            replies, "U07ENJD06T0", ["UBOT0001"], since)]

    def reply(self, ts, author="U07ENJD06T0", body="ok"):
        return {"ts": ts, "author": author, "body": body}

    def test_other_authors_are_dropped(self):
        got = self.keep([self.reply("1793292268.1", "UOTHER01"), self.reply("1793292269.1"),
                         self.reply("1793292270.1", "UBOT0001")])
        self.assertEqual(got, ["1793292269.1", "1793292270.1"])

    def test_replies_older_than_since_are_dropped(self):
        got = self.keep([self.reply("1793292266.9"), self.reply("1793292267.0")])
        self.assertEqual(got, ["1793292267.0"])

    def test_own_posts_are_dropped(self):
        got = self.keep([self.reply("1793292268.1", body="Pushed abc1234.\n\nSent using Claude"),
                         self.reply("1793292269.1", body="Pushed.\nSent using <@U0APMMVNAU8|Claude>")])
        self.assertEqual(got, [])


class OwnPostTests(unittest.TestCase):
    def test_raw_footer(self):
        self.assertTrue(poll.is_own_slack_post("done\n\nSent using <@U0APMMVNAU8|Claude>"))

    def test_rendered_footer(self):
        self.assertTrue(poll.is_own_slack_post("done\n\nSent using Claude"))

    def test_slack_bold_footer_as_read_back_from_a_thread(self):
        self.assertTrue(poll.is_own_slack_post(
            "No longer watching.\n*Sent using* <@U0APMMVNAU8|Claude>"))

    def test_quoted_footer_followed_by_more_words_is_not_own(self):
        self.assertFalse(poll.is_own_slack_post(
            "your footer says Sent using Claude but I disagree with the rename"))

    def test_trailing_whitespace(self):
        self.assertTrue(poll.is_own_slack_post("done\nSent using Claude  \n\n"))

    def test_mention_mid_text_is_not_own(self):
        text = "I was Sent using Claude earlier" + " and more text" * 12
        self.assertFalse(poll.is_own_slack_post(text))

    def test_plain_reply_is_not_own(self):
        self.assertFalse(poll.is_own_slack_post("please rename it"))


class SlackCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)

    def run_cli(self, content):
        path = self.dir / "slack.json"
        path.write_text(content, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = poll.main(["--tails", "o/r#1", "--slack", str(path),
                                  "--slack-human", "U07ENJD06T0", "--slack-since", "1.0",
                                  "--session-dir", str(self.dir)], gh=lambda *a, **k: 1 / 0)
            except SystemExit as exc:
                code = exc.code
        return code, err.getvalue()

    def test_invalid_files_are_usage_errors_not_tracebacks(self):
        bad = ["not json", '{"ts": "1.2"}', '[{"ts": "1.2", "author": "U1"}]',
               '[{"ts": 5, "author": "U1", "body": "x"}]', '["x"]',
               '[{"ts": "soon", "author": "U1", "body": "x"}]']
        for content in bad:
            with self.subTest(content=content):
                code, err = self.run_cli(content)
                self.assertEqual(code, 2)
                self.assertIn("--slack", err)
                self.assertNotIn("Traceback", err)

    def test_slack_arguments_are_validated(self):
        base = ["--tails", "o/r#1", "--slack", "x.json", "--session-dir", str(self.dir)]
        for extra in ([], ["--slack-human", "U07ENJD06T0"], ["--slack-since", "1.0"],
                      ["--slack-human", "bad", "--slack-since", "1.0"],
                      ["--slack-human", "U07ENJD06T0", "--slack-since", "soon"],
                      ["--slack-human", "U07ENJD06T0", "--slack-since", "1.0",
                       "--slack-bots", "UBOT0001,x"]):
            with self.subTest(extra=extra):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                    poll.main(base + extra)
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("--slack", err.getvalue())

    def test_slack_needs_tails(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            poll.main(["--baseline", "o/r#1", "--slack", "x.json", "--session-dir", str(self.dir)])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("--slack needs --tails", err.getvalue())


if __name__ == "__main__":
    unittest.main()
