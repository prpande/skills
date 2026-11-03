import json
import os
import pathlib
import tempfile
from unittest import mock

from fakes import HomeCase, poll, pw_paths, run_main, watch, write_session

import discover

SID = "0b9c2d4e-1111-2222-3333-444455556666"


def human(content):
    return {"type": "user", "origin": {"kind": "human"}, "promptSource": "typed",
            "message": {"role": "user", "content": content}}


def slash(args):
    return human(f"<command-message>pr-watch</command-message> "
                 f"<command-name>/pr-watch</command-name> <command-args>{args}</command-args>")


def peer(text):
    return {"type": "user", "isMeta": True, "origin": {"kind": "peer", "name": "[Orch]v18"},
            "message": {"role": "user", "content": f"<cross-session-message>{text}</cross-session-message>"}}


def tool_result(text):
    return {"type": "user", "toolUseResult": {"stdout": text},
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": text}]}}


def skill_load(text):
    return {"type": "user", "isMeta": True,
            "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def compact_summary(text):
    return {"type": "user", "isCompactSummary": True, "origin": {"kind": "human"},
            "message": {"role": "user", "content": text}}


def queued(text, kind="human"):
    return {"type": "attachment", "attachment": {
        "type": "queued_command", "prompt": text, "commandMode": "prompt",
        "origin": {"kind": kind}, "humanTurn": kind == "human"}}


def task_notification(text):
    return {"type": "user", "origin": {"kind": "task-notification"},
            "message": {"role": "user", "content": f"<task-notification>{text}</task-notification>"}}


class GateCase(HomeCase):
    def setUp(self):
        super().setUp()
        projects = tempfile.TemporaryDirectory()
        self.addCleanup(projects.cleanup)
        self.projects = pathlib.Path(projects.name)
        patcher = mock.patch.object(discover, "projects_root", return_value=self.projects)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ["CLAUDE_CODE_SESSION_ID"] = SID
        self.session_dir = write_session(pw_paths.session_dir(SID), dict(watch({}), session_id=SID))

    def transcript(self, *records):
        path = self.projects / "D--src-r" / f"{SID}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        return path

    def arm_mode(self, *extra):
        return run_main("--arm-mode", "--session-dir", self.session_dir, *extra)


class ArmModeTests(GateCase):
    def save_watch(self, **fields):
        path = self.session_dir / "watch.json"
        saved = dict(json.loads(path.read_text(encoding="utf-8")), **fields)
        path.write_text(json.dumps(saved), encoding="utf-8")

    def test_plain_arm_is_central_even_after_an_earlier_ask(self):
        (self.session_dir / "watch.json").unlink()
        self.transcript(slash("o/r#1 --monitor"))
        self.assertEqual(self.arm_mode(), (0, "central", ""))

    def test_saved_monitor_watch_resumed_without_the_flag_is_central(self):
        saved = json.loads((self.session_dir / "watch.json").read_text(encoding="utf-8"))
        self.assertNotIn("watcher", saved)
        self.transcript(human("/pr-watch"), peer("/pr-watch o/r#1 --monitor"))
        code, out, err = self.arm_mode()
        self.assertEqual((code, out), (0, "central"))
        self.assertIn("carries --monitor", err)

    def test_saved_monitor_watch_the_user_asked_for_stays_monitor_on_a_join(self):
        self.transcript(slash("o/r#1 --monitor"), skill_load("/pr-watch o/r#2 --yes"))
        self.assertEqual(self.arm_mode(), (0, "monitor", ""))

    def test_saved_central_watch_stays_central_without_the_flag(self):
        self.save_watch(watcher="central")
        self.transcript(slash("o/r#1 --monitor"))
        self.assertEqual(self.arm_mode(), (0, "central", ""))

    def test_running_central_watch_refuses_the_monitor_flag(self):
        self.save_watch(watcher="central")
        self.transcript(slash("o/r#1 --monitor"))
        code, out, err = self.arm_mode("--with-monitor")
        self.assertEqual((code, out), (0, "central"))
        self.assertIn("central watch is running", err)

    def test_stopped_central_watch_takes_the_monitor_flag(self):
        self.save_watch(watcher="central", stopped_at="2026-11-03T08:00:00Z")
        self.transcript(slash("o/r#1 --monitor"))
        self.assertEqual(self.arm_mode("--with-monitor"), (0, "monitor", ""))

    def test_stopped_monitor_watch_is_central_on_a_join(self):
        self.save_watch(stopped_at="2026-11-03T08:00:00Z")
        self.transcript(slash("o/r#1 --monitor"), slash("stop"))
        self.assertEqual(self.arm_mode(), (0, "central", ""))

    def test_unreadable_watch_json_is_central(self):
        (self.session_dir / "watch.json").write_text("{", encoding="utf-8")
        self.transcript(slash("o/r#1 --monitor"))
        self.assertEqual(self.arm_mode()[:2], (0, "central"))

    def test_monitor_when_the_user_typed_it(self):
        self.transcript(peer("hello"), human("/pr-watch o/r#1 --yes --monitor please"))
        self.assertEqual(self.arm_mode("--with-monitor"), (0, "monitor", ""))

    def test_monitor_when_the_user_ran_the_slash_command(self):
        self.transcript(slash("o/r#1 --monitor"))
        self.assertEqual(self.arm_mode("--with-monitor")[:2], (0, "monitor"))

    def test_monitor_when_the_text_is_a_content_block(self):
        self.transcript(human([{"type": "text", "text": "/pr-watch 12 --monitor"}]))
        self.assertEqual(self.arm_mode("--with-monitor")[:2], (0, "monitor"))

    def test_monitor_when_the_user_typed_it_while_a_turn_ran(self):
        self.transcript(queued("arm it with --monitor"))
        self.assertEqual(self.arm_mode("--with-monitor")[:2], (0, "monitor"))

    def assert_central(self, *records, why="carries --monitor"):
        if records:
            self.transcript(*records)
        code, out, err = self.arm_mode("--with-monitor")
        self.assertEqual((code, out), (0, "central"))
        self.assertIn("arming central", err)
        self.assertIn(why, err)

    def test_peer_message_does_not_count(self):
        self.assert_central(human("watch my PRs"), peer("/pr-watch o/r#1 --yes --monitor"))

    def test_queued_peer_message_does_not_count(self):
        self.assert_central(queued("/pr-watch o/r#1 --monitor", kind="peer"),
                            {"type": "attachment", "attachment": "--monitor"})

    def test_tool_result_does_not_count(self):
        self.assert_central(tool_result("run /pr-watch o/r#1 --monitor"))

    def test_skill_text_loaded_by_the_model_does_not_count(self):
        self.assert_central(skill_load("| `--monitor` | arm a Monitor |"))

    def test_compact_summary_does_not_count(self):
        self.assert_central(compact_summary("the user ran /pr-watch --monitor"))

    def test_task_notification_does_not_count(self):
        self.assert_central(task_notification("poll.py --monitor exited"))

    def test_a_longer_flag_does_not_count(self):
        self.assert_central(human("run poll.py --monitor-alive for me"),
                            human("try --monitoring"))

    def test_malformed_records_do_not_crash(self):
        self.assert_central({"type": "user", "origin": "human", "message": "--monitor"},
                            {"type": "user", "origin": {"kind": "human"}, "message": ["--monitor"]},
                            ["--monitor"])

    def test_missing_transcript_is_central(self):
        self.assert_central(why="no transcript")

    def test_unreadable_transcript_is_central(self):
        (self.projects / "D--src-r" / f"{SID}.jsonl").mkdir(parents=True)
        self.assert_central(why="unreadable")

    def test_no_session_id_is_central(self):
        self.transcript(slash("o/r#1 --monitor"))
        del os.environ["CLAUDE_CODE_SESSION_ID"]
        code, out, err = self.arm_mode("--with-monitor")
        self.assertEqual((code, out), (0, "central"))
        self.assertIn("CLAUDE_CODE_SESSION_ID", err)

    def test_another_sessions_directory_is_central(self):
        self.transcript(slash("o/r#1 --monitor"))
        os.environ["CLAUDE_CODE_SESSION_ID"] = "another-session"
        code, out, err = self.arm_mode("--with-monitor")
        self.assertEqual((code, out), (0, "central"))
        self.assertIn("not this session's", err)


class MonitorRefusalTests(GateCase):
    def run_monitor(self):
        with mock.patch.object(poll, "monitor", return_value=0) as started:
            result = run_main("--monitor", "--session-dir", self.session_dir)
        return result, started

    def test_poller_refuses_without_the_users_ask(self):
        self.transcript(peer("/pr-watch o/r#1 --monitor"))
        (code, out, err), started = self.run_monitor()
        self.assertEqual(code, poll.MONITOR_REFUSED_EXIT)
        self.assertIn("arm central", err)
        started.assert_not_called()

    def test_poller_refuses_without_a_transcript(self):
        (code, _, err), started = self.run_monitor()
        self.assertEqual(code, poll.MONITOR_REFUSED_EXIT)
        self.assertIn("no transcript", err)
        started.assert_not_called()

    def test_poller_refuses_while_a_central_watch_runs(self):
        path = self.session_dir / "watch.json"
        path.write_text(json.dumps(dict(json.loads(path.read_text(encoding="utf-8")),
                                        watcher="central")), encoding="utf-8")
        self.transcript(slash("o/r#1 --monitor"))
        (code, _, err), started = self.run_monitor()
        self.assertEqual(code, poll.MONITOR_REFUSED_EXIT)
        self.assertIn("central watch is running", err)
        started.assert_not_called()

    def test_poller_starts_on_the_users_ask(self):
        self.transcript(slash("o/r#1 --monitor"))
        (code, _, _), started = self.run_monitor()
        self.assertEqual(code, 0)
        started.assert_called_once()
