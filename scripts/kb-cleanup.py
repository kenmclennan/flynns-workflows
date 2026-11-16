#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import safe_run

proc = safe_run.run(["git", "status", "--porcelain"])
if proc.returncode != 0:
    print(f"git status failed: {proc.stderr.strip()}", file=sys.stderr)
    sys.exit(1)

dirty = [line[3:] for line in proc.stdout.splitlines() if line.strip()]
if dirty:
    print(
        "the worktree has uncommitted changes and is left in place: " + ", ".join(dirty),
        file=sys.stderr,
    )
    sys.exit(1)

print(json.dumps({"outcome": "done", "note": "worktree clean"}))
