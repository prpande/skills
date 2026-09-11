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


def my_threads(pr, self_login, allowlist):
    return [t for t in pr["reviewThreads"]["nodes"]
            if any(classify(c["author"], self_login, allowlist)[1] == "me"
                   for c in t["comments"]["nodes"])]


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
    out = gh(["api", f"repos/{owner}/{repo}/compare/{old}...{new}", "--paginate",
              "--jq", ".files[].filename"])
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def evaluate_authored(watch, pr, watch_pr, prev):
    threads, top = pending(pr, watch_pr, watch["self_login"], watch["bot_allowlist"])
    ids = sorted([c["id"] for _, tail in threads for c in tail] + [i["id"] for _, i in top])
    if not ids:
        return None, ""
    signature = "pending:" + ",".join(ids)
    if signature == prev.get("last_signature"):
        return None, signature
    return {"pr": pr["number"], "role": "authored", "kind": "pending",
            "threads": [t["id"] for t, _ in threads],
            "comments": [i["id"] for s, i in top if s == "issue"],
            "reviews": [i["id"] for s, i in top if s == "review"]}, signature


def evaluate_reviewed(gh, watch, pr, prev):
    me, allow = watch["self_login"], watch["bot_allowlist"]
    threads = my_threads(pr, me, allow)
    if not threads:
        return None, ""
    old, new = my_review_head(pr, me, allow), pr["headRefOid"]
    author = (pr.get("author") or {}).get("login")
    replies = [c for t in threads for c in replies_after_me(t, me, allow)]
    reply_ids = sorted(c["id"] for c in replies)
    author_replied = any((c["author"] or {}).get("login") == author for c in replies)
    if old and old != new:
        signature = f"head:{new}:" + ",".join(reply_ids)
        if signature == prev.get("last_signature"):
            return None, signature
        files = set(changed_files(gh, watch["owner"], watch["repo"], old, new))
        touches = any(t["path"] in files for t in threads)
        if not (touches or author_replied):
            return None, signature
        return {"pr": pr["number"], "role": "reviewed", "kind": "head-moved",
                "old_head": old, "new_head": new, "touches_my_findings": touches,
                "author_replied": author_replied}, signature
    if not reply_ids:
        return None, ""
    signature = "reply:" + ",".join(reply_ids)
    if signature == prev.get("last_signature"):
        return None, signature
    return {"pr": pr["number"], "role": "reviewed", "kind": "reply",
            "threads": [t["id"] for t in threads if replies_after_me(t, me, allow)]}, signature


def tick_once(gh, watch, poller, now, force=False):
    events = []
    prs = poller.setdefault("prs", {})
    closed = poller.setdefault("closed", [])
    numbers = sorted(int(n) for n in watch["prs"] if int(n) not in closed)
    heads = {}
    if numbers:
        heads = graphql(gh, tick_query(watch["owner"], watch["repo"], numbers), {},
                        allow_partial=True)["repository"]
    for n in numbers:
        node = heads.get(f"p{n}")
        if node is None or node["state"] != "OPEN":
            events.append({"pr": n, "kind": "closed",
                           "state": node["state"] if node else "MISSING"})
            closed.append(n)
            prs.pop(str(n), None)
            continue
        prev = prs.get(str(n), {})
        moved = (node["updatedAt"] != prev.get("updated_at")
                 or node["headRefOid"] != prev.get("last_head"))
        if not (moved or force):
            continue
        watch_pr = watch["prs"][str(n)]
        seen = {} if force else prev
        try:
            pr = fetch_pr(gh, watch["owner"], watch["repo"], n)
            if watch_pr["role"] == "authored":
                event, signature = evaluate_authored(watch, pr, watch_pr, seen)
            else:
                event, signature = evaluate_reviewed(gh, watch, pr, seen)
        except GhError as exc:
            print(f"pr-watch poller: PR #{n}: {exc}", file=sys.stderr, flush=True)
            continue
        prs[str(n)] = {"updated_at": node["updatedAt"], "last_head": node["headRefOid"],
                       "last_signature": signature}
        if event:
            events.append(event)
    queue = list(watch.get("push_queue", []))
    if not queue:
        poller["last_tick_queue"] = []
    elif (queue != poller.get("last_tick_queue")
          or now - poller.get("last_tick_event", 0) >= TICK_EVENT_RETRY_SECONDS):
        events.append({"kind": "tick", "push_queue": queue})
        poller["last_tick_queue"] = queue
        poller["last_tick_event"] = now
    return events


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is None:
            raise
        return json.loads(json.dumps(default))


def write_json_atomic(path, data):
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


def monitor(gh, state_dir, sleep=time.sleep, clock=time.time, max_ticks=None):
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        ticks += 1
        try:
            watch = read_json(state_dir / "watch.json")
            poller = read_json(state_dir / "watch-poller.json", default={})
            now = int(clock())
            last = poller.get("last_reconciliation", 0)
            force = now - last >= RECONCILE_SECONDS
            events = tick_once(gh, watch, poller, now, force=force)
            if force:
                poller["last_reconciliation"] = now
                found = sorted({e["pr"] for e in events if "pr" in e})
                if last and found:
                    events.append({"kind": "reconciled", "prs": found})
            for event in events:
                print(json.dumps(event), flush=True)
            write_json_atomic(state_dir / "watch-poller.json", poller)
        except Exception as exc:  # a standing watch must outlive any single failure
            print(f"pr-watch poller: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if max_ticks is None or ticks < max_ticks:
            sleep(TICK_SECONDS)
