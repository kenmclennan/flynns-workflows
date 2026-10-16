#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import drift


def main():
    try:
        stdin = json.load(sys.stdin)
    except ValueError:
        stdin = {}
    try:
        last = drift.parse_state(stdin.get("last_state"))
    except (ValueError, AttributeError) as exc:
        sys.stderr.write("last_state is not a valid from/to object: %r\n" % (exc,))
        sys.exit(1)

    now = {}
    try:
        for name in drift.REPOS:
            drift.ensure_clone(name)
            now[name] = drift.main_sha(name)
    except RuntimeError as exc:
        sys.stderr.write("%s\n" % exc)
        sys.exit(1)

    previous = last["to"]
    moved = [n for n in drift.REPOS if previous.get(n) != now[n]]
    if not moved:
        drift.emit({"outcome": "fail", "note": "no repo moved"})
        return

    lines = []
    for name in moved:
        old = previous.get(name)
        if old:
            lines.append("%s: %s -> %s (%s commit(s))" % (name, old[:7], now[name][:7], drift.commit_count(name, old, now[name])))
        else:
            lines.append("%s: first review at %s" % (name, now[name][:7]))
    state = {"from": {n: previous.get(n) for n in drift.REPOS}, "to": now}
    drift.emit(
        {
            "outcome": "pass",
            "title": "Review plugin skills: %s moved" % " and ".join(moved),
            "description": "\n".join(lines),
            "state": json.dumps(state, sort_keys=True),
        }
    )


if __name__ == "__main__":
    main()
