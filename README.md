# flynns-workflows

A personal `lc` workflow origin (see `CLAUDE.md`).

| Workflow                                                   | Gates                                 | Summary                                                                                                                                                                      |
| ---------------------------------------------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`blueprint-delivery`](docs/blueprint-delivery.md)         | spec PR, feature PR, code PR, plan PR | Delivers a whole Blueprint's `plan/` as one item by looping - one pass per work item through a spec/feature/code arc, then an adversarial design audit before closing.       |
| [`close-delivered-issues`](docs/close-delivered-issues.md) | close approval                        | Scheduled. Proposes closes for open GitHub issues whose fix has merged; nothing closes until the gate approves, and no agent runs.                                           |
| [`kb-audit`](docs/kb-audit.md)                             | review kb findings                    | Scheduled. Weekly audit of the knowledgebase for stale, unlinked and badly formatted docs; raises one inbox item and edits nothing itself.                                   |
| [`kb-ingest`](docs/kb-ingest.md)                           | plan review, PR merge                 | Takes one approved source into the knowledgebase through a plan, a PR and a human merge.                                                                                     |
| [`kb-scout`](docs/kb-scout.md)                             | review candidates                     | Scheduled. Follows trusted feeds one hop out, scores candidate sources for the knowledgebase, and raises one inbox item; the driver files a `kb-ingest` item per acceptance. |
| [`plugin-drift-review`](docs/plugin-drift-review.md)       | review findings                       | Scheduled. Finds where the lightcycle plugin's skills have drifted from the engine and official workflows; raises one inbox item.                                            |
| [`triage-github-issues`](docs/triage-github-issues.md)     | triage                                | Scheduled. Lists GitHub issues on the lightcycle repos not raised before as one inbox item; no agent runs.                                                                   |
