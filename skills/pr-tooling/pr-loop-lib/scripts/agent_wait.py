"""Wait for background subagents until one finishes or runs past its time limit.

Usage: python agent_wait.py [--wait SECONDS] [--session ID] [--projects DIR]
       AGENT_ID=DISPATCHED_AT+LIMIT_S ...

Prints one JSON object {"finished": [...], "overdue": [...], "running": [...]}
and exits 0 as soon as any agent has finished or is over its limit, or once
--wait seconds have passed. Exit 2 on bad arguments.
"""

import argparse
import glob
import json
import os
import sys
import time

POLL_SECONDS = 5


def parse_agent(spec):
    try:
        agent_id, rest = spec.split("=", 1)
        dispatched_at, limit_s = rest.split("+", 1)
        return agent_id.strip(), float(dispatched_at), float(limit_s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected AGENT_ID=DISPATCHED_AT+LIMIT_S, got {spec!r}")


def find_transcript(projects_dir, session_id, agent_id):
    pattern = os.path.join(glob.escape(projects_dir), "*", glob.escape(session_id), "subagents",
                           f"agent-{glob.escape(agent_id)}.jsonl")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def last_record(path):
    last = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                continue
    return last


def is_finished(transcript):
    meta_path = transcript[: -len(".jsonl")] + ".meta.json"
    try:
        with open(meta_path, encoding="utf-8") as f:
            if json.load(f).get("finished") is True:
                return True
    except (OSError, json.JSONDecodeError):
        pass
    try:
        record = last_record(transcript)
    except OSError:
        return False
    if not record or record.get("type") != "assistant":
        return False
    message = record.get("message") or {}
    if message.get("stop_reason") != "end_turn":
        return False
    content = message.get("content") or []
    return not any(isinstance(part, dict) and part.get("type") == "tool_use" for part in content)


def classify(agents, projects_dir, session_id, now):
    result = {"finished": [], "overdue": [], "running": []}
    for agent_id, dispatched_at, limit_s in agents:
        transcript = find_transcript(projects_dir, session_id, agent_id)
        if transcript and is_finished(transcript):
            result["finished"].append(agent_id)
        elif now - dispatched_at > limit_s:
            result["overdue"].append({"id": agent_id, "elapsed_s": int(now - dispatched_at),
                                      "limit_s": int(limit_s)})
        else:
            result["running"].append(agent_id)
    return result


def main(argv=None, clock=time.time, sleep=time.sleep):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wait", type=float, default=240)
    parser.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    parser.add_argument("--projects", default=os.path.join(os.path.expanduser("~"), ".claude", "projects"))
    parser.add_argument("agents", nargs="+", type=parse_agent)
    args = parser.parse_args(argv)
    if not args.session:
        parser.error("no session id: pass --session or set CLAUDE_CODE_SESSION_ID")

    started = clock()
    while True:
        now = clock()
        result = classify(args.agents, args.projects, args.session, now)
        if result["finished"] or result["overdue"] or now - started >= args.wait:
            print(json.dumps(result))
            return 0
        sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
