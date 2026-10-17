#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import scout_state


def load_decisions(stdin):
    raw = scout_state.read_artifact(stdin, "decisions")
    if raw is None:
        sys.stderr.write("no decisions artifact on the item; the gate closed without one\n")
        sys.exit(1)
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        decisions = [
            {
                "url": str(d["url"]),
                "verdict": str(d["verdict"]),
                "reason": str(d.get("reason") or ""),
                "item": str(d.get("item") or ""),
            }
            for d in data["decisions"]
        ]
        feeds = [
            {
                "url": str(f["url"]),
                "kind": str(f.get("kind") or "rss"),
                "tier": int(f.get("tier") or 1),
                "areas": str(f.get("areas") or ""),
                "reason": str(f.get("reason") or ""),
            }
            for f in data.get("feeds") or []
        ]
    except (ValueError, KeyError, TypeError) as exc:
        sys.stderr.write("decisions is not an object with a decisions list: %r\n" % (exc,))
        sys.exit(1)
    for d in decisions:
        if d["verdict"] not in scout_state.VERDICTS:
            sys.stderr.write("verdict %r for %s is not one of %s\n" % (d["verdict"], d["url"], ", ".join(scout_state.VERDICTS)))
            sys.exit(1)
    return decisions, feeds


def main():
    try:
        stdin = json.load(sys.stdin)
    except ValueError as exc:
        sys.stderr.write("stdin is not JSON: %s\n" % exc)
        sys.exit(1)
    decisions, feeds = load_decisions(stdin)
    now = scout_state.now_iso()

    conn = scout_state.connect()
    try:
        scout_state.migrate(conn)
        with conn:
            for d in decisions:
                scout_state.record_decision(conn, d["url"], d["verdict"], d["reason"], d["item"], now)
            for f in feeds:
                scout_state.add_feed(conn, f["url"], f["kind"], f["tier"], f["areas"], f["reason"], now)
    except Exception as exc:
        sys.stderr.write("could not record decisions: %s\n" % exc)
        sys.exit(1)
    finally:
        conn.close()
    scout_state.emit({"outcome": "written"})


if __name__ == "__main__":
    main()
