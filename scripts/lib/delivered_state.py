import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import triage_state
import workflow_config

SCHEMA_VERSION = 1

config = workflow_config.config
config_list = workflow_config.config_list
require_config = workflow_config.require_config
require_config_list = workflow_config.require_config_list
emit = triage_state.emit
data_dir = triage_state.data_dir


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
