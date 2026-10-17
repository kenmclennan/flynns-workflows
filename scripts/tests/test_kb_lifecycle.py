import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
FAKE_QMD = os.path.join(HERE, "fake-qmd.py")


def git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def run(script, **env):
    full = dict(os.environ)
    for key in [k for k in full if k.startswith("LC_WORKFLOW_CONFIG_")]:
        del full[key]
    full.update(env)
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script)], capture_output=True, text=True, env=full)


class MaintainTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.remote = os.path.join(self.root, "remote.git")
        self.seed = os.path.join(self.root, "seed")
        self.checkout = os.path.join(self.root, "checkout")
        self.log = os.path.join(self.root, "qmd.log")
        subprocess.run(["git", "init", "--bare", "-b", "main", self.remote], check=True, capture_output=True)
        subprocess.run(["git", "clone", self.remote, self.seed], check=True, capture_output=True)
        self.commit_upstream("one.md")
        subprocess.run(["git", "clone", self.remote, self.checkout], check=True, capture_output=True)

    def commit_upstream(self, name):
        with open(os.path.join(self.seed, name), "w") as handle:
            handle.write("x\n")
        git(self.seed, "checkout", "-B", "main")
        git(self.seed, "add", name)
        git(self.seed, "commit", "-m", name)
        git(self.seed, "push", "origin", "main")

    def maintain(self):
        proc = run(
            "kb-maintain.py",
            LC_WORKFLOW_CONFIG_CHECKOUT_PATH=self.checkout,
            LC_WORKFLOW_CONFIG_QMD_COMMAND=FAKE_QMD,
            FAKE_QMD_LOG=self.log,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def qmd_calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as handle:
            return handle.read().split("\n")[:-1]

    def test_clean_main_pulls_and_rebuilds_the_index(self):
        self.commit_upstream("two.md")
        self.maintain()
        self.assertTrue(os.path.exists(os.path.join(self.checkout, "two.md")))
        self.assertEqual(self.qmd_calls(), ["update", "embed"])

    def test_repeat_run_is_a_no_op_pull_and_safe(self):
        self.maintain()
        self.maintain()
        self.assertEqual(self.qmd_calls(), ["update", "embed", "update", "embed"])

    def test_dirty_checkout_is_left_alone(self):
        self.commit_upstream("two.md")
        with open(os.path.join(self.checkout, "scratch.md"), "w") as handle:
            handle.write("wip\n")
        proc = self.maintain()
        self.assertIn("uncommitted", proc.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.checkout, "two.md")))
        self.assertEqual(self.qmd_calls(), [])

    def test_other_branch_is_left_alone(self):
        git(self.checkout, "checkout", "-b", "ingest/x")
        proc = self.maintain()
        self.assertIn("not main", proc.stderr)
        self.assertEqual(self.qmd_calls(), [])

    def test_unset_checkout_path_exits_quietly(self):
        proc = run("kb-maintain.py")
        self.assertEqual(proc.returncode, 0)


class InstallTests(unittest.TestCase):
    @unittest.skipUnless(all(shutil.which(t) for t in ("gh", "npx")), "gh and npx are needed")
    def test_unset_checkout_path_warns_and_passes(self):
        proc = run("kb-install.py", LC_WORKFLOW_CONFIG_QMD_COMMAND=FAKE_QMD)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("checkout-path is not set", proc.stderr)

    def test_missing_hard_tool_fails(self):
        proc = run("kb-install.py", PATH="/nonexistent", LC_WORKFLOW_CONFIG_CHECKOUT_PATH="/somewhere")
        self.assertNotEqual(proc.returncode, 0)
        for name in ("gh", "npx", "python3"):
            self.assertIn("`%s` is not on PATH" % name, proc.stderr)

    @unittest.skipUnless(all(shutil.which(t) for t in ("gh", "npx")), "gh and npx are needed")
    def test_missing_qmd_warns_and_passes(self):
        proc = run("kb-install.py", LC_WORKFLOW_CONFIG_CHECKOUT_PATH="/somewhere", LC_WORKFLOW_CONFIG_QMD_COMMAND="/nonexistent/qmd")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("qmd", proc.stderr)

    @unittest.skipUnless(all(shutil.which(t) for t in ("gh", "npx")), "gh and npx are needed")
    def test_set_checkout_path_with_dependencies_present_is_silent(self):
        proc = run("kb-install.py", LC_WORKFLOW_CONFIG_CHECKOUT_PATH="/somewhere", LC_WORKFLOW_CONFIG_QMD_COMMAND=FAKE_QMD)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
