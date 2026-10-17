#!/usr/bin/env python3
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import scout_fetch
import scout_state


def cmd_feeds(conn, args):
    for f in scout_state.feeds_all(conn):
        print(
            "%s  tier %d  %s  mark %s  %s"
            % (f["url"], f["tier"], "enabled" if f["enabled"] else "disabled", f["high_water"] or "-", f["reason"])
        )


def cmd_queue(conn, args):
    for r in scout_state.queue(conn):
        score = "%.2f" % r["last_score"] if r["last_score"] is not None else "unscored"
        print(
            "%s  tier %d  inbound %d  %s  %s  %s"
            % (r["url"], r["tier"], r["inbound"], score, r["verdict"] or "undecided", r["title"])
        )


def cmd_why(conn, args):
    url = scout_fetch.normalize(args.url)
    d = scout_state.decision_for(conn, url)
    if d is None:
        print("no decision recorded for %s" % url)
        return
    print("%s: %s on %s (%s)%s" % (url, d["verdict"], d["decided_at"], d["reason"] or "no reason given", " item " + d["item_id"] if d["item_id"] else ""))


def cmd_add_feed(conn, args):
    with conn:
        added = scout_state.add_feed(conn, args.url, args.kind, args.tier, args.areas, args.reason, scout_state.now_iso())
    print("added" if added else "already present")


def cmd_set_feed(conn, args):
    with conn:
        found = scout_state.set_feed_enabled(conn, args.url, args.enabled)
    print("updated" if found else "no such feed")


def main():
    parser = argparse.ArgumentParser(prog="scout-cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("feeds").set_defaults(fn=cmd_feeds)
    sub.add_parser("queue").set_defaults(fn=cmd_queue)
    p = sub.add_parser("why")
    p.add_argument("url")
    p.set_defaults(fn=cmd_why)
    p = sub.add_parser("add-feed")
    p.add_argument("url")
    p.add_argument("--kind", default="rss")
    p.add_argument("--tier", type=int, default=1)
    p.add_argument("--areas", default="")
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_add_feed)
    for name, enabled in (("disable-feed", False), ("enable-feed", True)):
        p = sub.add_parser(name)
        p.add_argument("url")
        p.set_defaults(fn=cmd_set_feed, enabled=enabled)
    args = parser.parse_args()
    conn = scout_state.connect()
    try:
        scout_state.migrate(conn)
        args.fn(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
