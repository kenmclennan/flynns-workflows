#!/usr/bin/env python3
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def items():
    directory = os.environ.get("FAKE_LC_ITEMS", os.path.join(HERE, "lc-items"))
    out = {}
    for name in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        with open(os.path.join(directory, name)) as handle:
            item = json.load(handle)
        out[item["id"]] = item
    return out


def main():
    verb, arg = sys.argv[1], sys.argv[2]
    found = items()
    if verb == "search":
        for item in found.values():
            if arg in (item.get("description") or ""):
                sys.stdout.write("%-10s %-9s %-16s %s  [description] ...\n" % (
                    item["id"], item["state"], item.get("project", ""), item.get("title", "")))
                sys.stdout.write("- ...%s...\n" % arg)
        return
    if arg not in found:
        sys.stderr.write("no such item: %s\n" % arg)
        sys.exit(1)
    sys.stdout.write(json.dumps(found[arg]) + "\n")


if __name__ == "__main__":
    main()
