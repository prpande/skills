import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from fakes import SELF, HomeCase, poll, pw_paths

import discover

ORIGINS = {"D:/a": "o/r", "D:/a/sub": "o/r", "D:/b": "o/other", "D:/c": "o/r"}


def origin_of(path):
    return ORIGINS.get(str(path).replace("\\", "/"))


class Transcript:
    def __init__(self):
        self.records = []
        self.n = 0

    def call(self, command, cwd="D:/a", branch="feat-1", name="Bash", output=None,
             shape="string"):
        self.n += 1
        tid = f"t{self.n}"
        self.records.append({
            "type": "assistant", "cwd": cwd, "gitBranch": branch,
            "message": {"content": [{"type": "tool_use", "id": tid, "name": name,
                                     "input": {"command": command}}]}})
        if output is not None:
            content = {
                "string": output,
                "text-list": [{"type": "text", "text": output}],
                "tool-reference": [{"type": "tool_reference", "tool_name": "Other"},
                                   {"type": "text", "text": output}],
            }[shape]
            self.records.append({
                "type": "user", "cwd": cwd, "gitBranch": branch,
                "message": {"content": [{"type": "tool_result", "tool_use_id": tid,
                                         "content": content}]}})
        return self


def kinds(transcript):
    return discover.evidence(transcript.records, origin_of)


class EvidenceTests(unittest.TestCase):
    def test_commit_on_branch(self):
        ev = kinds(Transcript().call('git commit -m "x"'))
        self.assertEqual(ev["branches"], {("o", "r", "feat-1"): ["commit-on-branch"]})

    def test_push_on_branch_and_naming_branch(self):
        ev = kinds(Transcript().call("git push origin feat-1", branch="feat-1"))
        self.assertEqual(ev["branches"][("o", "r", "feat-1")],
                         ["push-on-branch", "push-names-branch"])

    def test_push_names_branch_via_dash_c_ignores_git_branch(self):
        ev = kinds(Transcript().call("git -C D:/a push -u origin feat-1", cwd="D:/b",
                                     branch="main"))
        self.assertEqual(ev["branches"], {("o", "r", "feat-1"): ["push-names-branch"]})

    def test_global_options_before_the_verb_are_skipped(self):
        ev = kinds(Transcript().call("git --no-optional-locks -C D:/a push -u origin feat-1",
                                     cwd="D:/b", branch="main"))
        self.assertEqual(ev["branches"], {("o", "r", "feat-1"): ["push-names-branch"]})
        for command in ("git --no-pager -c core.x=1 push origin feat-1",
                        "& git --git-dir=D:/a/.git push origin feat-1"):
            ev = kinds(Transcript().call(command, branch="feat-1"))
            self.assertEqual(ev["branches"][("o", "r", "feat-1")],
                             ["push-on-branch", "push-names-branch"], command)

    def test_remote_url_forms(self):
        for url in ("https://github.com/O/R.git", "git@github.com:o/r.git",
                    "ssh://git@github.com/o/r.git", "https://user@github.com/o/r",
                    "https://www.github.com/o/r/", "ssh://git@github.com:22/o/r"):
            self.assertEqual(discover.parse_origin(url), "o/r", url)
        for url in ("https://gitlab.com/o/r", "https://github.com.evil.io/o/r"):
            self.assertIsNone(discover.parse_origin(url), url)

    def test_ssh_host_alias_is_resolved_through_ssh_config(self):
        hosts = {"github-work": "github.com", "gh443": "ssh.github.com",
                 "ghe": "github.example.com"}
        asked = []

        def resolve(alias):
            asked.append(alias)
            return hosts.get(alias)
        for url in ("git@github-work:O/R.git", "ssh://git@github-work/o/r",
                    "github-work:o/r", "ssh://git@gh443:443/o/r.git"):
            self.assertEqual(discover.parse_origin(url, resolve), "o/r", url)
        for url in ("git@ghe:o/r.git", "git@unknown:o/r", "C:/src/r", "-oProxyCommand=x:o/r"):
            self.assertIsNone(discover.parse_origin(url, resolve), url)
        self.assertNotIn("-oProxyCommand=x", asked)
        self.assertNotIn("C", asked)

    def test_ssh_hostname_reads_the_resolved_hostname_once(self):
        discover.SSH_HOSTS.clear()
        self.addCleanup(discover.SSH_HOSTS.clear)
        done = mock.Mock(returncode=0, stdout="user git\nhostname github.com\nport 22\n")
        with mock.patch.object(discover.subprocess, "run", return_value=done) as run:
            self.assertEqual(discover.ssh_hostname("github-work"), "github.com")
            self.assertEqual(discover.ssh_hostname("github-work"), "github.com")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["ssh", "-G", "github-work"])
        with mock.patch.object(discover.subprocess, "run", side_effect=OSError("no ssh")):
            self.assertIsNone(discover.ssh_hostname("other"))

    def test_push_refspec_names_destination(self):
        ev = kinds(Transcript().call("git push origin HEAD:refs/heads/feat-2", branch="main"))
        self.assertEqual(ev["branches"][("o", "r", "feat-2")], ["push-names-branch"])

    def test_push_output_adopts_branch(self):
        out = "To github.com:o/r.git\n   1a2b3c4..5d6e7f8  feat-3 -> feat-3\n"
        ev = kinds(Transcript().call("git push", branch="main", output=out))
        self.assertEqual(ev["branches"][("o", "r", "feat-3")], ["push-output"])

    def push(self, line):
        ev = kinds(Transcript().call("git push", branch="main", output=line + "\n"))
        return ev["branches"].get(("o", "r", "feat-3"))

    def test_push_output_forms(self):
        self.assertEqual(self.push("   1a2b3c4..5d6e7f8  feat-3 -> feat-3"), ["push-output"])
        self.assertEqual(self.push(" + 1a2b3c4...5d6e7f8 feat-3 -> feat-3 (forced update)"),
                         ["push-output"])
        self.assertEqual(self.push(" * [new branch]      feat-3 -> feat-3"), ["push-output"])

    def test_push_output_with_different_sides_does_not_match(self):
        for line in ("   1a2b3c4..5d6e7f8  feat-3 -> origin/feat-3",
                     " + 1a2b3c4...5d6e7f8 feat-3 -> origin/feat-3 (forced update)",
                     " * [new branch]      feat-3 -> origin/feat-3"):
            ev = kinds(Transcript().call("git push", branch="main", output=line))
            self.assertNotIn(("o", "r", "feat-3"), ev["branches"], line)

    def test_push_shaped_line_from_a_non_push_command_is_not_evidence(self):
        line = "   1a2b3c4..5d6e7f8  feat-8 -> feat-8\n"
        for command in ("cat notes.md", "git fetch origin feat-8:feat-8",
                        "git push --dry-run origin feat-8", "git -C D:/a pull"):
            ev = kinds(Transcript().call(command, branch="main", output=line))
            self.assertNotIn(("o", "r", "feat-8"), ev["branches"], command)

    def test_fast_forward_fetch_is_not_evidence(self):
        line = " + 1a2b3c4...5d6e7f8 feat-8 -> feat-8 (forced update)\n"
        ev = kinds(Transcript().call("git fetch -f origin feat-8:feat-8", output=line))
        self.assertNotIn(("o", "r", "feat-8"), ev["branches"])

    def test_push_output_repo_follows_the_pushes_dash_c(self):
        line = "   1a2b3c4..5d6e7f8  feat-3 -> feat-3\n"
        ev = kinds(Transcript().call("git -C D:/a push", cwd="D:/b", branch="main", output=line))
        self.assertIn(("o", "r", "feat-3"), ev["branches"])

    def test_dash_c_of_another_command_is_not_the_repo(self):
        line = "   1a2b3c4..5d6e7f8  feat-3 -> feat-3\n"
        ev = kinds(Transcript().call("grep -C 3 foo; git push", branch="main", output=line))
        self.assertIn(("o", "r", "feat-3"), ev["branches"])

    def test_cd_sets_the_repo_for_later_git_segments(self):
        line = "   1a2b3c4..5d6e7f8  feat-3 -> feat-3\n"
        for command in ("cd D:/b && git push origin feat-1",
                        "Set-Location -Path 'D:/b'; git push origin feat-1",
                        "pushd D:/b && git push origin feat-1"):
            ev = kinds(Transcript().call(command, cwd="D:/a", branch="feat-1"))
            self.assertEqual(ev["branches"], {("o", "other", "feat-1"): ["push-names-branch"]},
                             command)
        ev = kinds(Transcript().call("cd D:/b; git push", cwd="D:/a", branch="main", output=line))
        self.assertEqual(ev["branches"], {("o", "other", "feat-3"): ["push-output"]})

    def test_relative_and_msys_cd_targets_resolve(self):
        ev = kinds(Transcript().call("cd sub && git push origin feat-4", cwd="D:/a", branch="main"))
        self.assertEqual(ev["branches"], {("o", "r", "feat-4"): ["push-names-branch"]})
        with mock.patch.object(discover, "WINDOWS", True):
            ev = kinds(Transcript().call("cd /d/b && git push origin feat-5", cwd="D:/a",
                                         branch="main"))
        self.assertEqual(ev["branches"], {("o", "other", "feat-5"): ["push-names-branch"]})

    def test_a_cd_with_no_target_changes_nothing(self):
        for command in ("cd && git push origin feat-1", "cd - && git push origin feat-1"):
            ev = kinds(Transcript().call(command, cwd="D:/a", branch="feat-1"))
            self.assertEqual(ev["branches"], {("o", "r", "feat-1"):
                                              ["push-on-branch", "push-names-branch"]}, command)

    def test_pr_create_result_adopts_url(self):
        url = "https://github.com/o/r/pull/7"
        ev = kinds(Transcript().call("gh pr create --fill", output=url + "\n"))
        self.assertEqual(ev["urls"], {url: ["pr-create"]})

    def test_pr_create_result_in_every_content_shape(self):
        url = "https://github.com/o/r/pull/8"
        for shape in ("string", "text-list", "tool-reference"):
            t = Transcript().call("gh pr create", output=url, shape=shape)
            self.assertEqual(kinds(t)["urls"], {url: ["pr-create"]}, shape)

    def test_viewing_or_checking_out_a_pr_is_not_evidence(self):
        url = "https://github.com/o/r/pull/8\n"
        for command in ("gh pr view 8", "gh pr checkout 8", "echo gh pr create"):
            self.assertEqual(kinds(Transcript().call(command, output=url))["urls"], {}, command)

    def test_redirections_are_not_branch_names(self):
        for command in ("git push origin feat-2 2>&1", "git push origin feat-2 > out.txt",
                        "git push origin feat-2 >> out.txt 2>&1",
                        "git push origin feat-2 | tail -3"):
            ev = kinds(Transcript().call(command, branch="main"))
            self.assertEqual(list(ev["branches"]), [("o", "r", "main"), ("o", "r", "feat-2")],
                             command)

    def test_dry_run_pushes_do_not_count(self):
        for command in ("git push --dry-run origin feat-2", "git push -n origin feat-2"):
            self.assertEqual(kinds(Transcript().call(command))["branches"], {}, command)

    def test_separators_inside_quotes_do_not_split(self):
        self.assertEqual(kinds(Transcript().call('echo "a; git push origin feat-2"'))["branches"],
                         {})
        ev = kinds(Transcript().call('git commit -m "fix; tidy | up"'))
        self.assertEqual(ev["branches"], {("o", "r", "feat-1"): ["commit-on-branch"]})

    def test_powershell_calls_count(self):
        ev = kinds(Transcript().call("git commit -m x", name="PowerShell"))
        self.assertIn(("o", "r", "feat-1"), ev["branches"])

    def test_pr_link_only_hints(self):
        t = Transcript()
        t.records.append({"type": "pr-link", "prNumber": 9, "prRepository": "o/r",
                          "prUrl": "https://github.com/o/r/pull/9"})
        ev = kinds(t)
        self.assertEqual(ev["branches"], {})
        self.assertEqual(ev["urls"], {})
        self.assertEqual(ev["hints"], {"https://github.com/o/r/pull/9"})

    def test_cwd_in_unknown_repo_or_non_write_commands_give_nothing(self):
        t = Transcript().call("git commit -m x", cwd="D:/nowhere").call("git status")
        self.assertEqual(kinds(t)["branches"], {})

    def test_commit_inside_chained_command(self):
        ev = kinds(Transcript().call("git add -A && git commit -m x"))
        self.assertIn(("o", "r", "feat-1"), ev["branches"])


class FakeDiscoverGh:
    def __init__(self):
        self.lists = {}
        self.views = {}
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        if args[:2] == ["pr", "list"]:
            repo = args[args.index("--repo") + 1]
            return json.dumps(self.lists.get(repo, []))
        if args[:2] == ["pr", "view"]:
            return json.dumps(self.views[args[2]])
        raise AssertionError(args)


def write_transcript(projects, session_id, transcript, folder="proj"):
    path = pathlib.Path(projects) / folder / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in transcript.records) + "\nnot json\n",
                    encoding="utf-8")
    return path


class DiscoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projects = self.tmp.name
        self.gh = FakeDiscoverGh()
        self.url = "https://github.com/o/r/pull/7"

    def run_discover(self, transcript):
        write_transcript(self.projects, "sess", transcript)
        return discover.discover(self.gh, "sess", SELF, origin_of, projects=self.projects)

    def listed(self):
        self.gh.lists.setdefault("o/r", []).append(
            {"number": 7, "url": self.url, "headRefName": "feat-1"})

    def view(self, state="OPEN", login=SELF, branch="feat-1"):
        self.gh.views[self.url] = {"number": 7, "url": self.url, "state": state,
                                   "headRefName": branch, "author": {"login": login}}

    def test_branch_evidence_resolves_to_open_authored_pr(self):
        self.listed()
        found = self.run_discover(Transcript().call("git commit -m x"))
        self.assertEqual(found, [{"ref": "o/r#7", "url": self.url, "branch": "feat-1",
                                  "evidence": ["commit-on-branch"]}])
        args = self.gh.calls[0]
        self.assertEqual(args[args.index("--author") + 1], SELF)
        self.assertEqual(args[args.index("--state") + 1], "open")

    def test_one_list_call_per_repo_keeps_only_branches_the_session_wrote(self):
        self.listed()
        self.gh.lists["o/r"] += [
            {"number": 8, "url": "https://github.com/o/r/pull/8", "headRefName": "feat-2"},
            {"number": 9, "url": "https://github.com/o/r/pull/9", "headRefName": "other"}]
        found = self.run_discover(Transcript().call("git commit -m a", branch="feat-1")
                                  .call("git commit -m b", branch="feat-2"))
        self.assertEqual([p["ref"] for p in found], ["o/r#7", "o/r#8"])
        self.assertEqual(sum(1 for c in self.gh.calls if c[:2] == ["pr", "list"]), 1)

    def test_a_full_pr_list_warns_that_later_prs_are_missed(self):
        self.gh.lists["o/r"] = [{"number": n, "url": f"https://github.com/o/r/pull/{n}",
                                 "headRefName": f"b{n}"} for n in range(discover.PR_LIST_LIMIT)]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.run_discover(Transcript().call("git commit -m x"))
        self.assertIn("PRs past that are not discovered", err.getvalue())

    def test_no_pr_for_branch_means_empty(self):
        self.assertEqual(self.run_discover(Transcript().call("git commit -m x")), [])

    def test_url_evidence_keeps_own_open_pr(self):
        self.view(branch="feat-9")
        found = self.run_discover(Transcript().call("gh pr create", output=self.url))
        self.assertEqual(found[0]["branch"], "feat-9")
        self.assertEqual(found[0]["evidence"], ["pr-create"])

    def test_pr_by_someone_else_is_dropped(self):
        self.view(login="other")
        self.assertEqual(self.run_discover(Transcript().call("gh pr create", output=self.url)), [])

    def test_closed_pr_is_dropped(self):
        self.view(state="MERGED")
        self.assertEqual(self.run_discover(Transcript().call("gh pr create", output=self.url)), [])

    def test_missing_author_fails_closed(self):
        self.view()
        del self.gh.views[self.url]["author"]
        self.assertEqual(self.run_discover(Transcript().call("gh pr create", output=self.url)), [])

    def test_author_comparison_ignores_case(self):
        self.view(login=SELF.upper())
        found = self.run_discover(Transcript().call("gh pr create", output=self.url))
        self.assertEqual(len(found), 1)

    def test_branch_and_url_evidence_merge_into_one_entry(self):
        self.listed()
        self.view()
        t = Transcript().call("git commit -m x").call("gh pr create", output=self.url)
        found = self.run_discover(t)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["evidence"], ["commit-on-branch", "pr-create"])

    def test_hint_without_evidence_is_dropped(self):
        t = Transcript()
        t.records.append({"type": "pr-link", "prNumber": 7, "prRepository": "o/r",
                          "prUrl": self.url})
        self.assertEqual(self.run_discover(t), [])
        self.assertEqual(self.gh.calls, [])

    def test_missing_transcript_returns_empty(self):
        self.assertEqual(discover.discover(self.gh, "nope", SELF, origin_of,
                                           projects=self.projects), [])

    def test_find_transcript_takes_newest_across_project_folders(self):
        old = write_transcript(self.projects, "sess", Transcript(), folder="a")
        new = write_transcript(self.projects, "sess", Transcript(), folder="b")
        os.utime(old, (1, 1))
        self.assertEqual(discover.find_transcript("sess", self.projects), new)
        self.assertIsNone(discover.find_transcript("other", self.projects))


class OriginParsingTests(unittest.TestCase):
    def origin(self, url):
        discover.ORIGIN_CACHE.clear()
        out = mock.Mock(returncode=0, stdout=url + "\n")
        with mock.patch.object(discover.subprocess, "run", return_value=out) as run:
            result = discover.origin_of("D:/x")
        self.assertEqual(run.call_args.kwargs["creationflags"], poll.no_window())
        return result

    def test_forms(self):
        self.assertEqual(self.origin("https://github.com/O/R.git"), "o/r")
        self.assertEqual(self.origin("https://github.com/o/r"), "o/r")
        self.assertEqual(self.origin("git@github.com:O/R.git"), "o/r")

    def test_non_github_and_failure_give_none(self):
        self.assertIsNone(self.origin("https://dev.azure.com/o/p/_git/r"))
        discover.ORIGIN_CACHE.clear()
        with mock.patch.object(discover.subprocess, "run",
                               return_value=mock.Mock(returncode=128, stdout="")):
            self.assertIsNone(discover.origin_of("D:/x"))

    def test_result_is_cached(self):
        discover.ORIGIN_CACHE.clear()
        out = mock.Mock(returncode=0, stdout="git@github.com:o/r.git\n")
        with mock.patch.object(discover.subprocess, "run", return_value=out) as run:
            discover.origin_of("D:/x")
            discover.origin_of("D:/x")
        self.assertEqual(run.call_count, 1)


class CloneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Transcript().call("x", cwd="D:/a/sub").call("x", cwd="D:/b").call("x", cwd="D:/c")
        t.call("x", cwd="D:/a/sub")
        write_transcript(self.tmp.name, "sess", t)

    def top(self, path):
        return {"D:/a/sub": "D:/a", "D:/c": "D:/c"}.get(path)

    def test_the_newest_matching_cwd_maps_to_its_top_level_and_stops_the_search(self):
        asked = []

        def counting_origin(path):
            asked.append(path)
            return origin_of(path)
        found = discover.find_clone("sess", "O", "R", counting_origin, projects=self.tmp.name,
                                    toplevel_of=self.top)
        self.assertEqual((found, asked), ("D:/a", ["D:/a/sub"]))

    def test_a_path_from_another_repo_is_skipped(self):
        t = Transcript().call("x", cwd="D:/c").call("x", cwd="D:/b")
        write_transcript(self.tmp.name, "other", t)
        self.assertEqual(discover.find_clone("other", "o", "r", origin_of, projects=self.tmp.name,
                                             toplevel_of=self.top), "D:/c")

    def test_a_git_dash_c_path_counts_as_a_clone_the_session_used(self):
        t = Transcript().call('git -C "D:/c" status', cwd="D:/b")
        t.call("git -C D:/a/sub log -1 && git status", cwd="D:/b")
        write_transcript(self.tmp.name, "dash", t)
        found = discover.find_clone("dash", "o", "r", origin_of, projects=self.tmp.name,
                                    toplevel_of=self.top)
        self.assertEqual(found, "D:/a")

    def test_a_cd_target_counts_as_a_clone_the_session_used(self):
        t = Transcript().call("Set-Location 'D:/c'; git status", cwd="D:/b")
        t.call("cd /d/a/sub && git log -1", cwd="D:/b")
        write_transcript(self.tmp.name, "cd", t)
        with mock.patch.object(discover, "WINDOWS", True):
            found = discover.find_clone("cd", "o", "r", origin_of, projects=self.tmp.name,
                                        toplevel_of=self.top)
        self.assertEqual(found, "D:/a")

    def test_no_transcript_or_no_match(self):
        self.assertIsNone(discover.find_clone("nope", "o", "r", origin_of, projects=self.tmp.name))
        self.assertIsNone(discover.find_clone("sess", "x", "y", origin_of, projects=self.tmp.name))


DRIVER = '''
import json, os, runpy, subprocess, sys
real_run = subprocess.run

def fake_run(cmd, *args, **kwargs):
    if cmd[0] == "git":
        return subprocess.CompletedProcess(cmd, 0, stdout="git@github.com:o/r.git\\n", stderr="")
    if cmd[0] != "gh":
        return real_run(cmd, *args, **kwargs)
    if cmd[1:3] == ["api", "user"]:
        return subprocess.CompletedProcess(cmd, 0, stdout="prpande\\n", stderr="")
    if cmd[1:3] == ["pr", "view"]:
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
    listed = [{"number": 8, "url": "https://github.com/o/r/pull/8", "headRefName": "feat-2"}]
    return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(listed), stderr="")

subprocess.run = fake_run
poll_py = sys.argv[1]
sys.path.insert(0, os.path.dirname(poll_py))
sys.argv = ["poll.py", "--discover", "--session-id", "sess-1"]
runpy.run_path(poll_py, run_name="__main__")
'''


def run_cli(*argv, gh=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = poll.main([str(a) for a in argv], gh=gh or FakeDiscoverGh())
    return code, out.getvalue().strip(), err.getvalue().strip()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for patcher in (mock.patch.object(discover, "projects_root",
                                          return_value=pathlib.Path(self.tmp.name)),
                        mock.patch.object(discover, "origin_of", origin_of),
                        mock.patch.object(discover, "repo_toplevel", lambda p: p)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_discover_without_transcript_prints_empty_list(self):
        code, out, err = run_cli("--discover", "--session-id", "sess-1")
        self.assertEqual((code, out, err), (0, "[]", "pr-watch: no transcript for session sess-1"))

    def test_discover_prints_found_prs(self):
        url = "https://github.com/o/r/pull/7"
        write_transcript(self.tmp.name, "sess-1", Transcript().call("gh pr create", output=url))
        gh = FakeDiscoverGh()
        gh.views[url] = {"number": 7, "url": url, "state": "OPEN", "headRefName": "f",
                         "author": {"login": SELF}}

        def routed(args):
            return SELF + "\n" if args[:2] == ["api", "user"] else gh(args)
        code, out, _ = run_cli("--discover", "--session-id", "sess-1", gh=routed)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)[0]["ref"], "o/r#7")

    def test_run_as_a_script_survives_a_failing_candidate(self):
        poll_py = pathlib.Path(poll.__file__)
        write_transcript(pathlib.Path(self.tmp.name) / ".claude" / "projects", "sess-1",
                         Transcript().call("gh pr create", output="https://github.com/o/r/pull/9")
                         .call("git commit -m b", branch="feat-2"))
        driver = pathlib.Path(self.tmp.name) / "driver.py"
        driver.write_text(DRIVER, encoding="utf-8")
        env = {**os.environ, "USERPROFILE": self.tmp.name, "HOME": self.tmp.name}
        out = subprocess.run([sys.executable, str(driver), str(poll_py)], capture_output=True,
                             text=True, env=env, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("boom", out.stderr)
        self.assertEqual([p["ref"] for p in json.loads(out.stdout)], ["o/r#8"])

    def test_find_clone_prints_first_candidate(self):
        write_transcript(self.tmp.name, "sess-1", Transcript().call("x", cwd="D:/a"))
        code, out, _ = run_cli("--find-clone", "o/r#7", "--session-id", "sess-1")
        self.assertEqual((code, out), (0, "D:/a"))

    def test_find_clone_none_known_exits_one(self):
        code, out, err = run_cli("--find-clone", "o/r#7", "--session-id", "sess-1")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err, "pr-watch: no local clone of o/r known to this session")


class HolderCloneTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for patcher in (mock.patch.object(discover, "projects_root",
                                          return_value=pathlib.Path(self.tmp.name)),
                        mock.patch.object(discover, "origin_of", origin_of),
                        mock.patch.object(discover, "repo_toplevel", lambda p: p)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def hold(self, worktree, holder="dead-1"):
        path = pw_paths.lease_path("o", "r", 7)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": 1, "holder": {"session_id": holder}}),
                        encoding="utf-8")
        watch_dir = pw_paths.session_dir(holder)
        watch_dir.mkdir(parents=True, exist_ok=True)
        (watch_dir / "watch.json").write_text(
            json.dumps({"prs": {"o/r#7": {"worktree": worktree}}}), encoding="utf-8")

    def test_falls_back_to_the_lease_holders_recorded_worktree(self):
        self.hold("D:/a")
        code, out, _ = run_cli("--find-clone", "o/r#7", "--session-id", "sess-1")
        self.assertEqual((code, out), (0, "D:/a"))

    def test_a_holder_worktree_of_another_repo_is_ignored(self):
        self.hold("D:/b")
        code, out, _ = run_cli("--find-clone", "o/r#7", "--session-id", "sess-1")
        self.assertEqual((code, out), (1, ""))

    def test_a_clone_this_session_used_wins_over_the_holders(self):
        self.hold("D:/a")
        write_transcript(self.tmp.name, "sess-1", Transcript().call("x", cwd="D:/c"))
        code, out, _ = run_cli("--find-clone", "o/r#7", "--session-id", "sess-1")
        self.assertEqual((code, out), (0, "D:/c"))


if __name__ == "__main__":
    unittest.main()
