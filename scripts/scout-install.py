#!/usr/bin/env python3
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import scout_state

REQUIRED = (("threshold", float), ("batch-cap", int), ("kb-repo", str))


def main():
    failures = []
    for key, cast in REQUIRED:
        raw = scout_state.config(key)
        if raw is None:
            continue
        try:
            cast(raw)
        except ValueError:
            failures.append("config key %r is %r, not a valid %s" % (key, raw, cast.__name__))
    for module in ("xml.etree.ElementTree", "html.parser", "sqlite3"):
        try:
            __import__(module)
        except ImportError:
            failures.append("python module %s is not importable" % module)
    if failures:
        sys.stderr.write("error: kb-scout cannot be installed: %s\n" % "; ".join(failures))
        sys.exit(1)
    if not shutil.which(scout_state.config("qmd-command", "qmd").split()[0]):
        sys.stderr.write("warning: qmd is not on PATH, so evaluate falls back to reading index.md files\n")

    os.makedirs(scout_state.data_dir(), exist_ok=True)
    conn = scout_state.connect()
    try:
        scout_state.migrate(conn)
        now = scout_state.now_iso()
        with conn:
            for url, kind, tier, areas, reason in scout_state.SEED_FEEDS:
                scout_state.add_feed(conn, url, kind, tier, areas, reason, now)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
