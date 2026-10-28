"""Old per-repo watches, session identity and monitor liveness, all read from the process list."""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess

from pw_io import read_json, write_json_atomic
from pw_paths import parse_ref, pr_key, progress_path

STALE_AFTER_SECONDS = 300
CLAUDE_IMAGE = re.compile(r"^claude\.exe", re.IGNORECASE)
MONITOR_FLAG = re.compile(r"(?:^|\s)--monitor(?:\s|$)")
LIST_COMMAND = ("Get-CimInstance Win32_Process | Select ProcessId,ParentProcessId,Name,CommandLine"
                " | ConvertTo-Json -Compress")


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def list_processes() -> list[dict]:
    if os.name != "nt":
        return []
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-Command", LIST_COMMAND],
                              capture_output=True, text=True, encoding="utf-8", timeout=60,
                              creationflags=_no_window())
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


def _canon(text: str) -> str:
    return text.replace('"', "").replace("'", "").replace("/", "\\").lower()


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


def scan(main, claude_pid, procs, now) -> dict:
    state_dir = pathlib.Path(main) / ".pr-autopilot"
    result = {"state": "none", "monitor_pid": None, "owner_pid": None,
              "heartbeat_age": None, "prs": []}
    try:
        watch = read_json(state_dir / "watch.json")
    except FileNotFoundError:
        return result
    owner, repo = str(watch.get("owner", "")), str(watch.get("repo", ""))
    result["prs"] = [pr_key(owner, repo, int(n)) for n in watch.get("prs", {}) if str(n).isdigit()]
    age = _heartbeat_age(state_dir / "watch-heartbeat", now)
    result["heartbeat_age"] = None if age == float("inf") else int(age)
    monitor = old_monitor(main, procs)
    if monitor is None:
        result["state"] = "stale" if age > STALE_AFTER_SECONDS else "live-unknown"
        return result
    result["monitor_pid"] = monitor["pid"]
    result["owner_pid"] = claude_ancestor(monitor["pid"], procs)
    result["state"] = "owned" if result["owner_pid"] == claude_pid else "foreign"
    return result


def import_progress(main, session_dir) -> list[str]:
    import poll

    state_dir = pathlib.Path(main) / ".pr-autopilot"
    watch_path = state_dir / "watch.json"
    watch = read_json(watch_path)
    fields = {*poll.COMMON_START, *poll.AUTHORED_START, *poll.REVIEWED_START}
    imported = []
    for number, entry in watch.get("prs", {}).items():
        owner, repo, n = parse_ref(f"{watch.get('owner', '')}/{watch.get('repo', '')}#{number}")
        target = progress_path(owner, repo, n)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(target, {k: v for k, v in entry.items() if k in fields})
        imported.append(pr_key(owner, repo, n))
    os.replace(watch_path, state_dir / "watch.json.migrated")
    for name in ("watch-heartbeat", "watch-poller.json"):
        (state_dir / name).unlink(missing_ok=True)
    return imported


def identity_ok(claude_pid, my_pid, procs, env) -> str | None:
    if env.get("CLAUDE_CODE_CHILD_SESSION"):
        return "CLAUDE_CODE_CHILD_SESSION is set: this process runs inside a launched claude"
    if not claude_pid:
        return "CLAUDE_PID is not set"
    if claude_pid not in {proc["pid"] for proc in _ancestors(my_pid, procs)}:
        return f"CLAUDE_PID {claude_pid} is not an ancestor of this process"
    return None


def leftover_monitors(session_dir, claude_pid, procs) -> list[int]:
    return [proc["pid"] for proc in _monitors_for(procs, "--session-dir", session_dir)
            if claude_ancestor(proc["pid"], procs) != claude_pid]


def monitor_alive(session_dir, claude_pid, procs, now) -> bool:
    mine = [proc for proc in _monitors_for(procs, "--session-dir", session_dir)
            if claude_ancestor(proc["pid"], procs) == claude_pid]
    heartbeat = pathlib.Path(session_dir) / "watch-heartbeat"
    return bool(mine) and _heartbeat_age(heartbeat, now) < STALE_AFTER_SECONDS


def end_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True,
                   creationflags=_no_window())
