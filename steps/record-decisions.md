---
script: scripts/record-decisions.py
accepts:
  decisions: required
detail: [outcome, report]
---

# Record-decisions

Engine-owned: no agent claims this stage. `scripts/record-decisions.py` runs when `review-candidates` closes `recorded`. It reads the `decisions` artifact from the item and writes, in one transaction, every verdict with its reason and the filed item id, and every feed addition. It writes every verdict even when none were accepted, so a rejection is remembered. Re-running the same artifact changes nothing. It prints `written`.

An `accept` or `reject` is final: that URL is never harvested again. A `defer` is stored with its reason but the candidate stays eligible and resurfaces. A missing or unparseable `decisions` artifact, or an unknown verdict, parks the step with the reason and the stderr tail.
