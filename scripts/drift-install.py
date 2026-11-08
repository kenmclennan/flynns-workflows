#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import drift


def main():
    root = drift.data_dir()
    os.makedirs(os.path.join(root, "repos"), exist_ok=True)
    os.makedirs(os.path.join(root, "snapshots"), exist_ok=True)
    with open(os.path.join(root, "layout-version"), "w") as handle:
        handle.write("%d\n" % drift.LAYOUT_VERSION)
    for name in drift.REPOS:
        if drift.config(name + "-url") is None:
            sys.stderr.write("warning: %s-url is not set, so the %s clone is skipped until it is\n" % (name, name))
            continue
        try:
            drift.ensure_clone(name, fetch=False)
        except RuntimeError as exc:
            sys.stderr.write("warning: could not clone %s yet, the guard will retry: %s\n" % (name, exc))


if __name__ == "__main__":
    main()
