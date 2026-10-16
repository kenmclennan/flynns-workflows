#!/usr/bin/env python3
import datetime
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import triage_state

FIELDS = "number,title,author,url,body,labels,updatedAt"


RULE = re.compile(r"^([-*_])(\s*\1){2,}$")
LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
EMPHASIS = re.compile(r"(\*\*|~~|`)|(?<!\w)(__|_)(?=\S)|(?<=\S)(__|_)(?!\w)|\*")


def summary(body):
    text = re.sub(r"<!--.*?-->", "", body or "", flags=re.DOTALL)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or RULE.match(line):
            continue
        line = EMPHASIS.sub("", LINK.sub(r"\1", line)).strip()
        if line:
            return line[:120]
    return "(no description)"


def fetch(gh, repo, since):
    cmd = [
        gh, "issue", "list", "--repo", repo, "--state", "open",
        "--search", "updated:>=" + since, "--limit", "100", "--json", FIELDS,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write("gh failed for %s (exit %d): %s\n" % (repo, proc.returncode, proc.stderr))
        sys.exit(1)
    return json.loads(proc.stdout or "[]")


def main():
    repos = triage_state.config_list("repos", triage_state.DEFAULT_REPOS)
    labels = {l.lower() for l in triage_state.config_list("labels")}
    ignored = {a.lower() for a in triage_state.config_list("ignore-authors")}
    lookback = int(triage_state.config("lookback-days", "14"))
    gh = triage_state.config("gh-command", "gh")

    conn = triage_state.connect()
    triage_state.migrate(conn)
    raised = {(r, n) for r, n in conn.execute("SELECT repo, number FROM raised")}
    marks = dict(conn.execute("SELECT repo, high_water FROM marks"))
    conn.close()

    default_since = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=lookback)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    new = []
    new_marks = {}
    for repo in repos:
        issues = fetch(gh, repo, marks.get(repo, default_since))
        for issue in issues:
            updated = issue.get("updatedAt") or ""
            if updated and updated > new_marks.get(repo, ""):
                new_marks[repo] = updated
            author = ((issue.get("author") or {}).get("login") or "")
            issue_labels = {(l.get("name") or "").lower() for l in issue.get("labels") or []}
            if (repo, issue["number"]) in raised:
                continue
            if author.lower() in ignored:
                continue
            if labels and not labels & issue_labels:
                continue
            new.append((repo, issue, author))

    if not new:
        triage_state.emit({"outcome": "fail", "note": "no new issues"})
        return

    lines = []
    for repo in repos:
        group = sorted((i for r, i, _ in new if r == repo), key=lambda i: i["number"])
        if not group:
            continue
        lines.append("%s" % repo)
        authors = {(i["number"]): a for r, i, a in new if r == repo}
        for i in group:
            lines.append(
                "- [%s#%d](%s) %s - @%s - %s"
                % (repo, i["number"], i["url"], i["title"], authors[i["number"]], summary(i.get("body")))
            )
        lines.append("")

    repo_count = len({r for r, _, _ in new})
    state = {
        "issues": [{"repo": r, "number": i["number"]} for r, i, _ in new],
        "marks": new_marks,
    }
    triage_state.emit(
        {
            "outcome": "pass",
            "title": "Triage %d new GitHub issue(s) on %d repo(s)" % (len(new), repo_count),
            "description": "\n".join(lines).rstrip(),
            "state": json.dumps(state, sort_keys=True),
        }
    )


if __name__ == "__main__":
    main()
