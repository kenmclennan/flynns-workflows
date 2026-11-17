#!/usr/bin/env python3
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import safe_run
import triage_state

FIELDS = "number,title,author,url,body,labels,updatedAt,comments"
LC_MARKER = "<!-- lc -->"


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


def new_comments(issue, floor, ignored):
    kept = []
    for comment in issue.get("comments") or []:
        created = comment.get("createdAt") or ""
        login = ((comment.get("author") or {}).get("login") or "")
        if created <= floor or login.lower() in ignored:
            continue
        if (comment.get("body") or "").lstrip().startswith(LC_MARKER):
            continue
        kept.append((login or "unknown", created, summary(comment.get("body"))))
    return sorted(kept, key=lambda c: c[1])


def fetch(gh, repo, since):
    cmd = [
        gh, "issue", "list", "--repo", repo, "--state", "open",
        "--search", "updated:>=" + since, "--limit", "100", "--json", FIELDS,
    ]
    proc = safe_run.run(cmd, network=True)
    if proc.returncode != 0:
        sys.stderr.write("gh failed for %s (exit %d): %s\n" % (repo, proc.returncode, proc.stderr))
        sys.exit(1)
    return json.loads(proc.stdout or "[]")


COMMENT_CAP = 100
NEWEST_COMMENTS = (
    "query($owner: String!, $name: String!, $number: Int!) { repository(owner: $owner, name: $name) "
    "{ issue(number: $number) { comments(last: 100) { nodes { createdAt body author { login } } } } } }"
)


def newest_comments(gh, repo, number):
    owner, name = repo.split("/", 1)
    cmd = [
        gh, "api", "graphql", "-f", "query=" + NEWEST_COMMENTS,
        "-f", "owner=" + owner, "-f", "name=" + name, "-F", "number=%d" % number,
    ]
    proc = safe_run.run(cmd, network=True)
    if proc.returncode != 0:
        sys.stderr.write("gh graphql failed for %s#%d (exit %d): %s\n" % (repo, number, proc.returncode, proc.stderr))
        sys.exit(1)
    data = json.loads(proc.stdout or "{}")
    return (((data.get("data") or {}).get("repository") or {}).get("issue") or {}).get("comments", {}).get("nodes") or []


def main():
    repos = triage_state.require_config_list("repos")
    labels = {l.lower() for l in triage_state.config_list("labels")}
    ignored = {a.lower() for a in triage_state.config_list("ignore-authors")}
    lookback = triage_state.require_config("lookback-days", int)
    gh = triage_state.require_config("gh-command")

    conn = triage_state.connect()
    triage_state.migrate(conn)
    floors = {
        (r, n): floor
        for r, n, floor in conn.execute(
            "SELECT r.repo, r.number, COALESCE(c.high_water, r.raised_at) FROM raised r "
            "LEFT JOIN comment_marks c ON c.repo = r.repo AND c.number = r.number"
        )
    }
    marks = dict(conn.execute("SELECT repo, high_water FROM marks"))
    conn.close()

    default_since = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=lookback)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    new = []
    commented = []
    new_marks = {}
    for repo in repos:
        issues = fetch(gh, repo, min(marks.get(repo, default_since), default_since))
        for issue in issues:
            updated = issue.get("updatedAt") or ""
            if updated and updated > new_marks.get(repo, ""):
                new_marks[repo] = updated
            author = ((issue.get("author") or {}).get("login") or "")
            issue_labels = {(l.get("name") or "").lower() for l in issue.get("labels") or []}
            floor = floors.get((repo, issue["number"]))
            if floor is not None:
                if len(issue.get("comments") or []) >= COMMENT_CAP:
                    issue["comments"] = newest_comments(gh, repo, issue["number"])
                kept = new_comments(issue, floor, ignored)
                if kept:
                    commented.append((repo, issue, kept))
                continue
            if author.lower() in ignored:
                continue
            if labels and not labels & issue_labels:
                continue
            new.append((repo, issue, author))

    if not new and not commented:
        triage_state.emit({"outcome": "fail", "note": "no new issues or comments"})
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

    if commented:
        lines.append("New comments")
        for repo in repos:
            group = sorted((c for c in commented if c[0] == repo), key=lambda c: c[1]["number"])
            if not group:
                continue
            lines.append("%s" % repo)
            for _, i, kept in group:
                lines.append("- [%s#%d](%s) %s" % (repo, i["number"], i["url"], i["title"]))
                for login, created, text in kept:
                    lines.append("  - @%s %s - %s" % (login, created, text))
            lines.append("")

    if new and commented:
        title = "Triage %d new GitHub issue(s) on %d repo(s), %d with new comments" % (
            len(new), len({r for r, _, _ in new}), len(commented))
    elif commented:
        title = "Triage 0 new GitHub issue(s), %d with new comments" % len(commented)
    else:
        title = "Triage %d new GitHub issue(s) on %d repo(s)" % (len(new), len({r for r, _, _ in new}))

    state = {
        "issues": [{"repo": r, "number": i["number"]} for r, i, _ in new],
        "marks": new_marks,
        "comments": [
            {"repo": r, "number": i["number"], "mark": max(c[1] for c in kept)}
            for r, i, kept in commented
        ],
    }
    triage_state.emit(
        {
            "outcome": "pass",
            "title": title,
            "description": "\n".join(lines).rstrip(),
            "state": json.dumps(state, sort_keys=True),
        }
    )


if __name__ == "__main__":
    main()
