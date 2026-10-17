---
presents: artifact:candidates-digest
produces:
  decisions: required
---

# Review-candidates (you + driver)

One item lists candidate sources for the knowledgebase, found by following links one hop out from trusted feeds. The scout writes nothing into the knowledgebase: you decide what is worth ingesting.

1. `lc show STEP`, then read the `candidates-digest`. The first line is the command that files an ingest item. Each candidate gives its title, link, author, tier, inbound count, score, summary and what the knowledgebase already has.
2. For each candidate decide one of: `accept`, `reject` or `defer`. For an acceptance, file a `kb-ingest` item with `--repo` set to the `kb-repo` named in the digest, and note the item id it returns. `defer` brings the candidate back at the next firing. To answer "why did we pass on this last time", run `scripts/scout-cli.py why <url>` from the workflow's data directory.
3. If a domain keeps producing accepted candidates, add it as a feed in the artifact below.
4. Attach the verdicts to the item: `lc attach ITEM decisions "<json>" --replace`, where the JSON is `{"decisions": [{"url": "...", "verdict": "accept", "reason": "one line", "item": "<filed item id, acceptances only>"}], "feeds": [{"url": "...", "kind": "rss", "tier": 1, "areas": "...", "reason": "..."}]}`. Every candidate in the digest gets an entry, including when none were accepted. `feeds` may be empty.
5. `lc done STEP recorded` once every candidate has a decision.
6. To drop the whole batch, `lc done ITEM abandoned`. It closes the item and records nothing, so the undecided candidates resurface at the next firing.
