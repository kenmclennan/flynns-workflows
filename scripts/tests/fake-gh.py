#!/usr/bin/env python3
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    args = sys.argv[1:]
    if os.environ.get("FAKE_GH_FAIL"):
        sys.stderr.write("fake gh: simulated failure\n")
        sys.exit(4)
    repo = args[args.index("--repo") + 1]
    directory = os.environ.get("FAKE_GH_RECORDINGS", os.path.join(HERE, "recordings"))
    path = os.path.join(directory, repo.replace("/", "__") + ".json")
    if not os.path.exists(path):
        sys.stdout.write("[]\n")
        return
    with open(path) as handle:
        sys.stdout.write(handle.read())


if __name__ == "__main__":
    main()
