#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import drift


def main():
    for name in drift.REPOS:
        try:
            drift.ensure_clone(name)
        except RuntimeError as exc:
            sys.stderr.write("warning: could not refresh %s, the guard will retry: %s\n" % (name, exc))
    drift.prune_snapshots()


if __name__ == "__main__":
    main()
