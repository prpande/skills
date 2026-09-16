import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
SKILL = REPO / "skills" / "team-tooling" / "human-reply"
sys.path.insert(0, str(SKILL / "scripts"))

import ai_filter  # noqa: E402
import corpus  # noqa: E402

MODULES = {name: SKILL / "channels" / f"{name}.md" for name in ("slack", "github", "notion")}
REFERENCE = SKILL / "references" / "ai-filter.md"

# The 2026 messages as sent and their 2025-voice rewrites, from the
# before-and-after section of the slack-reply shapes file.
SLACK_DESIGN_SHARE_SENT = (
    "Hi <@team> We're modernizing the new Appointment Details screen on BizApp to read directly from the "
    "federated GraphQL graph instead of the legacy SOAP/REST path it uses today \u2014 one contract, data coming "
    "from the domains that own it, and no BFF in the middle.\n\n"
    "On the Clients side that's a small set of additive changes: exposing automatedContactMethod on the client "
    "and adding two new resolvers \u2014 a progress-note status and forms count for an appointment. "
    "Additive-only \u2014 no SQL.\n\n"
    "We are planning to do this implementation ourselves and are looking for your review and sign-off on the "
    "approach, so it fits the Clients subgraph.\n\n"
    ":page_facing_up: Doc: <link>\n\n"
    "Thanks! :pray:\n"
    "cc: @<name>"
)
SLACK_DESIGN_SHARE_REWRITE = (
    "Hi <@team>, we are moving the BizApp Appointment Details screen to read from the federated graph instead "
    "of the legacy SOAP/REST path. On the Clients subgraph this needs automatedContactMethod on the client plus "
    "two new resolvers (progress note status, forms count). Additive only, no SQL changes.\n"
    "Design doc: <link>\n"
    "Please review whenever time permits.\n"
    "Thanks! :slightly_smiling_face:\n"
    "cc: @<name>"
)
SLACK_PROPOSAL_SENT = (
    "Hi <@team>/team, sharing the design proposal for a new endpoint in the Scheduling domain: Assign Guest "
    "Visit as per the discussion in the thread.\n"
    "This supports the BizApp workflow where a guest booked into a class is converted into a regular client. "
    "The endpoint updates the guest visit's ClientId to the newly created client via a direct SQL update within "
    "Scheduling \u2014 no Booking Service involvement.\n"
    "Design doc: <link>\n"
    "Key highlights:\n"
    "\u2022 PUT /v1/subscribers/{SubscriberId}/class-visits/{VisitId}/assign-guest-visit\n"
    "\u2022 Guest-only operation (ClientId = -2) \u2014 not a generic reassign\n"
    "\u2022 Atomic SQL update (validation + update in one query)\n"
    "\u2022 Stays entirely within the Scheduling domain\n\n"
    "Would appreciate feedback and approval before we move to implementation. Thanks! :slightly_smiling_face:\n"
    "cc: @<name>"
)
SLACK_PROPOSAL_REWRITE = (
    "Hi <@team>, following up on the thread above, here is the design proposal for the Assign Guest Visit "
    "endpoint in Scheduling. It updates a guest visit's ClientId to the newly created client with a single SQL "
    "update, guest visits only (ClientId = -2), no Booking Service involvement.\n"
    "Design doc: <link>\n"
    "Please take a look and let me know if this makes sense.\n"
    "Thanks! :slightly_smiling_face:\n"
    "cc: @<name>"
)

GITHUB_NATIVE_PR_BODY = (
    "## Summary\n"
    "Moves the null check into `InvoiceMapper.ToDomain` so both callers get it, and drops the duplicate guard "
    "the exporter carried since the mapper was split out of the billing service last spring.\n\n"
    "## Changes\n"
    "- `InvoiceMapper.ToDomain` returns early on a null invoice and logs the invoice id\n"
    "- `InvoiceExporter` no longer checks for null before mapping each row\n"
    "- tests cover the null path through both the exporter and the statement job\n\n"
    "## Testing\n"
    "Ran the exporter and statement suites locally.\n"
    "Overall this leaves one guard where there were two."
)
GITHUB_SCAFFOLDED_PR_BODY = (
    "## TL;DR\n"
    "This PR is not just a refactor, but a pivotal step that will enhance reliability across the exporter "
    "\u2014 every caller is now covered by a single guard in the mapper.\n\n"
    "## Key highlights\n"
    "- Additionally, `InvoiceMapper.ToDomain` now owns the null check for every invoice it maps\n"
    "- The exporter no longer duplicates the guard before it maps each row\n"
    "- New tests underscore the null path through the exporter and the statement job\n\n"
    "In summary, this change delivers a crucial and valuable improvement to how invoices are mapped."
)
NOTION_NATIVE_PAGE_COMMENT = (
    "Two things on the retry section before we sign off on the design:\n"
    "- the partner API caps pages at 500, so the batch size above cannot go higher without their sign-off\n"
    "- the backoff table should say which errors retry, since 409 from the ledger is not safe to repeat\n"
    "- the alert threshold is per region, not global, which changes the numbers in the last table\n"
    "Overall the flow reads right to me once those are fixed."
)
NOTION_SCAFFOLDED_PAGE_COMMENT = (
    "TL;DR: the retry design is solid but needs a couple of tweaks.\n"
    "This is not only about retries, but about building a robust and pivotal foundation that will enhance "
    "how we handle partner failures \u2014 the backoff table and the alert thresholds both need another pass, "
    "and the page should delve into which ledger errors are safe to repeat.\n"
    "In summary, a valuable direction with a few gaps to close."
)


def ctx(short_messages_use_bullets=False):
    return {"vocabulary": ai_filter.load_vocabulary(REFERENCE),
            "short_messages_use_bullets": short_messages_use_bullets}


def hits(text, channel, surface, short_messages_use_bullets=False):
    return ai_filter.score(text, surface, ai_filter.load_patterns(MODULES[channel]), ctx(short_messages_use_bullets))


def record(text, surface, ts="2026-03-04T10:12:00Z", held_out=False, thread="C1/1"):
    return {"channel": "slack", "surface": surface, "ts": ts, "audience": "C1", "thread": thread,
            "others": 2, "text": text, "held_out": held_out}


class PatternListTests(unittest.TestCase):
    def test_every_module_lists_all_nine_patterns(self):
        for name, path in MODULES.items():
            with self.subTest(channel=name):
                self.assertEqual(set(ai_filter.load_patterns(path)), set(ai_filter.DETECTORS))

    def test_slack_exempts_nothing(self):
        self.assertTrue(all(not exempt for exempt in ai_filter.load_patterns(MODULES["slack"]).values()))

    def test_github_and_notion_exempt_only_the_native_forms(self):
        native = {"labelled-list", "headers-bold-labels", "closing-restatement"}
        for name, surfaces in (("github", {"PR body", "review summary"}), ("notion", {"page comment"})):
            patterns = ai_filter.load_patterns(MODULES[name])
            with self.subTest(channel=name):
                self.assertEqual({pid for pid, exempt in patterns.items() if exempt}, native)
                self.assertTrue(all(patterns[pid] == surfaces for pid in native))

    def test_an_unknown_pattern_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "x.md"
            path.write_text("```ai-filter\nem-dash\nsparkle-emoji\n```\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ai_filter.load_patterns(path)

    def test_the_vocabulary_block_loads(self):
        vocabulary = ai_filter.load_vocabulary(REFERENCE)
        self.assertIn("pivotal", vocabulary)
        self.assertNotIn("key", vocabulary)


class SlackPairTests(unittest.TestCase):
    def test_the_scaffolded_proposal_is_dropped_at_the_default_threshold(self):
        found = hits(SLACK_PROPOSAL_SENT, "slack", "channel new post")
        self.assertEqual(found, ["em-dash", "labelled-list", "parallel-triple"])
        self.assertGreaterEqual(len(found), ai_filter.DEFAULT_THRESHOLD)

    def test_the_scaffolded_design_share_scores_two_and_needs_threshold_two(self):
        self.assertEqual(hits(SLACK_DESIGN_SHARE_SENT, "slack", "channel new post"),
                         ["em-dash", "emoji-section-marker"])

    def test_both_rewrites_score_nothing(self):
        for text in (SLACK_DESIGN_SHARE_REWRITE, SLACK_PROPOSAL_REWRITE):
            with self.subTest(text=text[:40]):
                self.assertEqual(hits(text, "slack", "channel new post"), [])


class NativeFormTests(unittest.TestCase):
    def test_a_native_pr_body_scores_nothing_on_the_pr_body_surface(self):
        self.assertEqual(hits(GITHUB_NATIVE_PR_BODY, "github", "PR body", short_messages_use_bullets=True), [])

    def test_the_same_text_scores_its_headers_and_closing_on_a_review_thread_reply(self):
        self.assertEqual(hits(GITHUB_NATIVE_PR_BODY, "github", "review thread reply", short_messages_use_bullets=True),
                         ["closing-restatement", "headers-bold-labels"])

    def test_a_scaffolded_pr_body_is_still_dropped_on_the_pr_body_surface(self):
        found = hits(GITHUB_SCAFFOLDED_PR_BODY, "github", "PR body", short_messages_use_bullets=True)
        self.assertEqual(found, ["em-dash", "not-x-but-y", "tldr-block", "vocabulary"])

    def test_a_native_page_comment_scores_nothing_on_the_page_comment_surface(self):
        self.assertEqual(hits(NOTION_NATIVE_PAGE_COMMENT, "notion", "page comment", short_messages_use_bullets=True), [])

    def test_the_same_comment_scores_its_labelled_list_and_closing_inline(self):
        self.assertEqual(hits(NOTION_NATIVE_PAGE_COMMENT, "notion", "inline comment", short_messages_use_bullets=True),
                         ["closing-restatement", "labelled-list"])

    def test_a_scaffolded_page_comment_is_still_dropped_on_the_page_comment_surface(self):
        found = hits(NOTION_SCAFFOLDED_PAGE_COMMENT, "notion", "page comment", short_messages_use_bullets=True)
        self.assertEqual(found, ["em-dash", "not-x-but-y", "tldr-block", "vocabulary"])

    def test_every_fixture_is_long_enough_to_be_scanned(self):
        for text in (SLACK_DESIGN_SHARE_SENT, SLACK_PROPOSAL_SENT, SLACK_PROPOSAL_REWRITE,
                     GITHUB_NATIVE_PR_BODY, GITHUB_SCAFFOLDED_PR_BODY,
                     NOTION_NATIVE_PAGE_COMMENT, NOTION_SCAFFOLDED_PAGE_COMMENT):
            with self.subTest(text=text[:40]):
                self.assertGreater(corpus.word_count(text), ai_filter.LONG_MESSAGE_WORDS)


class ParallelTripleTests(unittest.TestCase):
    triple = "intro\n- one\n- two\n- three"

    def test_counts_only_when_short_messages_never_use_bullets(self):
        self.assertTrue(ai_filter.parallel_triple(self.triple, ctx(False)))
        self.assertFalse(ai_filter.parallel_triple(self.triple, ctx(True)))

    def test_short_message_bullet_use_is_read_from_the_corpus(self):
        self.assertFalse(ai_filter.short_messages_use_bullets([record("just a line", "outer DM")]))
        self.assertTrue(ai_filter.short_messages_use_bullets([record("todo\n- a\n- b", "outer DM")]))


class ScopeTests(unittest.TestCase):
    patterns = {"em-dash": set(), "tldr-block": set(), "vocabulary": set()}
    loud = "TL;DR: pivotal and crucial \u2014 done\n" + "word " * 70
    quiet = "TL;DR: pivotal and crucial \u2014 done\nshort"

    def run_filter(self, records, cutoff="2026-01", threshold=3, borrow=False):
        kept, dropped = ai_filter.run_filter(records, self.patterns, ctx(), cutoff, threshold, borrow)
        return [r["ts"] for r in kept], [r["ts"] for r, _ in dropped]

    def test_only_long_post_cutoff_messages_are_scanned(self):
        records = [record(self.loud, "outer DM", ts="2025-12-01T00:00:00Z"),
                   record(self.loud, "outer DM", ts="2026-01-01T00:00:00Z"),
                   record(self.quiet, "outer DM", ts="2026-02-01T00:00:00Z"),
                   record(self.loud, "outer DM", ts="2026-03-01T00:00:00Z", held_out=True)]
        self.assertEqual(self.run_filter(records),
                         (["2025-12-01T00:00:00Z", "2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z"],
                          ["2026-01-01T00:00:00Z"]))

    def test_never_means_none_of_the_persons_messages_are_scanned(self):
        records = [record(self.loud, "outer DM", ts="2026-03-01T00:00:00Z")]
        self.assertEqual(self.run_filter(records, cutoff=None), (["2026-03-01T00:00:00Z"], []))

    def test_a_colleague_sample_is_scanned_regardless_of_date(self):
        records = [record(self.loud, "outer DM", ts="2024-03-01T00:00:00Z")]
        self.assertEqual(self.run_filter(records, cutoff=None, borrow=True), ([], ["2024-03-01T00:00:00Z"]))

    def test_the_threshold_decides(self):
        records = [record(self.loud, "outer DM", ts="2026-03-01T00:00:00Z")]
        self.assertEqual(self.run_filter(records, threshold=4), (["2026-03-01T00:00:00Z"], []))

    def test_the_threshold_may_rise_by_one_point_at_most(self):
        ai_filter.check_threshold(1)
        ai_filter.check_threshold(4)
        for bad in (0, 5):
            with self.subTest(threshold=bad), self.assertRaises(ValueError):
                ai_filter.check_threshold(bad)


class CliTests(unittest.TestCase):
    def test_writes_kept_records_and_prints_the_summary(self):
        records = [record(SLACK_PROPOSAL_SENT, "channel new post", ts="2026-03-01T00:00:00Z"),
                   record(SLACK_PROPOSAL_REWRITE, "channel new post", ts="2026-03-02T00:00:00Z"),
                   record("ok", "outer DM", ts="2026-03-03T00:00:00Z")]
        with tempfile.TemporaryDirectory() as tmp:
            source, kept = pathlib.Path(tmp) / "slack.jsonl", pathlib.Path(tmp) / "slack.kept.jsonl"
            corpus.write_jsonl(source, records)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = ai_filter.main(["--corpus", str(source), "--module", str(MODULES["slack"]),
                                       "--reference", str(REFERENCE), "--cutoff", "2026-01", "--kept", str(kept)])
            kept_ts = [r["ts"] for r in corpus.read_jsonl(kept)]
        summary = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(kept_ts, ["2026-03-02T00:00:00Z", "2026-03-03T00:00:00Z"])
        self.assertEqual({k: summary[k] for k in ("total", "scanned", "dropped", "drop_rate", "threshold")},
                         {"total": 3, "scanned": 2, "dropped": 1, "drop_rate": 0.333, "threshold": 3})
        self.assertEqual(summary["samples"][0]["id"], "C1/2026-03-01T00:00:00Z")

    def test_an_out_of_range_threshold_exits_two(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = ai_filter.main(["--corpus", "x", "--module", "x", "--reference", "x",
                                   "--cutoff", "never", "--threshold", "5", "--kept", "x"])
        self.assertEqual((code, err.getvalue()), (2, "ai_filter: threshold must be 1 to 4\n"))


if __name__ == "__main__":
    unittest.main()
