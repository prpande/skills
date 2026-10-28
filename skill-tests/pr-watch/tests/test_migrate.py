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
        self.assertEqual(["acme/widgets#13"], keys)
        self.assertEqual(["new"], json.loads(existing.read_text(encoding="utf-8"))["settled_ids"])

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
    def test_leftover_is_the_poller_under_a_dead_claude_only(self):
        mine = tree(4242, "claude.exe", session_cmd(), python_pid=300)
        old = [proc(7000, 1, "bash.exe"), proc(7001, 7000, "python.exe", session_cmd())]
        other_session = [proc(7002, 1, "python.exe", session_cmd(SESSION + "-2"))]
        self.assertEqual([7001], migrate.leftover_monitors(SESSION, 4242, mine + old + other_session))

    def test_alive_with_same_ancestor_and_fresh_heartbeat(self):
        (self.tmp / "watch-heartbeat").write_text(str(NOW - 30), encoding="utf-8")
        procs = tree(4242, "claude.exe.old.1.4242", session_cmd(self.tmp))
        self.assertTrue(migrate.monitor_alive(self.tmp, 4242, procs, NOW))

    def test_down_with_stale_heartbeat_no_heartbeat_or_other_ancestor(self):
        procs = tree(4242, "claude.exe", session_cmd(self.tmp))
        (self.tmp / "watch-heartbeat").write_text(str(NOW - 300), encoding="utf-8")
        self.assertFalse(migrate.monitor_alive(self.tmp, 4242, procs, NOW))
        (self.tmp / "watch-heartbeat").write_text(str(NOW - 5), encoding="utf-8")
        self.assertFalse(migrate.monitor_alive(self.tmp, 9999, procs, NOW))
        self.assertFalse(migrate.monitor_alive(self.tmp, 4242, [], NOW))
        (self.tmp / "watch-heartbeat").unlink()
        self.assertFalse(migrate.monitor_alive(self.tmp, 4242, procs, NOW))


class ListProcessesTests(unittest.TestCase):
    def run_with(self, stdout, returncode=0):
        done = mock.Mock(stdout=stdout, stderr="boom", returncode=returncode)
        with mock.patch.object(migrate.os, "name", "nt"), \
                mock.patch.object(migrate.subprocess, "run", return_value=done) as run:
            return migrate.list_processes(), run

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
    def test_check_identity_exit_codes(self):
        procs = tree(4242, "claude.exe", "x")
        procs.append(proc(os.getpid(), 200, "python.exe"))
        with mock.patch.object(migrate, "list_processes", return_value=procs):
            with mock.patch.dict(os.environ, {"CLAUDE_PID": "4242", "CLAUDE_CODE_CHILD_SESSION": "1"}):
                self.assertEqual(0, poll.main(["--check-identity"]))
            with mock.patch.dict(os.environ, {"CLAUDE_PID": "9"}),                     contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(1, poll.main(["--check-identity"]))
            self.assertIn("nearest claude ancestor", err.getvalue())

    def test_monitor_alive_prints_state(self):
        (self.tmp / "watch-heartbeat").write_text(str(int(time.time())), encoding="utf-8")
        procs = tree(4242, "claude.exe", session_cmd(self.tmp))
        with mock.patch.object(migrate, "list_processes", return_value=procs), \
                mock.patch.dict(os.environ, {"CLAUDE_PID": "4242"}), \
                mock.patch("sys.stdout") as out:
            poll.main(["--monitor-alive", "--session-dir", str(self.tmp)])
        self.assertIn("alive", "".join(c.args[0] for c in out.write.call_args_list))

    def test_end_leftover_monitors_uses_the_injected_killer(self):
        procs = [proc(7000, 1, "bash.exe"), proc(7001, 7000, "python.exe", session_cmd(self.tmp))]
        with mock.patch.object(migrate, "list_processes", return_value=procs), \
                mock.patch.object(migrate, "end_tree") as kill, \
                mock.patch.dict(os.environ, {"CLAUDE_PID": "4242"}),                 contextlib.redirect_stdout(io.StringIO()) as out:
            poll.main(["--end-leftover-monitors", "--session-dir", str(self.tmp)])
        kill.assert_called_once_with(7001)
        self.assertEqual([7001], json.loads(out.getvalue()))


if __name__ == "__main__":
    unittest.main()
