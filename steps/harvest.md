---
script: scripts/harvest.py
config: [batch-cap, fetch-command, checkout-path, qmd-command]
produces:
  candidates: required
detail: [outcome, out:candidates, needs, reason]
---

# Harvest

Engine-owned: no agent claims this stage. `scripts/harvest.py` runs the moment the item is filed, in the item's worktree of the knowledgebase, and reads the data directory from the environment. It reads the guard's `state` from the `schedule_state` field of its stdin object: the new entries per feed and the new high-water marks.

For each entry it records a tier 1 candidate, fetches the page, and records each outbound link on another host as a tier 2 candidate with an inbound count of one, or bumps the count if the link is already seen, and records the link's provenance: the entry that linked it, the link text and the sentence around it. It drops links that never become sources: bare site homepages and YouTube, Wikipedia, LinkedIn and X or Twitter hosts. Before reading pending candidates it deletes unscored, undecided tier 2 rows the same rule flags. One hop only. It skips anything whose URL is the `resource:` of a file under `references/` in the worktree, anything Ken already accepted or rejected, and any entry it processed before, so a re-run with the same state changes nothing. It then advances each feed's mark, all in one transaction.

It attaches `candidates` to its own step: the pending candidates, best first and capped at `batch-cap`, with the knowledgebase checkout path and `qmd` command for `evaluate`, which cannot see the data directory. It prints `harvested`. A missing or unparseable `schedule_state`, a worktree with no `references/` directory, a missing `batch-cap`, or a locked database parks the step with the reason and the stderr tail.
