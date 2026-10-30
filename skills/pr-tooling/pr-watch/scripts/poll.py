"""pr-watch poller.

Deterministic; no model runs here. Reads the session-owned watch.json and
never writes it. The monitor writes watch-poller.json, watch-heartbeat and the lease of
each PR it ticks; --tick-all writes watch-poller.json, the events.jsonl spool and the
leases of every central watch; --report and --reseed write watch-seen.json. Modes are
listed in main().
"""
from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import NamedTuple
import urllib.error
import urllib.parse
import urllib.request

if __name__ == "__main__":
    sys.modules.setdefault("poll", sys.modules[__name__])

import lease
from pw_io import GhError, as_pid, no_window, read_json, write_json_atomic
from pw_paths import (NAME, iso_utc, parse_iso, parse_ref, pr_key, progress_path, repo_slug,
                      sessions_root)
from pw_progress import starting_progress

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
TICK_SECONDS = 60
RECONCILE_SECONDS = 24 * 60 * 60
TICK_EVENT_RETRY_SECONDS = 600
QUEUE_WAIT_SECONDS = 3600
CHECK_FIELDS = "name,state,bucket,link,workflow,completedAt"
FAILED_ROLLUP = ("FAILURE", "ERROR")
FAILED_BASE = ("failure", "error", "timed_out")
ACTIONS_LINK = re.compile(r"^https://github\.com/[^/]+/[^/]+/actions/runs/(\d+)/job/(\d+)")
AZURE_LINK = re.compile(
    r"^https://dev\.azure\.com/([^/]+)/([^/]+)/_build/results\?buildId=(\d+)")
ADO_BUILD = "https://dev.azure.com/{org}/{project}/_apis/build/builds/{build_id}"
ADO_ORG = re.compile(r"^[A-Za-z0-9._-]+$")
ADO_PROJECT = re.compile(r"^[A-Za-z0-9._ %!&()@~-]+$")
POLLER_ERROR_AFTER = 5
REVIEW_QUIET_SECONDS = 30 * 60
NON_REVIEW_BOTS = ("github-actions", "dependabot")
GREEN_BUCKETS = ("pass", "skipping")
PR_FAULTS = (GhError, KeyError, TypeError, ValueError, AttributeError)
CLAUDE_GONE_EXIT = 3
IS_WINDOWS = os.name == "nt"
PROGRESS_SIGNATURE_FIELDS = ("settled_ids", "handled_top_level_ids", "posted_reply_ids",
                             "escalated_ids", "rereviewed_head", "ci_handled")
REPORTED_STATUSES = ("armed", "stopped")
LOG_LINES = 2000
FAILURE_MARK = re.compile(
    r"##\[error\]|\berror [A-Z]{2,5}\d{3,5}\b|\bFailed [\w.]+ \[|\bTest Run Failed\b|npm ERR!")
CONTEXT_BEFORE = 500
CONTEXT_AFTER = 20
GH_TIMEOUT_SECONDS = 120
COMPARE_FILE_CAP = 300
COMMENT_FIELDS = "id author { login __typename } createdAt updatedAt body"
REVIEW_FIELDS = "id author { login __typename } state submittedAt body commit { oid }"
THREAD_COMMENTS_QUERY = (
    "query($id: ID!, $after: String) { node(id: $id) { ... on PullRequestReviewThread { "
    "comments(first: 100, after: $after) { pageInfo { hasNextPage endCursor } "
    "nodes { " + COMMENT_FIELDS + " } } } } }")
EARLIER_QUERY = {
    field: ("query($owner: String!, $repo: String!, $n: Int!, $before: String) { "
            "repository(owner: $owner, name: $repo) { pullRequest(number: $n) { "
            + field + "(last: 100, before: $before) { pageInfo { hasPreviousPage startCursor } "
            "nodes { " + fields + " } } } } }")
    for field, fields in (("comments", COMMENT_FIELDS), ("reviews", REVIEW_FIELDS))}


def classify(author, self_login, allowlist):
    """Return (login, kind) where kind is "me", "bot" or "human"."""
    if not author:
        return "ghost", "bot"
    login = author.get("login") or "ghost"
    if login == self_login:
        return login, "me"
    if (author.get("__typename") == "Bot" or login.endswith("[bot]")
            or login in allowlist):
        return login, "bot"
    return login, "human"


def thread_tail(comments, cut_ids):
    last = -1
    for index, c in enumerate(comments):
        if c["id"] in cut_ids:
            last = index
    return comments[last + 1:]


def top_level_items(pr):
    items = [("issue", c, c["createdAt"]) for c in pr["comments"]["nodes"]]
    items += [("review", r, r.get("submittedAt"))
              for r in pr["reviews"]["nodes"] if (r.get("body") or "").strip()]
    return items


def pending(pr, watch_pr, self_login, allowlist):
    cut = set(watch_pr.get("posted_reply_ids", [])) | set(watch_pr.get("settled_ids", []))
    handled = watch_pr.get("handled_top_level_ids", {})
    threads = []
    for t in pr["reviewThreads"]["nodes"]:
        tail = thread_tail(t["comments"]["nodes"], cut)
        # A tail of only the user's own comments is them talking on their own PR,
        # the same case the top-level filter below drops.
        if tail and any(classify(c["author"], self_login, allowlist)[1] != "me" for c in tail):
            threads.append((t, tail))
    top = [(surface, item) for surface, item, _ in top_level_items(pr)
           if item["id"] not in handled
           and classify(item["author"], self_login, allowlist)[1] != "me"]
    return threads, top


def baseline(pr, self_login, allowlist):
    def kind(author):
        return classify(author, self_login, allowlist)[1]

    settled, stamps = [], []
    for t in pr["reviewThreads"]["nodes"]:
        comments = t["comments"]["nodes"]
        stamps += [c["createdAt"] for c in comments if kind(c["author"]) == "me"]
        if comments:
            last = kind(comments[-1]["author"])
            if last == "me" or (t["isResolved"] and last == "bot"):
                settled.append(comments[-1]["id"])
    stamps += [c["createdAt"] for c in pr["comments"]["nodes"] if kind(c["author"]) == "me"]
    stamps += [r["submittedAt"] for r in pr["reviews"]["nodes"]
               if kind(r["author"]) == "me" and r.get("submittedAt")]
    newest_me = max(stamps) if stamps else None
    head = pr.get("headRefOid")
    handled = {}
    for surface, item, when in top_level_items(pr):
        k = kind(item["author"])
        if newest_me and when and when < newest_me:
            handled[item["id"]] = "baseline"
            continue
        # A review submitted against the current head is feedback on the code as
        # it stands, so a bot review already on the PR when the watch is armed is
        # live work rather than history. Issue comments carry no commit.
        on_head = (surface == "review" and head
                   and (item.get("commit") or {}).get("oid") == head)
        if k == "me" or (k == "bot" and not on_head):
            handled[item["id"]] = "baseline"
    return {"settled_ids": settled, "handled_top_level_ids": handled}


def comment_record(item, surface, self_login, allowlist, thread=None):
    """The pr-loop-lib CommentRecord shape, and nothing else."""
    login, kind = classify(item["author"], self_login, allowlist)
    return {
        "id": item["id"],
        "surface": surface,
        "author": login,
        "author_type": "Bot" if kind == "bot" else "User",
        "created_at": item.get("createdAt") or item.get("submittedAt"),
        "updated_at": item.get("updatedAt"),
        "path": thread["path"] if thread else None,
        "line": thread["line"] if thread else None,
        "body": item.get("body") or "",
        "thread_id": thread["id"] if thread else None,
        "is_resolved": thread["isResolved"] if thread else None,
    }


SLACK_TS = re.compile(r"\d+\.\d+")
SLACK_ID = re.compile(r"[UWB][A-Z0-9]{6,}")
OWN_POST_FOOTER = re.compile(
    r"[*_]?Sent using[*_]?\s*(?:<@U0APMMVNAU8(?:\|[^>]*)?>|@?Claude\b)\s*$")


def load_slack(path):
    try:
        replies = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(replies, list):
        raise ValueError(f"{path} must hold a JSON list of replies")
    for reply in replies:
        if (not isinstance(reply, dict)
                or not all(isinstance(reply.get(k), str) for k in ("ts", "author", "body"))):
            raise ValueError(f"{path}: every reply needs string ts, author and body")
        if not SLACK_TS.fullmatch(reply["ts"]):
            raise ValueError(f"{path}: {reply['ts']!r} is not a Slack ts")
    return replies


def is_own_slack_post(body):
    return bool(OWN_POST_FOOTER.search(body.strip()[-120:]))


def slack_replies_to_handle(replies, human, bots, since):
    since = float(since)
    allowed = {human, *bots}
    return [r for r in replies
            if r["author"] in allowed and float(r["ts"]) >= since
            and not is_own_slack_post(r["body"])]


def slack_record(reply, human):
    return {
        "id": f"slack:{reply['ts']}",
        "surface": "slack",
        "author": reply["author"],
        "author_type": "User" if reply["author"] == human else "Bot",
        "created_at": iso_utc(float(reply["ts"])),
        "updated_at": None,
        "path": None,
        "line": None,
        "body": reply["body"],
        "thread_id": None,
        "is_resolved": None,
    }


def tails_payload(pr, watch_pr, self_login, allowlist, slack=None, slack_human=None):
    posted = set(watch_pr.get("posted_reply_ids", []))
    threads, top = pending(pr, watch_pr, self_login, allowlist)
    out = []
    for t, tail in threads:
        comments = t["comments"]["nodes"]
        start = len(comments) - len(tail)
        out.append({
            "thread_id": t["id"], "path": t["path"], "line": t["line"],
            "is_resolved": t["isResolved"], "is_outdated": t["isOutdated"],
            "follows_watch_reply": start > 0 and comments[start - 1]["id"] in posted,
            "tail_kinds": [classify(c["author"], self_login, allowlist)[1] for c in tail],
            "tail": [comment_record(c, "inline", self_login, allowlist, thread=t)
                     for c in tail],
        })
    return {
        "pr": pr_key_of(pr), "title": pr["title"], "body": pr.get("body") or "",
        "url": pr["url"], "head": pr["headRefOid"], "base": pr["baseRefName"],
        "branch": pr["headRefName"],
        "threads": out,
        "top_level": [comment_record(i, s, self_login, allowlist) for s, i in top]
                     + [slack_record(r, slack_human) for r in slack or []
                        if f"slack:{r['ts']}" not in watch_pr.get("handled_top_level_ids", {})],
    }


def entry_key(entry):
    return pr_key(entry["owner"], entry["repo"], entry["number"])


def pr_key_of(pr):
    return pr_key(*parse_ref(pr["url"]))


def progress_signature(entry):
    return json.dumps([entry.get(field) for field in PROGRESS_SIGNATURE_FIELDS], sort_keys=True)


def progress_file(session_dir, owner, repo, number, dry_run):
    if dry_run:
        return session_dir / "progress" / owner / repo / f"{number}.progress.json"
    return progress_path(owner, repo, number)


def load_view(session_dir, watch=None):
    if watch is None:
        watch = read_json(session_dir / "watch.json")
    dry_run = bool(watch.get("dry_run"))
    prs = {}
    for ref, entry in watch.get("prs", {}).items():
        try:
            owner, repo, number = parse_ref(ref)
            if not isinstance(entry, dict):
                raise ValueError("entry is not an object")
        except ValueError as exc:
            warn(f"watch.json entry {ref!r} skipped: {exc}")
            continue
        key, fault = pr_key(owner, repo, number), None
        try:
            stored = read_json(progress_file(session_dir, owner, repo, number, dry_run), default={})
            if not isinstance(stored, dict):
                raise ValueError("not an object")
        except ValueError as exc:
            warn(f"PR {key}: progress file unreadable: {exc}")
            stored, fault = {}, "progress unreadable"
        prs[key] = {**starting_progress(entry.get("role")), **stored, **entry,
                    "owner": owner, "repo": repo, "number": number, "load_fault": fault}
    return {"self_login": watch["self_login"], "bot_allowlist": watch.get("bot_allowlist", []),
            "ado_orgs": watch.get("ado_orgs", []), "push_queue": watch.get("push_queue", []),
            "session_id": watch.get("session_id"), "claude_pid": watch.get("claude_pid"),
            "dry_run": dry_run, "prs": prs}


def armed_entries(view, dropped=()):
    return {k: e for k, e in view["prs"].items()
            if e.get("status") == "armed" and k not in dropped}


def run_gh(args):
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8",
                             timeout=GH_TIMEOUT_SECONDS, creationflags=no_window())
    except subprocess.TimeoutExpired:
        raise GhError(f"gh timed out after {GH_TIMEOUT_SECONDS}s: gh {' '.join(args[:2])}") from None
    if out.returncode != 0:
        raise GhError(out.stderr.strip()[:400] or f"gh exited {out.returncode}", stdout=out.stdout)
    return out.stdout


def partial_body(exc):
    try:
        body = json.loads(exc.stdout or "")
    except ValueError:
        return None
    return body if isinstance(body, dict) and body.get("data") is not None else None


def graphql(gh, query, variables, allow_partial=False):
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        args += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
    try:
        data = json.loads(gh(args))
    except GhError as exc:
        data = partial_body(exc) if allow_partial else None
        if data is None:
            raise
    if data.get("errors") and not (allow_partial and data.get("data")):
        raise GhError(json.dumps(data["errors"])[:400])
    return data["data"]


def found(value, what):
    if value is None:
        raise GhError(f"{what} not found")
    return value


def fetch_pr(gh, owner, repo, number):
    query = (SCRIPT_DIR / "threads.graphql").read_text(encoding="utf-8")
    missing = f"PR #{number} in {owner}/{repo}"
    pr, threads, after = None, [], None
    while True:
        page = found((graphql(gh, query, {"owner": owner, "repo": repo, "n": number,
                                          "after": after})["repository"] or {})
                     .get("pullRequest"), missing)
        pr = pr or page
        threads += page["reviewThreads"]["nodes"]
        info = page["reviewThreads"]["pageInfo"]
        if not info["hasNextPage"]:
            break
        after = info["endCursor"]
    for t in threads:
        comments = t["comments"]
        while comments["pageInfo"]["hasNextPage"]:
            page = found(graphql(gh, THREAD_COMMENTS_QUERY, {
                "id": t["id"], "after": comments["pageInfo"]["endCursor"]})["node"],
                f"review thread {t['id']}")["comments"]
            comments = {"pageInfo": page["pageInfo"], "nodes": comments["nodes"] + page["nodes"]}
        t["comments"] = comments
    pr = dict(pr, reviewThreads={"pageInfo": {"hasNextPage": False, "endCursor": None},
                                 "nodes": threads})
    for field, query in EARLIER_QUERY.items():
        items = pr[field]
        while items["pageInfo"]["hasPreviousPage"]:
            page = found((graphql(gh, query, {
                "owner": owner, "repo": repo, "n": number,
                "before": items["pageInfo"]["startCursor"]})["repository"] or {})
                .get("pullRequest"), missing)[field]
            items = {"pageInfo": page["pageInfo"], "nodes": page["nodes"] + items["nodes"]}
        pr[field] = items
    return pr


def tick_query(groups):
    parts, aliases = [], {}
    for index, ((owner, repo), numbers) in enumerate(sorted(groups.items())):
        if not (NAME.match(owner) and NAME.match(repo)):
            raise ValueError(f"unsafe owner/repo: {owner}/{repo}")
        fields = " ".join(
            f"p{int(n)}: pullRequest(number: {int(n)}) {{ number updatedAt headRefOid state "
            f"baseRefName mergeable mergeStateStatus reviewDecision "
            f"commits(last: 1) {{ nodes {{ commit {{ statusCheckRollup {{ state }} }} }} }} }}"
            for n in numbers)
        aliases[f"r{index}"] = (owner, repo)
        parts.append(f'r{index}: repository(owner: "{owner}", name: "{repo}") {{ {fields} }}')
    return f"query {{ {' '.join(parts)} }}", aliases


def my_threads(pr, self_login, allowlist):
    return [t for t in pr["reviewThreads"]["nodes"]
            if t["comments"]["nodes"]
            and classify(t["comments"]["nodes"][0]["author"], self_login, allowlist)[1] == "me"]


def my_review_head(pr, self_login, allowlist):
    mine = [r for r in pr["reviews"]["nodes"]
            if classify(r["author"], self_login, allowlist)[1] == "me"
            and r.get("submittedAt") and r.get("commit")]
    return max(mine, key=lambda r: r["submittedAt"])["commit"]["oid"] if mine else None


def replies_after_me(thread, self_login, allowlist):
    comments = thread["comments"]["nodes"]
    mine = [i for i, c in enumerate(comments)
            if classify(c["author"], self_login, allowlist)[1] == "me"]
    if not mine:
        return []
    return [c for c in comments[mine[-1] + 1:]
            if classify(c["author"], self_login, allowlist)[1] != "me"]


def changed_files(gh, owner, repo, old, new):
    out = gh(["api", f"repos/{repo_slug(owner, repo)}/compare/{old}...{new}", "--paginate",
              "--jq", "(.files // [])[].filename"])
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def rollup_state(node):
    commits = (node.get("commits") or {}).get("nodes") or []
    if not commits:
        return None
    return ((commits[0].get("commit") or {}).get("statusCheckRollup") or {}).get("state")


def required_checks(gh, repo_slug, number):
    try:
        out = gh(["pr", "checks", str(number), "--repo", repo_slug, "--required",
                  "--json", CHECK_FIELDS])
    except GhError as exc:
        if "no required checks reported" in str(exc) or "no checks reported" in str(exc):
            return []
        raise
    return json.loads(out or "[]")


def check_platform(link):
    link = link or ""
    match = ACTIONS_LINK.match(link)
    if match:
        return {"platform": "github-actions", "run_id": match[1], "job_id": match[2]}
    match = AZURE_LINK.match(link)
    if match:
        return {"platform": "azure-pipelines", "org": match[1], "project": match[2],
                "build_id": match[3]}
    return {"platform": "other"}


def check_key(check):
    return f"{check.get('workflow') or ''}|{check['name']}"


class Evaluation(NamedTuple):
    event: dict | None
    signature: str
    pending: bool


def evaluate_ci(gh, entry, node, seen, stored):
    """`seen` dedupes (empty on a forced pass); `stored` is kept when nothing is red."""
    if rollup_state(node) not in FAILED_ROLLUP:
        return Evaluation(None, stored, False)
    slug = repo_slug(entry["owner"], entry["repo"])
    red = sorted((c for c in required_checks(gh, slug, entry["number"]) if c.get("bucket") == "fail"),
                 key=check_key)
    if not red:
        return Evaluation(None, stored, False)
    head = node["headRefOid"]
    handled = set(entry.get("ci_handled") or [])
    unhandled = any(f"{head}|{c.get('workflow') or ''}|{c['name']}|{c.get('completedAt') or ''}"
                    not in handled for c in red)
    signature = f"ci:{head}:" + ",".join(
        f"{check_key(c)}|{c.get('completedAt') or ''}" for c in red)
    if signature == seen.get("last_ci_signature"):
        return Evaluation(None, signature, unhandled)
    event = {"pr": entry_key(entry), "role": "authored", "kind": "ci-red", "head": head,
             "checks": [{"name": c["name"], "workflow": c.get("workflow") or "",
                         "completed_at": c.get("completedAt")} for c in red]}
    return Evaluation(event, signature, unhandled)


def evaluate_authored(view, pr, entry, prev):
    threads, top = pending(pr, entry, view["self_login"], view["bot_allowlist"])
    ids = sorted([c["id"] for _, tail in threads for c in tail] + [i["id"] for _, i in top])
    if not ids:
        return Evaluation(None, "", False)
    signature = "pending:" + ",".join(ids)
    if signature == prev.get("last_signature"):
        return Evaluation(None, signature, True)
    event = {"pr": entry_key(entry), "role": "authored", "kind": "pending",
             "threads": [t["id"] for t, _ in threads],
             "comments": [i["id"] for s, i in top if s == "issue"],
             "reviews": [i["id"] for s, i in top if s == "review"]}
    return Evaluation(event, signature, True)


def review_start(view, pr, entry):
    """The head the user last judged the PR at: the last re-review, else their review."""
    return entry.get("rereviewed_head") or my_review_head(
        pr, view["self_login"], view["bot_allowlist"])


def compare_capped(files):
    # GitHub's compare lists at most 300 files, so a full list may omit a flagged file.
    return len(files) >= COMPARE_FILE_CAP


def evaluate_reviewed(view, pr, entry, prev, compare):
    """`compare(old, new)` returns the paths changed between the two heads."""
    me, allow = view["self_login"], view["bot_allowlist"]
    key = entry_key(entry)
    threads = my_threads(pr, me, allow)
    if not threads:
        return Evaluation(None, "", False)
    replied = {t["id"]: replies_after_me(t, me, allow) for t in threads}
    replies = [c for thread_replies in replied.values() for c in thread_replies]
    escalated = set(entry.get("escalated_ids") or [])
    answered = all(c["id"] in escalated for c in replies)
    if answered and all(t["isResolved"] for t in threads):
        if prev.get("last_signature") == "settled":
            return Evaluation(None, "settled", False)
        return Evaluation({"pr": key, "role": "reviewed", "kind": "settled"}, "settled", False)
    old, new = review_start(view, pr, entry), pr["headRefOid"]
    author = (pr.get("author") or {}).get("login")
    reply_ids = sorted(c["id"] for c in replies)
    author_replied = any((c["author"] or {}).get("login") == author for c in replies)
    if old and old != new:
        signature = f"head:{new}:" + ",".join(reply_ids)
        files = set(compare(old, new))
        touches = compare_capped(files) or any(t["path"] in files for t in threads)
        review_pending = touches or author_replied or not answered
        if signature == prev.get("last_signature") or not (touches or author_replied):
            return Evaluation(None, signature, review_pending)
        event = {"pr": key, "role": "reviewed", "kind": "head-moved",
                 "old_head": old, "new_head": new, "touches_my_findings": touches,
                 "author_replied": author_replied}
        return Evaluation(event, signature, review_pending)
    review_pending = not answered
    if not replies:
        return Evaluation(None, "", review_pending)
    signature = "reply:" + ",".join(reply_ids)
    if signature == prev.get("last_signature"):
        return Evaluation(None, signature, review_pending)
    event = {"pr": key, "role": "reviewed", "kind": "reply",
             "threads": [tid for tid, thread_replies in replied.items() if thread_replies]}
    return Evaluation(event, signature, review_pending)


def warn(message):
    print(f"pr-watch poller: {message}", file=sys.stderr, flush=True)


def retry_gate(retry_after, key, prev, now, force):
    """(forced, seen, due-and-unspent) for one branch's slice of a shared retry_after."""
    due = isinstance(retry_after, int) and retry_after <= now
    retry = due and retry_after != prev.get(key)
    forced = force or retry
    return forced, ({} if forced else prev), retry


def retry_spend(retry_after, retry, failed, prev, key):
    """The value to store under `key`: spent (this retry_after) once, else kept."""
    return retry_after if retry and not failed else prev.get(key)


def pr_fault(poller, key, exc):
    warn(f"PR {key}: {type(exc).__name__}: {exc}")
    poller["errors"][key] = "check failed"


def tick_pr(gh, view, poller, key, node, now, force, events):
    prs, closed = poller["prs"], poller["closed"]
    entry = view["prs"][key]
    poller["heads"][key] = node["headRefOid"]
    if node["state"] != "OPEN":
        events.append({"pr": key, "kind": "closed", "state": node["state"]})
        closed.append(key)
        prs.pop(key, None)
        return
    prev = prs.get(key, {})
    rollup = rollup_state(node)
    retry_after = entry.get("retry_after")
    forced, seen, retry_review = retry_gate(retry_after, "retried_at", prev, now, force)
    ci_forced, ci_seen, retry_ci = retry_gate(retry_after, "ci_retried_at", prev, now, force)
    progress_sig = progress_signature(entry)
    moved = (node["updatedAt"] != prev.get("updated_at")
             or node["headRefOid"] != prev.get("last_head")
             or progress_sig != prev.get("progress_sig"))
    ci_moved = (node["headRefOid"] != prev.get("last_head")
                or rollup != prev.get("last_rollup") or rollup in FAILED_ROLLUP)
    if not (moved or ci_moved or forced or ci_forced):
        return
    authored = entry["role"] == "authored"
    signature = prev.get("last_signature", "")
    ci_signature = prev.get("last_ci_signature", "")
    review_pending = prev.get("review_pending", False)
    ci_pending = prev.get("ci_pending", False) if authored else False
    review_event = ci_event = None
    review_failed = ci_failed = False
    compared = prev.get("compared")

    def compare(old, new):
        nonlocal compared
        if not compared or compared[:2] != [old, new]:
            compared = [old, new, changed_files(gh, entry["owner"], entry["repo"], old, new)]
        return compared[2]

    if moved or forced:
        try:
            pr = fetch_pr(gh, entry["owner"], entry["repo"], entry["number"])
            if authored:
                review_event, signature, review_pending = evaluate_authored(view, pr, entry, seen)
            else:
                review_event, signature, review_pending = evaluate_reviewed(
                    view, pr, entry, seen, compare)
        except PR_FAULTS as exc:
            pr_fault(poller, key, exc)
            review_failed = True
    if authored and (ci_moved or ci_forced):
        try:
            ci_event, ci_signature, ci_pending = evaluate_ci(
                gh, entry, node, ci_seen, ci_signature)
        except PR_FAULTS as exc:
            pr_fault(poller, key, exc)
            ci_failed = True
    events += [e for e in (review_event, ci_event) if e]
    if review_failed:
        if ci_event:
            prs[key] = dict(prev, last_ci_signature=ci_signature)
        return
    pending_since = (prev.get("pending_since") or now) if review_pending or ci_pending else None
    new_entry = {"updated_at": node["updatedAt"], "last_head": node["headRefOid"],
                 "last_signature": signature, "last_rollup": rollup,
                 "last_ci_signature": ci_signature, "review_pending": review_pending,
                 "ci_pending": ci_pending, "pending_since": pending_since,
                 "progress_sig": progress_sig}
    if compared:
        new_entry["compared"] = compared
    # Spent independently per branch, so a standing CI-only failure does not
    # keep re-forcing the unchanged review branch too.
    retried_at = retry_spend(retry_after, retry_review, review_failed, prev, "retried_at")
    if retried_at is not None:
        new_entry["retried_at"] = retried_at
    if authored:
        ci_retried_at = retry_spend(retry_after, retry_ci, ci_failed, prev, "ci_retried_at")
        if ci_retried_at is not None:
            new_entry["ci_retried_at"] = ci_retried_at
    prs[key] = new_entry


def bot_activity_times(pr, self_login, allowlist):
    """Epoch seconds of every comment and review a reviewer bot left on the PR."""
    def is_review_bot(author):
        login, kind = classify(author, self_login, allowlist)
        return kind == "bot" and login.lower().removesuffix("[bot]") not in NON_REVIEW_BOTS

    times = []
    comments = [c for t in pr["reviewThreads"]["nodes"] for c in t["comments"]["nodes"]]
    for c in comments + pr["comments"]["nodes"]:
        if is_review_bot(c["author"]):
            times += [parse_iso(c["createdAt"]), parse_iso(c["updatedAt"])]
    for r in pr["reviews"]["nodes"]:
        if is_review_bot(r["author"]) and r.get("submittedAt"):
            times.append(parse_iso(r["submittedAt"]))
    return times


def human_reviewed(pr, self_login, allowlist):
    """True when a human other than the user left a submitted review or an inline comment."""
    def human(author):
        return classify(author, self_login, allowlist)[1] == "human"

    if any(human(r["author"]) and r.get("state") != "PENDING" for r in pr["reviews"]["nodes"]):
        return True
    return any(human(c["author"]) for t in pr["reviewThreads"]["nodes"]
               for c in t["comments"]["nodes"])


def head_commit_time(pr):
    nodes = (pr.get("commits") or {}).get("nodes") or [{}]
    stamp = (nodes[0].get("commit") or {}).get("committedDate")
    return parse_iso(stamp) if stamp else None


def review_blockers(gh, view, pr, entry, now):
    """What keeps an authored PR from being ready for human review; empty means ready."""
    me, allow = view["self_login"], view["bot_allowlist"]
    blockers = []
    if entry.get("role") != "authored":
        return ["not-authored"]
    if entry.get("review_ask") is not None:
        blockers.append("already-asked")
    if pr["state"] != "OPEN":
        blockers.append("not-open")
    if pr.get("isDraft"):
        blockers.append("draft")
    if any(not t["isResolved"] for t in pr["reviewThreads"]["nodes"]):
        blockers.append("unresolved-threads")
    threads, top = pending(pr, entry, me, allow)
    if threads or top:
        blockers.append("fix-pending")
    key = entry_key(entry)
    if (key in view.get("push_queue", []) or entry.get("queued_head")
            or entry.get("ci_rerun_queued")):
        blockers.append("fix-queued")
    bot_times = bot_activity_times(pr, me, allow)
    if not bot_times:
        blockers.append("no-bot-review")
    elif now - max(bot_times) < REVIEW_QUIET_SECONDS:
        blockers.append("bot-active")
    pushed = head_commit_time(pr)
    if pushed is None or now - pushed < REVIEW_QUIET_SECONDS:
        blockers.append("recent-push")
    if human_reviewed(pr, me, allow):
        blockers.append("human-reviewed")
    if not blockers:
        checks = required_checks(gh, repo_slug(entry["owner"], entry["repo"]), entry["number"])
        rollup = rollup_state(pr)
        if rollup != "SUCCESS" or any(c.get("bucket") not in GREEN_BUCKETS for c in checks):
            blockers.append("checks-not-green")
    return blockers


def review_ready_payload(gh, view, entry, pr, now):
    blockers = review_blockers(gh, view, pr, entry, now)
    return {"pr": entry_key(entry), "head": pr["headRefOid"], "ready": not blockers,
            "blockers": blockers}


def check_review_ready(gh, view, poller, key, node, now, force, events):
    """Emit review-ready once per head when a quiet, green authored PR may be asked about."""
    entry = view["prs"][key]
    state = poller.setdefault("review", {}).setdefault(key, {})
    head, stamp = node["headRefOid"], node["updatedAt"]
    if (entry["role"] != "authored" or entry.get("review_ask") is not None
            or rollup_state(node) != "SUCCESS"
            or now - parse_iso(stamp) < REVIEW_QUIET_SECONDS):
        return
    if not force and (state.get("checked") == [head, stamp] or state.get("emitted") == head):
        return
    pr = fetch_pr(gh, entry["owner"], entry["repo"], entry["number"])
    payload = review_ready_payload(gh, view, entry, pr, now)
    state["checked"] = [head, stamp]
    if payload["ready"]:
        state["emitted"] = head
        events.append({"pr": key, "role": "authored", "kind": "review-ready", "head": head})


def merge_blocker(node):
    """`conflicting`, `behind-ready`, or None when mergeable or not yet computed by GitHub."""
    if node.get("mergeable") == "CONFLICTING":
        return "conflicting"
    # GitHub reports BEHIND only where the base requires branches to be up to date;
    # reviewDecision is null where the base requires no review.
    if (node.get("mergeable") == "MERGEABLE" and node.get("mergeStateStatus") == "BEHIND"
            and node.get("reviewDecision") in ("APPROVED", None)
            and rollup_state(node) == "SUCCESS"):
        return "behind-ready"
    return None


def check_mergeability(view, poller, key, node, force, events):
    """Emit `conflicting` or `behind-ready` once per kind and head until the session records it."""
    entry = view["prs"][key]
    kind = merge_blocker(node) if entry["role"] == "authored" else None
    if kind is None:
        return
    mark = f"{kind}:{node['headRefOid']}"
    marks = poller.setdefault("merge", {})
    if entry.get("merge_notified") == mark or (not force and marks.get(key) == mark):
        return
    marks[key] = mark
    events.append({"pr": key, "role": "authored", "kind": kind, "head": node["headRefOid"],
                   "base": node.get("baseRefName")})


def head_groups(prs, closed):
    groups = {}
    for key in sorted(prs):
        entry = prs[key]
        if key not in closed:
            groups.setdefault((entry["owner"], entry["repo"]), []).append(entry["number"])
    return groups


def fetch_heads(gh, groups):
    """(owner, repo) -> {"p<N>": node or None}, or None for a repo the query could not resolve."""
    query, aliases = tick_query(groups)
    data = graphql(gh, query, {}, allow_partial=True)
    return {repo: data.get(alias) for alias, repo in aliases.items()}


def tick_once(gh, view, poller, now, force=False, heads=None):
    """`heads` is a fetch_heads result covering this view; without one the tick queries it."""
    events = []
    poller.setdefault("prs", {})
    closed = poller.setdefault("closed", [])
    closed[:] = [k for k in closed if k in view["prs"]]
    poller.pop("unreachable", None)
    errors = poller["errors"] = {}
    poller["heads"] = {}
    groups = head_groups(view["prs"], closed)
    if groups:
        if heads is None:
            heads = fetch_heads(gh, groups)
        for owner, repo in sorted(groups):
            nodes = heads.get((owner, repo))
            if nodes is None:
                warn(f"{repo_slug(owner, repo)}: repository missing from the heads query; "
                     "skipping its PRs this tick")
                errors.update(dict.fromkeys(
                    (pr_key(owner, repo, n) for n in groups[(owner, repo)]), "repo unreachable"))
                continue
            for n in groups[(owner, repo)]:
                key = pr_key(owner, repo, n)
                node = nodes.get(f"p{n}")
                if node is None:
                    warn(f"PR {key}: null alias in the heads query; skipping this tick")
                    errors[key] = "PR unreachable"
                    continue
                fault = view["prs"][key].get("load_fault")
                if fault and node["state"] == "OPEN":
                    errors[key] = fault
                    poller["heads"][key] = node["headRefOid"]
                    continue
                try:
                    tick_pr(gh, view, poller, key, node, now, force, events)
                except PR_FAULTS as exc:
                    pr_fault(poller, key, exc)
                    continue
                if node["state"] != "OPEN":
                    poller.get("review", {}).pop(key, None)
                    poller.get("merge", {}).pop(key, None)
                    continue
                check_mergeability(view, poller, key, node, force, events)
                try:
                    check_review_ready(gh, view, poller, key, node, now, force, events)
                except PR_FAULTS as exc:
                    warn(f"PR {key}: review-ready check: {type(exc).__name__}: {exc}")
    queue = list(view.get("push_queue", []))
    if not queue:
        poller["last_tick_queue"] = []
    elif (queue != poller.get("last_tick_queue")
          or now - poller.get("last_tick_event", 0) >= TICK_EVENT_RETRY_SECONDS):
        events.append({"kind": "tick", "push_queue": queue})
        poller["last_tick_queue"] = queue
        poller["last_tick_event"] = now
    return events


def missed_prs(before, after, events):
    """PRs among `events` whose signature actually changed since `before`."""
    return sorted(
        key for key in {e["pr"] for e in events if "pr" in e}
        if (after.get(key, {}).get("last_signature"),
            after.get(key, {}).get("last_ci_signature")) != before.get(key))


def claude_identity(session_dir):
    try:
        recorded = read_json(session_dir / "watch.json", default={}).get("claude_pid")
    except (OSError, ValueError):
        recorded = None
    return as_pid(recorded)


def lease_head(owner, repo, number):
    try:
        held = lease.read_lease(owner, repo, number)
    except OSError:
        return None
    return held.get("last_head_sha") if held else None


LEASE_LISTS = ("lease_dropped", "lease_warned")


def lease_lists(poller):
    return tuple(list(poller.get(name, ())) for name in LEASE_LISTS)


def filter_lease_lists(poller, keep):
    """Keep only the keys `keep` accepts in the poller's lease lists; True when a list changed."""
    kept = {name: [k for k in poller.get(name, ()) if keep(k)] for name in LEASE_LISTS}
    changed = any(kept[name] != list(poller.get(name, ())) for name in LEASE_LISTS)
    if changed:
        poller.update(kept)
    return changed


def write_session_leases(view, armed, poller, closed_before, now, *,
                         write_lease=lease.tick_write, central=False):
    filter_lease_lists(poller, armed.__contains__)
    dropped = set(poller.get("lease_dropped", ()))
    warned_missing = set(poller.get("lease_warned", ()))
    silenced, lease_events, unclosed = set(), [], set()
    for key, entry in armed.items():
        if key in closed_before or key in dropped:
            continue
        closing = key in poller["closed"]
        owner, repo, number = entry["owner"], entry["repo"], entry["number"]
        head = poller["heads"].get(key)
        if head is None:
            head = lease_head(owner, repo, number)
        since = poller["prs"].get(key, {}).get("pending_since")
        try:
            result = write_lease(
                owner, repo, number, session_id=view["session_id"], now=now, head=head,
                pending_since=iso_utc(since) if since and not closing else None,
                last_error=poller["errors"].get(key),
                poller_pid=None if central else os.getpid(), status="closed" if closing else "armed",
                central=central)
        except OSError as exc:
            warn(f"lease for {key}: {type(exc).__name__}: {exc}")
            result = "failed"
        if closing and result in ("busy", "failed"):
            # the closed event waits for the next tick, which sees the close again
            unclosed.add(key)
            silenced.add(key)
        elif result == "lost":
            silenced.add(key)
            dropped.add(key)
            try:
                holder = (lease.read_with_retry(owner, repo, number) or {}).get("holder", {})
            except OSError:
                holder = {}
            warn(f"lease for {key} is held by another session")
            lease_events.append({"pr": key, "kind": "lease-lost",
                                 "holder": holder.get("session_id")})
        elif result == "inactive":
            silenced.add(key)
            dropped.add(key)
        elif result == "missing" and key not in warned_missing:
            warned_missing.add(key)
            warn(f"no lease file for {key}")
    poller["lease_dropped"] = sorted(dropped)
    poller["lease_warned"] = sorted(warned_missing)
    return silenced, lease_events, unclosed


def silence_events(events, lease_events, silenced, gone):
    """Drop events of silenced PRs and `gone` keys from a tick's push queue; lease events lead."""
    kept = lease_events + [
        dict(e, push_queue=[k for k in e["push_queue"] if k not in gone])
        if e["kind"] == "tick" else e
        for e in events if e.get("pr") not in silenced]
    return [e for e in kept if e["kind"] != "tick" or e["push_queue"]]


def monitor(gh, session_dir, sleep=time.sleep, clock=time.time, max_ticks=None,
            write_lease=lease.tick_write, holder_alive=lease.holder_alive,
            started_at=lease.process_started_at):
    def beat():
        try:
            write_json_atomic(session_dir / "watch-heartbeat", int(clock()), sleep=sleep)
        except Exception as exc:  # a heartbeat is advisory; the watch must keep running
            warn(f"heartbeat: {type(exc).__name__}: {exc}")

    def beating_gh(args):
        beat()
        return gh(args)

    def save(view, poller):
        save_session_poller(
            Session(session_dir, view, poller, {}, False, False, loaded_leases), LIVE_FILES)

    claude_pid = claude_identity(session_dir)
    claude_started = started_at(claude_pid) if claude_pid else None
    if claude_pid and claude_started is None and IS_WINDOWS:
        return CLAUDE_GONE_EXIT
    ticks = failed_ticks = 0
    while max_ticks is None or ticks < max_ticks:
        ticks += 1
        if claude_started is not None and not holder_alive(
                {"pid": claude_pid, "pid_started_at": iso_utc(claude_started)}, started_at):
            return CLAUDE_GONE_EXIT
        beat()
        try:
            view = load_view(session_dir)
            poller = read_json(session_dir / "watch-poller.json", default={})
            if ticks == 1:
                # a PR closed under an earlier monitor may have been reopened and re-armed
                poller["closed"] = []
                poller["lease_dropped"] = []
                poller["lease_warned"] = []
            loaded_leases = lease_lists(poller)
            now = int(clock())
            last = poller.get("last_reconciliation", 0)
            due = now - last >= RECONCILE_SECONDS
            all_armed = armed_entries(view)
            dropped = set(poller.get("lease_dropped", ())) & set(all_armed)
            armed = armed_entries(view, dropped)
            ticked_view = dict(view, prs=armed)
            closed_before = set(poller.get("closed", [])) & set(armed)
            # forced first tick covers a resume; only the timed pass may claim a "reconciled" miss
            before = {n: (p.get("last_signature"), p.get("last_ci_signature"))
                      for n, p in poller.get("prs", {}).items()}
            events = tick_once(beating_gh, ticked_view, poller, now, force=ticks == 1 or due)
            if ticks == 1 or due:
                poller["last_reconciliation"] = now
            if due and last:
                missed = missed_prs(before, poller.get("prs", {}), events)
                if missed:
                    events.append({"kind": "reconciled", "prs": missed})
            poller.update(poller_pid=os.getpid(), claude_pid=claude_pid,
                          claude_started_at=iso_utc(claude_started) if claude_started else None)
            # an unsaved tick prints nothing; the next tick recomputes it from the old file
            save(view, poller)
            if not view["dry_run"]:
                lease_state = lease_lists(poller)
                silenced, lease_events, unclosed = write_session_leases(
                    view, all_armed, poller, closed_before, now, write_lease=write_lease)
                dropped = set(poller["lease_dropped"])
                if unclosed:
                    poller["closed"] = [k for k in poller["closed"] if k not in unclosed]
                if unclosed or lease_state != lease_lists(poller):
                    save(view, poller)
                events = silence_events(events, lease_events, silenced, silenced | dropped)
                if ticks == 1 or due:
                    try:
                        lease.prune_closed(now)
                    except OSError as exc:
                        warn(f"prune: {exc}")
            for event in events:
                print(json.dumps(event), flush=True)
            failed_ticks = 0
            if not [k for k in armed if k not in poller["closed"] and k not in dropped]:
                print(json.dumps({"kind": "idle"}), flush=True)
                return 0
        except Exception as exc:  # a standing watch must outlive any single failure
            warn(f"{type(exc).__name__}: {exc}")
            failed_ticks += 1
            if failed_ticks == POLLER_ERROR_AFTER:
                print(json.dumps({"kind": "poller-error", "error": str(exc)}), flush=True)
        if max_ticks is None or ticks < max_ticks:
            sleep(TICK_SECONDS)
            beat()
    return 0


class TickFiles(NamedTuple):
    poller: str
    spool: str


LIVE_FILES = TickFiles("watch-poller.json", "events.jsonl")
DRY_RUN_FILES = TickFiles("watch-poller.dry-run.json", "events.dry-run.jsonl")


class Session(NamedTuple):
    directory: pathlib.Path
    view: dict
    poller: dict
    ticked: dict
    force: bool
    poller_fault: bool
    leases_at_load: tuple = ()


def queue_peers(view, owner, repo, number, leased=None):
    """`leased` is lease.armed_peers(owner, repo, None) when the caller already read it."""
    peers = {e["number"] for e in view["prs"].values()
             if (e["owner"], e["repo"]) == (owner, repo) and e.get("role") == "authored"
             and e.get("status") == "armed"}
    peers.update(lease.armed_peers(owner, repo, None) if leased is None else leased)
    peers.discard(number)
    return sorted(peers)


def has_pending_check(gh, owner, repo, number, memo=None):
    """`memo` caches the answer per PR for one run."""
    key = (owner, repo, number)
    if memo is not None and key in memo:
        return memo[key]
    try:
        checks = required_checks(gh, repo_slug(owner, repo), number)
    except PR_FAULTS:
        pending = True
    else:
        pending = any(c.get("bucket") == "pending" for c in checks)
    if memo is not None:
        memo[key] = pending
    return pending


def tick_gate(gh, view, poller, now, memo=None):
    """True when some queued PR could drain now (step 04 section 8 step 1 would not stop it)."""
    leased = {}
    for key in view.get("push_queue", []):
        try:
            owner, repo, number = parse_ref(key)
        except ValueError:
            continue
        queued_at = view["prs"].get(key, {}).get("queued_at")
        if isinstance(queued_at, (int, float)) and now - queued_at >= QUEUE_WAIT_SECONDS:
            return True
        if (owner, repo) not in leased:
            leased[owner, repo] = lease.armed_peers(owner, repo, None)
        if not any(has_pending_check(gh, owner, repo, n, memo)
                   for n in queue_peers(view, owner, repo, number, leased[owner, repo])):
            return True
    return False


def session_dirs(root):
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir())


def read_poller(path):
    """(poller state, corrupt); a corrupt or non-object file reads as empty, like a first tick."""
    try:
        poller = read_json(path, default={})
    except ValueError:
        return {}, True
    return (poller, False) if isinstance(poller, dict) else ({}, True)


def load_session(directory, dry_run, files, now):
    """The session to tick, or None when it has no watch.json (step 01 deletes it once
    nothing is armed) or its watch is not central (a dry run takes every watch)."""
    try:
        watch = read_json(directory / "watch.json")
    except FileNotFoundError:
        return None
    if not dry_run and watch.get("watcher") != "central":
        return None
    view = load_view(directory, watch)
    poller, poller_fault = read_poller(directory / files.poller)
    force = now - poller.get("last_reconciliation", 0) >= RECONCILE_SECONDS
    if force:
        # the daily pass re-checks PRs closed earlier, in case one was reopened while armed
        poller["closed"] = []
    if dry_run:
        ticked = {k: e for k, e in view["prs"].items() if e.get("status") in REPORTED_STATUSES}
    else:
        ticked = armed_entries(view, set(poller.get("lease_dropped", ())))
    return Session(directory, view, poller, ticked, force, poller_fault, lease_lists(poller))


def append_spool(path, session_id, events):
    if not events:
        return
    lines = "".join(json.dumps({"session": session_id, **e}) + "\n" for e in events)
    with path.open("a+b") as handle:
        # a run killed mid-write leaves a partial last line; keep the next event off it
        torn = False
        if handle.seek(0, os.SEEK_END):
            handle.seek(-1, os.SEEK_END)
            torn = handle.read(1) != b"\n"
        handle.write((("\n" if torn else "") + lines).encode("utf-8"))


def session_id_of(session):
    return session.view.get("session_id") or session.directory.name


def keep_concurrent_claims(session, files):
    """A claim clears its PR from the lease lists on disk while this run holds the old lists;
    keep an in-memory key only if it is still on disk or this run added it."""
    try:
        disk, corrupt = read_poller(session.directory / files.poller)
    except OSError:
        return
    if corrupt:
        return
    for name, loaded in zip(LEASE_LISTS, session.leases_at_load):
        on_disk = set(disk.get(name, ()))
        was_loaded = set(loaded)
        mem = session.poller.get(name)
        if mem is not None:
            session.poller[name] = [k for k in mem if k in on_disk or k not in was_loaded]


def save_session_poller(session, files):
    keep_concurrent_claims(session, files)
    write_json_atomic(session.directory / files.poller, session.poller)


def prune_lease_lists(session, files, armed):
    if filter_lease_lists(session.poller, armed.__contains__):
        save_session_poller(session, files)


def is_live(session, files):
    return files is LIVE_FILES and not session.view["dry_run"]


def tick_session(gh, session, heads, now, files, write_lease, gate_memo=None):
    """One monitor tick for a session without idle or claude_pid checks; returns
    the events spooled, or None when nothing in it is armed."""
    view, poller, ticked = session.view, session.poller, session.ticked
    live = is_live(session, files)
    all_armed = armed_entries(view)
    if not ticked:
        if live:
            prune_lease_lists(session, files, all_armed)
        return None
    last, force = poller.get("last_reconciliation", 0), session.force
    closed_before = set(poller.get("closed", [])) & set(ticked)
    before = {n: (p.get("last_signature"), p.get("last_ci_signature"))
              for n, p in poller.get("prs", {}).items()}
    events = tick_once(gh, dict(view, prs=ticked), poller, now, force=force, heads=heads)
    if force:
        poller["last_reconciliation"] = now
        missed = missed_prs(before, poller["prs"], events) if last else []
        if missed:
            warn(f"session {session_id_of(session)}: reconciled {', '.join(missed)}")
    events = [e for e in events if e["kind"] != "tick"]
    silenced, lease_events, gone = set(), [], set()
    if live:
        silenced, lease_events, unclosed = write_session_leases(
            view, all_armed, poller, closed_before, now, write_lease=write_lease, central=True)
        if unclosed:
            poller["closed"] = [k for k in poller["closed"] if k not in unclosed]
        gone = silenced | set(poller["lease_dropped"])
    queue = [k for k in view["push_queue"] if k not in gone]
    if queue and tick_gate(gh, dict(view, push_queue=queue), poller, now, gate_memo):
        events.append({"kind": "tick", "push_queue": queue})
    if live:
        events = silence_events(events, lease_events, silenced, gone)
    # spooled before the save: a failed save re-raises these next run, and orch dedupes them
    append_spool(session.directory / files.spool, session_id_of(session), events)
    poller.pop("failed_ticks", None)
    poller["last_tick_at"] = now
    save_session_poller(session, files)
    return events


def record_failure(session, files, exc):
    """Count a failed tick in the saved poller state; the POLLER_ERROR_AFTER-th spools poller-error."""
    path = session.directory / files.poller
    try:
        poller, _ = read_poller(path)
        poller["failed_ticks"] = int(poller.get("failed_ticks") or 0) + 1
        events = ([{"kind": "poller-error", "error": str(exc)}]
                  if poller["failed_ticks"] == POLLER_ERROR_AFTER else [])
        append_spool(session.directory / files.spool, session_id_of(session), events)
        write_json_atomic(path, poller)
    except Exception as again:  # the run must go on to the other sessions
        warn(f"session {session.directory.name}: recording the failure: "
             f"{type(again).__name__}: {again}")
        return 0
    return len(events)


def tick_all(gh, sessions_root, now, *, dry_run=False, deadline_s=180, clock=time.monotonic,
             write_lease=lease.tick_write):
    start = clock()
    stats = {"sessions": 0, "events": 0, "gh_calls": 0, "skipped_after_deadline": 0, "errors": 0}

    def counting_gh(args):
        stats["gh_calls"] += 1
        return gh(args)

    files = DRY_RUN_FILES if dry_run else LIVE_FILES
    sessions = []
    for directory in session_dirs(sessions_root):
        try:
            session = load_session(directory, dry_run, files, now)
        except Exception as exc:  # one bad session dir must not stop every other watch
            warn(f"session {directory.name} skipped: {type(exc).__name__}: {exc}")
            stats["errors"] += 1
            continue
        if session is None:
            continue
        if session.poller_fault:
            warn(f"session {directory.name}: {files.poller} unreadable; ticking from empty state")
            stats["errors"] += 1
        sessions.append(session)
    groups = {}
    for session in sessions:
        for repo, numbers in head_groups(session.ticked,
                                         session.poller.get("closed", [])).items():
            groups.setdefault(repo, set()).update(numbers)
    heads, heads_error, gate_memo = {}, None, {}
    if groups:
        try:
            heads = fetch_heads(counting_gh, {repo: sorted(ns) for repo, ns in groups.items()})
        except Exception as exc:  # each session records it as its own failed tick
            warn(f"heads query: {type(exc).__name__}: {exc}")
            heads_error = exc
    forced = False
    sessions.sort(key=lambda s: (s.poller.get("last_tick_at", 0), s.directory.name))
    for session in sessions:
        if clock() - start >= deadline_s:
            stats["skipped_after_deadline"] += 1
            continue
        try:
            if heads_error is not None and session.ticked:
                raise heads_error
            events = tick_session(counting_gh, session, heads, now, files, write_lease, gate_memo)
        except Exception as exc:  # a standing watch must outlive any single failure
            warn(f"session {session.directory.name}: {type(exc).__name__}: {exc}")
            stats["errors"] += 1
            stats["events"] += record_failure(session, files, exc)
            continue
        if events is not None:
            stats["sessions"] += 1
            stats["events"] += len(events)
            forced = forced or (session.force and is_live(session, files))
    if forced:
        try:
            lease.prune_closed(now)
        except OSError as exc:
            warn(f"prune: {exc}")
    return stats


def all_ids(pr):
    ids = [c["id"] for t in pr["reviewThreads"]["nodes"] for c in t["comments"]["nodes"]]
    ids += [c["id"] for c in pr["comments"]["nodes"]]
    ids += [r["id"] for r in pr["reviews"]["nodes"]]
    return ids


def snip(body, width=300):
    return " ".join((body or "").split())[:width]


def attention_lines(view, pr, entry):
    me, allow = view["self_login"], view["bot_allowlist"]
    key = entry_key(entry)
    lines = []
    if entry["role"] == "authored":
        threads, top = pending(pr, entry, me, allow)
        for t, tail in threads:
            state = "resolved" if t["isResolved"] else "open"
            login, kind = classify(tail[-1]["author"], me, allow)
            lines.append(f"PR {key}  thread {t['path']}:{t['line']} [{state}]  "
                         f"{len(tail)} pending, last by {login} ({kind}): "
                         f"{snip(tail[-1]['body'])}")
        for surface, item in top:
            login, kind = classify(item["author"], me, allow)
            lines.append(f"PR {key}  {surface} by {login} ({kind}): {snip(item['body'])}")
    else:
        old = review_start(view, pr, entry)
        if my_threads(pr, me, allow) and old and old != pr["headRefOid"]:
            lines.append(f"PR {key}  head moved past your review: "
                         f"{old[:9]}..{pr['headRefOid'][:9]}")
    latest = {}
    for r in pr["reviews"]["nodes"]:
        login, kind = classify(r["author"], me, allow)
        if kind == "human" and r["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[login] = r
    for login, r in sorted(latest.items()):
        if r["state"] == "CHANGES_REQUESTED":
            lines.append(f"PR {key}  changes requested by {login}: "
                         f"{snip(r['body']) or '(no body)'}")
    return lines


def new_lines(key, pr, known, self_login, allowlist):
    lines = []
    for t in pr["reviewThreads"]["nodes"]:
        for c in t["comments"]["nodes"]:
            if c["id"] not in known:
                login, kind = classify(c["author"], self_login, allowlist)
                lines.append(f"PR {key}  [{kind}] thread {t['path']}:{t['line']}  "
                             f"{login}: {snip(c['body'])}")
    for c in pr["comments"]["nodes"]:
        if c["id"] not in known:
            login, kind = classify(c["author"], self_login, allowlist)
            lines.append(f"PR {key}  [{kind}] issue comment  {login}: {snip(c['body'])}")
    for r in pr["reviews"]["nodes"]:
        if r["id"] not in known:
            login, kind = classify(r["author"], self_login, allowlist)
            lines.append(f"PR {key}  [{kind}] review {r['state']}  {login}: "
                         f"{snip(r['body']) or '(no body)'}")
    return lines


def standing_line(key, pr, entry, self_login, allowlist):
    threads = pr["reviewThreads"]["nodes"]
    authors = [c["author"] for t in threads for c in t["comments"]["nodes"]]
    authors += [c["author"] for c in pr["comments"]["nodes"]]
    authors += [r["author"] for r in pr["reviews"]["nodes"]]
    humans = sorted({login for login, kind in
                     (classify(a, self_login, allowlist) for a in authors) if kind == "human"})
    unresolved = sum(1 for t in threads if not t["isResolved"])
    return (f"PR {key}  {entry['role']}  head={pr['headRefOid'][:9]}  "
            f"threads={len(threads)} unresolved={unresolved}  "
            f"humans: {', '.join(humans) or 'none'}")


def report(gh, session_dir, reseed=False):
    view = load_view(session_dir)
    seen_path = session_dir / "watch-seen.json"
    seen = read_json(seen_path, default={})
    me, allow = view["self_login"], view["bot_allowlist"]
    first_run = not seen
    attention, new, standing, errors = [], [], [], []
    fresh = dict(seen)
    for key, entry in sorted(view["prs"].items(),
                             key=lambda item: (item[1]["owner"], item[1]["repo"],
                                               item[1]["number"])):
        if entry.get("status") not in REPORTED_STATUSES:
            continue
        if entry.get("load_fault"):
            errors.append(f"PR {key}: {entry['load_fault']}")
            continue
        try:
            pr = fetch_pr(gh, entry["owner"], entry["repo"], entry["number"])
            lines = (attention_lines(view, pr, entry),
                     new_lines(key, pr, set(seen.get(key, [])), me, allow),
                     standing_line(key, pr, entry, me, allow), all_ids(pr))
        except PR_FAULTS as exc:
            errors.append(f"PR {key}: {type(exc).__name__}: {exc}")
            continue
        attention += lines[0]
        new += lines[1]
        standing.append(lines[2])
        fresh[key] = lines[3]
    for line in errors:
        print(f"ERROR  {line}")
    if not reseed and not (errors or attention or new or first_run):
        print(f"pr-watch: nothing new across {len(standing)} PRs; nothing needs attention")
    elif not reseed:
        print_sections(attention, new, standing, first_run)
    if fresh != seen:
        try:
            write_json_atomic(seen_path, fresh)
        except OSError as exc:
            print(f"pr-watch: could not save watch-seen.json: {exc}", file=sys.stderr)
            return 1
    if reseed:
        print(f"pr-watch: reseeded; {sum(len(v) for v in fresh.values())} ids accepted as seen")
    return 1 if errors else 0


def print_sections(attention, new, standing, first_run):
    print("ATTENTION")
    for line in attention or ["none"]:
        print(f"  {line}")
    if first_run:
        print(f"NEW  first run; {len(new)} items seeded as the baseline")
    else:
        print(f"NEW ({len(new)} items)")
        for line in new:
            print(f"  {line}")
    print("STANDING")
    for line in standing:
        print(f"  {line}")


def findings_payload(gh, view, entry, pr):
    me, allow = view["self_login"], view["bot_allowlist"]
    old, new = review_start(view, pr, entry), pr["headRefOid"]
    files = changed_files(gh, entry["owner"], entry["repo"], old, new) if old and old != new else []
    return {
        "pr": entry_key(entry), "title": pr["title"], "url": pr["url"],
        "author": (pr.get("author") or {}).get("login"),
        "old_head": old, "new_head": new, "changed_files": files,
        "compare_capped": compare_capped(files),
        "threads": [{
            "thread_id": t["id"], "path": t["path"], "line": t["line"],
            "is_resolved": t["isResolved"], "is_outdated": t["isOutdated"],
            "kinds": [classify(c["author"], me, allow)[1] for c in t["comments"]["nodes"]],
            "comments": [comment_record(c, "inline", me, allow, thread=t)
                         for c in t["comments"]["nodes"]],
        } for t in my_threads(pr, me, allow)],
    }


def keep_failing(conclusions, key, value):
    if key not in conclusions or value in FAILED_BASE:
        conclusions[key] = value


def base_conclusions(gh, repo_slug, ref):
    """(workflow, name) -> conclusion on the tip of `ref`; None when check suites disagree.

    The workflow is "" for a check run outside GitHub Actions and for a commit status.
    """
    sha = gh(["api", f"repos/{repo_slug}/commits/{urllib.parse.quote(ref, safe='')}",
              "-H", "Accept: application/vnd.github.sha"]).strip()
    commit = f"repos/{repo_slug}/commits/{urllib.parse.quote(sha, safe='')}"
    workflow_runs = gh(["api", f"repos/{repo_slug}/actions/runs?head_sha={urllib.parse.quote(sha, safe='')}",
                        "--paginate", "--jq", ".workflow_runs[] | [.check_suite_id, .name] | @tsv"])
    workflows = dict(row.split("\t", 1) for row in workflow_runs.splitlines() if "\t" in row)
    runs = gh(["api", f"{commit}/check-runs", "--paginate", "--jq",
               ".check_runs[] | [.name, (.conclusion // .status), .check_suite.id] | @tsv"])
    suites = {}
    for row in runs.splitlines():
        name, value, suite = (row.split("\t") + ["", ""])[:3]
        if name:
            keep_failing(suites.setdefault((workflows.get(suite, ""), name), {}), suite, value)
    out = {}
    for key, by_suite in suites.items():
        values = set(by_suite.values())
        out[key] = values.pop() if len(values) == 1 else None
    statuses = gh(["api", f"{commit}/status", "--jq", ".statuses[] | [.context, .state] | @tsv"])
    for row in statuses.splitlines():
        name, _, value = row.partition("\t")
        if name and out.get(("", name), "") is not None:
            keep_failing(out, ("", name), value)
    return out


def base_conclusion(on_base, workflow, name):
    """The base result for a PR check, by workflow and name; by name alone only when
    the one base row with that name has no workflow."""
    if (workflow, name) in on_base:
        return on_base[(workflow, name)]
    same_name = [key for key in on_base if key[1] == name]
    if len(same_name) == 1 and same_name[0][0] == "":
        return on_base[same_name[0]]
    return None


def checks_payload(gh, owner, repo, number):
    slug = repo_slug(owner, repo)
    base, head = gh(["api", f"repos/{slug}/pulls/{number}",
                     "--jq", '.base.ref + " " + .head.sha']).split()
    on_base = base_conclusions(gh, slug, base)
    checks = [{"name": c["name"], "state": c.get("state"), "bucket": c.get("bucket"),
               "link": c.get("link"), "workflow": c.get("workflow") or "",
               "completed_at": c.get("completedAt"),
               "on_base": base_conclusion(on_base, c.get("workflow") or "", c["name"]),
               **check_platform(c.get("link"))}
              for c in required_checks(gh, slug, number)]
    return {"pr": pr_key(owner, repo, number), "head": head, "base": base, "checks": checks}


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# urllib's default redirect handler carries Authorization onto the new
# host; refuse the redirect instead of following it with the PAT attached.
_NO_REDIRECT_OPENER = urllib.request.build_opener(_RefuseRedirect).open


def ado_request(url, method="GET", body=None, opener=None):
    pat = os.environ.get("AZURE_DEVOPS_EXT_PAT")
    if not pat:
        raise GhError("AZURE_DEVOPS_EXT_PAT is not set")
    token = base64.b64encode(f":{pat}".encode("ascii")).decode("ascii")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Basic {token}", "Content-Type": "application/json"})
    try:
        with (opener or _NO_REDIRECT_OPENER)(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        if isinstance(exc, urllib.error.HTTPError):
            exc.close()
        raise GhError(f"{method} {url.split('?')[0]}: {exc}") from None


def failed_records(timeline, kind):
    """Failed records of `kind`; without any, the finished canceled ones (an Azure timeout)."""
    records = [r for r in timeline.get("records") or [] if r.get("type") == kind]
    return ([r for r in records if r.get("result") == "failed"]
            or [r for r in records if r.get("result") == "canceled" and r.get("finishTime")])


def failure_window(text, count=LOG_LINES):
    """At most `count` lines: around the first and the last failure marker, else the tail."""
    lines = text.splitlines()
    if len(lines) <= count:
        return text
    marks = [i for i, line in enumerate(lines) if FAILURE_MARK.search(line)]
    if not marks:
        return "\n".join(lines[-count:])
    half = count // 2
    first_start = max(0, marks[0] - CONTEXT_BEFORE // 2)
    first_end = min(len(lines), first_start + half)
    last_end = min(len(lines), marks[-1] + 1 + CONTEXT_AFTER)
    last_start = max(0, last_end - half)
    if first_end >= last_start:
        return "\n".join(lines[min(first_start, last_start):max(first_end, last_end)])
    return "\n".join([*lines[first_start:first_end],
                      f"... {last_start - first_end} lines omitted ...",
                      *lines[last_start:last_end]])


def ado_timeline(target, ado_orgs, ado):
    """The build URL and its timeline; refuses an org outside `ado_orgs` before any request."""
    if not isinstance(ado_orgs, list):
        raise GhError(f"ado_orgs must be a list of strings, not {type(ado_orgs).__name__}")
    odd = next((org for org in ado_orgs if not isinstance(org, str)), None)
    if odd is not None:
        raise GhError(f"ado_orgs must be a list of strings, not a list holding {type(odd).__name__}")
    if not ADO_ORG.match(target["org"]):
        raise GhError(f"Azure DevOps org {target['org']} is not a valid name")
    if not ADO_PROJECT.match(target["project"]):
        raise GhError(f"Azure DevOps project {target['project']} is not a valid name")
    if target["org"].lower() not in {org.lower() for org in ado_orgs}:
        raise GhError(f"Azure DevOps org {target['org']} is not in ado_orgs")
    build = ADO_BUILD.format(**target)
    return build, json.loads(ado(f"{build}/timeline?api-version=7.1"))


def ci_log(gh, repo_slug, link, ado_orgs, ado=ado_request):
    target = check_platform(link)
    if target["platform"] == "github-actions":
        return failure_window(gh(["api", f"repos/{repo_slug}/actions/jobs/{target['job_id']}/logs"]))
    if target["platform"] == "azure-pipelines":
        build, timeline = ado_timeline(target, ado_orgs, ado)
        parts = [f"== {r.get('name')} ==\n" + ado(f"{build}/logs/{r['log']['id']}?api-version=7.1")
                 for r in failed_records(timeline, "Task") if (r.get("log") or {}).get("id")]
        if not parts:
            raise GhError(f"no failed task log in build {target['build_id']}")
        return failure_window("\n".join(parts))
    raise GhError(f"no CI source for {link}")


def ci_rerun(gh, repo_slug, link, ado_orgs, ado=ado_request):
    target = check_platform(link)
    if target["platform"] == "github-actions":
        gh(["run", "rerun", target["run_id"], "--failed", "--repo", repo_slug])
        return [f"run {target['run_id']}"]
    if target["platform"] == "azure-pipelines":
        build, timeline = ado_timeline(target, ado_orgs, ado)
        stages = [r["identifier"] for r in failed_records(timeline, "Stage") if r.get("identifier")]
        if not stages:
            raise GhError(f"no failed stage to retry in build {target['build_id']}")
        for stage in stages:
            ado(f"{build}/stages/{urllib.parse.quote(stage, safe='')}?api-version=7.1-preview.1",
                method="PATCH", body={"state": "retry", "forceRetryAllJobs": False})
        return [f"stage {stage}" for stage in stages]
    raise GhError(f"no CI source for {link}")


def assert_author(gh, repo_slug, number):
    author = gh(["api", f"repos/{repo_slug}/pulls/{number}", "--jq", ".user.login"]).strip()
    acting = gh(["api", "user", "--jq", ".login"]).strip()
    if author and author == acting:
        return 0
    print(f"push refused: PR #{number} is authored by {author or 'unknown'}; "
          f"acting login is {acting or 'unknown'}", file=sys.stderr)
    return 3


def slack_args(args):
    """The Slack replies --tails should handle, or [] without --slack; ValueError on bad usage."""
    if not args.slack:
        return []
    if not args.tails:
        raise ValueError("--slack needs --tails")
    if not (args.slack_human and args.slack_since):
        raise ValueError("--slack needs --slack-human and --slack-since")
    bots = [b for b in args.slack_bots.split(",") if b]
    if not all(SLACK_ID.fullmatch(i) for i in [args.slack_human, *bots]):
        raise ValueError("--slack-human and --slack-bots take Slack user ids")
    if not SLACK_TS.fullmatch(args.slack_since):
        raise ValueError("--slack-since must be a Slack ts")
    try:
        return slack_replies_to_handle(load_slack(args.slack), args.slack_human,
                                       bots, args.slack_since)
    except ValueError as exc:
        raise ValueError(f"--slack: {exc}") from exc


def main(argv=None, gh=run_gh):
    parser = argparse.ArgumentParser(prog="poll.py", description="pr-watch poller")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--monitor", action="store_true",
                      help="print one JSON line per actionable change, forever")
    mode.add_argument("--tick-all", action="store_true",
                      help="tick every central watch once, spool its events, print run stats")
    mode.add_argument("--report", action="store_true", help="print ATTENTION, NEW, STANDING")
    mode.add_argument("--reseed", action="store_true", help="accept every current id as seen")
    mode.add_argument("--baseline", metavar="REF", help="print the first-arm baseline")
    mode.add_argument("--tails", metavar="REF", help="print pending tails as CommentRecords")
    mode.add_argument("--findings", metavar="REF",
                      help="print the user's threads on a reviewed PR")
    mode.add_argument("--review-ready", metavar="REF",
                      help="print whether an authored PR is ready to ask humans to review")
    mode.add_argument("--checks", metavar="REF",
                      help="print the required checks on the PR head")
    mode.add_argument("--assert-author", type=int, metavar="PR",
                      help="exit 0 only if the acting login authored the PR")
    mode.add_argument("--ci-log", metavar="LINK",
                      help="print the log behind a check link, windowed on its first and "
                           "last failure markers")
    mode.add_argument("--ci-rerun", metavar="LINK",
                      help="rerun the failed jobs behind a check link")
    mode.add_argument("--claim", metavar="REF", help="claim the PR's lease for this session")
    mode.add_argument("--lease-status", metavar="REF",
                      help="set the status of a lease this session holds")
    mode.add_argument("--repo-peers", metavar="REF",
                      help="print the armed authored PRs in the same repo as a JSON list")
    mode.add_argument("--discover", action="store_true",
                      help="print the open PRs this session wrote to, as JSON")
    mode.add_argument("--find-clone", metavar="REF",
                      help="print a local clone of the PR's repo known to this session")
    mode.add_argument("--push-lock", nargs=2, metavar=("ACTION", "REF"),
                      help="take or release the per-repo push lock")
    mode.add_argument("--migrate-scan", metavar="MAIN",
                      help="print the state of the old-format watch in a main checkout")
    mode.add_argument("--migrate-import", metavar="MAIN",
                      help="import the old-format watch's progress into this session")
    mode.add_argument("--migrate-done", metavar="MAIN",
                      help="mark the old-format watch's import as complete")
    mode.add_argument("--check-identity", action="store_true",
                      help="exit 1 when CLAUDE_PID is not this process's claude")
    mode.add_argument("--end-leftover-monitors", action="store_true",
                      help="end this session's pollers left by an earlier claude process")
    mode.add_argument("--end-session-monitors", action="store_true",
                      help="end every --monitor poller for this session directory")
    mode.add_argument("--monitor-alive", action="store_true",
                      help="print alive or down for this session's monitor")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --tick-all: every armed or stopped watch, its own files, "
                             "no leases")
    parser.add_argument("--central", action="store_true",
                        help="with --claim: hold the lease as a central watch")
    parser.add_argument("--role", choices=("authored", "reviewed"), help="with --claim")
    parser.add_argument("--explicit", action="store_true",
                        help="with --claim: the user named this PR")
    parser.add_argument("--status", choices=("stopped", "released"), help="with --lease-status")
    parser.add_argument("--slack", metavar="FILE",
                        help="with --tails: JSON list of {ts, author, body} Slack thread replies")
    parser.add_argument("--slack-human", metavar="ID", help="with --slack: the human whose replies count")
    parser.add_argument("--slack-bots", metavar="ID,ID", default="",
                        help="with --slack: review bots whose replies count")
    parser.add_argument("--slack-since", metavar="TS", help="with --slack: oldest reply ts to keep")
    parser.add_argument("--session-dir", type=pathlib.Path,
                        help="<pr-watch home>/sessions/<session id>")
    parser.add_argument("--session-id", help="with --discover and --find-clone")
    parser.add_argument("--repo", help="owner/name; required with --assert-author, --ci-log, --ci-rerun")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.assert_author is not None and not args.repo:
        parser.error("--assert-author needs --repo owner/name")
    if (args.ci_log or args.ci_rerun) and not (args.repo and args.session_dir):
        parser.error("--ci-log and --ci-rerun need --repo owner/name and --session-dir")
    try:
        args.slack_replies = slack_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run and not args.tick_all:
        parser.error("--dry-run needs --tick-all")
    if args.central and not args.claim:
        parser.error("--central needs --claim")
    if args.claim and not args.role:
        parser.error("--claim needs --role")
    if args.lease_status and not args.status:
        parser.error("--lease-status needs --status")
    if args.push_lock and args.push_lock[0] not in ("take", "release"):
        parser.error("--push-lock action must be take or release")
    if (args.discover or args.find_clone) and not args.session_id:
        parser.error("--discover and --find-clone need --session-id")
    if (args.assert_author is None and args.repo_peers is None and args.session_dir is None
            and not (args.discover or args.find_clone or args.check_identity or args.tick_all)):
        parser.error("--session-dir is required for this mode")
    try:
        return run_mode(args, gh)
    except (GhError, OSError, ValueError, http.client.HTTPException) as exc:
        print(f"pr-watch: {exc}", file=sys.stderr)
        return 1


def forget_lease_silencing(session_dir, key):
    path = session_dir / LIVE_FILES.poller
    poller, _ = read_poller(path)
    if filter_lease_lists(poller, lambda k: k != key):
        write_json_atomic(path, poller)


def lease_mode(args):
    watch = read_json(args.session_dir / "watch.json")
    session_id = watch.get("session_id")
    if not session_id:
        raise ValueError("watch.json has no session_id")
    now = time.time()
    if args.push_lock:
        action, ref = args.push_lock
        owner, repo, _ = parse_ref(ref)
        if action == "release":
            lease.release_push_lock(owner, repo, session_id)
            print("released")
            return 0
        if lease.take_push_lock(owner, repo, session_id, now):
            print("taken")
            return 0
        print("pr-watch: busy", file=sys.stderr)
        return 1
    owner, repo, number = parse_ref(args.claim or args.lease_status)
    if args.lease_status:
        if lease.set_status(owner, repo, number, args.status, session_id, now):
            print(args.status)
            return 0
        print(f"pr-watch: {pr_key(owner, repo, number)} is not held by this session",
              file=sys.stderr)
        return 1
    pid = as_pid(watch.get("claude_pid"))
    started = lease.process_started_at(pid) if pid else None
    holder = {"session_id": session_id, "pid": pid,
              "pid_started_at": iso_utc(started) if started is not None else None,
              "poller_pid": None}
    ok, why = lease.claim(owner, repo, number, role=args.role, holder=holder,
                          explicit=args.explicit, now=now, central=args.central)
    if ok:
        forget_lease_silencing(args.session_dir, pr_key(owner, repo, number))
        print(why)
        return 0
    print(f"pr-watch: cannot claim {pr_key(owner, repo, number)}: {why}", file=sys.stderr)
    return 1


def discover_mode(args, gh):
    import discover
    if args.find_clone:
        owner, repo, number = parse_ref(args.find_clone)
        found = (discover.find_clone(args.session_id, owner, repo, discover.origin_of)
                 or discover.holder_clone(owner, repo, number, discover.origin_of))
        if not found:
            print(f"pr-watch: no local clone of {owner}/{repo} known to this session",
                  file=sys.stderr)
            return 1
        print(found)
        return 0
    if discover.find_transcript(args.session_id) is None:
        print(f"pr-watch: no transcript for session {args.session_id}", file=sys.stderr)
        print("[]")
        return 0
    me = gh(["api", "user", "--jq", ".login"]).strip()
    print(json.dumps(discover.discover(gh, args.session_id, me, discover.origin_of), indent=2))
    return 0


def migrate_mode(args):
    import migrate
    claude_pid = as_pid(os.environ.get("CLAUDE_PID"))
    if args.check_identity:
        reason = migrate.identity_ok(claude_pid, os.getpid(), migrate.list_processes())
        if reason:
            print(f"pr-watch: {reason}", file=sys.stderr)
            return 1
        return 0
    if args.end_session_monitors:
        pids = migrate.session_monitors(args.session_dir, migrate.list_processes())
        for pid in pids:
            migrate.end_tree(pid)
        print(json.dumps(pids))
        return 0
    if not claude_pid:
        print("pr-watch: CLAUDE_PID is not set", file=sys.stderr)
        return 1
    if args.migrate_import:
        print(json.dumps(migrate.import_progress(args.migrate_import)))
        return 0
    if args.migrate_done:
        migrate.finish_import(args.migrate_done)
        return 0
    procs = migrate.list_processes()
    if args.migrate_scan:
        print(json.dumps(migrate.scan(args.migrate_scan, claude_pid, procs, time.time())))
    elif args.end_leftover_monitors:
        pids = migrate.leftover_monitors(args.session_dir, claude_pid, procs)
        for pid in pids:
            migrate.end_tree(pid)
        print(json.dumps(pids))
    else:
        print("alive" if migrate.monitor_alive(args.session_dir, claude_pid, procs) else "down")
    return 0


def run_mode(args, gh):
    if (args.migrate_scan or args.migrate_import or args.migrate_done or args.check_identity
            or args.end_leftover_monitors or args.end_session_monitors
            or args.monitor_alive):
        return migrate_mode(args)
    if args.discover or args.find_clone:
        return discover_mode(args, gh)
    if args.assert_author is not None:
        return assert_author(gh, args.repo, args.assert_author)
    if args.repo_peers:
        owner, repo, number = parse_ref(args.repo_peers)
        print(json.dumps([pr_key(owner, repo, n) for n in lease.armed_peers(owner, repo, number)]))
        return 0
    if args.claim or args.lease_status or args.push_lock:
        return lease_mode(args)
    if args.tick_all:
        stats = tick_all(gh, sessions_root(), int(time.time()), dry_run=args.dry_run)
        print(json.dumps(stats), flush=True)
        return 0
    if args.monitor:
        return monitor(gh, args.session_dir)
    if args.report or args.reseed:
        return report(gh, args.session_dir, reseed=args.reseed)
    view = load_view(args.session_dir)
    if args.ci_log:
        print(ci_log(gh, args.repo, args.ci_log, view["ado_orgs"]))
        return 0
    if args.ci_rerun:
        for line in ci_rerun(gh, args.repo, args.ci_rerun, view["ado_orgs"]):
            print(f"rerun started: {line}")
        return 0
    owner, repo, number = parse_ref(args.checks or args.baseline or args.tails or args.findings
                                    or args.review_ready)
    if args.checks:
        print(json.dumps(checks_payload(gh, owner, repo, number), indent=2))
        return 0
    entry = view["prs"].get(pr_key(owner, repo, number))
    if entry and entry.get("load_fault") and not args.baseline:
        raise ValueError(f"PR {pr_key(owner, repo, number)}: {entry['load_fault']}")
    entry = entry or {
        **read_json(progress_file(args.session_dir, owner, repo, number, view["dry_run"]),
                    default={}),
        "owner": owner, "repo": repo, "number": number}
    pr = fetch_pr(gh, owner, repo, number)
    me, allow = view["self_login"], view["bot_allowlist"]
    if args.baseline:
        payload = baseline(pr, me, allow)
    elif args.tails:
        payload = tails_payload(pr, entry, me, allow, slack=args.slack_replies,
                                slack_human=args.slack_human)
    elif args.review_ready:
        payload = review_ready_payload(gh, view, entry, pr, time.time())
    else:
        payload = findings_payload(gh, view, entry, pr)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
