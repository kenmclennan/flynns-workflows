#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import scout_state


def load_scores(stdin):
    raw = scout_state.read_artifact(stdin, "scores")
    if raw is None:
        sys.stderr.write("no scores artifact on the item; evaluate did not attach one\n")
        sys.exit(1)
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, dict):
            data = data["scores"]
        return [
            {
                "url": str(s["url"]),
                "relevance": min(max(float(s["relevance"]), 0.0), 10.0),
                "novelty": min(max(float(s["novelty"]), 0.0), 10.0),
                "summary": str(s.get("summary") or ""),
                "kb_has": str(s.get("kb_has") or ""),
                "author": str(s.get("author") or ""),
            }
            for s in data
        ]
    except (ValueError, KeyError, TypeError) as exc:
        sys.stderr.write("scores is not a JSON list of url/relevance/novelty objects: %r\n" % (exc,))
        sys.exit(1)


def digest(rows, kb_repo):
    lines = [
        "File each accepted candidate as a kb-ingest item: lc new item \"<title>\" --workflow flynns-workflows/kb-ingest --repo %s"
        % kb_repo,
        "",
    ]
    for r in rows:
        lines.append("- %s" % (r["title"] or r["url"]))
        lines.append("  link: %s" % r["url"])
        lines.append("  author: %s" % (r["author"] or "unknown"))
        lines.append("  tier %d, inbound trusted links %d, score %.2f" % (r["tier"], r["inbound"], r["last_score"]))
        lines.append("  summary: %s" % (r["summary"] or "(none)"))
        lines.append("  knowledgebase already has: %s" % (r["kb_has"] or "(not recorded)"))
        lines.append("")
    return "\n".join(lines).strip()


def main():
    try:
        stdin = json.load(sys.stdin)
    except ValueError as exc:
        sys.stderr.write("stdin is not JSON: %s\n" % exc)
        sys.exit(1)
    scores = load_scores(stdin)
    threshold = scout_state.require_config("threshold", float)
    kb_repo = scout_state.require_config("kb-repo")
    now = scout_state.now_iso()

    conn = scout_state.connect()
    try:
        scout_state.migrate(conn)
        with conn:
            scored = set()
            for s in scores:
                result = scout_state.record_scores(
                    conn, s["url"], s["relevance"], s["novelty"], s["summary"], s["kb_has"], s["author"], now
                )
                if result is None:
                    sys.stderr.write("scores names %s, which is not a known candidate; skipped\n" % s["url"])
                else:
                    scored.add(s["url"])
            for row in scout_state.rescorable(conn):
                scout_state.rescore(conn, row["url"], now)
        survivors = scout_state.survivors_undecided(conn, threshold)
    finally:
        conn.close()

    if not survivors:
        scout_state.emit({"outcome": "none"})
        return
    scout_state.emit({"outcome": "survivors", "artifacts": {"candidates-digest": digest(survivors, kb_repo)}})


if __name__ == "__main__":
    main()
