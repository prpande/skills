"""Builders and a fake gh runner for the pr-watch poller tests."""
import json
import pathlib
import sys
import urllib.parse

REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "skills" / "pr-tooling" / "pr-watch" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import poll  # noqa: E402

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


def watch(prs, push_queue=(), owner="o", repo="r"):
    return {
        "session_id": "s-1", "owner": owner, "repo": repo, "self_login": SELF,
        "channel_id": "C0C15VC8Y0Z", "origin_worktree": "D:/src/r",
        "serialize_pushes": True, "bot_allowlist": list(ALLOW), "ado_orgs": ["mindbody"],
        "prs": {str(n): {"role": role, "posted_reply_ids": [], "settled_ids": [],
                         "escalated_ids": [], "handled_top_level_ids": {}}
                for n, role in prs.items()},
        "push_queue": list(push_queue),
    }


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
                if n in self.fail:
                    raise poll.GhError(f"fetch of {n} failed")
                if n in self.pages:
                    page = self.pages[n][int(variables.get("after", 0))]
                else:
                    page = self.prs[n]
                return json.dumps({"data": {"repository": {"pullRequest": page}}})
            if self.fail_heads:
                raise poll.GhError("heads query failed")
            nodes = {}
            for n, p in self.prs.items():
                if f"p{n}:" in query:
                    node = None if p is None or n in self.partial_heads else {
                        "number": n, "updatedAt": p["updatedAt"],
                        "headRefOid": p["headRefOid"], "state": p["state"]}
                    if node is not None and n in self.rollup:
                        node["commits"] = {"nodes": [{"commit": {
                            "statusCheckRollup": {"state": self.rollup[n]}}}]}
                    nodes[f"p{n}"] = node
            if self.partial_heads:
                body = {"data": {"repository": nodes},
                        "errors": [{"path": ["repository", f"p{n}"], "message": "not found"}
                                   for n in sorted(self.partial_heads)]}
                raise poll.GhError("GraphQL: not found", stdout=json.dumps(body))
            return json.dumps({"data": {"repository": nodes}})
        if args[:2] == ["pr", "checks"]:
            n = int(args[2])
            if n in self.fail_checks:
                raise poll.GhError("HTTP 502: checks unavailable")
            if n in self.no_checks:
                raise poll.GhError("no required checks reported on the 'main' branch")
            return json.dumps(self.checks.get(n, []))
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
            p = self.prs[int(path.rsplit("/", 1)[1])]
            if any(".base.ref" in a for a in args):
                return f"{p['baseRefName']} {p['headRefOid']}\n"
            return p["author"]["login"] + "\n"
        raise AssertionError(f"unexpected gh call: {args}")
