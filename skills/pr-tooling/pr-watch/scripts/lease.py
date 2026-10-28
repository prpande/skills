"""Per-PR lease: which Claude Code session holds a PR. An external orchestrator reads these files."""
from __future__ import annotations

import json
import os
import subprocess
import time

from pw_io import no_window, read_json, write_json_atomic
from pw_paths import (claim_lock_path, home, iso_utc, lease_path, parse_iso, pr_dir, pr_key,
                      progress_path, push_lock_path)

STALE_AFTER_SECONDS = 300
CLAIM_LOCK_STALE_SECONDS = 60
PUSH_LOCK_STALE_SECONDS = 300
CLOSED_RETENTION_SECONDS = 7 * 24 * 3600
START_TIME_TOLERANCE_SECONDS = 2
FILETIME_UNIX_EPOCH = 116444736000000000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
READ_ATTEMPTS = 3
READ_RETRY_SECONDS = 0.05
TICK_LOCK_ATTEMPTS = 3
STATUS_LOCK_ATTEMPTS = 100


def process_started_at(pid: int) -> float | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return None
        try:
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            ok = kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                          ctypes.byref(kernel), ctypes.byref(user))
            if not ok or exited.dwHighDateTime or exited.dwLowDateTime:
                return None
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != STILL_ACTIVE:
                return None
            ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
            return (ticks - FILETIME_UNIX_EPOCH) / 1e7
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def holder_alive(holder: dict, started_at=process_started_at) -> bool:
    try:
        recorded = parse_iso(holder["pid_started_at"])
        actual = started_at(holder["pid"])
    except (KeyError, TypeError, ValueError):
        return False
    return actual is not None and abs(actual - recorded) <= START_TIME_TOLERANCE_SECONDS


def list_agents() -> list:
    try:
        done = subprocess.run(["claude", "agents", "--json"], capture_output=True, text=True,
                              encoding="utf-8", timeout=20, creationflags=no_window())
        if done.returncode != 0:
            return []
        agents = json.loads(done.stdout)
        return agents if isinstance(agents, list) else []
    except Exception:
        return []


def holder_label(session_id: str, agents=list_agents) -> str:
    for agent in agents():
        if isinstance(agent, dict) and agent.get("sessionId") == session_id and agent.get("name"):
            return agent["name"]
    return session_id


def read_lease(owner: str, repo: str, n: int) -> dict | None:
    try:
        data = read_json(lease_path(owner, repo, n))
    except (FileNotFoundError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("holder"), dict):
        return None
    return data


def _heartbeat_age(data: dict, now: float) -> float:
    try:
        return now - parse_iso(data["heartbeat"])
    except (KeyError, TypeError, ValueError):
        return float("inf")


def _holder_dead(data: dict, now: float, started_at) -> bool:
    stale_after = data.get("stale_after_seconds", STALE_AFTER_SECONDS)
    return _heartbeat_age(data, now) > stale_after and not holder_alive(data["holder"], started_at)


def _refusal(data: dict, now: float, agents) -> str:
    age = _heartbeat_age(data, now)
    when = "never" if age == float("inf") else f"{max(0, int(age))}s ago"
    return f"held by {holder_label(data['holder'].get('session_id', '?'), agents)}, heartbeat {when}"


def _decide(old, session_id, explicit, now, started_at, agents) -> tuple[bool, str]:
    if old is None:
        return True, "claimed"
    if old["holder"].get("session_id") == session_id:
        return True, "reclaimed"
    status = old.get("status")
    if status in ("released", "closed"):
        return True, "claimed"
    if status == "armed" and _holder_dead(old, now, started_at):
        return True, "taken-over"
    if status == "stopped" and explicit and _holder_dead(old, now, started_at):
        return True, "taken-over"
    return False, _refusal(old, now, agents)


def _take_lock(path, now: float, stale_seconds: float = CLAIM_LOCK_STALE_SECONDS) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except PermissionError:
            # Windows refuses the create while the previous lock's delete is still pending.
            continue
        except FileExistsError:
            try:
                age = now - os.stat(path).st_mtime
            except FileNotFoundError:
                continue
            if age <= stale_seconds:
                return False
            aside = path.with_name(f"{path.name}.{os.getpid()}.{time.monotonic_ns()}.stale")
            try:
                os.replace(path, aside)
            except FileNotFoundError:
                continue
            except OSError:
                return False
            try:
                caught_fresh = now - os.stat(aside).st_mtime <= stale_seconds
            except FileNotFoundError:
                continue
            if caught_fresh:
                try:
                    os.link(aside, path)
                except OSError:
                    pass
                aside.unlink(missing_ok=True)
                return False
            aside.unlink(missing_ok=True)
    return False


def claim(owner, repo, n, *, role, holder, explicit, now, started_at=process_started_at,
          agents=list_agents) -> tuple[bool, str]:
    lock = claim_lock_path(owner, repo, n)
    if not _take_lock(lock, now):
        return False, "busy: another claim in progress"
    try:
        try:
            old = read_lease(owner, repo, n)
        except OSError:
            return False, "lease unreadable"
        ok, why = _decide(old, holder["session_id"], explicit, now, started_at, agents)
        if not ok:
            return False, why
        stamp = iso_utc(now)
        write_json_atomic(lease_path(owner, repo, n), {
            "schema": 1, "owner": owner, "repo": repo, "number": n, "role": role,
            "holder": {k: holder.get(k) for k in ("session_id", "pid", "pid_started_at", "poller_pid")},
            "heartbeat": stamp, "stale_after_seconds": STALE_AFTER_SECONDS, "status": "armed",
            "last_head_sha": old.get("last_head_sha") if old else None,
            "pending_since": None, "last_error": None, "updated_at": stamp,
        })
        return True, why
    finally:
        lock.unlink(missing_ok=True)


def take_push_lock(owner, repo, session_id, now) -> bool:
    path = push_lock_path(owner, repo)
    try:
        if path.read_text(encoding="utf-8") == session_id:
            os.utime(path)
            return True
    except OSError:
        pass
    if not _take_lock(path, now, PUSH_LOCK_STALE_SECONDS):
        return False
    path.write_text(session_id, encoding="utf-8")
    return True


def release_push_lock(owner, repo, session_id) -> None:
    path = push_lock_path(owner, repo)
    try:
        if path.read_text(encoding="utf-8") == session_id:
            path.unlink(missing_ok=True)
    except FileNotFoundError:
        pass


def read_with_retry(owner, repo, n) -> dict | None:
    for attempt in range(READ_ATTEMPTS):
        try:
            return read_lease(owner, repo, n)
        except OSError:
            if attempt == READ_ATTEMPTS - 1:
                raise
            time.sleep(READ_RETRY_SECONDS)


def _held_by(owner, repo, n, session_id) -> dict | None:
    data = read_with_retry(owner, repo, n)
    if data is None or data["holder"].get("session_id") != session_id:
        return None
    return data


def _hold_lock(owner, repo, n, now, attempts):
    lock = claim_lock_path(owner, repo, n)
    for attempt in range(attempts):
        if _take_lock(lock, now):
            return lock
        if attempt < attempts - 1:
            time.sleep(READ_RETRY_SECONDS)
    return None


def set_status(owner, repo, n, status, session_id, now) -> bool:
    lock = _hold_lock(owner, repo, n, now, STATUS_LOCK_ATTEMPTS)
    if lock is None:
        raise TimeoutError(f"the lease for {pr_key(owner, repo, n)} stayed locked")
    try:
        data = _held_by(owner, repo, n, session_id)
        if data is None:
            return False
        data.update(status=status, updated_at=iso_utc(now))
        write_json_atomic(lease_path(owner, repo, n), data)
        return True
    finally:
        lock.unlink(missing_ok=True)


def tick_write(owner, repo, n, *, session_id, now, head, pending_since, last_error, poller_pid,
               status="armed") -> str:
    lock = _hold_lock(owner, repo, n, now, TICK_LOCK_ATTEMPTS)
    if lock is None:
        return "busy"
    try:
        data = read_with_retry(owner, repo, n)
        if data is None:
            return "missing"
        if data["holder"].get("session_id") != session_id:
            return "lost"
        if data.get("status") != "armed":
            return "inactive"
        stamp = iso_utc(now)
        data["holder"]["poller_pid"] = poller_pid
        data.update(heartbeat=stamp, last_head_sha=head, pending_since=pending_since,
                    last_error=last_error, status=status, updated_at=stamp)
        write_json_atomic(lease_path(owner, repo, n), data)
        return "written"
    finally:
        lock.unlink(missing_ok=True)


def _lease_numbers(owner, repo) -> list[int]:
    directory = pr_dir(owner, repo)
    if not directory.is_dir():
        return []
    return sorted(int(p.stem) for p in directory.glob("*.json") if p.stem.isdigit())


def armed_peers(owner, repo, exclude_n) -> list[int]:
    peers = []
    for number in _lease_numbers(owner, repo):
        try:
            data = read_with_retry(owner, repo, number)
        except OSError:
            continue
        if (number != exclude_n and data is not None and data.get("status") == "armed"
                and data.get("role") == "authored"):
            peers.append(number)
    return peers


def _expired(owner, repo, n, now) -> bool:
    try:
        data = read_with_retry(owner, repo, n)
    except OSError:
        return False
    if data is None or data.get("status") != "closed":
        return False
    try:
        return now - parse_iso(data["updated_at"]) > CLOSED_RETENTION_SECONDS
    except (KeyError, TypeError, ValueError):
        return False


def _prune_one(owner, repo, n, now) -> bool:
    if not _expired(owner, repo, n, now):
        return False
    lock = _hold_lock(owner, repo, n, now, TICK_LOCK_ATTEMPTS)
    if lock is None:
        return False
    try:
        if not _expired(owner, repo, n, now):
            return False
        lease_path(owner, repo, n).unlink(missing_ok=True)
        progress_path(owner, repo, n).unlink(missing_ok=True)
        return True
    finally:
        lock.unlink(missing_ok=True)


def prune_closed(now) -> int:
    root = home() / "prs"
    if not root.is_dir():
        return 0
    pruned = 0
    for repo_dir in (d for owner_dir in root.iterdir() if owner_dir.is_dir()
                     for d in owner_dir.iterdir() if d.is_dir()):
        owner, repo = repo_dir.parent.name, repo_dir.name
        pruned += sum(_prune_one(owner, repo, number, now) for number in _lease_numbers(owner, repo))
    return pruned
