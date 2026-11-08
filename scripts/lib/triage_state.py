import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import workflow_config

SCHEMA_VERSION = 1

def data_dir():
    return os.environ.get("LC_WORKFLOW_DATA_DIR") or os.getcwd()


def db_path():
    return os.path.join(data_dir(), "triage.db")


def connect():
    return sqlite3.connect(db_path(), timeout=30)


def migrate(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    with conn:
        if version < 1:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS raised ("
                "repo TEXT NOT NULL, number INTEGER NOT NULL, raised_at TEXT NOT NULL, "
                "PRIMARY KEY (repo, number))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS marks (repo TEXT PRIMARY KEY, high_water TEXT NOT NULL)"
            )
        conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)


config = workflow_config.config
config_list = workflow_config.config_list
require_config = workflow_config.require_config
require_config_list = workflow_config.require_config_list


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")
