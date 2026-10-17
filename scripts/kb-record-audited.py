#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import kb_audit
import kb_audit_state


def main():
    try:
        stdin = json.load(sys.stdin)
    except ValueError as exc:
        sys.stderr.write("stdin is not JSON: %s\n" % exc)
        sys.exit(1)
    sha = (stdin.get("schedule_state") or "").strip()
    if not kb_audit.valid_sha(sha):
        sys.stderr.write("schedule_state is missing or is not a commit sha; nothing to record\n")
        sys.exit(1)
    try:
        kb_audit_state.write_sha(sha)
    except OSError as exc:
        sys.stderr.write("could not record the audited sha: %s\n" % exc)
        sys.exit(1)
    kb_audit.emit({"outcome": "recorded"})


if __name__ == "__main__":
    main()
