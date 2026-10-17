#!/usr/bin/env python3
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    url = sys.argv[1]
    directory = os.environ.get("FAKE_FETCH_RECORDINGS", os.path.join(HERE, "recordings", "scout"))
    path = os.path.join(directory, re.sub(r"[^A-Za-z0-9]+", "_", url) + ".txt")
    if not os.path.exists(path):
        sys.stderr.write("fake fetch: no recording for %s\n" % url)
        sys.exit(4)
    with open(path) as handle:
        sys.stdout.write(handle.read())


if __name__ == "__main__":
    main()
