#!/usr/bin/env python3
import shutil
import sys

HARD = ("git", "npx", "python3")


def main():
    failures = ["`%s` is not on PATH" % name for name in HARD if not shutil.which(name)]
    if failures:
        sys.stderr.write("error: kb-audit cannot be installed: %s\n" % "; ".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    main()
