"""Wait for a free agent-cap slot with the agent-cap mod's own wait script.

Usage: python agent_cap_wait.py [--need N|full] [--session ID] [--started MS]

Reads the mod's wait command from wait-command.txt in the agent-cap state
folder (AGENT_CAP_DIR, else ~/.claude/agent-cap), runs it with these
arguments, prints its output and exits with its code: 0 "free: ...", 10
"wait: ..." (still full after at most 170 s; run the command it prints next),
11 "gave-up: ..." (30 minutes in all), 64 bad arguments. A machine without
the mod has no state folder or no wait-command.txt: then, and when the
command cannot run, it prints "free: ..." and exits 0.
"""

import os
import shlex
import subprocess
import sys

POINTER = "wait-command.txt"
PASS_THROUGH_CODES = {0, 10, 11, 64}
TIMEOUT_S = 200


def state_dir(env):
    if env.get("AGENT_CAP_DIR"):
        return env["AGENT_CAP_DIR"].rstrip("\\/")
    return os.path.join(os.path.expanduser("~"), ".claude", "agent-cap")


def wait_command(env):
    try:
        with open(os.path.join(state_dir(env), POINTER), encoding="utf-8") as f:
            line = f.readline().strip()
    except OSError:
        return None
    return shlex.split(line) if line else None


def main(argv=None, env=None, run=subprocess.run):
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    command = wait_command(env)
    if not command:
        print("free: no agent-cap wait command on this machine, so it has no agent cap.")
        return 0
    try:
        done = run(command + list(argv), capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"free: the agent-cap wait command could not run ({e}); going on as if no slot were taken.")
        return 0
    if done.returncode not in PASS_THROUGH_CODES:
        detail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        print(f"free: the agent-cap wait command failed with exit {done.returncode} ({detail[0]}); going on as if no slot were taken.")
        return 0
    print(done.stdout.strip())
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
