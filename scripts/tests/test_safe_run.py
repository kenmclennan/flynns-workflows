import ast
import os
import stat
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SCRIPTS, "lib"))

import safe_run

FAKE = os.path.join(HERE, "fake-hang.py")


class SafeRunTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.dir)
        self.counter = os.path.join(self.dir, "count")
        self.pidfile = os.path.join(self.dir, "pid")
        self.patch_env("FAKE_HANG_COUNT", self.counter)
        for name in ("FAKE_HANG_FAIL", "FAKE_HANG_EXIT", "FAKE_HANG_PIDFILE"):
            self.patch_env(name, None)
        previous = safe_run.RETRY_PAUSE
        safe_run.RETRY_PAUSE = 0
        self.addCleanup(setattr, safe_run, "RETRY_PAUSE", previous)

    def patch_env(self, name, value):
        previous = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
        self.addCleanup(lambda: os.environ.pop(name, None) if previous is None else os.environ.__setitem__(name, previous))

    def attempts(self):
        if not os.path.exists(self.counter):
            return 0
        with open(self.counter) as handle:
            return len(handle.read().split())

    def fake_tool(self, name):
        path = os.path.join(self.dir, name)
        with open(path, "w") as handle:
            handle.write("#!%s\n" % sys.executable)
            handle.write("import os, sys\nos.execv(sys.executable, [sys.executable, %r] + sys.argv[1:])\n" % FAKE)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return path

    def run_failing(self, cmd, **kwargs):
        with self.assertRaises(SystemExit) as caught:
            safe_run.run(cmd, **kwargs)
        self.assertEqual(caught.exception.code, 1)

    def capture_stderr(self, cmd, **kwargs):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            self.run_failing(cmd, **kwargs)
        return buffer.getvalue()

    def test_hanging_local_command_returns_within_the_limit(self):
        started = time.monotonic()
        message = self.capture_stderr([sys.executable, FAKE], timeout=1)
        self.assertLess(time.monotonic() - started, 10)
        self.assertIn("timed out after 1s", message)
        self.assertIn(os.path.basename(sys.executable), message)
        self.assertEqual(self.attempts(), 1)

    def test_network_read_is_attempted_twice(self):
        message = self.capture_stderr([sys.executable, FAKE], timeout=1, network=True)
        self.assertEqual(self.attempts(), 2)
        self.assertIn("both attempts", message)

    def test_network_read_with_transient_exit_is_retried_once(self):
        self.patch_env("FAKE_HANG_FAIL", "fatal: unable to access 'x': Could not resolve host")
        git = self.fake_tool("git")
        self.run_failing([git, "fetch", "origin"], timeout=5)
        self.assertEqual(self.attempts(), 2)

    def test_non_transient_exit_is_returned_without_retry(self):
        self.patch_env("FAKE_HANG_FAIL", "error: no such ref")
        proc = safe_run.run([sys.executable, FAKE], timeout=5, network=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no such ref", proc.stderr)
        self.assertEqual(self.attempts(), 1)

    def test_hanging_write_runs_once_for_a_gh_issue_close(self):
        gh = self.fake_tool("gh")
        message = self.capture_stderr([gh, "issue", "close", "1", "--comment", "c"], timeout=1)
        self.assertEqual(self.attempts(), 1)
        self.assertIn("may have been applied", message)

    def test_hanging_write_runs_once_for_a_gh_api_post(self):
        gh = self.fake_tool("gh")
        self.run_failing([gh, "api", "repos/o/r/issues", "--method", "POST"], timeout=1)
        self.assertEqual(self.attempts(), 1)

    def test_hanging_write_runs_once_when_marked(self):
        self.run_failing([sys.executable, FAKE], timeout=1, write=True)
        self.assertEqual(self.attempts(), 1)

    def test_transient_write_exit_is_returned_unchanged(self):
        self.patch_env("FAKE_HANG_FAIL", "HTTP 502")
        gh = self.fake_tool("gh")
        proc = safe_run.run([gh, "issue", "close", "1"], timeout=5)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.attempts(), 1)

    def test_gh_write_classification(self):
        writes = [
            ["issue", "close", "1"], ["issue", "comment", "1"], ["pr", "create"],
            ["api", "-X", "PATCH", "x"], ["api", "--method", "DELETE", "x"], ["api", "x", "-f", "k=v"],
        ]
        reads = [["issue", "list"], ["issue", "view", "1"], ["api", "repos/o/r/issues"]]
        for args in writes:
            self.assertTrue(safe_run.classify(["gh"] + args)[1], args)
        for args in reads:
            self.assertEqual(safe_run.classify(["gh"] + args), (True, False), args)

    def test_default_timeouts_are_pinned(self):
        self.assertEqual(safe_run.default_timeout(["git", "push", "origin"]), 600)
        self.assertEqual(safe_run.default_timeout(["git", "fetch", "origin"]), 120)
        self.assertEqual(safe_run.default_timeout(["git", "--git-dir", "x", "ls-remote", "u"]), 120)
        self.assertEqual(safe_run.default_timeout(["git", "status"]), 60)
        self.assertEqual(safe_run.default_timeout(["lc", "show", "X-1"]), 60)

    def test_hanging_grandchild_is_killed(self):
        self.patch_env("FAKE_HANG_PIDFILE", self.pidfile)
        self.run_failing([sys.executable, FAKE], timeout=2)
        with open(self.pidfile) as handle:
            pid = int(handle.read())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        self.fail("grandchild %d is still alive" % pid)

    def test_network_git_gains_low_speed_flags(self):
        built = safe_run.build_command(["git", "fetch", "origin"], True)
        self.assertEqual(built[:5], ["git", "-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=30"])
        self.assertEqual(built[5:], ["fetch", "origin"])
        self.assertEqual(safe_run.build_command(["git", "status"], False), ["git", "status"])

    def test_only_safe_run_imports_subprocess(self):
        offenders = []
        for root, dirs, files in os.walk(SCRIPTS):
            dirs[:] = [d for d in dirs if d not in ("tests", "fixtures")]
            for name in files:
                path = os.path.join(root, name)
                if not name.endswith(".py") or path == os.path.join(SCRIPTS, "lib", "safe_run.py"):
                    continue
                with open(path) as handle:
                    tree = ast.parse(handle.read())
                for node in ast.walk(tree):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        names = [node.module or ""]
                    if any(n.split(".")[0] == "subprocess" for n in names):
                        offenders.append(path)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
