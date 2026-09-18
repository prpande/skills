import contextlib
import io
import json
import pathlib
import sys
import types
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
SKILL = REPO / "skills" / "team-tooling" / "human-reply"
sys.path.insert(0, str(SKILL / "scripts"))

import corpus  # noqa: E402
import github_records  # noqa: E402

API = "https://api.github.com/repos/acme/web"


class FakeGh:
    """Answers `gh` argument lists from a dict; records every call."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, argv, **kwargs):
        key = " ".join(argv[1:])
        self.calls.append(key)
        if key not in self.answers:
            raise AssertionError(f"unexpected gh call: {key}")
        return types.SimpleNamespace(stdout=json.dumps(self.answers[key]))


def comment(cid, login, ts, body="text", reply_to=None, number=7, kind="pulls"):
    field = "pull_request_url" if kind == "pulls" else "issue_url"
    item = {"id": cid, "user": {"login": login}, "created_at": ts, "body": body, field: f"{API}/{kind}/{number}"}
    if reply_to:
        item["in_reply_to_id"] = reply_to
    return item


def answers():
    since = "2025-09-01T00:00:00Z"
    return {
        f"api repos/acme/web/pulls/comments?since={since}&per_page=100&page=1": [
            comment(1, "bot-reviewer", "2026-02-01T09:00:00Z"),
            comment(2, "me", "2026-02-01T10:00:00Z", "fixed in abc123", reply_to=1),
            comment(3, "me", "2025-08-01T10:00:00Z", "outside the window"),
        ],
        f"api repos/acme/web/issues/comments?since={since}&per_page=100&page=1": [
            comment(10, "me", "2026-03-01T10:00:00Z", "shipping this today", number=8, kind="issues"),
            comment(11, "ana", "2026-03-01T11:00:00Z", number=8, kind="issues"),
        ],
        "api repos/acme/web/pulls?state=all&sort=updated&direction=desc&per_page=100&page=1": [
            {"number": 8, "user": {"login": "me"}, "created_at": "2026-02-28T10:00:00Z",
             "updated_at": "2026-03-01T11:00:00Z", "body": "## Summary\nAdds retries"},
            {"number": 9, "user": {"login": "me"}, "created_at": "2026-02-27T10:00:00Z",
             "updated_at": "2026-02-27T10:00:00Z", "body": None},
            {"number": 2, "user": {"login": "me"}, "created_at": "2025-01-01T10:00:00Z",
             "updated_at": "2025-01-02T10:00:00Z", "body": "older than the window"},
        ],
        "search prs --repo acme/web --reviewed-by me --updated >=2025-09-01 --limit 1000 --json number,author": [
            {"number": 7, "author": {"login": "ana"}},
        ],
        "api repos/acme/web/pulls/7/reviews?per_page=100&page=1": [
            {"id": 55, "user": {"login": "me"}, "submitted_at": "2026-02-02T10:00:00Z", "body": "Looks right to me"},
            {"id": 56, "user": {"login": "me"}, "submitted_at": "2026-02-02T11:00:00Z", "body": ""},
        ],
    }


class CollectTests(unittest.TestCase):
    def test_each_surface_is_collected_in_the_window_newest_first(self):
        records = github_records.collect("acme/web", "me", "2025-09-01", "2026-09-16", FakeGh(answers()))
        self.assertEqual([(r["surface"], r["thread"], r["others"]) for r in records], [
            ("issue comment", "acme/web#8", 1),
            ("PR body", "acme/web#8", 1),
            ("review summary", "acme/web#7/r55", 1),
            ("review thread reply", "acme/web#7/c1", 1),
        ])

    def test_every_record_validates_against_the_module(self):
        surfaces = corpus.load_surfaces(SKILL / "channels" / "github.md")
        for item in github_records.collect("acme/web", "me", "2025-09-01", "2026-09-16", FakeGh(answers())):
            with self.subTest(thread=item["thread"]):
                self.assertEqual(corpus.validate_record(item, surfaces), [])

    def test_the_pull_list_stops_at_the_first_pr_updated_before_the_window(self):
        data = answers()
        data["api repos/acme/web/pulls?state=all&sort=updated&direction=desc&per_page=100&page=1"] = (
            [{"number": 100 + i, "user": {"login": "ana"}, "created_at": "2025-01-01T00:00:00Z",
              "updated_at": "2025-01-01T00:00:00Z", "body": "x"} for i in range(100)])
        fake = FakeGh(data)
        github_records.collect("acme/web", "me", "2025-09-01", "2026-09-16", fake)
        self.assertFalse(any("page=2" in call for call in fake.calls))

    def test_a_full_page_fetches_the_next_one(self):
        fake = FakeGh({"api x?per_page=100&page=1": [{"n": i} for i in range(100)],
                       "api x?per_page=100&page=2": [{"n": 100}]})
        self.assertEqual(len(list(github_records.pages("x", fake))), 101)


class ReposTests(unittest.TestCase):
    def test_repos_come_from_author_reviewer_and_commenter_searches(self):
        tail = ["--updated", ">=2025-09-01", "--limit", "1000", "--json", "repository"]
        fake = FakeGh({
            " ".join(["search", "prs", "--author", "me", *tail]): [{"repository": {"nameWithOwner": "acme/web"}}],
            " ".join(["search", "prs", "--reviewed-by", "me", *tail]): [{"repository": {"nameWithOwner": "acme/api"}}],
            " ".join(["search", "prs", "--commenter", "me", *tail]): [],
            " ".join(["search", "issues", "--commenter", "me", *tail]): [{"repository": {"nameWithOwner": "acme/web"}}],
        })
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = github_records.main(["repos", "--login", "me", "--since", "2025-09-01"], runner=fake)
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "acme/api\nacme/web\n")


class CliTests(unittest.TestCase):
    def test_records_prints_jsonl_and_a_count_on_stderr(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            code = github_records.main(["records", "--repo", "acme/web", "--login", "me", "--since", "2025-09-01",
                                        "--until", "2026-09-16"], runner=FakeGh(answers()))
        self.assertEqual(code, 0)
        self.assertEqual(len(out.getvalue().splitlines()), 4)
        self.assertEqual(err.getvalue(), "github_records: acme/web 4 records\n")


if __name__ == "__main__":
    unittest.main()
