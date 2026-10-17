#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import scout_fetch
import scout_state


def main():
    threshold = scout_state.require_config("threshold", float)
    fetch_command = scout_state.config("fetch-command")

    conn = scout_state.connect()
    try:
        scout_state.migrate(conn)
        feeds = scout_state.feeds_enabled(conn)
        waiting = scout_state.pending_count(conn) + len(scout_state.survivors_undecided(conn, threshold))
        known = {r["url"] for r in scout_state.queue(conn)}
    finally:
        conn.close()

    entries = []
    marks = {}
    for feed in feeds:
        body = scout_fetch.fetch(feed["url"], fetch_command)
        if body is None:
            continue
        try:
            parsed = scout_fetch.parse_feed(body)
        except Exception as exc:
            sys.stderr.write("could not parse %s: %s\n" % (feed["url"], exc))
            continue
        for entry in scout_fetch.new_entries(parsed, feed["high_water"], known):
            entry = dict(entry, feed=feed["url"], url=scout_fetch.normalize(entry["url"]))
            entries.append(entry)
            if entry["published"] > marks.get(feed["url"], ""):
                marks[feed["url"]] = entry["published"]

    if not entries and not waiting:
        scout_state.emit({"outcome": "fail", "note": "no new entries and nothing waiting"})
        return

    lines = []
    for feed in feeds:
        group = [e for e in entries if e["feed"] == feed["url"]]
        if not group:
            continue
        lines.append(feed["url"])
        for e in group:
            lines.append("- [%s](%s)%s" % (e["title"] or e["url"], e["url"], " - " + e["author"] if e["author"] else ""))
        lines.append("")
    lines.append("%d candidate(s) or survivor(s) already waiting." % waiting)

    state = {"entries": entries, "marks": marks}
    scout_state.emit(
        {
            "outcome": "pass",
            "title": "Scout: %d new entries, %d waiting" % (len(entries), waiting),
            "description": "\n".join(lines).strip(),
            "state": json.dumps(state, sort_keys=True),
        }
    )


if __name__ == "__main__":
    main()
