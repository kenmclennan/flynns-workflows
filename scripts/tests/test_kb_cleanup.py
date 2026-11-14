import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "kb-cleanup.py")


def git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True,
    )


class KbCleanupTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        git(self.dir, "init", "-b", "main")
        with open(os.path.join(self.dir, "a.md"), "w") as handle:
            handle.write("a\n")
        git(self.dir, "add", "a.md")
        git(self.dir, "commit", "-m", "base")

    def run_script(self):
        return subprocess.run(
            [sys.executable, SCRIPT], input="{}", capture_output=True, text=True, cwd=self.dir,
        )

    def test_clean_tree_prints_done(self):
        proc = self.run_script()

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["outcome"], "done")

    def test_dirty_tree_fails_naming_the_path(self):
        with open(os.path.join(self.dir, "stray.md"), "w") as handle:
            handle.write("x\n")

        proc = self.run_script()

        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("stray.md", proc.stderr)


if __name__ == "__main__":
    unittest.main()
