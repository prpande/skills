import contextlib
import io
import json
import pathlib
import tempfile
import unittest
import unittest.mock

from fakes import poll

import state_put


class StatePutTests(unittest.TestCase):
    def place(self, tmp, data, name="watch.json"):
        source = pathlib.Path(tmp) / "staged.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        destination = pathlib.Path(tmp) / "state" / name
        return source, destination

    def test_it_places_the_staged_object_at_the_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = self.place(tmp, {"prs": {"29": {"role": "authored"}}})
            self.assertEqual(state_put.main([str(source), str(destination)]), 0)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")),
                             {"prs": {"29": {"role": "authored"}}})

    def test_it_creates_a_missing_state_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = self.place(tmp, {"a": 1}, name="pr-29.json")
            self.assertEqual(state_put.main([str(source), str(destination)]), 0)
            self.assertTrue(destination.exists())

    def test_a_briefly_locked_destination_is_retried(self):
        calls = []
        real = poll.os.replace

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) <= 2:
                raise PermissionError("destination is open")
            real(src, dst)

        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(poll.os, "replace", flaky), \
                unittest.mock.patch.object(poll.time, "sleep", lambda _: None):
            source, destination = self.place(tmp, {"a": 1})
            self.assertEqual(state_put.main([str(source), str(destination)]), 0)
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"a": 1})
            self.assertEqual(len(calls), 3)

    def test_an_unreadable_source_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "staged.json"
            source.write_text("{not json", encoding="utf-8")
            destination = pathlib.Path(tmp) / "state" / "watch.json"
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(state_put.main([str(source), str(destination)]), 1)
            self.assertIn("unreadable source", err.getvalue())
            self.assertFalse(destination.parent.exists())

    def test_it_refuses_a_call_that_is_not_two_paths(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(state_put.main(["only-one.json"]), 2)
        self.assertIn("usage:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
