"""List repos and emit one person's GitHub messages as unredacted corpus records on stdout.

    python github_records.py repos --login <login> --since 2025-09-01
    python github_records.py records --repo owner/name --login <login> --since 2025-09-01 --until 2026-09-16

Pipe `records` straight into redact.py so nothing unredacted touches disk.
"""
import argparse
import json
import subprocess
import sys

PAGE = 100
SEARCH_LIMIT = "1000"


def gh_json(args, runner):
    result = runner(["gh", *args], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def pages(path, runner):
    separator = "&" if "?" in path else "?"
    page = 1
    while True:
        batch = gh_json(["api", f"{path}{separator}per_page={PAGE}&page={page}"], runner)
        yield from batch
        if len(batch) < PAGE:
            return
        page += 1


def in_window(ts, since, until):
    return since <= ts[:10] <= until


def number_from_url(url):
    return int(url.rstrip("/").rsplit("/", 1)[1])


def record(surface, ts, repo, thread, others, text):
    return {"channel": "github", "surface": surface, "ts": ts, "audience": repo,
            "thread": thread, "others": others, "text": text, "held_out": False}


def review_comment_records(comments, login, repo, since, until):
    participants = {}
    for c in comments:
        key = (number_from_url(c["pull_request_url"]), c.get("in_reply_to_id") or c["id"])
        participants.setdefault(key, set()).add(c["user"]["login"])
    records = []
    for c in comments:
        if c["user"]["login"] != login or not in_window(c["created_at"], since, until):
            continue
        number, root = number_from_url(c["pull_request_url"]), c.get("in_reply_to_id") or c["id"]
        records.append(record("review thread reply", c["created_at"], repo, f"{repo}#{number}/c{root}",
                              len(participants[(number, root)] - {login}), c["body"]))
    return records


def commenters(comments, url_field):
    by_number = {}
    for c in comments:
        by_number.setdefault(number_from_url(c[url_field]), set()).add(c["user"]["login"])
    return by_number


def issue_comment_records(comments, login, repo, since, until):
    by_number = commenters(comments, "issue_url")
    return [record("issue comment", c["created_at"], repo, f"{repo}#{number_from_url(c['issue_url'])}",
                   len(by_number[number_from_url(c["issue_url"])] - {login}), c["body"])
            for c in comments
            if c["user"]["login"] == login and in_window(c["created_at"], since, until)]


def pr_body_records(prs, login, repo, since, until, others_by_number):
    return [record("PR body", pr["created_at"], repo, f"{repo}#{pr['number']}",
                   len(others_by_number.get(pr["number"], set()) - {login}), pr["body"])
            for pr in prs
            if pr["user"]["login"] == login and pr.get("body") and in_window(pr["created_at"], since, until)]


def review_records(reviews, login, repo, number, pr_author, since, until):
    return [record("review summary", r["submitted_at"], repo, f"{repo}#{number}/r{r['id']}",
                   0 if pr_author == login else 1, r["body"])
            for r in reviews
            if r["user"]["login"] == login and r.get("body") and r.get("submitted_at")
            and in_window(r["submitted_at"], since, until)]


def discover_repos(login, since, runner):
    searches = [["prs", "--author"], ["prs", "--reviewed-by"], ["prs", "--commenter"], ["issues", "--commenter"]]
    repos = set()
    for kind, flag in searches:
        results = gh_json(["search", kind, flag, login, "--updated", f">={since}",
                           "--limit", SEARCH_LIMIT, "--json", "repository"], runner)
        repos.update(item["repository"]["nameWithOwner"] for item in results)
    return sorted(repos)


def collect(repo, login, since, until, runner):
    stamp = f"{since}T00:00:00Z"
    review_comments = list(pages(f"repos/{repo}/pulls/comments?since={stamp}", runner))
    issue_comments = list(pages(f"repos/{repo}/issues/comments?since={stamp}", runner))
    prs = []
    for pr in pages(f"repos/{repo}/pulls?state=all&sort=updated&direction=desc", runner):
        if pr["updated_at"][:10] < since:
            break
        prs.append(pr)
    others = commenters(issue_comments, "issue_url")
    for number, logins in commenters(review_comments, "pull_request_url").items():
        others.setdefault(number, set()).update(logins)

    records = review_comment_records(review_comments, login, repo, since, until)
    records += issue_comment_records(issue_comments, login, repo, since, until)
    records += pr_body_records(prs, login, repo, since, until, others)
    reviewed = gh_json(["search", "prs", "--repo", repo, "--reviewed-by", login, "--updated", f">={since}",
                        "--limit", SEARCH_LIMIT, "--json", "number,author"], runner)
    for pr in reviewed:
        reviews = pages(f"repos/{repo}/pulls/{pr['number']}/reviews", runner)
        records += review_records(reviews, login, repo, pr["number"], pr["author"]["login"], since, until)
    return sorted(records, key=lambda r: r["ts"], reverse=True)


def main(argv=None, runner=subprocess.run):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("repos")
    r.add_argument("--login", required=True)
    r.add_argument("--since", required=True, help="YYYY-MM-DD")
    c = sub.add_parser("records")
    c.add_argument("--repo", required=True)
    c.add_argument("--login", required=True)
    c.add_argument("--since", required=True, help="YYYY-MM-DD")
    c.add_argument("--until", required=True, help="YYYY-MM-DD, inclusive")
    args = parser.parse_args(argv)

    if args.command == "repos":
        for repo in discover_repos(args.login, args.since, runner):
            print(repo)
        return 0
    records = collect(args.repo, args.login, args.since, args.until, runner)
    for item in records:
        print(json.dumps(item, ensure_ascii=False))
    print(f"github_records: {args.repo} {len(records)} records", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
