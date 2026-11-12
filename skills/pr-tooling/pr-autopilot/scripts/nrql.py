#!/usr/bin/env python3
"""Run one read-only NRQL query for the pr-autopilot context mapper.

Usage: nrql.py --state <file> "<NRQL>"

The state file counts the queries run for one context map. The query
after the cap is refused. The cap holds for serial or overlapping calls
on one state file. The orchestrator, not the mapper, starts a new map's
count with `--reset`.
Exit codes: 0 ran; 64 rejected, not counted; 65 cap reached or state
file unusable; 66 no account id or no usable newrelic CLI; any other
code is the CLI's own (or 2 for a usage error).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

MAX_QUERIES = 6
MAX_LIMIT = 20
REPLACE_ATTEMPTS = 5
QUERY_TIMEOUT_SECONDS = 120
LOCK_WAIT_SECONDS = 5.0
CLI_SUFFIXES = {"", ".exe"}
EXIT_REJECTED = 64
EXIT_CAP = 65
EXIT_UNAVAILABLE = 66

STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.|'')*'")
FUNCTION_CALL = re.compile(r"\b(?!(?:IN|AND|OR|NOT|LIKE|WHERE)\()\w+\(", re.IGNORECASE)


class LockTimeout(Exception):
    pass


def check_query(query: str) -> str | None:
    """Return why the query is refused, or None when it may run."""
    text = STRING_LITERAL.sub("''", " ".join(query.split()))
    upper = text.upper()
    if not re.match(r"^(SELECT|FROM)\b", upper):
        return "only SELECT queries are allowed"
    if ";" in text:
        return "one statement per call"
    if not re.search(r"\bSINCE\b", upper):
        return "add a SINCE clause (SINCE 7 days ago)"
    facet = re.search(r"\bFACET\b", upper)
    if facet and re.search(r"\bTIMESERIES\b", upper):
        return "FACET with TIMESERIES is not parsed by the CLI; drop one"
    limits = re.findall(r"\bLIMIT\s+(\w+)", upper)
    for limit in limits:
        if not re.fullmatch(r"[0-9]+", limit) or int(limit) > MAX_LIMIT:
            return f"LIMIT must be a number no higher than {MAX_LIMIT}"
    if not limits and (facet or not FUNCTION_CALL.search(text)):
        return f"add LIMIT {MAX_LIMIT} or lower (needed for FACET and raw rows)"
    return None


def account_id(env: dict[str, str], home: pathlib.Path) -> str | None:
    """Read only the account id; the credentials file also holds keys."""
    if env.get("NEW_RELIC_ACCOUNT_ID"):
        return env["NEW_RELIC_ACCOUNT_ID"]
    try:
        profile = json.loads(
            (home / ".newrelic" / "default-profile.json").read_text(encoding="utf-8")
        )
        credentials = json.loads(
            (home / ".newrelic" / "credentials.json").read_text(encoding="utf-8")
        )
        value = credentials[profile]["accountID"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return str(value) if value else None


def load_state(path: pathlib.Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"queries": []}
    if not isinstance(state, dict) or not isinstance(state.get("queries"), list):
        raise ValueError(f"{path} is not a query state file")
    return state


def save_state(path: pathlib.Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
                os.replace(tmp, path)
                return
            except PermissionError:
                # Windows: a scanner or indexer can hold the target briefly.
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(0.1 * (attempt + 1))
    finally:
        tmp.unlink(missing_ok=True)


def lock_path(path: pathlib.Path) -> pathlib.Path:
    return path.with_name(path.name + ".lock")


@contextlib.contextmanager
def state_lock(path: pathlib.Path, wait: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path(path)
    deadline = time.monotonic() + wait
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except (FileExistsError, PermissionError):
            # Windows reports a lock that is being deleted as PermissionError.
            if time.monotonic() >= deadline:
                raise LockTimeout(str(lock))
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def settle_entry(path: pathlib.Path, query: str, outcome, wait: float) -> None:
    """Record the exit of the pending entry for `query`; None removes it."""
    with state_lock(path, wait):
        state = load_state(path)
        pending = {"query": query, "exit": None}
        for index in range(len(state["queries"]) - 1, -1, -1):
            if state["queries"][index] == pending:
                if outcome is None:
                    del state["queries"][index]
                else:
                    state["queries"][index]["exit"] = outcome
                break
        save_state(path, state)


def use_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(
    argv=None,
    *,
    env=None,
    home=None,
    which=shutil.which,
    run=subprocess.run,
    lock_wait=LOCK_WAIT_SECONDS,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", required=True, type=pathlib.Path)
    parser.add_argument("--reset", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("query", nargs="?")
    args = parser.parse_args(argv)
    if args.reset and args.query is not None:
        parser.error("--reset takes no query")
    if not args.reset and args.query is None:
        parser.error("a query is required")
    env = os.environ if env is None else env
    home = pathlib.Path.home() if home is None else home

    if args.reset:
        try:
            save_state(args.state, {"queries": []})
            lock_path(args.state).unlink(missing_ok=True)
        except (OSError, ValueError) as error:
            print(f"state file unusable ({error}); refusing to run", file=sys.stderr)
            return EXIT_CAP
        return 0

    refusal = check_query(args.query)
    if refusal:
        print(f"query rejected, not counted: {refusal}", file=sys.stderr)
        return EXIT_REJECTED

    cli = which("newrelic")
    if cli and pathlib.Path(cli).suffix.lower() not in CLI_SUFFIXES:
        cli = None
    account = account_id(env, home)
    if not cli or not account:
        print("no usable newrelic CLI or account id; skip production signals", file=sys.stderr)
        return EXIT_UNAVAILABLE

    try:
        with state_lock(args.state, lock_wait):
            state = load_state(args.state)
            used = len(state["queries"])
            if used >= MAX_QUERIES:
                print(
                    f"query cap reached: {used} of {MAX_QUERIES} used. "
                    "Write the map from the results you have.",
                    file=sys.stderr,
                )
                return EXIT_CAP
            state["queries"].append({"query": args.query, "exit": None})
            save_state(args.state, state)
    except LockTimeout:
        print("state file busy; refusing to run", file=sys.stderr)
        return EXIT_CAP
    except (OSError, ValueError) as error:
        print(f"state file unusable ({error}); refusing to run", file=sys.stderr)
        return EXIT_CAP

    def settle(outcome) -> None:
        try:
            settle_entry(args.state, args.query, outcome, lock_wait)
        except (OSError, ValueError, LockTimeout) as error:
            print(f"warning: could not update the query count ({error})", file=sys.stderr)

    try:
        result = run(
            [cli, "nrql", "query", "--accountId", account, "--query", args.query],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=QUERY_TIMEOUT_SECONDS,
        )
    except OSError as error:
        print(f"newrelic CLI could not start ({error}); query not run", file=sys.stderr)
        settle(None)
        return EXIT_UNAVAILABLE
    except subprocess.TimeoutExpired:
        print(f"newrelic CLI timed out after {QUERY_TIMEOUT_SECONDS}s; query counted", file=sys.stderr)
        settle("timeout")
        return 1
    sys.stdout.write(result.stdout or "")
    sys.stderr.write(result.stderr or "")
    print(f"[{used + 1} of {MAX_QUERIES} queries used]", file=sys.stderr)
    settle(result.returncode)
    return result.returncode


if __name__ == "__main__":
    use_utf8_output()
    sys.exit(main())
