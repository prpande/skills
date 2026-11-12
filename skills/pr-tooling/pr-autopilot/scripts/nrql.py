#!/usr/bin/env python3
"""Run one read-only NRQL query for the pr-autopilot context mapper.

Usage: nrql.py --state <file> "<NRQL>"

The state file counts the queries run for one context map. The query
after the cap is refused, so the cap holds whatever the caller intends.
Exit codes: 0 ran, 2 query rejected (not counted), 3 cap reached,
4 no account id or no `newrelic` CLI, else the CLI's own exit code.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

MAX_QUERIES = 6
MAX_LIMIT = 20
EXIT_REJECTED = 2
EXIT_CAP = 3
EXIT_UNAVAILABLE = 4


def check_query(query: str) -> str | None:
    """Return why the query is refused, or None when it may run."""
    text = " ".join(query.split())
    upper = text.upper()
    if not re.match(r"^(SELECT|FROM)\b", upper):
        return "only SELECT queries are allowed"
    if ";" in text:
        return "one statement per call"
    if not re.search(r"\bSINCE\b", upper):
        return "add a SINCE clause (SINCE 7 days ago)"
    if re.search(r"\bFACET\b", upper) and re.search(r"\bTIMESERIES\b", upper):
        return "FACET with TIMESERIES is not parsed by the CLI; drop one"
    for limit in re.findall(r"\bLIMIT\s+(\S+)", upper):
        if not limit.isdigit() or int(limit) > MAX_LIMIT:
            return f"LIMIT must be a number no higher than {MAX_LIMIT}"
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
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None, *, env=None, home=None, which=shutil.which, run=subprocess.run) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", required=True, type=pathlib.Path)
    parser.add_argument("query")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    home = pathlib.Path.home() if home is None else home

    refusal = check_query(args.query)
    if refusal:
        print(f"query rejected, not counted: {refusal}", file=sys.stderr)
        return EXIT_REJECTED

    try:
        state = load_state(args.state)
    except ValueError as error:
        print(f"{error}; refusing to run", file=sys.stderr)
        return EXIT_CAP
    used = len(state["queries"])
    if used >= MAX_QUERIES:
        print(
            f"query cap reached: {used} of {MAX_QUERIES} used. "
            "Write the map from the results you have.",
            file=sys.stderr,
        )
        return EXIT_CAP

    cli = which("newrelic")
    account = account_id(env, home)
    if not cli or not account:
        print("no newrelic CLI or account id; skip production signals", file=sys.stderr)
        return EXIT_UNAVAILABLE

    state["queries"].append({"query": args.query, "exit": None})
    save_state(args.state, state)
    result = run(
        [cli, "nrql", "query", "--accountId", account, "--query", args.query],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    state["queries"][-1]["exit"] = result.returncode
    save_state(args.state, state)
    sys.stdout.write(result.stdout or "")
    sys.stderr.write(result.stderr or "")
    print(f"[{used + 1} of {MAX_QUERIES} queries used]", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
