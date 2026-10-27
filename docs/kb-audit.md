# Kb-audit

A weekly audit of the knowledgebase (`kenmclennan/knowledgebase`). It raises one inbox item listing stale, unlinked and badly formatted docs, and files and edits nothing itself.

- **guard** (`scripts/kb-tip-moved.py`) passes only when the knowledgebase's `main` tip differs from the last audited sha. An unchanged knowledgebase files nothing and spends nothing.
- **measure** is a script stage that spends no tokens. Over a snapshot of the tip it lists unresolved links, unreachable docs, island topics, thinly linked docs, uncited references, citations with no body link, root index counts that disagree with the topic, passed `stale_after` dates, and prettier and markdownlint counts by topic.
- **audit** is an agent stage. It reads the measurements and the docs they point at, judges contradictions, duplicated concepts and stale indexes, and writes a ranked digest of at most twelve entries. Formatting is one entry per topic.
- **record-audited** and **record-clean** store the audited sha before the gate, so it is recorded whatever the gate decides. A clean audit closes unseen.
- **review-kb-findings** is the one human gate. `filed`, `reviewed` and `done` all close the item. Rewrites become `kb-ingest` items and repairs become `small-change` items, filed from the gate.

## Operator setup

Set `knowledgebase-url` (where the clone and the tip come from; credentials come from the machine's git setup) and `min-cross-topic-links` (the floor below which a concept doc counts as thinly connected). Both are required. Enable the suggested schedule in config; `lc schedule list` shows it. `git`, `python3` and `npx` must be on PATH.
