"""Tests for the pr-watch per-PR lease."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

import fakes  # noqa: F401
import lease
import pw_paths

NOW = 1_800_000_000.0
AGENTS = [{"sessionId": "s-1", "name": "[Tag]Name"}]


def holder(session="s-1", pid=100, started=NOW - 5000, poller=200):
    return {"session_id": session, "pid": pid, "pid_started_at": pw_paths.iso_utc(started), "poller_pid": poller}


def alive(h):
    return lambda pid: pw_paths.parse_iso(h["pid_started_at"]) if pid == h["pid"] else None


def dead(pid):
    return None


class LeaseCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"PR_WATCH_HOME": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def put(self, n=1, *, h=None, status="armed", heartbeat=NOW - 30, updated=None, **extra):
        data = {"schema": 1, "owner": "o", "repo": "r", "number": n, "role": "authored",
                "holder": h or holder(), "heartbeat": pw_paths.iso_utc(heartbeat),
                "stale_after_seconds": 300, "status": status, "last_head_sha": "abc",
                "pending_since": None, "last_error": None,
                "updated_at": pw_paths.iso_utc(updated if updated is not None else heartbeat)}
        data.update(extra)
        path = pw_paths.lease_path("o", "r", n)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def claim(self, h, *, explicit=False, started_at=dead, agents=lambda: AGENTS, n=1):
        return lease.claim("o", "r", n, role="authored", holder=h, explicit=explicit,
                           now=NOW, started_at=started_at, agents=agents)


class ClaimTests(LeaseCase):
    def test_claim_fresh_writes_contract_fields(self):
        h = holder()
        ok, why = self.claim(h, started_at=alive(h))
        self.assertEqual((ok, why), (True, "claimed"))
        data = lease.read_lease("o", "r", 1)
        keys = ("schema", "owner", "repo", "number", "role", "status", "stale_after_seconds",
                "pending_since", "last_error")
        self.assertEqual(
            {k: data[k] for k in keys},
            {"schema": 1, "owner": "o", "repo": "r", "number": 1, "role": "authored", "status": "armed",
             "stale_after_seconds": 300, "pending_since": None, "last_error": None})
        self.assertEqual(data["heartbeat"], pw_paths.iso_utc(NOW))
        self.assertEqual(data["updated_at"], pw_paths.iso_utc(NOW))
        self.assertEqual(data["holder"], h)
        self.assertFalse(pw_paths.claim_lock_path("o", "r", 1).exists())

    def test_claim_keeps_last_head_sha(self):
        self.put(status="released")
        self.claim(holder("s-2", pid=300))
        self.assertEqual(lease.read_lease("o", "r", 1)["last_head_sha"], "abc")

    def test_same_session_new_pid_reclaims_even_with_fresh_heartbeat(self):
        old = holder(pid=100)
        self.put(h=old, heartbeat=NOW - 5)
        new = holder(pid=101)
        self.assertEqual(self.claim(new, started_at=alive(old)), (True, "reclaimed"))
        self.assertEqual(lease.read_lease("o", "r", 1)["holder"]["pid"], 101)

    def test_live_other_session_refused_with_label(self):
        other = holder("s-1")
        self.put(h=other, heartbeat=NOW - 30)
        ok, why = self.claim(holder("s-2", pid=300), started_at=alive(other))
        self.assertFalse(ok)
        self.assertIn("[Tag]Name", why)
        self.assertIn("heartbeat 30s ago", why)

    def test_label_falls_back_to_session_id(self):
        self.put(h=holder("s-9"), heartbeat=NOW - 30)
        ok, why = self.claim(holder("s-2", pid=300), started_at=alive(holder("s-9")))
        self.assertFalse(ok)
        self.assertIn("held by s-9", why)

    def test_dead_holder_with_stale_heartbeat_taken(self):
        self.put(heartbeat=NOW - 301)
        self.assertEqual(self.claim(holder("s-2", pid=300)), (True, "claimed"))
        self.assertEqual(lease.read_lease("o", "r", 1)["holder"]["session_id"], "s-2")

    def test_dead_holder_with_fresh_heartbeat_refused(self):
        self.put(heartbeat=NOW - 100)
        ok, why = self.claim(holder("s-2", pid=300))
        self.assertFalse(ok)
        self.assertIn("heartbeat 100s ago", why)

    def test_stale_heartbeat_but_live_process_refused(self):
        other = holder()
        self.put(h=other, heartbeat=NOW - 900)
        ok, _ = self.claim(holder("s-2", pid=300), started_at=alive(other))
        self.assertFalse(ok)

    def test_alive_pid_with_different_start_time_counts_dead(self):
        other = holder()
        self.put(h=other, heartbeat=NOW - 301)
        reused = lambda pid: pw_paths.parse_iso(other["pid_started_at"]) + 3600
        self.assertEqual(self.claim(holder("s-2", pid=300), started_at=reused), (True, "claimed"))

    def test_renamed_exe_holder_still_live(self):
        other = holder()
        self.put(h=other, heartbeat=NOW - 301)
        within_tolerance = lambda pid: pw_paths.parse_iso(other["pid_started_at"]) + 2
        ok, _ = self.claim(holder("s-2", pid=300), started_at=within_tolerance)
        self.assertFalse(ok)

    def test_released_and_closed_claimable(self):
        for status in ("released", "closed"):
            with self.subTest(status=status):
                self.put(status=status, heartbeat=NOW - 5)
                self.assertEqual(self.claim(holder("s-2", pid=300), started_at=alive(holder())),
                                 (True, "claimed"))

    def test_stopped_dead_holder_needs_explicit(self):
        self.put(status="stopped", heartbeat=NOW - 1000)
        ok, _ = self.claim(holder("s-2", pid=300), explicit=False)
        self.assertFalse(ok)
        self.assertEqual(lease.read_lease("o", "r", 1)["holder"]["session_id"], "s-1")
        self.assertEqual(self.claim(holder("s-2", pid=300), explicit=True), (True, "claimed"))

    def test_stopped_live_holder_refused_even_explicit(self):
        other = holder()
        self.put(h=other, status="stopped", heartbeat=NOW - 1000)
        ok, _ = self.claim(holder("s-2", pid=300), explicit=True, started_at=alive(other))
        self.assertFalse(ok)

    def test_garbage_lease_is_unheld(self):
        path = pw_paths.lease_path("o", "r", 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"sch', encoding="utf-8")
        self.assertIsNone(lease.read_lease("o", "r", 1))
        self.assertEqual(self.claim(holder()), (True, "claimed"))

    def test_fresh_claim_lock_is_busy_stale_is_removed(self):
        lock = pw_paths.claim_lock_path("o", "r", 1)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("", encoding="utf-8")
        os.utime(lock, (NOW - 10, NOW - 10))
        self.assertEqual(self.claim(holder()), (False, "busy: another claim in progress"))
        self.assertTrue(lock.exists())
        os.utime(lock, (NOW - 61, NOW - 61))
        self.assertEqual(self.claim(holder()), (True, "claimed"))
        self.assertFalse(lock.exists())

    def test_lock_removed_when_claim_refused(self):
        other = holder()
        self.put(h=other, heartbeat=NOW - 30)
        self.claim(holder("s-2", pid=300), started_at=alive(other))
        self.assertFalse(pw_paths.claim_lock_path("o", "r", 1).exists())


class WriteTests(LeaseCase):
    def test_tick_write_updates_heartbeat_side_fields(self):
        self.put(heartbeat=NOW - 100)
        ok = lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="def",
                              pending_since=pw_paths.iso_utc(NOW - 50), last_error="boom", poller_pid=999)
        self.assertTrue(ok)
        data = lease.read_lease("o", "r", 1)
        self.assertEqual(data["heartbeat"], pw_paths.iso_utc(NOW))
        self.assertEqual(data["last_head_sha"], "def")
        self.assertEqual(data["pending_since"], pw_paths.iso_utc(NOW - 50))
        self.assertEqual(data["last_error"], "boom")
        self.assertEqual(data["holder"]["poller_pid"], 999)
        self.assertEqual(data["holder"]["pid"], 100)
        self.assertEqual(data["status"], "armed")
        self.assertEqual(data["updated_at"], pw_paths.iso_utc(NOW))

    def test_tick_write_can_set_closed(self):
        self.put()
        lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="abc", pending_since=None,
                         last_error=None, poller_pid=None, status="closed")
        self.assertEqual(lease.read_lease("o", "r", 1)["status"], "closed")

    def test_tick_write_refuses_lost_lease(self):
        before = self.put(h=holder("s-2"), heartbeat=NOW - 100)
        ok = lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="def", pending_since=None,
                              last_error=None, poller_pid=1)
        self.assertFalse(ok)
        self.assertEqual(lease.read_lease("o", "r", 1), before)

    def test_tick_write_without_lease_is_false(self):
        self.assertFalse(lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="x",
                                          pending_since=None, last_error=None, poller_pid=1))

    def test_set_status_only_by_holder(self):
        self.put()
        self.assertFalse(lease.set_status("o", "r", 1, "stopped", "s-2", NOW))
        self.assertEqual(lease.read_lease("o", "r", 1)["status"], "armed")
        self.assertTrue(lease.set_status("o", "r", 1, "stopped", "s-1", NOW))
        data = lease.read_lease("o", "r", 1)
        self.assertEqual((data["status"], data["updated_at"]), ("stopped", pw_paths.iso_utc(NOW)))

    def test_set_status_without_lease_is_false(self):
        self.assertFalse(lease.set_status("o", "r", 1, "stopped", "s-1", NOW))


class SweepTests(LeaseCase):
    def test_prune_closed_after_seven_days(self):
        week = 7 * 24 * 3600
        self.put(1, status="closed", updated=NOW - week - 1)
        self.put(2, status="closed", updated=NOW - week + 1)
        self.put(3, status="armed", updated=NOW - 10 * week)
        self.put(4, status="released", updated=NOW - 10 * week)
        for n in (1, 2):
            pw_paths.progress_path("o", "r", n).write_text("{}", encoding="utf-8")
        self.assertEqual(lease.prune_closed(NOW), 1)
        self.assertIsNone(lease.read_lease("o", "r", 1))
        self.assertFalse(pw_paths.progress_path("o", "r", 1).exists())
        self.assertIsNotNone(lease.read_lease("o", "r", 2))
        self.assertTrue(pw_paths.progress_path("o", "r", 2).exists())
        self.assertIsNotNone(lease.read_lease("o", "r", 3))
        self.assertIsNotNone(lease.read_lease("o", "r", 4))

    def test_prune_closed_without_state_dir_is_zero(self):
        self.assertEqual(lease.prune_closed(NOW), 0)

    def test_armed_peers_spans_sessions_excludes_self(self):
        self.put(1, h=holder("s-1"))
        self.put(2, h=holder("s-2"))
        self.put(3, h=holder("s-3"), status="released")
        self.put(10, h=holder("s-1"))
        pw_paths.progress_path("o", "r", 1).write_text("{}", encoding="utf-8")
        self.assertEqual(lease.armed_peers("o", "r", 1), [2, 10])
        self.assertEqual(lease.armed_peers("o", "r", 99), [1, 2, 10])
        self.assertEqual(lease.armed_peers("o", "other", 1), [])


class LabelAndProcessTests(unittest.TestCase):
    def test_holder_label_names_session(self):
        self.assertEqual(lease.holder_label("s-1", agents=lambda: AGENTS), "[Tag]Name")

    def test_holder_label_falls_back_to_id(self):
        self.assertEqual(lease.holder_label("s-9", agents=lambda: AGENTS), "s-9")
        self.assertEqual(lease.holder_label("s-9", agents=lambda: []), "s-9")

    def test_list_agents_returns_empty_on_failure(self):
        with mock.patch.object(lease.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(lease.list_agents(), [])

    def test_list_agents_parses_json(self):
        done = mock.Mock(returncode=0, stdout=json.dumps(AGENTS))
        with mock.patch.object(lease.subprocess, "run", return_value=done) as run:
            self.assertEqual(lease.list_agents(), AGENTS)
        self.assertEqual(run.call_args.args[0], ["claude", "agents", "--json"])

    def test_list_agents_nonzero_exit_is_empty(self):
        done = mock.Mock(returncode=1, stdout="[]")
        with mock.patch.object(lease.subprocess, "run", return_value=done):
            self.assertEqual(lease.list_agents(), [])

    def test_holder_alive_tolerance(self):
        h = holder(started=NOW)
        self.assertTrue(lease.holder_alive(h, started_at=lambda pid: NOW + 2))
        self.assertFalse(lease.holder_alive(h, started_at=lambda pid: NOW + 3))
        self.assertFalse(lease.holder_alive(h, started_at=lambda pid: None))

    @unittest.skipUnless(os.name == "nt", "process creation time is read through kernel32")
    def test_process_started_at_real_process(self):
        started = lease.process_started_at(os.getpid())
        self.assertIsNotNone(started)
        self.assertLessEqual(time.time() - 300, started)
        self.assertLessEqual(started, time.time() + 1)
        self.assertIsNone(lease.process_started_at(0x7FFFFFF0))


if __name__ == "__main__":
    unittest.main()
