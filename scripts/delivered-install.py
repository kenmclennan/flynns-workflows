#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import delivered_state as ds


def main():
    os.makedirs(ds.data_dir(), exist_ok=True)
    conn = ds.connect()
    try:
        ds.migrate(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
