import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
)


def sh(*cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, env=GIT_ENV, check=True, capture_output=True)


def make_repo(path, files):
    os.makedirs(path)
    sh("git", "init", "-q", "-b", "main", cwd=path)
    commit(path, files)


def commit(path, files, msg="change"):
    for rel, text in files.items():
        full = os.path.join(path, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as handle:
            handle.write(text)
    sh("git", "add", "-A", cwd=path)
    sh("git", "commit", "-q", "-m", msg, cwd=path)


ENGINE = {"lightcycle/cli.py": "COMMANDS = ['show', 'done', 'attach']\nFLAGS = ['--replace', '--note']\n"}
WORKFLOWS = {"workflows/spec-driven.md": "entry: spec-writer\n", "steps/spec-writer.md": "# Spec-writer\n"}
SKILL_OK = "Run `lc show X` then `lc attach X foo bar --replace`.\n"
SKILL_BAD = SKILL_OK + "Then `lc frobnicate X`.\n"
SKILL_PATH = "plugins/lightcycle/skills/driver/SKILL.md"


class DriftTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.data = os.path.join(self.root, "data")
        os.makedirs(self.data)
        self.paths = {n: os.path.join(self.root, "src-" + n) for n in ("engine", "workflows", "plugin")}
        make_repo(self.paths["engine"], ENGINE)
        make_repo(self.paths["workflows"], WORKFLOWS)
        make_repo(self.paths["plugin"], {SKILL_PATH: SKILL_OK})

    def run_script(self, script, stdin="{}", urls=None):
        env = dict(os.environ, LC_WORKFLOW_DATA_DIR=self.data)
        for name, path in (urls or self.paths).items():
            env["LC_WORKFLOW_CONFIG_%s_URL" % name.upper()] = path
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, script)],
            input=stdin, capture_output=True, text=True, cwd=self.data, env=env,
        )

    def guard(self, last_state):
        proc = self.run_script("moved.py", json.dumps({"last_state": last_state}))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def check(self, state):
        proc = self.run_script("check-references.py", json.dumps({"schedule_state": state}))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_first_run_passes_with_all_three_moved(self):
        out = self.guard(None)
        self.assertEqual(out["outcome"], "pass")
        self.assertEqual(out["title"], "Review plugin skills: engine and workflows and plugin moved")
        state = json.loads(out["state"])
        self.assertEqual(state["from"], {"engine": None, "workflows": None, "plugin": None})

    def test_second_run_with_nothing_moved_fails(self):
        out = self.guard(None)
        again = self.guard(out["state"])
        self.assertEqual(again["outcome"], "fail")

    def test_one_moved_repo_passes_naming_it(self):
        out = self.guard(None)
        commit(self.paths["plugin"], {SKILL_PATH: SKILL_BAD})
        again = self.guard(out["state"])
        self.assertEqual(again["outcome"], "pass")
        self.assertEqual(again["title"], "Review plugin skills: plugin moved")
        self.assertIn("1 commit(s)", again["description"])

    def test_check_references_reports_planted_miss(self):
        commit(self.paths["plugin"], {SKILL_PATH: SKILL_BAD})
        out = self.check(self.guard(None)["state"])
        self.assertEqual(out["outcome"], "misses")
        self.assertIn("frobnicate", out["artifacts"]["missing-references"])
        self.assertIn(":2:", out["artifacts"]["missing-references"])

    def test_check_references_clean_when_all_resolve(self):
        out = self.check(self.guard(None)["state"])
        self.assertEqual(out["outcome"], "clean")
        self.assertEqual(out["artifacts"]["missing-references"], "none")

    def test_review_context_names_existing_snapshots(self):
        out = self.check(self.guard(None)["state"])
        context = out["artifacts"]["review-context"]
        for name in ("engine", "workflows", "plugin"):
            line = [l for l in context.splitlines() if l.startswith(name + ": snapshot ")][0]
            self.assertTrue(os.path.isdir(line.split("snapshot ", 1)[1]))
        self.assertIn("first review", context)

    def test_review_context_has_diff_commands_after_a_move(self):
        first = self.guard(None)
        commit(self.paths["plugin"], {SKILL_PATH: SKILL_BAD})
        out = self.check(self.guard(first["state"])["state"])
        self.assertIn("diff --stat", out["artifacts"]["review-context"])

    def test_install_with_unreachable_url_warns_and_exits_zero(self):
        urls = {n: os.path.join(self.root, "no-such-" + n) for n in self.paths}
        proc = self.run_script("drift-install.py", urls=urls)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("warning", proc.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.data, "layout-version")))

    def test_upgrade_creates_missing_layout_and_is_idempotent(self):
        for _ in range(2):
            self.assertEqual(self.run_script("drift-upgrade.py").returncode, 0)
        self.assertTrue(os.path.isdir(os.path.join(self.data, "snapshots")))

    def test_maintain_prunes_old_snapshots(self):
        shas = []
        for i in range(4):
            commit(self.paths["plugin"], {SKILL_PATH: SKILL_OK + "v%d\n" % i})
            out = self.guard(None)
            self.check(out["state"])
            shas.append(json.loads(out["state"])["to"]["plugin"])
            os.utime(os.path.join(self.data, "snapshots", "plugin-" + shas[-1]), (i + 1, i + 1))
        proc = self.run_script("drift-maintain.py")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        left = [d for d in os.listdir(os.path.join(self.data, "snapshots")) if d.startswith("plugin-")]
        self.assertEqual(sorted(left), sorted("plugin-" + s for s in shas[-2:]))

    def test_maintain_tolerates_an_unreachable_remote(self):
        urls = {name: os.path.join(self.data, "no-such-repo") for name in self.paths}
        proc = self.run_script("drift-maintain.py", urls=urls)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("could not refresh", proc.stderr)


if __name__ == "__main__":
    unittest.main()
