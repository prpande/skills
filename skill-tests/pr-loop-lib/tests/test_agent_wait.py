import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

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

    def test_tool_use_turn_is_still_running(self):
        self.write_agent("a1", [{"type": "assistant", "message": {"stop_reason": "tool_use",
                                                                   "content": [{"type": "tool_use"}]}}])
        _, result, clock = self.run_wait("a1=990+600", wait=12)
        self.assertEqual(result, {"finished": [], "overdue": [], "running": ["a1"]})
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

    def test_agent_without_transcript_runs_until_its_limit(self):
        _, result, _ = self.run_wait("missing=990+600", wait=6)
        self.assertEqual(result["running"], ["missing"])
        _, result, _ = self.run_wait("missing=0+600")
        self.assertEqual([o["id"] for o in result["overdue"]], ["missing"])

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


if __name__ == "__main__":
    unittest.main()
