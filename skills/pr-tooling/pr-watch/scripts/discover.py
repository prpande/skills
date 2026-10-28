"""Find the PRs a session wrote to, and the local clones it has used, from its own transcript."""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import poll
from pw_paths import NAME, parse_ref, pr_key

ORIGIN_CACHE: dict[str, str | None] = {}

GITHUB_REMOTE = re.compile(r"^(?:https://github\.com/|git@github\.com:)([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
                           re.IGNORECASE)
GIT_WRITE = re.compile(r"""^\s*git\s+((?:-C\s+(?:"[^"]*"|'[^']*'|\S+)\s+|-c\s+\S+\s+)*)"""
                       r"""(commit|push)\b(.*)$""", re.DOTALL)
DASH_C = re.compile(r"""-C\s+("[^"]*"|'[^']*'|\S+)""")
PUSH_LINE = re.compile(r"^[0-9a-f]+\.\.[0-9a-f]+\s+(\S+) -> \1$")
PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
SEGMENT_BREAK = re.compile(r"&&|\|\||[;|\n]")


def projects_root():
    return pathlib.Path.home() / ".claude" / "projects"


def find_transcript(session_id, projects=None):
    if not NAME.match(session_id):
        return None
    root = pathlib.Path(projects) if projects is not None else projects_root()
    found = list(root.glob(f"*/{session_id}.jsonl"))
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def read_records(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                yield record


def origin_of(path):
    key = str(path)
    if key not in ORIGIN_CACHE:
        ORIGIN_CACHE[key] = parse_origin(git_output(["-C", key, "remote", "get-url", "origin"]))
    return ORIGIN_CACHE[key]


def parse_origin(url):
    match = GITHUB_REMOTE.match(url.strip()) if url else None
    return f"{match.group(1)}/{match.group(2)}".lower() if match else None


def git_output(args):
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8",
                             timeout=20, creationflags=poll.no_window())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def repo_toplevel(path):
    return git_output(["-C", str(path), "rev-parse", "--show-toplevel"]) or None


def result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(i.get("text", "") for i in content if isinstance(i, dict))
    return ""


def pushed_branches(rest):
    positional = [t.strip("\"'") for t in rest.split() if not t.startswith("-")]
    names = []
    for spec in positional[1:]:
        name = spec.lstrip("+").rsplit(":", 1)[-1]
        name = name.removeprefix("refs/heads/")
        if name and name != "HEAD" and not name.startswith("refs/"):
            names.append(name)
    return names


def add(found, key, kind):
    kinds = found.setdefault(key, [])
    if kind not in kinds:
        kinds.append(kind)


def evidence(records, origin_of):
    branches: dict[tuple, list] = {}
    urls: dict[str, list] = {}
    hints: set[str] = set()
    calls: dict[str, dict] = {}
    cwd = branch_now = None

    def repo_for(path):
        origin = origin_of(path) if path else None
        return tuple(origin.split("/", 1)) if origin else None

    for record in records:
        cwd = record.get("cwd") or cwd
        branch_now = record.get("gitBranch") or branch_now
        kind = record.get("type")
        if kind == "pr-link":
            if record.get("prUrl"):
                hints.add(record["prUrl"])
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if kind == "assistant" and item.get("type") == "tool_use" \
                    and item.get("name") in ("Bash", "PowerShell"):
                command = (item.get("input") or {}).get("command") or ""
                calls[item.get("id")] = {"command": command, "cwd": cwd}
                for segment in SEGMENT_BREAK.split(command):
                    git_call(segment, cwd, branch_now, repo_for, branches)
            elif kind == "user" and item.get("type") == "tool_result":
                call = calls.get(item.get("tool_use_id"))
                if call:
                    call_result(call, result_text(item.get("content")), repo_for, branches, urls)
    return {"branches": branches, "urls": urls, "hints": hints}


def git_call(segment, cwd, git_branch, repo_for, branches):
    match = GIT_WRITE.match(segment)
    if not match:
        return
    options, verb, rest = match.groups()
    dash_c = DASH_C.search(options)
    repo = repo_for(dash_c.group(1).strip("\"'") if dash_c else cwd)
    if not repo:
        return
    if git_branch and not dash_c:
        add(branches, (*repo, git_branch), f"{verb}-on-branch")
    if verb == "push":
        for name in pushed_branches(rest):
            add(branches, (*repo, name), "push-names-branch")


def call_result(call, text, repo_for, branches, urls):
    dash_c = DASH_C.search(call["command"])
    repo = repo_for(dash_c.group(1).strip("\"'") if dash_c else call["cwd"])
    if repo:
        for line in text.splitlines():
            match = PUSH_LINE.match(line.strip())
            if match:
                add(branches, (*repo, match.group(1)), "push-output")
    if "gh pr create" in call["command"]:
        for url in PR_URL.findall(text):
            add(urls, url, "pr-create")


def self_authored_open(pr, self_login):
    return (str(pr.get("state", "OPEN")).upper() == "OPEN"
            and (pr.get("author") or {}).get("login", self_login).lower() == self_login.lower())


def gh_json(gh, args):
    try:
        return json.loads(gh(args))
    except poll.GhError as exc:
        print(f"pr-watch: {exc}", file=sys.stderr)
        return None


def discover(gh, session_id, self_login, origin_of, projects=None):
    path = find_transcript(session_id, projects)
    if path is None:
        return []
    found = evidence(read_records(path), origin_of)
    prs: dict[str, dict] = {}

    def keep(pr, kinds):
        owner, repo, number = parse_ref(pr["url"])
        entry = prs.setdefault(pr_key(owner, repo, number), {
            "ref": pr_key(owner, repo, number), "url": pr["url"],
            "branch": pr["headRefName"], "evidence": []})
        entry["evidence"].extend(k for k in kinds if k not in entry["evidence"])

    for (owner, repo, branch), kinds in found["branches"].items():
        listed = gh_json(gh, ["pr", "list", "--repo", f"{owner}/{repo}", "--head", branch,
                              "--author", self_login, "--state", "open",
                              "--json", "number,url,headRefName"])
        for pr in listed or []:
            keep(pr, kinds)
    for url, kinds in found["urls"].items():
        pr = gh_json(gh, ["pr", "view", url, "--json", "number,author,state,headRefName,url"])
        if pr and self_authored_open(pr, self_login):
            keep(pr, kinds)
    return list(prs.values())


def clone_candidates(session_id, owner, repo, origin_of, projects=None, toplevel_of=None):
    toplevel_of = toplevel_of or repo_toplevel
    path = find_transcript(session_id, projects)
    if path is None:
        return []
    wanted = f"{owner}/{repo}".lower()
    newest_first = dict.fromkeys(r["cwd"] for r in reversed(list(read_records(path)))
                                 if r.get("cwd"))
    found = []
    for cwd in newest_first:
        top = toplevel_of(cwd) if origin_of(cwd) == wanted else None
        if top and top not in found:
            found.append(top)
    return found
