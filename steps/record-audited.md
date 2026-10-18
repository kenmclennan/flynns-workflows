---
script: scripts/kb-record-audited.py
detail: [outcome, report]
---

# Record-audited

Engine-owned: no agent claims this stage. `scripts/kb-record-audited.py` runs after `audit`, under the stage name `record-audited` when there are findings and `record-clean` when there are none. It reads the tip sha from the `schedule_state` field of its stdin object and stores it as the last audited sha in the data directory, through the `kb_audit_state` module. It prints `recorded`.

It records before the gate rather than at it so one idempotent write covers `done`, `filed`, `reviewed` and an item closed by hand. A missing or malformed `schedule_state`, or an unwritable data directory, parks the step with the reason and the stderr tail.
