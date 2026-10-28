"""Old per-repo watches, session identity and monitor liveness, all read from the process list."""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess

from lease import CLOSED_RETENTION_SECONDS, STALE_AFTER_SECONDS
from pw_io import no_window, read_json, write_json_atomic
from pw_paths import lease_path, parse_ref, pr_key, progress_path
from pw_progress import FIELDS as PROGRESS_FIELDS

CLAUDE_IMAGE = re.compile(r"^claude\.exe", re.IGNORECASE)
MONITOR_FLAG = re.compile(r"(?:^|\s)--monitor(?:\s|$)")
LIST_COMMAND = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_Process | Select ProcessId,ParentProcessId,Name,CommandLine"
                " | ConvertTo-Json -Compress")


def list_processes() -> list[dict]:
    if os.name != "nt":
        return []
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-Command", LIST_COMMAND],
                              capture_output=True, text=True, encoding="utf-8", timeout=60,
                              creationflags=no_window())
        if done.returncode != 0:
            raise OSError(done.stderr.strip() or f"powershell exited {done.returncode}")
        rows = json.loads(done.stdout)
    except (subprocess.SubprocessError, ValueError) as exc:
        raise OSError(f"cannot list processes: {exc}") from exc
    if isinstance(rows, dict):
        rows = [rows]
    return [{"pid": row.get("ProcessId"), "ppid": row.get("ParentProcessId"),
             "name": row.get("Name") or "", "cmdline": row.get("CommandLine") or ""}
            for row in rows if isinstance(row, dict)]


MSYS_DRIVE = re.compile(r"(^|[\s=])\\([a-z])(?=\\|\s|$)")


def _canon(text: str) -> str:
    plain = text.replace('"', "").replace("'", "").replace("/", "\\").lower()
    return MSYS_DRIVE.sub(r"\1\2:", plain)


def _monitors_for(procs, option: str, directory) -> list[dict]:
    wanted = re.escape(_canon(str(directory)).rstrip("\\"))
    arg = re.compile(rf"(?:^|\s){re.escape(option)}[\s=]+{wanted}\\?(?:\s|$)")
    found = []
    for proc in procs:
        if not proc["name"].lower().startswith("python"):
            continue
        cmd = _canon(proc["cmdline"])
        if "poll.py" in cmd and MONITOR_FLAG.search(cmd) and arg.search(cmd):
            found.append(proc)
    return found


def old_monitor(main, procs) -> dict | None:
    found = _monitors_for(procs, "--state-dir", pathlib.Path(main) / ".pr-autopilot")
    return found[0] if found else None


def _ancestors(pid, procs):
    by_pid = {proc["pid"]: proc for proc in procs}
    seen = {pid}
    current = by_pid.get(pid)
    while current is not None:
        parent = current["ppid"]
        if parent in seen or parent not in by_pid:
            return
        seen.add(parent)
        current = by_pid[parent]
        yield current


def claude_ancestor(pid, procs) -> int | None:
    for proc in _ancestors(pid, procs):
        if CLAUDE_IMAGE.match(proc["name"]):
            return proc["pid"]
    return None


def _heartbeat_age(path, now: float) -> float:
    try:
        return now - int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return float("inf")


def _old_prs(watch) -> list[tuple[tuple[str, str, int], dict]]:
    owner, repo = watch.get("owner", ""), watch.get("repo", "")
    found = []
    for n, entry in watch.get("prs", {}).items():
        try:
            found.append((parse_ref(f"{owner}/{repo}#{n}"), entry))
        except ValueError:
            continue
    return found


def _unclaimed_after_import(migrated, now) -> list[str]:
    # A lease is pruned only after 7 days closed, so an older import cannot be mistaken for an interrupted one.
    try:
        if now - migrated.stat().st_mtime > CLOSED_RETENTION_SECONDS:
            return []
        watch = read_json(migrated)
    except (OSError, ValueError):
        return []
    if not isinstance(watch, dict):
        return []
    return [pr_key(*ref) for ref, _ in _old_prs(watch) if not lease_path(*ref).exists()]


def scan(main, claude_pid, procs, now) -> dict:
    state_dir = pathlib.Path(main) / ".pr-autopilot"
    result = {"state": "none", "monitor_pid": None, "owner_pid": None,
              "heartbeat_age": None, "prs": []}
    try:
        watch = read_json(state_dir / "watch.json")
    except FileNotFoundError:
        result["prs"] = _unclaimed_after_import(state_dir / "watch.json.migrated", now)
        return result
    result["prs"] = [pr_key(*ref) for ref, _ in _old_prs(watch)]
    age = _heartbeat_age(state_dir / "watch-heartbeat", now)
    result["heartbeat_age"] = None if age == float("inf") else int(age)
    monitor = old_monitor(main, procs)
    if monitor is None:
        result["state"] = "stale" if age > STALE_AFTER_SECONDS else "live-unknown"
        return result
    result["monitor_pid"] = monitor["pid"]
    result["owner_pid"] = claude_ancestor(monitor["pid"], procs)
    owned = claude_pid and result["owner_pid"] == claude_pid
    result["state"] = "owned" if owned else "foreign"
    return result


def import_progress(main) -> list[str]:
    state_dir = pathlib.Path(main) / ".pr-autopilot"
    watch_path = state_dir / "watch.json"
    covered = []
    if watch_path.exists():
        watch = read_json(watch_path)
        for (owner, repo, n), entry in _old_prs(watch):
            target = progress_path(owner, repo, n)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                write_json_atomic(target, {k: v for k, v in entry.items() if k in PROGRESS_FIELDS})
            covered.append(pr_key(owner, repo, n))
        os.replace(watch_path, state_dir / "watch.json.migrated")
        os.utime(state_dir / "watch.json.migrated")
    for name in ("watch-heartbeat", "watch-poller.json"):
        (state_dir / name).unlink(missing_ok=True)
    return covered


def identity_ok(claude_pid, my_pid, procs) -> str | None:
    if not claude_pid:
        return "CLAUDE_PID is not set"
    nearest = claude_ancestor(my_pid, procs)
    if nearest != claude_pid:
        return f"CLAUDE_PID {claude_pid} is not the nearest claude ancestor ({nearest})"
    return None


def leftover_monitors(session_dir, claude_pid, procs) -> list[int]:
    if not claude_pid:
        return []
    return [proc["pid"] for proc in _monitors_for(procs, "--session-dir", session_dir)
            if claude_ancestor(proc["pid"], procs) != claude_pid]


def monitor_alive(session_dir, claude_pid, procs) -> bool:
    """True when this claude runs a poller for `session_dir`; the heartbeat goes stale across a sleep."""
    if not claude_pid:
        return False
    return any(claude_ancestor(proc["pid"], procs) == claude_pid
               for proc in _monitors_for(procs, "--session-dir", session_dir))


def end_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True,
                   creationflags=no_window())
