#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import triage_state


def main():
    os.makedirs(triage_state.data_dir(), exist_ok=True)
    conn = triage_state.connect()
    try:
        triage_state.migrate(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
