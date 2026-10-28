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
IMPORTED_AT = time.time()
AGENTS = [{"sessionId": "s-1", "name": "[Tag]Name"}]


def holder(session="s-1", pid=100, started=NOW - 5000, poller=200):
    return {"session_id": session, "pid": pid, "pid_started_at": pw_paths.iso_utc(started), "poller_pid": poller}


def alive(h):
    return lambda pid: pw_paths.parse_iso(h["pid_started_at"]) if pid == h["pid"] else None


def dead(pid):
    return None


class FakeClock:
    def __init__(self, on_sleep=None):
        self.t = 0.0
        self.on_sleep = on_sleep

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds
        if self.on_sleep:
            self.on_sleep()


class LeaseCase(unittest.TestCase):
    def fake_clock(self, on_sleep=None):
        clock = FakeClock(on_sleep)
        for name in ("monotonic", "sleep"):
            patcher = mock.patch.object(lease.time, name, getattr(clock, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        return clock

    def no_wait(self):
        patcher = mock.patch.object(lease, "CLAIM_LOCK_WAIT_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

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
        self.assertEqual(self.claim(holder("s-2", pid=300)), (True, "taken-over"))
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
        self.assertEqual(self.claim(holder("s-2", pid=300), started_at=reused), (True, "taken-over"))

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
        self.assertEqual(self.claim(holder("s-2", pid=300), explicit=True), (True, "taken-over"))

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

    def lock_at(self, mtime):
        lock = pw_paths.claim_lock_path("o", "r", 1)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("", encoding="utf-8")
        os.utime(lock, (mtime, mtime))
        return lock

    def test_fresh_claim_lock_is_busy_stale_is_removed(self):
        self.no_wait()
        lock = self.lock_at(NOW - 10)
        self.assertEqual(self.claim(holder()), (False, "busy: another claim in progress"))
        self.assertTrue(lock.exists())
        os.utime(lock, (NOW - 61, NOW - 61))
        self.assertEqual(self.claim(holder()), (True, "claimed"))
        self.assertFalse(lock.exists())

    def test_claim_waits_for_a_claim_in_progress(self):
        lock = self.lock_at(NOW)
        clock = self.fake_clock(on_sleep=lambda: lock.unlink(missing_ok=True))
        self.assertEqual(self.claim(holder()), (True, "claimed"))
        self.assertLess(clock.t, 1)

    def test_claim_breaks_a_lock_left_by_a_dead_claimer_inside_its_wait(self):
        lock = self.lock_at(NOW - 10)
        clock = self.fake_clock()
        self.assertEqual(self.claim(holder()), (True, "claimed"))
        self.assertGreater(clock.t, 50)
        self.assertLess(clock.t, lease.CLAIM_LOCK_WAIT_SECONDS)
        self.assertFalse(lock.exists())

    def test_lock_removed_when_claim_refused(self):
        other = holder()
        self.put(h=other, heartbeat=NOW - 30)
        self.claim(holder("s-2", pid=300), started_at=alive(other))
        self.assertFalse(pw_paths.claim_lock_path("o", "r", 1).exists())

    def test_claim_keeps_github_casing_in_fields_and_lowercases_path(self):
        ok, _ = lease.claim("O", "R", 1, role="authored", holder=holder(), explicit=False, now=NOW,
                            started_at=dead, agents=lambda: AGENTS)
        self.assertTrue(ok)
        self.assertTrue(pw_paths.lease_path("O", "R", 1).exists())
        raw = json.loads(pw_paths.lease_path("o", "r", 1).read_text(encoding="utf-8"))
        self.assertEqual((raw["owner"], raw["repo"]), ("O", "R"))

    def test_rewrites_keep_field_casing(self):
        lease.claim("O", "R", 1, role="authored", holder=holder(), explicit=False, now=NOW,
                    started_at=dead, agents=lambda: AGENTS)
        lease.tick_write("O", "R", 1, session_id="s-1", now=NOW, head="x", pending_since=None,
                         last_error=None, poller_pid=1)
        lease.set_status("O", "R", 1, "stopped", "s-1", NOW)
        raw = json.loads(pw_paths.lease_path("o", "r", 1).read_text(encoding="utf-8"))
        self.assertEqual((raw["owner"], raw["repo"]), ("O", "R"))

    def test_unreadable_lease_refuses_claim_and_leaves_no_lock(self):
        with mock.patch.object(lease, "read_json", side_effect=PermissionError("locked")):
            self.assertEqual(self.claim(holder()), (False, "lease unreadable"))
        self.assertFalse(pw_paths.claim_lock_path("o", "r", 1).exists())

    def test_missing_lease_file_still_means_unheld(self):
        with mock.patch.object(lease, "read_json", side_effect=FileNotFoundError):
            self.assertIsNone(lease.read_lease("o", "r", 1))

    def test_stale_lock_break_loses_race_to_another_claimer_is_busy(self):
        self.no_wait()
        lock = pw_paths.claim_lock_path("o", "r", 1)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("", encoding="utf-8")
        os.utime(lock, (NOW - 61, NOW - 61))
        real_replace = os.replace

        def other_claimer_wins(src, dst):
            if str(dst).endswith(".stale"):
                os.utime(src, (NOW, NOW))
                raise FileNotFoundError
            return real_replace(src, dst)

        with mock.patch.object(lease.os, "replace", side_effect=other_claimer_wins):
            self.assertEqual(self.claim(holder()), (False, "busy: another claim in progress"))
        self.assertTrue(lock.exists())

    def test_stale_lock_break_that_catches_a_fresh_lock_puts_it_back(self):
        self.no_wait()
        lock = pw_paths.claim_lock_path("o", "r", 1)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("", encoding="utf-8")
        os.utime(lock, (NOW - 61, NOW - 61))
        real_replace = os.replace

        def claimer_a_recreated_it(src, dst):
            if str(dst).endswith(".stale"):
                os.utime(src, (NOW, NOW))
            return real_replace(src, dst)

        with mock.patch.object(lease.os, "replace", side_effect=claimer_a_recreated_it):
            self.assertEqual(self.claim(holder()), (False, "busy: another claim in progress"))
        self.assertTrue(lock.exists())
        self.assertEqual(os.stat(lock).st_mtime, NOW)
        self.assertEqual(list(lock.parent.glob("*.stale")), [])

    def test_stale_lock_held_open_is_busy_not_an_error(self):
        self.no_wait()
        lock = pw_paths.claim_lock_path("o", "r", 1)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("", encoding="utf-8")
        os.utime(lock, (NOW - 61, NOW - 61))
        real_replace = os.replace

        def refused(src, dst):
            if str(dst).endswith(".stale"):
                raise PermissionError("held open")
            return real_replace(src, dst)

        with mock.patch.object(lease.os, "replace", side_effect=refused):
            self.assertEqual(self.claim(holder()), (False, "busy: another claim in progress"))
        self.assertTrue(lock.exists())

    def test_stale_lock_is_renamed_aside_then_removed(self):
        lock = pw_paths.claim_lock_path("o", "r", 1)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("", encoding="utf-8")
        os.utime(lock, (NOW - 61, NOW - 61))
        self.assertEqual(self.claim(holder()), (True, "claimed"))
        self.assertEqual(list(lock.parent.glob("*.stale")), [])

    def test_negative_heartbeat_age_is_clamped(self):
        self.put(heartbeat=NOW + 50)
        ok, why = self.claim(holder("s-2", pid=300))
        self.assertFalse(ok)
        self.assertIn("heartbeat 0s ago", why)


class WriteTests(LeaseCase):
    def test_tick_write_updates_heartbeat_side_fields(self):
        self.put(heartbeat=NOW - 100)
        ok = lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="def",
                              pending_since=pw_paths.iso_utc(NOW - 50), last_error="boom", poller_pid=999)
        self.assertEqual(ok, "written")
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
        self.assertEqual(ok, "lost")
        self.assertEqual(lease.read_lease("o", "r", 1), before)

    def test_tick_write_without_lease_is_missing(self):
        self.assertEqual(lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="x",
                                          pending_since=None, last_error=None, poller_pid=1),
                         "missing")

    def test_tick_write_leaves_a_non_armed_lease_alone(self):
        for status in ("released", "stopped", "closed"):
            with self.subTest(status=status):
                self.put(status=status)
                path = pw_paths.lease_path("o", "r", 1)
                before = path.read_bytes()
                result = lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="x",
                                          pending_since=None, last_error=None, poller_pid=1)
                self.assertEqual(result, "inactive")
                self.assertEqual(path.read_bytes(), before)

    def test_tick_write_cannot_close_a_non_armed_lease(self):
        self.put(status="released")
        before = pw_paths.lease_path("o", "r", 1).read_bytes()
        result = lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="x",
                                  pending_since=None, last_error=None, poller_pid=None,
                                  status="closed")
        self.assertEqual(result, "inactive")
        self.assertEqual(pw_paths.lease_path("o", "r", 1).read_bytes(), before)

    def test_set_status_only_by_holder(self):
        self.put()
        self.assertFalse(lease.set_status("o", "r", 1, "stopped", "s-2", NOW))
        self.assertEqual(lease.read_lease("o", "r", 1)["status"], "armed")
        self.assertTrue(lease.set_status("o", "r", 1, "stopped", "s-1", NOW))
        data = lease.read_lease("o", "r", 1)
        self.assertEqual((data["status"], data["updated_at"]), ("stopped", pw_paths.iso_utc(NOW)))

    def test_set_status_without_lease_is_false(self):
        self.assertFalse(lease.set_status("o", "r", 1, "stopped", "s-1", NOW))

    def test_tick_write_retries_transient_read_error(self):
        self.put()
        real = lease.read_json
        calls = []

        def flaky(path, default=None):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("replace in progress")
            return real(path, default)

        with mock.patch.object(lease, "read_json", side_effect=flaky),                 mock.patch.object(lease.time, "sleep"):
            ok = lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="d", pending_since=None,
                                  last_error=None, poller_pid=1)
        self.assertEqual(ok, "written")
        self.assertEqual(len(calls), 3)

    def test_tick_write_skips_while_a_claim_holds_the_lock(self):
        self.put()
        before = pw_paths.lease_path("o", "r", 1).read_bytes()
        lock = pw_paths.claim_lock_path("o", "r", 1)
        lock.touch()
        os.utime(lock, (NOW, NOW))
        with mock.patch.object(lease.time, "sleep"):
            result = lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="x",
                                      pending_since=None, last_error=None, poller_pid=1)
        self.assertEqual(result, "busy")
        self.assertEqual(pw_paths.lease_path("o", "r", 1).read_bytes(), before)

    def test_set_status_raises_when_the_lock_stays_held(self):
        self.put()
        lock = pw_paths.claim_lock_path("o", "r", 1)
        lock.touch()
        os.utime(lock, (NOW, NOW))
        clock = self.fake_clock(on_sleep=lambda: os.utime(lock, (NOW + clock.t, NOW + clock.t)))
        with self.assertRaises(TimeoutError):
            lease.set_status("o", "r", 1, "stopped", "s-1", NOW)
        self.assertEqual(lease.read_lease("o", "r", 1)["status"], "armed")

    def test_set_status_breaks_a_lock_left_by_a_dead_holder(self):
        self.put()
        lock = pw_paths.claim_lock_path("o", "r", 1)
        lock.touch()
        os.utime(lock, (NOW, NOW))
        clock = self.fake_clock()
        self.assertTrue(lease.set_status("o", "r", 1, "stopped", "s-1", NOW))
        self.assertGreater(clock.t, lease.CLAIM_LOCK_STALE_SECONDS)
        self.assertEqual(lease.read_lease("o", "r", 1)["status"], "stopped")

    def test_lease_writes_release_the_lock(self):
        self.put()
        lease.tick_write("o", "r", 1, session_id="s-1", now=NOW, head="x", pending_since=None,
                         last_error=None, poller_pid=1)
        lease.set_status("o", "r", 1, "stopped", "s-1", NOW)
        self.assertFalse(pw_paths.claim_lock_path("o", "r", 1).exists())

    def test_lock_create_refused_by_a_pending_delete_counts_as_busy(self):
        with mock.patch.object(lease.os, "open", side_effect=PermissionError("delete pending")):
            self.assertFalse(lease._take_lock(pw_paths.claim_lock_path("o", "r", 1), NOW))

    def test_set_status_propagates_persistent_read_error(self):
        self.put()
        with mock.patch.object(lease, "read_json", side_effect=PermissionError("locked")),                 mock.patch.object(lease.time, "sleep"):
            with self.assertRaises(PermissionError):
                lease.set_status("o", "r", 1, "stopped", "s-1", NOW)


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

    def test_prune_skips_a_lease_whose_lock_is_held(self):
        self.put(1, status="closed", updated=NOW - 8 * 24 * 3600)
        lock = pw_paths.claim_lock_path("o", "r", 1)
        lock.touch()
        os.utime(lock, (NOW, NOW))
        with mock.patch.object(lease.time, "sleep"):
            self.assertEqual(lease.prune_closed(NOW), 0)
        self.assertIsNotNone(lease.read_lease("o", "r", 1))

    def test_prune_keeps_a_lease_reclaimed_before_the_lock_was_taken(self):
        self.put(1, status="closed", updated=NOW - 8 * 24 * 3600)
        real = lease._hold_lock

        def claim_first(*args):
            self.put(1, status="armed", updated=NOW)
            return real(*args)

        with mock.patch.object(lease, "_hold_lock", side_effect=claim_first):
            self.assertEqual(lease.prune_closed(NOW), 0)
        self.assertEqual(lease.read_lease("o", "r", 1)["status"], "armed")

    def test_armed_peers_retries_then_skips_unreadable(self):
        self.put(2)
        self.put(3)
        real = lease.read_json
        failures = {"left": 2}

        def flaky(path, default=None):
            if path.stem == "2" and failures["left"]:
                failures["left"] -= 1
                raise PermissionError("replace in progress")
            if path.stem == "3":
                raise PermissionError("locked")
            return real(path, default)

        with mock.patch.object(lease, "read_json", side_effect=flaky),                 mock.patch.object(lease.time, "sleep"):
            self.assertEqual(lease.armed_peers("o", "r", 1), [2])

    def test_prune_closed_retries_then_skips_unreadable(self):
        week = 7 * 24 * 3600
        self.put(1, status="closed", updated=NOW - week - 1)
        self.put(2, status="closed", updated=NOW - week - 1)
        real = lease.read_json
        failures = {"left": 2}

        def flaky(path, default=None):
            if path.stem == "1" and failures["left"]:
                failures["left"] -= 1
                raise PermissionError("replace in progress")
            if path.stem == "2":
                raise PermissionError("locked")
            return real(path, default)

        with mock.patch.object(lease, "read_json", side_effect=flaky),                 mock.patch.object(lease.time, "sleep"):
            self.assertEqual(lease.prune_closed(NOW), 1)
        self.assertTrue(pw_paths.lease_path("o", "r", 2).exists())
        self.assertFalse(pw_paths.lease_path("o", "r", 1).exists())

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

    def test_armed_peers_skips_reviewed_leases(self):
        self.put(2, h=holder("s-2"))
        self.put(3, h=holder("s-3"), role="reviewed")
        self.assertEqual(lease.armed_peers("o", "r", 1), [2])


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
        self.assertLess(IMPORTED_AT - 3600, started)
        self.assertLessEqual(started, IMPORTED_AT + 2)
        self.assertIsNone(lease.process_started_at(0x7FFFFFF0))

    @unittest.skipUnless(os.name == "nt", "process creation time is read through kernel32")
    def test_exited_process_with_open_handle_reads_as_gone(self):
        import subprocess
        import sys
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        self.assertIsNone(lease.process_started_at(child.pid))


if __name__ == "__main__":
    unittest.main()
