#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import scout_fetch
import scout_state


def load_state(stdin):
    raw = stdin.get("schedule_state")
    if not raw:
        sys.stderr.write("schedule_state is missing or empty; nothing to harvest\n")
        sys.exit(1)
    try:
        state = json.loads(raw)
        entries = [
            {
                "feed": str(e["feed"]),
                "url": scout_fetch.normalize(e["url"]),
                "title": str(e.get("title") or ""),
                "author": str(e.get("author") or ""),
            }
            for e in state["entries"]
        ]
        marks = {str(f): str(m) for f, m in state["marks"].items()}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        sys.stderr.write("schedule_state is not a valid entries-and-marks object: %r\n" % (exc,))
        sys.exit(1)
    return entries, marks


def main():
    try:
        stdin = json.load(sys.stdin)
    except ValueError as exc:
        sys.stderr.write("stdin is not JSON: %s\n" % exc)
        sys.exit(1)
    entries, marks = load_state(stdin)
    batch_cap = scout_state.require_config("batch-cap", int)
    fetch_command = scout_state.config("fetch-command")

    in_kb = scout_fetch.kb_resources(os.getcwd())
    if in_kb is None:
        sys.stderr.write(
            "no references/ directory in %s; harvest must run in the knowledgebase worktree to check what it already holds\n"
            % os.getcwd()
        )
        sys.exit(1)

    now = scout_state.now_iso()
    conn = scout_state.connect()
    try:
        scout_state.migrate(conn)
        with conn:
            for entry in entries:
                url = entry["url"]
                if url in in_kb or scout_state.is_decided(conn, url):
                    continue
                row = scout_state.seen_row(conn, url)
                if row and row["tier"] == 1:
                    continue
                scout_state.record_candidate(conn, url, entry["title"], entry["feed"], 1, now, entry["author"])
                page = scout_fetch.fetch(url, fetch_command)
                if page is None:
                    continue
                for link in scout_fetch.extract_links(page, url):
                    if link in in_kb or scout_state.is_decided(conn, link):
                        continue
                    if scout_state.seen_row(conn, link):
                        scout_state.bump_inbound(conn, link)
                    else:
                        scout_state.record_candidate(conn, link, "", entry["feed"], 2, now)
            for feed, mark in marks.items():
                scout_state.advance_mark(conn, feed, mark)
        pending = scout_state.candidates_pending(conn, batch_cap)
    finally:
        conn.close()

    candidates = {
        "kb_checkout": scout_state.config("checkout-path", "none"),
        "qmd": scout_state.config("qmd-command", "qmd"),
        "batch_cap": batch_cap,
        "candidates": [
            {"url": r["url"], "title": r["title"], "author": r["author"], "tier": r["tier"], "inbound": r["inbound"], "feed": r["feed"]}
            for r in pending
        ],
    }
    scout_state.emit(
        {"outcome": "harvested", "artifacts": {"candidates": json.dumps(candidates, indent=2, sort_keys=True)}}
    )


if __name__ == "__main__":
    main()
