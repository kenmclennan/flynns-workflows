---
script: scripts/close-issues.py
accepts:
  approved: required
detail: [outcome, report, needs, reason]
---

# Close-issues

Engine-owned: no agent claims this stage. `scripts/close-issues.py` runs when `review-closes` closes `approved`. It reads the `approved` artifact and, for each `owner/repo#N`, re-runs the classification live. It skips an issue that is no longer a proposed close or has no referring item, and skips one already closed. Otherwise it closes the issue with the comment `Fixed by #1013 (LC-1301): <item title>.`, one sentence per referring item, with `owner/repo#N` for a PR on another repo.

It prints `closed` with a note naming each issue closed and each skipped with its reason; the note becomes the item's closing note. A missing or unparseable `approved` artifact, or a `gh` or `lc` failure, parks the step with the reason and the stderr tail. A re-run after a failure is safe: closed issues are skipped.
