import datetime
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile

from kb_doc import address_paths, body_links, resolve, resolve_address, source_resources, split_frontmatter, top_level_keys

import kb_audit_state
import workflow_config

RESERVED = ("index.md", "log.md")
HEADING = re.compile(r"^#+\s+(.*)$")
BACKTICKED_MD = re.compile(r"`([^`\s]+\.md)`")
GROUPED = ("related-overflow", "citation-without-link")
RELATED_MAX = 8
RELATED = re.compile(r"^##[ \t]+Related[ \t]*$(.*?)(?=^##[ \t]|\Z)", re.M | re.S)
RESPONDS = re.compile(r"^##[ \t]+What responds to it[ \t]*$(.*?)(?=^##[ \t]|\Z)", re.M | re.S)
EXAMPLES = 5
MD_ERROR = re.compile(r"^(?:\./)?(\S[^:]*\.md):\d+")
CHUNK = 200
NUMBER_WORDS = ("two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty").split()
COUNTING_NOUNS = "techniques? concepts? entry entries docs? documents? patterns? pages?".split()
NUMBER = re.compile(r"\b(\d+|%s)(?=\s+(?:%s)\b)" % ("|".join(NUMBER_WORDS), "|".join(COUNTING_NOUNS)), re.I)
INDEX_ENTRY = re.compile(r"^\s*[-*]\s+\[[^\]]*\]\((?:<([^>\n]+)>|([^)\s<]+))\)\s*(.*)$")
SHA = re.compile(r"^[0-9a-f]{7,64}$")


def data_dir():
    return kb_audit_state.data_dir()


config = workflow_config.config
require_config = workflow_config.require_config


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def clone_path():
    return os.path.join(data_dir(), "kb.git")


def snapshot_path():
    return os.path.join(data_dir(), "snapshot")


def git(*args, git_dir=None, check=True):
    cmd = ["git"]
    if git_dir:
        cmd += ["--git-dir", git_dir]
    cmd += list(args)
    proc = subprocess.run(cmd, capture_output=True, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if check and proc.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), proc.stderr.decode(errors="replace").strip()))
    return proc


def tip_sha(url):
    out = git("ls-remote", url, "refs/heads/main").stdout.decode().split()
    if not out:
        raise RuntimeError("%s has no refs/heads/main" % url)
    return out[0]


def ensure_clone(url):
    path = clone_path()
    if not os.path.isdir(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        git("clone", "--bare", "--quiet", url, path)
    current = git("remote", "get-url", "origin", git_dir=path, check=False).stdout.decode().strip()
    if current != url:
        git("remote", "set-url", "origin", url, git_dir=path)
    git("fetch", "--quiet", "origin", "+main:main", git_dir=path)
    return path


def commit_count(old, new):
    proc = git("rev-list", "--count", "%s..%s" % (old, new), git_dir=clone_path(), check=False)
    return proc.stdout.decode().strip() if proc.returncode == 0 else None


def export_snapshot(sha):
    dest = snapshot_path()
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    data = git("archive", "--format=tar", sha, git_dir=clone_path()).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)
    return dest


def markdown_files(root):
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "node_modules")
        for name in sorted(files):
            if name.endswith(".md"):
                found.append(os.path.relpath(os.path.join(base, name), root).replace(os.sep, "/"))
    return found


def is_reference(path):
    return path.startswith("references/")


def is_concept(path, excluded=()):
    return not is_reference(path) and posixpath.basename(path) not in RESERVED and posixpath.basename(path) != "CLAUDE.md" and path not in excluded


def schema_files(root, docs):
    path = os.path.join(root, "CLAUDE.md")
    if not os.path.isfile(path):
        return set()
    named, active = set(), False
    with open(path, encoding="utf-8") as handle:
        for line in handle.read().split("\n"):
            heading = HEADING.match(line)
            if heading:
                active = bool(re.search(r"schema|tooling", heading.group(1), re.I))
            elif active:
                named.update(posixpath.normpath(m) for m in BACKTICKED_MD.findall(line) if posixpath.normpath(m) in docs)
    return named


def topic_of(path):
    parts = path.split("/")
    if len(parts) < 2 or parts[0] == "references":
        return None
    return parts[0]


def related_count(body):
    section = RELATED.search(body)
    if not section:
        return 0
    return sum(1 for line in section.group(1).split("\n") if re.match(r"^[-*][ \t]", line))


def responds_targets(path, body):
    section = RESPONDS.search(body)
    if not section:
        return set()
    return {t for t in (resolve(path, link) for link in body_links(section.group(1))) if t}


def load(root):
    docs = {}
    for path in markdown_files(root):
        with open(os.path.join(root, path), encoding="utf-8") as handle:
            front, body = split_frontmatter(handle.read())
        keys = top_level_keys(front, unquote=True) if front is not None else {}
        links = []
        if not is_reference(path):
            for link in body_links(body):
                target = resolve(path, link)
                if target:
                    links.append((link, target))
        docs[path] = {
            "keys": keys,
            "sources": source_resources(front or ""),
            "links": links,
            "addresses": address_paths(front or ""),
            "related": related_count(body),
            "responds": responds_targets(path, body),
        }
    return docs


def reachable(docs):
    seen = set()
    queue = [p for p in docs if posixpath.basename(p) == "index.md"]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        for _, target in docs.get(current, {}).get("links", []):
            if target in docs and target not in seen:
                queue.append(target)
    return seen


def cited_by_sources(path, doc, root):
    cited = []
    for resource in doc["sources"]:
        found = [c for c in (posixpath.normpath(resource), resolve(path, resource)) if c and is_reference(c) and os.path.exists(os.path.join(root, c))]
        if found:
            cited.append(found[0])
    return cited


def number_value(token):
    token = token.lower()
    return int(token) if token.isdigit() else NUMBER_WORDS.index(token) + 2


def index_count_defects(root, docs, excluded):
    path = os.path.join(root, "index.md")
    if not os.path.isfile(path):
        return []
    found = []
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    for line in lines:
        entry = INDEX_ENTRY.match(line)
        if not entry:
            continue
        target = resolve("index.md", entry.group(1) or entry.group(2))
        if not target or posixpath.basename(target) != "index.md" or posixpath.dirname(target) in ("", "."):
            continue
        topic = topic_of(target)
        if not topic:
            continue
        count = sum(1 for p in docs if topic_of(p) == topic and is_concept(p, excluded))
        for token in NUMBER.findall(entry.group(3)):
            if number_value(token) != count:
                found.append(("index-count", "index.md", "%s: blurb says %s, topic has %d concept docs" % (topic, token, count)))
    return found


def addresses_defects(docs, excluded):
    found, addressing = [], {}
    for path, doc in docs.items():
        if not is_concept(path, excluded):
            continue
        for target in doc["addresses"]:
            resolved = resolve_address(path, target, docs.__contains__)
            if resolved:
                addressing.setdefault(resolved, set()).add(path)
            else:
                found.append(("addresses-unresolved", path, "addresses %s does not resolve" % target))
    for path, doc in sorted(docs.items()):
        if not is_concept(path, excluded) or doc["keys"].get("type") != "Problem":
            continue
        listed, addressed = doc["responds"], addressing.get(path, set())
        for missing in sorted(addressed - listed):
            found.append(("addresses-unlisted", path, '%s addresses it but is not listed under "What responds to it"' % missing))
        for extra in sorted(listed - addressed):
            found.append(("addresses-unaddressed", path, 'lists %s under "What responds to it" but that doc does not address it' % extra))
    return found


def measure(root, today):
    docs = load(root)
    excluded = schema_files(root, docs)
    out = []

    for path, doc in docs.items():
        for link, target in doc["links"]:
            if not os.path.exists(os.path.join(root, target)):
                out.append(("unresolved-link", path, link))

    seen = reachable(docs)
    for path in docs:
        if is_concept(path, excluded) and path not in seen:
            out.append(("unreachable-doc", path, "no index.md reaches it by following links"))

    topics = sorted({topic_of(p) for p in docs if topic_of(p)})
    connected = set()
    for path, doc in docs.items():
        mine = topic_of(path)
        if not mine:
            continue
        targets = {t for _, t in doc["links"] if t in docs and topic_of(t) and topic_of(t) != mine}
        for target in targets:
            connected.add(mine)
            connected.add(topic_of(target))
    islands = [t for t in topics if t not in connected]
    for topic in islands:
        out.append(("island-topic", topic, "no link in or out to another topic"))

    for path, doc in docs.items():
        if is_concept(path, excluded) and doc["related"] > RELATED_MAX:
            out.append(("related-overflow", path, "%d Related entries, more than %d" % (doc["related"], RELATED_MAX)))

    out.extend(addresses_defects(docs, excluded))

    cited = set()
    for path, doc in docs.items():
        if is_reference(path):
            continue
        cited.update(t for _, t in doc["links"])
        cited.update(cited_by_sources(path, doc, root))
    for path in docs:
        if is_reference(path) and posixpath.basename(path) not in RESERVED and path not in cited:
            out.append(("uncited-reference", path, "no concept doc cites it"))

    for path, doc in docs.items():
        if not is_concept(path, excluded):
            continue
        linked = {t for _, t in doc["links"]}
        for target in cited_by_sources(path, doc, root):
            if target not in linked:
                out.append(("citation-without-link", path, "cites %s in sources but does not link it" % target))

    out.extend(index_count_defects(root, docs, excluded))

    for path, doc in docs.items():
        value = doc["keys"].get("stale_after")
        if not value:
            continue
        try:
            due = datetime.date.fromisoformat(value[:10])
        except ValueError:
            continue
        if due < today:
            out.append(("stale", path, "stale_after %s has passed" % value[:10]))

    return out


def topic_label(path):
    path = path[2:] if path.startswith("./") else path
    return path.split("/", 1)[0] if "/" in path else "(root)"


def group_by_topic(defects, cap=EXAMPLES):
    groups, rest = {}, []
    for defect in defects:
        if defect[0] in GROUPED:
            groups.setdefault((defect[0], topic_label(defect[1])), []).append(defect[1])
        else:
            rest.append(defect)
    for (kind, topic), paths in sorted(groups.items()):
        paths = sorted(paths)
        if kind == "related-overflow":
            detail = "%d doc(s) have more than %d Related entries" % (len(paths), RELATED_MAX)
        else:
            detail = "%d doc(s) cite a references/ file without linking it" % len(paths)
        rest.append((kind, topic, "%s; e.g. %s" % (detail, ", ".join(paths[:cap]))))
    return rest


def prettier_counts(output):
    counts = {}
    for line in output.splitlines():
        line = line.strip()
        if line and line.endswith(".md"):
            label = topic_label(line)
            counts[label] = counts.get(label, 0) + 1
    return counts


def markdownlint_counts(output):
    counts = {}
    for line in output.splitlines():
        match = MD_ERROR.match(line.strip())
        if match:
            label = topic_label(match.group(1))
            counts[label] = counts.get(label, 0) + 1
    return counts


def run_tool(name, command, files, root):
    chunks = []
    for start in range(0, len(files), CHUNK):
        try:
            proc = subprocess.run(command + files[start:start + CHUNK], capture_output=True, text=True, cwd=root)
        except FileNotFoundError:
            raise RuntimeError("%s needs `npx`, which is not on PATH" % name) from None
        if proc.returncode not in (0, 1):
            raise RuntimeError("%s failed to run (exit %d): %s" % (name, proc.returncode, (proc.stderr or proc.stdout)[-400:]))
        chunks.append(proc.stdout + "\n" + proc.stderr)
    return "\n".join(chunks)


def tool_counts(root):
    files = markdown_files(root)
    prettier = prettier_counts(run_tool("prettier", ["npx", "--yes", "prettier", "--prose-wrap=never", "--list-different"], files, root))
    lint = markdownlint_counts(run_tool("markdownlint", ["npx", "--yes", "markdownlint-cli2"], files, root))
    return prettier, lint


def render(defects, prettier, lint, measured_tools):
    lines = ["%s: %s - %s" % d for d in defects] or ["no defects"]
    lines.append("")
    if not measured_tools:
        lines.append("formatting not measured")
    else:
        lines += ["prettier %s: %d file(s)" % (t, n) for t, n in sorted(prettier.items())]
        lines += ["markdownlint %s: %d error(s)" % (t, n) for t, n in sorted(lint.items())]
        if not prettier and not lint:
            lines.append("no formatting failures")
    return "\n".join(lines)


def valid_sha(value):
    return bool(value) and bool(SHA.match(value))
