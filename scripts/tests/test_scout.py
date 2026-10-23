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
sys.path.insert(0, os.path.join(SCRIPTS, "lib"))

import scout_fetch
import scout_state

FAKE_FETCH = os.path.join(HERE, "fake-fetch.py")
FOWLER = "https://martinfowler.com/feed.atom"
GUARDRAILS = "https://martinfowler.com/articles/guardrails.html"
READING = "https://martinfowler.com/articles/reading-output.html"
THIRD = "https://example.org/third"
BECK_POST = "https://tidyfirst.substack.com/p/c"
NOW = "2026-10-18T09:00:00Z"


def run(script, data_dir, stdin="{}", cwd=None, **config):
    env = dict(os.environ)
    for key in [k for k in env if k.startswith("LC_WORKFLOW_CONFIG_")]:
        del env[key]
    env["LC_WORKFLOW_DATA_DIR"] = data_dir
    env["LC_WORKFLOW_CONFIG_FETCH_COMMAND"] = FAKE_FETCH
    env["LC_WORKFLOW_CONFIG_THRESHOLD"] = "6"
    env["LC_WORKFLOW_CONFIG_BATCH_CAP"] = "10"
    env["LC_WORKFLOW_CONFIG_KB_REPO"] = "kenmclennan/knowledgebase"
    for key, value in config.items():
        env["LC_WORKFLOW_CONFIG_" + key.upper().replace("-", "_")] = value
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script)],
        input=stdin, capture_output=True, text=True, cwd=cwd or data_dir, env=env,
    )


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.data = os.path.join(self.root, "data")
        os.makedirs(self.data)
        self.kb = os.path.join(self.root, "kb")
        os.makedirs(os.path.join(self.kb, "references"))
        self.assertEqual(run("scout-install.py", self.data).returncode, 0)

    def guard(self, **config):
        proc = run("feeds-moved.py", self.data, **config)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def harvest(self, state):
        proc = run("harvest.py", self.data, json.dumps({"schedule_state": state}), cwd=self.kb)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def rank(self, scores, **config):
        stdin = json.dumps({"item_artifacts": {"scores": json.dumps(scores)}})
        proc = run("rank.py", self.data, stdin, **config)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def record(self, decisions):
        stdin = json.dumps({"item_artifacts": {"decisions": json.dumps(decisions)}})
        return run("record-decisions.py", self.data, stdin)

    def db(self):
        conn = scout_state.sqlite3.connect(os.path.join(self.data, "scout.db"))
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn

    def rows(self, sql):
        return [tuple(r) for r in self.db().execute(sql).fetchall()]


class StateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        os.environ["LC_WORKFLOW_DATA_DIR"] = self.dir
        self.addCleanup(os.environ.pop, "LC_WORKFLOW_DATA_DIR")
        self.conn = scout_state.connect()
        self.addCleanup(self.conn.close)
        scout_state.migrate(self.conn)

    def test_migrate_is_safe_on_a_current_database(self):
        scout_state.add_feed(self.conn, "u", "rss", 1, "", "", NOW)
        self.conn.commit()
        scout_state.migrate(self.conn)
        scout_state.migrate(self.conn)
        self.assertEqual(len(scout_state.feeds_all(self.conn)), 1)
        self.assertEqual(self.conn.execute("PRAGMA user_version").fetchone()[0], scout_state.SCHEMA_VERSION)

    def test_add_feed_is_idempotent_and_can_be_disabled(self):
        self.assertTrue(scout_state.add_feed(self.conn, "u", "rss", 1, "a", "r", NOW))
        self.assertFalse(scout_state.add_feed(self.conn, "u", "rss", 1, "a", "r", NOW))
        self.assertEqual(len(scout_state.feeds_enabled(self.conn)), 1)
        self.assertTrue(scout_state.set_feed_enabled(self.conn, "u", False))
        self.assertEqual(scout_state.feeds_enabled(self.conn), [])
        self.assertFalse(scout_state.set_feed_enabled(self.conn, "nope", True))

    def test_advance_mark_only_moves_forward(self):
        scout_state.add_feed(self.conn, "u", "rss", 1, "", "", NOW)
        scout_state.advance_mark(self.conn, "u", "2026-02-01T00:00:00Z")
        scout_state.advance_mark(self.conn, "u", "2026-01-01T00:00:00Z")
        self.assertEqual(scout_state.feeds_enabled(self.conn)[0]["high_water"], "2026-02-01T00:00:00Z")

    def test_record_candidate_upgrades_tier_and_bump_counts_inbound(self):
        self.assertTrue(scout_state.record_candidate(self.conn, "p", "", "f", 2, NOW))
        self.assertFalse(scout_state.record_candidate(self.conn, "p", "", "f", 2, NOW))
        scout_state.bump_inbound(self.conn, "p")
        self.assertEqual(scout_state.seen_row(self.conn, "p")["inbound"], 2)
        self.assertTrue(scout_state.record_candidate(self.conn, "p", "Title", "f", 1, NOW))
        row = scout_state.seen_row(self.conn, "p")
        self.assertEqual((row["tier"], row["title"], row["inbound"]), (1, "Title", 2))

    def test_pending_orders_tier_then_inbound_and_respects_limit(self):
        scout_state.record_candidate(self.conn, "low", "", "f", 2, NOW)
        scout_state.record_candidate(self.conn, "high", "", "f", 2, NOW)
        scout_state.bump_inbound(self.conn, "high")
        scout_state.record_candidate(self.conn, "own", "t", "f", 1, NOW)
        self.assertEqual([r["url"] for r in scout_state.candidates_pending(self.conn, 10)], ["own", "high", "low"])
        self.assertEqual(len(scout_state.candidates_pending(self.conn, 2)), 2)

    def test_scoring_removes_from_pending_and_survivors_follow_threshold(self):
        scout_state.record_candidate(self.conn, "own", "t", "f", 1, NOW)
        scout_state.record_candidate(self.conn, "weak", "t", "f", 2, NOW)
        scout_state.record_scores(self.conn, "own", 9, 8, "s", "k", "a", NOW)
        scout_state.record_scores(self.conn, "weak", 2, 2, "s", "k", "a", NOW)
        self.assertEqual(scout_state.candidates_pending(self.conn, 10), [])
        self.assertEqual([r["url"] for r in scout_state.survivors_undecided(self.conn, 6)], ["own"])
        self.assertIsNone(scout_state.record_scores(self.conn, "unknown", 1, 1, "", "", "", NOW))

    def test_rescoring_fires_only_when_inbound_changes(self):
        scout_state.record_candidate(self.conn, "p", "", "f", 2, NOW)
        scout_state.record_scores(self.conn, "p", 6, 6, "s", "k", "a", NOW)
        self.assertEqual(scout_state.rescorable(self.conn), [])
        scout_state.bump_inbound(self.conn, "p")
        self.assertEqual([r["url"] for r in scout_state.rescorable(self.conn)], ["p"])
        before = scout_state.seen_row(self.conn, "p")["last_score"]
        after = scout_state.rescore(self.conn, "p", NOW)
        self.assertGreater(after, before)
        self.assertEqual(scout_state.rescorable(self.conn), [])

    def test_decisions_final_verdicts_hide_a_candidate_and_defer_does_not(self):
        scout_state.record_candidate(self.conn, "p", "", "f", 2, NOW)
        scout_state.record_scores(self.conn, "p", 9, 9, "", "", "", NOW)
        scout_state.record_decision(self.conn, "p", "defer", "later", "", NOW)
        self.assertFalse(scout_state.is_decided(self.conn, "p"))
        self.assertEqual(len(scout_state.survivors_undecided(self.conn, 1)), 1)
        scout_state.record_decision(self.conn, "p", "reject", "off topic", "", NOW)
        self.assertTrue(scout_state.is_decided(self.conn, "p"))
        self.assertEqual(scout_state.decision_for(self.conn, "p")["reason"], "off topic")
        self.assertEqual(scout_state.survivors_undecided(self.conn, 1), [])
        self.assertIsNone(scout_state.decision_for(self.conn, "other"))
        with self.assertRaises(ValueError):
            scout_state.record_decision(self.conn, "p", "maybe", "", "", NOW)


class FetchTests(unittest.TestCase):
    def test_parses_atom_and_rss(self):
        with open(os.path.join(HERE, "recordings", "scout", "https_martinfowler_com_feed_atom.txt")) as handle:
            entries = scout_fetch.parse_feed(handle.read())
        self.assertEqual([e["url"] for e in entries], [GUARDRAILS, READING])
        self.assertEqual(entries[0]["published"], "2026-10-14T09:00:00Z")
        rss = (
            '<rss version="2.0"><channel><item><title>T</title><link>https://x.test/a</link>'
            "<pubDate>Wed, 14 Oct 2026 09:00:00 GMT</pubDate></item></channel></rss>"
        )
        parsed = scout_fetch.parse_feed(rss)
        self.assertEqual((parsed[0]["url"], parsed[0]["published"]), ("https://x.test/a", "2026-10-14T09:00:00Z"))

    def test_extract_links_keeps_only_external_http_links_outside_nav(self):
        with open(os.path.join(HERE, "recordings", "scout", "https_martinfowler_com_articles_guardrails_html.txt")) as handle:
            links = scout_fetch.extract_links(handle.read(), GUARDRAILS)
        self.assertEqual(links, [THIRD])

    def extract_recording(self, name, base):
        with open(os.path.join(HERE, "recordings", "scout", name)) as handle:
            return scout_fetch.extract_links(handle.read(), base)

    def test_extract_links_article_page_keeps_only_body_links(self):
        links = self.extract_recording(
            "https_martinfowler_com_articles_software_meets_hardware_html.txt",
            "https://martinfowler.com/articles/software-meets-hardware.html",
        )
        self.assertEqual(links, [])

    def test_extract_links_fragments_page_keeps_body_links_without_amazon(self):
        links = self.extract_recording(
            "https_martinfowler_com_fragments_2026_10_21_html.txt",
            "https://martinfowler.com/fragments/2026-10-21.html",
        )
        self.assertEqual(
            links,
            [
                "https://x.com/GergelyOrosz/status/2108863325756961274",
                "https://bjsm.bmj.com/content/60/9/677",
                "https://anitab.org/press-release",
                "https://copyconstruct.medium.com/how-to-effectively-debug-when-you-no-longer-understand-the-code-bd3dcb2c5f7b",
            ],
        )

    def test_extract_links_substack_post_drops_chrome_comments_images_and_sponsorship(self):
        links = self.extract_recording(
            "https_newsletter_kentbeck_com_p_decompose_run_on_tests.txt",
            "https://newsletter.kentbeck.com/p/decompose-run-on-tests",
        )
        self.assertEqual(links, ["http://grammar.ccc.commnet.edu/grammar/runons.htm", "https://testdesiderata.com"])

    def test_extract_links_excludes_assets_and_amazon_inside_a_body(self):
        page = (
            '<div class="paperBody deep">'
            '<a href="https://substackcdn.com/image/fetch/x">i</a>'
            '<a href="https://other.example/pic.PNG">p</a>'
            '<a href="https://www.amazon.com/gp/product/1">a</a>'
            '<a href="https://amzn.to/abc">b</a>'
            '<a href="https://other.example/doc.pdf">pdf</a>'
            '<a href="https://page.example/x">page</a></div>'
        )
        self.assertEqual(scout_fetch.extract_links(page, GUARDRAILS), ["https://other.example/doc.pdf", "https://page.example/x"])

    def test_extract_links_body_without_links_does_not_fall_back(self):
        page = '<a href="https://out.example/a">a</a><div class="paperBody shallow"><p>none</p></div>'
        self.assertEqual(scout_fetch.extract_links(page, GUARDRAILS), [])

    def test_extract_links_appendix_alone_counts_as_a_body(self):
        page = '<a href="https://out.example/a">a</a><div class="appendix"><a href="https://in.example/b">b</a></div>'
        self.assertEqual(scout_fetch.extract_links(page, GUARDRAILS), ["https://in.example/b"])

    def test_extract_links_still_skips_nav_inside_a_body(self):
        page = '<div class="body markup"><nav><a href="https://nav.example/a">n</a></nav><a href="https://in.example/b">b</a></div>'
        self.assertEqual(scout_fetch.extract_links(page, GUARDRAILS), ["https://in.example/b"])

    def test_first_run_is_capped_and_later_runs_use_the_mark(self):
        entries = [{"url": "https://x.test/%d" % i, "published": "2026-01-%02dT00:00:00Z" % i} for i in range(1, 10)]
        self.assertEqual(len(scout_fetch.new_entries(entries, "", set())), scout_fetch.FIRST_RUN_ENTRIES)
        self.assertEqual(len(scout_fetch.new_entries(entries, "2026-01-07T00:00:00Z", set())), 2)

    def test_kb_resources_reads_resource_lines(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        os.makedirs(os.path.join(root, "references"))
        with open(os.path.join(root, "references", "a.md"), "w") as handle:
            handle.write("---\nresource: https://Example.org/third/\n---\nbody\n")
        self.assertEqual(scout_fetch.kb_resources(root), {THIRD})
        self.assertIsNone(scout_fetch.kb_resources(os.path.join(root, "nowhere")))


class StageTests(Base):
    def test_guard_passes_on_new_entries_and_reads_nothing_into_state(self):
        out = self.guard()
        self.assertEqual(out["outcome"], "pass")
        self.assertIn("2 new entries", out["title"])
        self.assertIn(GUARDRAILS, out["description"])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM seen"), [(0,)])
        self.assertEqual(self.rows("SELECT high_water FROM feeds WHERE url = '%s'" % FOWLER), [("",)])

    def test_run_one_lists_candidates_with_tiers_and_inbound_and_run_two_files_nothing(self):
        out = self.guard()
        candidates = json.loads(self.harvest(out["state"])["artifacts"]["candidates"])["candidates"]
        by_url = {c["url"]: c for c in candidates}
        self.assertEqual(set(by_url), {GUARDRAILS, READING, THIRD})
        self.assertEqual((by_url[GUARDRAILS]["tier"], by_url[GUARDRAILS]["inbound"]), (1, 0))
        self.assertEqual((by_url[THIRD]["tier"], by_url[THIRD]["inbound"]), (2, 1))
        self.rank([
            {"url": u, "relevance": 8, "novelty": 8, "summary": "s", "kb_has": "k", "author": "a"} for u in by_url
        ])
        self.assertEqual(self.record({"decisions": [
            {"url": u, "verdict": "reject", "reason": "r"} for u in by_url
        ]}).returncode, 0)
        second = self.guard()
        self.assertEqual(second["outcome"], "fail")

    def test_harvest_is_idempotent(self):
        state = self.guard()["state"]
        self.harvest(state)
        before = self.rows("SELECT url, tier, inbound FROM seen ORDER BY url")
        self.harvest(state)
        self.assertEqual(self.rows("SELECT url, tier, inbound FROM seen ORDER BY url"), before)

    def test_page_linked_from_two_trusted_entries_is_one_row_with_inbound_two(self):
        state = json.loads(self.guard()["state"])
        state["entries"].append(
            {"feed": "https://tidyfirst.substack.com/feed", "url": BECK_POST, "title": "C", "author": "", "published": ""}
        )
        self.harvest(json.dumps(state))
        self.assertEqual(self.rows("SELECT inbound, tier FROM seen WHERE url = '%s'" % THIRD), [(2, 2)])

    def test_harvest_drops_what_the_knowledgebase_holds_and_what_was_decided(self):
        with open(os.path.join(self.kb, "references", "third.md"), "w") as handle:
            handle.write("---\nresource: %s\n---\n" % THIRD)
        self.assertEqual(self.record({"decisions": [{"url": READING, "verdict": "reject", "reason": "dull"}]}).returncode, 0)
        self.harvest(self.guard()["state"])
        self.assertEqual(self.rows("SELECT url FROM seen ORDER BY url"), [(GUARDRAILS,)])

    def test_harvest_advances_the_mark_so_the_guard_then_fails(self):
        self.harvest(self.guard()["state"])
        self.assertEqual(
            self.rows("SELECT high_water FROM feeds WHERE url = '%s'" % FOWLER), [("2026-10-15T09:00:00Z",)]
        )

    def test_harvest_needs_the_knowledgebase_worktree(self):
        stdin = json.dumps({"schedule_state": self.guard()["state"]})
        proc = run("harvest.py", self.data, stdin, cwd=self.root)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("references/", proc.stderr)

    def test_guard_passes_for_waiting_candidates_alone(self):
        self.harvest(self.guard()["state"])
        out = self.guard()
        self.assertEqual(out["outcome"], "pass")
        self.assertIn("3 waiting", out["title"])

    def test_rank_survivors_and_none(self):
        self.harvest(self.guard()["state"])
        scores = [
            {"url": GUARDRAILS, "relevance": 9, "novelty": 8, "summary": "Guardrails.", "kb_has": "nothing close", "author": "Martin Fowler"},
            {"url": READING, "relevance": 1, "novelty": 1, "summary": "", "kb_has": "", "author": ""},
        ]
        out = self.rank(scores)
        self.assertEqual(out["outcome"], "survivors")
        digest = out["artifacts"]["candidates-digest"]
        self.assertIn("--repo kenmclennan/knowledgebase", digest)
        self.assertIn("tier 1, inbound trusted links 0, score 9.", digest)
        self.assertNotIn(READING, digest)
        self.assertEqual(self.rank([], threshold="99")["outcome"], "none")

    def test_below_threshold_candidate_is_rescored_only_when_inbound_rises(self):
        state = json.loads(self.guard()["state"])
        self.harvest(json.dumps(state))
        scores = [{"url": THIRD, "relevance": 6, "novelty": 6, "summary": "", "kb_has": "", "author": ""}]
        self.assertEqual(self.rank(scores, threshold="6.5")["outcome"], "none")
        before = self.rows("SELECT last_score FROM seen WHERE url = '%s'" % THIRD)
        self.assertEqual(self.rank([], threshold="6.5")["outcome"], "none")
        self.assertEqual(self.rows("SELECT last_score FROM seen WHERE url = '%s'" % THIRD), before)
        state["entries"] = [
            {"feed": "https://tidyfirst.substack.com/feed", "url": BECK_POST, "title": "C", "author": "", "published": ""}
        ]
        self.harvest(json.dumps(state))
        out = self.rank([], threshold="6.5")
        self.assertEqual(out["outcome"], "survivors")
        self.assertIn(THIRD, out["artifacts"]["candidates-digest"])

    def test_one_accept_and_one_reject_are_readable_and_never_resurface(self):
        self.harvest(self.guard()["state"])
        done = self.record({
            "decisions": [
                {"url": GUARDRAILS, "verdict": "accept", "reason": "on point", "item": "KB-7"},
                {"url": READING, "verdict": "reject", "reason": "already covered"},
            ],
            "feeds": [{"url": "https://example.org/feed", "kind": "rss", "tier": 1, "reason": "keeps producing"}],
        })
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["outcome"], "written")
        cli = lambda *a: subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "scout-cli.py"), *a],
            capture_output=True, text=True, env=dict(os.environ, LC_WORKFLOW_DATA_DIR=self.data),
        ).stdout
        self.assertIn("accept", cli("why", GUARDRAILS))
        self.assertIn("on point", cli("why", GUARDRAILS))
        self.assertIn("KB-7", cli("why", GUARDRAILS))
        self.assertIn("already covered", cli("why", READING))
        self.assertIn("https://example.org/feed", cli("feeds"))
        again = self.harvest(self.guard()["state"])
        pending = json.loads(again["artifacts"]["candidates"])["candidates"]
        self.assertEqual([c["url"] for c in pending], [THIRD])

    def test_record_decisions_writes_every_verdict_when_none_were_accepted(self):
        done = self.record({"decisions": [
            {"url": GUARDRAILS, "verdict": "reject", "reason": "a"},
            {"url": READING, "verdict": "defer", "reason": "b"},
        ]})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM decisions"), [(2,)])
        again = self.record({"decisions": [{"url": GUARDRAILS, "verdict": "reject", "reason": "a"}]})
        self.assertEqual(again.returncode, 0)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM decisions"), [(2,)])

    def test_record_decisions_is_all_or_nothing_on_a_bad_verdict(self):
        done = self.record({"decisions": [
            {"url": GUARDRAILS, "verdict": "accept", "reason": "a"},
            {"url": READING, "verdict": "bogus", "reason": "b"},
        ]})
        self.assertEqual(done.returncode, 1)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM decisions"), [(0,)])

    def test_missing_inputs_park_with_a_reason(self):
        self.assertEqual(run("record-decisions.py", self.data).returncode, 1)
        self.assertEqual(run("rank.py", self.data).returncode, 1)
        self.assertEqual(run("harvest.py", self.data, "{}", cwd=self.kb).returncode, 1)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def _bare_env(self):
        env = dict(os.environ, LC_WORKFLOW_DATA_DIR=self.dir)
        for key in [k for k in env if k.startswith("LC_WORKFLOW_CONFIG_")]:
            del env[key]
        return env

    def test_install_passes_with_no_config_set(self):
        proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "scout-install.py")], capture_output=True, text=True, env=self._bare_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_install_fails_on_a_malformed_key(self):
        env = self._bare_env()
        env["LC_WORKFLOW_CONFIG_THRESHOLD"] = "high"
        proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "scout-install.py")], capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("threshold", proc.stderr)

    def test_install_seeds_both_feeds_once_and_upgrade_is_safe(self):
        for _ in range(2):
            self.assertEqual(run("scout-install.py", self.dir).returncode, 0)
        self.assertEqual(run("scout-upgrade.py", self.dir).returncode, 0)
        conn = sqlite3.connect(os.path.join(self.dir, "scout.db"))
        self.addCleanup(conn.close)
        urls = [r[0] for r in conn.execute("SELECT url FROM feeds ORDER BY url")]
        self.assertEqual(urls, ["https://martinfowler.com/feed.atom", "https://tidyfirst.substack.com/feed"])


if __name__ == "__main__":
    unittest.main()
