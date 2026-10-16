---
script: scripts/record-raised.py
---

# Record-raised

Engine-owned: no agent claims this stage. `scripts/record-raised.py` runs the moment the item is filed. It reads the guard's `state` from the `schedule_state` field of its stdin object, upserts every issue into the `raised` table of `triage.db` in the data directory, and advances each repo's high-water mark to the larger of the stored and new value, in one transaction. It prints `recorded`.

It records before triage rather than at the gate so one idempotent write covers `triaged`, `abandoned` and an item closed by hand. A missing or unparseable `schedule_state`, or a locked database, parks the step with the reason and the stderr tail.
