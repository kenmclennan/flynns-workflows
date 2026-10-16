#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import drift


def stored_version(root):
    try:
        with open(os.path.join(root, "layout-version")) as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return 0


def main():
    root = drift.data_dir()
    version = stored_version(root)
    if version >= drift.LAYOUT_VERSION:
        return
    os.makedirs(os.path.join(root, "repos"), exist_ok=True)
    os.makedirs(os.path.join(root, "snapshots"), exist_ok=True)
    with open(os.path.join(root, "layout-version"), "w") as handle:
        handle.write("%d\n" % drift.LAYOUT_VERSION)


if __name__ == "__main__":
    main()
