import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "kb-fixtures")
HAS_NPX = shutil.which("npx") is not None


def git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def overlay(name, dest):
    src = os.path.join(FIXTURES, name)
    for root, _, files in os.walk(src):
        for item in files:
            target = os.path.join(dest, os.path.relpath(os.path.join(root, item), src))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy(os.path.join(root, item), target)


class KbCheckTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        git(self.dir, "init", "-b", "main")
        overlay("base", self.dir)
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-m", "base")
        git(self.dir, "checkout", "-b", "ingest/test")

    def check(self, fixture, tools=False):
        overlay(fixture, self.dir)
        env = dict(os.environ, KB_CHECK_BASE="main")
        if not tools:
            env["KB_CHECK_SKIP_TOOLS"] = "1"
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "kb-check.py")],
            input="{}", capture_output=True, text=True, cwd=self.dir, env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def report(self, out):
        self.assertEqual(out["outcome"], "broken")
        return out["artifacts"]["check-report"]

    def test_clean_fixture_passes(self):
        out = self.check("clean")
        self.assertEqual(out["outcome"], "clean")
        self.assertNotIn("artifacts", out)

    def test_unresolved_relative_link_fails(self):
        report = self.report(self.check("unresolved-link"))
        self.assertIn("topic/new.md: relative link ../nowhere/missing.md does not resolve", report)

    def test_doc_unreachable_from_any_index_fails(self):
        report = self.report(self.check("unreachable-doc"))
        self.assertIn("topic/new.md: not reachable from index.md", report)

    def test_citation_without_body_link_fails(self):
        report = self.report(self.check("citation-without-link"))
        self.assertIn("cites references/old.md in `sources` but does not link it", report)

    def test_missing_frontmatter_fails(self):
        report = self.report(self.check("missing-frontmatter"))
        self.assertIn("topic/new.md: frontmatter is missing or has no `type`", report)

    def test_committed_change_is_checked_like_an_uncommitted_one(self):
        overlay("unresolved-link", self.dir)
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-m", "ingest")
        env = dict(os.environ, KB_CHECK_BASE="main", KB_CHECK_SKIP_TOOLS="1")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "kb-check.py")],
            input="{}", capture_output=True, text=True, cwd=self.dir, env=env,
        )
        self.assertEqual(json.loads(proc.stdout)["outcome"], "broken")

    def test_unchanged_branch_is_clean(self):
        env = dict(os.environ, KB_CHECK_BASE="main")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "kb-check.py")],
            input="{}", capture_output=True, text=True, cwd=self.dir, env=env,
        )
        self.assertEqual(json.loads(proc.stdout)["outcome"], "clean")

    @unittest.skipUnless(HAS_NPX, "npx is not installed")
    def test_unformatted_file_fails_prettier(self):
        report = self.report(self.check("unformatted", tools=True))
        self.assertIn("prettier:", report)
        self.assertIn("topic/new.md", report)

    @unittest.skipUnless(HAS_NPX, "npx is not installed")
    def test_clean_fixture_passes_formatters_too(self):
        self.assertEqual(self.check("clean", tools=True)["outcome"], "clean")


if __name__ == "__main__":
    unittest.main()
