import contextlib
import io
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills" / "pr-tooling" / "pr-loop-lib" / "scripts"))

import agent_cap_wait  # noqa: E402

FAKE = """import sys
print("args:" + " ".join(sys.argv[1:]))
code = int(sys.argv[sys.argv.index("--exit") + 1]) if "--exit" in sys.argv else 0
print("trace", file=sys.stderr)
sys.exit(code)
"""


def posix(path):
    return str(path).replace("\\", "/")


class AgentCapWaitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.state = self.root / "agent cap"
        self.state.mkdir()
        self.fake = self.root / "fake wait.py"
        self.fake.write_text(FAKE, encoding="utf-8")
        self.env = {"AGENT_CAP_DIR": str(self.state)}

    def tearDown(self):
        self.tmp.cleanup()

    def point(self, line):
        (self.state / agent_cap_wait.POINTER).write_text(line, encoding="utf-8")

    def point_at_fake(self):
        self.point(f'"{posix(sys.executable)}" "{posix(self.fake)}"')

    def run_main(self, *argv, env=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = agent_cap_wait.main(list(argv), self.env if env is None else env)
        return code, out.getvalue()

    def test_no_state_folder_is_free_at_once(self):
        code, out = self.run_main(env={"AGENT_CAP_DIR": str(self.root / "absent")})
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("free: no agent-cap wait command"))

    def test_a_plain_file_in_place_of_the_state_folder_is_free(self):
        blocker = self.root / "agent-cap-file"
        blocker.write_text("", encoding="utf-8")
        code, out = self.run_main(env={"AGENT_CAP_DIR": str(blocker)})
        self.assertEqual((code, out.split(":")[0]), (0, "free"))

    def test_a_state_folder_without_the_pointer_is_free(self):
        code, out = self.run_main()
        self.assertEqual((code, out.split(":")[0]), (0, "free"))

    def test_the_pointer_command_gets_the_arguments_and_its_output_and_code_pass_through(self):
        self.point_at_fake()
        for exit_code in (0, 10, 11, 64):
            code, out = self.run_main("--need", "full", "--exit", str(exit_code))
            self.assertEqual(code, exit_code)
            self.assertEqual(out.strip(), f"args:--need full --exit {exit_code}")

    def test_a_command_that_cannot_start_is_free(self):
        self.point(f'"{posix(self.root / "no-such-node.exe")}" "x.ts"')
        code, out = self.run_main("--need", "1")
        self.assertEqual(code, 0)
        self.assertIn("could not run", out)

    def test_a_command_that_crashes_is_free_and_says_why(self):
        self.point_at_fake()
        code, out = self.run_main("--exit", "1")
        self.assertEqual(code, 0)
        self.assertIn("failed with exit 1 (trace)", out)

    def test_the_default_state_folder_is_under_the_claude_home(self):
        self.assertEqual(pathlib.Path(agent_cap_wait.state_dir({})).parts[-2:], (".claude", "agent-cap"))
        self.assertEqual(agent_cap_wait.state_dir({"AGENT_CAP_DIR": "/x/cap/"}), "/x/cap")


if __name__ == "__main__":
    unittest.main()
