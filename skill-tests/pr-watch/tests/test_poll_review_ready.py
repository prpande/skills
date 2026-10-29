import contextlib
import io
import json
import tempfile
import unittest

from fakes import (NOW, SELF, FakeGh, HomeCase, claim_leases, comment, pk, poll, pull, review,
                   rk, thread, watch, write_session)

OLD = "2026-09-10T09:00:00Z"
PUSHED = "2026-09-10T08:00:00Z"
BOT = "copilot-pull-request-reviewer"


def ready_pr(**kw):
    kw.setdefault("comments", [comment("b1", BOT, OLD, typename="Bot")])
    return pull(1411, updated=OLD, committed=PUSHED, **kw)


def handled_view(role="authored"):
    view = watch({1411: role})
    view["prs"][rk(1411)]["handled_top_level_ids"] = {"b1": "skipped"}
    return view


class ReviewBlockerTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGh()
        self.view = handled_view()
        self.entry = self.view["prs"][rk(1411)]
        self.gh.checks[pk(1411)] = [{"name": "build", "bucket": "pass"}]
        self.now = NOW

    def blockers(self, pr):
        return poll.review_blockers(self.gh, self.view, pr, self.entry, self.now)

    def test_quiet_green_pr_with_a_bot_review_is_ready(self):
        self.assertEqual(self.blockers(ready_pr()), [])

    def test_draft_and_closed_block(self):
        self.assertIn("draft", self.blockers(ready_pr(is_draft=True)))
        self.assertIn("not-open", self.blockers(ready_pr(state="MERGED")))

    def test_unresolved_thread_blocks_and_a_resolved_one_does_not(self):
        t = thread("T1", [comment("c1", BOT, OLD, typename="Bot")])
        self.assertIn("unresolved-threads", self.blockers(ready_pr(threads=[t])))
        t = thread("T1", [comment("c1", BOT, OLD, typename="Bot"), comment("c2", SELF, OLD)],
                   resolved=True)
        self.entry["settled_ids"] = ["c2"]
        self.assertEqual(self.blockers(ready_pr(threads=[t])), [])

    def test_unhandled_bot_comment_is_a_pending_fix(self):
        self.entry["handled_top_level_ids"] = {}
        self.assertIn("fix-pending", self.blockers(ready_pr()))

    def test_queued_work_blocks(self):
        self.entry["queued_head"] = "h9"
        self.assertIn("fix-queued", self.blockers(ready_pr()))
        self.entry["queued_head"] = None
        self.entry["ci_rerun_queued"] = [{"link": "x"}]
        self.assertIn("fix-queued", self.blockers(ready_pr()))
        self.entry["ci_rerun_queued"] = []
        self.view["push_queue"] = [rk(1411)]
        self.assertIn("fix-queued", self.blockers(ready_pr()))

    def test_no_bot_review_blocks(self):
        self.assertIn("no-bot-review", self.blockers(ready_pr(comments=[])))

    def test_a_status_bot_is_not_a_reviewer(self):
        pr = ready_pr(comments=[comment("a1", "github-actions[bot]", OLD, typename="Bot")])
        self.entry["handled_top_level_ids"] = {"a1": "skipped"}
        self.assertIn("no-bot-review", self.blockers(pr))

    def test_recent_bot_activity_blocks_until_thirty_minutes_pass(self):
        self.now = poll.parse_iso(OLD) + 29 * 60
        self.assertIn("bot-active", self.blockers(ready_pr()))
        self.now = poll.parse_iso(OLD) + 30 * 60
        self.assertNotIn("bot-active", self.blockers(ready_pr()))

    def test_a_bot_edit_counts_as_activity(self):
        edited = comment("b1", BOT, OLD, typename="Bot")
        edited["updatedAt"] = "2026-09-10T11:00:00Z"
        self.now = poll.parse_iso("2026-09-10T11:10:00Z")
        self.assertIn("bot-active", self.blockers(ready_pr(comments=[edited])))

    def test_recent_push_blocks(self):
        pr = ready_pr()
        pr["commits"]["nodes"][0]["commit"]["committedDate"] = "2026-09-10T09:50:00Z"
        self.now = poll.parse_iso("2026-09-10T10:00:00Z")
        self.assertIn("recent-push", self.blockers(pr))

    def test_missing_commit_time_blocks(self):
        pr = ready_pr()
        pr["commits"] = {"nodes": []}
        self.assertIn("recent-push", self.blockers(pr))

    def test_human_review_or_inline_comment_blocks(self):
        self.entry["handled_top_level_ids"] = {"b1": "skipped", "r1": "skipped"}
        pr = ready_pr(reviews=[review("r1", "alice", OLD, state="APPROVED")])
        self.assertIn("human-reviewed", self.blockers(pr))
        t = thread("T1", [comment("c1", "alice", OLD)], resolved=True)
        self.entry["settled_ids"] = ["c1"]
        self.assertIn("human-reviewed", self.blockers(ready_pr(threads=[t])))

    def test_the_users_own_review_and_a_pending_human_review_do_not_block(self):
        self.entry["handled_top_level_ids"] = {"b1": "skipped", "r1": "skipped"}
        own = ready_pr(reviews=[review("r1", SELF, OLD, state="COMMENTED")])
        self.assertEqual(self.blockers(own), [])
        draft_review = ready_pr(reviews=[review("r1", "alice", OLD, state="PENDING")])
        self.assertEqual(self.blockers(draft_review), [])

    def test_non_green_checks_block(self):
        self.gh.checks[pk(1411)] = [{"name": "build", "bucket": "pending"}]
        self.assertIn("checks-not-green", self.blockers(ready_pr()))
        self.gh.checks[pk(1411)] = [{"name": "build", "bucket": "skipping"}]
        self.assertEqual(self.blockers(ready_pr()), [])
        self.assertIn("checks-not-green", self.blockers(ready_pr(rollup="FAILURE")))

    def test_already_asked_blocks(self):
        self.entry["review_ask"] = {"drafted_at": "x", "outbox_ts": "1", "destination": "none"}
        self.assertIn("already-asked", self.blockers(ready_pr()))

    def test_reviewed_pr_is_never_ready(self):
        view = handled_view("reviewed")
        entry = view["prs"][rk(1411)]
        self.assertEqual(poll.review_blockers(self.gh, view, ready_pr(), entry, self.now),
                         ["not-authored"])


class ReviewReadyTickTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGh()
        self.view = handled_view()
        self.entry = self.view["prs"][rk(1411)]
        self.gh.prs[pk(1411)] = ready_pr()
        self.gh.rollup[pk(1411)] = "SUCCESS"
        self.gh.checks[pk(1411)] = [{"name": "build", "bucket": "pass"}]
        self.poller = {}
        self.now = poll.parse_iso(OLD) + 3600

    def tick(self, force=False):
        return [e for e in poll.tick_once(self.gh, self.view, self.poller, self.now, force=force)
                if e["kind"] == "review-ready"]

    def test_emits_once_per_head(self):
        self.assertEqual(self.tick(), [{"pr": rk(1411), "role": "authored",
                                        "kind": "review-ready", "head": "h2"}])
        self.now += 60
        self.assertEqual(self.tick(), [])

    def test_reconciliation_re_emits_an_unrecorded_ask(self):
        self.tick()
        self.assertEqual(len(self.tick(force=True)), 1)

    def test_recorded_ask_emits_nothing(self):
        self.entry["review_ask"] = {"drafted_at": "x", "outbox_ts": "1", "destination": "none"}
        self.assertEqual(self.tick(), [])

    def test_a_quiet_window_not_yet_elapsed_is_not_fetched(self):
        self.now = poll.parse_iso(OLD) + 600
        self.assertEqual(self.tick(), [])
        before = self.gh.thread_fetches()
        self.now += 60
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.gh.thread_fetches(), before)

    def test_red_rollup_is_not_fetched(self):
        self.gh.rollup[pk(1411)] = "FAILURE"
        self.assertEqual(self.tick(), [])
        before = self.gh.thread_fetches()
        self.now += 60
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.gh.thread_fetches(), before)

    def test_a_blocked_pr_is_checked_once_per_update(self):
        self.gh.prs[pk(1411)] = ready_pr(comments=[])
        self.assertEqual(self.tick(), [])
        before = self.gh.thread_fetches()
        self.now += 60
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.gh.thread_fetches(), before)

    def test_a_new_update_re_checks(self):
        self.gh.prs[pk(1411)] = ready_pr(comments=[])
        self.tick()
        self.gh.prs[pk(1411)] = ready_pr()
        self.gh.prs[pk(1411)]["updatedAt"] = "2026-09-10T09:30:00Z"
        self.now += 60
        self.assertEqual(len(self.tick()), 1)

    def test_a_closed_pr_drops_its_marker(self):
        self.tick()
        self.gh.prs[pk(1411)]["state"] = "MERGED"
        self.now += 60
        poll.tick_once(self.gh, self.view, self.poller, self.now)
        self.assertNotIn(rk(1411), self.poller["review"])

    def test_reviewed_pr_emits_nothing(self):
        self.view = handled_view("reviewed")
        self.assertEqual(self.tick(), [])


class ReviewReadyCliTests(HomeCase):
    def test_prints_ready_and_blockers(self):
        view = handled_view()
        gh = FakeGh()
        gh.prs[pk(1411)] = ready_pr()
        gh.checks[pk(1411)] = [{"name": "build", "bucket": "pass"}]
        with tempfile.TemporaryDirectory() as d:
            claim_leases(view)
            write_session(d, view)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = poll.main(["--review-ready", rk(1411), "--session-dir", d], gh=gh)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue()),
                         {"pr": rk(1411), "head": "h2", "ready": True, "blockers": []})
