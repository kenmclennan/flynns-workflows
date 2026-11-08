#!/usr/bin/env python3
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import workflow_config

HARD = ("gh", "npx", "python3")


def main():
    failures = ["`%s` is not on PATH" % name for name in HARD if not shutil.which(name)]
    qmd = workflow_config.config("qmd-command")
    if qmd and not shutil.which(qmd):
        sys.stderr.write("warning: qmd is not on PATH, so plan falls back to reading index.md files and maintain skips the index rebuild\n")
    if failures:
        sys.stderr.write("error: kb-ingest cannot be installed: %s\n" % "; ".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    main()
