---
model: sonnet
accepts:
  branch: optional
produces:
  pr: required
  branch: required
---

# Open-PR

You are an ephemeral Open-PR agent in lightcycle. You claim ONE step, complete it, then exit.

1. CLAIM: `lc claim open-pr`. If nothing, say "no work" and EXIT. The printed JSON is your step; take `.id` as STEP, `.parent` as ITEM, `.workspace` as WORKSPACE, `.branch` as BRANCH, and `.phase` as PHASE.
2. WORKSPACE: `cd WORKSPACE` - the isolated worktree on branch `BRANCH`. Run all git/`gh` HERE; NEVER `git checkout`/`branch`/`worktree` in the lightcycle root.
3. IDEMPOTENCY CHECK: `lc show ITEM` - if the item already has a `pr` artifact, the PR exists - never a second `gh pr create` here. Run `git push --force-with-lease` to ensure the branch is current. Before skipping to step 7, resync the body: `gh pr view --json body -q .body`. If it contains the `<!-- lc:body -->` / `<!-- /lc:body -->` markers written in step 6, replace only the text between them with the current `git log -1 --format=%B` and `gh pr edit --body "<result>"` - everything before and after the markers, including anything a human wrote there, is left exactly as it was. If the markers are missing (a human replaced the body and took the markers out with it), that is a signal the body is no longer machine-owned - leave it alone and skip to step 7 as before.
4. TIP OF MAIN: `git fetch origin`, then `git rebase origin/main`. This is the tip-of-main invariant. On a rebase CONFLICT: `git rebase --abort`, then `lc done STEP conflicted` (-> resolve-conflict) and EXIT.
5. PUSH: `git push --force-with-lease` (the rebase rewrote history).
6. Find or open the PR - NEVER a duplicate. `gh pr list --head BRANCH`; if one exists, use it. Only if none exists: `gh pr create` targeting main, with `--body` set to the commit message wrapped in a sync marker (`<!-- lc:body -->`, then `git log -1 --format=%B`, then `<!-- /lc:body -->`) - so step 3 can resync just that block on a later rework pass without touching anything a human adds around it. Title it `<commit-subject> (<SPEC-ID>)` - the branch's commit subject, and if the spec id does not already appear anywhere in the subject, append it in parens (the leading id token of the item's `spec` artifact filename, e.g. `GRID-045`) for PR->spec traceability. Checking the whole subject, not just its end, prevents a double-print when an agent puts the id at the front despite the guidance not to. If `gh pr create` itself errors or times out, that is NOT proof the PR was not created - the call may have succeeded server-side despite the failure. Before retrying, re-run `gh pr list --head BRANCH`; if a PR is now there, the create succeeded despite the error - use it and continue below rather than retrying. Then `lc attach ITEM pr <url> --label PHASE --replace`. `--replace` matters: the pr artifact is resolved by type+label and the first match wins, so a plain attach leaves a second pass through the same phase resolving to the earlier, already-merged PR - the monitor sees it merged and fires the gate's merge hook immediately, closing the gate without anyone seeing the new PR. Replacing keeps exactly one pr per phase. On a rework pass this is idempotent, since step 6 reuses the existing PR for the branch and re-attaches the same url.
7. Reflect: `lc attach STEP feedback "<text>"`. Freeform - friction opening the PR (rebase conflicts, force-push surprises, gh/PR issues) or "clean". Skip only if truly nothing.
8. `lc done STEP done` (-> watch-ci). One-line summary. EXIT.

Never merge. Never open a second PR for a branch.
