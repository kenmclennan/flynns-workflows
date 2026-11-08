import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
ROOT = os.path.dirname(SCRIPTS)
sys.path.insert(0, os.path.join(SCRIPTS, "lib"))

import workflow_config
from stage_env import declared, examples, step_keys, variable, workflow_env, with_environment

WORKFLOWS = (
    "blueprint-delivery",
    "close-delivered-issues",
    "kb-audit",
    "kb-ingest",
    "kb-scout",
    "plugin-drift-review",
    "triage-github-issues",
)
OPTIONAL = {
    "kb-scout": {"fetch-command"},
    "triage-github-issues": {"labels", "ignore-authors"},
}
STAGE_KEYS = {
    "close-issues": ("close-delivered-issues", ["gh-command", "lc-command"]),
    "rank": ("kb-scout", ["threshold", "kb-repo"]),
    "harvest": ("kb-scout", ["batch-cap", "fetch-command", "checkout-path", "qmd-command"]),
    "measure": ("kb-audit", ["knowledgebase-url", "min-cross-topic-links"]),
    "check-references": ("plugin-drift-review", ["skills-path"]),
}
NO_CONFIG_STAGES = ("record-decisions", "record-raised", "record-audited", "record-proposed", "check")


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(os.environ.pop, "LC_WORKFLOW_CONFIG_SOME_KEY", None)

    def test_config_takes_a_key_and_nothing_else(self):
        self.assertEqual(list(inspect.signature(workflow_config.config).parameters), ["key"])

    def test_config_is_none_when_unset_or_blank(self):
        self.assertIsNone(workflow_config.config("some-key"))
        os.environ["LC_WORKFLOW_CONFIG_SOME_KEY"] = "   "
        self.assertIsNone(workflow_config.config("some-key"))

    def test_config_list_is_empty_when_unset_and_splits_when_set(self):
        self.assertEqual(workflow_config.config_list("some-key"), [])
        os.environ["LC_WORKFLOW_CONFIG_SOME_KEY"] = "a, b,,c"
        self.assertEqual(workflow_config.config_list("some-key"), ["a", "b", "c"])

    def test_require_config_exits_naming_an_unset_key(self):
        err = self.fail_with(lambda: workflow_config.require_config("some-key"))
        self.assertIn("some-key", err)

    def test_require_config_list_exits_naming_an_unset_key(self):
        err = self.fail_with(lambda: workflow_config.require_config_list("some-key"))
        self.assertIn("some-key", err)

    def test_require_config_exits_naming_a_key_that_fails_its_cast(self):
        os.environ["LC_WORKFLOW_CONFIG_SOME_KEY"] = "many"
        err = self.fail_with(lambda: workflow_config.require_config("some-key", int))
        self.assertIn("some-key", err)
        self.assertIn("many", err)

    def test_require_config_casts_a_set_key(self):
        os.environ["LC_WORKFLOW_CONFIG_SOME_KEY"] = "14"
        self.assertEqual(workflow_config.require_config("some-key", int), 14)

    def fail_with(self, call):
        import io
        captured = io.StringIO()
        original = sys.stderr
        sys.stderr = captured
        try:
            with self.assertRaises(SystemExit) as raised:
                call()
        finally:
            sys.stderr = original
        self.assertEqual(raised.exception.code, 1)
        return captured.getvalue()


class ScriptSiteTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def run_site(self, script, workflow, unset=None, stdin="{}", **overrides):
        env = with_environment(os.environ, workflow_env(workflow, **overrides))
        env["LC_WORKFLOW_DATA_DIR"] = self.dir
        if unset:
            env.pop(variable(unset), None)
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, script)],
            input=stdin, capture_output=True, text=True, cwd=self.dir, env=env,
        )

    def assert_names_key(self, script, workflow, key, stdin="{}", **overrides):
        failed = self.run_site(script, workflow, unset=key, stdin=stdin, **overrides)
        self.assertNotEqual(failed.returncode, 0, "%s ran with %s unset" % (script, key))
        self.assertIn("config key %s is required" % key, failed.stderr)
        set_ = self.run_site(script, workflow, stdin=stdin, **overrides)
        self.assertNotIn("config key %s is required" % key, set_.stderr)

    def test_delivered_issues_guard(self):
        for key in ("repos", "gh-command", "lc-command"):
            self.assert_names_key("delivered-issues.py", "close-delivered-issues", key)

    def test_close_issues_stage(self):
        stdin = json.dumps({"item_artifacts": {"approved": json.dumps({"issues": []})}})
        for key in ("gh-command", "lc-command"):
            self.assert_names_key("close-issues.py", "close-delivered-issues", key, stdin=stdin)

    def test_new_issues_guard(self):
        for key in ("repos", "gh-command", "lookback-days"):
            self.assert_names_key("new-issues.py", "triage-github-issues", key)

    def test_new_issues_guard_names_a_non_integer_lookback(self):
        proc = self.run_site("new-issues.py", "triage-github-issues", **{"lookback-days": "soon"})
        self.assertEqual(proc.returncode, 1)
        self.assertIn("lookback-days", proc.stderr)

    def test_new_issues_guard_runs_with_the_optional_keys_unset(self):
        proc = self.run_site("new-issues.py", "triage-github-issues", unset="labels")
        self.assertNotIn("labels", proc.stderr)
        self.assertNotIn("ignore-authors", proc.stderr)
        self.assertEqual(workflow_config.config_list("labels"), [])
        self.assertEqual(workflow_config.config_list("ignore-authors"), [])

    def test_kb_install_passes_with_qmd_command_unset(self):
        proc = self.run_site("kb-install.py", "kb-ingest", unset="qmd-command")
        self.assertNotIn("is required", proc.stderr)

    def test_kb_maintain(self):
        self.assert_names_key("kb-maintain.py", "kb-ingest", "qmd-command")

    def test_scout_install_passes_with_qmd_command_unset(self):
        proc = self.run_site("scout-install.py", "kb-scout", unset="qmd-command")
        self.assertNotIn("is required", proc.stderr)

    def test_harvest_stage(self):
        stdin = json.dumps({"schedule_state": json.dumps({"entries": [], "marks": {}})})
        for key in ("checkout-path", "qmd-command"):
            self.assert_names_key("harvest.py", "kb-scout", key, stdin=stdin)

    def test_harvest_with_fetch_command_unset_reads_it_as_none(self):
        self.assertIsNone(workflow_config.config("fetch-command"))

    def test_drift_install_skips_the_clone_for_an_unset_url(self):
        for key in ("engine-url", "workflows-url", "plugin-url"):
            proc = self.run_site("drift-install.py", "plugin-drift-review", unset=key)
            self.assertNotIn("is required", proc.stderr)
            self.assertIn("%s is not set" % key, proc.stderr)

    def test_check_references_stage(self):
        sha = "a" * 40
        stdin = json.dumps({"schedule_state": {"to": {"engine": sha, "workflows": sha, "plugin": sha}}})
        self.assert_names_key("check-references.py", "plugin-drift-review", "skills-path", stdin=stdin)


class CommittedContentTests(unittest.TestCase):
    def test_every_required_key_has_a_config_example(self):
        checked = 0
        for name in WORKFLOWS:
            block = declared(name)
            example = examples(name)
            for key, kind in block.items():
                if kind == "required":
                    self.assertIn(key, example, "%s requires %s but gives no config-example" % (name, key))
            checked += 1
        self.assertEqual(checked, len(WORKFLOWS))

    def test_only_the_named_keys_stay_optional(self):
        for name in WORKFLOWS:
            optional = {key for key, kind in declared(name).items() if kind == "optional"}
            self.assertEqual(optional, OPTIONAL.get(name, set()), name)

    def test_each_stage_lists_exactly_its_keys_and_declares_them(self):
        for step, (workflow, keys) in STAGE_KEYS.items():
            self.assertEqual(step_keys(step), keys, step)
            for key in keys:
                self.assertIn(key, declared(workflow), "%s lists %s, which %s does not declare" % (step, key, workflow))

    def test_stages_that_read_no_config_list_none(self):
        for step in NO_CONFIG_STAGES:
            self.assertEqual(step_keys(step), [], step)


if __name__ == "__main__":
    unittest.main()
