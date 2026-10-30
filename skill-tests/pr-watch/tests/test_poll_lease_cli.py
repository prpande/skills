import contextlib
import io
import json
import os
import time
import unittest

from fakes import HomeCase, lease, poll, pw_paths, watch, write_session

REF = "o/r#1"
OLD = time.time() - 10_000


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = poll.main([str(a) for a in argv])
    return code, out.getvalue().strip(), err.getvalue().strip()


class LeaseCliCase(HomeCase):
    def session(self, session_id):
        view = watch({REF: "authored"})
        view["session_id"] = session_id
        view["claude_pid"] = os.getpid()
        return write_session(pw_paths.home() / "sessions" / session_id, view)

    def put_lease(self, session_id, number=1, status="armed", heartbeat=OLD, repo="r"):
        path = pw_paths.lease_path("o", repo, number)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": 1, "owner": "o", "repo": repo, "number": number, "role": "authored",
            "holder": {"session_id": session_id, "pid": 2_000_000_000,
                       "pid_started_at": pw_paths.iso_utc(OLD), "poller_pid": None},
            "heartbeat": pw_paths.iso_utc(heartbeat), "stale_after_seconds": 300,
            "status": status, "last_head_sha": None, "pending_since": None,
            "last_error": None, "updated_at": pw_paths.iso_utc(heartbeat)}), encoding="utf-8")


class ClaimCliTests(LeaseCliCase):
    def test_claim_then_reclaim_with_same_session(self):
        d = self.session("s-a")
        self.assertEqual(run("--claim", REF, "--session-dir", d, "--role", "authored")[:2],
                         (0, "claimed"))
        self.assertEqual(run("--claim", REF, "--session-dir", d, "--role", "authored")[:2],
                         (0, "reclaimed"))
        self.assertEqual(lease.read_lease("o", "r", 1)["holder"]["session_id"], "s-a")

    def test_claim_cli_central_flag_writes_central_lease(self):
        d = self.session("s-a")
        self.assertEqual(run("--claim", REF, "--session-dir", d, "--role", "authored",
                             "--central")[:2], (0, "claimed"))
        record = lease.read_lease("o", "r", 1)
        self.assertEqual((record["watcher"], record["stale_after_seconds"]), ("central", 900))

    def test_claim_clears_the_pr_from_the_sessions_lease_silencing(self):
        d = self.session("s-a")
        key = pw_paths.pr_key("o", "r", 1)
        (d / "watch-poller.json").write_text(json.dumps({
            "lease_dropped": [key, "o/r#2"], "lease_warned": [key], "closed": []}),
            encoding="utf-8")
        self.assertEqual(run("--claim", REF, "--session-dir", d, "--role", "authored")[0], 0)
        saved = json.loads((d / "watch-poller.json").read_text(encoding="utf-8"))
        self.assertEqual((saved["lease_dropped"], saved["lease_warned"], saved["closed"]),
                         (["o/r#2"], [], []))

    def test_claim_without_a_poller_file_creates_none(self):
        d = self.session("s-a")
        run("--claim", REF, "--session-dir", d, "--role", "authored")
        self.assertFalse((d / "watch-poller.json").exists())

    def test_claim_without_central_flag_writes_a_monitor_lease(self):
        run("--claim", REF, "--session-dir", self.session("s-a"), "--role", "authored")
        self.assertEqual(lease.read_lease("o", "r", 1)["stale_after_seconds"], 300)

    def test_central_without_claim_is_a_usage_error(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            run("--report", "--session-dir", self.session("s-a"), "--central")

    def test_a_claude_pid_stored_as_text_is_written_as_an_integer(self):
        d = self.session("s-a")
        view = json.loads((d / "watch.json").read_text(encoding="utf-8"))
        view["claude_pid"] = str(os.getpid())
        (d / "watch.json").write_text(json.dumps(view), encoding="utf-8")
        run("--claim", REF, "--session-dir", d, "--role", "authored")
        self.assertEqual(lease.read_lease("o", "r", 1)["holder"]["pid"], os.getpid())

    def test_claim_of_another_sessions_dead_lease_prints_taken_over(self):
        self.put_lease("s-old")
        code, out, _ = run("--claim", REF, "--session-dir", self.session("s-new"),
                           "--role", "authored")
        self.assertEqual((code, out), (0, "taken-over"))
        self.assertEqual(lease.read_lease("o", "r", 1)["holder"]["session_id"], "s-new")

    def test_refusal_exits_1_and_names_the_holder(self):
        self.put_lease("s-old", heartbeat=time.time() - 30)
        code, out, err = run("--claim", REF, "--session-dir", self.session("s-new"),
                             "--role", "authored")
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("pr-watch: "))
        self.assertIn("s-old", err)

    def test_claim_without_role_is_a_usage_error(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            run("--claim", REF, "--session-dir", self.session("s-a"))


class LeaseStatusCliTests(LeaseCliCase):
    def test_holder_sets_status(self):
        d = self.session("s-a")
        run("--claim", REF, "--session-dir", d, "--role", "authored")
        self.assertEqual(run("--lease-status", REF, "--session-dir", d, "--status", "stopped")[:2],
                         (0, "stopped"))
        self.assertEqual(lease.read_lease("o", "r", 1)["status"], "stopped")

    def test_non_holder_exits_1(self):
        run("--claim", REF, "--session-dir", self.session("s-a"), "--role", "authored")
        code, _, err = run("--lease-status", REF, "--session-dir", self.session("s-b"),
                           "--status", "released")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("pr-watch: "))
        self.assertEqual(lease.read_lease("o", "r", 1)["status"], "armed")


class RepoPeersCliTests(LeaseCliCase):
    def test_lists_armed_peers_in_the_same_repo_only(self):
        self.put_lease("s-x", number=2)
        self.put_lease("s-x", number=3, status="closed")
        self.put_lease("s-x", number=4, repo="other")
        self.put_lease("s-x", number=1)
        code, out, _ = run("--repo-peers", REF)
        self.assertEqual((code, json.loads(out)), (0, ["o/r#2"]))


class PushLockCliTests(LeaseCliCase):
    def test_second_session_is_busy_and_cannot_release(self):
        a, b = self.session("s-a"), self.session("s-b")
        self.assertEqual(run("--push-lock", "take", REF, "--session-dir", a)[:2], (0, "taken"))
        code, _, err = run("--push-lock", "take", REF, "--session-dir", b)
        self.assertEqual(code, 1)
        self.assertEqual(err, "pr-watch: busy")
        self.assertEqual(run("--push-lock", "release", REF, "--session-dir", b)[0], 0)
        self.assertEqual(pw_paths.push_lock_path("o", "r").read_text(encoding="utf-8"), "s-a")
        run("--push-lock", "release", REF, "--session-dir", a)
        self.assertFalse(pw_paths.push_lock_path("o", "r").exists())
        self.assertEqual(run("--push-lock", "take", REF, "--session-dir", b)[:2], (0, "taken"))

    def test_lock_older_than_300_seconds_is_taken(self):
        self.assertTrue(lease.take_push_lock("o", "r", "s-a", 1_000.0))
        path = pw_paths.push_lock_path("o", "r")
        os.utime(path, (1_000.0, 1_000.0))
        self.assertFalse(lease.take_push_lock("o", "r", "s-b", 1_300.0))
        self.assertTrue(lease.take_push_lock("o", "r", "s-b", 1_301.0))
        self.assertEqual(path.read_text(encoding="utf-8"), "s-b")

    def test_holder_retaking_its_own_push_lock_succeeds(self):
        self.assertTrue(lease.take_push_lock("o", "r", "s-a", 1_000.0))
        self.assertTrue(lease.take_push_lock("o", "r", "s-a", 1_010.0))
        self.assertFalse(lease.take_push_lock("o", "r", "s-b", 1_010.0))


if __name__ == "__main__":
    unittest.main()
