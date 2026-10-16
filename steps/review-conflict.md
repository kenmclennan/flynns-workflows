---
escalation: true
---

# Review-conflict (you + driver)

`resolve-conflict` tried to reconcile this item's branch with `origin/main` and escalated - either a semantic conflict it should not guess at, or a rebase whose tests kept failing after repeated attempts. A human finishes what the agent could not.

`review-conflict` only routes onward on `resolved` - closing it any other way, or leaving it as the item's only open step, ends the item outright rather than re-entering the PR/CI cycle.

1. `lc show STEP` - if `resolve-conflict` forwarded an escalation note, it explains what is ambiguous or what kept failing after a prior rebase attempt. If this step opened instead because the PR's own conflict-retry cap was hit directly, there may be no note - check the PR's conflict markers on the branch itself.
2. The item's branch is already checked out in its own worktree (`.worktrees/ITEM` in the target repo). `cd` there, `git fetch origin`, then `git rebase origin/main`.
3. Reconcile any conflicts by hand, preserving both sides' intent - the same discipline `resolve-conflict` itself follows. Run the repo's own test command to confirm the rebase is clean (read it from the repo - its CI workflow, README, or build file - never from memory).
4. Decide:
   - **Resolved** - force-push the rebased branch (`git push --force-with-lease`), then `lc done STEP resolved` - re-enters the PR/CI cycle the same way `resolve-conflict`'s own `resolved` outcome does.
   - **Abandon** - the conflict is not worth resolving, or the underlying change should not land - `lc done ITEM abandoned`, the item-level close, which also closes this step; do not additionally run the `resolved` outcome above.
   - **Leave it blocked** for a later look - `lc set STEP --state waiting --needs "<what a human must decide>" --reason "<what happened that led here>"`, then EXIT.

The `--note` on `lc done` and any `--needs` or `--reason` text you park with are read by a human or the next agent. They follow the standard below.

@include plain-language
