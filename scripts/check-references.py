#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import drift


def main():
    try:
        stdin = json.load(sys.stdin)
        state = drift.parse_state(stdin.get("schedule_state"))
    except (ValueError, AttributeError) as exc:
        sys.stderr.write("schedule_state is not a valid from/to object: %r\n" % (exc,))
        sys.exit(1)
    if not all(state["to"].get(n) for n in drift.REPOS):
        sys.stderr.write("schedule_state names no SHA for one of the repos; nothing to check\n")
        sys.exit(1)

    try:
        roots = {n: drift.snapshot(n, state["to"][n]) for n in drift.REPOS}
    except RuntimeError as exc:
        sys.stderr.write("%s\n" % exc)
        sys.exit(1)

    skills = drift.skills_path()
    if not os.path.isdir(os.path.join(roots["plugin"], skills)):
        sys.stderr.write("skills path %s is not in the plugin at %s\n" % (skills, state["to"]["plugin"]))
        sys.exit(1)

    misses = drift.find_misses(roots["plugin"], skills, drift.Index(roots))

    context = []
    for name in drift.REPOS:
        old = state["from"].get(name)
        context.append("%s: snapshot %s" % (name, roots[name]))
        context.append("  bare clone %s" % drift.clone_path(name))
        context.append("  from %s to %s" % (old or "(first review)", state["to"][name]))
        if old:
            context.append("  changed files: git --git-dir %s diff --stat %s %s" % (drift.clone_path(name), old, state["to"][name]))
            context.append("  diff: git --git-dir %s diff %s %s" % (drift.clone_path(name), old, state["to"][name]))
    context.append("skills: %s" % os.path.join(roots["plugin"], skills))

    drift.emit(
        {
            "outcome": "misses" if misses else "clean",
            "artifacts": {
                "missing-references": "\n".join(misses) if misses else "none",
                "review-context": "\n".join(context),
            },
        }
    )


if __name__ == "__main__":
    main()
