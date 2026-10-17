#!/usr/bin/env python3
import os
import sys


def main():
    log = os.environ.get("FAKE_QMD_LOG")
    if log:
        with open(log, "a") as handle:
            handle.write(" ".join(sys.argv[1:]) + "\n")


if __name__ == "__main__":
    main()
