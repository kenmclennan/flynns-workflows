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

    def changes(self, out):
        return out["artifacts"]["changes-since"]

    def test_first_run_lists_engine_and_workflows_subjects_only(self):
        commit(self.paths["engine"], {"lightcycle/more.py": "X = 1\n"}, msg="feat: engine two")
        commit(self.paths["plugin"], {SKILL_PATH: SKILL_OK + "p\n"}, msg="feat: plugin two")
        text = self.changes(self.check(self.guard(None)["state"]))
        self.assertIn("engine: first review, last 2 commits", text)
        self.assertIn("workflows: first review, last 1 commits", text)
        self.assertIn("feat: engine two", text)
        self.assertNotIn("plugin two", text)

    def test_move_lists_only_commits_between_from_and_to_newest_first(self):
        first = self.guard(None)
        commit(self.paths["engine"], {"lightcycle/a.py": "A = 1\n"}, msg="feat: older")
        commit(self.paths["engine"], {"lightcycle/b.py": "B = 1\n"}, msg="feat: newer")
        text = self.changes(self.check(self.guard(first["state"])["state"]))
        engine = text.split("workflows:")[0]
        self.assertIn(", 2 commits", engine)
        self.assertLess(engine.index("feat: newer"), engine.index("feat: older"))
        self.assertNotIn("change", engine.split("\n", 1)[1])
        self.assertIn("workflows: no changes", text)

    def test_unreachable_from_falls_back_and_says_so(self):
        state = self.guard(None)["state"]
        parsed = json.loads(state)
        parsed["from"]["engine"] = "0" * 40
        text = self.changes(self.check(json.dumps(parsed)))
        self.assertIn("engine: %s unreachable, last 1 commits" % ("0" * 40), text)

    def test_cap_limits_the_first_review_listing(self):
        for i in range(3):
            commit(self.paths["engine"], {"lightcycle/n%d.py" % i: "N = 1\n"}, msg="feat: n%d" % i)
        state = self.guard(None)["state"]
        sys.path.insert(0, os.path.join(SCRIPTS, "lib"))
        import drift
        self.addCleanup(setattr, drift, "CHANGES_CAP", drift.CHANGES_CAP)
        drift.CHANGES_CAP = 2
        os.environ["LC_WORKFLOW_DATA_DIR"] = self.data
        self.addCleanup(os.environ.pop, "LC_WORKFLOW_DATA_DIR")
        os.environ["LC_WORKFLOW_CONFIG_ENGINE_URL"] = self.paths["engine"]
        self.addCleanup(os.environ.pop, "LC_WORKFLOW_CONFIG_ENGINE_URL")
        drift.ensure_clone("engine")
        parsed = drift.parse_state(state)
        text = drift.changes_since({"from": {}, "to": parsed["to"]})
        self.assertIn("engine: first review, last 2 commits", text)
        self.assertIn("feat: n2", text)
        self.assertNotIn("feat: n0", text)

    def test_changes_since_is_present_on_clean_and_misses(self):
        clean = self.check(self.guard(None)["state"])
        self.assertEqual(clean["outcome"], "clean")
        self.assertIn("changes-since", clean["artifacts"])
        commit(self.paths["plugin"], {SKILL_PATH: SKILL_BAD})
        misses = self.check(self.guard(None)["state"])
        self.assertEqual(misses["outcome"], "misses")
        self.assertIn("changes-since", misses["artifacts"])

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

    def test_changed_url_repoints_the_clone_and_fetches_from_it(self):
        out = self.guard(None)
        old_plugin = json.loads(out["state"])["to"]["plugin"]
        moved = os.path.join(self.root, "moved-plugin")
        make_repo(moved, {SKILL_PATH: SKILL_BAD})
        expected = subprocess.run(
            ["git", "rev-parse", "main"], cwd=moved, capture_output=True, text=True
        ).stdout.strip()
        urls = dict(self.paths, plugin=moved)
        proc = self.run_script("moved.py", json.dumps({"last_state": out["state"]}), urls=urls)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        new_plugin = json.loads(json.loads(proc.stdout)["state"])["to"]["plugin"]
        self.assertEqual(new_plugin, expected)
        self.assertNotEqual(new_plugin, old_plugin)

    def test_unfetchable_changed_url_names_both_urls(self):
        self.guard(None)
        bad = os.path.join(self.root, "no-such-plugin")
        proc = self.run_script("drift-maintain.py", urls=dict(self.paths, plugin=bad))
        self.assertIn(bad, proc.stderr)
        self.assertIn(self.paths["plugin"], proc.stderr)


if __name__ == "__main__":
    unittest.main()
