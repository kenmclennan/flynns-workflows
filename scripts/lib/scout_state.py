import datetime
import json
import os
import sqlite3
import sys

SCHEMA_VERSION = 1

SEED_FEEDS = [
    ("https://martinfowler.com/feed.atom", "atom", 1, "emerging tools, organisational learning", "Martin Fowler, seed"),
    ("https://tidyfirst.substack.com/feed", "rss", 1, "the developer's own learning, understanding agent output", "Kent Beck, seed"),
]

VERDICTS = ("accept", "reject", "defer")
FINAL_VERDICTS = ("accept", "reject")


def data_dir():
    return os.environ.get("LC_WORKFLOW_DATA_DIR") or os.getcwd()


def db_path():
    return os.path.join(data_dir(), "scout.db")


def connect():
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def migrate(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    with conn:
        if version < 1:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS feeds ("
                "url TEXT PRIMARY KEY, kind TEXT NOT NULL, tier INTEGER NOT NULL, areas TEXT NOT NULL DEFAULT '', "
                "enabled INTEGER NOT NULL DEFAULT 1, high_water TEXT NOT NULL DEFAULT '', "
                "added TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '')"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS seen ("
                "url TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', feed TEXT NOT NULL, tier INTEGER NOT NULL, "
                "inbound INTEGER NOT NULL DEFAULT 0, first_seen TEXT NOT NULL, last_score REAL, scored_at TEXT, "
                "relevance REAL, novelty REAL, summary TEXT NOT NULL DEFAULT '', kb_has TEXT NOT NULL DEFAULT '', "
                "author TEXT NOT NULL DEFAULT '', scored_inbound INTEGER NOT NULL DEFAULT 0)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS decisions ("
                "url TEXT PRIMARY KEY, verdict TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', "
                "decided_at TEXT NOT NULL, item_id TEXT NOT NULL DEFAULT '')"
            )
        conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)


def _rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def add_feed(conn, url, kind, tier, areas, reason, now, enabled=True):
    cur = conn.execute(
        "INSERT OR IGNORE INTO feeds (url, kind, tier, areas, enabled, added, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (url, kind, int(tier), areas, 1 if enabled else 0, now, reason),
    )
    return cur.rowcount == 1


def set_feed_enabled(conn, url, enabled):
    return conn.execute("UPDATE feeds SET enabled = ? WHERE url = ?", (1 if enabled else 0, url)).rowcount == 1


def feeds_enabled(conn):
    return _rows(conn.execute("SELECT * FROM feeds WHERE enabled = 1 ORDER BY url"))


def feeds_all(conn):
    return _rows(conn.execute("SELECT * FROM feeds ORDER BY url"))


def advance_mark(conn, url, mark):
    conn.execute("UPDATE feeds SET high_water = ? WHERE url = ? AND high_water < ?", (mark, url, mark))


def seen_row(conn, url):
    row = conn.execute("SELECT * FROM seen WHERE url = ?", (url,)).fetchone()
    return dict(row) if row else None


def record_candidate(conn, url, title, feed, tier, now, author=""):
    row = seen_row(conn, url)
    if row is None:
        conn.execute(
            "INSERT INTO seen (url, title, feed, tier, inbound, first_seen, author) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (url, title, feed, int(tier), 1 if tier == 2 else 0, now, author),
        )
        return True
    if tier < row["tier"]:
        conn.execute(
            "UPDATE seen SET tier = ?, title = ?, feed = ?, author = ? WHERE url = ?",
            (int(tier), title or row["title"], feed, author or row["author"], url),
        )
        return True
    return False


def bump_inbound(conn, url):
    conn.execute("UPDATE seen SET inbound = inbound + 1 WHERE url = ?", (url,))


def candidates_pending(conn, limit):
    return _rows(
        conn.execute(
            "SELECT s.* FROM seen s LEFT JOIN decisions d ON d.url = s.url "
            "WHERE s.scored_at IS NULL AND (d.verdict IS NULL OR d.verdict = 'defer') "
            "ORDER BY s.tier ASC, s.inbound DESC, s.first_seen ASC, s.url ASC LIMIT ?",
            (int(limit),),
        )
    )


def pending_count(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM seen s LEFT JOIN decisions d ON d.url = s.url "
        "WHERE s.scored_at IS NULL AND (d.verdict IS NULL OR d.verdict = 'defer')"
    ).fetchone()[0]


def combined_score(relevance, novelty, tier, inbound):
    bonus = (1.0 if tier == 1 else 0.0) + 0.5 * min(max(inbound - 1, 0), 4)
    return round(0.6 * relevance + 0.4 * novelty + bonus, 2)


def record_scores(conn, url, relevance, novelty, summary, kb_has, author, now):
    row = seen_row(conn, url)
    if row is None:
        return None
    score = combined_score(relevance, novelty, row["tier"], row["inbound"])
    conn.execute(
        "UPDATE seen SET relevance = ?, novelty = ?, summary = ?, kb_has = ?, author = ?, last_score = ?, "
        "scored_at = ?, scored_inbound = inbound WHERE url = ?",
        (relevance, novelty, summary or row["summary"], kb_has or row["kb_has"], author or row["author"], score, now, url),
    )
    return score


def rescorable(conn):
    return _rows(
        conn.execute(
            "SELECT * FROM seen WHERE scored_at IS NOT NULL AND relevance IS NOT NULL AND inbound > scored_inbound"
        )
    )


def rescore(conn, url, now):
    row = seen_row(conn, url)
    score = combined_score(row["relevance"], row["novelty"], row["tier"], row["inbound"])
    conn.execute(
        "UPDATE seen SET last_score = ?, scored_at = ?, scored_inbound = inbound WHERE url = ?", (score, now, url)
    )
    return score


def survivors_undecided(conn, threshold):
    return _rows(
        conn.execute(
            "SELECT s.* FROM seen s LEFT JOIN decisions d ON d.url = s.url "
            "WHERE s.last_score IS NOT NULL AND s.last_score >= ? AND (d.verdict IS NULL OR d.verdict = 'defer') "
            "ORDER BY s.last_score DESC, s.url ASC",
            (float(threshold),),
        )
    )


def record_decision(conn, url, verdict, reason, item_id, now):
    if verdict not in VERDICTS:
        raise ValueError("verdict %r is not one of %s" % (verdict, ", ".join(VERDICTS)))
    conn.execute(
        "INSERT INTO decisions (url, verdict, reason, decided_at, item_id) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(url) DO UPDATE SET verdict = excluded.verdict, reason = excluded.reason, "
        "decided_at = excluded.decided_at, item_id = excluded.item_id",
        (url, verdict, reason, now, item_id),
    )


def decision_for(conn, url):
    row = conn.execute("SELECT * FROM decisions WHERE url = ?", (url,)).fetchone()
    return dict(row) if row else None


def is_decided(conn, url):
    row = decision_for(conn, url)
    return row is not None and row["verdict"] in FINAL_VERDICTS


def queue(conn):
    return _rows(
        conn.execute(
            "SELECT s.*, d.verdict AS verdict FROM seen s LEFT JOIN decisions d ON d.url = s.url "
            "ORDER BY s.last_score IS NULL DESC, s.last_score DESC, s.url ASC"
        )
    )


def config(key, default=None):
    value = os.environ.get("LC_WORKFLOW_CONFIG_" + key.upper().replace("-", "_"))
    if value is None or value.strip() == "":
        return default
    return value.strip()


def require_config(key, cast=str):
    raw = config(key)
    if raw is None:
        sys.stderr.write("config key %r is required and not set\n" % key)
        sys.exit(1)
    try:
        return cast(raw)
    except ValueError:
        sys.stderr.write("config key %r is %r, which is not a valid %s\n" % (key, raw, cast.__name__))
        sys.exit(1)


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_artifact(stdin, name):
    for source in ("item_artifacts", "step_artifacts"):
        found = stdin.get(source)
        if isinstance(found, dict) and name in found:
            value = found[name]
            return value.get("value") if isinstance(value, dict) else value
        if isinstance(found, list):
            for entry in reversed(found):
                if isinstance(entry, dict) and entry.get("type") == name:
                    return entry.get("value")
    return None
