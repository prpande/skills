import os
import pathlib
import tempfile
import unittest
import unittest.mock

from fakes import pw_paths


class PwPathsTests(unittest.TestCase):
    def test_ref_forms_lowercase(self):
        self.assertEqual(pw_paths.parse_ref("Mindbody/Mindbody.Clients#14"),
                         ("mindbody", "mindbody.clients", 14))
        self.assertEqual(pw_paths.parse_ref("https://github.com/prpande/prism-sandbox/pull/3"),
                         ("prpande", "prism-sandbox", 3))
        self.assertEqual(pw_paths.parse_ref("7", default_repo="PrPande/Skills"),
                         ("prpande", "skills", 7))

    def test_bad_refs_raise(self):
        for bad in ("7", "o/r#x", "o r/x#1", "o/r", "../x/y#1", "./r#1", "o/..#1", "o/.#1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pw_paths.parse_ref(bad)

    def test_bare_number_with_bad_default_repo_raises(self):
        with self.assertRaises(ValueError):
            pw_paths.parse_ref("7", default_repo="nope")

    def test_pr_key_lowercase(self):
        self.assertEqual(pw_paths.pr_key("Mindbody", "Mindbody.Clients", 14),
                         "mindbody/mindbody.clients#14")

    def test_case_variants_share_one_lease_path(self):
        self.assertEqual(pw_paths.lease_path("Mindbody", "Mindbody.Clients", 14),
                         pw_paths.lease_path("mindbody", "mindbody.clients", 14))

    def test_paths_under_home(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = pathlib.Path(raw)
            with unittest.mock.patch.dict(os.environ, {"PR_WATCH_HOME": raw}):
                self.assertEqual(pw_paths.home(), tmp)
                self.assertEqual(pw_paths.progress_path("o", "r", 5),
                                 tmp / "prs" / "o" / "r" / "5.progress.json")
                self.assertEqual(pw_paths.lease_path("o", "r", 5),
                                 tmp / "prs" / "o" / "r" / "5.json")
                self.assertEqual(pw_paths.pr_dir("o", "r"), tmp / "prs" / "o" / "r")
                self.assertEqual(pw_paths.session_dir("s-1"), tmp / "sessions" / "s-1")
                self.assertEqual(pw_paths.claim_lock_path("o", "r", 5).parent,
                                 pw_paths.pr_dir("o", "r"))

    def test_default_home(self):
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop("PR_WATCH_HOME", None)
            self.assertEqual(pw_paths.home(), pathlib.Path.home() / ".claude" / "pr-watch")

    def test_bad_session_id_raises(self):
        with self.assertRaises(ValueError):
            pw_paths.session_dir("../x")

    def test_iso_round_trip(self):
        self.assertEqual(pw_paths.iso_utc(2_000_000_000), "2033-05-18T03:33:20Z")
        self.assertEqual(pw_paths.parse_iso("2033-05-18T03:33:20Z"), 2_000_000_000)


if __name__ == "__main__":
    unittest.main()
