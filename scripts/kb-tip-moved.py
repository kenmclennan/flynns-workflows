#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import kb_audit
import kb_audit_state


def main():
    url = kb_audit.require_config("knowledgebase-url")
    try:
        tip = kb_audit.tip_sha(url)
        last = kb_audit_state.read_sha()
    except RuntimeError as exc:
        sys.stderr.write("%s\n" % exc)
        sys.exit(1)

    if tip == last:
        kb_audit.emit({"outcome": "fail", "note": "tip unchanged"})
        return

    if last is None:
        detail = "first audit"
    else:
        try:
            kb_audit.ensure_clone(url)
            count = kb_audit.commit_count(last, tip)
        except RuntimeError:
            count = None
        detail = (
            "%s commit(s) since %s" % (count, last[:7]) if count is not None
            else "commits since %s could not be counted" % last[:7]
        )
    kb_audit.emit(
        {
            "outcome": "pass",
            "title": "Audit the knowledgebase at %s" % tip[:7],
            "description": "Knowledgebase main is at %s: %s." % (tip[:7], detail),
            "state": tip,
        }
    )


if __name__ == "__main__":
    main()
