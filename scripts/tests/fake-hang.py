#!/usr/bin/env python3
import os
import subprocess
import sys
import time


def main():
    counter = os.environ.get("FAKE_HANG_COUNT")
    if counter:
        with open(counter, "a") as handle:
            handle.write("x\n")
    if os.environ.get("FAKE_HANG_FAIL"):
        sys.stderr.write(os.environ["FAKE_HANG_FAIL"] + "\n")
        sys.exit(int(os.environ.get("FAKE_HANG_EXIT", "1")))
    pidfile = os.environ.get("FAKE_HANG_PIDFILE")
    if pidfile:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        with open(pidfile, "w") as handle:
            handle.write(str(child.pid))
    time.sleep(600)


if __name__ == "__main__":
    main()
