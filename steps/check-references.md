---
script: scripts/check-references.py
produces:
  missing-references: optional
  review-context: optional
  changes-since: optional
---

# Check-references

Engine-owned: no agent claims this stage. `scripts/check-references.py` runs the moment the item is filed. It reads the guard's `state` from the `schedule_state` field of its stdin object and exports a read-only snapshot of each repo at its `to` SHA into `snapshots/` in the data directory. It then lists every `lc` verb and subcommand, flag, config key, doctor finding kind, workflow stage and step name, and official workflow name that the plugin's skills mention in code spans and fenced blocks, and checks each against the engine and workflow snapshots.

It attaches `missing-references` (one line per miss, or `none`), `review-context` (snapshot paths, bare-clone paths and SHAs for `review-skills`, which cannot find them otherwise) and `changes-since` (the commit subjects between the previous and current SHAs for the engine and the workflows, or the last 200 on a first review, so `review-skills` knows which capabilities are new). It prints `clean` or `misses`. Both go on to `review-skills`: a clean mechanical pass does not mean the behaviour described is right.

A name is checked by presence in the source files named in `scripts/lib/drift.py`, so a miss can be a false positive: an example or a deliberate non-existent command in a "do not run" snippet. A missing or unparseable `schedule_state`, or a snapshot that cannot be made, parks the step with the reason and the stderr tail.
