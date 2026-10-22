#!/usr/bin/env python3
import json
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
    if args[:2] in (["issue", "view"], ["issue", "close"]):
        ref = "%s#%s" % (repo, args[2])
        closed_path = os.path.join(directory, "closed.json")
        closed = []
        if os.path.exists(closed_path):
            with open(closed_path) as handle:
                closed = json.load(handle)
        if args[1] == "view":
            sys.stdout.write(json.dumps({"state": "CLOSED" if ref in closed else "OPEN"}) + "\n")
            return
        log = os.environ.get("FAKE_GH_LOG")
        if log:
            with open(log, "a") as handle:
                handle.write(json.dumps({"ref": ref, "comment": args[args.index("--comment") + 1]}) + "\n")
        return
    path = os.path.join(directory, repo.replace("/", "__") + ".json")
    if not os.path.exists(path):
        sys.stdout.write("[]\n")
        return
    with open(path) as handle:
        sys.stdout.write(handle.read())


if __name__ == "__main__":
    main()
