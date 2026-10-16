import json
import os
import sqlite3
import sys

SCHEMA_VERSION = 1

DEFAULT_REPOS = [
    "kenmclennan/lightcycle",
    "kenmclennan/lightcycle-workflows",
    "kenmclennan/lightcycle-plugin",
    "kenmclennan/lightcycle-specs",
]


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


def config(key, default=None):
    value = os.environ.get("LC_WORKFLOW_CONFIG_" + key.upper().replace("-", "_"))
    if value is None or value.strip() == "":
        return default
    return value.strip()


def config_list(key, default=None):
    value = config(key)
    if value is None:
        return default if default is not None else []
    return [part.strip() for part in value.split(",") if part.strip()]


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")
