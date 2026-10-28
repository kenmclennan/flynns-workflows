---
summary: one inbox item listing GitHub issues on the lightcycle repos not raised before
when-to-use: an operator enables its suggested schedule; it is not filed by hand
schedule:
  cron: 0 9,14 * * 1-5
  name: triage
  guard: script:scripts/new-issues.py
lifecycle:
  install: scripts/install.py
  upgrade: scripts/upgrade.py
config:
  repos: optional
  labels: optional
  ignore-authors: optional
  lookback-days: optional
  gh-command: optional
config-example:
  repos: kenmclennan/lightcycle
  gh-command: scripts/tests/fake-gh.py
---

# Triage-github-issues

A schedule guard script looks for open GitHub issues on the lightcycle repos that were not raised before. When it finds any, the engine files one item listing them. The `record-raised` script stage then marks them raised in a SQLite file in the workflow's data directory, and one human gate lets Ken and the driver triage. No agent runs anywhere in the flow, so a firing with nothing new and a firing with something new both spend no tokens.

Issues are recorded as raised before triage, so `triaged`, `abandoned` and an item closed by hand all leave them marked and they never come back. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

The `schedule:` block is a suggestion. The bundle never enables it; an operator does, in config.

entry: record-raised

display:
  record-raised  Recording raised issues
  triage         Triage new issues

edges:
  record-raised  recorded  triage  primary
  triage         triaged
  triage         abandoned
