import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

import kb_audit_state
from kb_audit_helpers import git, make_remote, run


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.remote = make_remote("clean")
        self.data = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.remote)
        self.addCleanup(shutil.rmtree, self.data)
        self.tip = git(self.remote, "rev-parse", "main")
        previous = os.environ.get("LC_WORKFLOW_DATA_DIR")
        os.environ["LC_WORKFLOW_DATA_DIR"] = self.data
        self.addCleanup(lambda: os.environ.__setitem__("LC_WORKFLOW_DATA_DIR", previous) if previous else os.environ.pop("LC_WORKFLOW_DATA_DIR", None))

    def guard(self, url=None):
        return run("kb-tip-moved.py", self.data, url or self.remote)

    def record(self, sha):
        proc = run("kb-record-audited.py", self.data, self.remote, stdin=json.dumps({"schedule_state": sha}))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {"outcome": "recorded"})

    def test_no_recorded_sha_passes_as_first_audit(self):
        out = json.loads(self.guard().stdout)
        self.assertEqual(out["outcome"], "pass")
        self.assertEqual(out["state"], self.tip)
        self.assertIn("first audit", out["description"])

    def test_unchanged_tip_fails_and_files_nothing(self):
        self.record(self.tip)
        proc = self.guard()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["outcome"], "fail")
        self.assertNotIn("state", out)

    def test_moved_tip_passes_with_the_sha_as_state(self):
        self.record(self.tip)
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work)
        git(work, "clone", self.remote, "w")
        clone = os.path.join(work, "w")
        with open(os.path.join(clone, "extra.md"), "w") as handle:
            handle.write("# Extra\n")
        git(clone, "add", "extra.md")
        git(clone, "commit", "-m", "more")
        git(clone, "push", "origin", "main")
        out = json.loads(self.guard().stdout)
        self.assertEqual(out["outcome"], "pass")
        self.assertEqual(out["state"], git(self.remote, "rev-parse", "main"))
        self.assertIn("1 commit(s) since", out["description"])

    def test_failing_ls_remote_does_not_pass(self):
        proc = self.guard(url=os.path.join(self.data, "no-such-repo"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")

    def test_record_rejects_a_non_sha(self):
        proc = run("kb-record-audited.py", self.data, self.remote, stdin=json.dumps({"schedule_state": "not a sha"}))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIsNone(kb_audit_state.read_sha())


if __name__ == "__main__":
    unittest.main()
