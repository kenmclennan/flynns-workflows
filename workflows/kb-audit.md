---
summary: one inbox item listing stale, unlinked and badly formatted docs in the knowledgebase, found since the last audit
when-to-use: an operator enables its suggested schedule; it is not filed by hand
schedule:
  cron: 0 9 * * 1
  guard: script:scripts/kb-tip-moved.py
lifecycle:
  install: scripts/kb-audit-install.py
config:
  knowledgebase-url: required
  min-cross-topic-links: required
config-example:
  knowledgebase-url: scripts/tests/no-such-repo
  min-cross-topic-links: 2
---

# Kb-audit

A schedule guard reads the knowledgebase's `main` tip and passes only when it differs from the last audited sha, so an unchanged knowledgebase files nothing and spends nothing. The engine then files one item. The `measure` script stage snapshots that tip and runs every mechanical check from the knowledgebase's `CLAUDE.md` Lint section: unresolved links, unreachable docs, island topics, thinly linked docs, uncited references, citations with no body link, passed `stale_after` dates, and prettier and markdownlint counts by topic. The `audit` agent stage reads the measurements and the docs they point at and judges what a script cannot, then ranks everything into a digest. One human gate, `review-kb-findings`, lets Ken and the driver decide what becomes `kb-ingest` items (rewrites) and `small-change` items (repairs). The workflow files and edits nothing itself.

An agent stage gets neither the data directory nor the guard's state, so `measure` produces a `review-context` artifact naming the snapshot and the shas, which `audit` reads from the `inputs` of its claim.

The audited sha is recorded before the gate by `record-audited`, or by `record-clean` when `audit` found nothing, so it is recorded whatever the gate decides. A clean audit closes unseen: nobody is asked to read anything. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

The `schedule:` block is a suggestion. The bundle never enables it; an operator does, in config.

entry: measure

display:
  measure              Measuring the knowledgebase
  audit                Auditing the knowledgebase
  record-audited       Recording the audit
  record-clean         Recording the clean audit
  review-kb-findings   Review knowledgebase findings

nodes:
  record-clean  record-audited

edges:
  measure             measured  audit               primary
  audit               findings  record-audited      primary
  audit               clean     record-clean
  record-audited      recorded  review-kb-findings  primary
  record-clean        recorded
  review-kb-findings  done
  review-kb-findings  filed
  review-kb-findings  reviewed

disposition:
  recorded  completed
  done      completed
  filed     completed
  reviewed  completed
