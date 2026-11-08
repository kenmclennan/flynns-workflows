#!/usr/bin/env python3
import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import workflow_config


def run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def skip(reason):
    sys.stderr.write("kb-maintain: %s; leaving the checkout alone\n" % reason)
    sys.exit(0)


def main():
    qmd = shlex.split(workflow_config.require_config("qmd-command"))
    path = workflow_config.config("checkout-path")
    if not path or not os.path.isdir(os.path.join(path, ".git")):
        skip("checkout-path is not a git checkout")
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], path).stdout.strip()
    if branch != "main":
        skip("checkout is on %r, not main" % branch)
    if run(["git", "status", "--porcelain"], path).stdout.strip():
        skip("checkout has uncommitted changes")
    pull = run(["git", "pull", "--ff-only"], path)
    if pull.returncode != 0:
        skip("fast-forward pull failed: %s" % pull.stderr.strip()[-200:])
    for verb in ("update", "embed"):
        try:
            proc = run(qmd + [verb], path)
        except FileNotFoundError:
            skip("qmd is not available")
        if proc.returncode != 0:
            skip("qmd %s failed: %s" % (verb, proc.stderr.strip()[-200:]))


if __name__ == "__main__":
    main()
