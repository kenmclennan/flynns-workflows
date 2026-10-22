#!/usr/bin/env python3
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import delivered
import delivered_state as ds


def list_issues(gh, repo):
    cmd = [gh, "issue", "list", "--repo", repo, "--state", "open", "--limit", "200",
           "--json", "number,title,url"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        delivered.fail("gh failed for %s (exit %d): %s" % (repo, proc.returncode, proc.stderr))
    return json.loads(proc.stdout or "[]")


def section(heading, entries, repos):
    lines = [heading]
    for repo in repos:
        group = sorted((e for e in entries if e["repo"] == repo), key=lambda e: e["number"])
        if not group:
            continue
        lines.append(repo)
        for e in group:
            issue = e["issue"]
            lines.append(
                "- [%s#%d](%s) %s - %s"
                % (repo, e["number"], issue["url"], issue["title"],
                   "; ".join(delivered.describe(i, repo) for i in e["items"]))
            )
    return lines


def main():
    repos = ds.config_list("repos", ds.DEFAULT_REPOS)
    gh = ds.config("gh-command", "gh")
    lc = ds.config("lc-command", "lc")

    conn = ds.connect()
    ds.migrate(conn)
    shown = {(r, n): f for r, n, f in conn.execute("SELECT repo, number, fingerprint FROM shown")}
    conn.close()

    proposed = []
    look = []
    for repo in repos:
        for issue in list_issues(gh, repo):
            items = delivered.referencing_items(lc, repo, issue["number"])
            if not items:
                continue
            fp = delivered.fingerprint(items)
            if shown.get((repo, issue["number"])) == fp:
                continue
            entry = {"repo": repo, "number": issue["number"], "issue": issue,
                     "items": items, "fingerprint": fp}
            (proposed if delivered.classify(items) == "proposed" else look).append(entry)

    if not proposed and not look:
        ds.emit({"outcome": "fail", "note": "nothing new to propose"})
        return

    lines = [
        "To close issues, attach the approved set and finish the gate step: "
        "lc attach STEP approved '{\"issues\": [\"owner/repo#N\"]}' --replace, "
        "then lc done STEP approved. To close nothing, attach an empty set and lc done STEP declined.",
        "",
    ]
    lines += section("Proposed closes", proposed, repos)
    lines.append("")
    lines += section("Needs a look", look, repos)
    state = {
        "shown": [
            {"repo": e["repo"], "number": e["number"], "fingerprint": e["fingerprint"]}
            for e in proposed + look
        ]
    }
    ds.emit(
        {
            "outcome": "pass",
            "title": "Propose closing %d delivered GitHub issue(s); %d need a look"
            % (len(proposed), len(look)),
            "description": "\n".join(lines).rstrip(),
            "state": json.dumps(state, sort_keys=True),
        }
    )


if __name__ == "__main__":
    main()
