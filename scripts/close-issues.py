#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import delivered
import delivered_state as ds
import scout_state

REF = re.compile(r"^([^/\s]+/[^#\s]+)#(\d+)$")


def load_approved(stdin):
    raw = scout_state.read_artifact(stdin, "approved")
    if raw is None:
        delivered.fail("no approved artifact on the item; the gate closed without one")
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        refs = [str(r) for r in data["issues"]]
    except (ValueError, KeyError, TypeError) as exc:
        delivered.fail("approved is not an object with an issues list: %r" % (exc,))
    parsed = []
    for ref in refs:
        match = REF.match(ref)
        if not match:
            delivered.fail("%r is not an owner/repo#N reference" % ref)
        parsed.append((match.group(1), int(match.group(2))))
    return parsed


def is_open(gh, repo, number):
    out = delivered.run([gh, "issue", "view", str(number), "--repo", repo, "--json", "state"])
    return str(json.loads(out).get("state", "")).upper() == "OPEN"


def main():
    try:
        stdin = json.load(sys.stdin)
    except ValueError as exc:
        delivered.fail("stdin is not JSON: %s" % exc)
    approved = load_approved(stdin)
    gh = ds.config("gh-command", "gh")
    lc = ds.config("lc-command", "lc")

    closed = []
    skipped = []
    for repo, number in approved:
        ref = "%s#%d" % (repo, number)
        items = delivered.referencing_items(lc, repo, number)
        if not items:
            skipped.append("%s (no referencing item)" % ref)
            continue
        if delivered.classify(items) != "proposed":
            skipped.append("%s (no longer a proposed close)" % ref)
            continue
        if not is_open(gh, repo, number):
            skipped.append("%s (already closed)" % ref)
            continue
        proc = subprocess.run(
            [gh, "issue", "close", str(number), "--repo", repo,
             "--comment", delivered.comment(items, repo)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            delivered.fail("gh issue close %s failed (exit %d): %s" % (ref, proc.returncode, proc.stderr))
        closed.append("%s (%s)" % (ref, ", ".join(i["id"] for i in items)))

    note = "Closed: %s." % ("; ".join(closed) if closed else "none")
    if skipped:
        note += " Skipped: %s." % "; ".join(skipped)
    ds.emit({"outcome": "closed", "note": note})


if __name__ == "__main__":
    main()
