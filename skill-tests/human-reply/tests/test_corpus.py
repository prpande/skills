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

import corpus  # noqa: E402

MODULES = {name: SKILL / "channels" / f"{name}.md" for name in ("slack", "github", "notion")}


def record(thread, ts, others=1, surface="outer DM", text="hello there", held_out=False, audience="D1"):
    return {"channel": "slack", "surface": surface, "ts": ts, "audience": audience,
            "thread": thread, "others": others, "text": text, "held_out": held_out}


class SurfaceTests(unittest.TestCase):
    def test_each_module_lists_the_spec_surfaces_in_order(self):
        expected = {
            "slack": ["inner-circle DM", "outer DM", "group DM", "channel thread reply", "channel new post", "write-up"],
            "github": ["review thread reply", "review summary", "PR body", "issue comment"],
            "notion": ["page comment", "inline comment"],
        }
        for name, path in MODULES.items():
            with self.subTest(channel=name):
                self.assertEqual(list(corpus.load_surfaces(path)), expected[name])

    def test_every_minimum_is_a_positive_multiple_of_ten_at_or_below_its_default(self):
        for name, path in MODULES.items():
            for surface, limits in corpus.load_surfaces(path).items():
                with self.subTest(channel=name, surface=surface):
                    self.assertEqual(limits["minimum"] % 10, 0)
                    self.assertGreater(limits["minimum"], 0)
                    self.assertLessEqual(limits["minimum"], limits["default"])

    def test_a_byte_order_mark_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "slack.jsonl"
            line = json.dumps(record("D1/1", "2026-03-04T10:12:00Z")) + "\n"
            path.write_bytes(line.encode("utf-8-sig"))
            self.assertEqual(corpus.read_jsonl(path), [record("D1/1", "2026-03-04T10:12:00Z")])

    def test_a_missing_block_is_an_error(self):
        with self.assertRaises(ValueError):
            corpus.fenced_block("no fences here", "surfaces")


class ValidateTests(unittest.TestCase):
    surfaces = {"outer DM": {"minimum": 20, "default": 50}}

    def test_a_good_record_has_no_errors(self):
        self.assertEqual(corpus.validate_record(record("D1/1", "2026-03-04T10:12:00Z"), self.surfaces), [])

    def test_each_defect_is_named(self):
        bad = record("D1/1", "2026-03-04 10:12", surface="channel post")
        bad["others"] = "2"
        bad["author"] = "someone"
        del bad["held_out"]
        self.assertEqual(corpus.validate_record(bad, self.surfaces), [
            "field others is not int",
            "missing field held_out",
            "unknown fields ['author']",
            "surface 'channel post' is not in the channel module",
            "ts '2026-03-04 10:12' is not YYYY-MM-DDTHH:MM:SSZ",
        ])

    def test_cli_exits_one_and_prints_each_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "slack.jsonl"
            corpus.write_jsonl(path, [record("D1/1", "2026-03-04T10:12:00Z"),
                                      record("D1/2", "2026-03-04T10:12:00Z", surface="nope")])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = corpus.main(["validate", "--corpus", str(path), "--module", str(MODULES["slack"])])
        self.assertEqual(code, 1)
        self.assertIn(":2: surface 'nope' is not in the channel module", out.getvalue())
        self.assertTrue(out.getvalue().endswith("corpus: 2 records, 1 errors\n"))


class WordCountTests(unittest.TestCase):
    def test_links_and_fenced_blocks_count_as_one_word_each(self):
        text = ("see <https://nr.example/q?x=1|NR captures> and [the doc](https://notion.so/p) "
                "then\n```\nline one of a trace\nline two\n```\ndone")
        self.assertEqual(corpus.word_count(text), 7)

    def test_inline_code_counts_its_words(self):
        self.assertEqual(corpus.word_count("check `tbl Resource` now"), 4)


class CutoffTests(unittest.TestCase):
    def test_the_cutoff_month_counts_as_after(self):
        self.assertTrue(corpus.is_pre_cutoff(record("t", "2025-12-31T23:59:59Z"), "2026-01"))
        self.assertFalse(corpus.is_pre_cutoff(record("t", "2026-01-01T00:00:00Z"), "2026-01"))

    def test_no_cutoff_means_everything_is_before(self):
        self.assertTrue(corpus.is_pre_cutoff(record("t", "2026-09-01T00:00:00Z"), None))


class NormalizeTests(unittest.TestCase):
    def test_repeated_ids_collapse_and_the_newest_are_kept_newest_first(self):
        records = [record("D1/1", "2025-01-01T00:00:00Z"), record("D1/2", "2025-03-01T00:00:00Z"),
                   record("D1/2", "2025-03-01T00:00:00Z", text="resumed copy"), record("D1/3", "2025-02-01T00:00:00Z")]
        kept = corpus.normalize(records, cap=2)
        self.assertEqual([r["ts"] for r in kept], ["2025-03-01T00:00:00Z", "2025-02-01T00:00:00Z"])
        self.assertEqual(kept[0]["text"], "hello there")

    def test_cli_normalize_rewrites_and_oldest_prints_the_resume_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "slack.jsonl"
            corpus.write_jsonl(path, [record("D1/1", "2025-01-01T00:00:00Z"), record("D1/2", "2025-03-01T00:00:00Z")])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(corpus.main(["normalize", "--corpus", str(path), "--cap", "1"]), 0)
                self.assertEqual(corpus.main(["oldest", "--corpus", str(path)]), 0)
        self.assertEqual(out.getvalue(), "corpus: 2 records in, 1 kept\n2025-03-01T00:00:00Z\n")

    def test_oldest_of_an_empty_corpus_is_none(self):
        self.assertIsNone(corpus.oldest_ts([]))


class HoldoutTests(unittest.TestCase):
    def test_three_pre_cutoff_threads_with_another_participant_are_marked(self):
        records = [record(f"D1/{i}", "2025-06-01T00:00:00Z") for i in range(6)]
        records.append(record("D1/solo", "2025-06-01T00:00:00Z", others=0))
        records.append(record("D1/late", "2026-06-01T00:00:00Z"))
        chosen = corpus.select_holdouts(records, "2026-01", seed=7)
        self.assertEqual(len(chosen), 3)
        self.assertTrue(all(pool == "pre-cutoff" for _, pool in chosen))
        threads = {t for t, _ in chosen}
        self.assertNotIn("D1/solo", threads)
        self.assertNotIn("D1/late", threads)
        self.assertEqual({r["thread"] for r in records if r["held_out"]}, threads)

    def test_a_thread_with_a_pr_body_is_not_eligible(self):
        records = [record("R1/pr", "2025-06-01T00:00:00Z", surface="PR body"),
                   record("R1/pr", "2025-06-02T00:00:00Z", surface="issue comment"),
                   record("R1/review", "2025-06-01T00:00:00Z", surface="review thread reply")]
        self.assertEqual(corpus.select_holdouts(records, None, seed=1), [("R1/review", "pre-cutoff")])
        self.assertEqual([r["held_out"] for r in records], [False, False, True])

    def test_the_same_seed_picks_the_same_threads(self):
        make = lambda: [record(f"D1/{i}", "2025-06-01T00:00:00Z") for i in range(10)]
        self.assertEqual(corpus.select_holdouts(make(), "2026-01", seed=3),
                         corpus.select_holdouts(make(), "2026-01", seed=3))

    def test_a_dm_with_one_other_participant_qualifies(self):
        records = [record("D1/1", "2025-06-01T00:00:00Z", others=1)]
        self.assertEqual(corpus.select_holdouts(records, None, seed=1), [("D1/1", "pre-cutoff")])

    def test_no_cutoff_draws_from_the_whole_window(self):
        records = [record("D1/1", "2026-08-01T00:00:00Z"), record("D1/2", "2026-09-01T00:00:00Z")]
        chosen = corpus.select_holdouts(records, None, seed=1)
        self.assertEqual(sorted(chosen), [("D1/1", "pre-cutoff"), ("D1/2", "pre-cutoff")])

    def test_a_thread_straddling_the_cutoff_is_in_neither_pool(self):
        records = [record("D1/1", "2025-12-30T00:00:00Z"), record("D1/1", "2026-01-02T00:00:00Z", text="later")]
        passed = {corpus.record_id(r) for r in records}
        self.assertEqual(corpus.select_holdouts(records, "2026-01", seed=1, passed_ids=passed), [])

    def test_post_cutoff_threads_fill_the_remainder_only_when_every_record_passed(self):
        records = [record("D1/pre", "2025-06-01T00:00:00Z"),
                   record("D1/ok", "2026-03-01T00:00:00Z", audience="D2"),
                   record("D1/dropped", "2026-03-02T00:00:00Z", audience="D3")]
        first = corpus.select_holdouts(records, "2026-01", seed=1)
        self.assertEqual(first, [("D1/pre", "pre-cutoff")])
        passed = {"D2/2026-03-01T00:00:00Z"}
        second = corpus.select_holdouts(records, "2026-01", seed=1, passed_ids=passed)
        self.assertEqual(second, [("D1/pre", "earlier"), ("D1/ok", "post-cutoff")])

    def test_no_qualifying_thread_returns_an_empty_list(self):
        records = [record("D1/1", "2025-06-01T00:00:00Z", others=0)]
        self.assertEqual(corpus.select_holdouts(records, "2026-01", seed=1, passed_ids=set()), [])
        self.assertFalse(records[0]["held_out"])

    def test_cli_rewrites_the_corpus_and_prints_the_pools(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "slack.jsonl"
            corpus.write_jsonl(path, [record("D1/1", "2025-06-01T00:00:00Z")])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = corpus.main(["holdout", "--corpus", str(path), "--cutoff", "2026-01", "--seed", "4"])
            rewritten = corpus.read_jsonl(path)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue()), [{"thread": "D1/1", "pool": "pre-cutoff"}])
        self.assertTrue(rewritten[0]["held_out"])

    def test_cli_rejects_a_cutoff_that_is_not_a_month_or_never(self):
        for bad in ("2026-1", "2026-13", "none", "Jan 2026"):
            with self.subTest(cutoff=bad), contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as exit_:
                    corpus.main(["holdout", "--corpus", "x", "--cutoff", bad, "--seed", "1"])
                self.assertEqual(exit_.exception.code, 2)
                self.assertIn("YYYY-MM or never", err.getvalue())

    def test_cli_reset_clears_marks_left_by_an_earlier_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "slack.jsonl"
            corpus.write_jsonl(path, [record("D1/late", "2026-03-01T00:00:00Z", held_out=True),
                                      record("D1/early", "2025-03-01T00:00:00Z", audience="D2")])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                corpus.main(["holdout", "--corpus", str(path), "--cutoff", "2026-01", "--seed", "4", "--reset"])
            rewritten = corpus.read_jsonl(path)
        self.assertEqual(json.loads(out.getvalue()), [{"thread": "D1/early", "pool": "pre-cutoff"}])
        self.assertEqual([r["held_out"] for r in rewritten], [False, True])


if __name__ == "__main__":
    unittest.main()
