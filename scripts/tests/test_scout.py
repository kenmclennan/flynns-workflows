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
from stage_env import stage_env, with_environment, workflow_env

FAKE_FETCH = os.path.join(HERE, "fake-fetch.py")
FOWLER = "https://martinfowler.com/feed.atom"
GUARDRAILS = "https://martinfowler.com/articles/guardrails.html"
READING = "https://martinfowler.com/articles/reading-output.html"
THIRD = "https://example.org/third"
BECK_POST = "https://tidyfirst.substack.com/p/c"
NOW = "2026-10-18T09:00:00Z"


STAGE_STEPS = {
    "harvest.py": "harvest",
    "rank.py": "rank",
    "record-decisions.py": "record-decisions",
}


def run(script, data_dir, stdin="{}", cwd=None, **config):
    overrides = dict({"fetch-command": FAKE_FETCH, "threshold": "6", "batch-cap": "10"}, **config)
    if script in STAGE_STEPS:
        configured = stage_env(STAGE_STEPS[script], "kb-scout", **overrides)
    else:
        configured = workflow_env("kb-scout", **overrides)
    env = with_environment(os.environ, configured)
    env["LC_WORKFLOW_DATA_DIR"] = data_dir
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

    def write(self, sql, params=()):
        conn = self.db()
        conn.execute(sql, params)
        conn.commit()

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


V1_SCHEMA = [
    "CREATE TABLE feeds (url TEXT PRIMARY KEY, kind TEXT NOT NULL, tier INTEGER NOT NULL, areas TEXT NOT NULL DEFAULT '', "
    "enabled INTEGER NOT NULL DEFAULT 1, high_water TEXT NOT NULL DEFAULT '', added TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '')",
    "CREATE TABLE seen (url TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', feed TEXT NOT NULL, tier INTEGER NOT NULL, "
    "inbound INTEGER NOT NULL DEFAULT 0, first_seen TEXT NOT NULL, last_score REAL, scored_at TEXT, "
    "relevance REAL, novelty REAL, summary TEXT NOT NULL DEFAULT '', kb_has TEXT NOT NULL DEFAULT '', "
    "author TEXT NOT NULL DEFAULT '', scored_inbound INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE decisions (url TEXT PRIMARY KEY, verdict TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', "
    "decided_at TEXT NOT NULL, item_id TEXT NOT NULL DEFAULT '')",
]


class MigrationTests(unittest.TestCase):
    def v1(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        for sql in V1_SCHEMA:
            conn.execute(sql)
        conn.execute("INSERT INTO seen (url, feed, tier, inbound, first_seen) VALUES ('t1', 'f', 1, 0, ?)", (NOW,))
        conn.execute(
            "INSERT INTO seen (url, feed, tier, inbound, first_seen, last_score, scored_at) VALUES ('s2', 'f', 2, 1, ?, 7, ?)",
            (NOW, NOW),
        )
        conn.execute("INSERT INTO seen (url, feed, tier, inbound, first_seen) VALUES ('u2', 'f', 2, 1, ?)", (NOW,))
        conn.execute("INSERT INTO decisions (url, verdict, decided_at) VALUES ('s2', 'accept', ?)", (NOW,))
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        return conn

    def test_migrate_takes_a_version_one_database_to_two_keeping_every_row(self):
        conn = self.v1()
        scout_state.migrate(conn)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
        rows = conn.execute("SELECT url, roundup, picked FROM seen ORDER BY url").fetchall()
        self.assertEqual([tuple(r) for r in rows], [("s2", 0, 0), ("t1", 0, 0), ("u2", 0, 0)])
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()}
        self.assertIn("idx_links_parent", names)
        self.assertIn("sqlite_autoindex_links_1", names)
        self.assertEqual(conn.execute("SELECT verdict FROM decisions WHERE url = 's2'").fetchone()[0], "accept")
        self.assertEqual([r["url"] for r in scout_state.candidates_pending(conn, 10)], ["t1", "u2"])

    def test_migrate_is_rerunnable_after_a_half_migration(self):
        conn = self.v1()
        conn.execute("ALTER TABLE seen ADD COLUMN roundup INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        scout_state.migrate(conn)
        columns = {r[1] for r in conn.execute("PRAGMA table_info(seen)").fetchall()}
        self.assertTrue({"roundup", "picked"} <= columns)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)


class OrderingTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        os.environ["LC_WORKFLOW_DATA_DIR"] = tempfile.gettempdir()
        self.addCleanup(os.environ.pop, "LC_WORKFLOW_DATA_DIR")
        scout_state.migrate(self.conn)

    def cand(self, url, tier=2, score=None, parent=None, picked=False, inbound=None):
        scout_state.record_candidate(self.conn, url, "", "f", tier, NOW)
        if score is not None:
            self.conn.execute("UPDATE seen SET last_score = ?, scored_at = ? WHERE url = ?", (score, NOW, url))
        if picked:
            self.conn.execute("UPDATE seen SET picked = 1 WHERE url = ?", (url,))
        if inbound:
            self.conn.execute("UPDATE seen SET inbound = ? WHERE url = ?", (inbound, url))
        for p in ([parent] if isinstance(parent, str) else parent or []):
            scout_state.record_link(self.conn, url, p, "", "", NOW)

    def order(self, limit=20):
        return [r["url"] for r in scout_state.candidates_pending(self.conn, limit)]

    def build(self):
        self.cand("P1", tier=1, score=8)
        self.cand("P2", tier=1, score=6.6)
        self.cand("a", parent="P1", picked=True)
        self.cand("b", parent="P1")
        self.cand("c", parent="P2")
        self.cand("d", inbound=5)
        self.cand("t", tier=1)

    def test_tier_one_then_picked_then_parent_score_then_legacy(self):
        self.build()
        self.assertEqual(self.order(), ["t", "a", "b", "c", "d"])
        self.assertEqual(len(self.order(2)), 2)

    def test_a_link_from_two_parents_ranks_by_the_higher_score(self):
        self.build()
        self.cand("both", parent=["P2", "P1"])
        self.cand("b2", parent="P1")
        self.assertEqual(self.order()[1:4], ["a", "b", "b2"])
        self.assertLess(self.order().index("both"), self.order().index("c"))

    def test_picked_beats_parent_score(self):
        self.build()
        self.cand("e", parent="P2", picked=True)
        order = self.order()
        self.assertLess(order.index("e"), order.index("b"))

    def test_an_unscored_parent_does_not_lend_rank(self):
        self.cand("U", tier=1)
        self.cand("x", parent="U")
        self.cand("y", inbound=3)
        self.assertEqual(self.order(), ["U", "y", "x"])


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
        self.assertEqual(links, ["http://grammar.ccc.commnet.edu/grammar/runons.htm"])

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

    def test_extract_link_context_on_the_fragments_recording(self):
        with open(os.path.join(HERE, "recordings", "scout", "https_martinfowler_com_fragments_2026_10_21_html.txt")) as handle:
            found = scout_fetch.extract_link_context(handle.read(), "https://martinfowler.com/fragments/2026-10-21.html")
        self.assertEqual(
            [(f["url"], f["anchor"], f["context"]) for f in found],
            [
                ("https://bjsm.bmj.com/content/60/9/677", "a study", "See a post and a study."),
                ("https://anitab.org/press-release", "press", "press debugging book"),
                (
                    "https://copyconstruct.medium.com/how-to-effectively-debug-when-you-no-longer-understand-the-code-bd3dcb2c5f7b",
                    "debugging",
                    "press debugging book",
                ),
            ],
        )

    def test_extract_link_context_on_the_kent_beck_recording(self):
        with open(os.path.join(HERE, "recordings", "scout", "https_newsletter_kentbeck_com_p_decompose_run_on_tests.txt")) as handle:
            found = scout_fetch.extract_link_context(handle.read(), "https://newsletter.kentbeck.com/p/decompose-run-on-tests")
        self.assertEqual([(f["url"], f["anchor"]) for f in found], [("http://grammar.ccc.commnet.edu/grammar/runons.htm", "run-ons")])

    def test_noise_hosts_and_bare_homepages_are_dropped_on_a_dot_boundary(self):
        page = (
            '<div class="paperBody">'
            + "".join(
                '<a href="%s">l</a>' % u
                for u in (
                    "https://www.youtube.com/watch?v=1",
                    "https://en.wikipedia.org/wiki/X",
                    "https://www.linkedin.com/in/a",
                    "https://x.com/a/status/1",
                    "https://twitter.com/a",
                    "https://stratechery.com",
                    "https://cucumber.io/?ref=x",
                    "https://page.example/x",
                    "https://notyoutube.com/a",
                    "https://x.com.example/a",
                )
            )
            + "</div>"
        )
        self.assertEqual(
            scout_fetch.extract_links(page, GUARDRAILS),
            ["https://page.example/x", "https://notyoutube.com/a", "https://x.com.example/a"],
        )

    def test_long_blocks_yield_a_window_before_the_anchor(self):
        lead = "word " * 80
        page = '<div class="paperBody"><p>%s<a href="https://page.example/x">here</a> %s</p></div>' % (lead, "tail " * 80)
        found = scout_fetch.extract_link_context(page, GUARDRAILS)[0]
        self.assertEqual(len(found["context"]), 300)
        self.assertIn("here", found["context"])
        self.assertTrue(found["context"].startswith("word"))

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

    def test_harvest_records_provenance_once_and_a_second_parent_adds_a_row(self):
        state = json.loads(self.guard()["state"])
        self.harvest(json.dumps(state))
        rows = self.rows("SELECT parent, anchor, context FROM links WHERE url = '%s'" % THIRD)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], GUARDRAILS)
        self.assertTrue(rows[0][1])
        self.assertIn(rows[0][1], rows[0][2])
        before = self.rows("SELECT COUNT(*) FROM links")
        self.harvest(json.dumps(state))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM links"), before)
        state["entries"].append(
            {"feed": "https://tidyfirst.substack.com/feed", "url": BECK_POST, "title": "C", "author": "", "published": ""}
        )
        self.harvest(json.dumps(state))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM links WHERE url = '%s'" % THIRD), [(2,)])
        self.assertEqual(self.rows("SELECT inbound FROM seen WHERE url = '%s'" % THIRD), [(2,)])

    def test_harvest_sweeps_legacy_noise_and_nothing_else(self):
        self.guard()
        conn = self.db()
        for url, scored in (
            ("https://www.youtube.com/watch?v=1", False),
            ("https://stratechery.com", False),
            ("https://real.example/article", False),
            ("https://www.youtube.com/watch?v=2", True),
            ("https://www.youtube.com/watch?v=3", False),
        ):
            conn.execute(
                "INSERT INTO seen (url, feed, tier, inbound, first_seen, scored_at) VALUES (?, 'f', 2, 1, ?, ?)",
                (url, NOW, NOW if scored else None),
            )
            conn.execute("INSERT INTO links (url, parent, first_seen) VALUES (?, 'p', ?)", (url, NOW))
        conn.execute(
            "INSERT INTO decisions (url, verdict, decided_at) VALUES ('https://www.youtube.com/watch?v=3', 'defer', ?)", (NOW,)
        )
        conn.commit()
        self.harvest(self.guard()["state"])
        remaining = {r[0] for r in self.rows("SELECT url FROM seen WHERE tier = 2")}
        self.assertTrue(
            {"https://real.example/article", "https://www.youtube.com/watch?v=2", "https://www.youtube.com/watch?v=3"} <= remaining
        )
        self.assertNotIn("https://stratechery.com", remaining)
        self.assertNotIn("https://www.youtube.com/watch?v=1", remaining)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM links WHERE url = 'https://stratechery.com'"), [(0,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM links WHERE url = 'https://real.example/article'"), [(1,)])

    def test_rank_records_picks_roundup_and_title_and_skips_unlinked_follows(self):
        self.harvest(self.guard()["state"])
        score = {
            "url": GUARDRAILS, "relevance": 9, "novelty": 8, "title": "A fresh title", "roundup": True,
            "follow": ["HTTPS://Example.org/third/", "https://nowhere.example/x"],
        }
        titled = {"url": THIRD, "relevance": 5, "novelty": 5, "title": "Third page"}
        stdin = json.dumps({"item_artifacts": {"scores": json.dumps([score, titled])}})
        proc = run("rank.py", self.data, stdin)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("https://nowhere.example/x", proc.stderr)
        self.assertNotIn(THIRD + " ", proc.stderr)
        self.assertEqual(self.rows("SELECT picked FROM seen WHERE url = '%s'" % THIRD), [(1,)])
        self.assertEqual(self.rows("SELECT roundup, title FROM seen WHERE url = '%s'" % GUARDRAILS), [(1, "Agent guardrails")])
        self.assertEqual(self.rows("SELECT roundup, title FROM seen WHERE url = '%s'" % THIRD), [(0, "Third page")])
        digest = json.loads(proc.stdout)["artifacts"]["candidates-digest"]
        self.assertIn("  roundup, follows: %s" % THIRD, digest)

    def test_rank_ignores_follow_when_not_a_roundup_and_all_valid_or_none_valid(self):
        self.harvest(self.guard()["state"])
        stdin = json.dumps({"item_artifacts": {"scores": json.dumps([
            {"url": GUARDRAILS, "relevance": 9, "novelty": 8, "roundup": False, "follow": [THIRD]}
        ])}})
        self.assertEqual(run("rank.py", self.data, stdin).returncode, 0)
        self.assertEqual(self.rows("SELECT picked FROM seen WHERE url = '%s'" % THIRD), [(0,)])
        stdin = json.dumps({"item_artifacts": {"scores": json.dumps([
            {"url": GUARDRAILS, "relevance": 9, "novelty": 8, "roundup": True, "follow": ["https://a.example/1", "https://a.example/2"]}
        ])}})
        proc = run("rank.py", self.data, stdin)
        self.assertEqual(proc.stderr.count("skipped"), 2)
        self.assertEqual(self.rows("SELECT picked FROM seen WHERE url = '%s'" % THIRD), [(0,)])

    def test_digest_shows_via_for_tier_two_and_nothing_extra_for_tier_one(self):
        state = json.loads(self.guard()["state"])
        state["entries"].append(
            {"feed": "https://tidyfirst.substack.com/feed", "url": BECK_POST, "title": "C", "author": "", "published": ""}
        )
        self.harvest(json.dumps(state))
        self.write("UPDATE seen SET title = 'Guardrails post' WHERE url = '%s'" % GUARDRAILS)
        scores = [{"url": u, "relevance": 9, "novelty": 8} for u in (GUARDRAILS, THIRD)]
        digest = self.rank(scores)["artifacts"]["candidates-digest"]
        block = digest.split("- ")[1:]
        third = [b for b in block if THIRD in b][0].split("\n")
        self.assertTrue(third[1].startswith("  via "), third)
        self.assertIn("(+1 more)", third[1])
        tier_one = [b for b in block if "link: %s" % GUARDRAILS in b][0]
        self.assertNotIn("  via ", tier_one)
        self.assertNotIn("roundup, follows", tier_one)

    def test_digest_first_line_is_the_anchor_without_a_title_and_legacy_rows_print_as_before(self):
        self.harvest(self.guard()["state"])
        legacy = "https://legacy.example/a"
        self.write("INSERT INTO seen (url, feed, tier, inbound, first_seen) VALUES (?, 'f', 2, 1, ?)", (legacy, NOW))
        anchor = self.rows("SELECT anchor FROM links WHERE url = '%s'" % THIRD)[0][0]
        digest = self.rank([{"url": u, "relevance": 9, "novelty": 8} for u in (THIRD, legacy)])["artifacts"]["candidates-digest"]
        block = digest.split("- ")[1:]
        self.assertEqual([b for b in block if THIRD in b][0].split("\n")[0], anchor)
        legacy_block = [b for b in block if legacy in b][0].split("\n")
        self.assertEqual(legacy_block[0], legacy)
        self.assertNotIn("  via ", "\n".join(legacy_block))

    def test_guard_passes_for_picked_unscored_rows_alone(self):
        self.harvest(self.guard()["state"])
        self.write("UPDATE seen SET picked = 1 WHERE url = '%s'" % THIRD)
        self.assertEqual(self.guard()["outcome"], "pass")

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
        def cli(*a):
            return subprocess.run(
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
        env = with_environment(os.environ, {})
        env["LC_WORKFLOW_DATA_DIR"] = self.dir
        return env

    def _install(self, env):
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, "scout-install.py")], capture_output=True, text=True, env=env)

    def test_install_passes_with_no_config_set(self):
        env = with_environment(self._bare_env(), workflow_env("kb-scout", **{"qmd-command": os.path.join(HERE, "fake-qmd.py")}))
        proc = self._install(env)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_install_passes_with_an_unset_qmd_command(self):
        env = with_environment(self._bare_env(), workflow_env("kb-scout"))
        del env["LC_WORKFLOW_CONFIG_QMD_COMMAND"]
        proc = self._install(env)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_install_fails_on_a_malformed_key(self):
        env = with_environment(self._bare_env(), workflow_env("kb-scout", threshold="high"))
        proc = self._install(env)
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
