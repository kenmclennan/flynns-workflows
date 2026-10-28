---
summary: one inbox item listing candidate sources for the knowledgebase, found by following links one hop out from trusted feeds and scored against Ken's areas
when-to-use: an operator enables its suggested schedule; it is not filed by hand
schedule:
  cron: 0 9 * * 2,5
  name: kb-scout
  guard: script:scripts/feeds-moved.py
lifecycle:
  install: scripts/scout-install.py
  upgrade: scripts/scout-upgrade.py
config:
  threshold: required
  batch-cap: required
  kb-repo: required
  checkout-path: optional
  qmd-command: optional
  fetch-command: optional
config-example:
  threshold: 6.0
  batch-cap: 10
  kb-repo: kenmclennan/knowledgebase
  fetch-command: scripts/tests/fake-fetch.py
---

# Kb-scout

A schedule guard fetches every enabled trusted feed and passes when any has entries newer than its high-water mark, or when candidates or undecided survivors are already waiting. The engine then files one item. The `harvest` script stage records each new entry as a tier 1 candidate, follows its outbound links one hop to tier 2 candidates with an inbound-link count, drops anything the knowledgebase already holds or Ken already decided, and advances the marks. The `evaluate` agent stage reads up to `batch-cap` pending candidates against the knowledgebase and scores them. The `rank` script stage applies `threshold`. One human gate, `review-candidates`, lets Ken and the driver accept, reject or defer each survivor and file a `kb-ingest` item per acceptance. The scout mirrors nothing and writes nothing to the knowledgebase.

Trust propagates along links: the agent never evaluates anything a trusted author did not point at. The state - feeds, everything seen, every decision - lives in a SQLite file in the workflow's data directory, never in the knowledgebase, so a record of what was declined does not sit next to the material an agent is meant to use. `scripts/scout-cli.py` reads it, so the gate can answer why a source was passed over last time.

`harvest` and `evaluate` declare the knowledgebase as their workspace: the dedupe reads `references/` from a clean worktree at `origin/main`. An agent stage gets neither the data directory nor the guard's state, so `harvest` produces a `candidates` artifact that `evaluate` reads from the `inputs` of its claim, and `rank` attaches `candidates-digest` for the gate. An abandoned gate records nothing, so undecided survivors resurface at the next firing. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

The `schedule:` block is a suggestion. The bundle never enables it; an operator does, in config.

entry: harvest

workspace:
  harvest   project
  evaluate  project

display:
  harvest            Harvesting new candidates
  evaluate           Scoring candidates
  rank               Ranking candidates
  review-candidates  Review knowledgebase candidates
  record-decisions   Recording decisions

edges:
  harvest            harvested  evaluate           primary
  evaluate           scored     rank               primary
  rank               survivors  review-candidates  primary
  rank               none
  review-candidates  recorded   record-decisions   primary
  review-candidates  abandoned
  record-decisions   written

disposition:
  none       completed
  written    completed
  abandoned  abandoned
