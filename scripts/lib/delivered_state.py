import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import triage_state

SCHEMA_VERSION = 1

config = triage_state.config
config_list = triage_state.config_list
emit = triage_state.emit
data_dir = triage_state.data_dir
DEFAULT_REPOS = triage_state.DEFAULT_REPOS


def db_path():
    return os.path.join(data_dir(), "delivered.db")


def connect():
    return sqlite3.connect(db_path(), timeout=30)


def migrate(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    with conn:
        if version < 1:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS shown ("
                "repo TEXT NOT NULL, number INTEGER NOT NULL, fingerprint TEXT NOT NULL, "
                "shown_at TEXT NOT NULL, PRIMARY KEY (repo, number))"
            )
        conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
