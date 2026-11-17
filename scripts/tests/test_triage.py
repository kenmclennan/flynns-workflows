import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from stage_env import stage_env, with_environment, workflow_env

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
FAKE_GH = os.path.join(HERE, "fake-gh.py")
REPOS = "kenmclennan/lightcycle,kenmclennan/lightcycle-plugin"


def run(script, data_dir, stdin="{}", **config):
    if script == "record-raised.py":
        configured = stage_env("record-raised", "triage-github-issues", **config)
    else:
        configured = workflow_env("triage-github-issues", **dict({"gh-command": FAKE_GH, "repos": REPOS}, **config))
    env = with_environment(os.environ, configured)
    env["LC_WORKFLOW_DATA_DIR"] = data_dir
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
        self.assertNotIn("New comments", out["description"])

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
        self.assertEqual(self.rows("PRAGMA user_version"), [(2,)])

    def test_upgrade_noop_at_current_and_creates_missing(self):
        self.assertEqual(run("upgrade.py", self.dir).returncode, 0)
        self.assertEqual(self.rows("PRAGMA user_version"), [(2,)])
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
        self.assertEqual(self.rows("SELECT count(*) FROM raised"), [(2,)])
        self.assertEqual(self.rows("SELECT count(*) FROM comment_marks"), [(0,)])

    REPO = "kenmclennan/lightcycle"

    def seed_raised(self, number, raised_at="2026-10-15T00:00:00Z"):
        conn = sqlite3.connect(os.path.join(self.dir, "triage.db"))
        with conn:
            conn.execute("INSERT INTO raised VALUES (?, ?, ?)", (self.REPO, number, raised_at))
        conn.close()

    def issue(self, number, comments=None, updated="2026-10-16T10:00:00Z", author="a"):
        issue = {
            "number": number, "title": "T%d" % number, "author": {"login": author},
            "url": "https://github.com/%s/issues/%d" % (self.REPO, number),
            "body": "b", "labels": [], "updatedAt": updated,
        }
        if comments is not None:
            issue["comments"] = comments
        return issue

    def comment(self, login, at, body="hello there"):
        return {"author": {"login": login}, "body": body, "createdAt": at}

    def record_issues(self, issues):
        rec = os.path.join(self.dir, "rec")
        os.makedirs(rec, exist_ok=True)
        with open(os.path.join(rec, "kenmclennan__lightcycle.json"), "w") as handle:
            json.dump(issues, handle)
        os.environ["FAKE_GH_RECORDINGS"] = rec
        self.addCleanup(os.environ.pop, "FAKE_GH_RECORDINGS", None)

    def commented_guard(self, issues, **config):
        self.record_issues(issues)
        return self.guard(repos=self.REPO, **config)

    def test_new_comment_on_raised_issue_surfaces(self):
        self.seed_raised(101)
        out = self.commented_guard([self.issue(101, [self.comment("alice", "2026-10-16T09:00:00Z")])])
        self.assertEqual(out["outcome"], "pass")
        self.assertEqual(out["title"], "Triage 0 new GitHub issue(s), 1 with new comments")
        self.assertIn("New comments", out["description"])
        self.assertIn("@alice 2026-10-16T09:00:00Z - hello there", out["description"])

    def test_comment_surfaces_once(self):
        self.seed_raised(101)
        issues = [self.issue(101, [self.comment("alice", "2026-10-16T09:00:00Z")])]
        out = self.commented_guard(issues)
        self.assertEqual(out["outcome"], "pass")
        self.record(out)
        self.assertEqual(self.rows("SELECT high_water FROM comment_marks"), [("2026-10-16T09:00:00Z",)])
        self.assertEqual(self.guard(repos=self.REPO)["outcome"], "fail")

    def test_comment_before_raised_at_is_not_surfaced(self):
        self.seed_raised(101)
        out = self.commented_guard([self.issue(101, [self.comment("alice", "2026-10-14T09:00:00Z")])])
        self.assertEqual(out["outcome"], "fail")

    def test_ignored_and_lc_comments_are_dropped(self):
        self.seed_raised(101)
        noise = [
            self.comment("Bot", "2026-10-16T09:00:00Z"),
            self.comment("alice", "2026-10-16T09:30:00Z", "  <!-- lc -->\nfinding"),
        ]
        cfg = {"ignore-authors": "bot"}
        self.assertEqual(self.commented_guard([self.issue(101, noise)], **cfg)["outcome"], "fail")
        human = noise + [self.comment("carol", "2026-10-16T10:00:00Z", "real point")]
        out = self.commented_guard([self.issue(101, human)], **cfg)
        self.assertEqual(out["outcome"], "pass")
        self.assertIn("@carol", out["description"])
        self.assertNotIn("@Bot", out["description"])
        self.assertNotIn("finding", out["description"])

    def test_capped_comment_listing_fetches_newest_via_graphql(self):
        self.seed_raised(101)
        oldest = [self.comment("alice", "2026-10-15T%02d:%02d:00Z" % (i // 60, i % 60)) for i in range(100)]
        newest = oldest[1:] + [self.comment("carol", "2026-10-16T09:00:00Z", "past the cap")]
        self.record_issues([self.issue(101, oldest)])
        rec = os.environ["FAKE_GH_RECORDINGS"]
        graphql = {"data": {"repository": {"issue": {"comments": {"nodes": newest}}}}}
        with open(os.path.join(rec, "kenmclennan__lightcycle__101.graphql.json"), "w") as handle:
            json.dump(graphql, handle)
        out = self.guard(repos=self.REPO)
        self.assertEqual(out["outcome"], "pass")
        self.assertIn("@carol 2026-10-16T09:00:00Z - past the cap", out["description"])

    def test_listing_under_the_cap_does_not_call_graphql(self):
        self.seed_raised(101)
        out = self.commented_guard([self.issue(101, [self.comment("alice", "2026-10-16T09:00:00Z")])])
        self.assertEqual(out["outcome"], "pass")

    def test_update_without_comment_is_not_surfaced(self):
        self.seed_raised(101)
        out = self.commented_guard([self.issue(101, [], updated="2026-10-17T00:00:00Z")])
        self.assertEqual(out["outcome"], "fail")

    def test_mixed_new_issue_and_commented_issue(self):
        self.seed_raised(101)
        self.seed_raised(102)
        out = self.commented_guard([
            self.issue(100),
            self.issue(101, [self.comment("alice", "2026-10-16T09:00:00Z")]),
            self.issue(102, []),
        ])
        self.assertEqual(out["title"], "Triage 1 new GitHub issue(s) on 1 repo(s), 1 with new comments")
        self.assertIn("#100", out["description"])
        self.assertIn("#101", out["description"])
        self.assertNotIn("#102", out["description"])

    def logged_since(self, seed_mark):
        log = os.path.join(self.dir, "args.log")
        wrapper = os.path.join(self.dir, "gh-wrap.sh")
        with open(wrapper, "w") as handle:
            handle.write('#!/bin/sh\necho "$@" >> "%s"\nexec "%s" "$@"\n' % (log, FAKE_GH))
        os.chmod(wrapper, 0o755)
        conn = sqlite3.connect(os.path.join(self.dir, "triage.db"))
        with conn:
            conn.execute("INSERT INTO marks VALUES (?, ?)", (self.REPO, seed_mark))
        conn.close()
        self.guard(**{"gh-command": wrapper, "lookback-days": "30", "repos": self.REPO})
        with open(log) as handle:
            return handle.read().split("updated:>=")[1].split()[0]

    def test_comment_older_than_repo_mark_is_still_fetched(self):
        mark = "2999-01-01T00:00:00Z"
        since = self.logged_since(mark)
        self.assertLess(since, mark)
        self.assertGreater(since, "2020-01-01T00:00:00Z")

    def test_mark_older_than_window_is_used(self):
        mark = "2020-01-01T00:00:00Z"
        self.assertEqual(self.logged_since(mark), mark)

    def test_record_raised_stores_comment_mark_keeps_larger_and_skips_unknown(self):
        def state(mark):
            return {
                "issues": [{"repo": self.REPO, "number": 1}], "marks": {},
                "comments": [
                    {"repo": self.REPO, "number": 1, "mark": mark},
                    {"repo": self.REPO, "number": 2, "mark": mark},
                ],
            }
        for mark in ("2026-10-16T00:00:00Z", "2026-10-01T00:00:00Z"):
            proc = run("record-raised.py", self.dir, json.dumps({"schedule_state": json.dumps(state(mark))}))
            self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.rows("SELECT repo, number, high_water FROM comment_marks"),
                         [(self.REPO, 1, "2026-10-16T00:00:00Z")])
        old = {"issues": [{"repo": self.REPO, "number": 1}], "marks": {}}
        proc = run("record-raised.py", self.dir, json.dumps({"schedule_state": json.dumps(old)}))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_migrate_takes_a_version_one_database_to_two_keeping_every_row(self):
        fresh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, fresh)
        conn = sqlite3.connect(os.path.join(fresh, "triage.db"))
        with conn:
            conn.execute("CREATE TABLE raised (repo TEXT NOT NULL, number INTEGER NOT NULL, raised_at TEXT NOT NULL, PRIMARY KEY (repo, number))")
            conn.execute("CREATE TABLE marks (repo TEXT PRIMARY KEY, high_water TEXT NOT NULL)")
            conn.execute("INSERT INTO raised VALUES ('r', 1, 'x')")
            conn.execute("INSERT INTO marks VALUES ('r', 'y')")
            conn.execute("PRAGMA user_version = 1")
        conn.close()
        self.assertEqual(run("upgrade.py", fresh).returncode, 0)
        conn = sqlite3.connect(os.path.join(fresh, "triage.db"))
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT repo, number, raised_at FROM raised").fetchall(), [("r", 1, "x")])
            self.assertEqual(conn.execute("SELECT repo, high_water FROM marks").fetchall(), [("r", "y")])
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
            self.assertIn("sqlite_autoindex_comment_marks_1", names)
            self.assertEqual(conn.execute("PRAGMA foreign_key_list(comment_marks)").fetchall(), [])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
