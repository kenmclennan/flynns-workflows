---
summary: one inbox item listing where the lightcycle plugin's skills have drifted from the engine and official workflows
when-to-use: an operator enables its suggested schedule; it is not filed by hand
schedule:
  cron: 0 8 * * *
  guard: script:scripts/moved.py
lifecycle:
  install: scripts/drift-install.py
  upgrade: scripts/drift-upgrade.py
  maintain: scripts/drift-maintain.py
  cron: 0 7 * * *
config:
  engine-url: optional
  workflows-url: optional
  plugin-url: optional
  skills-path: optional
config-example:
  engine-url: scripts/tests/no-such-repo
---

# Plugin-drift-review

A schedule guard fetches the engine, the official workflows and the plugin, and passes only when one of their `main` SHAs has moved since the last review. The engine then files one item. The `check-references` script stage mechanically checks every name the plugin's skills mention against the engine and workflows. The `review-skills` agent stage reads the skills against the engine and workflows and reports what they get wrong or do not teach. One human gate, `review-findings`, lets Ken and the driver decide what becomes items. The workflow files nothing itself.

An agent stage gets neither the data directory nor the guard's state, so `check-references` attaches a `review-context` artifact, plus a `changes-since` artifact listing what changed, as declared outputs (which `review-skills` reads from the `inputs` of its claim) naming the snapshot paths and SHAs for `review-skills` to read. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

The `schedule:` block is a suggestion. The bundle never enables it; an operator does, in config.

entry: check-references

display:
  check-references  Checking references
  review-skills     Reviewing skills
  review-findings   Review drift findings

edges:
  check-references  clean     review-skills  primary
  check-references  misses    review-skills
  review-skills     findings  review-findings  primary
  review-skills     clean
  review-findings   reviewed
  review-findings   abandoned
