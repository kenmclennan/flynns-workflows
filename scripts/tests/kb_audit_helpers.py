import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, "kb-audit-fixtures")


def git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def make_remote(fixture):
    work = tempfile.mkdtemp()
    shutil.copytree(os.path.join(FIXTURES, fixture), work, dirs_exist_ok=True)
    git(work, "init", "-b", "main")
    git(work, "add", "-A")
    git(work, "commit", "-m", "kb")
    bare = tempfile.mkdtemp()
    git(work, "clone", "--bare", work, bare)
    shutil.rmtree(work)
    return bare


def run(script, data_dir, url, stdin="{}", **extra):
    env = dict(os.environ)
    env["LC_WORKFLOW_DATA_DIR"] = data_dir
    env["LC_WORKFLOW_CONFIG_KNOWLEDGEBASE_URL"] = url
    env["LC_WORKFLOW_CONFIG_MIN_CROSS_TOPIC_LINKS"] = "1"
    env["KB_AUDIT_SKIP_TOOLS"] = "1"
    env["KB_AUDIT_TODAY"] = "2026-06-01"
    env.update(extra)
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script)],
        input=stdin, capture_output=True, text=True, cwd=data_dir, env=env,
    )
