"""pr-watch poller.

Deterministic; no model runs here. Reads the session-owned watch.json and
never writes it. The monitor writes watch-poller.json; --report and
--reseed write watch-seen.json. Modes are listed in main().
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
TICK_SECONDS = 60
RECONCILE_SECONDS = 24 * 60 * 60
TICK_EVENT_RETRY_SECONDS = 600
NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


class GhError(RuntimeError):
    pass


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
        if tail:
            threads.append((t, tail))
    top = []
    for surface, item, _ in top_level_items(pr):
        if classify(item["author"], self_login, allowlist)[1] == "me":
            continue
        if item["id"] not in handled:
            top.append((surface, item))
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
    handled = {}
    for _, item, when in top_level_items(pr):
        k = kind(item["author"])
        if k in ("bot", "me") or (newest_me and when and when < newest_me):
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


def tails_payload(pr, watch_pr, self_login, allowlist):
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
        "pr": pr["number"], "title": pr["title"], "body": pr.get("body") or "",
        "url": pr["url"], "head": pr["headRefOid"], "base": pr["baseRefName"],
        "branch": pr["headRefName"],
        "threads": out,
        "top_level": [comment_record(i, s, self_login, allowlist) for s, i in top],
        "truncated": pr.get("truncated", []),
    }


def run_gh(args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise GhError(out.stderr.strip()[:400] or f"gh exited {out.returncode}")
    return out.stdout


def graphql(gh, query, variables, allow_partial=False):
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        args += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
    data = json.loads(gh(args))
    if data.get("errors") and not (allow_partial and data.get("data")):
        raise GhError(json.dumps(data["errors"])[:400])
    return data["data"]


def fetch_pr(gh, owner, repo, number):
    query = (SCRIPT_DIR / "threads.graphql").read_text(encoding="utf-8")
    pr, threads, after = None, [], None
    while True:
        page = graphql(gh, query, {"owner": owner, "repo": repo, "n": number,
                                   "after": after})["repository"]["pullRequest"]
        if page is None:
            raise GhError(f"PR #{number} not found in {owner}/{repo}")
        pr = pr or page
        threads += page["reviewThreads"]["nodes"]
        info = page["reviewThreads"]["pageInfo"]
        if not info["hasNextPage"]:
            break
        after = info["endCursor"]
    pr = dict(pr, reviewThreads={"pageInfo": {"hasNextPage": False, "endCursor": None},
                                 "nodes": threads})
    pr["truncated"] = truncation(pr)
    return pr


def truncation(pr):
    notes = [f"thread {t['id']} has more than 100 comments"
             for t in pr["reviewThreads"]["nodes"]
             if t["comments"]["pageInfo"]["hasNextPage"]]
    if pr["comments"]["pageInfo"]["hasPreviousPage"]:
        notes.append("more than 100 issue comments; the oldest are not read")
    if pr["reviews"]["pageInfo"]["hasPreviousPage"]:
        notes.append("more than 100 reviews; the oldest are not read")
    return notes


def tick_query(owner, repo, numbers):
    if not (NAME.match(owner) and NAME.match(repo)):
        raise ValueError(f"unsafe owner/repo: {owner}/{repo}")
    fields = " ".join(
        f"p{int(n)}: pullRequest(number: {int(n)}) {{ number updatedAt headRefOid state }}"
        for n in numbers)
    return f'query {{ repository(owner: "{owner}", name: "{repo}") {{ {fields} }} }}'
