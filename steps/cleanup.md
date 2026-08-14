# Cleanup (you + driver)

The code PR for this pass is merged; tidy up. Unlike a generic `cleanup`, this does NOT close the item - one delivered work item is one pass through the loop, not the whole item. The item as a whole only ends once `audit-design` finds nothing left to remedy and reaches the fileless `done` terminal. Because the item stays open, `lc done ITEM merged` never runs in this workflow and never removes anything - every worktree/branch this pass minted (spec, feature, code) is still sitting on disk once the code PR merges, and a later pass mints fresh ones alongside them rather than reusing them. Tearing them down is this step's job, by hand, since nothing else in the loop does it. The step surfaces in `lc inbox`; the driver runs this skill to do the close-out with you.

1. CLAIM: `lc claim cleanup`. The printed JSON is this step; take `.id` as STEP, `.parent` as ITEM, and `.repo_path` as CODE_PATH (the target project's own checkout, outside any worktree - safe to run `git worktree` commands from). `lc show STEP` for which work item this pass just delivered (the `work-item` artifact), and `lc show ITEM` for this pass's `branch` artifacts (labels `spec`, `feature`, `code`) - all three are merged by now.
2. Remove each one's worktree and branch, from the repo that hosts it, never from the lightcycle root:
   - Specs repo (`lc specs-dir`): `git worktree list` there, find the entry whose branch matches the `spec`-labelled branch artifact, `git worktree remove <path> --force`, then `git branch -D <branch>`.
   - CODE_PATH: same for the `feature`-labelled branch, then the `code`-labelled branch (this step's own) - run both from CODE_PATH, not from inside the code-phase worktree itself, since a worktree cannot remove itself while you are standing in it.
3. `lc done STEP done --note "<work item just delivered>"` (-> `plan-next`) - forwards the note, so the next `plan-next` pass has a hint of what was just delivered (never authority - it re-reads the codebase either way).

Do NOT run `lc done ITEM merged` here - that closes the whole item, and more work may remain in the Blueprint's `plan/`.
