---
script: scripts/record-proposed.py
detail: [outcome, report, needs, reason]
---

# Record-proposed

Engine-owned: no agent claims this stage. `scripts/record-proposed.py` runs the moment the item is filed. It reads the guard's `state` from the `schedule_state` field of its stdin object and upserts every shown issue with its fingerprint into the `shown` table of `delivered.db` in the data directory, in one transaction. It prints `recorded`.

It records before the gate rather than at a decline so one idempotent write covers a decline, a partial approval and an item closed by hand. A missing or unparseable `schedule_state`, or a locked database, parks the step with the reason and the stderr tail.
