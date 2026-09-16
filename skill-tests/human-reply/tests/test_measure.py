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
import measure  # noqa: E402

SLACK = SKILL / "channels" / "slack.md"
SURFACES = {"outer DM": {"minimum": 20, "default": 50}, "write-up": {"minimum": 60, "default": 150}}


def words(n):
    return " ".join(["w"] * n)


def record(n, surface="outer DM", ts="2025-06-01T00:00:00Z", held_out=False, text=None, audience="D1"):
    return {"channel": "slack", "surface": surface, "ts": ts, "audience": audience, "thread": f"{audience}/{ts}",
            "others": 1, "text": text if text is not None else words(n), "held_out": held_out}


class PercentileTests(unittest.TestCase):
    def test_nearest_rank(self):
        values = list(range(1, 11))
        self.assertEqual([measure.percentile(values, p) for p in (50, 75, 90, 100)], [5, 8, 9, 10])

    def test_a_single_value_is_every_percentile(self):
        self.assertEqual(measure.percentile([7], 90), 7)

    def test_round_up_to_ten(self):
        self.assertEqual([measure.round_up_to_ten(n) for n in (1, 10, 11, 36)], [10, 10, 20, 40])


class SurfaceTests(unittest.TestCase):
    def test_thirty_pre_cutoff_records_derive_the_budget_from_their_90th_percentile(self):
        records = [record(n) for n in range(1, 31)]
        records += [record(200, ts="2026-03-01T00:00:00Z") for _ in range(10)]
        row = measure.surface_stats(records, SURFACES, "2026-01")["outer DM"]
        self.assertEqual((row["records"], row["pre_cutoff_records"]), (40, 30))
        self.assertEqual((row["budget"], row["label"]), (30, "measured"))
        self.assertEqual((row["median"], row["p75"], row["p90"]), (20, 30, 200))
        self.assertEqual(row["over_budget"], 0.25)

    def test_twenty_nine_pre_cutoff_records_take_the_default_and_are_estimated(self):
        records = [record(n) for n in range(1, 30)]
        records += [record(5, ts="2026-03-01T00:00:00Z") for _ in range(20)]
        row = measure.surface_stats(records, SURFACES, "2026-01")["outer DM"]
        self.assertEqual((row["pre_cutoff_records"], row["budget"], row["label"]), (29, 50, "estimated"))

    def test_the_budget_never_drops_below_the_module_minimum(self):
        row = measure.surface_stats([record(3) for _ in range(30)], SURFACES, None)["outer DM"]
        self.assertEqual((row["budget"], row["label"]), (20, "measured"))

    def test_no_cutoff_uses_the_whole_window(self):
        records = [record(40, ts="2026-08-01T00:00:00Z") for _ in range(30)]
        row = measure.surface_stats(records, SURFACES, None)["outer DM"]
        self.assertEqual((row["pre_cutoff_records"], row["budget"]), (30, 40))

    def test_an_empty_surface_still_gets_a_row(self):
        row = measure.surface_stats([], SURFACES, None)["write-up"]
        self.assertEqual(row, {"records": 0, "pre_cutoff_records": 0, "median": None, "p75": None, "p90": None,
                               "budget": 150, "label": "estimated", "over_budget": None})


class PatternRateTests(unittest.TestCase):
    def test_rates_are_shares_of_messages_over_sixty_words(self):
        long_a = "Hi folks, " + words(60) + " I think `Foo.Bar` is it?\ncc: @a"
        long_b = words(61) + "\n- one\n- two\n> quoted\nThanks! :slightly_smiling_face:"
        short = "Hi, I think so? " + words(3)
        rates = measure.pattern_rates([record(0, text=long_a), record(0, text=long_b), record(0, text=short)])
        self.assertEqual(rates["long_messages"], 2)
        self.assertEqual({k: rates[k] for k in ("opener", "hedge", "question", "code span", "cc line",
                                                  "bullets", "quote-reply", "sign-off", "emoji", "link")},
                         {"opener": 0.5, "hedge": 0.5, "question": 0.5, "code span": 0.5, "cc line": 0.5,
                          "bullets": 0.5, "quote-reply": 0.5, "sign-off": 0.5, "emoji": 0.5, "link": 0.0})

    def test_no_long_messages_gives_no_rates(self):
        self.assertIsNone(measure.pattern_rates([record(5)])["opener"])


class DriftTests(unittest.TestCase):
    def test_quarters_report_the_90th_percentile_and_the_share_over_150_words(self):
        records = [record(10, ts="2025-02-01T00:00:00Z"), record(20, ts="2025-03-01T00:00:00Z"),
                   record(160, ts="2025-11-01T00:00:00Z"), record(30, ts="2025-12-01T00:00:00Z")]
        self.assertEqual(measure.quarters(records), {
            "2025Q1": {"messages": 2, "p90": 20, "over_150": 0.0},
            "2025Q4": {"messages": 2, "p90": 160, "over_150": 0.5},
        })


class MeasureTests(unittest.TestCase):
    def test_held_out_records_are_not_measured_and_long_ids_are_listed(self):
        records = [record(70, audience="D1"), record(70, audience="D2", held_out=True), record(10, audience="D3")]
        stats = measure.measure(records, SURFACES, None, "slack")
        self.assertEqual(stats["surfaces"]["outer DM"]["records"], 2)
        self.assertEqual(stats["long_message_ids"], ["D1/2025-06-01T00:00:00Z"])
        self.assertEqual((stats["channel"], stats["method"], stats["cutoff"]), ("slack", "measured", "never"))

    def test_cli_writes_stats_json_for_every_module_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = pathlib.Path(tmp) / "slack.kept.jsonl", pathlib.Path(tmp) / "slack.stats.json"
            corpus.write_jsonl(source, [record(12)])
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                code = measure.main(["--corpus", str(source), "--module", str(SLACK),
                                     "--cutoff", "2026-01", "--out", str(out)])
            stats = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(list(stats["surfaces"]), list(corpus.load_surfaces(SLACK)))
        self.assertEqual(printed.getvalue(), "measure: 1 records, 0 over 60 words\n")


if __name__ == "__main__":
    unittest.main()
