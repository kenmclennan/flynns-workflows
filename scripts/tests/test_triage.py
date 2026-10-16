import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
FAKE_GH = os.path.join(HERE, "fake-gh.py")
REPOS = "kenmclennan/lightcycle,kenmclennan/lightcycle-plugin"


def run(script, data_dir, stdin="{}", **config):
    env = dict(os.environ)
    env["LC_WORKFLOW_DATA_DIR"] = data_dir
    env["LC_WORKFLOW_CONFIG_GH_COMMAND"] = FAKE_GH
    env["LC_WORKFLOW_CONFIG_REPOS"] = REPOS
    for key, value in config.items():
        env["LC_WORKFLOW_CONFIG_" + key.upper().replace("-", "_")] = value
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script)],
        input=stdin, capture_output=True, text=True, cwd=data_dir, env=env,
    )


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.assertEqual(run("install.py", self.dir).returncode, 0)

    def guard(self, **config):
        proc = run("new-issues.py", self.dir, **config)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def record(self, out):
        proc = run("record-raised.py", self.dir, json.dumps({"schedule_state": out["state"]}))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def rows(self, sql):
        conn = sqlite3.connect(os.path.join(self.dir, "triage.db"))
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_two_new_issues_pass_listing_both(self):
        out = self.guard(**{"ignore-authors": "dependabot"})
        self.assertEqual(out["outcome"], "pass")
        self.assertIn("lightcycle#101", out["description"])
        self.assertIn("lightcycle-plugin#7", out["description"])
        self.assertNotIn("#102", out["description"])
        self.assertIn("Parked steps do not show in lc inbox.", out["description"])
        self.assertTrue(out["title"].startswith("Triage 2 new"))

    def test_same_recording_after_record_raised_fails(self):
        cfg = {"ignore-authors": "dependabot"}
        out = self.guard(**cfg)
        self.record(out)
        again = self.guard(**cfg)
        self.assertEqual(again["outcome"], "fail")

    def test_summary_defaults_when_body_empty(self):
        out = self.guard()
        self.assertIn("@dependabot - (no description)", out["description"])

    def recorded(self, body):
        rec = os.path.join(self.dir, "rec")
        os.makedirs(rec)
        issue = {
            "number": 1, "title": "T", "author": {"login": "a"}, "url": "u",
            "body": body, "labels": [], "updatedAt": "2026-10-15T10:00:00Z",
        }
        with open(os.path.join(rec, "kenmclennan__lightcycle.json"), "w") as handle:
            json.dump([issue], handle)
        os.environ["FAKE_GH_RECORDINGS"] = rec
        self.addCleanup(os.environ.pop, "FAKE_GH_RECORDINGS", None)
        return self.guard(repos="kenmclennan/lightcycle")["description"]

    def test_summary_skips_leading_heading(self):
        self.assertTrue(self.recorded("## What happens\n\nThe gate...").endswith(" - The gate..."))

    def test_summary_defaults_when_body_is_only_headings(self):
        self.assertTrue(self.recorded("## Problem\n\n### What happens\n---\n<!-- x -->").endswith("(no description)"))

    def test_summary_strips_markup_and_trims(self):
        text = self.recorded("<!-- hi -->\n**Bold** and [a link](http://x) in `my_var` " + "z" * 200)
        self.assertIn(" - Bold and a link in my_var zzz", text)
        self.assertEqual(len(text.rsplit(" - ", 1)[1]), 120)

    def test_label_filter_keeps_only_matching(self):
        out = self.guard(labels="bug")
        self.assertIn("#101", out["description"])
        self.assertNotIn("#102", out["description"])
        self.assertNotIn("plugin#7", out["description"])

    def test_already_raised_is_dropped(self):
        conn = sqlite3.connect(os.path.join(self.dir, "triage.db"))
        with conn:
            conn.execute("INSERT INTO raised VALUES ('kenmclennan/lightcycle', 101, 'x')")
        conn.close()
        out = self.guard(**{"ignore-authors": "dependabot"})
        self.assertNotIn("#101", out["description"])
        self.assertIn("plugin#7", out["description"])

    def test_first_run_uses_lookback_days(self):
        log = os.path.join(self.dir, "args.log")
        wrapper = os.path.join(self.dir, "gh-wrap.sh")
        with open(wrapper, "w") as handle:
            handle.write('#!/bin/sh\necho "$@" >> "%s"\nexec "%s" "$@"\n' % (log, FAKE_GH))
        os.chmod(wrapper, 0o755)
        self.guard(**{"gh-command": wrapper, "lookback-days": "3"})
        with open(log) as handle:
            self.assertIn("updated:>=", handle.read())

    def test_gh_failure_exits_nonzero(self):
        env_key = "FAKE_GH_FAIL"
        os.environ[env_key] = "1"
        self.addCleanup(os.environ.pop, env_key, None)
        proc = run("new-issues.py", self.dir)
        self.assertNotEqual(proc.returncode, 0)

    def test_install_is_idempotent(self):
        self.assertEqual(run("install.py", self.dir).returncode, 0)
        self.assertEqual(self.rows("PRAGMA user_version"), [(1,)])

    def test_upgrade_noop_at_current_and_creates_missing(self):
        self.assertEqual(run("upgrade.py", self.dir).returncode, 0)
        self.assertEqual(self.rows("PRAGMA user_version"), [(1,)])
        fresh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, fresh)
        self.assertEqual(run("upgrade.py", fresh).returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(fresh, "triage.db")))

    def test_record_raised_idempotent_and_keeps_larger_mark(self):
        repo = "kenmclennan/lightcycle"
        newer = {"issues": [{"repo": repo, "number": 1}], "marks": {repo: "2026-10-16T00:00:00Z"}}
        older = {"issues": [{"repo": repo, "number": 1}], "marks": {repo: "2026-10-01T00:00:00Z"}}
        for state in (newer, newer, older):
            proc = run("record-raised.py", self.dir, json.dumps({"schedule_state": json.dumps(state)}))
            self.assertEqual(json.loads(proc.stdout), {"outcome": "recorded"})
        self.assertEqual(self.rows("SELECT count(*) FROM raised"), [(1,)])
        self.assertEqual(self.rows("SELECT high_water FROM marks"), [("2026-10-16T00:00:00Z",)])

    def test_null_schedule_state_exits_nonzero(self):
        proc = run("record-raised.py", self.dir, json.dumps({"schedule_state": None}))
        self.assertNotEqual(proc.returncode, 0)

    def test_fixture_state_is_accepted(self):
        with open(os.path.join(SCRIPTS, "fixtures", "new-issues.py.json")) as handle:
            state = json.load(handle)["pass"]["state"]
        proc = run("record-raised.py", self.dir, json.dumps({"schedule_state": state}))
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
