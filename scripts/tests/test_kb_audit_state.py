import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

import kb_audit_state


class StateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.dir)
        previous = os.environ.get("LC_WORKFLOW_DATA_DIR")
        os.environ["LC_WORKFLOW_DATA_DIR"] = self.dir
        self.addCleanup(lambda: os.environ.__setitem__("LC_WORKFLOW_DATA_DIR", previous) if previous else os.environ.pop("LC_WORKFLOW_DATA_DIR", None))

    def test_first_read_is_empty(self):
        self.assertIsNone(kb_audit_state.read_sha())

    def test_write_round_trips(self):
        kb_audit_state.write_sha("abc1234")
        self.assertEqual(kb_audit_state.read_sha(), "abc1234")

    def test_repeat_write_is_idempotent(self):
        kb_audit_state.write_sha("abc1234")
        kb_audit_state.write_sha("abc1234")
        self.assertEqual(kb_audit_state.read_sha(), "abc1234")

    def test_later_write_replaces(self):
        kb_audit_state.write_sha("abc1234")
        kb_audit_state.write_sha("def5678")
        self.assertEqual(kb_audit_state.read_sha(), "def5678")

    def test_corrupt_file_is_reported(self):
        with open(kb_audit_state.state_path(), "w") as handle:
            handle.write("not json")
        with self.assertRaises(RuntimeError):
            kb_audit_state.read_sha()


if __name__ == "__main__":
    unittest.main()
