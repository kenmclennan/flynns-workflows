# flynns-workflows

A personal `lc` workflow origin (see `CLAUDE.md`).

| Workflow | Gates | Summary |
| --- | --- | --- |
| [`blueprint-delivery`](docs/blueprint-delivery.md) | spec PR, feature PR, code PR, plan PR | Delivers a whole Blueprint's `plan/` as one item by looping - one pass per work item through a spec/feature/code arc, then an adversarial design audit before closing. |
