---
script: scripts/kb-cleanup.py
detail: [outcome, report]
---

# Cleanup

An engine-owned script stage: no agent claims it. The PR is merged and this terminal stage ends the flow. `scripts/kb-cleanup.py` runs in the item's worktree and checks `git status --porcelain`. Uncommitted changes fail the stage naming each path, so the engine parks it and leaves the worktree for a human. A clean tree prints `done`; the engine then completes the step, closes the item, removes its worktrees and deletes its branches.
