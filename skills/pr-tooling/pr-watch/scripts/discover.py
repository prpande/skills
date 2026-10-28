"""Find the PRs a session wrote to, and the local clones it has used, from its own transcript."""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import lease
from pw_io import GhError, no_window, read_json
from pw_paths import NAME, parse_ref, pr_key, repo_slug, session_dir

ORIGIN_CACHE: dict[str, str | None] = {}

SSH_HOSTS: dict[str, str | None] = {}

REMOTE_PATH = r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$"
GITHUB_REMOTE = re.compile(
    r"^(?:(?:https?|ssh|git)://(?:[^@/\s]+@)?(?:www\.)?github\.com(?::\d+)?/|git@github\.com:)"
    + REMOTE_PATH, re.IGNORECASE)
SSH_HOST = r"(?P<host>(?!-)[A-Za-z0-9_.-]+)"
SSH_ALIAS_REMOTE = re.compile(r"^ssh://(?:[^@/\s]+@)?" + SSH_HOST + r"(?::\d+)?/" + REMOTE_PATH)
SCP_ALIAS_REMOTE = re.compile(r"^(?:[^@/\s:]+@)?" + SSH_HOST + ":" + REMOTE_PATH)
GITHUB_SSH_HOSTS = ("github.com", "ssh.github.com")
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
TOKEN = re.compile(r"""\"[^\"]*\"|'[^']*'|\S+""")
REDIRECT = re.compile(r"^\d*>")
BARE_REDIRECT = re.compile(r"^\d*>>?$")
PUSH_LINES = (
    re.compile(r"^[0-9a-f]+\.\.[0-9a-f]+\s+(\S+) -> \1$"),
    re.compile(r"^\+\s+[0-9a-f]+\.\.\.[0-9a-f]+\s+(\S+) -> \1(?: \(forced update\))?$"),
    re.compile(r"^\*\s+\[new branch\]\s+(\S+) -> \1$"),
)
PR_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
CD_COMMANDS = {"cd", "chdir", "pushd", "set-location", "sl", "push-location"}
MSYS_DRIVE = re.compile(r"^/([a-zA-Z])(?=/|$)")
ABSOLUTE = re.compile(r"^(?:[a-zA-Z]:)?[/\\]")
WINDOWS = os.name == "nt"


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


def parse_origin(url, resolve_host=None):
    url = (url or "").strip()
    match = GITHUB_REMOTE.match(url)
    if not match:
        match = SSH_ALIAS_REMOTE.match(url) or SCP_ALIAS_REMOTE.match(url)
        if not match or (resolve_host or ssh_hostname)(match.group("host")) not in GITHUB_SSH_HOSTS:
            return None
    return repo_slug(match.group("owner"), match.group("repo"))


def ssh_hostname(alias):
    """The HostName ssh's own config gives `alias` (`ssh -G` reads it without connecting)."""
    if alias not in SSH_HOSTS:
        try:
            out = subprocess.run(["ssh", "-G", alias], capture_output=True, text=True,
                                 encoding="utf-8", timeout=10, creationflags=no_window())
        except (OSError, subprocess.TimeoutExpired):
            out = None
        lines = out.stdout.splitlines() if out and out.returncode == 0 else []
        SSH_HOSTS[alias] = next((line.split(None, 1)[1].strip().lower() for line in lines
                                 if line.lower().startswith("hostname ")), None)
    return SSH_HOSTS[alias]


def git_output(args):
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8",
                             timeout=20, creationflags=no_window())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def repo_toplevel(path):
    return git_output(["-C", str(path), "rev-parse", "--show-toplevel"]) or None


def result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(i["text"] for i in content
                         if isinstance(i, dict) and isinstance(i.get("text"), str))
    return ""


def split_segments(command):
    segments, current, quote, i = [], [], None, 0
    while i < len(command):
        ch = command[i]
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif command.startswith(("&&", "||"), i):
            segments.append("".join(current))
            current, i = [], i + 2
            continue
        elif ch in ";|\n":
            segments.append("".join(current))
            current, i = [], i + 1
            continue
        current.append(ch)
        i += 1
    segments.append("".join(current))
    return segments


def without_redirects(tokens):
    kept, skip = [], False
    for token in tokens:
        if skip:
            skip = False
        elif BARE_REDIRECT.match(token):
            skip = True
        elif not REDIRECT.match(token):
            kept.append(token)
    return kept


def native_path(path, base):
    """`path` as git here can open it: MSYS `/d/x` becomes `D:/x` on Windows; relative joins `base`."""
    path = os.path.expanduser(path.strip("\"'"))
    if WINDOWS:
        path = MSYS_DRIVE.sub(lambda m: f"{m.group(1).upper()}:", path)
    if base and not ABSOLUTE.match(path):
        path = f"{str(base).rstrip('/')}/{path}"
    return path


def cd_target(tokens):
    """The directory a `cd`, `Set-Location` or `pushd` segment moves to, or None."""
    if not tokens or tokens[0].lower() not in CD_COMMANDS:
        return None
    args = [t for t in without_redirects(tokens[1:]) if not t.startswith("-")]
    return args[0] if args else None


def segment_dirs(command, cwd):
    """(segment, tokens, directory a `cd` earlier in the call moved to, else None) per segment."""
    here = None
    for segment in split_segments(command):
        tokens = TOKEN.findall(segment)
        target = cd_target(tokens)
        if target:
            here = native_path(target, here or cwd)
        yield segment, tokens, here


def parse_git_write(segment):
    """(verb, -C path or None, argument tokens) for a real git commit or push, else None."""
    tokens = TOKEN.findall(segment)
    if tokens[:1] == ["&"]:
        tokens = tokens[1:]
    if not tokens or tokens[0] != "git":
        return None
    dash_c, i = None, 1
    while i < len(tokens) and tokens[i].startswith("-"):
        if tokens[i] in GIT_OPTIONS_WITH_VALUE:
            if tokens[i] == "-C" and i + 1 < len(tokens):
                dash_c = tokens[i + 1].strip("\"'")
            i += 2
        else:
            i += 1
    if i >= len(tokens) or tokens[i] not in ("commit", "push"):
        return None
    args = without_redirects(tokens[i + 1:])
    if "--dry-run" in args or (tokens[i] == "push" and "-n" in args):
        return None
    return tokens[i], dash_c, args


def pushed_branches(args):
    positional = [t.strip("\"'") for t in args if not t.startswith("-")]
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
            if (kind == "assistant" and item.get("type") == "tool_use"
                    and item.get("name") in ("Bash", "PowerShell")):
                command = (item.get("input") or {}).get("command") or ""
                calls[item.get("id")] = call = {"creates_pr": False, "push_repos": []}
                for segment, tokens, here in segment_dirs(command, cwd):
                    if tokens[:3] == ["gh", "pr", "create"]:
                        call["creates_pr"] = True
                    parsed = parse_git_write(segment)
                    if parsed:
                        verb, dash_c, args = parsed
                        where = native_path(dash_c, here or cwd) if dash_c else here
                        git_call((verb, where, args), cwd, branch_now, repo_for, branches, call)
            elif kind == "user" and item.get("type") == "tool_result":
                call = calls.get(item.get("tool_use_id"))
                if call:
                    call_result(call, result_text(item.get("content")), branches, urls)
    return {"branches": branches, "urls": urls, "hints": hints}


def git_call(parsed, cwd, git_branch, repo_for, branches, call):
    verb, dash_c, args = parsed
    repo = repo_for(dash_c or cwd)
    if not repo:
        return
    if git_branch and not dash_c:
        add(branches, (*repo, git_branch), f"{verb}-on-branch")
    if verb == "push":
        call["push_repos"].append(repo)
        for name in pushed_branches(args):
            add(branches, (*repo, name), "push-names-branch")


def call_result(call, text, branches, urls):
    for line in text.splitlines():
        for pattern in PUSH_LINES:
            match = pattern.match(line.strip())
            if match:
                for repo in call["push_repos"]:
                    add(branches, (*repo, match.group(1)), "push-output")
    if call["creates_pr"]:
        for url in PR_URL.findall(text):
            add(urls, url, "pr-create")


def self_authored_open(pr, self_login):
    login = (pr.get("author") or {}).get("login") or ""
    return str(pr.get("state", "")).upper() == "OPEN" and login.lower() == self_login.lower()


def gh_json(gh, args):
    try:
        return json.loads(gh(args))
    except GhError as exc:
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

    by_repo: dict[tuple[str, str], dict[str, list]] = {}
    for (owner, repo, branch), kinds in found["branches"].items():
        by_repo.setdefault((owner, repo), {})[branch] = kinds
    for (owner, repo), branches in by_repo.items():
        listed = gh_json(gh, ["pr", "list", "--repo", repo_slug(owner, repo), "--author", self_login,
                              "--state", "open", "--limit", "1000",
                              "--json", "number,url,headRefName"])
        for pr in listed or []:
            if pr["headRefName"] in branches:
                keep(pr, branches[pr["headRefName"]])
    for url, kinds in found["urls"].items():
        pr = gh_json(gh, ["pr", "view", url, "--json", "number,author,state,headRefName,url"])
        if pr and self_authored_open(pr, self_login):
            keep(pr, kinds)
    return list(prs.values())


def dash_c_paths(record):
    content = (record.get("message") or {}).get("content")
    paths = []
    for item in content if isinstance(content, list) else []:
        if (isinstance(item, dict) and item.get("type") == "tool_use"
                and item.get("name") in ("Bash", "PowerShell")):
            command = (item.get("input") or {}).get("command") or ""
            for _, tokens, here in segment_dirs(command, record.get("cwd")):
                if cd_target(tokens):
                    paths.append(here)
                elif tokens[:2] == ["git", "-C"] and len(tokens) > 2:
                    paths.append(native_path(tokens[2], here or record.get("cwd")))
    return paths


def holder_clone(owner, repo, number, origin_of, toplevel_of=None):
    """The worktree the PR's last lease holder recorded, when it is still a clone of the repo."""
    try:
        held = lease.read_lease(owner, repo, number) or {}
        watch = read_json(session_dir(held["holder"]["session_id"]) / "watch.json")
    except (OSError, ValueError, KeyError, TypeError):
        return None
    entry = (watch.get("prs") or {}).get(pr_key(owner, repo, number)) or {}
    worktree = entry.get("worktree")
    if not worktree or origin_of(worktree) != repo_slug(owner, repo):
        return None
    return (toplevel_of or repo_toplevel)(worktree)


def find_clone(session_id, owner, repo, origin_of, projects=None, toplevel_of=None):
    """The top level of the clone of owner/repo this session used most recently, else None."""
    toplevel_of = toplevel_of or repo_toplevel
    path = find_transcript(session_id, projects)
    if path is None:
        return None
    used = []
    for record in read_records(path):
        used += [p for p in [record.get("cwd"), *dash_c_paths(record)] if p]
    wanted = repo_slug(owner, repo)
    for cwd in dict.fromkeys(reversed(used)):
        top = toplevel_of(cwd) if origin_of(cwd) == wanted else None
        if top:
            return top
    return None
