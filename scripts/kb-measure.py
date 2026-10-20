#!/usr/bin/env python3
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import kb_audit
import kb_audit_state


def today():
    override = os.environ.get("KB_AUDIT_TODAY")
    return datetime.date.fromisoformat(override) if override else datetime.date.today()


def main():
    try:
        stdin = json.load(sys.stdin)
    except ValueError as exc:
        sys.stderr.write("stdin is not JSON: %s\n" % exc)
        sys.exit(1)
    sha = (stdin.get("schedule_state") or "").strip()
    if not kb_audit.valid_sha(sha):
        sys.stderr.write("schedule_state is missing or is not a commit sha; nothing to measure\n")
        sys.exit(1)
    url = kb_audit.require_config("knowledgebase-url")
    try:
        min_links = int(kb_audit.require_config("min-cross-topic-links"))
    except ValueError:
        sys.stderr.write("config key min-cross-topic-links must be a whole number\n")
        sys.exit(1)

    try:
        kb_audit.ensure_clone(url)
        root = kb_audit.export_snapshot(sha)
        defects = kb_audit.measure(root, min_links, today())
        shown = defects if os.environ.get("KB_AUDIT_PER_FILE") else kb_audit.group_by_topic(defects, min_links)
        tools = not os.environ.get("KB_AUDIT_SKIP_TOOLS")
        prettier, lint = kb_audit.tool_counts(root) if tools else ({}, {})
        previous = kb_audit_state.read_sha()
    except (RuntimeError, OSError) as exc:
        sys.stderr.write("%s\n" % exc)
        sys.exit(1)

    context = [
        "snapshot: %s" % root,
        "sha: %s" % sha,
        "previously audited: %s" % (previous or "first audit"),
    ]
    kb_audit.emit(
        {
            "outcome": "measured",
            "artifacts": {
                "measurements": kb_audit.render(shown, prettier, lint, tools),
                "review-context": "\n".join(context),
            },
            "note": "%d defect(s)" % len(defects),
        }
    )


if __name__ == "__main__":
    main()
