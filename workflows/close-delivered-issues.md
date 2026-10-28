---
summary: one inbox item proposing closes for open GitHub issues whose fix has merged
when-to-use: an operator enables its suggested schedule; it is not filed by hand
schedule:
  cron: 0 10 * * 1-5
  name: issue-close
  guard: script:scripts/delivered-issues.py
lifecycle:
  install: scripts/delivered-install.py
  upgrade: scripts/delivered-upgrade.py
config:
  repos: optional
  gh-command: optional
  lc-command: optional
config-example:
  repos: kenmclennan/lightcycle
  gh-command: scripts/tests/fake-gh.py
  lc-command: scripts/tests/fake-lc.py
---

# Close-delivered-issues

A schedule guard script lists open GitHub issues on the lightcycle repos that an `lc` item refers to. It sorts them into "proposed closes" (every referring item is done and completed with a merged PR) and "needs a look" (anything else), and fails when nothing is new or changed. When it passes, the engine files one item listing both groups. The `record-proposed` script stage records what was shown, and one human gate lets Ken approve closes, all or a named subset. The `close-issues` script stage then closes the approved issues with a comment naming the PRs and items that fixed them. No agent runs anywhere, so a quiet firing spends no tokens and files nothing.

Nothing closes without the gate. An issue shown once is not proposed again until a referring item is added or changes state. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

The `schedule:` block is a suggestion. The bundle never enables it; an operator does, in config.

entry: record-proposed

display:
  record-proposed  Recording proposals
  review-closes    Approve issue closes
  close-issues     Closing issues

edges:
  record-proposed  recorded  review-closes  primary
  review-closes    approved  close-issues   primary
  review-closes    declined
  close-issues     closed

disposition:
  declined  completed
  closed    completed
