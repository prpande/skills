"""Per-PR lease: which Claude Code session holds a PR. An external orchestrator reads these files."""
from __future__ import annotations

import json
import os
import subprocess

from pw_io import read_json, write_json_atomic
from pw_paths import (claim_lock_path, home, iso_utc, lease_path, parse_iso, pr_dir,
                      progress_path)

STALE_AFTER_SECONDS = 300
CLAIM_LOCK_STALE_SECONDS = 60
CLOSED_RETENTION_SECONDS = 7 * 24 * 3600
START_TIME_TOLERANCE_SECONDS = 2
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
FILETIME_UNIX_EPOCH = 116444736000000000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


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
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return None
        try:
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            ok = kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                          ctypes.byref(kernel), ctypes.byref(user))
            if not ok:
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
                              encoding="utf-8", timeout=20, creationflags=NO_WINDOW)
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
    except (OSError, ValueError):
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
    when = "never" if age == float("inf") else f"{int(age)}s ago"
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
        return True, "claimed"
    if status == "stopped" and explicit and _holder_dead(old, now, started_at):
        return True, "claimed"
    return False, _refusal(old, now, agents)


def _take_lock(path, now: float) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            try:
                age = now - os.stat(path).st_mtime
            except FileNotFoundError:
                continue
            if age <= CLAIM_LOCK_STALE_SECONDS:
                return False
            path.unlink(missing_ok=True)
    return False


def claim(owner, repo, n, *, role, holder, explicit, now, started_at=process_started_at,
          agents=list_agents) -> tuple[bool, str]:
    lock = claim_lock_path(owner, repo, n)
    if not _take_lock(lock, now):
        return False, "busy: another claim in progress"
    try:
        old = read_lease(owner, repo, n)
        ok, why = _decide(old, holder["session_id"], explicit, now, started_at, agents)
        if not ok:
            return False, why
        stamp = iso_utc(now)
        write_json_atomic(lease_path(owner, repo, n), {
            "schema": 1, "owner": owner.lower(), "repo": repo.lower(), "number": n, "role": role,
            "holder": {k: holder.get(k) for k in ("session_id", "pid", "pid_started_at", "poller_pid")},
            "heartbeat": stamp, "stale_after_seconds": STALE_AFTER_SECONDS, "status": "armed",
            "last_head_sha": old.get("last_head_sha") if old else None,
            "pending_since": None, "last_error": None, "updated_at": stamp,
        })
        return True, why
    finally:
        lock.unlink(missing_ok=True)


def _held_by(owner, repo, n, session_id) -> dict | None:
    data = read_lease(owner, repo, n)
    if data is None or data["holder"].get("session_id") != session_id:
        return None
    return data


def set_status(owner, repo, n, status, session_id, now) -> bool:
    data = _held_by(owner, repo, n, session_id)
    if data is None:
        return False
    data.update(status=status, updated_at=iso_utc(now))
    write_json_atomic(lease_path(owner, repo, n), data)
    return True


def tick_write(owner, repo, n, *, session_id, now, head, pending_since, last_error, poller_pid,
               status="armed") -> bool:
    data = _held_by(owner, repo, n, session_id)
    if data is None:
        return False
    stamp = iso_utc(now)
    data["holder"]["poller_pid"] = poller_pid
    data.update(heartbeat=stamp, last_head_sha=head, pending_since=pending_since,
                last_error=last_error, status=status, updated_at=stamp)
    write_json_atomic(lease_path(owner, repo, n), data)
    return True


def _lease_numbers(owner, repo) -> list[int]:
    directory = pr_dir(owner, repo)
    if not directory.is_dir():
        return []
    return sorted(int(p.stem) for p in directory.glob("*.json") if p.stem.isdigit())


def armed_peers(owner, repo, exclude_n) -> list[int]:
    peers = []
    for number in _lease_numbers(owner, repo):
        data = read_lease(owner, repo, number)
        if number != exclude_n and data is not None and data.get("status") == "armed":
            peers.append(number)
    return peers


def prune_closed(now) -> int:
    root = home() / "prs"
    if not root.is_dir():
        return 0
    pruned = 0
    for repo_dir in (d for owner_dir in root.iterdir() if owner_dir.is_dir()
                     for d in owner_dir.iterdir() if d.is_dir()):
        for number in _lease_numbers(repo_dir.parent.name, repo_dir.name):
            data = read_lease(repo_dir.parent.name, repo_dir.name, number)
            if data is None or data.get("status") != "closed":
                continue
            try:
                age = now - parse_iso(data["updated_at"])
            except (KeyError, TypeError, ValueError):
                continue
            if age > CLOSED_RETENTION_SECONDS:
                lease_path(repo_dir.parent.name, repo_dir.name, number).unlink(missing_ok=True)
                progress_path(repo_dir.parent.name, repo_dir.name, number).unlink(missing_ok=True)
                pruned += 1
    return pruned
