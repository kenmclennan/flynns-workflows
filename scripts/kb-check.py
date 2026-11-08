#!/usr/bin/env python3
import json
import os
import posixpath
import re
import subprocess
import sys

BASE = os.environ.get("KB_CHECK_BASE", "origin/main")
RESERVED = ("index.md", "log.md")
LINK = re.compile(r"(?<!!)\[(?:[^\[\]]|\[[^\]]*\])*\]\((?:<([^>\n]+)>|([^)\s<]+))(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s*(```+|~~~+)")


def git(*args):
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write("git %s failed: %s\n" % (" ".join(args), proc.stderr.strip()))
        sys.exit(1)
    return proc.stdout


def changed_files():
    base = git("merge-base", BASE, "HEAD").strip()
    tracked = git("diff", "--name-only", "--diff-filter=AMR", base, "--", "*.md").split("\n")
    fresh = git("ls-files", "--others", "--exclude-standard", "--", "*.md").split("\n")
    return sorted({p for p in tracked + fresh if p})


def split_frontmatter(text):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end == -1:
        return None, text
    return text[4:end], text[end + 4:].lstrip("\n")


def top_level_keys(front):
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^([A-Za-z_][\w-]*):[ \t]*(.*)$", front, re.M)}


def source_resources(front):
    block = re.search(r"^sources:[ \t]*\n((?:[ \t]+.*\n?|\n)*)", front + "\n", re.M)
    if not block:
        return []
    return [m.group(1).strip().strip("\"'") for m in re.finditer(r"^\s*-?\s*resource:\s*(.+)$", block.group(1), re.M)]


def address_paths(front):
    match = re.search(r"^addresses:[ \t]*(.*)$", front, re.M)
    if not match:
        return []
    rest = match.group(1).strip()
    if not rest and front[match.end():].lstrip().startswith("["):
        rest = "["
    if rest.startswith("["):
        start = front.index("[", match.start(1))
        end = front.find("]", start)
        raw = front[start + 1:end if end != -1 else len(front)].split(",")
    elif rest:
        raw = [rest]
    else:
        raw = []
        for line in front[match.end():].split("\n"):
            item = re.match(r"^[ \t]*-[ \t]*(.+)$", line)
            if item:
                raw.append(item.group(1))
            elif line.strip():
                break
    return [r.strip().strip("\"'").strip() for r in raw if r.strip().strip("\"'").strip()]


def resolve_address(path, target):
    for candidate in (resolve(path, target), posixpath.normpath(target)):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def is_problem(path):
    front, _ = split_frontmatter(read(path))
    return front is not None and top_level_keys(front).get("type", "").strip("\"'") == "Problem"


def responds_list(path):
    _, body = split_frontmatter(read(path))
    section = re.search(r"^##[ \t]+What responds to it[ \t]*$(.*?)(?=^##[ \t]|\Z)", body, re.M | re.S)
    if not section:
        return set()
    return {t for t in (resolve(path, link) for link in body_links(section.group(1))) if t}


def all_docs():
    found = []
    for root, dirs, names in os.walk("."):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
        for item in names:
            if item.endswith(".md"):
                found.append(posixpath.normpath(os.path.join(root, item).replace(os.sep, "/")))
    return sorted(found)


def addressing_map():
    mapping = {}
    for path in all_docs():
        if posixpath.basename(path) in RESERVED or path.startswith("references/"):
            continue
        front, _ = split_frontmatter(read(path))
        for target in address_paths(front or ""):
            resolved = resolve_address(path, target)
            if resolved:
                mapping.setdefault(resolved, set()).add(path)
    return mapping


def problem_failures(files, addressed):
    problems = set()
    for path in files:
        if path.startswith("references/") or posixpath.basename(path) in RESERVED:
            continue
        if is_problem(path):
            problems.add(path)
        front, _ = split_frontmatter(read(path))
        for target in address_paths(front or ""):
            resolved = resolve_address(path, target)
            if resolved and is_problem(resolved):
                problems.add(resolved)
    failures = []
    for problem in sorted(problems):
        listed, addressing = responds_list(problem), addressed.get(problem, set())
        for extra in sorted(listed - addressing):
            failures.append("%s: lists %s under \"What responds to it\" but that doc does not address it" % (problem, extra))
        for missing in sorted(addressing - listed):
            failures.append("%s: %s addresses it but is not listed under \"What responds to it\"" % (problem, missing))
    return failures


def body_links(body):
    links, fenced = [], False
    for line in body.split("\n"):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            links.extend(m.group(1) or m.group(2) for m in LINK.finditer(re.sub(r"`[^`]*`", "", line)))
    return links


def resolve(path, target):
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
        return None
    return posixpath.normpath(posixpath.join(posixpath.dirname(path), target))


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def reachable_from_root():
    seen, queue = set(), ["index.md"] if os.path.exists("index.md") else []
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        if not current.endswith(".md") or not os.path.isfile(current):
            continue
        _, body = split_frontmatter(read(current))
        for link in body_links(body):
            if link.startswith("/"):
                continue
            target = resolve(current, link)
            if target and target not in seen:
                queue.append(target)
    return seen


def tool_findings(name, command, files):
    try:
        proc = subprocess.run(command + files, capture_output=True, text=True)
    except FileNotFoundError:
        sys.stderr.write("%s needs `npx`, which is not on PATH\n" % name)
        sys.exit(1)
    if proc.returncode == 0:
        return []
    if proc.returncode != 1:
        sys.stderr.write("%s failed to run (exit %d): %s\n" % (name, proc.returncode, (proc.stderr or proc.stdout)[-400:]))
        sys.exit(1)
    return ["%s: %s" % (name, line.strip()) for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]


def check(files):
    failures = []
    reachable = reachable_from_root()
    for path in files:
        name = posixpath.basename(path)
        front, body = split_frontmatter(read(path))
        if name in RESERVED:
            if front is not None and not (path == "index.md" and set(top_level_keys(front)) <= {"okf_version"}):
                failures.append("%s: reserved file carries frontmatter, which belongs only to concept docs" % path)
        else:
            keys = top_level_keys(front) if front is not None else {}
            if not keys.get("type", "").strip("\"'"):
                failures.append("%s: frontmatter is missing or has no `type`" % path)
            if path.startswith("references/"):
                for key in ("resource", "retrieved_at"):
                    if not keys.get(key):
                        failures.append("%s: reference frontmatter is missing `%s`" % (path, key))
        if path.startswith("references/"):
            continue
        linked = set()
        for link in body_links(body):
            if link.startswith("/"):
                failures.append("%s: link %s is bundle-absolute; use a relative link" % (path, link))
                continue
            target = resolve(path, link)
            if target is None:
                continue
            linked.add(target)
            if not os.path.exists(target):
                failures.append("%s: relative link %s does not resolve" % (path, link))
        if name not in RESERVED:
            if path not in reachable:
                failures.append("%s: not reachable from index.md by following links" % path)
            for target in address_paths(front or ""):
                if not resolve_address(path, target):
                    failures.append("%s: addresses %s does not resolve" % (path, target))
            for resource in source_resources(front or ""):
                cited = [c for c in (posixpath.normpath(resource), resolve(path, resource)) if c and c.startswith("references/") and os.path.exists(c)]
                if cited and not set(cited) & linked:
                    failures.append("%s: cites %s in `sources` but does not link it in the body" % (path, cited[0]))
    failures += problem_failures(files, addressing_map())
    return failures


def main():
    json.load(sys.stdin)
    root = git("rev-parse", "--show-toplevel").strip()
    os.chdir(root)
    files = [p for p in changed_files() if os.path.isfile(p)]
    failures = check(files)
    if files and not os.environ.get("KB_CHECK_SKIP_TOOLS"):
        failures += tool_findings("prettier", ["npx", "--yes", "prettier", "--prose-wrap=never", "--check"], files)
        failures += tool_findings("markdownlint", ["npx", "--yes", "markdownlint-cli2"], files)
    if failures:
        out = {"outcome": "broken", "artifacts": {"check-report": "\n".join(failures)}, "note": "%d failure(s) in %d file(s)" % (len(failures), len(files))}
    else:
        out = {"outcome": "clean", "note": "%d file(s) checked" % len(files)}
    sys.stdout.write(json.dumps(out) + "\n")


if __name__ == "__main__":
    main()
