#!/usr/bin/env python3
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import triage_state


def load_state(stdin):
    raw = stdin.get("schedule_state")
    if not raw:
        sys.stderr.write("schedule_state is missing or empty; nothing to record\n")
        sys.exit(1)
    try:
        state = json.loads(raw)
        issues = [(i["repo"], int(i["number"])) for i in state["issues"]]
        marks = {str(r): str(m) for r, m in state["marks"].items()}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        sys.stderr.write("schedule_state is not a valid issues-and-marks object: %r\n" % (exc,))
        sys.exit(1)
    return issues, marks


def main():
    try:
        stdin = json.load(sys.stdin)
    except ValueError as exc:
        sys.stderr.write("stdin is not JSON: %s\n" % exc)
        sys.exit(1)
    issues, marks = load_state(stdin)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = triage_state.connect()
    try:
        triage_state.migrate(conn)
        with conn:
            conn.executemany(
                "INSERT OR IGNORE INTO raised (repo, number, raised_at) VALUES (?, ?, ?)",
                [(r, n, now) for r, n in issues],
            )
            conn.executemany(
                "INSERT INTO marks (repo, high_water) VALUES (?, ?) "
                "ON CONFLICT(repo) DO UPDATE SET high_water = MAX(high_water, excluded.high_water)",
                list(marks.items()),
            )
    except Exception as exc:
        sys.stderr.write("could not record raised issues: %s\n" % exc)
        sys.exit(1)
    finally:
        conn.close()
    triage_state.emit({"outcome": "recorded"})


if __name__ == "__main__":
    main()
