import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "pr-tooling" / "pr-loop-lib" / "scripts"))

import agent_wait  # noqa: E402

SESSION = "11111111-2222-3333-4444-555555555555"


class FakeClock:
    def __init__(self, start):
        self.now = start
        self.sleeps = 0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps += 1
        self.now += seconds


class AgentWaitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.projects = pathlib.Path(self.tmp.name)
        self.subagents = self.projects / "D--some-project" / SESSION / "subagents"
        self.subagents.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write_agent(self, agent_id, records, meta=None):
        path = self.subagents / f"agent-{agent_id}.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        if meta is not None:
            (self.subagents / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")

    def run_wait(self, *specs, wait=240, clock=None):
        clock = clock or FakeClock(1000)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = agent_wait.main(["--wait", str(wait), "--session", SESSION, "--projects", str(self.projects),
                                    *specs], clock=clock.time, sleep=clock.sleep)
        return code, json.loads(out.getvalue()), clock

    def test_meta_finished_flag_counts_as_finished(self):
        self.write_agent("a1", [{"type": "user"}], meta={"finished": True})
        code, result, clock = self.run_wait("a1=990+600")
        self.assertEqual(code, 0)
        self.assertEqual(result["finished"], ["a1"])
        self.assertEqual(clock.sleeps, 0)

    def test_end_turn_without_tool_use_counts_as_finished(self):
        self.write_agent("a1", [{"type": "assistant", "message": {"stop_reason": "end_turn",
                                                                   "content": [{"type": "text", "text": "ok"}]}}])
        _, result, _ = self.run_wait("a1=990+600")
        self.assertEqual(result["finished"], ["a1"])

    def test_only_the_last_record_decides(self):
        done = {"type": "assistant", "message": {"stop_reason": "end_turn", "content": []}}
        self.write_agent("a1", [done, {"type": "user"}])
        _, result, _ = self.run_wait("a1=990+600", wait=6)
        self.assertEqual(result["running"], ["a1"])

    def test_large_transcript_reads_last_record(self):
        filler = {"type": "user", "pad": "x" * 1000}
        done = {"type": "assistant", "message": {"stop_reason": "end_turn", "content": []}}
        self.write_agent("a1", [filler] * 600 + [done])
        _, result, _ = self.run_wait("a1=990+600")
        self.assertEqual(result["finished"], ["a1"])

    def test_tool_use_turn_is_still_running(self):
        self.write_agent("a1", [{"type": "assistant", "message": {"stop_reason": "tool_use",
                                                                   "content": [{"type": "tool_use"}]}}])
        _, result, clock = self.run_wait("a1=990+600", wait=12)
        self.assertEqual(result, {"finished": [], "overdue": [], "running": ["a1"], "no_transcript": []})
        self.assertGreater(clock.sleeps, 0)

    def test_agent_past_its_limit_is_overdue(self):
        self.write_agent("a1", [{"type": "user"}])
        _, result, _ = self.run_wait("a1=300+600")
        self.assertEqual(result["overdue"], [{"id": "a1", "elapsed_s": 700, "limit_s": 600}])

    def test_returns_when_an_agent_passes_its_limit_during_the_wait(self):
        self.write_agent("a1", [{"type": "user"}])
        _, result, clock = self.run_wait("a1=1000+20", wait=240)
        self.assertEqual([o["id"] for o in result["overdue"]], ["a1"])
        self.assertLess(clock.now - 1000, 40)

    def test_finished_wins_over_overdue(self):
        self.write_agent("a1", [{"type": "user"}], meta={"finished": True})
        _, result, _ = self.run_wait("a1=0+60")
        self.assertEqual(result["finished"], ["a1"])
        self.assertEqual(result["overdue"], [])

    def test_agent_without_transcript_runs_until_its_limit_and_is_flagged(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            _, result, _ = self.run_wait("missing=990+600", wait=6)
            self.assertEqual(result["running"], ["missing"])
            self.assertEqual(result["no_transcript"], ["missing"])
            _, result, _ = self.run_wait("missing=0+600")
        self.assertEqual([o["id"] for o in result["overdue"]], ["missing"])
        self.assertEqual(result["no_transcript"], ["missing"])
        self.assertIn("missing", err.getvalue())

    def test_agent_with_transcript_is_not_flagged(self):
        self.write_agent("a1", [{"type": "user"}])
        _, result, _ = self.run_wait("a1=0+600")
        self.assertEqual(result["no_transcript"], [])

    def test_agent_at_exactly_its_limit_is_still_running(self):
        self.write_agent("a1", [{"type": "user"}])
        _, result, _ = self.run_wait("a1=400+600", wait=0)
        self.assertEqual(result["running"], ["a1"])
        self.assertEqual(result["overdue"], [])

    def test_session_id_with_glob_characters_is_matched_literally(self):
        odd = self.projects / "D--p" / "s[1]" / "subagents"
        odd.mkdir(parents=True)
        (odd / "agent-a1.jsonl").write_text("{}\n", encoding="utf-8")
        (odd / "agent-a1.meta.json").write_text('{"finished": true}', encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            agent_wait.main(["--session", "s[1]", "--projects", str(self.projects), "a1=990+600"])
        self.assertEqual(json.loads(out.getvalue())["finished"], ["a1"])

    def test_meta_finished_must_be_true_not_truthy(self):
        self.write_agent("a1", [{"type": "user"}], meta={"finished": "yes"})
        _, result, _ = self.run_wait("a1=990+600", wait=0)
        self.assertEqual(result["finished"], [])

    def test_unusable_meta_falls_back_to_the_transcript(self):
        done = {"type": "assistant", "message": {"stop_reason": "end_turn", "content": []}}
        bad_metas = [b"{not json", b"null", b"[]", "é".encode("utf-8")[:1]]
        for i, raw in enumerate(bad_metas):
            agent_id = f"a{i}"
            self.write_agent(agent_id, [done])
            (self.subagents / f"agent-{agent_id}.meta.json").write_bytes(raw)
        _, result, _ = self.run_wait(*[f"a{i}=990+600" for i in range(len(bad_metas))])
        self.assertEqual(sorted(result["finished"]), sorted(f"a{i}" for i in range(len(bad_metas))))

    def test_last_record_that_is_not_an_object_is_not_finished(self):
        (self.subagents / "agent-a1.jsonl").write_text("[1, 2]\n", encoding="utf-8")
        _, result, _ = self.run_wait("a1=990+600", wait=0)
        self.assertEqual(result["running"], ["a1"])

    def test_last_record_with_non_object_message_is_not_finished(self):
        for i, message in enumerate(("end_turn", ["end_turn"], None)):
            self.write_agent(f"a{i}", [{"type": "assistant", "message": message}])
        _, result, _ = self.run_wait("a0=990+600", "a1=990+600", "a2=990+600", wait=0)
        self.assertEqual(result["running"], ["a0", "a1", "a2"])

    def test_dispatch_time_in_the_future_exits_2(self):
        for spec in ("a1=1000000+600", "a1=1000000000+600"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                self.run_wait(spec)
            self.assertEqual(caught.exception.code, 2)

    def test_dispatch_time_within_a_minute_ahead_is_accepted(self):
        self.write_agent("a1", [{"type": "user"}])
        _, result, _ = self.run_wait("a1=1050+600", wait=0)
        self.assertEqual(result["running"], ["a1"])

    def test_partial_last_line_is_skipped(self):
        done = {"type": "assistant", "message": {"stop_reason": "end_turn", "content": []}}
        (self.subagents / "agent-a1.jsonl").write_text(json.dumps(done) + '\n{"type": "assis', encoding="utf-8")
        _, result, _ = self.run_wait("a1=990+600")
        self.assertEqual(result["finished"], ["a1"])

    def test_transcript_with_invalid_utf8_is_still_read(self):
        done = json.dumps({"type": "assistant", "message": {"stop_reason": "end_turn", "content": []}})
        (self.subagents / "agent-a1.jsonl").write_bytes(b'{"x": "\xff"}\n' + done.encode("utf-8") + b"\n")
        _, result, _ = self.run_wait("a1=990+600")
        self.assertEqual(result["finished"], ["a1"])

    def test_final_record_larger_than_the_tail_read_is_not_finished_without_meta(self):
        big = {"type": "assistant", "message": {"stop_reason": "end_turn", "content": "x" * (agent_wait.TAIL_BYTES + 10)}}
        self.write_agent("a1", [big])
        _, result, _ = self.run_wait("a1=990+600", wait=0)
        self.assertEqual(result["running"], ["a1"])
        self.write_agent("a2", [big], meta={"finished": True})
        _, result, _ = self.run_wait("a2=990+600")
        self.assertEqual(result["finished"], ["a2"])

    def test_transcript_found_once_is_cached(self):
        self.write_agent("a1", [{"type": "user"}])
        cache = {}
        agent_wait.classify([("a1", 990, 600)], str(self.projects), SESSION, 1000, cache)
        self.assertIn("a1", cache)
        result = agent_wait.classify([("a1", 990, 600)], "/nonexistent", SESSION, 1000, cache)
        self.assertEqual(result["no_transcript"], [])
        self.assertEqual(result["running"], ["a1"])

    def test_reports_every_agent_in_one_result(self):
        self.write_agent("done", [{"type": "user"}], meta={"finished": True})
        self.write_agent("slow", [{"type": "user"}])
        self.write_agent("busy", [{"type": "user"}])
        _, result, _ = self.run_wait("done=990+600", "slow=0+600", "busy=990+600")
        self.assertEqual(result["finished"], ["done"])
        self.assertEqual([o["id"] for o in result["overdue"]], ["slow"])
        self.assertEqual(result["running"], ["busy"])

    def test_bad_agent_spec_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            agent_wait.main(["--session", SESSION, "a1-no-limit"])
        self.assertEqual(caught.exception.code, 2)

    def test_non_finite_spec_exits_2(self):
        for spec in ("a1=-inf+600", "a1=1000+inf", "a1=nan+600"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                agent_wait.main(["--session", SESSION, spec])
            self.assertEqual(caught.exception.code, 2)

    def test_missing_session_exits_2(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                agent_wait.main(["a1=990+600"])
        self.assertEqual(caught.exception.code, 2)

    def test_negative_or_nan_wait_exits_2(self):
        for wait in ("-1", "nan"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                agent_wait.main(["--wait", wait, "--session", SESSION, "a1=990+600"])
            self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
