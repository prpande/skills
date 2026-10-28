"""Tests for the old-watch scan and import, identity check and monitor liveness."""
import contextlib
import io
import json
import os
import pathlib
import tempfile
import time
import unittest
from unittest import mock

import fakes  # noqa: F401
import migrate
import poll
import pw_paths

NOW = 2_000_000_000
MAIN = r"D:\src\Repo"
SESSION = r"C:\Users\me\.claude\pr-watch\sessions\abc-123"


def proc(pid, ppid, name, cmdline=""):
    return {"pid": pid, "ppid": ppid, "name": name, "cmdline": cmdline}


def old_cmd(main=MAIN):
    return f'python.exe "C:\\skills\\scripts\\poll.py" --monitor --state-dir "{main}\\.pr-autopilot"'


def session_cmd(directory=SESSION):
    return f'python.exe "C:\\skills\\scripts\\poll.py" --monitor --session-dir "{directory}"'


def tree(claude_pid, claude_name, cmd, python_pid=300):
    return [proc(claude_pid, 1, claude_name),
            proc(200, claude_pid, "bash.exe"),
            proc(python_pid, 200, "python.exe", cmd)]


class WatchDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="pw-migrate-"))
        self.addCleanup(self._cleanup)
        self.main = self.tmp / "main"
        self.state = self.main / ".pr-autopilot"
        self.state.mkdir(parents=True)
        self.home = self.tmp / "home"
        patch = mock.patch.dict(os.environ, {"PR_WATCH_HOME": str(self.home)})
        patch.start()
        self.addCleanup(patch.stop)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_watch(self, prs=None):
        prs = prs if prs is not None else {"12": {"role": "authored", "settled_ids": ["a"]}}
        (self.state / "watch.json").write_text(
            json.dumps({"owner": "Acme", "repo": "Widgets", "prs": prs}), encoding="utf-8")

    def write_heartbeat(self, age):
        (self.state / "watch-heartbeat").write_text(str(NOW - age), encoding="utf-8")


class ScanTests(WatchDirCase):
    def test_none_without_a_watch(self):
        self.assertEqual("none", migrate.scan(self.main, 4242, [], NOW)["state"])

    def test_owned_when_monitor_ancestor_is_my_claude_even_if_renamed(self):
        self.write_watch()
        self.write_heartbeat(10)
        procs = tree(4242, "claude.exe.old.1730.4242", old_cmd(self.main))
        result = migrate.scan(self.main, 4242, procs, NOW)
        self.assertEqual("owned", result["state"])
        self.assertEqual(300, result["monitor_pid"])
        self.assertEqual(4242, result["owner_pid"])
        self.assertEqual(10, result["heartbeat_age"])
        self.assertEqual(["acme/widgets#12"], result["prs"])

    def test_foreign_when_another_claude_owns_the_monitor(self):
        self.write_watch()
        self.write_heartbeat(10)
        procs = tree(9999, "claude.exe", old_cmd(self.main))
        result = migrate.scan(self.main, 4242, procs, NOW)
        self.assertEqual("foreign", result["state"])
        self.assertEqual(9999, result["owner_pid"])

    def test_stale_without_process_and_old_heartbeat(self):
        self.write_watch()
        self.write_heartbeat(301)
        self.assertEqual("stale", migrate.scan(self.main, 4242, [], NOW)["state"])

    def test_live_unknown_without_process_and_fresh_heartbeat(self):
        self.write_watch()
        self.write_heartbeat(100)
        self.assertEqual("live-unknown", migrate.scan(self.main, 4242, [], NOW)["state"])

    def test_heartbeat_at_exactly_300_seconds_is_live_unknown(self):
        self.write_watch()
        self.write_heartbeat(300)
        self.assertEqual("live-unknown", migrate.scan(self.main, 4242, [], NOW)["state"])

    def test_unresolvable_ancestor_or_missing_claude_pid_is_never_owned(self):
        self.write_watch()
        self.write_heartbeat(10)
        orphan = [proc(300, 1, "python.exe", old_cmd(self.main))]
        result = migrate.scan(self.main, 4242, orphan, NOW)
        self.assertEqual("foreign", result["state"])
        self.assertIsNone(result["owner_pid"])
        self.assertEqual("foreign", migrate.scan(self.main, None, orphan, NOW)["state"])
        procs = tree(4242, "claude.exe", old_cmd(self.main))
        self.assertEqual("foreign", migrate.scan(self.main, None, procs, NOW)["state"])

    def test_missing_heartbeat_is_stale(self):
        self.write_watch()
        result = migrate.scan(self.main, 4242, [], NOW)
        self.assertEqual("stale", result["state"])
        self.assertIsNone(result["heartbeat_age"])

    def test_old_monitor_ignores_other_repos_and_session_monitors(self):
        procs = [proc(1, 0, "python.exe", old_cmd(r"D:\src\Other")),
                 proc(2, 0, "python.exe", session_cmd()),
                 proc(3, 0, "python.exe", old_cmd(self.main).replace("\\", "/").replace('"', "").upper())]
        self.assertEqual(3, migrate.old_monitor(self.main, procs)["pid"])

    def test_old_monitor_requires_the_monitor_flag(self):
        cmd = old_cmd(self.main).replace("--monitor ", "--report ")
        self.assertIsNone(migrate.old_monitor(self.main, [proc(1, 0, "python.exe", cmd)]))

    def test_old_monitor_does_not_match_a_longer_path(self):
        cmd = old_cmd(str(self.main) + "-two")
        self.assertIsNone(migrate.old_monitor(self.main, [proc(1, 0, "python.exe", cmd)]))


class ClaudeAncestorTests(unittest.TestCase):
    def test_first_claude_ancestor(self):
        procs = tree(4242, "claude.exe.old.1730.4242", "x")
        self.assertEqual(4242, migrate.claude_ancestor(300, procs))

    def test_none_without_claude_and_cycle_safe(self):
        procs = [proc(1, 2, "a.exe"), proc(2, 1, "b.exe")]
        self.assertIsNone(migrate.claude_ancestor(1, procs))
        self.assertIsNone(migrate.claude_ancestor(77, procs))


class ImportTests(WatchDirCase):
    def test_import_keeps_progress_lowercases_keys_and_retires_old_files(self):
        self.write_watch({"12": {"role": "authored", "settled_ids": ["s1"],
                                 "posted_reply_ids": ["r1"], "slack_ts": "1.2",
                                 "title": "not progress"}})
        self.write_heartbeat(5)
        (self.state / "watch-poller.json").write_text("{}", encoding="utf-8")
        keys = migrate.import_progress(self.main, self.home / "sessions" / "s")
        self.assertEqual(["acme/widgets#12"], keys)
        written = json.loads(pw_paths.progress_path("acme", "widgets", 12).read_text(encoding="utf-8"))
        self.assertEqual(["s1"], written["settled_ids"])
        self.assertEqual(["r1"], written["posted_reply_ids"])
        self.assertEqual("1.2", written["slack_ts"])
        self.assertNotIn("title", written)
        self.assertFalse((self.state / "watch.json").exists())
        self.assertTrue((self.state / "watch.json.migrated").exists())
        self.assertFalse((self.state / "watch-heartbeat").exists())
        self.assertFalse((self.state / "watch-poller.json").exists())

    def test_existing_progress_file_is_never_overwritten(self):
        self.write_watch({"12": {"settled_ids": ["old"]}, "13": {"settled_ids": ["x"]}})
        existing = pw_paths.progress_path("acme", "widgets", 12)
        existing.parent.mkdir(parents=True)
        existing.write_text('{"settled_ids": ["new"]}', encoding="utf-8")
        keys = migrate.import_progress(self.main, self.home)
        self.assertEqual(["acme/widgets#12", "acme/widgets#13"], keys)
        self.assertEqual(["new"], json.loads(existing.read_text(encoding="utf-8"))["settled_ids"])

    def test_rerun_after_crash_between_rename_and_unlink_cleans_up(self):
        self.write_watch()
        self.write_heartbeat(5)
        (self.state / "watch-poller.json").write_text("{}", encoding="utf-8")
        (self.state / "watch.json").replace(self.state / "watch.json.migrated")
        self.assertEqual([], migrate.import_progress(self.main, self.home))
        self.assertFalse((self.state / "watch-heartbeat").exists())
        self.assertFalse((self.state / "watch-poller.json").exists())

    def test_returns_existing_keys_too_and_skips_non_digit_keys(self):
        self.write_watch({"12": {"settled_ids": ["old"]}, "x": {}, "13": {"settled_ids": ["n"]}})
        existing = pw_paths.progress_path("acme", "widgets", 12)
        existing.parent.mkdir(parents=True)
        existing.write_text('{"settled_ids": ["new"]}', encoding="utf-8")
        keys = migrate.import_progress(self.main, self.home)
        self.assertEqual(["acme/widgets#12", "acme/widgets#13"], keys)
        self.assertEqual(["new"], json.loads(existing.read_text(encoding="utf-8"))["settled_ids"])
        self.assertTrue((self.state / "watch.json.migrated").exists())

    def test_a_failed_write_leaves_the_old_watch_in_place(self):
        self.write_watch()
        self.write_heartbeat(5)
        with mock.patch.object(migrate, "write_json_atomic", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                migrate.import_progress(self.main, self.home)
        self.assertTrue((self.state / "watch.json").exists())
        self.assertTrue((self.state / "watch-heartbeat").exists())


class IdentityTests(unittest.TestCase):
    def test_ok_when_claude_is_the_nearest_ancestor(self):
        procs = tree(4242, "claude.exe", "x")
        self.assertIsNone(migrate.identity_ok(4242, 300, procs, {}))

    def test_child_session_env_is_ignored(self):
        procs = tree(4242, "claude.exe", "x")
        self.assertIsNone(migrate.identity_ok(4242, 300, procs, {"CLAUDE_CODE_CHILD_SESSION": "1"}))

    def test_refuses_when_nearest_claude_is_another_pid(self):
        procs = [proc(5000, 1, "claude.exe"), proc(4242, 5000, "claude.exe"),
                 proc(200, 4242, "bash.exe"), proc(300, 200, "python.exe")]
        reason = migrate.identity_ok(5000, 300, procs, {})
        self.assertIn("5000", reason)
        self.assertIn("4242", reason)

    def test_refuses_a_missing_claude_pid(self):
        self.assertIsNotNone(migrate.identity_ok(None, 300, tree(4242, "claude.exe", "x"), {}))

    def test_cyclic_chain_terminates_at_the_nearest_claude(self):
        procs = [proc(900, 800, "python.exe"), proc(800, 700, "pwsh.exe"),
                 proc(700, 17736, "cmd.exe"), proc(17736, 3124, "claude.exe"),
                 proc(3124, 600, "python.exe"), proc(600, 500, "WindowsTerminal.exe"),
                 proc(500, 400, "conhost.exe"), proc(400, 17736, "cmd.exe")]
        self.assertEqual(17736, migrate.claude_ancestor(900, procs))
        self.assertIsNone(migrate.identity_ok(17736, 900, procs, {}))
        self.assertIsNone(migrate.claude_ancestor(3124, [p for p in procs if p["pid"] != 17736]))


class LeftoverAndAliveTests(WatchDirCase):
    def test_missing_claude_pid_ends_nothing_and_is_never_alive(self):
        (self.tmp / "watch-heartbeat").write_text(str(NOW - 5), encoding="utf-8")
        orphan = [proc(7001, 1, "python.exe", session_cmd(self.tmp))]
        self.assertEqual([], migrate.leftover_monitors(self.tmp, None, orphan))
        self.assertFalse(migrate.monitor_alive(self.tmp, None, orphan))
        self.assertFalse(migrate.monitor_alive(self.tmp, 4242, orphan))

    def test_leftover_is_the_poller_under_a_dead_claude_only(self):
        mine = tree(4242, "claude.exe", session_cmd(), python_pid=300)
        old = [proc(7000, 1, "bash.exe"), proc(7001, 7000, "python.exe", session_cmd())]
        other_session = [proc(7002, 1, "python.exe", session_cmd(SESSION + "-2"))]
        self.assertEqual([7001], migrate.leftover_monitors(SESSION, 4242, mine + old + other_session))

    def test_alive_with_same_ancestor_whatever_the_heartbeat_says(self):
        procs = tree(4242, "claude.exe.old.1.4242", session_cmd(self.tmp))
        self.assertTrue(migrate.monitor_alive(self.tmp, 4242, procs))
        (self.tmp / "watch-heartbeat").write_text(str(NOW - 3600), encoding="utf-8")
        self.assertTrue(migrate.monitor_alive(self.tmp, 4242, procs))

    def test_down_with_no_process_or_other_ancestor(self):
        procs = tree(4242, "claude.exe", session_cmd(self.tmp))
        (self.tmp / "watch-heartbeat").write_text(str(NOW - 5), encoding="utf-8")
        self.assertFalse(migrate.monitor_alive(self.tmp, 9999, procs))
        self.assertFalse(migrate.monitor_alive(self.tmp, 4242, []))


class ListProcessesTests(unittest.TestCase):
    def run_with(self, stdout, returncode=0):
        done = mock.Mock(stdout=stdout, stderr="boom", returncode=returncode)
        with mock.patch.object(migrate.os, "name", "nt"), \
                mock.patch.object(migrate.subprocess, "run", return_value=done) as run:
            return migrate.list_processes(), run

    def test_command_forces_utf8_output(self):
        _, run = self.run_with("[]")
        self.assertTrue(run.call_args.args[0][-1].startswith(
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"))

    def test_single_object_and_array_shapes(self):
        row = {"ProcessId": 1, "ParentProcessId": 0, "Name": "a.exe", "CommandLine": None}
        one, run = self.run_with(json.dumps(row))
        many, _ = self.run_with(json.dumps([row, row]))
        self.assertEqual([{"pid": 1, "ppid": 0, "name": "a.exe", "cmdline": ""}], one)
        self.assertEqual(2, len(many))
        self.assertEqual("powershell", run.call_args.args[0][0])
        self.assertIn("-NoProfile", run.call_args.args[0])

    def test_failure_raises(self):
        with self.assertRaises(OSError):
            self.run_with("", returncode=1)

    def test_empty_off_windows(self):
        with mock.patch.object(migrate.os, "name", "posix"):
            self.assertEqual([], migrate.list_processes())


class CliTests(WatchDirCase):
    def run_cli(self, argv, env, procs):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(migrate, "list_processes", return_value=procs))
            stack.enter_context(mock.patch.dict(os.environ, env))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = poll.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_check_identity_exit_codes(self):
        procs = tree(4242, "claude.exe", "x")
        procs.append(proc(os.getpid(), 200, "python.exe"))
        code, _, _ = self.run_cli(["--check-identity"],
                                  {"CLAUDE_PID": "4242", "CLAUDE_CODE_CHILD_SESSION": "1"}, procs)
        self.assertEqual(0, code)
        code, _, err = self.run_cli(["--check-identity"], {"CLAUDE_PID": "9"}, procs)
        self.assertEqual(1, code)
        self.assertIn("nearest claude ancestor", err)

    def test_monitor_alive_prints_state(self):
        (self.tmp / "watch-heartbeat").write_text(str(int(time.time())), encoding="utf-8")
        procs = tree(4242, "claude.exe", session_cmd(self.tmp))
        _, out, _ = self.run_cli(["--monitor-alive", "--session-dir", str(self.tmp)],
                                 {"CLAUDE_PID": "4242"}, procs)
        self.assertEqual("alive", out.strip())

    def test_end_leftover_monitors_uses_the_injected_killer(self):
        procs = [proc(7000, 1, "bash.exe"), proc(7001, 7000, "python.exe", session_cmd(self.tmp))]
        with mock.patch.object(migrate, "end_tree") as kill:
            _, out, _ = self.run_cli(["--end-leftover-monitors", "--session-dir", str(self.tmp)],
                                     {"CLAUDE_PID": "4242"}, procs)
        kill.assert_called_once_with(7001)
        self.assertEqual([7001], json.loads(out))

    def test_every_mode_but_check_identity_refuses_without_claude_pid(self):
        procs = [proc(7000, 1, "bash.exe"), proc(7001, 7000, "python.exe", session_cmd(self.tmp))]
        session = ["--session-dir", str(self.tmp)]
        for argv in (["--migrate-scan", str(self.main)] + session,
                     ["--migrate-import", str(self.main)] + session,
                     ["--end-leftover-monitors"] + session,
                     ["--monitor-alive"] + session):
            with self.subTest(argv=argv[0]), mock.patch.object(migrate, "end_tree") as kill:
                code, out, err = self.run_cli(argv, {"CLAUDE_PID": ""}, procs)
                self.assertEqual(1, code)
                self.assertEqual("", out)
                self.assertIn("pr-watch: CLAUDE_PID is not set", err)
                kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
