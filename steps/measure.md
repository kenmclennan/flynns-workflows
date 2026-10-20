---
script: scripts/kb-measure.py
produces:
  measurements: optional
  review-context: optional
detail: [outcome, out:measurements, needs, reason]
---

# Measure

Engine-owned: no agent claims this stage. `scripts/kb-measure.py` runs the moment the item is filed. It reads the guard's `state` (the tip sha) from the `schedule_state` field of its stdin object, refreshes a bare clone of the knowledgebase in the data directory, and exports that sha to a snapshot directory, replacing the previous one.

Over the snapshot it lists: relative links that do not resolve; concept docs no `index.md` reaches by following links; topic directories with no link in or out to another topic; concept docs with fewer than `min-cross-topic-links` cross-topic links (an island topic's docs are left to the island line); `references/` files no concept doc cites; `sources` citations of a `references/` file with no matching body link; docs whose `stale_after` has passed. It then counts prettier and markdownlint failures, one line per topic and tool, never one per file. Thin-doc and citation-without-link defects are likewise one line per topic, with a count and up to five example paths; setting KB_AUDIT_PER_FILE restores one line per file.

It attaches `measurements` (one line per defect, grouped per topic for thin-doc and citation-without-link, then the tool counts) and `review-context` (snapshot path, sha, and the previously audited sha or `first audit`) and prints `measured`. It always ends `measured`: a defect is data, not a failure. A missing `npx`, an unreadable snapshot, a failed clone, or a missing `schedule_state` parks the step with the reason and the stderr tail.
