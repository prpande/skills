"""Wait for background subagents until one finishes or runs past its time limit.

Usage: python agent_wait.py [--wait SECONDS] [--session ID] [--projects DIR]
       AGENT_ID=DISPATCHED_AT+LIMIT_S ...

Prints one JSON object {"finished": [...], "overdue": [...], "running": [...],
"no_transcript": [...]} and exits 0 as soon as any agent has finished or is
over its limit, or once --wait seconds have passed. "no_transcript" lists the
unfinished agents whose transcript file was never found; their running or
overdue state then rests on the time limit alone. Exit 2 on bad arguments,
including a dispatch time more than a minute in the future (milliseconds, say).
"""

import argparse
import glob
import json
import math
import os
import sys
import time

POLL_SECONDS = 5
FUTURE_TOLERANCE_S = 60


def parse_agent(spec):
    try:
        agent_id, rest = spec.split("=", 1)
        dispatched_at, limit_s = rest.split("+", 1)
        dispatched_at, limit_s = float(dispatched_at), float(limit_s)
        if not (math.isfinite(dispatched_at) and math.isfinite(limit_s)):
            raise ValueError("non-finite")
        return agent_id.strip(), dispatched_at, limit_s
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected AGENT_ID=DISPATCHED_AT+LIMIT_S, got {spec!r}")


def find_transcript(projects_dir, session_id, agent_id):
    pattern = os.path.join(glob.escape(projects_dir), "*", glob.escape(session_id), "subagents",
                           f"agent-{glob.escape(agent_id)}.jsonl")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


TAIL_BYTES = 256 * 1024


def last_record(path):
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - TAIL_BYTES))
        tail = f.read().decode("utf-8", errors="replace")
    for line in reversed(tail.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def is_finished(transcript):
    meta_path = transcript[: -len(".jsonl")] + ".meta.json"
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        if isinstance(meta, dict) and meta.get("finished") is True:
            return True
    except (OSError, ValueError):
        pass
    try:
        record = last_record(transcript)
    except OSError:
        return False
    if not isinstance(record, dict) or record.get("type") != "assistant":
        return False
    message = record.get("message")
    return isinstance(message, dict) and message.get("stop_reason") == "end_turn"


def classify(agents, projects_dir, session_id, now, transcripts):
    result = {"finished": [], "overdue": [], "running": [], "no_transcript": []}
    for agent_id, dispatched_at, limit_s in agents:
        transcript = transcripts.get(agent_id) or find_transcript(projects_dir, session_id, agent_id)
        if transcript:
            transcripts[agent_id] = transcript
        if transcript and is_finished(transcript):
            result["finished"].append(agent_id)
            continue
        if not transcript:
            result["no_transcript"].append(agent_id)
        if now - dispatched_at > limit_s:
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
    if not args.wait >= 0:
        parser.error("--wait must be a number of seconds, 0 or more")

    started = clock()
    for agent_id, dispatched_at, _ in args.agents:
        if dispatched_at > started + FUTURE_TOLERANCE_S:
            parser.error(f"{agent_id}: dispatch time {dispatched_at:.0f} is in the future; pass epoch seconds")
    transcripts = {}
    while True:
        now = clock()
        result = classify(args.agents, args.projects, args.session, now, transcripts)
        if result["finished"] or result["overdue"] or now - started >= args.wait:
            if result["no_transcript"]:
                print("no transcript found for: " + ", ".join(result["no_transcript"]), file=sys.stderr)
            print(json.dumps(result))
            return 0
        sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
