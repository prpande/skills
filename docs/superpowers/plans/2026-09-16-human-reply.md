# human-reply Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks 4, 8, 10, and 12 open pull requests and Task 9 is run by the user; keep those in the main session.

**Goal:** Ship `human-reply`, a skill that drafts Slack, GitHub, and Notion messages in the user's measured voice after a guided setup, retire `slack-reply`, and let `pr-watch` draft its replies through it.

**Architecture:** Four stdlib Python scripts do the deterministic work of setup (redaction, corpus records and hold-outs, the AI-writing filter, measurement) plus one GitHub collector. Everything else is skill prose: a `SKILL.md` router, eight setup step files, three channel modules holding platform facts, and five references. Per-user profiles live in `~/.claude/human-reply/`, never in the repo.

**Tech Stack:** Python 3.8+ standard library, `unittest`, `gh` CLI, Slack and Notion MCP tools, Claude Code skills.

**Spec:** `docs/superpowers/specs/2026-09-16-human-reply-design.md`. Read it before any task; section numbers below refer to it.

## Global Constraints

- Python standard library only; scripts must run on Python 3.8 or later. `pytest` is not installed. Tests use `unittest` and run from the repo root with:
  ```
  python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v
  ```
- Never pass `newline=` to `Path.read_text` or `Path.write_text` (Python 3.13 only). Use `open(path, encoding="utf-8", newline="\n")`.
- Every file below is given in full. Write it byte for byte. The Python files spell some characters inside string literals as backslash-u escapes; a write tool that turns an escape into the literal character still produces a passing file, so either form is fine.
- Skill prose cites its own files as `human-reply/<dir>/<file>.md`, never a bare path starting at `references/`. `SKILL.md` must not name a `human-reply/setup/*.md` file in backticks, because it lands one PR before the setup files and `python scripts/validate.py` resolves every such path.
- No line may start with `TODO: `, `XXX `, `[TBD]`, or `[fill in` (validator placeholder scan).
- Code comments: default none; keep only a non-obvious why.
- One build or test command at a time, foreground, timeout at least 300000 ms.
- Each PR changes at most 15 files, tests included. Check `git diff origin/main --stat` (or against the PR's base branch) before `gh pr create`.
- Commits and PR bodies carry no attribution: no `Co-Authored-By` trailer, no session link, no "Generated with" footer.
- Before each commit, scan the staged files for secret-shaped text. `human-reply/references/redaction-check.md` and the test fixtures split every secret with `{join}` or build it at runtime for this reason; keep them that way.
- On this machine the Bash tool is proxied and blocks compound or index-writing git (exit 126). Write the commit message to `<scratchpad>/msg.txt` with the Write tool and commit from PowerShell in the worktree:
  ```powershell
  Start-Process git -ArgumentList @('add','--',<paths...>) -NoNewWindow -Wait
  Start-Process git -ArgumentList @('commit','-F','"<scratchpad>\msg.txt"') -NoNewWindow -Wait
  ```
- All edits happen in a git worktree, never in the launch checkout. Enter each PR's worktree with `EnterWorktree`.
- Nothing in this plan posts to Slack, GitHub comments, or Notion. The skill itself never lists or calls a send tool.

## Deviations from the spec

Recorded so a reviewer does not read them as drift.

- **`others` field.** Corpus records carry `others`, the count of thread participants who are not the person. The hold-out rule in spec 3.3 needs it; the spec's record example omits it.
- **Extra reference and scripts.** `human-reply/references/redaction-check.md` is the single fixture for both redaction paths (spec 3.3 and 8). `scripts/corpus.py` holds the record schema, word counting, `normalize`, `oldest`, and hold-out selection; `scripts/ai_filter.py` implements the filter; `scripts/github_records.py` is the GitHub collector, so its surface assignment is tested rather than improvised.
- **Machine-read blocks.** Channel modules carry a `surfaces` block (`name | minimum | default`) and an `ai-filter` block (`id` or `id | exempt: a, b`). `human-reply/references/ai-filter.md` carries a `vocabulary` block.
- **`tldr-block`** matches only "TL;DR" and "TLDR". A "Summary" header scores under `headers-bold-labels`, because native PR bodies open with `## Summary`.
- **Known filter miss.** The Slack design-share "sent" message from the `slack-reply` shapes file scores 2 (em dash, emoji section marker) and is kept at the default threshold of 3. The test records this instead of asserting "each side lands where it should".
- **Percentiles** use the nearest-rank method.
- **Redaction** copies rules 1 to 12 of `pr-loop-lib/references/secret-scan-rules.md` verbatim and leaves out rule 13, which applies to `.env` files only. Rule 1 is widened to remove the whole PEM block, key body included.
- **Budgets.** Minimum and default per surface come from the `slack-reply` tiers and `pr-watch`'s 60-word cap. The GitHub values other than review thread reply, and the Notion values, were set without corpus data.
- **Slack re-windowing** restarts at the day after the oldest captured message, a one-day overlap removed by `normalize`, so no message on the boundary day is lost.
- **pr-watch gate** checks the Surfaces row of the surface being written: `review thread reply` for thread replies, `issue comment` for top-level replies. The spec names only the first row; top-level replies land on the second surface.
- **pr-watch fallback note** goes to the PR's Slack thread as a new "voice fallback" line, since `pr-watch` has no run summary.
- **Historical docs.** Backticked paths to files this plan deletes or renames (`slack-reply/...`, the old pr-watch reply guide) are rewritten to their full `skills/...` form, which the validator does not resolve. The text keeps its meaning.
- **PR split.** `SKILL.md` ships in the first PR: without a `.md` file directly in `human-reply/`, the validator would treat `human-reply/channels/` and `human-reply/references/` as separate skill roots named `channels` and `references`, and every other skill's bare path starting at `references/` would resolve against the wrong folder. The design docs ship in the last PR, once every path they cite exists.
- **Tests** use `unittest`, not pytest (spec 9), matching `skill-tests/pr-watch/`.

## PR map

| PR | Branch | Base | Tasks | Files |
|---|---|---|---|---|
| 1 engine | `human-reply-engine` | `main` | 1–4 | 15 |
| 2 setup | `human-reply-setup` | `human-reply-engine` | 5–9 | 13 |
| 3 retire slack-reply | `retire-slack-reply` | `human-reply-setup` | 10 | 6 |
| 4 pr-watch and docs | `pr-watch-human-reply` | `retire-slack-reply` | 11–12 | 11 |

PR 3 must not open until Task 9's acceptance item 1 passes (spec 10 step 3). Task 13 is a local memory edit, not a PR.

## File map

| File | Responsibility | Task |
|---|---|---|
| `skills/team-tooling/human-reply/scripts/corpus.py` | record schema, word count, normalize, oldest, hold-outs | 1 |
| `skills/team-tooling/human-reply/channels/slack.md` | Slack surfaces, markup, shapes, audit, filter patterns | 1 |
| `skills/team-tooling/human-reply/channels/github.md` | GitHub surfaces, markup, shapes, audit, filter patterns | 1 |
| `skills/team-tooling/human-reply/channels/notion.md` | Notion surfaces, markup, shapes, audit, filter patterns | 1 |
| `skills/team-tooling/human-reply/references/corpus-record.md` | the JSONL record shape | 1 |
| `skill-tests/human-reply/tests/test_corpus.py` | tests for corpus.py and the surfaces blocks | 1 |
| `skills/team-tooling/human-reply/scripts/redact.py` | secret redaction on stdin records | 2 |
| `skills/team-tooling/human-reply/references/redaction-check.md` | known-bad and known-clean redaction cases | 2 |
| `skill-tests/human-reply/tests/test_redact.py` | tests for redact.py | 2 |
| `skills/team-tooling/human-reply/scripts/ai_filter.py` | scaffolding score and drop | 3 |
| `skills/team-tooling/human-reply/references/ai-filter.md` | pattern definitions, threshold, vocabulary | 3 |
| `skill-tests/human-reply/tests/test_ai_filter.py` | tests for ai_filter.py | 3 |
| `skills/team-tooling/human-reply/SKILL.md` | router, runtime workflow, output contract | 4 |
| `skills/team-tooling/human-reply/references/profile-schema.md` | profile formats and reader return format | 4 |
| `skills/team-tooling/human-reply/references/humanizer-handoff.md` | the humanizer instruction | 4 |
| `skills/team-tooling/human-reply/scripts/measure.py` | per-surface numbers and budgets | 5 |
| `skill-tests/human-reply/tests/test_measure.py` | tests for measure.py | 5 |
| `skills/team-tooling/human-reply/scripts/github_records.py` | GitHub repo discovery and records | 6 |
| `skill-tests/human-reply/tests/test_github_records.py` | tests for github_records.py | 6 |
| `skills/team-tooling/human-reply/setup/01-detect.md` … `04-filter.md` | setup steps 1 to 4 | 7 |
| `skills/team-tooling/human-reply/setup/05-measure.md` … `08-finish.md` | setup steps 5 to 8 | 8 |
| `README.md` | skills table, install lines, design doc links | 8, 10, 12 |
| `skills/team-tooling/slack-reply/` | deleted | 10 |
| `skills/pr-tooling/pr-watch/references/reply-contract.md` | posting contract and the human-reply gate | 11 |
| `skills/pr-tooling/pr-watch/SKILL.md` and its `04-fix-path`, `05-rereview`, `06-notify` steps | point replies at the contract | 11 |
| `docs/superpowers/specs/2026-09-16-human-reply-design.md`, `docs/superpowers/plans/2026-09-16-human-reply.md` | design docs | 12 |

---

## PR 1: engine

Worktree: create with `EnterWorktree` from `origin/main`, then `git switch -c human-reply-engine`.

### Task 1: Corpus records and channel modules

**Files:**
- Create: `skills/team-tooling/human-reply/scripts/corpus.py`
- Create: `skills/team-tooling/human-reply/channels/slack.md`
- Create: `skills/team-tooling/human-reply/channels/github.md`
- Create: `skills/team-tooling/human-reply/channels/notion.md`
- Create: `skills/team-tooling/human-reply/references/corpus-record.md`
- Test: `skill-tests/human-reply/tests/test_corpus.py`

**Interfaces:**
- Consumes: nothing.
- Produces, in `corpus.py`:
  - `FIELDS: dict[str, type]` for `channel, surface, ts, audience, thread, others, text, held_out`; `HOLDOUTS_PER_CHANNEL = 3`
  - `read_jsonl(path) -> list[dict]`, `write_jsonl(path, records) -> None`
  - `fenced_block(markdown: str, tag: str) -> list[str]`, raising `ValueError` when the block is missing
  - `load_surfaces(module_path) -> dict[str, {"minimum": int, "default": int}]` in module order
  - `word_count(text) -> int`, `record_id(record) -> "<audience>/<ts>"`, `is_pre_cutoff(record, cutoff: str | None) -> bool`
  - `validate_record(record, surfaces) -> list[str]`
  - `normalize(records, cap) -> list[dict]` newest first, `oldest_ts(records) -> str | None`
  - `select_holdouts(records, cutoff, seed, passed_ids=None) -> list[(thread, pool)]`, pool one of `earlier`, `pre-cutoff`, `post-cutoff`; marks `held_out` in place
  - CLI `corpus.py validate|holdout|normalize|oldest`
- Produces, in each channel module: a `surfaces` fenced block and an `ai-filter` fenced block.

- [ ] **Step 1: Write the failing test**

````python
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
SKILL = REPO / "skills" / "team-tooling" / "human-reply"
sys.path.insert(0, str(SKILL / "scripts"))

import corpus  # noqa: E402

MODULES = {name: SKILL / "channels" / f"{name}.md" for name in ("slack", "github", "notion")}


def record(thread, ts, others=1, surface="outer DM", text="hello there", held_out=False, audience="D1"):
    return {"channel": "slack", "surface": surface, "ts": ts, "audience": audience,
            "thread": thread, "others": others, "text": text, "held_out": held_out}


class SurfaceTests(unittest.TestCase):
    def test_each_module_lists_the_spec_surfaces_in_order(self):
        expected = {
            "slack": ["inner-circle DM", "outer DM", "group DM", "channel thread reply", "channel new post", "write-up"],
            "github": ["review thread reply", "review summary", "PR body", "issue comment"],
            "notion": ["page comment", "inline comment"],
        }
        for name, path in MODULES.items():
            with self.subTest(channel=name):
                self.assertEqual(list(corpus.load_surfaces(path)), expected[name])

    def test_every_minimum_is_a_positive_multiple_of_ten_at_or_below_its_default(self):
        for name, path in MODULES.items():
            for surface, limits in corpus.load_surfaces(path).items():
                with self.subTest(channel=name, surface=surface):
                    self.assertEqual(limits["minimum"] % 10, 0)
                    self.assertGreater(limits["minimum"], 0)
                    self.assertLessEqual(limits["minimum"], limits["default"])

    def test_a_missing_block_is_an_error(self):
        with self.assertRaises(ValueError):
            corpus.fenced_block("no fences here", "surfaces")


class ValidateTests(unittest.TestCase):
    surfaces = {"outer DM": {"minimum": 20, "default": 50}}

    def test_a_good_record_has_no_errors(self):
        self.assertEqual(corpus.validate_record(record("D1/1", "2026-03-04T10:12:00Z"), self.surfaces), [])

    def test_each_defect_is_named(self):
        bad = record("D1/1", "2026-03-04 10:12", surface="channel post")
        bad["others"] = "2"
        bad["author"] = "someone"
        del bad["held_out"]
        self.assertEqual(corpus.validate_record(bad, self.surfaces), [
            "field others is not int",
            "missing field held_out",
            "unknown fields ['author']",
            "surface 'channel post' is not in the channel module",
            "ts '2026-03-04 10:12' is not YYYY-MM-DDTHH:MM:SSZ",
        ])

    def test_cli_exits_one_and_prints_each_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "slack.jsonl"
            corpus.write_jsonl(path, [record("D1/1", "2026-03-04T10:12:00Z"),
                                      record("D1/2", "2026-03-04T10:12:00Z", surface="nope")])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = corpus.main(["validate", "--corpus", str(path), "--module", str(MODULES["slack"])])
        self.assertEqual(code, 1)
        self.assertIn(":2: surface 'nope' is not in the channel module", out.getvalue())
        self.assertTrue(out.getvalue().endswith("corpus: 2 records, 1 errors\n"))


class WordCountTests(unittest.TestCase):
    def test_links_and_fenced_blocks_count_as_one_word_each(self):
        text = ("see <https://nr.example/q?x=1|NR captures> and [the doc](https://notion.so/p) "
                "then\n```\nline one of a trace\nline two\n```\ndone")
        self.assertEqual(corpus.word_count(text), 7)

    def test_inline_code_counts_its_words(self):
        self.assertEqual(corpus.word_count("check `tbl Resource` now"), 4)


class CutoffTests(unittest.TestCase):
    def test_the_cutoff_month_counts_as_after(self):
        self.assertTrue(corpus.is_pre_cutoff(record("t", "2025-12-31T23:59:59Z"), "2026-01"))
        self.assertFalse(corpus.is_pre_cutoff(record("t", "2026-01-01T00:00:00Z"), "2026-01"))

    def test_no_cutoff_means_everything_is_before(self):
        self.assertTrue(corpus.is_pre_cutoff(record("t", "2026-09-01T00:00:00Z"), None))


class NormalizeTests(unittest.TestCase):
    def test_repeated_ids_collapse_and_the_newest_are_kept_newest_first(self):
        records = [record("D1/1", "2025-01-01T00:00:00Z"), record("D1/2", "2025-03-01T00:00:00Z"),
                   record("D1/2", "2025-03-01T00:00:00Z", text="resumed copy"), record("D1/3", "2025-02-01T00:00:00Z")]
        kept = corpus.normalize(records, cap=2)
        self.assertEqual([r["ts"] for r in kept], ["2025-03-01T00:00:00Z", "2025-02-01T00:00:00Z"])
        self.assertEqual(kept[0]["text"], "hello there")

    def test_cli_normalize_rewrites_and_oldest_prints_the_resume_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "slack.jsonl"
            corpus.write_jsonl(path, [record("D1/1", "2025-01-01T00:00:00Z"), record("D1/2", "2025-03-01T00:00:00Z")])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(corpus.main(["normalize", "--corpus", str(path), "--cap", "1"]), 0)
                self.assertEqual(corpus.main(["oldest", "--corpus", str(path)]), 0)
        self.assertEqual(out.getvalue(), "corpus: 2 records in, 1 kept\n2025-03-01T00:00:00Z\n")

    def test_oldest_of_an_empty_corpus_is_none(self):
        self.assertIsNone(corpus.oldest_ts([]))


class HoldoutTests(unittest.TestCase):
    def test_three_pre_cutoff_threads_with_another_participant_are_marked(self):
        records = [record(f"D1/{i}", "2025-06-01T00:00:00Z") for i in range(6)]
        records.append(record("D1/solo", "2025-06-01T00:00:00Z", others=0))
        records.append(record("D1/late", "2026-06-01T00:00:00Z"))
        chosen = corpus.select_holdouts(records, "2026-01", seed=7)
        self.assertEqual(len(chosen), 3)
        self.assertTrue(all(pool == "pre-cutoff" for _, pool in chosen))
        threads = {t for t, _ in chosen}
        self.assertNotIn("D1/solo", threads)
        self.assertNotIn("D1/late", threads)
        self.assertEqual({r["thread"] for r in records if r["held_out"]}, threads)

    def test_the_same_seed_picks_the_same_threads(self):
        make = lambda: [record(f"D1/{i}", "2025-06-01T00:00:00Z") for i in range(10)]
        self.assertEqual(corpus.select_holdouts(make(), "2026-01", seed=3),
                         corpus.select_holdouts(make(), "2026-01", seed=3))

    def test_a_dm_with_one_other_participant_qualifies(self):
        records = [record("D1/1", "2025-06-01T00:00:00Z", others=1)]
        self.assertEqual(corpus.select_holdouts(records, None, seed=1), [("D1/1", "pre-cutoff")])

    def test_no_cutoff_draws_from_the_whole_window(self):
        records = [record("D1/1", "2026-08-01T00:00:00Z"), record("D1/2", "2026-09-01T00:00:00Z")]
        chosen = corpus.select_holdouts(records, None, seed=1)
        self.assertEqual(sorted(chosen), [("D1/1", "pre-cutoff"), ("D1/2", "pre-cutoff")])

    def test_a_thread_straddling_the_cutoff_is_in_neither_pool(self):
        records = [record("D1/1", "2025-12-30T00:00:00Z"), record("D1/1", "2026-01-02T00:00:00Z", text="later")]
        passed = {corpus.record_id(r) for r in records}
        self.assertEqual(corpus.select_holdouts(records, "2026-01", seed=1, passed_ids=passed), [])

    def test_post_cutoff_threads_fill_the_remainder_only_when_every_record_passed(self):
        records = [record("D1/pre", "2025-06-01T00:00:00Z"),
                   record("D1/ok", "2026-03-01T00:00:00Z", audience="D2"),
                   record("D1/dropped", "2026-03-02T00:00:00Z", audience="D3")]
        first = corpus.select_holdouts(records, "2026-01", seed=1)
        self.assertEqual(first, [("D1/pre", "pre-cutoff")])
        passed = {"D2/2026-03-01T00:00:00Z"}
        second = corpus.select_holdouts(records, "2026-01", seed=1, passed_ids=passed)
        self.assertEqual(second, [("D1/pre", "earlier"), ("D1/ok", "post-cutoff")])

    def test_no_qualifying_thread_returns_an_empty_list(self):
        records = [record("D1/1", "2025-06-01T00:00:00Z", others=0)]
        self.assertEqual(corpus.select_holdouts(records, "2026-01", seed=1, passed_ids=set()), [])
        self.assertFalse(records[0]["held_out"])

    def test_cli_rewrites_the_corpus_and_prints_the_pools(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "slack.jsonl"
            corpus.write_jsonl(path, [record("D1/1", "2025-06-01T00:00:00Z")])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = corpus.main(["holdout", "--corpus", str(path), "--cutoff", "2026-01", "--seed", "4"])
            rewritten = corpus.read_jsonl(path)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue()), [{"thread": "D1/1", "pool": "pre-cutoff"}])
        self.assertTrue(rewritten[0]["held_out"])

    def test_cli_reset_clears_marks_left_by_an_earlier_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "slack.jsonl"
            corpus.write_jsonl(path, [record("D1/late", "2026-03-01T00:00:00Z", held_out=True),
                                      record("D1/early", "2025-03-01T00:00:00Z", audience="D2")])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                corpus.main(["holdout", "--corpus", str(path), "--cutoff", "2026-01", "--seed", "4", "--reset"])
            rewritten = corpus.read_jsonl(path)
        self.assertEqual(json.loads(out.getvalue()), [{"thread": "D1/early", "pool": "pre-cutoff"}])
        self.assertEqual([r["held_out"] for r in rewritten], [False, True])


if __name__ == "__main__":
    unittest.main()
````

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `ModuleNotFoundError: No module named 'corpus'`.

- [ ] **Step 3: Write `corpus.py`**

````python
"""Corpus records for human-reply setup: read, validate, count words, pick hold-outs.

    python corpus.py validate --corpus <channel>.jsonl --module channels/<channel>.md
    python corpus.py holdout --corpus <channel>.jsonl --cutoff 2026-01|never --seed N [--passed kept.jsonl] [--reset]
    python corpus.py normalize --corpus <channel>.jsonl --cap 1500
    python corpus.py oldest --corpus <channel>.jsonl
"""
import argparse
import json
import random
import re
import sys

FIELDS = {
    "channel": str,
    "surface": str,
    "ts": str,
    "audience": str,
    "thread": str,
    "others": int,
    "text": str,
    "held_out": bool,
}
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FENCED_CODE = re.compile(r"```[\s\S]*?```")
SLACK_LINK = re.compile(r"<https?://[^>\n]+>")
MARKDOWN_LINK = re.compile(r"\[[^\]\n]*\]\([^)\s]+\)")
HOLDOUTS_PER_CHANNEL = 3


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def fenced_block(markdown, tag):
    """Lines inside the first ```<tag> fence, without blanks or # comments."""
    match = re.search(rf"^```{re.escape(tag)}[ \t]*\n(.*?)^```", markdown, re.S | re.M)
    if not match:
        raise ValueError(f"no ```{tag} block")
    lines = [line.strip() for line in match.group(1).splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def load_surfaces(module_path):
    """{surface: {"minimum": int, "default": int}} in module order."""
    with open(module_path, encoding="utf-8") as f:
        lines = fenced_block(f.read(), "surfaces")
    surfaces = {}
    for line in lines:
        name, minimum, default = [part.strip() for part in line.split("|")]
        surfaces[name] = {"minimum": int(minimum), "default": int(default)}
    return surfaces


def word_count(text):
    """Whitespace tokens, with each fenced block and each link counted as one."""
    text = FENCED_CODE.sub(" CODE ", text)
    text = SLACK_LINK.sub(" LINK ", text)
    text = MARKDOWN_LINK.sub(" LINK ", text)
    return len(text.split())


def record_id(record):
    return f"{record['audience']}/{record['ts']}"


def is_pre_cutoff(record, cutoff):
    """cutoff is "YYYY-MM" or None; a message sent in the cutoff month is after it."""
    return cutoff is None or record["ts"][:7] < cutoff


def validate_record(record, surfaces):
    errors = []
    for field, kind in FIELDS.items():
        if field not in record:
            errors.append(f"missing field {field}")
        elif type(record[field]) is not kind:
            errors.append(f"field {field} is not {kind.__name__}")
    extra = set(record) - set(FIELDS)
    if extra:
        errors.append(f"unknown fields {sorted(extra)}")
    if isinstance(record.get("surface"), str) and record["surface"] not in surfaces:
        errors.append(f"surface {record['surface']!r} is not in the channel module")
    if isinstance(record.get("ts"), str) and not TS.match(record["ts"]):
        errors.append(f"ts {record['ts']!r} is not YYYY-MM-DDTHH:MM:SSZ")
    if isinstance(record.get("others"), int) and record["others"] < 0:
        errors.append("others is negative")
    return errors


def normalize(records, cap):
    """Drop repeated ids, keep the newest `cap` records, newest first."""
    unique = {}
    for record in records:
        unique.setdefault(record_id(record), record)
    return sorted(unique.values(), key=lambda r: r["ts"], reverse=True)[:cap]


def oldest_ts(records):
    return min((r["ts"] for r in records), default=None)


def _threads(records):
    threads = {}
    for record in records:
        threads.setdefault(record["thread"], []).append(record)
    return threads


def select_holdouts(records, cutoff, seed, passed_ids=None):
    """Mark up to three threads held out and return [(thread, pool)] for every held-out thread.

    Threads already held out are kept. The pre-cutoff pool (the whole window
    when cutoff is None) is drawn first. Only when a cutoff exists and
    passed_ids is given does the post-cutoff pool fill the remainder, and
    only with threads whose every record passed the filter.
    """
    rng = random.Random(seed)
    threads = _threads(records)
    chosen = [(t, "earlier") for t, rs in threads.items() if any(r["held_out"] for r in rs)]
    eligible = {t: rs for t, rs in threads.items()
                if max(r["others"] for r in rs) >= 1 and t not in dict(chosen)}
    pre = sorted(t for t, rs in eligible.items() if all(is_pre_cutoff(r, cutoff) for r in rs))
    pools = [("pre-cutoff", pre)]
    if cutoff is not None and passed_ids is not None:
        post = sorted(t for t, rs in eligible.items()
                      if not any(is_pre_cutoff(r, cutoff) for r in rs)
                      and all(record_id(r) in passed_ids for r in rs))
        pools.append(("post-cutoff", post))
    for name, pool in pools:
        need = HOLDOUTS_PER_CHANNEL - len(chosen)
        if need <= 0:
            break
        for thread in rng.sample(pool, min(need, len(pool))):
            chosen.append((thread, name))
    held = dict(chosen)
    for record in records:
        if record["thread"] in held:
            record["held_out"] = True
    return chosen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--corpus", required=True)
    v.add_argument("--module", required=True)
    h = sub.add_parser("holdout")
    h.add_argument("--corpus", required=True)
    h.add_argument("--cutoff", required=True, help="YYYY-MM, or never")
    h.add_argument("--seed", required=True, type=int)
    h.add_argument("--passed", help="JSONL of records that passed the filter")
    h.add_argument("--reset", action="store_true", help="clear every hold-out mark before choosing")
    n =sub.add_parser("normalize")
    n.add_argument("--corpus", required=True)
    n.add_argument("--cap", required=True, type=int)
    o = sub.add_parser("oldest")
    o.add_argument("--corpus", required=True)
    args = parser.parse_args(argv)

    records = read_jsonl(args.corpus)
    if args.command == "normalize":
        kept = normalize(records, args.cap)
        write_jsonl(args.corpus, kept)
        print(f"corpus: {len(records)} records in, {len(kept)} kept")
        return 0
    if args.command == "oldest":
        print(oldest_ts(records) or "none")
        return 0
    if args.command == "validate":
        surfaces = load_surfaces(args.module)
        bad = 0
        for index, record in enumerate(records, 1):
            for error in validate_record(record, surfaces):
                bad += 1
                print(f"{args.corpus}:{index}: {error}")
        print(f"corpus: {len(records)} records, {bad} errors")
        return 1 if bad else 0

    cutoff = None if args.cutoff == "never" else args.cutoff
    passed = {record_id(r) for r in read_jsonl(args.passed)} if args.passed else None
    if args.reset:
        for record in records:
            record["held_out"] = False
    chosen = select_holdouts(records, cutoff, args.seed, passed)
    write_jsonl(args.corpus, records)
    print(json.dumps([{"thread": t, "pool": p} for t, p in chosen]))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
````

- [ ] **Step 4: Write the three channel modules and the record reference**

`skills/team-tooling/human-reply/channels/slack.md`:

````markdown
# Slack channel module

What is true of Slack for every person. The person's own numbers,
phrasebook, and examples live in `~/.claude/human-reply/channels/slack.md`,
written by setup. When the two disagree on a number, the profile wins; on
markup, this file wins.

## Surfaces

| Surface | Who reads it | Collector assigns it when | Default register |
|---|---|---|---|
| inner-circle DM | a person the interview named as inner circle, 1:1 | a 1:1 DM whose other member is on the inner-circle list | no greeting, no sign-off |
| outer DM | anyone else, 1:1 | any other 1:1 DM | greeting only on first contact of the day |
| group DM | a small ad-hoc group | a multi-person DM | as outer DM |
| channel thread reply | squad and project channels | a channel message inside a thread | no greeting |
| channel new post | another squad's channel, a guild, platform support | a top-level channel message of 120 words or fewer | one greeting line |
| write-up | any channel | a top-level channel message over 120 words | no greeting; one code block or link list at most |

The minimum is the smallest budget a measured profile may derive. The
default is the budget a surface gets when it has fewer than 30 pre-cutoff
records. Both are word counts with each link and fenced block counted as
one word.

```surfaces
# surface | minimum | default
inner-circle DM | 10 | 20
outer DM | 20 | 50
group DM | 20 | 50
channel thread reply | 20 | 60
channel new post | 40 | 120
write-up | 60 | 150
```

Anything over the budget belongs in a Notion page, a PR body, or a second
message in the thread. Slack carries the pointer and the ask.

## Markup that survives sending

Drafts are delivered as markdown and pasted into Slack, or sent through the
Slack tool by the person. Three conversions bite:

- A `>` line swallows every following line until a blank line. Put a blank
  line after each quoted line, before the answer, and another before the
  next quote.
- Inline code needs backticks; plain identifiers come out as prose. Table
  names, endpoints, class and method names, flags, error strings, and
  header names go in backticks. A snippet over one line goes in a fenced
  block.
- A bare URL at the end of a line can swallow the newline and the next
  word into the link. End the URL with punctuation or write
  `[title](url)`.

Mentions are `<@name>` for a person and `<!subteam^id>` for a group; in a
draft, write `@name` and let the person resolve it when pasting.

## Shapes

Skeletons only. Angle brackets are slots. The profile adds the person's
own examples per shape.

In-thread reply, one point:

```
<the point in one sentence>. <one sentence of evidence or reasoning, link inline>.
```

Answering several questions:

```
> <question one>

<answer>

> <question two>

<answer>
```

Cross-team ask:

```
<greeting and name>
<one or two sentences: what we are doing and why we are here, link inline>
<the ask as a question; two or more asks become a numbered list>
<sign-off line>
<cc line>
```

PR review request:

```
<greeting> <what the PR does, one clause>. <ask>.
<PR link and title>
<sign-off line>
```

Investigation update:

```
<headline: what was found>
<two to four lines: the mechanism, numbers and links inline>
<one line: workaround or next step>
```

Design or doc share:

```
<greeting>
<one sentence: what the doc proposes and for which flow>. <doc link inline>.
<the ask>
```

Pushback:

```
<the disagreement in one sentence>. <the reason in one sentence>.
```

Heads-up:

```
<the fact in one sentence>. <what it means for the reader, link inline>.
```

The default shape when none matches is the in-thread reply.

## Audit checklist

1. The first line of output named the channel, surface, budget, and
   profile provenance, and the draft is inside that budget.
2. The point is in the first line of the draft.
3. At most one ask.
4. Evidence is a link, a number, or a short code block inline, not a
   paragraph.
5. No headers, no bold labels, no TL;DR block on top, no nested bullets;
   emoji section markers only where the profile's shapes use them.
6. Nothing the thread already says is repeated.
7. Identifiers in backticks, snippets in fenced blocks, a blank line after
   every `>` line, no bare URL ending a line.
8. Read once as the recipient: they can act with at most one linked doc
   open.

## AI-filter patterns

The scaffolding patterns scored on this channel by
`human-reply/references/ai-filter.md`, one id per line. An `exempt:` list
names surfaces where the pattern is the native form and does not score.

```ai-filter
emoji-section-marker
tldr-block
labelled-list
headers-bold-labels
em-dash
parallel-triple
closing-restatement
vocabulary
not-x-but-y
```
````

`skills/team-tooling/human-reply/channels/github.md`:

````markdown
# GitHub channel module

What is true of GitHub for every person. The person's own numbers,
phrasebook, and examples live in `~/.claude/human-reply/channels/github.md`,
written by setup. When the two disagree on a number, the profile wins; on
markup, this file wins.

## Surfaces

| Surface | Who reads it | Collector assigns it when | Default register |
|---|---|---|---|
| review thread reply | the PR author or a reviewer, on one line of code | a pull request review comment (`pulls/comments`) | no greeting, no sign-off |
| review summary | the PR author | the body of a submitted review, when not empty | no greeting |
| PR body | every reviewer | the body of a pull request the person opened | headers and lists allowed |
| issue comment | everyone watching the issue or PR conversation | a comment on an issue or on a PR's conversation tab (`issues/comments`) | no greeting |

The minimum is the smallest budget a measured profile may derive. The
default is the budget a surface gets when it has fewer than 30 pre-cutoff
records. Both are word counts with each link and fenced block counted as
one word.

```surfaces
# surface | minimum | default
review thread reply | 20 | 60
review summary | 20 | 80
PR body | 40 | 200
issue comment | 20 | 80
```

## Markup

GitHub renders GitHub Flavored Markdown on every surface.

- Cite code with a link to the line range at a commit:
  `https://github.com/<owner>/<repo>/blob/<sha>/<path>#L10-L20`. Line
  numbers go in the link, not in the prose.
- An exact proposed change goes in a `suggestion` fenced block on a review
  thread reply, and nowhere else.
- `@login` notifies the person. Never mention a bot account.
- `#123` links an issue or PR in the same repo; `owner/repo#123` across
  repos.
- A `>` line quotes; a blank line ends the quote.
- Identifiers go in backticks, multi-line snippets in fenced blocks with a
  language tag.

## Shapes

Skeletons only. Angle brackets are slots. The profile adds the person's
own examples per shape.

Fixed, on a review thread reply:

```
<what changed, one clause>, in <short sha>
```

Refuted, on a review thread reply:

```
<what the code does, one clause> <line-range link at a commit>
```

Superseded:

```
<what the code says now>, since <short sha>
```

Answered and left open:

```
<what is pending> <why, one clause>
```

Review summary:

```
<the verdict in one sentence>
<one line per blocking point, each pointing at its thread>
```

PR body:

```
<what the PR does and why, two or three sentences>
<changes, as a list when there are three or more>
<how it was tested>
```

Issue comment:

```
<the answer or the finding in one sentence>. <evidence, link inline>.
```

The default shape when none matches is the issue comment.

## Audit checklist

1. The first line of output named the channel, surface, budget, and
   profile provenance, and the draft is inside that budget.
2. The substance is in the first sentence.
3. Every identifier in backticks, every multi-line snippet in a fenced
   block, every code citation a line-range link at a commit or a
   repo-relative path.
4. Nothing from the comment being answered is repeated.
5. No greeting or thanks-opener on a review thread reply, review summary,
   or issue comment.
6. No @-mention of a bot account.
7. No promise of future work with a date.

## AI-filter patterns

The scaffolding patterns scored on this channel by
`human-reply/references/ai-filter.md`, one id per line. An `exempt:` list
names surfaces where the pattern is the native form and does not score.

```ai-filter
emoji-section-marker
tldr-block
labelled-list | exempt: PR body, review summary
headers-bold-labels | exempt: PR body, review summary
em-dash
parallel-triple
closing-restatement | exempt: PR body, review summary
vocabulary
not-x-but-y
```
````

`skills/team-tooling/human-reply/channels/notion.md`:

````markdown
# Notion channel module

What is true of Notion for every person. The person's own numbers,
phrasebook, and examples live in `~/.claude/human-reply/channels/notion.md`,
written by setup. When the two disagree on a number, the profile wins; on
markup, this file wins.

## Surfaces

| Surface | Who reads it | Collector assigns it when | Default register |
|---|---|---|---|
| page comment | everyone following the page | a comment in a discussion attached to the page itself | no greeting |
| inline comment | the author of the highlighted text | a comment in a discussion anchored to a block or a text selection | no greeting, one or two sentences |

The minimum is the smallest budget a measured profile may derive. The
default is the budget a surface gets when it has fewer than 30 pre-cutoff
records. Both are word counts with each link and fenced block counted as
one word.

```surfaces
# surface | minimum | default
page comment | 20 | 60
inline comment | 10 | 40
```

Notion is the weakest collector: comments are reached page by page, so
the sample is capped at 500 records and the profile header says so.

## Markup

Comments take rich text, not full page markdown.

- Headers, tables, and toggles do not render in a comment. Use line breaks.
- Inline code, bold, italic, and links render.
- Mention a person with `@name`; the person resolves it when pasting.
- Link a page by pasting its URL; Notion turns it into a page mention.
- A long answer belongs on the page as an edit or a new block, with the
  comment pointing at it.

## Shapes

Skeletons only. Angle brackets are slots. The profile adds the person's
own examples per shape.

Inline comment:

```
<the point about the highlighted text in one sentence>
```

Page comment answering a question:

```
<the answer in one sentence>. <the reason or the link>.
```

Page comment raising a concern:

```
<the concern in one sentence>. <what would resolve it>.
```

The default shape when none matches is the page comment answering a
question.

## Audit checklist

1. The first line of output named the channel, surface, budget, and
   profile provenance, and the draft is inside that budget.
2. The point is in the first sentence.
3. No headers, tables, or toggles.
4. Nothing already in the highlighted text or the page is restated.
5. Identifiers in backticks.

## AI-filter patterns

The scaffolding patterns scored on this channel by
`human-reply/references/ai-filter.md`, one id per line. An `exempt:` list
names surfaces where the pattern is the native form and does not score.

```ai-filter
emoji-section-marker
tldr-block
labelled-list | exempt: page comment
headers-bold-labels | exempt: page comment
em-dash
parallel-triple
closing-restatement | exempt: page comment
vocabulary
not-x-but-y
```
````

`skills/team-tooling/human-reply/references/corpus-record.md`:

````markdown
# Corpus record

Every collector writes one JSON object per line to
`~/.claude/human-reply/corpus/<channel>.jsonl`, or to
`corpus/borrow-<channel>.jsonl` for a colleague sample. Records pass
through redaction before they are written; nothing unredacted touches
disk. `python scripts/corpus.py validate` checks a file against this
shape.

## Fields

```
{"channel": "slack", "surface": "channel thread reply", "ts": "2026-03-04T10:12:00Z",
 "audience": "C0123", "thread": "C0123/1709546000.1", "others": 2,
 "text": "...", "held_out": false}
```

| Field | Type | Meaning |
|---|---|---|
| `channel` | string | `slack`, `github`, or `notion` |
| `surface` | string | exactly one surface name from the channel module's `surfaces` block, assigned by the collector using that module's Surfaces table |
| `ts` | string | when the message was sent, UTC, `YYYY-MM-DDTHH:MM:SSZ` |
| `audience` | string | the channel id, `owner/repo`, or page id; never a person's name |
| `thread` | string | an id for the conversation the message belongs to, stable across its records, so calibration can rebuild the context |
| `others` | integer | how many participants in the thread are not the person; 0 when unknown |
| `text` | string | the message as sent, after redaction |
| `held_out` | boolean | `false` when written; set by the hold-out step, never by a collector |

No other field is allowed. A record's id, used in drop samples and the
long-message list, is `<audience>/<ts>`.

## Thread ids by channel

- Slack: `<channel id>/<thread ts>`, or `<channel id>/<ts>` for a message
  outside a thread.
- GitHub: `<owner>/<repo>#<number>` for PR bodies and issue comments,
  `<owner>/<repo>#<number>/r<review id>` for a review summary, and
  `<owner>/<repo>#<number>/c<first comment id of the thread>` for a review
  thread reply.
- Notion: `<page id>/<discussion id>`.

## Counting words

Word counts everywhere in this skill split on whitespace after replacing
each fenced block, each Slack link `<https://...>`, and each markdown
link `[text](url)` with a single word.
````

- [ ] **Step 5: Run the tests and watch them pass**

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: every test in `test_corpus.py` passes, `OK`.

- [ ] **Step 6: Commit**

```
git add skills/team-tooling/human-reply/scripts/corpus.py skills/team-tooling/human-reply/channels skills/team-tooling/human-reply/references/corpus-record.md skill-tests/human-reply/tests/test_corpus.py
git commit -m "Add human-reply corpus records and channel modules"
```

### Task 2: Redaction

**Files:**
- Create: `skills/team-tooling/human-reply/scripts/redact.py`
- Create: `skills/team-tooling/human-reply/references/redaction-check.md`
- Test: `skill-tests/human-reply/tests/test_redact.py`

**Interfaces:**
- Consumes: `corpus.fenced_block` (Task 1); `skills/pr-tooling/pr-loop-lib/references/secret-scan-rules.md` rules 1 to 12, read by the test.
- Produces: `SOURCE_PATTERNS: list[(kind, regex)]`, `PEM_BLOCK`, `redact(text) -> (text, count)`, `main(argv=None, stdin=None)`. CLI: JSONL on stdin, `--out` appends, stderr line `redact: <touched> of <seen> records touched`. The redaction-check block format is `input ==> expected`, with `{join}` removed from the input before redacting.

- [ ] **Step 1: Write the failing test**

````python
import contextlib
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
SKILL = REPO / "skills" / "team-tooling" / "human-reply"
sys.path.insert(0, str(SKILL / "scripts"))

import corpus  # noqa: E402
import redact  # noqa: E402

RULES = REPO / "skills" / "pr-tooling" / "pr-loop-lib" / "references" / "secret-scan-rules.md"
CHECK = SKILL / "references" / "redaction-check.md"


def scan_rule_patterns():
    """{rule number: regex} from the fenced block of secret-scan-rules.md."""
    block = re.search(r"^```\n(.*?)^```", RULES.read_text(encoding="utf-8"), re.S | re.M).group(1)
    rules, number = {}, None
    for line in block.splitlines():
        header = re.match(r"^# (\d+) ", line)
        if header:
            number = int(header.group(1))
        elif line.strip() and number is not None:
            rules[number] = line
    return rules


def check_cases():
    lines = corpus.fenced_block(CHECK.read_text(encoding="utf-8"), "redaction-check")
    return [tuple(line.split(" ==> ")) for line in lines]


class PatternCopyTests(unittest.TestCase):
    def test_patterns_match_rules_one_to_twelve_in_order(self):
        rules = scan_rule_patterns()
        self.assertEqual([rules[n] for n in range(1, 13)], [p for _, p in redact.SOURCE_PATTERNS])

    def test_the_env_rule_is_the_only_rule_not_copied(self):
        self.assertEqual(sorted(set(scan_rule_patterns()) - set(range(1, 13))), [13])


class RedactionCheckTests(unittest.TestCase):
    def test_every_case_redacts_to_its_expected_output(self):
        cases = check_cases()
        self.assertEqual(len(cases), 14)
        for given, expected in cases:
            with self.subTest(given=given):
                self.assertEqual(redact.redact(given.replace("{join}", ""))[0], expected)

    def test_the_check_file_itself_matches_no_scan_rule(self):
        text = CHECK.read_text(encoding="utf-8")
        for number, pattern in scan_rule_patterns().items():
            with self.subTest(rule=number):
                self.assertIsNone(re.search(pattern, text, re.M))

    def test_a_pem_body_is_removed_with_its_header(self):
        key = "-----BEGIN OPENSSH " + "PRIVATE KEY-----\nb3BlbnNzaC1rZXk\nAAAA\n-----END OPENSSH PRIVATE KEY-----"
        self.assertEqual(redact.redact(f"old key:\n{key}\nrotated")[0], "old key:\n<redacted:private-key>\nrotated")

    def test_clean_text_reports_zero_replacements(self):
        self.assertEqual(redact.redact("the retry policy stops at 3 attempts"), ("the retry policy stops at 3 attempts", 0))


class CliTests(unittest.TestCase):
    def test_appends_redacted_records_and_counts_touched_ones(self):
        records = [
            {"text": "use ghp_" + "0123456789abcdefghijklmnopqrstuvwxyz" + " now", "surface": "outer DM"},
            {"text": "nothing secret", "surface": "outer DM"},
        ]
        stdin = io.StringIO("".join(json.dumps(r) + "\n" for r in records))
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "slack.jsonl"
            out.write_text(json.dumps({"text": "earlier", "surface": "outer DM"}) + "\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                code = redact.main(["--out", str(out)], stdin=stdin)
            written = corpus.read_jsonl(out)
        self.assertEqual(code, 0)
        self.assertEqual([r["text"] for r in written], ["earlier", "use <redacted:github-pat> now", "nothing secret"])
        self.assertEqual(stderr.getvalue(), "redact: 1 of 2 records touched\n")


if __name__ == "__main__":
    unittest.main()
````

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `ModuleNotFoundError: No module named 'redact'`.

- [ ] **Step 3: Write `redact.py`**

```python
"""Replace secret-shaped substrings in corpus records with <redacted:kind> placeholders.

Reads JSONL records on stdin, appends redacted records to --out, and prints
how many records were touched to stderr.
"""
import argparse
import json
import re
import sys

# Rules 1-12 of pr-loop-lib/references/secret-scan-rules.md, verbatim and in
# order. Rule 13 applies only to .env files and has no meaning for messages.
SOURCE_PATTERNS = [
    ("private-key", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"),
    ("keyed-assignment", r"""(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[:=]\s*["']?[A-Za-z0-9+/=_\-]{20,}["']?"""),
    ("password", r"""(?i)password\s*[:=]\s*["'][^"']{8,}["']"""),
    ("google-oauth-client-id", r"[A-Za-z0-9]{32,64}\.apps\.googleusercontent\.com"),
    ("aws-access-key-id", r"AKIA[0-9A-Z]{16}"),
    ("aws-secret-access-key", r"""(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[:=]\s*["']?[A-Za-z0-9+/=]{40}["']?"""),
    ("slack-token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("github-pat", r"ghp_[A-Za-z0-9]{36}"),
    ("github-fine-grained-pat", r"github_pat_[A-Za-z0-9_]{82}"),
    ("connection-string", r"(?i)(Server|Host|Data Source)\s*=\s*[^;]+;\s*.*?(?:Password|Pwd)\s*=\s*[^;]+"),
    ("mongodb-connection-string", r"mongodb(\+srv)?://[^:]+:[^@]+@"),
    ("postgres-connection-string", r"postgres(?:ql)?://[^:]+:[^@]+@"),
]

# The scan rule only needs the header to block a commit; redaction must also
# remove the key body, so rule 1 is widened to the whole PEM block.
PEM_BLOCK = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"
    r"[\s\S]*?(?:-----END (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----|\Z)"
)

COMPILED = [(kind, re.compile(pattern)) for kind, pattern in SOURCE_PATTERNS]


def redact(text):
    """Return (redacted_text, replacement_count)."""
    total = 0
    text, n = PEM_BLOCK.subn("<redacted:private-key>", text)
    total += n
    for kind, pattern in COMPILED:
        if kind == "private-key":
            continue
        text, n = pattern.subn(f"<redacted:{kind}>", text)
        total += n
    return text, total


def main(argv=None, stdin=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="JSONL file to append redacted records to")
    args = parser.parse_args(argv)
    stdin = stdin if stdin is not None else sys.stdin
    seen = touched = 0
    with open(args.out, "a", encoding="utf-8", newline="\n") as out:
        for line in stdin:
            if not line.strip():
                continue
            record = json.loads(line)
            record["text"], count = redact(record["text"])
            seen += 1
            touched += 1 if count else 0
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"redact: {touched} of {seen} records touched", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    sys.exit(main())
```

- [ ] **Step 4: Write the redaction check**

`skills/team-tooling/human-reply/references/redaction-check.md`:

````markdown
# Redaction check

The known-bad and known-clean cases every redaction path must pass before
a corpus record is written. `scripts/redact.py` is tested against this
file, and the no-Python path redacts every case here by hand before its
first write, as the setup collect step describes.

## Format

One case per line in the fenced block: the input, then ` ==> `, then the
exact expected output. Every input has the text `{join}` inside its
secret so that this file itself never matches a secret scan; delete each
`{join}` before redacting. Expected outputs contain no `{join}`.

A path passes when every input, with `{join}` removed, redacts to exactly
its expected output. One miss fails the whole check.

## Cases

```redaction-check
the key is -----BEGIN RSA PRIV{join}ATE KEY----- MIIEow {join}IBAAKCAQEA -----END RSA PRIVATE KEY----- rotate it ==> the key is <redacted:private-key> rotate it
set api_{join}key = "abcdefghijklmnopqrstuvwxyz123456" in the config ==> set <redacted:keyed-assignment> in the config
pass{join}word: "hunter2hunter2" was in the log ==> <redacted:password> was in the log
client 1234567890abcdef1234567890abcdef.apps.google{join}usercontent.com is ours ==> client <redacted:google-oauth-client-id> is ours
the id AKIA{join}ABCDEFGHIJKLMNOP leaked ==> the id <redacted:aws-access-key-id> leaked
aws_secret_access_{join}key=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEYAB ==> <redacted:aws-secret-access-key>
bot token xox{join}b-1234567890-abcdefghij works ==> bot token <redacted:slack-token> works
use ghp_{join}0123456789abcdefghijklmnopqrstuvwxyz for now ==> use <redacted:github-pat> for now
use github_pat_{join}0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghij for now ==> use <redacted:github-fine-grained-pat> for now
Server=db1;Database=x;User Id=sa;Pass{join}word=Sup3rS3cret; is the string ==> <redacted:connection-string>; is the string
mongo{join}db://admin:pa55word@cluster0 is prod ==> <redacted:mongodb-connection-string>cluster0 is prod
post{join}gres://app:pa55word@db:5432/x is staging ==> <redacted:postgres-connection-string>db:5432/x is staging
the retry policy stops at 3 attempts ==> the retry policy stops at 3 attempts
see https://example.com/docs for the password reset flow ==> see https://example.com/docs for the password reset flow
```
````

- [ ] **Step 5: Run the tests and watch them pass**

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `OK`.

- [ ] **Step 6: Commit**

```
git add skills/team-tooling/human-reply/scripts/redact.py skills/team-tooling/human-reply/references/redaction-check.md skill-tests/human-reply/tests/test_redact.py
git commit -m "Add human-reply redaction with a shared known-bad fixture"
```

### Task 3: AI-writing filter

**Files:**
- Create: `skills/team-tooling/human-reply/scripts/ai_filter.py`
- Create: `skills/team-tooling/human-reply/references/ai-filter.md`
- Test: `skill-tests/human-reply/tests/test_ai_filter.py`

**Interfaces:**
- Consumes: `corpus.fenced_block`, `is_pre_cutoff`, `read_jsonl`, `record_id`, `word_count`, `write_jsonl` (Task 1); the `ai-filter` blocks in the channel modules (Task 1).
- Produces: `DEFAULT_THRESHOLD = 3`, `LONG_MESSAGE_WORDS = 60`, `MAX_RAISE = 1`, `DETECTORS: dict[id, fn(text, ctx) -> bool]`, `load_patterns(module_path) -> {id: set(exempt surfaces)}`, `load_vocabulary(reference_path) -> list[str]`, `short_messages_use_bullets(records) -> bool`, `score(text, surface, patterns, ctx) -> sorted ids`, `in_scope(record, cutoff, borrow) -> bool`, `run_filter(records, patterns, ctx, cutoff, threshold, borrow=False) -> (kept, [(record, hits)])`, `check_threshold(n)` raising `ValueError` outside 1 to 4. CLI flags `--corpus --module --reference --cutoff --threshold --borrow --kept`; prints JSON `total, scanned, dropped, drop_rate, threshold, samples`; exit 2 on a bad threshold.

- [ ] **Step 1: Write the failing test**

````python
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
SKILL = REPO / "skills" / "team-tooling" / "human-reply"
sys.path.insert(0, str(SKILL / "scripts"))

import ai_filter  # noqa: E402
import corpus  # noqa: E402

MODULES = {name: SKILL / "channels" / f"{name}.md" for name in ("slack", "github", "notion")}
REFERENCE = SKILL / "references" / "ai-filter.md"

# The 2026 messages as sent and their 2025-voice rewrites, from the
# before-and-after section of the slack-reply shapes file.
SLACK_DESIGN_SHARE_SENT = (
    "Hi <@team> We're modernizing the new Appointment Details screen on BizApp to read directly from the "
    "federated GraphQL graph instead of the legacy SOAP/REST path it uses today \u2014 one contract, data coming "
    "from the domains that own it, and no BFF in the middle.\n\n"
    "On the Clients side that's a small set of additive changes: exposing automatedContactMethod on the client "
    "and adding two new resolvers \u2014 a progress-note status and forms count for an appointment. "
    "Additive-only \u2014 no SQL.\n\n"
    "We are planning to do this implementation ourselves and are looking for your review and sign-off on the "
    "approach, so it fits the Clients subgraph.\n\n"
    ":page_facing_up: Doc: <link>\n\n"
    "Thanks! :pray:\n"
    "cc: @<name>"
)
SLACK_DESIGN_SHARE_REWRITE = (
    "Hi <@team>, we are moving the BizApp Appointment Details screen to read from the federated graph instead "
    "of the legacy SOAP/REST path. On the Clients subgraph this needs automatedContactMethod on the client plus "
    "two new resolvers (progress note status, forms count). Additive only, no SQL changes.\n"
    "Design doc: <link>\n"
    "Please review whenever time permits.\n"
    "Thanks! :slightly_smiling_face:\n"
    "cc: @<name>"
)
SLACK_PROPOSAL_SENT = (
    "Hi <@team>/team, sharing the design proposal for a new endpoint in the Scheduling domain: Assign Guest "
    "Visit as per the discussion in the thread.\n"
    "This supports the BizApp workflow where a guest booked into a class is converted into a regular client. "
    "The endpoint updates the guest visit's ClientId to the newly created client via a direct SQL update within "
    "Scheduling \u2014 no Booking Service involvement.\n"
    "Design doc: <link>\n"
    "Key highlights:\n"
    "\u2022 PUT /v1/subscribers/{SubscriberId}/class-visits/{VisitId}/assign-guest-visit\n"
    "\u2022 Guest-only operation (ClientId = -2) \u2014 not a generic reassign\n"
    "\u2022 Atomic SQL update (validation + update in one query)\n"
    "\u2022 Stays entirely within the Scheduling domain\n\n"
    "Would appreciate feedback and approval before we move to implementation. Thanks! :slightly_smiling_face:\n"
    "cc: @<name>"
)
SLACK_PROPOSAL_REWRITE = (
    "Hi <@team>, following up on the thread above, here is the design proposal for the Assign Guest Visit "
    "endpoint in Scheduling. It updates a guest visit's ClientId to the newly created client with a single SQL "
    "update, guest visits only (ClientId = -2), no Booking Service involvement.\n"
    "Design doc: <link>\n"
    "Please take a look and let me know if this makes sense.\n"
    "Thanks! :slightly_smiling_face:\n"
    "cc: @<name>"
)

GITHUB_NATIVE_PR_BODY = (
    "## Summary\n"
    "Moves the null check into `InvoiceMapper.ToDomain` so both callers get it, and drops the duplicate guard "
    "the exporter carried since the mapper was split out of the billing service last spring.\n\n"
    "## Changes\n"
    "- `InvoiceMapper.ToDomain` returns early on a null invoice and logs the invoice id\n"
    "- `InvoiceExporter` no longer checks for null before mapping each row\n"
    "- tests cover the null path through both the exporter and the statement job\n\n"
    "## Testing\n"
    "Ran the exporter and statement suites locally.\n"
    "Overall this leaves one guard where there were two."
)
GITHUB_SCAFFOLDED_PR_BODY = (
    "## TL;DR\n"
    "This PR is not just a refactor, but a pivotal step that will enhance reliability across the exporter "
    "\u2014 every caller is now covered by a single guard in the mapper.\n\n"
    "## Key highlights\n"
    "- Additionally, `InvoiceMapper.ToDomain` now owns the null check for every invoice it maps\n"
    "- The exporter no longer duplicates the guard before it maps each row\n"
    "- New tests underscore the null path through the exporter and the statement job\n\n"
    "In summary, this change delivers a crucial and valuable improvement to how invoices are mapped."
)
NOTION_NATIVE_PAGE_COMMENT = (
    "Two things on the retry section before we sign off on the design:\n"
    "- the partner API caps pages at 500, so the batch size above cannot go higher without their sign-off\n"
    "- the backoff table should say which errors retry, since 409 from the ledger is not safe to repeat\n"
    "- the alert threshold is per region, not global, which changes the numbers in the last table\n"
    "Overall the flow reads right to me once those are fixed."
)
NOTION_SCAFFOLDED_PAGE_COMMENT = (
    "TL;DR: the retry design is solid but needs a couple of tweaks.\n"
    "This is not only about retries, but about building a robust and pivotal foundation that will enhance "
    "how we handle partner failures \u2014 the backoff table and the alert thresholds both need another pass, "
    "and the page should delve into which ledger errors are safe to repeat.\n"
    "In summary, a valuable direction with a few gaps to close."
)


def ctx(short_messages_use_bullets=False):
    return {"vocabulary": ai_filter.load_vocabulary(REFERENCE),
            "short_messages_use_bullets": short_messages_use_bullets}


def hits(text, channel, surface, short_messages_use_bullets=False):
    return ai_filter.score(text, surface, ai_filter.load_patterns(MODULES[channel]), ctx(short_messages_use_bullets))


def record(text, surface, ts="2026-03-04T10:12:00Z", held_out=False, thread="C1/1"):
    return {"channel": "slack", "surface": surface, "ts": ts, "audience": "C1", "thread": thread,
            "others": 2, "text": text, "held_out": held_out}


class PatternListTests(unittest.TestCase):
    def test_every_module_lists_all_nine_patterns(self):
        for name, path in MODULES.items():
            with self.subTest(channel=name):
                self.assertEqual(set(ai_filter.load_patterns(path)), set(ai_filter.DETECTORS))

    def test_slack_exempts_nothing(self):
        self.assertTrue(all(not exempt for exempt in ai_filter.load_patterns(MODULES["slack"]).values()))

    def test_github_and_notion_exempt_only_the_native_forms(self):
        native = {"labelled-list", "headers-bold-labels", "closing-restatement"}
        for name, surfaces in (("github", {"PR body", "review summary"}), ("notion", {"page comment"})):
            patterns = ai_filter.load_patterns(MODULES[name])
            with self.subTest(channel=name):
                self.assertEqual({pid for pid, exempt in patterns.items() if exempt}, native)
                self.assertTrue(all(patterns[pid] == surfaces for pid in native))

    def test_an_unknown_pattern_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "x.md"
            path.write_text("```ai-filter\nem-dash\nsparkle-emoji\n```\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                ai_filter.load_patterns(path)

    def test_the_vocabulary_block_loads(self):
        vocabulary = ai_filter.load_vocabulary(REFERENCE)
        self.assertIn("pivotal", vocabulary)
        self.assertNotIn("key", vocabulary)


class SlackPairTests(unittest.TestCase):
    def test_the_scaffolded_proposal_is_dropped_at_the_default_threshold(self):
        found = hits(SLACK_PROPOSAL_SENT, "slack", "channel new post")
        self.assertEqual(found, ["em-dash", "labelled-list", "parallel-triple"])
        self.assertGreaterEqual(len(found), ai_filter.DEFAULT_THRESHOLD)

    def test_the_scaffolded_design_share_scores_two_and_needs_threshold_two(self):
        self.assertEqual(hits(SLACK_DESIGN_SHARE_SENT, "slack", "channel new post"),
                         ["em-dash", "emoji-section-marker"])

    def test_both_rewrites_score_nothing(self):
        for text in (SLACK_DESIGN_SHARE_REWRITE, SLACK_PROPOSAL_REWRITE):
            with self.subTest(text=text[:40]):
                self.assertEqual(hits(text, "slack", "channel new post"), [])


class NativeFormTests(unittest.TestCase):
    def test_a_native_pr_body_scores_nothing_on_the_pr_body_surface(self):
        self.assertEqual(hits(GITHUB_NATIVE_PR_BODY, "github", "PR body", short_messages_use_bullets=True), [])

    def test_the_same_text_scores_its_headers_and_closing_on_a_review_thread_reply(self):
        self.assertEqual(hits(GITHUB_NATIVE_PR_BODY, "github", "review thread reply", short_messages_use_bullets=True),
                         ["closing-restatement", "headers-bold-labels"])

    def test_a_scaffolded_pr_body_is_still_dropped_on_the_pr_body_surface(self):
        found = hits(GITHUB_SCAFFOLDED_PR_BODY, "github", "PR body", short_messages_use_bullets=True)
        self.assertEqual(found, ["em-dash", "not-x-but-y", "tldr-block", "vocabulary"])

    def test_a_native_page_comment_scores_nothing_on_the_page_comment_surface(self):
        self.assertEqual(hits(NOTION_NATIVE_PAGE_COMMENT, "notion", "page comment", short_messages_use_bullets=True), [])

    def test_the_same_comment_scores_its_labelled_list_and_closing_inline(self):
        self.assertEqual(hits(NOTION_NATIVE_PAGE_COMMENT, "notion", "inline comment", short_messages_use_bullets=True),
                         ["closing-restatement", "labelled-list"])

    def test_a_scaffolded_page_comment_is_still_dropped_on_the_page_comment_surface(self):
        found = hits(NOTION_SCAFFOLDED_PAGE_COMMENT, "notion", "page comment", short_messages_use_bullets=True)
        self.assertEqual(found, ["em-dash", "not-x-but-y", "tldr-block", "vocabulary"])

    def test_every_fixture_is_long_enough_to_be_scanned(self):
        for text in (SLACK_DESIGN_SHARE_SENT, SLACK_PROPOSAL_SENT, SLACK_PROPOSAL_REWRITE,
                     GITHUB_NATIVE_PR_BODY, GITHUB_SCAFFOLDED_PR_BODY,
                     NOTION_NATIVE_PAGE_COMMENT, NOTION_SCAFFOLDED_PAGE_COMMENT):
            with self.subTest(text=text[:40]):
                self.assertGreater(corpus.word_count(text), ai_filter.LONG_MESSAGE_WORDS)


class ParallelTripleTests(unittest.TestCase):
    triple = "intro\n- one\n- two\n- three"

    def test_counts_only_when_short_messages_never_use_bullets(self):
        self.assertTrue(ai_filter.parallel_triple(self.triple, ctx(False)))
        self.assertFalse(ai_filter.parallel_triple(self.triple, ctx(True)))

    def test_short_message_bullet_use_is_read_from_the_corpus(self):
        self.assertFalse(ai_filter.short_messages_use_bullets([record("just a line", "outer DM")]))
        self.assertTrue(ai_filter.short_messages_use_bullets([record("todo\n- a\n- b", "outer DM")]))


class ScopeTests(unittest.TestCase):
    patterns = {"em-dash": set(), "tldr-block": set(), "vocabulary": set()}
    loud = "TL;DR: pivotal and crucial \u2014 done\n" + "word " * 70
    quiet = "TL;DR: pivotal and crucial \u2014 done\nshort"

    def run_filter(self, records, cutoff="2026-01", threshold=3, borrow=False):
        kept, dropped = ai_filter.run_filter(records, self.patterns, ctx(), cutoff, threshold, borrow)
        return [r["ts"] for r in kept], [r["ts"] for r, _ in dropped]

    def test_only_long_post_cutoff_messages_are_scanned(self):
        records = [record(self.loud, "outer DM", ts="2025-12-01T00:00:00Z"),
                   record(self.loud, "outer DM", ts="2026-01-01T00:00:00Z"),
                   record(self.quiet, "outer DM", ts="2026-02-01T00:00:00Z"),
                   record(self.loud, "outer DM", ts="2026-03-01T00:00:00Z", held_out=True)]
        self.assertEqual(self.run_filter(records),
                         (["2025-12-01T00:00:00Z", "2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z"],
                          ["2026-01-01T00:00:00Z"]))

    def test_never_means_none_of_the_persons_messages_are_scanned(self):
        records = [record(self.loud, "outer DM", ts="2026-03-01T00:00:00Z")]
        self.assertEqual(self.run_filter(records, cutoff=None), (["2026-03-01T00:00:00Z"], []))

    def test_a_colleague_sample_is_scanned_regardless_of_date(self):
        records = [record(self.loud, "outer DM", ts="2024-03-01T00:00:00Z")]
        self.assertEqual(self.run_filter(records, cutoff=None, borrow=True), ([], ["2024-03-01T00:00:00Z"]))

    def test_the_threshold_decides(self):
        records = [record(self.loud, "outer DM", ts="2026-03-01T00:00:00Z")]
        self.assertEqual(self.run_filter(records, threshold=4), (["2026-03-01T00:00:00Z"], []))

    def test_the_threshold_may_rise_by_one_point_at_most(self):
        ai_filter.check_threshold(1)
        ai_filter.check_threshold(4)
        for bad in (0, 5):
            with self.subTest(threshold=bad), self.assertRaises(ValueError):
                ai_filter.check_threshold(bad)


class CliTests(unittest.TestCase):
    def test_writes_kept_records_and_prints_the_summary(self):
        records = [record(SLACK_PROPOSAL_SENT, "channel new post", ts="2026-03-01T00:00:00Z"),
                   record(SLACK_PROPOSAL_REWRITE, "channel new post", ts="2026-03-02T00:00:00Z"),
                   record("ok", "outer DM", ts="2026-03-03T00:00:00Z")]
        with tempfile.TemporaryDirectory() as tmp:
            source, kept = pathlib.Path(tmp) / "slack.jsonl", pathlib.Path(tmp) / "slack.kept.jsonl"
            corpus.write_jsonl(source, records)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = ai_filter.main(["--corpus", str(source), "--module", str(MODULES["slack"]),
                                       "--reference", str(REFERENCE), "--cutoff", "2026-01", "--kept", str(kept)])
            kept_ts = [r["ts"] for r in corpus.read_jsonl(kept)]
        summary = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(kept_ts, ["2026-03-02T00:00:00Z", "2026-03-03T00:00:00Z"])
        self.assertEqual({k: summary[k] for k in ("total", "scanned", "dropped", "drop_rate", "threshold")},
                         {"total": 3, "scanned": 2, "dropped": 1, "drop_rate": 0.333, "threshold": 3})
        self.assertEqual(summary["samples"][0]["id"], "C1/2026-03-01T00:00:00Z")

    def test_an_out_of_range_threshold_exits_two(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = ai_filter.main(["--corpus", "x", "--module", "x", "--reference", "x",
                                   "--cutoff", "never", "--threshold", "5", "--kept", "x"])
        self.assertEqual((code, err.getvalue()), (2, "ai_filter: threshold must be 1 to 4\n"))


if __name__ == "__main__":
    unittest.main()
````

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `ModuleNotFoundError: No module named 'ai_filter'`.

- [ ] **Step 3: Write `ai_filter.py`**

````python
"""Score long messages for AI scaffolding and drop the ones at or over the threshold.

    python ai_filter.py --corpus <channel>.jsonl --module channels/<channel>.md
        --reference references/ai-filter.md --cutoff 2026-01|never
        [--threshold 3] [--borrow] --kept <channel>.kept.jsonl

Prints a JSON summary: total, scanned, dropped, drop_rate, threshold, and
up to five dropped samples with the patterns each one hit.
"""
import argparse
import json
import re
import sys

from corpus import fenced_block, is_pre_cutoff, read_jsonl, record_id, word_count, write_jsonl

DEFAULT_THRESHOLD = 3
LONG_MESSAGE_WORDS = 60
MAX_RAISE = 1
SAMPLES = 5

BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+\S")
EMOJI_START = re.compile(r"^\s*(?::[a-z0-9_+\-]+:|[\u2600-\u27bf\U0001F300-\U0001FAFF])\s*\S")
TLDR_START = re.compile(r"^\W*tl;?dr\b", re.I)
KEY_LIST = re.compile(r"\bkey (?:highlights|takeaways)\b", re.I)
HEADER = re.compile(r"^\s{0,3}#{1,6}\s+\S")
BOLD_LABEL = re.compile(r"\*\*[^*\n]{1,40}:\*\*|\*\*[^*\n]{1,40}\*\*\s*:|^\s*\*[^*\n]{1,40}:\*|^\s*\*[^*\n]{1,40}\*\s*:", re.M)
CLOSING = re.compile(r"^\W*(?:in short|in summary|to summari[sz]e|overall|all in all|net[- ]net|bottom line)\b", re.I)
NOT_BUT = re.compile(
    r"\bnot (?:just |only |merely )?[^.!?\n]{1,60}?,? but\b"
    r"|\bisn'?t (?:just |only |merely )?[^.!?\n]{1,40}?[;,] it'?s\b",
    re.I,
)


def _lines(text):
    return [line for line in text.splitlines() if line.strip()]


def emoji_section_marker(text, ctx):
    lines = _lines(text)
    return len(lines) >= 2 and any(EMOJI_START.match(line) for line in lines)


def tldr_block(text, ctx):
    lines = _lines(text)
    return len(lines) >= 2 and bool(TLDR_START.match(lines[0]))


def labelled_list(text, ctx):
    if KEY_LIST.search(text):
        return True
    lines = _lines(text)
    return any(a.rstrip().endswith(":") and BULLET.match(b) for a, b in zip(lines, lines[1:]))


def headers_bold_labels(text, ctx):
    return any(HEADER.match(line) for line in _lines(text)) or bool(BOLD_LABEL.search(text))


def em_dash(text, ctx):
    return "\u2014" in text


def parallel_triple(text, ctx):
    if ctx["short_messages_use_bullets"]:
        return False
    run = 0
    for line in _lines(text):
        run = run + 1 if BULLET.match(line) else 0
        if run >= 3:
            return True
    return False


def closing_restatement(text, ctx):
    lines = _lines(text)
    return bool(lines) and bool(CLOSING.match(lines[-1]))


def vocabulary(text, ctx):
    found = {word for word in ctx["vocabulary"]
             if re.search(rf"\b{re.escape(word)}\w*", text, re.I)}
    return len(found) >= 2


def not_x_but_y(text, ctx):
    return bool(NOT_BUT.search(text))


DETECTORS = {
    "emoji-section-marker": emoji_section_marker,
    "tldr-block": tldr_block,
    "labelled-list": labelled_list,
    "headers-bold-labels": headers_bold_labels,
    "em-dash": em_dash,
    "parallel-triple": parallel_triple,
    "closing-restatement": closing_restatement,
    "vocabulary": vocabulary,
    "not-x-but-y": not_x_but_y,
}


def load_patterns(module_path):
    """{pattern_id: set of exempt surfaces} from the module's ```ai-filter block."""
    with open(module_path, encoding="utf-8") as f:
        lines = fenced_block(f.read(), "ai-filter")
    patterns = {}
    for line in lines:
        pattern_id, _, rest = line.partition("|")
        pattern_id = pattern_id.strip()
        if pattern_id not in DETECTORS:
            raise ValueError(f"unknown ai-filter pattern {pattern_id!r} in {module_path}")
        exempt = set()
        rest = rest.strip()
        if rest:
            if not rest.startswith("exempt:"):
                raise ValueError(f"expected 'exempt:' after {pattern_id!r} in {module_path}")
            exempt = {s.strip() for s in rest[len("exempt:"):].split(",") if s.strip()}
        patterns[pattern_id] = exempt
    return patterns


def load_vocabulary(reference_path):
    with open(reference_path, encoding="utf-8") as f:
        return fenced_block(f.read(), "vocabulary")


def short_messages_use_bullets(records):
    return any(BULLET.match(line)
               for r in records if word_count(r["text"]) <= LONG_MESSAGE_WORDS
               for line in r["text"].splitlines())


def score(text, surface, patterns, ctx):
    """Sorted pattern ids the text hits on this surface."""
    return sorted(pid for pid, exempt in patterns.items()
                  if surface not in exempt and DETECTORS[pid](text, ctx))


def in_scope(record, cutoff, borrow):
    return (not record["held_out"]
            and word_count(record["text"]) > LONG_MESSAGE_WORDS
            and (borrow or (cutoff is not None and not is_pre_cutoff(record, cutoff))))


def run_filter(records, patterns, ctx, cutoff, threshold, borrow=False):
    """Split records into (kept, dropped); dropped items are (record, hits)."""
    kept, dropped = [], []
    for record in records:
        hits = score(record["text"], record["surface"], patterns, ctx) if in_scope(record, cutoff, borrow) else []
        if len(hits) >= threshold:
            dropped.append((record, hits))
        else:
            kept.append(record)
    return kept, dropped


def check_threshold(threshold):
    if threshold < 1 or threshold > DEFAULT_THRESHOLD + MAX_RAISE:
        raise ValueError(f"threshold must be 1 to {DEFAULT_THRESHOLD + MAX_RAISE}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--cutoff", required=True, help="YYYY-MM, or never")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--borrow", action="store_true", help="colleague sample: scan every long message")
    parser.add_argument("--kept", required=True)
    args = parser.parse_args(argv)
    try:
        check_threshold(args.threshold)
    except ValueError as error:
        print(f"ai_filter: {error}", file=sys.stderr)
        return 2

    records = read_jsonl(args.corpus)
    cutoff = None if args.cutoff == "never" else args.cutoff
    ctx = {"vocabulary": load_vocabulary(args.reference),
           "short_messages_use_bullets": short_messages_use_bullets(records)}
    patterns = load_patterns(args.module)
    kept, dropped = run_filter(records, patterns, ctx, cutoff, args.threshold, args.borrow)
    write_jsonl(args.kept, kept)
    scanned = sum(1 for r in records if in_scope(r, cutoff, args.borrow))
    summary = {
        "total": len(records),
        "scanned": scanned,
        "dropped": len(dropped),
        "drop_rate": round(len(dropped) / len(records), 3) if records else 0.0,
        "threshold": args.threshold,
        "samples": [{"id": record_id(r), "hits": hits, "text": r["text"]} for r, hits in dropped[:SAMPLES]],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
````

- [ ] **Step 4: Write the filter reference**

`skills/team-tooling/human-reply/references/ai-filter.md`:

````markdown
# AI filter

Keeps messages the person drafted with AI tools out of the profile. The
pattern list for each channel lives in that channel module's `ai-filter`
block; this file defines what each pattern id means, how a message is
scored, and the threshold. `scripts/ai_filter.py` implements it; the
no-Python path applies the same definitions by reading each message.

## Scope

A message is scanned when all of these hold:

- it is not held out for calibration
- it is over 60 words, counting each link and each fenced block as one word
- it is the person's own message sent in or after the cutoff month, or it
  is any message in a colleague sample

A person who answered "never" to the cutoff question has none of their
own messages scanned. Messages not scanned are always kept.

## Score

Each pattern id listed in the channel module scores one point when the
message shows it, unless the message's surface is in that pattern's
`exempt:` list. A message scoring the threshold or more is dropped.

The default threshold is 3. Setup lets the person change it once per
channel: lower it to any value from 1, or raise it by one point, to 4 at
most. A threshold other than 3 is written into the channel profile
header as `threshold: <n>`.

## Pattern ids

| Id | The message shows it when |
|---|---|
| `emoji-section-marker` | it has two or more non-blank lines and a line starts with an emoji or a `:shortcode:` followed by text |
| `tldr-block` | it has two or more non-blank lines and the first starts with "TL;DR" or "TLDR"; a "Summary" header counts under `headers-bold-labels` instead |
| `labelled-list` | it contains "Key highlights" or "Key takeaways", or a line ending in `:` is followed directly by a bullet line |
| `headers-bold-labels` | a line starts with a markdown header (`#` to `######`), or it contains a bold label such as `**Impact:**` or Slack's `*Impact:*` |
| `em-dash` | it contains an em dash |
| `parallel-triple` | it has three bullet lines in a row, and none of the person's messages of 60 words or fewer in this channel uses a bullet |
| `closing-restatement` | its last non-blank line starts with "In short", "In summary", "To summarize", "Overall", "All in all", "Net-net", or "Bottom line" |
| `vocabulary` | it uses two or more different words from the vocabulary block below, matched as word starts |
| `not-x-but-y` | it has a "not X, but Y" construction, or an "isn't X, it's Y" one |

## Vocabulary

Taken from the humanizer skill's list of overused AI words, without
"actually", "key", "highlight", and "landscape", which engineers use in
their literal sense too often to count.

```vocabulary
additionally
align with
crucial
delve
emphasizing
enduring
enhance
fostering
garner
interplay
intricate
intricacies
pivotal
showcase
tapestry
testament
underscore
valuable
vibrant
```

## Drop rate

The drop rate is dropped messages over all messages in the channel,
including short ones and held-out ones. `scripts/ai_filter.py` prints
it with the drop count and five dropped samples. Setup reads it before
and after the one threshold change, as its filter step describes.
````

- [ ] **Step 5: Run the tests and watch them pass**

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `OK`.

- [ ] **Step 6: Commit**

```
git add skills/team-tooling/human-reply/scripts/ai_filter.py skills/team-tooling/human-reply/references/ai-filter.md skill-tests/human-reply/tests/test_ai_filter.py
git commit -m "Add the human-reply AI-writing filter"
```

### Task 4: SKILL.md, profile schema, humanizer handoff, and PR 1

**Files:**
- Create: `skills/team-tooling/human-reply/SKILL.md`
- Create: `skills/team-tooling/human-reply/references/profile-schema.md`
- Create: `skills/team-tooling/human-reply/references/humanizer-handoff.md`

**Interfaces:**
- Consumes: channel modules (Task 1), `human-reply/references/ai-filter.md` (Task 3).
- Produces: the runtime first line `<Channel>, <surface>, budget <n> words, profile <method> <built date>[, <label> budget][, partial: <reasons>]`; the profile formats that Tasks 7, 8, and 11 read, including the header rule that `partial` and `estimated` appear before the first `##` heading and the Surfaces table's `Label` column; the reader return format with keys `shapes, phrasebook, typing_habits, disagreement, sign_offs, banned`.

- [ ] **Step 1: Write `SKILL.md`**

````markdown
---
name: human-reply
description: >
  Use whenever a message is being drafted, rewritten, shortened, or checked
  for the user to post on Slack, GitHub, or Notion: thread replies, DMs,
  channel posts, PR review replies, review summaries, PR bodies, issue
  comments, Notion page and inline comments; when the user says "reply to
  this thread", "draft a comment on this PR", "answer this Notion comment",
  "make this sound like me", "shorten this", or "/human-reply". Also runs
  the one-time setup that builds the user's voice profile from their own
  messages. Drafts in the user's measured voice for that channel. Text
  only, never posts.
argument-hint: "[setup [slack|github|notion] | draft <what to say> | rewrite <text> | audit <text>]"
allowed-tools: Read, Bash, Write, Skill, ToolSearch, Agent, mcp__plugin_slack_slack__slack_search_public_and_private, mcp__plugin_slack_slack__slack_read_thread, mcp__plugin_slack_slack__slack_search_users, mcp__claude_ai_Notion__notion-fetch, mcp__claude_ai_Notion__notion-search, mcp__claude_ai_Notion__notion-get-comments, mcp__claude_ai_Notion__notion-list-recent-pages
---

# human-reply

Writes a message the way the user writes it on that channel. Platform
facts live in the `human-reply/channels/` folder. The user's own numbers,
phrasebook, shapes, and habits live in `~/.claude/human-reply/`, written
by setup. This skill never calls a tool that sends, posts, comments, or
reacts.

## Route

| Arguments | Mode |
|---|---|
| `setup`, or `setup <channel>` | setup |
| `draft <what to say>`, or a request to reply or write | draft |
| `rewrite <text>`, or "make this sound like me", "shorten this" | rewrite |
| `audit <text>` | audit |

With no arguments and no request in the conversation, ask which mode.

## Setup

Follow the eight step files in the `human-reply/setup/` folder in number
order: 01-detect, 02-interview, 03-collect, 04-filter, 05-measure,
06-read, 07-calibrate, 08-finish. Read a step only when the previous one
is done. Setup writes only under `~/.claude/human-reply/`.

## Draft, rewrite, and audit

### 1. Channel

Settle the channel from, in order:

1. an explicit channel in the arguments or the request
2. a URL in the request: `slack.com` is Slack, `github.com` is GitHub,
   `notion.so` or `notion.site` is Notion
3. the pasted thread: Slack mentions like `<@U...>` and `:emoji:`, GitHub
   review comments with file paths and line numbers, Notion page text

When none of these settles it, ask one question naming the three channels
and stop.

Read `~/.claude/human-reply/channels/<channel>.md`. When it does not
exist, do not draft: say there is no profile for that channel and that
`/human-reply setup <channel>` builds one. There is no generic voice.

### 2. Surface and budget

Read the channel module in the `human-reply/channels/` folder. Pick the
surface from its Surfaces table by where the message will be posted. On
Slack, a 1:1 DM is an inner-circle DM when the other person is on the
`inner circle` line of `~/.claude/human-reply/profile.md`.

Take the budget and label from the profile's Surfaces row. Print this as
the first line of output, before anything else:

```
<Channel>, <surface>, budget <n> words, profile <method> <built date>[, <label> budget][, partial: <reasons>]
```

For example: `Slack, channel thread reply, budget 60 words, profile
measured 2026-09-16`. Add the `estimated budget` part when the row's
label is `estimated`, and the partial part when the profile header has a
`status` line. A wrong channel or surface shows up here before anything
is pasted.

### 3. Shape

Pick the shape from the profile's Shapes for that surface. When none
fits, use the default shape the channel module names.

### 4. Write

Write inside the budget, counting each link and each fenced block as one
word. Use:

- the profile's phrasebook, and the hedges, typing habits, disagreement
  pattern, and sign-offs from `~/.claude/human-reply/profile.md`; where the
  channel profile's Habits say otherwise, Habits win for that channel
- nothing on the Banned list
- the channel module's markup rules

A reply inside a thread never restates the thread. For `rewrite`, keep
every fact, link, code span, and mention of the original.

### 5. Audit

Check the draft against the channel module's audit checklist and every
rule under the profile's Calibration notes. Fix every hit.

### 6. Humanizer

When the `humanizer` skill is installed, run the draft through it with
the instruction in `human-reply/references/humanizer-handoff.md` and follow the checks
that file lists after it returns. On any conflict, the profile's
phrasebook wins.

### 7. Deliver

After the first line, print the draft in one fenced block with the
channel's markup exactly as it should be pasted, then one line saying
where it goes. Nothing else. For `rewrite`, that line also gives the word
count before and after.

### Audit mode

For `audit <text>`, do steps 1 to 3 and step 5 on the given text without
changing it. Print the first line, then each checklist or calibration hit
with the offending line quoted, then the word count against the budget,
then `pass` or `fail`.

## Called by another skill

`pr-watch` calls `draft` with channel `github`, the surface, and the
content the reply must carry as the ask. Put that content in the draft.
Do not read the caller's own rules; items it wants included or removed
arrive in the ask.
````

- [ ] **Step 2: Write the profile schema**

`skills/team-tooling/human-reply/references/profile-schema.md`:

````markdown
# Profile schema

The normative formats for the files setup writes under
`~/.claude/human-reply/` and for what a reader subagent returns. Headings
are fixed: runtime reads the files by section and a person edits them by
hand. A section with nothing in it keeps its heading.

## profile.md

```
# Voice profile
built: 2026-09-16 | method: measured | channels: slack, github
cutoff: 2026-01 | window: 2025-09-16..2026-09-16
inner circle: Ana, Raj
borrowed from: Mei (traits listed below)

## Hedges
- "I think", at most one hedge per message [slack, github]

## Typing habits
- keeps apostrophes out of contractions in short messages [slack, github]

## Disagreement
- first sentence states the disagreement, second gives the reason [slack, github]

## Sign-offs
- asks end with "Thanks!" and nothing after [slack, github]

## Banned
- anything on the humanizer skill's word list
- "Great catch" [slack, github]

## Borrowed traits
- opens replies with the verdict, no greeting | from Mei | adopted 2026-09-16 | told: yes
```

Header lines:

- `method` is the Python probe from the detect step: `measured` or
  `estimated`. Each channel file's own `method` is authoritative for that
  channel.
- `cutoff` is `YYYY-MM` or `never`. `inner circle` is `none` when empty.
  `borrowed from` is `none` when nothing was adopted.

Voice entries are one line each and end with the channels that returned
them in square brackets. An entry lives here only when two or more
channels returned it. The `humanizer` line under Banned is always present
and has no channels.

## channels/<channel>.md

```
# Slack voice
sample: 1412 messages, 2025-09-16..2026-09-16, 61 dropped by the AI filter | method: measured | threshold: 3 | redaction: script
status: partial (drop rate 0.46 after the threshold adjustment)

## Surfaces
| Surface | Audience | Records | Median | 75th | 90th | Budget | Label | Register |
|---|---|---|---|---|---|---|---|---|
| outer DM | anyone else, 1:1 | 212 (140 pre-cutoff) | 14 | 22 | 38 | 40 | measured | greeting only on first contact of the day |

## Pattern rates
| Pattern | Share of messages over 60 words |
|---|---|
| hedge | 0.35 |

| Quarter | Messages | 90th | Over 150 words |
|---|---|---|---|
| 2025Q4 | 310 | 41 | 0.01 |

## Phrasebook
### openers
- "Hey folks" (12)

## Shapes
### outer DM: quick answer
When: a direct question with a yes or no answer.
Skeleton:
    <answer>. <one reason>.
Examples:
    yes, <name> merged it this morning. it is behind the flag still.

## Habits
- lowercase first letter in DMs

## Calibration notes
- DMs to the squad stay under ten words
```

Header lines:

- `sample` gives the kept record count, the window, and the drop count.
- `method` is `measured` or `estimated` for this channel.
- `threshold` is always written; runtime and `pr-watch` read it.
- `redaction` is `script` or `model`.
- `status` is present only when the channel is partial, and lists every
  reason from `setup.json` separated by `; `.

Surfaces table:

- One row per surface in the channel module's `surfaces` block, in that
  order, even when the surface has no records.
- `Records` shows the total and, in brackets, the pre-cutoff count.
- On an estimated channel, `Median`, `75th`, and `90th` hold ranges and
  the budget is derived from the upper bound of the `90th` range.
- `Label` is `measured` or `estimated`. `Register` comes from the channel
  module's Surfaces table, amended by calibration notes.

Shapes use `### <surface>: <shape name>`, then `When:`, `Skeleton:`, and
`Examples:` with each skeleton and example indented four spaces.

## Reader return format

A reader subagent returns one JSON object:

```
{
  "shapes": [
    {"surface": "outer DM", "name": "quick answer",
     "when": "a direct question with a yes or no answer",
     "skeleton": "<answer>. <one reason>.",
     "examples": ["yes, <name> merged it this morning. it is behind the flag still."]}
  ],
  "phrasebook": {
    "openers": ["Hey folks"], "asks": [], "evidence": [], "hedges": ["I think"],
    "pivots": [], "closers": [], "visibility": [], "tone markers": []
  },
  "typing_habits": ["lowercase first letter in DMs"],
  "disagreement": ["first sentence states the disagreement, second gives the reason"],
  "sign_offs": ["asks end with \"Thanks!\" and nothing after"],
  "banned": ["never writes \"Great catch\""]
}
```

- `surface` is a surface name from the channel module.
- `phrasebook` has exactly the eight role keys shown; a role with nothing
  is an empty list.
- `banned` lists constructions common in drafted messages that the person
  never uses in the sample.
- No other keys. After the merge, each phrasebook phrase becomes
  `{"phrase": "...", "count": n}`.
````

- [ ] **Step 3: Write the humanizer handoff**

`skills/team-tooling/human-reply/references/humanizer-handoff.md`:

`````markdown
# Humanizer handoff

The draft step runs a finished draft through the `humanizer` skill when it
is installed. Pass the draft with this instruction, with the slots
filled, and nothing else:

````
Remove AI writing patterns from the draft below. Constraints:
- You may delete words or replace a word or phrase with a plainer one.
  Never add a sentence, a clause, a greeting, a sign-off, or a caveat.
- Keep every fact, number, link, code span, fenced block, @mention, and
  placeholder in angle brackets exactly as written.
- Keep the markup: line breaks, blank lines after quote lines, bullets,
  and backticks stay where they are.
- These phrases are the author's own. Keep them even if your list flags
  them: <phrasebook phrases used in the draft, one per line, or "none">
- The draft must stay at or under <budget> words.
Return only the edited draft.

<draft>
````

After it returns:

1. Check that every phrase passed as the author's own is still there. Put
   back any that was removed.
2. Count words. Over the budget, trim the humanizer's output, never by
   restoring cut text.
3. Run the channel audit checklist again.
`````

- [ ] **Step 4: Validate and test**

Run: `python scripts/validate.py`
Expected: `OK`.

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `OK`.

- [ ] **Step 5: Commit**

```
git add skills/team-tooling/human-reply/SKILL.md skills/team-tooling/human-reply/references/profile-schema.md skills/team-tooling/human-reply/references/humanizer-handoff.md
git commit -m "Add the human-reply router, profile schema, and humanizer handoff"
```

- [ ] **Step 6: Check the size and open PR 1**

Run: `git diff origin/main --stat`
Expected: 15 files changed.

Push the branch and open the PR against `main` with the repo's PR template if one exists. The body says what the engine does, that the skill is not installable yet because setup lands in the next PR, the deviations list from this plan in present tense, and the test command. No attribution footer.

---

## PR 2: setup

Worktree: `EnterWorktree` from `human-reply-engine`, then `git switch -c human-reply-setup`.

### Task 5: Measure

**Files:**
- Create: `skills/team-tooling/human-reply/scripts/measure.py`
- Test: `skill-tests/human-reply/tests/test_measure.py`

**Interfaces:**
- Consumes: `corpus.is_pre_cutoff`, `load_surfaces`, `read_jsonl`, `record_id`, `word_count` (Task 1).
- Produces: `percentile(values, p)` nearest rank, `round_up_to_ten(n)`, `surface_stats(records, surfaces, cutoff) -> {surface: {records, pre_cutoff_records, median, p75, p90, budget, label, over_budget}}`, `pattern_rates(records)`, `quarters(records) -> {"2025Q1": {messages, p90, over_150}}`, `measure(records, surfaces, cutoff, channel) -> stats dict` excluding held-out records. CLI `--corpus --module --cutoff --out`, stdout `measure: <n> records, <m> over 60 words`.

- [ ] **Step 1: Write the failing test**

```python
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
SKILL = REPO / "skills" / "team-tooling" / "human-reply"
sys.path.insert(0, str(SKILL / "scripts"))

import corpus  # noqa: E402
import measure  # noqa: E402

SLACK = SKILL / "channels" / "slack.md"
SURFACES = {"outer DM": {"minimum": 20, "default": 50}, "write-up": {"minimum": 60, "default": 150}}


def words(n):
    return " ".join(["w"] * n)


def record(n, surface="outer DM", ts="2025-06-01T00:00:00Z", held_out=False, text=None, audience="D1"):
    return {"channel": "slack", "surface": surface, "ts": ts, "audience": audience, "thread": f"{audience}/{ts}",
            "others": 1, "text": text if text is not None else words(n), "held_out": held_out}


class PercentileTests(unittest.TestCase):
    def test_nearest_rank(self):
        values = list(range(1, 11))
        self.assertEqual([measure.percentile(values, p) for p in (50, 75, 90, 100)], [5, 8, 9, 10])

    def test_a_single_value_is_every_percentile(self):
        self.assertEqual(measure.percentile([7], 90), 7)

    def test_round_up_to_ten(self):
        self.assertEqual([measure.round_up_to_ten(n) for n in (1, 10, 11, 36)], [10, 10, 20, 40])


class SurfaceTests(unittest.TestCase):
    def test_thirty_pre_cutoff_records_derive_the_budget_from_their_90th_percentile(self):
        records = [record(n) for n in range(1, 31)]
        records += [record(200, ts="2026-03-01T00:00:00Z") for _ in range(10)]
        row = measure.surface_stats(records, SURFACES, "2026-01")["outer DM"]
        self.assertEqual((row["records"], row["pre_cutoff_records"]), (40, 30))
        self.assertEqual((row["budget"], row["label"]), (30, "measured"))
        self.assertEqual((row["median"], row["p75"], row["p90"]), (20, 30, 200))
        self.assertEqual(row["over_budget"], 0.25)

    def test_twenty_nine_pre_cutoff_records_take_the_default_and_are_estimated(self):
        records = [record(n) for n in range(1, 30)]
        records += [record(5, ts="2026-03-01T00:00:00Z") for _ in range(20)]
        row = measure.surface_stats(records, SURFACES, "2026-01")["outer DM"]
        self.assertEqual((row["pre_cutoff_records"], row["budget"], row["label"]), (29, 50, "estimated"))

    def test_the_budget_never_drops_below_the_module_minimum(self):
        row = measure.surface_stats([record(3) for _ in range(30)], SURFACES, None)["outer DM"]
        self.assertEqual((row["budget"], row["label"]), (20, "measured"))

    def test_no_cutoff_uses_the_whole_window(self):
        records = [record(40, ts="2026-08-01T00:00:00Z") for _ in range(30)]
        row = measure.surface_stats(records, SURFACES, None)["outer DM"]
        self.assertEqual((row["pre_cutoff_records"], row["budget"]), (30, 40))

    def test_an_empty_surface_still_gets_a_row(self):
        row = measure.surface_stats([], SURFACES, None)["write-up"]
        self.assertEqual(row, {"records": 0, "pre_cutoff_records": 0, "median": None, "p75": None, "p90": None,
                               "budget": 150, "label": "estimated", "over_budget": None})


class PatternRateTests(unittest.TestCase):
    def test_rates_are_shares_of_messages_over_sixty_words(self):
        long_a = "Hi folks, " + words(60) + " I think `Foo.Bar` is it?\ncc: @a"
        long_b = words(61) + "\n- one\n- two\n> quoted\nThanks! :slightly_smiling_face:"
        short = "Hi, I think so? " + words(3)
        rates = measure.pattern_rates([record(0, text=long_a), record(0, text=long_b), record(0, text=short)])
        self.assertEqual(rates["long_messages"], 2)
        self.assertEqual({k: rates[k] for k in ("opener", "hedge", "question", "code span", "cc line",
                                                  "bullets", "quote-reply", "sign-off", "emoji", "link")},
                         {"opener": 0.5, "hedge": 0.5, "question": 0.5, "code span": 0.5, "cc line": 0.5,
                          "bullets": 0.5, "quote-reply": 0.5, "sign-off": 0.5, "emoji": 0.5, "link": 0.0})

    def test_no_long_messages_gives_no_rates(self):
        self.assertIsNone(measure.pattern_rates([record(5)])["opener"])


class DriftTests(unittest.TestCase):
    def test_quarters_report_the_90th_percentile_and_the_share_over_150_words(self):
        records = [record(10, ts="2025-02-01T00:00:00Z"), record(20, ts="2025-03-01T00:00:00Z"),
                   record(160, ts="2025-11-01T00:00:00Z"), record(30, ts="2025-12-01T00:00:00Z")]
        self.assertEqual(measure.quarters(records), {
            "2025Q1": {"messages": 2, "p90": 20, "over_150": 0.0},
            "2025Q4": {"messages": 2, "p90": 160, "over_150": 0.5},
        })


class MeasureTests(unittest.TestCase):
    def test_held_out_records_are_not_measured_and_long_ids_are_listed(self):
        records = [record(70, audience="D1"), record(70, audience="D2", held_out=True), record(10, audience="D3")]
        stats = measure.measure(records, SURFACES, None, "slack")
        self.assertEqual(stats["surfaces"]["outer DM"]["records"], 2)
        self.assertEqual(stats["long_message_ids"], ["D1/2025-06-01T00:00:00Z"])
        self.assertEqual((stats["channel"], stats["method"], stats["cutoff"]), ("slack", "measured", "never"))

    def test_cli_writes_stats_json_for_every_module_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = pathlib.Path(tmp) / "slack.kept.jsonl", pathlib.Path(tmp) / "slack.stats.json"
            corpus.write_jsonl(source, [record(12)])
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                code = measure.main(["--corpus", str(source), "--module", str(SLACK),
                                     "--cutoff", "2026-01", "--out", str(out)])
            stats = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(list(stats["surfaces"]), list(corpus.load_surfaces(SLACK)))
        self.assertEqual(printed.getvalue(), "measure: 1 records, 0 over 60 words\n")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `ModuleNotFoundError: No module named 'measure'`.

- [ ] **Step 3: Write `measure.py`**

````python
"""Measure a filtered channel corpus and write <channel>.stats.json.

    python measure.py --corpus <channel>.kept.jsonl --module channels/<channel>.md
        --cutoff 2026-01|never --out <channel>.stats.json

Held-out records are never measured.
"""
import argparse
import json
import math
import re
import sys

from corpus import is_pre_cutoff, load_surfaces, read_jsonl, record_id, word_count

LONG_MESSAGE_WORDS = 60
VERY_LONG_WORDS = 150
BUDGET_FLOOR_RECORDS = 30

LINE_PATTERNS = {
    "cc line": re.compile(r"^\s*cc:", re.I | re.M),
    "bullets": re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+\S", re.M),
    "quote-reply": re.compile(r"^\s*>", re.M),
}
TEXT_PATTERNS = {
    "opener": re.compile(r"^\s*(?:hi|hey|hello)\b", re.I),
    "sign-off": re.compile(r"(?:thanks|thank you|cheers)[!.]*\s*(?::[a-z0-9_+\-]+:)?\s*$|:[a-z0-9_+\-]*smil[a-z_]*:\s*$", re.I),
    "hedge": re.compile(r"\b(?:i think|imo|afaik|maybe|not sure|from the top of my head)\b", re.I),
    "question": re.compile(r"\?"),
    "link": re.compile(r"https?://"),
    "code span": re.compile(r"(?<!`)`[^`\n]+`(?!`)"),
    "fenced block": re.compile(r"```"),
    "bold": re.compile(r"\*\*[^*\n]+\*\*|(?<![\w*])\*[^*\n]+\*(?![\w*])"),
    "emoji": re.compile(r":[a-z0-9_+\-]+:|[\u2600-\u27bf\U0001F300-\U0001FAFF]"),
}


def percentile(values, p):
    """Nearest-rank percentile of a non-empty list."""
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def round_up_to_ten(n):
    return int(math.ceil(n / 10) * 10)


def surface_stats(records, surfaces, cutoff):
    stats = {}
    for name, limits in surfaces.items():
        counts = [word_count(r["text"]) for r in records if r["surface"] == name]
        pre = [word_count(r["text"]) for r in records
               if r["surface"] == name and is_pre_cutoff(r, cutoff)]
        row = {"records": len(counts), "pre_cutoff_records": len(pre),
               "median": None, "p75": None, "p90": None}
        if counts:
            row.update(median=percentile(counts, 50), p75=percentile(counts, 75), p90=percentile(counts, 90))
        if len(pre) >= BUDGET_FLOOR_RECORDS:
            row["budget"] = max(round_up_to_ten(percentile(pre, 90)), limits["minimum"])
            row["label"] = "measured"
        else:
            row["budget"] = limits["default"]
            row["label"] = "estimated"
        row["over_budget"] = round(sum(c > row["budget"] for c in counts) / len(counts), 2) if counts else None
        stats[name] = row
    return stats


def pattern_rates(records):
    long = [r["text"] for r in records if word_count(r["text"]) > LONG_MESSAGE_WORDS]
    rates = {"long_messages": len(long)}
    for name, pattern in {**TEXT_PATTERNS, **LINE_PATTERNS}.items():
        rates[name] = round(sum(bool(pattern.search(t)) for t in long) / len(long), 2) if long else None
    return rates


def quarter_of(ts):
    return f"{ts[:4]}Q{(int(ts[5:7]) - 1) // 3 + 1}"


def quarters(records):
    grouped = {}
    for record in records:
        grouped.setdefault(quarter_of(record["ts"]), []).append(word_count(record["text"]))
    return {q: {"messages": len(c), "p90": percentile(c, 90),
                "over_150": round(sum(n > VERY_LONG_WORDS for n in c) / len(c), 3)}
            for q, c in sorted(grouped.items())}


def measure(records, surfaces, cutoff, channel):
    usable = [r for r in records if not r["held_out"]]
    return {
        "channel": channel,
        "method": "measured",
        "cutoff": cutoff or "never",
        "surfaces": surface_stats(usable, surfaces, cutoff),
        "pattern_rates": pattern_rates(usable),
        "quarters": quarters(usable),
        "long_message_ids": [record_id(r) for r in usable if word_count(r["text"]) > LONG_MESSAGE_WORDS],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--cutoff", required=True, help="YYYY-MM, or never")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    records = read_jsonl(args.corpus)
    cutoff = None if args.cutoff == "never" else args.cutoff
    channel = records[0]["channel"] if records else None
    stats = measure(records, load_surfaces(args.module), cutoff, channel)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"measure: {len(records)} records, {len(stats['long_message_ids'])} over {LONG_MESSAGE_WORDS} words")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
````

- [ ] **Step 4: Run the tests and watch them pass**

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `OK`.

- [ ] **Step 5: Commit**

```
git add skills/team-tooling/human-reply/scripts/measure.py skill-tests/human-reply/tests/test_measure.py
git commit -m "Add human-reply measurement and budget derivation"
```

### Task 6: GitHub collector

**Files:**
- Create: `skills/team-tooling/human-reply/scripts/github_records.py`
- Test: `skill-tests/human-reply/tests/test_github_records.py`

**Interfaces:**
- Consumes: nothing at runtime. The test uses `corpus.load_surfaces` and `validate_record` (Task 1) and the GitHub channel module.
- Produces: `discover_repos(login, since, runner) -> sorted list of owner/name`, `collect(repo, login, since, until, runner) -> records newest first`, `main(argv=None, runner=subprocess.run)`. `runner` has the `subprocess.run` signature. CLI `repos --login --since` and `records --repo --login --since --until`; records go to stdout as JSONL, the count to stderr as `github_records: <repo> <n> records`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `ModuleNotFoundError: No module named 'github_records'`.

- [ ] **Step 3: Write `github_records.py`**

```python
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
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `OK`.

- [ ] **Step 5: Smoke the discovery against the live account**

Run: `gh api user --jq .login`, then `python skills/team-tooling/human-reply/scripts/github_records.py repos --login <that login> --since 2026-06-01`
Expected: one `owner/name` per line and exit 0. Do not run `records` into a file here; that belongs to setup.

- [ ] **Step 6: Commit**

```
git add skills/team-tooling/human-reply/scripts/github_records.py skill-tests/human-reply/tests/test_github_records.py
git commit -m "Add the human-reply GitHub collector"
```

### Task 7: Setup steps 1 to 4

**Files:**
- Create: `skills/team-tooling/human-reply/setup/01-detect.md`
- Create: `skills/team-tooling/human-reply/setup/02-interview.md`
- Create: `skills/team-tooling/human-reply/setup/03-collect.md`
- Create: `skills/team-tooling/human-reply/setup/04-filter.md`

**Interfaces:**
- Consumes: every CLI from Tasks 1, 2, 3, and 6, with the flags given in their Interfaces blocks.
- Produces: `~/.claude/human-reply/corpus/setup.json` with keys `started, done, python, method, channels, skipped, seed, reused, cutoff, inner_circle, window, borrow`, and per channel `redacted, redaction, holdouts, github_repos_done, drop_rate_first, threshold, partial, calibration, dropped, method`; corpus files `<channel>.jsonl`, `<channel>.kept.jsonl`, `borrow-<channel>.jsonl`, `borrow-<channel>.kept.jsonl`.

These are prose, so there is no failing test to write first. The check is the validator plus a read-through against spec 3.1 to 3.4.

- [ ] **Step 1: Write `01-detect.md`**

````markdown
# Setup 1: Detect

Find out what can be collected before asking the person anything.

`<skill-dir>` below is the folder holding this skill's `SKILL.md`. `<home>`
is `~/.claude/human-reply`. Setup keeps its answers and progress in
`<home>/corpus/setup.json`; every later step reads it and writes back what
it decides.

## 1. Leftovers from an interrupted run

If `<home>/corpus/` exists:

- Delete every `borrow-*.jsonl` in it without asking. A colleague sample
  never outlives the run that collected it.
- If `setup.json` exists, say which step it reached and which channels it
  covers, and ask one question: resume, or start over. Start over deletes
  `<home>/corpus/` entirely. Resume skips to the first step `setup.json`
  does not mark done; the collect step picks up from the records on disk.
- If `setup.json` does not exist but `<channel>.jsonl` files do, they are
  a sample kept by an earlier finished setup. Ask one question: collect
  fresh, which deletes them, or reuse them. Reuse marks those channels as
  collected in `setup.json` under `"reused"`; the collect step then skips
  straight to validation for them and runs the first hold-out pass with
  `--reset`.

## 2. Probe the channels

| Channel | Connected when | Collector |
|---|---|---|
| Slack | a Slack message search tool that covers DMs is listed, such as `slack_search_public_and_private` | month-windowed search from the person |
| GitHub | `gh auth status` exits 0 | `<skill-dir>/scripts/github_records.py` |
| Notion | a Notion comments tool such as `notion-get-comments` is listed | recent pages, comments per page |

Deferred tools count as listed: search for them with ToolSearch before
deciding a channel is not connected.

## 3. Probe Python

Run `python3 --version`, then `python --version` if the first fails. Keep
the first one that prints `Python 3.8` or later as the interpreter for
every script call.

If neither works, say:

- the measuring step will run inside the model instead
- that costs more tokens and produces estimates in ranges, not counts
- redaction will be done by the model and checked against a fixture first
- Python installs from https://www.python.org/downloads/

Then ask: install and rerun setup, or continue without Python. Record
`method: measured` when Python works and `method: estimated` otherwise.

## 4. Report and choose

Print one table: channel, connected or not, collector. Then ask which of
the connected channels to set up. When the person invoked
`setup <channel>`, confirm that one channel instead of asking. A channel
that is not connected is recorded as skipped with the reason, and the
finish step names it.

## 5. Write the state

Write `<home>/corpus/setup.json`:

```
{
  "started": "2026-09-16",
  "done": ["detect"],
  "python": "python3",
  "method": "measured",
  "channels": ["slack", "github"],
  "skipped": {"notion": "no Notion comments tool is connected"},
  "seed": 48213
}
```

`python` is `null` when there is no interpreter. `seed` is any integer
from 1 to 99999; the hold-out steps use it so a resumed run picks the same
threads. When `setup <channel>` rebuilds one channel and profiles already
exist, `channels` holds that one channel only.
````

- [ ] **Step 2: Write `02-interview.md`**

````markdown
# Setup 2: Interview

Four questions, one per turn, in this order. Wait for each answer before
asking the next. Write every answer into `<home>/corpus/setup.json` as it
arrives, so an interrupted interview resumes at the next question.

When `<home>/profile.md` already exists, first show its `cutoff`,
`window`, and `inner circle` lines and ask whether they still hold. On a
yes, copy them into `setup.json` and ask only question 4. On a no, ask all
four.

## 1. Cutoff

Ask: "When did you start drafting messages with AI tools? A month is
enough, or say never."

- Store `"cutoff": "YYYY-MM"`, or `"cutoff": "never"`.
- Messages sent before that month are trusted. Messages from that month
  on and over sixty words go through the filter step.
- "Never" means none of the person's own messages are filtered.

## 2. Inner circle

Skip this question when Slack is not in `channels`.

Ask: "Who is your inner circle on Slack? Name the people you DM most."

Resolve each name with the Slack user search tool. When a name matches
more than one person, show the matches and ask which one, in the same
turn as nothing else. Store:

```
"inner_circle": [{"name": "Ana", "slack_id": "U0123ABCD"}]
```

An empty list is allowed; every 1:1 DM is then an outer DM.

## 3. Sample window

Ask: "How far back should I read? The default is the last twelve months."

Store `"window": {"since": "YYYY-MM-DD", "until": "YYYY-MM-DD"}`, with
`until` set to today.

When the cutoff is a month and it is on or before the month of `since`,
nothing in the window is pre-cutoff, so every budget would fall back to a
module default. Say that, and offer to move `since` back to twelve months
before the cutoff. Store whichever window the person accepts.

## 4. Borrowing from a colleague

Ask: "Is there a colleague whose writing you want to borrow from? Give
their name and the channel to read them on, or say no."

On a name, ask one follow-up: "Have you told them their messages will be
read for this?"

- On a yes, resolve the colleague on that channel: a Slack user id, a
  GitHub login, or a Notion user id from the Notion user search. Store:

  ```
  "borrow": {"name": "Ana", "channel": "slack", "author": "U0123ABCD", "told": "2026-09-16"}
  ```

- On a no, store `"borrow": null` and say the colleague sample is skipped
  until they have been told.
- The borrow channel must be one of `channels`; when it is not, say so and
  store `"borrow": null`.

Add `"interview"` to `done`.
````

- [ ] **Step 3: Write `03-collect.md`**

````markdown
# Setup 3: Collect

Write each chosen channel's messages to `<home>/corpus/<channel>.jsonl`,
one record per line in the shape from `human-reply/references/corpus-record.md`, then
mark hold-out threads. Channels run one at a time, in the order listed in
`setup.json`.

Every path passed to a script is absolute: resolve `<home>` and
`<skill-dir>` once and use the resolved paths. `<py>` is the interpreter
stored in `setup.json`.

A channel listed under `"reused"` in `setup.json` skips sections 1 to 6
and starts at section 7, and its first hold-out pass adds `--reset`.

## 1. Redaction comes first

Nothing unredacted is written to disk, not even a temp file.

With Python, records reach disk only through `redact.py`, which reads
JSONL on stdin and appends to `--out`. Pipe a batch in with a quoted
heredoc from Bash:

```
<py> <skill-dir>/scripts/redact.py --out <home>/corpus/slack.jsonl <<'RECORDS'
{"channel": "slack", "surface": "outer DM", ...}
RECORDS
```

or with a single-quoted here-string from PowerShell:

```
@'
{"channel": "slack", "surface": "outer DM", ...}
'@ | <py> <skill-dir>/scripts/redact.py --out <home>/corpus/slack.jsonl
```

Keep the `redact: N of M records touched` line from each batch and add
the touched counts up per channel in `setup.json` as `"redacted"`.

Without Python, redact by hand using the patterns in
`scripts/redact.py`: a whole private-key block becomes
`<redacted:private-key>`, and every match of the other patterns becomes
`<redacted:kind>` with the kind named beside the pattern. Before the first
record of the run is written, redact every case in
`human-reply/references/redaction-check.md` and compare with its expected output. On
any miss, stop setup and say Python is required to collect. On a pass,
append records with the shell and set `"redaction": "model"` for the
channel in `setup.json`; the finish step reads it.

## 2. Resume point

When `<home>/corpus/<channel>.jsonl` already has records, run:

```
<py> <skill-dir>/scripts/corpus.py oldest --corpus <home>/corpus/<channel>.jsonl
```

and continue collecting backwards from that date instead of from
`window.until`. Duplicates are removed later by `normalize`. Without
Python, read the oldest `ts` from the file.

## 3. Slack

Get the person's own Slack user id from the search tool's description or
from the user search tool.

Search one calendar month at a time, newest month first, and run two
windows per month: one with `channel_types` set to
`public_channel,private_channel`, one with `im,mpim`. The newest month
ends at `window.until` and the oldest starts at `window.since`. Each call:

- `query`: `from:<@USER_ID> after:<last day of the previous month> before:<first day of the next month>`
- `sort`: `timestamp`, `sort_dir`: `desc`, `limit`: 20, `include_context`: false
- `cursor`: the cursor from the previous page, empty on the first page

A window ends when no cursor comes back, or when a page is short and the
page before it was short too. An empty page after a full one does not end
the window; ask for the next page. The search stops at 20 pages. When a
window reaches page 20, start a new window with the same `after:` and
`before:` set to the day after the oldest message captured so far; the
one-day overlap is removed by `normalize`.

Build one record per message:

| Field | Value |
|---|---|
| `surface` | a 1:1 DM whose other member's id is in `inner_circle`: `inner-circle DM`; any other 1:1 DM: `outer DM`; a group DM: `group DM`; a channel message with a thread timestamp different from its own: `channel thread reply`; any other channel message: `channel new post` at 120 words or fewer, `write-up` over 120 |
| `ts` | the message timestamp converted to UTC `YYYY-MM-DDTHH:MM:SSZ` |
| `audience` | the channel or DM id |
| `thread` | `<channel id>/<thread ts>`, or `<channel id>/<ts>` outside a thread |
| `others` | 1 for a 1:1 DM; the member count minus one for a group DM, or 2 when unknown; 1 for a thread reply; 1 for a top-level post that shows replies, 0 otherwise |
| `text` | the message text as returned |

Pipe each page's records through redaction before asking for the next
page. After each month, run:

```
<py> <skill-dir>/scripts/corpus.py normalize --corpus <home>/corpus/slack.jsonl --cap 1500
```

Stop when it reports 1500 kept or the month is before `window.since`.

## 4. GitHub

```
gh api user --jq .login
<py> <skill-dir>/scripts/github_records.py repos --login <login> --since <window.since>
```

For each repo it prints, collect and redact in one pipe, then add the repo
to `"github_repos_done"` in `setup.json` so a resumed run skips it:

```
<py> <skill-dir>/scripts/github_records.py records --repo <owner/name> --login <login> --since <window.since> --until <window.until> | <py> <skill-dir>/scripts/redact.py --out <home>/corpus/github.jsonl
```

A repo that fails with a 403 or 404 is skipped and named in the summary.
After the last repo, run `normalize` with `--cap 1500`.

Without Python, call the same `gh search` and `gh api` endpoints that
`scripts/github_records.py` calls and build the same records by hand.

## 5. Notion

1. Fetch `{"id": "self"}` with the Notion fetch tool to get the person's
   user id.
2. List pages: the recent pages tool with `limit` 200 and its cursor, plus
   the Notion search tool with `filters.created_by_user_ids` set to the
   person and `filters.created_date_range.start_date` set to
   `window.since`. Drop repeats.
3. For each page, call the comments tool twice: once with `page_id` only,
   which returns page-level discussions, and once with
   `include_all_blocks: true` and `include_resolved: true`. A discussion
   in the first answer is a `page comment` discussion; one only in the
   second is an `inline comment` discussion.
4. For each comment the person wrote inside the window, build a record:
   `audience` is the page id, `thread` is `<page id>/<discussion id>`,
   `others` is the number of other authors in the discussion.
5. Pipe each page's records through redaction. Stop at 500 records after
   `normalize --cap 500`, or when the pages run out.

Tell the person that Notion comments are reached page by page, so the
sample covers only pages they visited or created recently.

## 6. Colleague sample

Skip unless `borrow` is set. Run the collector for `borrow.channel` with
the colleague as author and write to
`<home>/corpus/borrow-<channel>.jsonl`:

- Slack: `from:<@author id>`, with `channel_types` set to
  `public_channel,private_channel` only.
- GitHub: `github_records.py` with `--login <colleague login>`.
- Notion: comments whose author is the colleague's user id.

Cap at 300 with `normalize --cap 300`. Borrow records are never held out
and never measured.

## 7. Validate

For each channel file, and the borrow file when there is one:

```
<py> <skill-dir>/scripts/corpus.py validate --corpus <home>/corpus/<channel>.jsonl --module <skill-dir>/channels/<channel>.md
```

A record that fails is fixed by rebuilding it from the source, never by
editing the redacted text. Without Python, check every field against
`human-reply/references/corpus-record.md`.

## 8. Hold out, first pass

For each channel in `channels`:

```
<py> <skill-dir>/scripts/corpus.py holdout --corpus <home>/corpus/<channel>.jsonl --cutoff <cutoff> --seed <seed>
```

This marks up to three pre-cutoff threads, or threads from the whole
window when the cutoff is `never`, where someone other than the person
took part. Store the printed list as `"holdouts"` for the channel. The
filter step runs the second pass when a channel got fewer than three.

Without Python, pick the threads at random under the same rule and set
`held_out` to `true` on every record of each chosen thread.

Add `"collect"` to `done`, and print per channel: records kept, date of
the oldest record, records touched by redaction, and hold-out threads
marked.
````

- [ ] **Step 4: Write `04-filter.md`**

````markdown
# Setup 4: Filter

Drop the messages that read as AI-written, using the score and threshold
in `human-reply/references/ai-filter.md` and the pattern list in each channel
module's `ai-filter` block. Channels run one at a time.

## 1. First run and first read

```
<py> <skill-dir>/scripts/ai_filter.py --corpus <home>/corpus/<channel>.jsonl --module <skill-dir>/channels/<channel>.md --reference <skill-dir>/references/ai-filter.md --cutoff <cutoff> --kept <home>/corpus/<channel>.kept.jsonl
```

It prints `total`, `scanned`, `dropped`, `drop_rate`, `threshold`, and up
to five dropped `samples`, each with the patterns it hit. Store
`drop_rate` as `"drop_rate_first"` for the channel.

Show the person the drop count out of the total, and the five samples
with their hits, each sample cut to its first 300 characters.

## 2. The one adjustment

When `drop_rate_first` is over 0.4, say that more than 40 percent of the
channel was dropped and name the two likely causes:

- the cutoff month is wrong, and messages from before AI drafting are
  being scanned
- the person writes in this shape by default

Ask them to pick one: re-ask the cutoff, or raise the threshold by one.

When `drop_rate_first` is 0.4 or less, ask whether the drops look right,
and offer the same adjustment as optional: a new threshold from 1 up to
4, or no change.

Only one adjustment per channel:

- **New cutoff.** Ask the cutoff question from the interview step again.
  Store the answer, then clear and redo the hold-outs, since the old ones
  were chosen against the old date:

  ```
  <py> <skill-dir>/scripts/corpus.py holdout --corpus <home>/corpus/<channel>.jsonl --cutoff <new cutoff> --seed <seed> --reset
  ```

- **New threshold.** Lower is allowed to any value from 1. Higher is
  allowed by one point, to 4. Store `"threshold": <n>` for the channel.

Rerun the filter command with the new `--cutoff` or `--threshold`. A
channel with no adjustment keeps threshold 3 and needs no rerun.

## 3. Second read

Read `drop_rate` from the latest run. When it is over 0.4, do not loop:
keep the filtered set, add
`"drop rate <rate> after the threshold adjustment"` to the channel's
`"partial"` list in `setup.json`, and tell the person the channel will be
marked partial for that reason.

## 4. Enough records

Count the records in `<channel>.kept.jsonl` that are not held out. Under
100, there is no profile for this channel: say the sample is too small to
measure and offer two ways on:

- widen the window: ask the window question again, then rerun the collect
  step for this channel
- move the cutoff later: ask the cutoff question again, then rerun this
  step

When the person declines both, move the channel from `channels` to
`skipped` with the reason `fewer than 100 records after the filter`.

## 5. Hold out, second pass

Skip when the channel already has three hold-out threads or the cutoff is
`never`. Otherwise:

```
<py> <skill-dir>/scripts/corpus.py holdout --corpus <home>/corpus/<channel>.jsonl --cutoff <cutoff> --seed <seed> --passed <home>/corpus/<channel>.kept.jsonl
```

Threads already held out come back with pool `earlier`. New ones come
from post-cutoff threads whose every message passed the filter, with pool
`post-cutoff`. Store the list as the channel's `"holdouts"`, then rerun
the filter command with the channel's threshold so the kept file carries
the new marks.

When a channel still has no hold-out thread, set
`"calibration": "skipped"` for it and add
`"no thread with another participant to calibrate against"` to its
`"partial"` list.

## 6. Colleague sample

When `borrow` is set:

```
<py> <skill-dir>/scripts/ai_filter.py --corpus <home>/corpus/borrow-<channel>.jsonl --module <skill-dir>/channels/<channel>.md --reference <skill-dir>/references/ai-filter.md --cutoff never --borrow --kept <home>/corpus/borrow-<channel>.kept.jsonl
```

Report the drop count. No adjustment is offered on a colleague sample.

## Without Python

Score by reading. For each message in scope under `human-reply/references/ai-filter.md`,
check each pattern id the channel lists, skipping ids whose `exempt:`
list names the message's surface. Record dropped record ids per channel
in `setup.json` as `"dropped"` instead of writing a kept file; later
steps treat a dropped id as absent. The reads, the adjustment, the
100-record check, and the hold-out rules are the same.

Add `"filter"` to `done`.
````

- [ ] **Step 5: Validate**

Run: `python scripts/validate.py`
Expected: `OK`.

- [ ] **Step 6: Check each CLI line against its script**

For every command line in the four files, run the script with `--help` (for `corpus.py`, `corpus.py <subcommand> --help`) and confirm every flag the step uses is listed. Expected: no unknown flag.

- [ ] **Step 7: Commit**

```
git add skills/team-tooling/human-reply/setup/01-detect.md skills/team-tooling/human-reply/setup/02-interview.md skills/team-tooling/human-reply/setup/03-collect.md skills/team-tooling/human-reply/setup/04-filter.md
git commit -m "Add human-reply setup steps for detect, interview, collect, and filter"
```

### Task 8: Setup steps 5 to 8, README, and PR 2

**Files:**
- Create: `skills/team-tooling/human-reply/setup/05-measure.md`
- Create: `skills/team-tooling/human-reply/setup/06-read.md`
- Create: `skills/team-tooling/human-reply/setup/07-calibrate.md`
- Create: `skills/team-tooling/human-reply/setup/08-finish.md`
- Modify: `README.md` (skills table, both install blocks)

**Interfaces:**
- Consumes: `measure.py` CLI (Task 5); `setup.json` keys and corpus files (Task 7); the profile and reader formats in `human-reply/references/profile-schema.md` (Task 4); the draft mode in `SKILL.md` (Task 4).
- Produces: `~/.claude/human-reply/profile.md` and `~/.claude/human-reply/channels/<channel>.md` in the schema formats; `<channel>.stats.json`, `<channel>.read.json`, and `corpus/draft/` during setup.

- [ ] **Step 1: Write `05-measure.md`**

````markdown
# Setup 5: Measure

Turn each channel's kept records into numbers. Held-out records are never
measured.

## With Python

```
<py> <skill-dir>/scripts/measure.py --corpus <home>/corpus/<channel>.kept.jsonl --module <skill-dir>/channels/<channel>.md --cutoff <cutoff> --out <home>/corpus/<channel>.stats.json
```

`stats.json` holds, per surface in the module: `records`,
`pre_cutoff_records`, `median`, `p75`, `p90`, `budget`, `label`, and
`over_budget`; then `pattern_rates` over messages longer than sixty
words, per-quarter `quarters` with the 90th percentile and the share over
150 words, and `long_message_ids`.

A surface with 30 or more pre-cutoff records has a budget from its own
90th percentile, rounded up to ten and floored at the module minimum, and
`label: measured`. Any other surface takes the module default and
`label: estimated`.

When the script exits non-zero, show its error and ask whether to
estimate this channel instead. Do not switch without the answer. On a yes,
follow the section below for this channel only and set the channel's
`"method": "estimated"` in `setup.json`.

## No pre-cutoff records

When every surface in a channel has `pre_cutoff_records` of 0, say the
budgets have nothing from before the cutoff to measure and offer to widen
the window, which reruns the collect and filter steps for the channel.
When the person declines, keep the stats as they are, where every surface
is already on its default and labelled estimated, and add
`"budgets not measured: no messages before the cutoff"` to the channel's
`"partial"` list.

## Without Python

Dispatch one subagent per channel on the sonnet model. Give it:

- the channel module path and the corpus path
- the record ids to ignore: held-out records and ids in `"dropped"`
- the cutoff, and the word-counting rule from
  `human-reply/references/corpus-record.md`

Ask it to read a stratified sample of 300 records spread across the
surfaces in proportion to their counts, and to write
`<home>/corpus/<channel>.stats.json` with the same fields as the script,
with these differences:

- `"method": "estimated"`
- `median`, `p75`, and `p90` are ranges such as `"15-25"`
- the budget is the upper bound of the `p90` range, rounded up to ten and
  floored at the module minimum; `p90_bucket` keeps the range beside it
- every pattern rate is rounded to the nearest 0.1
- every surface row has `label: estimated`

Check the file parses as JSON before moving on.

Add `"measure"` to `done`, and print per channel a table of surface,
records, pre-cutoff records, budget, and label.
````

- [ ] **Step 2: Write `06-read.md`**

`````markdown
# Setup 6: Read

Readers turn a channel's messages into shapes, a phrasebook, and habits.
Numbers come from the measure step; readers never count words.

## 1. The sample

Readers read `<home>/corpus/<channel>.kept.jsonl` and skip every record
that is held out or whose id is in the channel's `"dropped"` list. The
sample is fixed so three readers see the same messages:

- every record over sixty words, newest first, up to 300
- 200 records of sixty words or fewer, newest first, taken one surface at
  a time in the module's surface order until 200 are taken or none remain

## 2. Three readers per channel

Dispatch three subagents on the sonnet model for each channel, in
parallel. Each gets this prompt with the slots filled:

````
Read the messages one person wrote on <channel>, from <corpus path>.
Skip records whose held_out is true and these ids (<audience>/<ts>): <dropped ids or "none">.
Read this sample: every record over sixty words, newest first, up to 300;
then 200 records of sixty words or fewer, newest first, one surface at a
time in this order until 200 are taken: <surface names from the module>.
Count words by splitting on whitespace after replacing each fenced block
and each link with one word.

The platform's shape skeletons are in <module path> under Shapes. Use
them as a starting vocabulary, not a limit.

Return only a JSON object in the reader return format from
<skill-dir>/references/profile-schema.md. Rules:
- Every example is a message from the sample, copied exactly except that
  every person's name becomes <name> and every team or squad name becomes
  <team>. Placeholders like <redacted:kind> stay as they are.
- Give two examples for a shape on a surface with 30 or more records, one
  otherwise. Surface record counts: <surface: records, from stats.json>.
- Phrasebook phrases are literal text the person wrote, three to eight
  words, grouped by role.
- Write nothing to disk.
````

## 3. Check each return

A return fails when it is not valid JSON in the reader return format, or
when a surface with 30 or more records has a shape with fewer than two
examples. Re-run a failed reader once with a fresh subagent. When the
second attempt fails too, drop that reader and add
`"reader returned off-schema twice"` to the channel's `"partial"` list.
With fewer than two readers left, there is nothing to vote on: use the
one remaining return as is.

## 4. Merge within a channel

- **Shapes, disagreement, typing habits, sign-offs, banned.** Keep an
  entry two or more readers returned. Two shapes are the same when they
  are on the same surface and their skeletons have the same slots in the
  same order. Merge their examples, drop repeats, and keep two, or one on
  a surface under 30 records.
- **Phrasebook.** No vote. Count each candidate phrase's records in the
  channel corpus, case-insensitively, ignoring held-out records:

  ```
  grep -v '"held_out": true' <home>/corpus/<channel>.kept.jsonl | grep -ciF "<phrase>"
  ```

  Keep the phrase when the count is 2 or more, with that count.

Write the merged result to `<home>/corpus/<channel>.read.json` in the
reader return format, with a `count` on each phrasebook entry.

## 5. Reconcile across channels

Voice entries are the hedges from the phrasebook, typing habits,
disagreement, sign-offs, and banned. Build a map from each entry to the
channels that returned it:

1. Start from the existing profile files, when there are any. An entry in
   `<home>/profile.md` carries its channels at the end of its line. An
   entry under `## Habits` in `<home>/channels/<channel>.md` belongs to
   that channel.
2. Remove every entry of the channels read in this run, then add their
   entries from each `<channel>.read.json`.
3. An entry with two or more channels goes into `profile.md`, with its
   channels listed. An entry with one channel goes under that channel's
   `## Habits`.

This also demotes: an entry in `profile.md` that a rebuilt channel no
longer returns drops to the Habits of the channels that still have it.
With one channel set up in total, `profile.md` voice sections stay empty
and every entry is a Habit.

Two entries are the same when they describe the same habit, even in
different words; keep the wording of the first.

## 6. Colleague traits

When `borrow` is set, dispatch one sonnet subagent on
`<home>/corpus/borrow-<channel>.kept.jsonl`:

````
Read the messages in <path>. Return only a JSON list of five to ten
traits of how this person writes, each one line that someone else could
follow, such as "opens replies with the verdict, no greeting" or "uses >
quote-reply for multi-part answers". Do not quote any message. Write
nothing to disk.
````

Show the traits numbered and ask which to adopt. Store the adopted lines
as `"borrowed"` in `setup.json`. Delete
`<home>/corpus/borrow-<channel>.jsonl` and its kept file as soon as the
answer is in.

Add `"read"` to `done`.
`````

- [ ] **Step 3: Write `07-calibrate.md`**

```markdown
# Setup 7: Calibrate

Build draft profiles, test them against threads the person really
answered, and fix what reads wrong. One round.

## 1. Draft profiles

Write the profiles in the formats from `human-reply/references/profile-schema.md`,
into `<home>/corpus/draft/` rather than their final place:

- `draft/channels/<channel>.md` for each channel in `channels`, from
  `<channel>.stats.json`, `<channel>.read.json`, the channel module's
  Surfaces table for the Audience and Register columns, and the channel's
  entries in `setup.json` for the header and status lines.
- `draft/profile.md` from `setup.json` and the reconciliation in the read
  step. Carry every voice entry of a channel not rebuilt in this run over
  from its existing profile file unchanged. Borrowed traits already in an
  existing `profile.md` stay, and the lines in `"borrowed"` are added with
  today's date.

When `setup <channel>` rebuilds one channel, copy the other channels'
existing files into `draft/channels/`, then apply the reconciliation's
Habits changes to them.

## 2. Draft against each held-out thread

For each channel whose `"calibration"` is not `skipped`, and for each
thread in its `"holdouts"`:

1. Pick the target: the person's earliest record in the thread that
   comes after a message by someone else. The context is everything in
   the thread before the target.
2. Fetch the context:
   - Slack: the thread read tool with the channel id and the thread's
     parent ts from the `thread` field.
   - GitHub: `gh api repos/<owner>/<repo>/pulls/<n>/comments` for a
     review thread, keeping the comments whose id or `in_reply_to_id` is
     the root id; `gh api repos/<owner>/<repo>/issues/<n>/comments` plus
     `gh pr view <n> --repo <owner>/<repo> --json title,body` for a
     conversation thread or review summary.
   - Notion: the comments tool with `page_id` and `discussion_id`.

   When the fetched context shows nobody but the person, drop the thread
   and say so.
3. Draft a reply to the context with the draft mode in `SKILL.md`, reading
   the profile from `<home>/corpus/draft/` instead of `<home>/`, with the
   ask "reply to the last message" and no other hint. Do not look at the
   target first.
4. Show the draft and the target side by side, with the pool the thread
   came from: `pre-cutoff`, `post-cutoff`, or `earlier`.

After all of a channel's threads are shown, ask: "What reads wrong in my
drafts? One sentence per thing." Wait for the answer.

## 3. Adjust

For each thing the person names:

- write a rule under `## Calibration notes` in
  `draft/channels/<channel>.md`, stated as an instruction, such as "never
  open a GitHub reply with a greeting"
- when it is about length, change the surface's budget and note the
  change in the rule; a budget never drops below the module minimum
- when it is about wording, remove or add phrasebook entries, and add a
  line under Banned for anything the person never says
- when it is about register, amend the surface's Register cell

## 4. Re-draft once

Re-draft the channel's first remaining held-out thread from the adjusted
draft profile, the same way as above, and show it alone. Ask one yes or
no question: "Does this read like you?" Store `"calibration": "accepted"`
or `"calibration": "rejected"` for the channel. There is no second round
either way; a rejected channel is named in the finish summary.

A channel with `"calibration": "skipped"` gets no draft and no re-draft.

Add `"calibrate"` to `done`.
```

- [ ] **Step 4: Write `08-finish.md`**

```markdown
# Setup 8: Finish

Let the person check their own messages before they are kept, write the
profiles, and clean up.

## 1. Review the examples

Profiles are permanent and their shape examples are the person's own
messages. Print every example from every `draft/channels/<channel>.md`
in one numbered list, grouped by channel and shape. Ask the person to
name any number to strike or to replace with other wording. Apply the
answer to the draft files. A shape left with no example keeps its
skeleton.

## 2. Write

Copy `<home>/corpus/draft/profile.md` to `<home>/profile.md` and each
`draft/channels/<channel>.md` to `<home>/channels/<channel>.md`,
replacing what was there.

## 3. Summary

Print:

- the path of every file written
- per channel: kept records, window, drop count, method, threshold, and
  calibration result
- every channel in `skipped`, with its reason
- every channel marked partial, with each reason

## 4. Clean up

1. Delete every `borrow-*` file in `<home>/corpus/` without asking.
2. When any channel has `"redaction": "model"`, delete `<home>/corpus/`
   and say it was deleted because the model did the redaction.
3. Otherwise ask one question: keep the collected messages, or delete
   them. Keep leaves the person's own `<channel>*.jsonl` files and deletes
   everything else in `<home>/corpus/`, including `setup.json` and
   `draft/`. Delete removes `<home>/corpus/`.

End with: `setup <channel>` rebuilds one channel, and `setup` rebuilds
all of them.
```

- [ ] **Step 5: Add human-reply to the README**

In the skills table, add this row directly after the `slack-reply` row:

```
| [`human-reply`](./skills/team-tooling/human-reply/SKILL.md) | Draft, rewrite, or audit a Slack, GitHub, or Notion message in the user's own voice. A guided setup measures the user's real messages per channel, filters out AI-drafted ones, and writes a voice profile to the home folder. Text only, never posts. |
```

In the `ln -s` block, add after the `slack-reply` line:

```
ln -s "$PWD/skills/team-tooling/human-reply"             "$HOME/.claude/skills/human-reply"
```

In the `cp -r` block, add after the `slack-reply` line:

```
cp -r skills/team-tooling/human-reply             "$HOME/.claude/skills/human-reply"
```

- [ ] **Step 6: Validate and test**

Run: `python scripts/validate.py`
Expected: `OK`.

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `OK`.

- [ ] **Step 7: Commit**

```
git add skills/team-tooling/human-reply/setup/05-measure.md skills/team-tooling/human-reply/setup/06-read.md skills/team-tooling/human-reply/setup/07-calibrate.md skills/team-tooling/human-reply/setup/08-finish.md README.md
git commit -m "Add human-reply setup steps for measure, read, calibrate, and finish"
```

- [ ] **Step 8: Check the size and open PR 2**

Run: `git diff human-reply-engine --stat`
Expected: 13 files changed.

Push and open the PR with base `human-reply-engine`. The body describes setup end to end and carries an "Acceptance" section with two empty tables that Task 9 fills: the extractor regression table and the second-person result. Mark the PR as not ready to merge until both are filled.

### Task 9: Acceptance (run by the user)

No file changes. The main session prepares the comparison; the user runs setup.

- [ ] **Step 1: Install from the PR 2 worktree**

The user links the skill from the PR 2 worktree into `~/.claude/skills/human-reply`, keeps `slack-reply` installed, and starts a new session.

- [ ] **Step 2: The user runs setup on Slack**

The user runs `/human-reply setup slack` and answers the interview. Any defect found here is fixed in the PR 2 branch, with a test when it is in a script, and setup is rerun.

- [ ] **Step 3: Compare against slack-reply (spec 9, acceptance item 1)**

Read the tier table in `skills/team-tooling/slack-reply/SKILL.md`, the phrasebook in `skills/team-tooling/slack-reply/references/corpus-notes.md`, and the generated `~/.claude/human-reply/channels/slack.md`. Fill the PR 2 table:

```
| Surface | Hand median | Generated median | Hand budget | Generated budget | Within 5 words |
```

and list every hand phrasebook entry with whether the generated phrasebook has it. Pass when every median and budget is within five words and every hand entry appears.

- [ ] **Step 4: Second person (spec 9, acceptance item 2)**

A colleague installs from the PR 2 branch and runs setup on at least one channel. Record per channel whether calibration ran and whether they accepted the re-draft. Pass when every channel that ran calibration was accepted and at least one ran. Version one is not done until this passes; PR 3 does not wait for it.

---

## PR 3: retire slack-reply

### Task 10: Delete slack-reply

Worktree: `EnterWorktree` from `human-reply-setup`, then `git switch -c retire-slack-reply`. Start only after Task 9 step 3 passes.

**Files:**
- Delete: `skills/team-tooling/slack-reply/SKILL.md`, `skills/team-tooling/slack-reply/references/corpus-notes.md`, `skills/team-tooling/slack-reply/references/shapes.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-09-11-pr-watch.md`, `docs/superpowers/specs/2026-09-11-pr-watch-design.md`

**Interfaces:**
- Consumes: the README rows added in Task 8.
- Produces: no `slack-reply` path that the validator resolves.

- [ ] **Step 1: Delete the folder**

```
git rm -r skills/team-tooling/slack-reply
```

- [ ] **Step 2: Remove its README row and install lines**

Delete the `slack-reply` row from the skills table, its `ln -s` line, and its `cp -r` line.

- [ ] **Step 3: Rewrite backticked slack-reply paths in the pr-watch docs**

Write `<scratchpad>/retire_refs.py`:

```python
import pathlib

OLD = "`" + "slack-reply/"
NEW = "`skills/team-tooling/slack-reply/"
for name in ["docs/superpowers/plans/2026-09-11-pr-watch.md", "docs/superpowers/specs/2026-09-11-pr-watch-design.md"]:
    path = pathlib.Path(name)
    with path.open(encoding="utf-8", newline="") as f:
        text = f.read()
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text.replace(OLD, NEW))
    print(name, text.count(OLD))
```

Run it from the worktree root: `python <scratchpad>/retire_refs.py`
Expected: `docs/superpowers/plans/2026-09-11-pr-watch.md 6` and `docs/superpowers/specs/2026-09-11-pr-watch-design.md 1`.

- [ ] **Step 4: Validate**

Run: `python scripts/validate.py`
Expected: `OK`.

- [ ] **Step 5: Commit, check size, open PR 3**

```
git add -A skills/team-tooling/slack-reply README.md docs/superpowers/plans/2026-09-11-pr-watch.md docs/superpowers/specs/2026-09-11-pr-watch-design.md
git commit -m "Retire slack-reply in favour of human-reply"
```

Run: `git diff human-reply-setup --stat`
Expected: 6 files changed.

Open the PR with base `human-reply-setup`. The body links PR 2's acceptance table as the reason the deletion is safe.

---

## PR 4: pr-watch and docs

Worktree: `EnterWorktree` from `retire-slack-reply`, then `git switch -c pr-watch-human-reply`.

### Task 11: pr-watch drafts through human-reply

**Files:**
- Delete: `skills/pr-tooling/pr-watch/references/reply-voice.md`
- Create: `skills/pr-tooling/pr-watch/references/reply-contract.md`
- Modify: `skills/pr-tooling/pr-watch/SKILL.md`, `skills/pr-tooling/pr-watch/steps/04-fix-path.md`, `skills/pr-tooling/pr-watch/steps/05-rereview.md`, `skills/pr-tooling/pr-watch/steps/06-notify.md`

**Interfaces:**
- Consumes: `human-reply` draft mode and the profile header and Surfaces `Label` rules (Task 4).
- Produces: section "Writing a reply" in the contract, which `04-fix-path.md` section 7 step 1 and `05-rereview.md` step 5 follow; the `voice fallback` Slack line.

- [ ] **Step 1: Replace the reply guide with the contract**

```
git rm skills/pr-tooling/pr-watch/references/reply-voice.md
```

Create `skills/pr-tooling/pr-watch/references/reply-contract.md`:

```markdown
# Reply contract

Every reply `pr-watch` posts on GitHub follows this contract. The replies
post under the user's login and must read as the user typing them by
hand. The contract says what a reply carries and what it must never say.
The wording comes from the user's voice profile when one is usable, and
is written plainly otherwise.

## Shapes

- **Fixed.** Carries the short sha and what changed. Must not restate the
  comment or explain why it was right.
- **Refuted.** Carries the evidence: file, line, what the code does. Must
  not argue or hedge; the evidence does the disagreeing.
- **Superseded.** Carries what the code says now and the commit that
  changed it.
- **Answered and left open.** Carries what is pending and why. Must not
  promise a date or future work.
- **Re-review verdict.** One line per finding: the verdict in plain words,
  then the evidence.
- **Closing a thread as author.** One line, or nothing.

A file is cited by its repo-relative path in plain text, or by a GitHub
link to the line range at a commit. Line numbers go in the link, not in
the prose.

## Never

No greeting, no thanks-opener, no "Addressed:" or "Not addressing:" or
any prefix, no restating the comment, no summary of what was checked, no
"Great catch", no promise of future work, no mention of tools, agents,
automation, or a process. No phrase lifted from any colleague. No
@-mention of a bot account.

## Writing a reply

1. **Check the profile.** Use the user's voice only when all of these
   hold:
   - `~/.claude/skills/human-reply/SKILL.md` exists
   - `~/.claude/human-reply/channels/github.md` exists
   - the lines of that file before its first `##` heading contain neither
     `partial` nor `estimated`
   - in its Surfaces table, the row for the surface being written is not
     labelled `estimated`: `review thread reply` for a thread reply,
     `issue comment` for a top-level reply

   When any of them fails, skip to step 4.
2. **Draft.** Invoke the `human-reply` skill with `draft`, channel
   `github`, the surface, and an ask that names the shape and lists what
   the shape must carry, with the facts filled in (the sha, the evidence
   link, the pending reason). Take the text inside its fenced block and
   nothing else.
3. **Audit.** Run the audit below on that text. When it passes, the reply
   is that text. When it fails, invoke `human-reply` once more with the
   same ask plus each failing item stated as content to add or remove,
   such as "include the short sha 3f9c2e1" or "remove the opening
   thanks". When the second draft also fails, go to step 4 and post the
   Slack "voice fallback" line from `pr-watch/steps/06-notify.md`.
4. **Plain reply.** Write the reply yourself in one to four plain
   sentences that carry what the shape requires and break nothing under
   Never, then run the audit below.

Under `dry_run`, the same steps run; only the posting is replaced.

## Audit before posting

Each line must answer yes.

1. Does the reply fit exactly one shape above and carry what that shape
   requires (sha, evidence, pending reason)?
2. Is the evidence a path, a line-range link, or a sha, not a paragraph?
3. Is nothing from the comment being answered repeated?
4. Is it free of everything under Never?
5. Nothing that says or implies the reply was generated, checked by a
   tool, or part of a process?
```

- [ ] **Step 2: Point the steps at the contract**

Write `<scratchpad>/contract_refs.py`:

```python
import pathlib

OLD_PATH = "pr-watch/references/" + "reply-voice.md"
EDITS = {
    "skills/pr-tooling/pr-watch/SKILL.md": [(
        "Every reply is written with\n  `" + OLD_PATH + "`.",
        "Every reply follows\n  `pr-watch/references/reply-contract.md`.",
    )],
    "skills/pr-tooling/pr-watch/steps/04-fix-path.md": [(
        "   (facts only), the short sha, and the files, using\n   `" + OLD_PATH + "`. Run its audit and its last step.",
        "   (facts only), the short sha, and the files, following Writing a reply\n   in `pr-watch/references/reply-contract.md`. Post only the reply text.",
    )],
    "skills/pr-tooling/pr-watch/steps/05-rereview.md": [(
        "   one reply on its thread written with `" + OLD_PATH + "`",
        "   one reply on its thread written by Writing a reply in `pr-watch/references/reply-contract.md`",
    )],
    "skills/pr-tooling/pr-watch/steps/06-notify.md": [(
        "| resolve failed | `Could not resolve the thread at <path>:<line>; it stays open.` |\n",
        "| resolve failed | `Could not resolve the thread at <path>:<line>; it stays open.` |\n"
        "| voice fallback | `Replied plainly on <path>:<line>: the drafted reply failed the contract audit twice.` |\n",
    )],
}
for name, pairs in EDITS.items():
    path = pathlib.Path(name)
    with path.open(encoding="utf-8", newline="") as f:
        text = f.read()
    for old, new in pairs:
        crlf = "\r\n" in text
        if crlf:
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        if text.count(old) != 1:
            raise SystemExit(f"{name}: expected one match, found {text.count(old)}")
        text = text.replace(old, new)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("edited", name)
```

Run: `python <scratchpad>/contract_refs.py`
Expected: four `edited` lines and no `expected one match` error.

- [ ] **Step 3: Rewrite backticked paths to the deleted guide in the pr-watch docs**

Write `<scratchpad>/voice_refs.py`:

```python
import pathlib
import sys

OLD = "`pr-watch/references/" + "reply-voice.md`"
NEW = "`skills/pr-tooling/pr-watch/references/" + "reply-voice.md`"
for name in sys.argv[1:]:
    path = pathlib.Path(name)
    with path.open(encoding="utf-8", newline="") as f:
        text = f.read()
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text.replace(OLD, NEW))
    print(name, text.count(OLD))
```

Run: `python <scratchpad>/voice_refs.py docs/superpowers/plans/2026-09-11-pr-watch.md docs/superpowers/specs/2026-09-11-pr-watch-design.md`
Expected: `docs/superpowers/plans/2026-09-11-pr-watch.md 3` and `docs/superpowers/specs/2026-09-11-pr-watch-design.md 2`.

Then check nothing else names the old guide:

Run: `git grep -n "reply-voice" -- skills skill-tests`
Expected: no output.

- [ ] **Step 4: Validate and run the pr-watch tests**

Run: `python scripts/validate.py`
Expected: `OK`.

Run: `python -m unittest discover -s skill-tests/pr-watch/tests -v`
Expected: `OK`.

- [ ] **Step 5: Commit**

```
git add -A skills/pr-tooling/pr-watch docs/superpowers/plans/2026-09-11-pr-watch.md docs/superpowers/specs/2026-09-11-pr-watch-design.md
git commit -m "Draft pr-watch replies through human-reply behind the posting contract"
```

### Task 12: Design docs, README links, and PR 4

**Files:**
- Create: `docs/superpowers/specs/2026-09-16-human-reply-design.md` (from branch `worktree-human-reply-design`)
- Create: `docs/superpowers/plans/2026-09-16-human-reply.md` (from branch `worktree-human-reply-design`)
- Modify: `README.md`

**Interfaces:**
- Consumes: every file from Tasks 1 to 11, since the docs cite them.
- Produces: nothing downstream.

- [ ] **Step 1: Bring the docs over**

```
git checkout worktree-human-reply-design -- docs/superpowers/specs/2026-09-16-human-reply-design.md docs/superpowers/plans/2026-09-16-human-reply.md
```

The spec already cites the deleted `slack-reply` files and the old pr-watch guide by their full `skills/...` paths, so it needs no edit.

- [ ] **Step 2: Link the docs from the README**

After the last design-doc link near the top of `README.md`, add:

```
- [2026-09-16 human-reply design](./docs/superpowers/specs/2026-09-16-human-reply-design.md)
- [2026-09-16 human-reply implementation plan](./docs/superpowers/plans/2026-09-16-human-reply.md)
```

- [ ] **Step 3: Validate and test**

Run: `python scripts/validate.py`
Expected: `OK`.

Run: `python -m unittest discover -s skill-tests/human-reply/tests -t skill-tests/human-reply/tests -v`
Expected: `OK`.

- [ ] **Step 4: Commit, check size, open PR 4**

```
git add docs/superpowers/specs/2026-09-16-human-reply-design.md docs/superpowers/plans/2026-09-16-human-reply.md README.md
git commit -m "Add the human-reply design and plan documents"
```

Run: `git diff retire-slack-reply --stat`
Expected: 11 files changed.

Open the PR with base `retire-slack-reply`. The body states the gate in plain terms: `pr-watch` drafts through `human-reply` only when the user's GitHub profile is complete and measured on the surface being written, redrafts once on an audit failure, and otherwise posts a plain reply under the contract.

### Task 13: Memory pointer (local, no PR)

**Files:**
- Modify: `~/src/config/claude/memory/slack-messages-draft-only-humanized.md`
- Modify: `~/src/config/claude/memory/MEMORY.md` (its index line for that file)

- [ ] **Step 1: Edit after PR 3 merges**

Replace every instruction to run `slack-reply` with `human-reply` (draft mode, channel slack), keeping the rest of the rule: send only to the outbox or the user's own DM, run `humanizer` after drafting, and a self-DM handover is sent rendered. Update the one-line index entry the same way.

---

## Self-review

- **Spec coverage.** 3.1 detect: Task 7 `01-detect.md`. 3.2 interview: `02-interview.md`. 3.3 collect, redaction, hold-outs: Tasks 1, 2, 6 and `03-collect.md`. 3.4 filter, both reads, threshold, second hold-out pass: Task 3 and `04-filter.md`. 3.5 measure and fallback: Task 5 and `05-measure.md`. 3.6 read, merge, reconciliation, borrow: `06-read.md`. 3.7 calibrate: `07-calibrate.md`. 3.8 finish: `08-finish.md`. 4 profile: `human-reply/references/profile-schema.md`. 5 runtime: `SKILL.md` and `human-reply/references/humanizer-handoff.md`. 6 pr-watch: Task 11. 7 failure handling: interrupted runs in `01-detect.md` and `03-collect.md`, under 100 records and drop rate in `04-filter.md`, no pre-cutoff records and script failure in `05-measure.md`, reader failures in `06-read.md`, runtime refusals in `SKILL.md`. 8 privacy: redaction before disk (Task 2, `03-collect.md`), borrow deletion (`01-detect.md`, `06-read.md`, `08-finish.md`), example review (`08-finish.md`). 9 tests: Tasks 1, 2, 3, 5, 6; acceptance in Task 9. 10 migration: Tasks 8, 10, 11, 13.
- **Placeholders.** Angle-bracket slots such as `<skill-dir>` and `<home>` are part of the skill prose and defined in `01-detect.md`. `<scratchpad>` is the executor's scratch directory.
- **Names.** `corpus.py` subcommands `validate`, `holdout` (`--passed`, `--reset`), `normalize` (`--cap`), `oldest`; `ai_filter.py` flags `--corpus --module --reference --cutoff --threshold --borrow --kept`; `measure.py` flags `--corpus --module --cutoff --out`; `github_records.py` subcommands `repos` and `records`. The setup steps use exactly these.
