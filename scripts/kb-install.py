#!/usr/bin/env python3
import os
import shutil
import sys

HARD = ("gh", "npx", "python3")


def main():
    failures = ["`%s` is not on PATH" % name for name in HARD if not shutil.which(name)]
    if not shutil.which(os.environ.get("LC_WORKFLOW_CONFIG_QMD_COMMAND") or "qmd"):
        sys.stderr.write("warning: qmd is not on PATH, so plan falls back to reading index.md files and maintain skips the index rebuild\n")
    if failures:
        sys.stderr.write("error: kb-ingest cannot be installed: %s\n" % "; ".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    main()
