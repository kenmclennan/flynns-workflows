import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys

LAYOUT_VERSION = 1
REPOS = ("engine", "workflows", "plugin")
KEEP_SNAPSHOTS = 2
CHANGES_CAP = 200
CHANGES_REPOS = ("engine", "workflows")

DEFAULT_URLS = {
    "engine": "https://github.com/kenmclennan/lightcycle.git",
    "workflows": "https://github.com/kenmclennan/lightcycle-workflows.git",
    "plugin": "https://github.com/kenmclennan/lightcycle-plugin.git",
}
DEFAULT_SKILLS_PATH = "plugins/lightcycle/skills"

# Where each kind of reference is defined: (repo, globs). A name is real when it
# appears as a token in any file those globs select. One table, so an engine
# layout change touches one place.
SOURCES = {
    "verb": [("engine", ["**/*.py", "docs/**/*.md"])],
    "flag": [("engine", ["**/*.py", "docs/**/*.md"])],
    "config key": [("engine", ["**/*.py", "docs/**/*.md"])],
    "doctor finding": [("engine", ["**/*.py", "docs/**/*.md"])],
    "stage or step": [
        ("workflows", ["**/*.md"]),
        ("engine", ["docs/**/*.md", "**/workflows/*.md", "**/steps/*.md"]),
    ],
    "workflow": [("workflows", ["workflows/*.md"])],
}

IGNORE = {"name", "id", "title", "step", "item", "stage", "outcome", "agent", "human"}

TOKEN = re.compile(r"[a-z][a-z0-9_-]*|--[a-z][a-z0-9-]*")


def data_dir():
    return os.environ.get("LC_WORKFLOW_DATA_DIR") or os.getcwd()


def config(key, default=None):
    value = os.environ.get("LC_WORKFLOW_CONFIG_" + key.upper().replace("-", "_"))
    if value is None or value.strip() == "":
        return default
    return value.strip()


def url(name):
    return config(name + "-url", DEFAULT_URLS[name])


def skills_path():
    return config("skills-path", DEFAULT_SKILLS_PATH).strip("/")


def clone_path(name):
    return os.path.join(data_dir(), "repos", name + ".git")


def snapshot_path(name, sha):
    return os.path.join(data_dir(), "snapshots", "%s-%s" % (name, sha))


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def git(*args, git_dir=None, check=True):
    cmd = ["git"]
    if git_dir:
        cmd += ["--git-dir", git_dir]
    cmd += list(args)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    proc = subprocess.run(cmd, capture_output=True, env=env)
    if check and proc.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), proc.stderr.decode(errors="replace").strip()))
    return proc


def ensure_clone(name, fetch=True):
    path = clone_path(name)
    if not os.path.isdir(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        git("clone", "--bare", "--quiet", url(name), path)
    if fetch:
        git("fetch", "--quiet", "origin", "+main:main", git_dir=path)
    return path


def main_sha(name):
    return git("rev-parse", "main", git_dir=clone_path(name)).stdout.decode().strip()


def commit_count(name, old, new):
    proc = git("rev-list", "--count", "%s..%s" % (old, new), git_dir=clone_path(name), check=False)
    return proc.stdout.decode().strip() if proc.returncode == 0 else "?"


def subjects(name, *args):
    proc = git("log", "--format=%h %s", *args, git_dir=clone_path(name), check=False)
    if proc.returncode != 0:
        return None
    return [l for l in proc.stdout.decode(errors="replace").splitlines() if l]


def changes_since(roots_state):
    old_shas, new_shas = roots_state["from"], roots_state["to"]
    blocks = []
    for name in CHANGES_REPOS:
        old, new = old_shas.get(name), new_shas[name]
        if old and old == new:
            blocks.append("%s: no changes" % name)
            continue
        lines = subjects(name, "%s..%s" % (old, new)) if old else None
        if lines is not None:
            head = "%s: %s -> %s, %d commits" % (name, old, new, len(lines))
        else:
            lines = subjects(name, "-n", str(CHANGES_CAP), new) or []
            if old:
                head = "%s: %s unreachable, last %d commits" % (name, old, len(lines))
            else:
                head = "%s: first review, last %d commits" % (name, len(lines))
        blocks.append("\n".join([head] + lines))
    return "\n".join(blocks)


def parse_state(raw):
    if not raw:
        return {"from": {}, "to": {}}
    state = json.loads(raw) if isinstance(raw, str) else raw
    return {"from": state.get("from") or {}, "to": state.get("to") or {}}


def snapshot(name, sha):
    dest = snapshot_path(name, sha)
    if os.path.isdir(dest):
        return dest
    tmp = dest + ".partial"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    archive = git("archive", "--format=tar", sha, git_dir=clone_path(name)).stdout
    proc = subprocess.run(["tar", "-x", "-C", tmp], input=archive, capture_output=True)
    if proc.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("tar failed: %s" % proc.stderr.decode(errors="replace").strip())
    os.rename(tmp, dest)
    return dest


def prune_snapshots():
    root = os.path.join(data_dir(), "snapshots")
    if not os.path.isdir(root):
        return []
    removed = []
    for name in REPOS:
        mine = [
            os.path.join(root, d) for d in os.listdir(root)
            if d.startswith(name + "-") and not d.endswith(".partial")
        ]
        mine.sort(key=os.path.getmtime, reverse=True)
        for path in mine[KEEP_SNAPSHOTS:]:
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path)
    return removed


def tokens_in(root, globs):
    found = set()
    for base, _, files in os.walk(root):
        for f in files:
            rel = os.path.relpath(os.path.join(base, f), root)
            if not any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.replace("**/", "")) for g in globs):
                continue
            try:
                with open(os.path.join(base, f), errors="replace") as handle:
                    found.update(TOKEN.findall(handle.read().lower()))
            except OSError:
                continue
    return found


class Index:
    def __init__(self, roots):
        self.roots = roots
        self.cache = {}

    def has(self, kind, name):
        needle = name.lower()
        for repo, globs in SOURCES[kind]:
            key = (repo, tuple(globs))
            if key not in self.cache:
                self.cache[key] = tokens_in(self.roots[repo], globs)
            if needle in self.cache[key]:
                return True
        return False

    def sources(self, kind):
        return ", ".join(sorted({repo for repo, _ in SOURCES[kind]}))


LC_CALL = re.compile(r"(?<![\w/.-])lc\s+([a-z][a-z0-9-]*)(?:\s+([a-z][a-z0-9-]*))?")
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")
CONFIG_CALL = re.compile(r"\blc\s+config\s+(?:get\s+|set\s+|unset\s+)?([a-z][a-z0-9_.-]*)")
STEP_FLAG = re.compile(r"--step\s+([a-z][a-z0-9-]*)")
CLAIM_CALL = re.compile(r"\blc\s+claim\s+([a-z][a-z0-9-]*)")
WORKFLOW_REF = re.compile(r"(?:--workflow\s+|\blc\s+workflow\s+(?:add|check|describe|simulate)\s+)lightcycle/([a-z][a-z0-9-]*)")
DOCTOR_KIND = re.compile(r"`([a-z][a-z0-9]*(?:[-_][a-z0-9]+)+)`")


def code_segments(text):
    inside = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if inside:
            yield number, line, line
        else:
            for span in re.findall(r"`([^`]+)`", line):
                yield number, span, line


def extract(text):
    refs = []
    for number, code, line in code_segments(text):
        for m in LC_CALL.finditer(code):
            refs.append((number, "verb", m.group(1)))
            second = m.group(2)
            if second and m.group(1) not in ("claim", "done", "show", "attach", "new", "config", "trace"):
                refs.append((number, "verb", second))
        if re.search(r"(?<![\w/.-])lc\s", code):
            for m in FLAG.finditer(code):
                refs.append((number, "flag", m.group(0)))
        for m in CONFIG_CALL.finditer(code):
            refs.append((number, "config key", m.group(1)))
        for m in STEP_FLAG.finditer(code):
            refs.append((number, "stage or step", m.group(1)))
        for m in CLAIM_CALL.finditer(code):
            refs.append((number, "stage or step", m.group(1)))
        for m in WORKFLOW_REF.finditer(code):
            refs.append((number, "workflow", m.group(1)))
    for number, line in enumerate(text.splitlines(), 1):
        if "doctor" in line.lower() and "lc " not in line:
            for m in DOCTOR_KIND.finditer(line):
                refs.append((number, "doctor finding", m.group(1)))
    seen = set()
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            yield ref


def find_misses(plugin_root, skills_rel, index):
    misses = []
    base = os.path.join(plugin_root, skills_rel)
    for dirpath, _, files in sorted(os.walk(base)):
        for f in sorted(files):
            if not f.endswith(".md"):
                continue
            path = os.path.join(dirpath, f)
            with open(path, errors="replace") as handle:
                text = handle.read()
            rel = os.path.relpath(path, plugin_root)
            for number, kind, name in extract(text):
                bare = name.lstrip("-")
                if bare in IGNORE:
                    continue
                if not index.has(kind, name):
                    misses.append("%s:%d: %s `%s` not found in %s" % (rel, number, kind, name, index.sources(kind)))
    return misses
