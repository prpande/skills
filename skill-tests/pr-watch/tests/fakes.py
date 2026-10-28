"""Builders and a fake gh runner for the pr-watch poller tests."""
import atexit
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
import urllib.parse
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "skills" / "pr-tooling" / "pr-watch" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

if "PR_WATCH_HOME" not in os.environ:
    _SAFETY_HOME = tempfile.mkdtemp(prefix="pr-watch-tests-")
    os.environ["PR_WATCH_HOME"] = _SAFETY_HOME
    atexit.register(shutil.rmtree, _SAFETY_HOME, ignore_errors=True)

import lease  # noqa: E402
import poll  # noqa: E402
import pw_paths  # noqa: E402,F401

SELF = "prpande"
ALLOW = ["sonarqube-mbodevme", "mindbody-ado-pipelines", "mergewatch-playlist"]
T0 = "2026-09-10T09:00:00Z"
T1 = "2026-09-10T10:00:00Z"
T2 = "2026-09-10T11:00:00Z"
T3 = "2026-09-10T12:00:00Z"
NOW = 2_000_000_000
ACTIONS = "https://github.com/o/r/actions/runs/34439594621/job/102752575845"
AZURE = ("https://dev.azure.com/mindbody/19477e8d-94b2-4461-9dfc-2f54fa23767d"
         "/_build/results?buildId=3366211")
SONAR = "https://sonarqube.example/dashboard?id=r&pullRequest=1411"


def author(login, typename="User"):
    return {"login": login, "__typename": typename}


def comment(cid, login, at, body="looks off", typename="User"):
    return {"id": cid, "author": author(login, typename), "createdAt": at,
            "updatedAt": at, "body": body}


def thread(tid, comments, resolved=False, path="src/A.cs", line=10, outdated=False):
    return {"id": tid, "isResolved": resolved, "isOutdated": outdated,
            "path": path, "line": line,
            "comments": {"pageInfo": {"hasNextPage": False}, "nodes": list(comments)}}


def review(rid, login, at, state="COMMENTED", body="", oid="h1", typename="User"):
    return {"id": rid, "author": author(login, typename), "state": state,
            "submittedAt": at, "body": body, "commit": {"oid": oid}}


def pull(number=1411, threads=(), comments=(), reviews=(), head="h2",
         author_login=SELF, updated="2026-09-11T10:00:00Z", state="OPEN"):
    return {
        "number": number, "title": f"AB#1552495: slice {number}", "body": "body",
        "url": f"https://github.com/o/r/pull/{number}", "state": state,
        "headRefOid": head, "headRefName": f"branch-{number}", "baseRefName": "main",
        "updatedAt": updated, "author": author(author_login),
        "reviewThreads": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                          "nodes": list(threads)},
        "comments": {"pageInfo": {"hasPreviousPage": False}, "nodes": list(comments)},
        "reviews": {"pageInfo": {"hasPreviousPage": False}, "nodes": list(reviews)},
    }


def pk(number, owner="o", repo="r"):
    return (owner.lower(), repo.lower(), number)


def rk(number, owner="o", repo="r"):
    return pw_paths.pr_key(owner, repo, number)


PR_FIELDS = ("role", "worktree", "branch", "title", "url", "status")


def watch(prs, push_queue=(), owner="o", repo="r", dry_run=False):
    """The view poll.load_view returns; an int key means `owner/repo#N` of the defaults."""
    view = {
        "session_id": "s-1", "claude_pid": None, "self_login": SELF,
        "bot_allowlist": list(ALLOW), "ado_orgs": ["mindbody"], "dry_run": dry_run,
        "push_queue": list(push_queue), "prs": {},
    }
    for ref, role in prs.items():
        o, r, n = pw_paths.parse_ref(ref if isinstance(ref, str) else f"{owner}/{repo}#{ref}")
        view["prs"][pw_paths.pr_key(o, r, n)] = {
            **poll.starting_progress(role), "role": role, "status": "armed",
            "branch": f"branch-{n}", "title": f"AB#1552495: slice {n}",
            "url": f"https://github.com/{o}/{r}/pull/{n}", "owner": o, "repo": r, "number": n}
    return view


def write_session(directory, view):
    """Write `view` as a session directory: watch.json plus one progress file per PR."""
    assert os.environ.get("PR_WATCH_HOME"), "tests must not write to the real pr-watch home"
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    top = {k: v for k, v in view.items() if k != "prs"}
    top.update(channel_id="C0C15VC8Y0Z", origin_worktree="D:/src/r", serialize_pushes=True,
               prs={})
    for key, entry in view["prs"].items():
        top["prs"][key] = {k: entry[k] for k in PR_FIELDS if k in entry}
        progress = {k: v for k, v in entry.items()
                    if k not in PR_FIELDS and k not in ("owner", "repo", "number")}
        path = poll.progress_file(directory, entry["owner"], entry["repo"], entry["number"],
                                  view["dry_run"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(progress), encoding="utf-8")
    (directory / "watch.json").write_text(json.dumps(top), encoding="utf-8")
    return directory


def claim_leases(view, session_id="s-1", now=None):
    now = now if now is not None else NOW
    holder = {"session_id": session_id, "pid": 1, "pid_started_at": pw_paths.iso_utc(now),
              "poller_pid": None}
    for entry in view["prs"].values():
        ok, why = lease.claim(entry["owner"], entry["repo"], entry["number"], role=entry["role"],
                              holder=holder, explicit=True, now=now)
        assert ok, why


class HomeCase(unittest.TestCase):
    """A fresh pr-watch home per test, so leases and progress files never leak between tests."""

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        patcher = mock.patch.dict(os.environ, {"PR_WATCH_HOME": self.home.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("CLAUDE_PID", "CLAUDE_CODE_SESSION_ID"):
            os.environ.pop(name, None)


class FakeGh:
    """Stands in for poll.run_gh; answers only the calls the poller makes."""

    def __init__(self):
        self.prs = {}
        self.pages = {}
        self.compare = {}
        self.user = SELF
        self.fail = set()
        self.fail_heads = False
        self.partial_heads = set()
        self.null_repos = set()
        self.calls = []
        self.rollup = {}
        self.checks = {}
        self.no_checks = set()
        self.base_runs = {}
        self.base_statuses = {}
        self.base_workflow_runs = {}
        self.job_logs = {}
        self.thread_comment_pages = {}
        self.earlier = {}
        self.fail_checks = set()
        self.fail_user = False

    def thread_fetches(self):
        return sum(1 for a in self.calls
                   if a[:2] == ["api", "graphql"] and "reviewThreads" in a[3])

    def heads_requests(self):
        return sum(1 for a in self.calls
                   if a[:2] == ["api", "graphql"] and 'repository(owner: "' in a[3])

    def checks_calls(self):
        return sum(1 for a in self.calls if a[:2] == ["pr", "checks"])

    def __call__(self, args):
        self.calls.append(list(args))
        if args[:2] == ["api", "graphql"]:
            query = args[3][len("query="):]
            pairs = args[4:]
            variables = dict(pairs[i + 1].split("=", 1) for i in range(0, len(pairs), 2))
            if "node(id:" in query:
                page = self.thread_comment_pages[(variables["id"], variables["after"])]
                return json.dumps({"data": {"node": page and {"comments": page}}})
            if "before: $before" in query:
                field = "comments" if "comments(last" in query else "reviews"
                page = self.earlier[(int(variables["n"]), field, variables["before"])]
                return json.dumps({"data": {"repository": {"pullRequest": page and {field: page}}}})
            if "$n" in query:
                n = int(variables["n"])
                key = (variables["owner"].lower(), variables["repo"].lower(), n)
                if key in self.fail:
                    raise poll.GhError(f"fetch of {n} failed")
                if key in self.pages:
                    page = self.pages[key][int(variables.get("after", 0))]
                else:
                    page = self.prs[key]
                return json.dumps({"data": {"repository": {"pullRequest": page}}})
            if self.fail_heads:
                raise poll.GhError("heads query failed")
            data, errors = {}, []
            for chunk in re.split(r"(?=\br\d+: repository\()", query)[1:]:
                alias, owner, name = re.match(
                    r'(r\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)', chunk).groups()
                owner, name = owner.lower(), name.lower()
                if (owner, name) in self.null_repos:
                    data[alias] = None
                    errors.append({"path": [alias], "message": "Could not resolve to a Repository"})
                    continue
                nodes = {}
                for n in map(int, re.findall(r"\bp(\d+): pullRequest", chunk)):
                    key = (owner, name, n)
                    if key not in self.prs:
                        continue
                    p = self.prs[key]
                    node = None if p is None or key in self.partial_heads else {
                        "number": n, "updatedAt": p["updatedAt"],
                        "headRefOid": p["headRefOid"], "state": p["state"]}
                    if node is not None and key in self.rollup:
                        node["commits"] = {"nodes": [{"commit": {
                            "statusCheckRollup": {"state": self.rollup[key]}}}]}
                    if key in self.partial_heads:
                        errors.append({"path": [alias, f"p{n}"], "message": "not found"})
                    nodes[f"p{n}"] = node
                data[alias] = nodes
            if errors:
                raise poll.GhError("GraphQL: not found",
                                   stdout=json.dumps({"data": data, "errors": errors}))
            return json.dumps({"data": data})
        if args[:2] == ["pr", "checks"]:
            n = int(args[2])
            owner, name = args[args.index("--repo") + 1].lower().split("/")
            key = (owner, name, n)
            if key in self.fail_checks:
                raise poll.GhError("HTTP 502: checks unavailable")
            if key in self.no_checks:
                raise poll.GhError("no required checks reported on the 'main' branch")
            return json.dumps(self.checks.get(key, []))
        if args[:2] == ["run", "rerun"]:
            return ""
        path = args[1]
        if "/actions/jobs/" in path and path.endswith("/logs"):
            return self.job_logs[path.split("/actions/jobs/")[1].split("/")[0]]
        if "/actions/runs?head_sha=" in path:
            sha = urllib.parse.unquote(path.split("head_sha=")[1])
            return "".join(f"{suite}\t{name}\n"
                           for suite, name in self.base_workflow_runs.get(sha, []))
        if "/compare/" in path:
            files = self.compare.get(path.split("/compare/")[1], [])
            if files is None and not args[args.index("--jq") + 1].startswith("(.files // [])"):
                raise poll.GhError("jq: error: Cannot iterate over null")
            return "".join(f"{f}\n" for f in files or [])
        if path == "user":
            if self.fail_user:
                raise poll.GhError("HTTP 401: Bad credentials")
            return self.user + "\n"
        if "/commits/" in path:
            tail = path.split("/commits/")[1]
            if not tail.endswith(("/check-runs", "/status")):
                return urllib.parse.unquote(tail) + "\n"  # a ref resolves to itself as its sha
            ref = urllib.parse.unquote(tail.rsplit("/", 1)[0])
            if path.endswith("/check-runs"):
                return "".join("\t".join((*row, "1")[:3]) + "\n"
                               for row in self.base_runs.get(ref, []))
            return "".join(f"{name}\t{value}\n"
                           for name, value in self.base_statuses.get(ref, []))
        if "/pulls/" in path:
            owner, name = path.split("/")[1:3]
            p = self.prs[(owner.lower(), name.lower(), int(path.rsplit("/", 1)[1]))]
            if any(".base.ref" in a for a in args):
                return f"{p['baseRefName']} {p['headRefOid']}\n"
            return p["author"]["login"] + "\n"
        raise AssertionError(f"unexpected gh call: {args}")
