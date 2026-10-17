#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import scout_state


def main():
    os.makedirs(scout_state.data_dir(), exist_ok=True)
    conn = scout_state.connect()
    try:
        scout_state.migrate(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
