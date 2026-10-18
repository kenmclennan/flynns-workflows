---
script: scripts/rank.py
accepts:
  scores: required
produces:
  candidates-digest: optional
detail: [outcome, out:candidates-digest, needs, reason]
---

# Rank

Engine-owned: no agent claims this stage. `scripts/rank.py` runs when `evaluate` finishes. It reads the `scores` artifact from the item and writes each relevance and novelty into the state with a combined score: 0.6 times relevance plus 0.4 times novelty, plus 1.0 for a tier 1 candidate and 0.5 for each inbound trusted link beyond the first, up to four. Every score is written, whether or not it clears `threshold`.

A candidate below threshold stays in state with its score. It is re-scored, from its stored relevance and novelty, only when its inbound count has risen since it was scored; `evaluate` is never run on it again. A survivor is any scored candidate at or above `threshold` that Ken has not accepted or rejected, including one a previous, abandoned gate left undecided.

It prints `survivors` or `none`. On `survivors` it attaches `candidates-digest` to its own step: the filing line for `kb-ingest` items with `kb-repo`, then for each survivor the title, link, author, tier, inbound count, score, summary and what the knowledgebase already has. On `none` the item closes and Ken never sees it. A missing or unparseable `scores` artifact, or a missing `threshold` or `kb-repo`, parks the step with the reason and the stderr tail.
