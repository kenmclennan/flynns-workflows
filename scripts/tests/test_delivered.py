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
FAKE_LC = os.path.join(HERE, "fake-lc.py")
LC = "kenmclennan/lightcycle"
PLUGIN = "kenmclennan/lightcycle-plugin"


def item(item_id, number, state="done", disposition="completed", prs=None, repo=LC,
         workflow="lightcycle/spec-driven@abc", title="Fix it"):
    runs = [{"phase": "code", "state": "merged", "pr": p} for p in prs or []]
    return {
        "id": item_id, "title": title, "state": state, "disposition": disposition,
        "workflow": workflow, "runs": runs, "project": "lightcycle",
        "description": "Fixes https://github.com/%s/issues/%d please" % (repo, number),
    }


class DeliveredTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.items = os.path.join(self.dir, "items")
        self.gh = os.path.join(self.dir, "gh")
        self.log = os.path.join(self.dir, "gh.log")
        os.makedirs(self.items)
        os.makedirs(self.gh)
        self.run_script("delivered-install.py")

    def run_script(self, script, stdin="{}", **env):
        full = dict(os.environ)
        full.update({
            "LC_WORKFLOW_DATA_DIR": self.dir,
            "LC_WORKFLOW_CONFIG_GH_COMMAND": FAKE_GH,
            "LC_WORKFLOW_CONFIG_LC_COMMAND": FAKE_LC,
            "LC_WORKFLOW_CONFIG_REPOS": LC,
            "FAKE_GH_RECORDINGS": self.gh,
            "FAKE_LC_ITEMS": self.items,
            "FAKE_GH_LOG": self.log,
        })
        full.update(env)
        return subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, script)],
            input=stdin, capture_output=True, text=True, cwd=self.dir, env=full,
        )

    def add_item(self, **kwargs):
        record = item(**kwargs)
        with open(os.path.join(self.items, record["id"] + ".json"), "w") as handle:
            json.dump(record, handle)

    def set_issues(self, numbers, repo=LC):
        issues = [{"number": n, "title": "Issue %d" % n,
                   "url": "https://github.com/%s/issues/%d" % (repo, n)} for n in numbers]
        with open(os.path.join(self.gh, repo.replace("/", "__") + ".json"), "w") as handle:
            json.dump(issues, handle)

    def guard(self):
        proc = self.run_script("delivered-issues.py")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def record(self, out):
        proc = self.run_script("record-proposed.py", json.dumps({"schedule_state": out["state"]}))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def close(self, refs):
        approved = json.dumps({"issues": refs})
        return self.run_script("close-issues.py", json.dumps({"item_artifacts": {"approved": approved}}))

    def logged(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as handle:
            return [json.loads(line) for line in handle]

    def test_completed_item_with_merged_pr_is_proposed(self):
        self.set_issues([12])
        self.add_item(item_id="LC-1301", number=12, prs=["https://github.com/%s/pull/1013" % LC])
        out = self.guard()
        self.assertEqual(out["outcome"], "pass")
        proposed, look = out["description"].split("Needs a look")
        self.assertIn("Proposed closes", proposed)
        self.assertIn("lightcycle#12", proposed)
        self.assertIn("LC-1301 (done, completed) PR #1013", proposed)
        self.assertNotIn("lightcycle#12", look)
        self.assertTrue(out["title"].startswith("Propose closing 1 delivered"))

    def test_abandoned_item_needs_a_look(self):
        self.set_issues([12])
        self.add_item(item_id="LC-1302", number=12, disposition="abandoned")
        out = self.guard()
        proposed, look = out["description"].split("Needs a look")
        self.assertNotIn("lightcycle#12", proposed)
        self.assertIn("lightcycle#12", look)
        self.assertIn("LC-1302 abandoned", look)

    def test_done_without_merged_pr_and_open_items_need_a_look(self):
        self.set_issues([12, 13])
        self.add_item(item_id="LC-1303", number=12)
        self.add_item(item_id="LC-1304", number=13, state="running", disposition=None)
        look = self.guard()["description"].split("Needs a look")[1]
        self.assertIn("LC-1303 done, no merged PR", look)
        self.assertIn("LC-1304 still open", look)

    def test_one_unfinished_item_keeps_issue_out_of_proposed(self):
        self.set_issues([12])
        self.add_item(item_id="LC-1301", number=12, prs=["https://github.com/%s/pull/1" % LC])
        self.add_item(item_id="LC-1305", number=12, state="running", disposition=None)
        proposed, look = self.guard()["description"].split("Needs a look")
        self.assertNotIn("lightcycle#12", proposed)
        self.assertIn("lightcycle#12", look)

    def test_issue_with_no_item_is_absent_and_nothing_files(self):
        self.set_issues([12])
        out = self.guard()
        self.assertEqual(out, {"outcome": "fail", "note": "nothing new to propose"})

    def test_triage_items_are_not_references(self):
        self.set_issues([12])
        self.add_item(item_id="GHI-1", number=12, workflow="flynns-workflows/triage-github-issues@abc")
        self.assertEqual(self.guard()["outcome"], "fail")

    def test_number_prefix_is_not_a_match(self):
        self.set_issues([76])
        self.add_item(item_id="LC-1306", number=766, prs=["https://github.com/%s/pull/9" % LC])
        self.assertEqual(self.guard()["outcome"], "fail")

    def test_gh_failure_exits_nonzero(self):
        proc = self.run_script("delivered-issues.py", FAKE_GH_FAIL="1")
        self.assertNotEqual(proc.returncode, 0)

    def test_declined_issue_not_proposed_again_until_items_change(self):
        self.set_issues([12])
        self.add_item(item_id="LC-1301", number=12, prs=["https://github.com/%s/pull/1013" % LC])
        self.record(self.guard())
        self.assertEqual(self.guard()["outcome"], "fail")
        self.add_item(item_id="LC-1307", number=12, state="running", disposition=None)
        again = self.guard()
        self.assertEqual(again["outcome"], "pass")
        self.assertIn("LC-1307 still open", again["description"])

    def test_close_closes_only_approved_with_comment_form(self):
        self.set_issues([12, 13])
        self.add_item(item_id="LC-1301", number=12, title="Show parked steps",
                      prs=["https://github.com/%s/pull/1013" % LC])
        self.add_item(item_id="LC-1308", number=13, prs=["https://github.com/%s/pull/1014" % LC])
        proc = self.close([LC + "#12"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["outcome"], "closed")
        self.assertIn("kenmclennan/lightcycle#12 (LC-1301)", out["note"])
        self.assertEqual(self.logged(), [
            {"ref": LC + "#12", "comment": "Fixed by #1013 (LC-1301): Show parked steps."}
        ])

    def test_comment_names_other_repo_pr(self):
        self.add_item(item_id="LC-1301", number=12, title="T",
                      prs=["https://github.com/%s/pull/7" % PLUGIN])
        self.assertEqual(self.close([LC + "#12"]).returncode, 0)
        self.assertEqual(self.logged()[0]["comment"], "Fixed by %s#7 (LC-1301): T." % PLUGIN)

    def test_close_skips_already_closed_issue(self):
        self.add_item(item_id="LC-1301", number=12, prs=["https://github.com/%s/pull/1" % LC])
        with open(os.path.join(self.gh, "closed.json"), "w") as handle:
            json.dump([LC + "#12"], handle)
        proc = self.close([LC + "#12"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("already closed", json.loads(proc.stdout)["note"])
        self.assertEqual(self.logged(), [])

    def test_close_skips_issue_no_longer_proposed(self):
        self.add_item(item_id="LC-1301", number=12, state="running", disposition=None)
        proc = self.close([LC + "#12"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("no longer a proposed close", json.loads(proc.stdout)["note"])
        self.assertEqual(self.logged(), [])

    def test_missing_approved_artifact_exits_nonzero(self):
        self.assertNotEqual(self.run_script("close-issues.py").returncode, 0)

    def test_install_idempotent_and_upgrade(self):
        self.assertEqual(self.run_script("delivered-install.py").returncode, 0)
        self.assertEqual(self.run_script("delivered-upgrade.py").returncode, 0)
        conn = sqlite3.connect(os.path.join(self.dir, "delivered.db"))
        self.assertEqual(conn.execute("PRAGMA user_version").fetchall(), [(1,)])
        conn.close()
        fresh = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, fresh)
        self.assertEqual(self.run_script("delivered-upgrade.py", LC_WORKFLOW_DATA_DIR=fresh).returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(fresh, "delivered.db")))

    def test_record_proposed_idempotent_and_null_state_fails(self):
        state = json.dumps({"shown": [{"repo": LC, "number": 1, "fingerprint": "x"}]})
        for _ in range(2):
            proc = self.run_script("record-proposed.py", json.dumps({"schedule_state": state}))
            self.assertEqual(json.loads(proc.stdout), {"outcome": "recorded"})
        conn = sqlite3.connect(os.path.join(self.dir, "delivered.db"))
        self.assertEqual(conn.execute("SELECT count(*) FROM shown").fetchall(), [(1,)])
        conn.close()
        self.assertNotEqual(
            self.run_script("record-proposed.py", json.dumps({"schedule_state": None})).returncode, 0)

    def test_fixture_state_is_accepted(self):
        with open(os.path.join(SCRIPTS, "fixtures", "delivered-issues.py.json")) as handle:
            state = json.load(handle)["pass"]["state"]
        proc = self.run_script("record-proposed.py", json.dumps({"schedule_state": state}))
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
