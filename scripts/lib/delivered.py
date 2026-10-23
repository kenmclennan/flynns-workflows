import hashlib
import json
import re
import subprocess
import sys

EXCLUDED_WORKFLOWS = {"triage-github-issues", "close-delivered-issues"}
SEARCH_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9]*-[0-9][0-9.]*)\s")
PR_URL = re.compile(r"^https://github\.com/([^/]+/[^/]+)/pull/(\d+)")


def fail(message):
    sys.stderr.write(message + "\n")
    sys.exit(1)


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        fail("%s failed (exit %d): %s" % (" ".join(cmd[:3]), proc.returncode, proc.stderr))
    return proc.stdout


def issue_url(repo, number):
    return "https://github.com/%s/issues/%d" % (repo, number)


def mention_pattern(repo, number):
    url = re.escape(issue_url(repo, number))
    short = re.escape("%s#%d" % (repo, number))
    return re.compile("(?:%s|%s)(?!\\d)" % (url, short))


def search_ids(lc, text):
    ids = []
    for line in run([lc, "search", text]).splitlines():
        match = SEARCH_LINE.match(line)
        if match and match.group(1) not in ids:
            ids.append(match.group(1))
    return ids


def show(lc, item_id):
    try:
        return json.loads(run([lc, "show", item_id]))
    except ValueError as exc:
        fail("lc show %s is not JSON: %s" % (item_id, exc))


def workflow_name(item):
    return (item.get("workflow") or "").rsplit("/", 1)[-1].split("@", 1)[0]


def referencing_items(lc, repo, number):
    pattern = mention_pattern(repo, number)
    found = []
    candidates = search_ids(lc, issue_url(repo, number))
    for item_id in search_ids(lc, "%s#%d" % (repo, number)):
        if item_id not in candidates:
            candidates.append(item_id)
    for item_id in candidates:
        item = show(lc, item_id)
        if workflow_name(item) in EXCLUDED_WORKFLOWS:
            continue
        if pattern.search(item.get("description") or ""):
            found.append(item)
    return sorted(found, key=lambda i: i["id"])


def merged_prs(item):
    return [r["pr"] for r in item.get("runs") or [] if r.get("state") == "merged" and r.get("pr")]


def pr_label(url, issue_repo):
    match = PR_URL.match(url)
    if not match:
        return url
    repo, number = match.groups()
    return "#%s" % number if repo == issue_repo else "%s#%s" % (repo, number)


def item_status(item):
    state = item.get("state")
    disposition = item.get("disposition")
    prs = merged_prs(item)
    if state != "done":
        return False, "still open"
    if disposition != "completed":
        return False, disposition or "done, no disposition"
    if not prs:
        return False, "done, no merged PR"
    return True, "done, completed"


def in_flight(items):
    return any(i.get("state") != "done" for i in items)


def classify(items):
    return "proposed" if items and all(item_status(i)[0] for i in items) else "look"


def fingerprint(items):
    lines = sorted(
        "|".join(
            [i["id"], i.get("state") or "", i.get("disposition") or "", ",".join(merged_prs(i))]
        )
        for i in items
    )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def describe(item, issue_repo):
    ok, reason = item_status(item)
    if ok:
        prs = ", ".join(pr_label(p, issue_repo) for p in merged_prs(item))
        return "%s (%s) PR %s" % (item["id"], reason, prs)
    return "%s %s" % (item["id"], reason)


def comment(items, issue_repo):
    parts = []
    for item in items:
        prs = ", ".join(pr_label(p, issue_repo) for p in merged_prs(item))
        parts.append("Fixed by %s (%s): %s." % (prs, item["id"], item.get("title") or ""))
    return " ".join(parts)
