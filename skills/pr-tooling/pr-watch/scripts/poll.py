"""pr-watch poller.

Deterministic; no model runs here. Reads the session-owned watch.json and
never writes it. The monitor writes watch-poller.json; --report and
--reseed write watch-seen.json. Modes are listed in main().
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
TICK_SECONDS = 60
RECONCILE_SECONDS = 24 * 60 * 60
TICK_EVENT_RETRY_SECONDS = 600
NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
CHECK_FIELDS = "name,state,bucket,link,workflow,completedAt"
FAILED_ROLLUP = ("FAILURE", "ERROR")
FAILED_BASE = ("failure", "error", "timed_out")
ACTIONS_LINK = re.compile(r"^https://github\.com/[^/]+/[^/]+/actions/runs/(\d+)/job/(\d+)")
AZURE_LINK = re.compile(
    r"^https://dev\.azure\.com/([^/]+)/([^/]+)/_build/results\?buildId=(\d+)")
ADO_BUILD = "https://dev.azure.com/{org}/{project}/_apis/build/builds/{build_id}"
LOG_LINES = 5000


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
        f"p{int(n)}: pullRequest(number: {int(n)}) {{ number updatedAt headRefOid state "
        f"commits(last: 1) {{ nodes {{ commit {{ statusCheckRollup {{ state }} }} }} }} }}"
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


def evaluate_ci(gh, watch, number, node, prev):
    if rollup_state(node) not in FAILED_ROLLUP:
        return None, ""
    slug = f"{watch['owner']}/{watch['repo']}"
    red = sorted((c for c in required_checks(gh, slug, number) if c.get("bucket") == "fail"),
                 key=check_key)
    if not red:
        return None, ""
    head = node["headRefOid"]
    signature = f"ci:{head}:" + ",".join(
        f"{check_key(c)}|{c.get('completedAt') or ''}" for c in red)
    if signature == prev.get("last_ci_signature"):
        return None, signature
    return {"pr": number, "role": "authored", "kind": "ci-red", "head": head,
            "checks": [{"name": c["name"], "workflow": c.get("workflow") or "",
                        "completed_at": c.get("completedAt")} for c in red]}, signature


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
        rollup = rollup_state(node)
        moved = (node["updatedAt"] != prev.get("updated_at")
                 or node["headRefOid"] != prev.get("last_head"))
        ci_moved = (node["headRefOid"] != prev.get("last_head")
                    or rollup != prev.get("last_rollup"))
        if not (moved or ci_moved or force):
            continue
        watch_pr = watch["prs"][str(n)]
        seen = {} if force else prev
        found = []
        signature = prev.get("last_signature", "")
        ci_signature = prev.get("last_ci_signature", "")
        try:
            if moved or force:
                pr = fetch_pr(gh, watch["owner"], watch["repo"], n)
                if watch_pr["role"] == "authored":
                    event, signature = evaluate_authored(watch, pr, watch_pr, seen)
                else:
                    event, signature = evaluate_reviewed(gh, watch, pr, seen)
                found.append(event)
            if watch_pr["role"] == "authored" and (ci_moved or force):
                event, ci_signature = evaluate_ci(gh, watch, n, node, seen)
                found.append(event)
        except GhError as exc:
            print(f"pr-watch poller: PR #{n}: {exc}", file=sys.stderr, flush=True)
            continue
        prs[str(n)] = {"updated_at": node["updatedAt"], "last_head": node["headRefOid"],
                       "last_signature": signature, "last_rollup": rollup,
                       "last_ci_signature": ci_signature}
        events += [e for e in found if e]
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


def all_ids(pr):
    ids = [c["id"] for t in pr["reviewThreads"]["nodes"] for c in t["comments"]["nodes"]]
    ids += [c["id"] for c in pr["comments"]["nodes"]]
    ids += [r["id"] for r in pr["reviews"]["nodes"]]
    return ids


def snip(body, width=300):
    return " ".join((body or "").split())[:width]


def attention_lines(watch, pr, watch_pr):
    me, allow = watch["self_login"], watch["bot_allowlist"]
    n = pr["number"]
    lines = []
    if watch_pr["role"] == "authored":
        threads, top = pending(pr, watch_pr, me, allow)
        for t, tail in threads:
            state = "resolved" if t["isResolved"] else "open"
            login, kind = classify(tail[-1]["author"], me, allow)
            lines.append(f"PR {n}  thread {t['path']}:{t['line']} [{state}]  "
                         f"{len(tail)} pending, last by {login} ({kind}): "
                         f"{snip(tail[-1]['body'])}")
        for surface, item in top:
            login, kind = classify(item["author"], me, allow)
            lines.append(f"PR {n}  {surface} by {login} ({kind}): {snip(item['body'])}")
    else:
        old = my_review_head(pr, me, allow)
        if my_threads(pr, me, allow) and old and old != pr["headRefOid"]:
            lines.append(f"PR {n}  head moved past your review: "
                         f"{old[:9]}..{pr['headRefOid'][:9]}")
    latest = {}
    for r in pr["reviews"]["nodes"]:
        login, kind = classify(r["author"], me, allow)
        if kind == "human" and r["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[login] = r
    for login, r in sorted(latest.items()):
        if r["state"] == "CHANGES_REQUESTED":
            lines.append(f"PR {n}  changes requested by {login}: "
                         f"{snip(r['body']) or '(no body)'}")
    return lines


def new_lines(pr, known, self_login, allowlist):
    n = pr["number"]
    lines = []
    for t in pr["reviewThreads"]["nodes"]:
        for c in t["comments"]["nodes"]:
            if c["id"] not in known:
                login, kind = classify(c["author"], self_login, allowlist)
                lines.append(f"PR {n}  [{kind}] thread {t['path']}:{t['line']}  "
                             f"{login}: {snip(c['body'])}")
    for c in pr["comments"]["nodes"]:
        if c["id"] not in known:
            login, kind = classify(c["author"], self_login, allowlist)
            lines.append(f"PR {n}  [{kind}] issue comment  {login}: {snip(c['body'])}")
    for r in pr["reviews"]["nodes"]:
        if r["id"] not in known:
            login, kind = classify(r["author"], self_login, allowlist)
            lines.append(f"PR {n}  [{kind}] review {r['state']}  {login}: "
                         f"{snip(r['body']) or '(no body)'}")
    return lines


def standing_line(pr, watch_pr, self_login, allowlist):
    threads = pr["reviewThreads"]["nodes"]
    authors = [c["author"] for t in threads for c in t["comments"]["nodes"]]
    authors += [c["author"] for c in pr["comments"]["nodes"]]
    authors += [r["author"] for r in pr["reviews"]["nodes"]]
    humans = sorted({login for login, kind in
                     (classify(a, self_login, allowlist) for a in authors) if kind == "human"})
    unresolved = sum(1 for t in threads if not t["isResolved"])
    return (f"PR {pr['number']}  {watch_pr['role']}  head={pr['headRefOid'][:9]}  "
            f"threads={len(threads)} unresolved={unresolved}  "
            f"humans: {', '.join(humans) or 'none'}")


def report(gh, state_dir, reseed=False):
    watch = read_json(state_dir / "watch.json")
    seen_path = state_dir / "watch-seen.json"
    seen = read_json(seen_path, default={})
    me, allow = watch["self_login"], watch["bot_allowlist"]
    first_run = not seen
    attention, new, standing, errors, notes = [], [], [], [], []
    fresh = dict(seen)
    for key in sorted(watch["prs"], key=int):
        watch_pr = watch["prs"][key]
        try:
            pr = fetch_pr(gh, watch["owner"], watch["repo"], int(key))
        except GhError as exc:
            errors.append(f"PR {key}: {exc}")
            continue
        notes += [f"PR {key}: {note}" for note in pr["truncated"]]
        attention += attention_lines(watch, pr, watch_pr)
        new += new_lines(pr, set(seen.get(key, [])), me, allow)
        standing.append(standing_line(pr, watch_pr, me, allow))
        fresh[key] = all_ids(pr)
    if fresh != seen:
        write_json_atomic(seen_path, fresh)
    for line in errors:
        print(f"ERROR  {line}")
    if reseed:
        print(f"pr-watch: reseeded; {sum(len(v) for v in fresh.values())} ids accepted as seen")
        return 1 if errors else 0
    if not (errors or attention or notes or new) and not first_run:
        print(f"pr-watch: nothing new across {len(standing)} PRs; nothing needs attention")
        return 0
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
    for line in notes:
        print(f"  note: {line}")
    return 1 if errors else 0


def findings_payload(gh, watch, pr):
    me, allow = watch["self_login"], watch["bot_allowlist"]
    old, new = my_review_head(pr, me, allow), pr["headRefOid"]
    files = changed_files(gh, watch["owner"], watch["repo"], old, new) if old and old != new else []
    return {
        "pr": pr["number"], "title": pr["title"], "url": pr["url"],
        "author": (pr.get("author") or {}).get("login"),
        "old_head": old, "new_head": new, "changed_files": files,
        "threads": [{
            "thread_id": t["id"], "path": t["path"], "line": t["line"],
            "is_resolved": t["isResolved"], "is_outdated": t["isOutdated"],
            "kinds": [classify(c["author"], me, allow)[1] for c in t["comments"]["nodes"]],
            "comments": [comment_record(c, "inline", me, allow, thread=t)
                         for c in t["comments"]["nodes"]],
        } for t in my_threads(pr, me, allow)],
        "truncated": pr.get("truncated", []),
    }


def base_conclusions(gh, repo_slug, ref):
    commit = f"repos/{repo_slug}/commits/{urllib.parse.quote(ref, safe='')}"
    rows = gh(["api", f"{commit}/check-runs", "--paginate",
               "--jq", ".check_runs[] | [.name, (.conclusion // .status)] | @tsv"]).splitlines()
    rows += gh(["api", f"{commit}/status",
                "--jq", ".statuses[] | [.context, .state] | @tsv"]).splitlines()
    out = {}
    for row in rows:
        name, _, value = row.partition("\t")
        if name and (name not in out or value in FAILED_BASE):
            out[name] = value
    return out


def checks_payload(gh, watch, number):
    slug = f"{watch['owner']}/{watch['repo']}"
    base, head = gh(["api", f"repos/{slug}/pulls/{number}",
                     "--jq", '.base.ref + " " + .head.sha']).split()
    on_base = base_conclusions(gh, slug, base)
    checks = [{"name": c["name"], "state": c.get("state"), "bucket": c.get("bucket"),
               "link": c.get("link"), "workflow": c.get("workflow") or "",
               "completed_at": c.get("completedAt"), "on_base": on_base.get(c["name"]),
               **check_platform(c.get("link"))}
              for c in required_checks(gh, slug, number)]
    return {"pr": number, "head": head, "base": base, "checks": checks}


def ado_request(url, method="GET", body=None, opener=None):
    pat = os.environ.get("AZURE_DEVOPS_EXT_PAT")
    if not pat:
        raise GhError("AZURE_DEVOPS_EXT_PAT is not set")
    token = base64.b64encode(f":{pat}".encode("ascii")).decode("ascii")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Basic {token}", "Content-Type": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise GhError(f"{method} {url.split('?')[0]}: {exc}") from None


def failed_records(timeline, kind):
    return [r for r in timeline.get("records") or []
            if r.get("type") == kind and r.get("result") == "failed"]


def last_lines(text, count=LOG_LINES):
    return "\n".join(text.splitlines()[-count:])


def ci_log(gh, repo_slug, link, ado=ado_request):
    target = check_platform(link)
    if target["platform"] == "github-actions":
        return last_lines(gh(["run", "view", "--job", target["job_id"], "--repo", repo_slug,
                              "--log-failed"]))
    if target["platform"] == "azure-pipelines":
        build = ADO_BUILD.format(**target)
        timeline = json.loads(ado(f"{build}/timeline?api-version=7.1"))
        parts = [f"== {r.get('name')} ==\n" + ado(f"{build}/logs/{r['log']['id']}?api-version=7.1")
                 for r in failed_records(timeline, "Task") if (r.get("log") or {}).get("id")]
        if not parts:
            raise GhError(f"no failed task log in build {target['build_id']}")
        return last_lines("\n".join(parts))
    raise GhError(f"no CI source for {link}")


def ci_rerun(gh, repo_slug, link, ado=ado_request):
    target = check_platform(link)
    if target["platform"] == "github-actions":
        gh(["run", "rerun", target["run_id"], "--failed", "--repo", repo_slug])
        return [f"run {target['run_id']}"]
    if target["platform"] == "azure-pipelines":
        build = ADO_BUILD.format(**target)
        timeline = json.loads(ado(f"{build}/timeline?api-version=7.1"))
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


def main(argv=None, gh=run_gh):
    parser = argparse.ArgumentParser(prog="poll.py", description="pr-watch poller")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--monitor", action="store_true",
                      help="print one JSON line per actionable change, forever")
    mode.add_argument("--report", action="store_true", help="print ATTENTION, NEW, STANDING")
    mode.add_argument("--reseed", action="store_true", help="accept every current id as seen")
    mode.add_argument("--baseline", type=int, metavar="PR", help="print the first-arm baseline")
    mode.add_argument("--tails", type=int, metavar="PR",
                      help="print pending tails as CommentRecords")
    mode.add_argument("--findings", type=int, metavar="PR",
                      help="print the user's threads on a reviewed PR")
    mode.add_argument("--checks", type=int, metavar="PR",
                      help="print the required checks on the PR head")
    mode.add_argument("--assert-author", type=int, metavar="PR",
                      help="exit 0 only if the acting login authored the PR")
    mode.add_argument("--ci-log", metavar="LINK",
                      help="print the last 5000 lines of the failed steps behind a check link")
    mode.add_argument("--ci-rerun", metavar="LINK",
                      help="rerun the failed jobs behind a check link")
    parser.add_argument("--state-dir", type=pathlib.Path, help="<main checkout>/.pr-autopilot")
    parser.add_argument("--repo", help="owner/name; required with --assert-author, --ci-log, --ci-rerun")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.assert_author is not None:
        if not args.repo:
            parser.error("--assert-author needs --repo owner/name")
        return assert_author(gh, args.repo, args.assert_author)
    if args.ci_log or args.ci_rerun:
        if not args.repo:
            parser.error("--ci-log and --ci-rerun need --repo owner/name")
        try:
            if args.ci_log:
                print(ci_log(gh, args.repo, args.ci_log))
            else:
                for line in ci_rerun(gh, args.repo, args.ci_rerun):
                    print(f"rerun started: {line}")
        except GhError as exc:
            print(f"pr-watch: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.state_dir is None:
        parser.error("--state-dir is required for this mode")
    if args.monitor:
        monitor(gh, args.state_dir)
        return 0
    if args.report or args.reseed:
        return report(gh, args.state_dir, reseed=args.reseed)
    watch = read_json(args.state_dir / "watch.json")
    if args.checks:
        print(json.dumps(checks_payload(gh, watch, args.checks), indent=2))
        return 0
    number = args.baseline or args.tails or args.findings
    pr = fetch_pr(gh, watch["owner"], watch["repo"], number)
    me, allow = watch["self_login"], watch["bot_allowlist"]
    if args.baseline:
        payload = baseline(pr, me, allow)
    elif args.tails:
        payload = tails_payload(pr, watch["prs"].get(str(number), {}), me, allow)
    else:
        payload = findings_payload(gh, watch, pr)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
